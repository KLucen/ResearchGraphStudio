"""Lite P0 usage accounting and cache primitives.

The existing extraction, Query and P5 ledgers predate Lite and keep their
original wire shape.  This module presents one read model over those ledgers
and provides additive rows for the future A/B/D services.  It never stores
credentials or raw prompts.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.knowledge_models import ModelRun, Section
from researchgraph.lite_models import LiteCacheEntry, LiteTokenUsage
from researchgraph.models import AttachmentRevision, Job, Paper, now
from researchgraph.p5_models import P5ModelRun, P5Workflow
from researchgraph.query_models import QueryModelRun, QueryRun


class UsageKindView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_kind: str
    calls: int = 0
    retry_count: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    unknown_usage_calls: int = 0
    unrecorded_runs: int = 0
    unattributed_runs: int = 0
    calls_known: bool = True
    estimated_usage_calls: int = 0
    cost_estimate: float | None = None
    cost_known: bool = True


class LiteUsageView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    paper_id: str | None = None
    calls: int = 0
    retry_count: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    unknown_usage_calls: int = 0
    unrecorded_runs: int = 0
    unattributed_runs: int = 0
    calls_known: bool = True
    estimated_usage_calls: int = 0
    cost_estimate: float | None = None
    cost_known: bool = True
    by_kind: list[UsageKindView] = Field(default_factory=list)


@dataclass
class _Usage:
    task_kind: str
    calls: int = 0
    retry_count: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    unknown_usage_calls: int = 0
    unrecorded_runs: int = 0
    unattributed_runs: int = 0
    estimated_usage_calls: int = 0
    cost_estimate: float | None = 0.0
    cost_known: bool = True

    def add(
        self,
        *,
        calls: int = 0,
        retries: int = 0,
        cache_hits: int = 0,
        unknown_calls: int = 0,
        unrecorded_runs: int = 0,
        unattributed_runs: int = 0,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        usage_source: str = "unknown",
        cost_estimate: float | None = None,
    ) -> None:
        self.calls += max(calls, 0)
        self.retry_count += max(retries, 0)
        self.cache_hits += max(cache_hits, 0)
        self.unknown_usage_calls += max(unknown_calls, 0)
        self.unrecorded_runs += max(unrecorded_runs, 0)
        self.unattributed_runs += max(unattributed_runs, 0)
        if input_tokens is not None:
            self.input_tokens += max(input_tokens, 0)
        if output_tokens is not None:
            self.output_tokens += max(output_tokens, 0)
        if total_tokens is not None:
            self.total_tokens += max(total_tokens, 0)
        elif input_tokens is not None or output_tokens is not None:
            self.total_tokens += max(input_tokens or 0, 0) + max(output_tokens or 0, 0)
        if usage_source == "estimated":
            self.estimated_usage_calls += max(calls, 0)
        elif usage_source not in {"provider", "estimated"}:
            self.unknown_usage_calls += max(calls, 0)
        if cost_estimate is None:
            if calls or unknown_calls or unrecorded_runs or unattributed_runs:
                self.cost_known = False
        else:
            self.cost_estimate = (self.cost_estimate or 0.0) + max(cost_estimate, 0.0)


def _safe_int(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _usage_values(
    parameters: dict[str, Any] | None,
) -> tuple[int | None, int | None, int | None, str]:
    parameters = parameters or {}
    usage = parameters.get("usage")
    if not isinstance(usage, dict):
        return None, None, None, "unknown"
    input_tokens = _safe_int(usage.get("prompt_tokens", usage.get("input_tokens")))
    output_tokens = _safe_int(usage.get("completion_tokens", usage.get("output_tokens")))
    total_tokens = _safe_int(usage.get("total_tokens"))
    source = parameters.get("usage_source")
    if source not in {"provider", "estimated", "unknown"}:
        source = (
            "provider"
            if any(v is not None for v in (input_tokens, output_tokens, total_tokens))
            else "unknown"
        )
    return input_tokens, output_tokens, total_tokens, source


def _attempt_count(parameters: dict[str, Any] | None) -> tuple[int | None, int]:
    attempts = (parameters or {}).get("attempts")
    if isinstance(attempts, list) and attempts:
        return len(attempts), max(0, len(attempts) - 1)
    return None, 0


def _legacy_kind(prompt_name: str | None) -> str:
    prompt = (prompt_name or "legacy").strip()
    for prefix, kind in (
        ("P02", "legacy:p02"),
        ("P12", "legacy:p12"),
        ("P13", "legacy:p13"),
        ("P07", "legacy:d"),
    ):
        if prompt.startswith(prefix):
            return kind
    return "legacy:" + prompt[:32]


def _add_row(bucket: dict[str, _Usage], kind: str, **kwargs: Any) -> None:
    bucket.setdefault(kind, _Usage(kind)).add(**kwargs)


def _frozen_paper_ids(snapshot: dict[str, Any] | None) -> set[str] | None:
    """Resolve actual frozen input versions rather than the whole search scope."""

    context = (snapshot or {}).get("context")
    if not isinstance(context, dict) or not isinstance(context.get("source_versions"), list):
        return None
    versions = context["source_versions"]
    if not all(isinstance(v, dict) and isinstance(v.get("paper_id"), str) for v in versions):
        return None
    return {v["paper_id"] for v in versions}


def _add_unattributed(
    bucket: dict[str, _Usage], kind: str, parameters: dict[str, Any] | None
) -> None:
    calls, _ = _attempt_count(parameters)
    _add_row(
        bucket,
        kind,
        unrecorded_runs=1 if calls is None else 0,
        unattributed_runs=1,
    )


def aggregate_usage(
    session: Session, project_id: str, paper_id: str | None = None
) -> LiteUsageView:
    """Aggregate existing ledgers plus Lite rows without changing their history."""

    bucket: dict[str, _Usage] = {}
    paper_revision_ids: set[str] | None = None
    if paper_id is not None:
        paper_revision_ids = set(
            session.scalars(
                select(AttachmentRevision.id).where(AttachmentRevision.paper_id == paper_id)
            )
        )

    lite_stmt = select(LiteTokenUsage).where(LiteTokenUsage.project_id == project_id)
    if paper_id is not None:
        lite_stmt = lite_stmt.where(LiteTokenUsage.paper_id == paper_id)
    for row in session.scalars(lite_stmt):
        if row.cache_hit:
            _add_row(bucket, row.task_kind, cache_hits=1)
            continue
        _add_row(
            bucket,
            row.task_kind,
            calls=1,
            retries=row.retry_count,
            cache_hits=1 if row.cache_hit else 0,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            total_tokens=row.total_tokens,
            usage_source=row.usage_source,
            cost_estimate=row.cost_estimate,
        )

    legacy_stmt = (
        select(ModelRun, Job.project_id)
        .join(Job, Job.id == ModelRun.job_id)
        .where(Job.project_id == project_id)
    )
    for run, _project in session.execute(legacy_stmt):
        if paper_revision_ids is not None and run.document_version_id not in paper_revision_ids:
            continue
        calls, retries = _attempt_count(run.parameters)
        input_tokens, output_tokens, total_tokens, source = _usage_values(run.parameters)
        _add_row(
            bucket,
            _legacy_kind(run.prompt_name),
            calls=calls or 0,
            retries=retries,
            unrecorded_runs=1 if calls is None else 0,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            usage_source=source,
            cost_estimate=(run.parameters or {}).get("cost_estimate")
            if type((run.parameters or {}).get("cost_estimate")) in {int, float}
            else None,
        )

    query_stmt = (
        select(QueryModelRun, QueryRun)
        .join(QueryRun, QueryRun.id == QueryModelRun.query_run_id)
        .where(QueryModelRun.project_id == project_id)
    )
    for query_run, query in session.execute(query_stmt):
        if paper_id is not None:
            scope = _frozen_paper_ids(query.snapshot)
            if scope is not None and paper_id not in scope:
                continue
            if scope != {paper_id}:
                _add_unattributed(bucket, _legacy_kind(query_run.prompt_name), query_run.parameters)
                continue
        calls, retries = _attempt_count(query_run.parameters)
        input_tokens, output_tokens, total_tokens, source = _usage_values(query_run.parameters)
        _add_row(
            bucket,
            _legacy_kind(query_run.prompt_name),
            calls=calls or 0,
            retries=retries,
            unrecorded_runs=1 if calls is None else 0,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            usage_source=source,
            cost_estimate=(query_run.parameters or {}).get("cost_estimate")
            if type((query_run.parameters or {}).get("cost_estimate")) in {int, float}
            else None,
        )

    p5_stmt = (
        select(P5ModelRun, P5Workflow.project_id)
        .join(P5Workflow, P5Workflow.id == P5ModelRun.workflow_id)
        .where(P5Workflow.project_id == project_id)
    )
    for p5_run, _project in session.execute(p5_stmt):
        if paper_id is not None:
            workflow = session.get(P5Workflow, p5_run.workflow_id)
            scope = _frozen_paper_ids(workflow.snapshot if workflow is not None else None)
            if scope is not None and paper_id not in scope:
                continue
            if scope != {paper_id}:
                _add_unattributed(bucket, "legacy:p5", p5_run.parameters)
                continue
        calls, retries = _attempt_count(p5_run.parameters)
        input_tokens, output_tokens, total_tokens, source = _usage_values(p5_run.parameters)
        _add_row(
            bucket,
            "legacy:p5",
            calls=calls or 0,
            retries=retries,
            unrecorded_runs=1 if calls is None else 0,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            usage_source=source,
            cost_estimate=(p5_run.parameters or {}).get("cost_estimate")
            if type((p5_run.parameters or {}).get("cost_estimate")) in {int, float}
            else None,
        )

    totals = _Usage("all")
    for item in bucket.values():
        totals.calls += item.calls
        totals.retry_count += item.retry_count
        totals.cache_hits += item.cache_hits
        totals.input_tokens += item.input_tokens
        totals.output_tokens += item.output_tokens
        totals.total_tokens += item.total_tokens
        totals.unknown_usage_calls += item.unknown_usage_calls
        totals.unrecorded_runs += item.unrecorded_runs
        totals.unattributed_runs += item.unattributed_runs
        totals.estimated_usage_calls += item.estimated_usage_calls
        if item.cost_estimate is not None:
            totals.cost_estimate = (totals.cost_estimate or 0.0) + item.cost_estimate
        if not item.cost_known:
            totals.cost_known = False

    # A zero-call project has a precise zero; a project with calls but no pricing
    # information must keep cost explicitly unknown.
    cost = totals.cost_estimate if totals.cost_known else None
    return LiteUsageView(
        project_id=project_id,
        paper_id=paper_id,
        calls=totals.calls,
        retry_count=totals.retry_count,
        cache_hits=totals.cache_hits,
        input_tokens=totals.input_tokens,
        output_tokens=totals.output_tokens,
        total_tokens=totals.total_tokens,
        unknown_usage_calls=totals.unknown_usage_calls,
        unrecorded_runs=totals.unrecorded_runs,
        unattributed_runs=totals.unattributed_runs,
        calls_known=not (totals.unrecorded_runs or totals.unattributed_runs),
        estimated_usage_calls=totals.estimated_usage_calls,
        cost_estimate=cost,
        cost_known=totals.cost_known
        if (
            totals.calls
            or totals.unknown_usage_calls
            or totals.unrecorded_runs
            or totals.unattributed_runs
        )
        else True,
        by_kind=[
            UsageKindView.model_validate(
                {
                    **item.__dict__,
                    "cost_estimate": item.cost_estimate if item.cost_known else None,
                    "calls_known": not (item.unrecorded_runs or item.unattributed_runs),
                }
            )
            for item in sorted(bucket.values(), key=lambda v: v.task_kind)
        ],
    )


def record_usage(
    session: Session,
    *,
    project_id: str,
    task_kind: str,
    created_at: str | None = None,
    paper_id: str,
    document_version_id: str,
    section_id: str | None = None,
    task_run_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    retry_count: int = 0,
    cache_hit: bool = False,
    usage_source: str = "unknown",
    cost_estimate: float | None = None,
    status: str = "succeeded",
    reason_code: str | None = None,
    extra: dict[str, Any] | None = None,
) -> LiteTokenUsage:
    """Record one concrete provider request in the Lite ledger.

    Callers must invoke this once for every request that reached a provider,
    including each retry.  ``retry_count`` is therefore a per-request flag:
    ``0`` marks the initial request and ``1`` marks a retry request.  It is
    not a retry ordinal and must not contain a run-wide retry total; the
    aggregate sums the rows to keep ``calls`` equal to the actual request
    count and ``retry_count`` equal to the number of retry requests.
    """
    if usage_source not in {"provider", "estimated", "unknown"}:
        raise ValueError("usage_source must be provider, estimated or unknown")
    _validate_source_scope(session, project_id, paper_id, document_version_id, section_id)
    if type(retry_count) is not int or retry_count not in {0, 1}:
        raise ValueError("retry_count must be 0 for an initial request or 1 for a retry request")
    if cost_estimate is not None and (
        type(cost_estimate) not in {int, float}
        or not math.isfinite(cost_estimate)
        or cost_estimate < 0
    ):
        raise ValueError("cost_estimate must be finite and non-negative")
    for name, value in (
        ("input_tokens", input_tokens),
        ("output_tokens", output_tokens),
        ("total_tokens", total_tokens),
    ):
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f"{name} must be a non-negative integer")
    if cache_hit:
        if any(value is not None for value in (input_tokens, output_tokens, total_tokens)):
            raise ValueError("cache hits cannot record token usage")
        if cost_estimate is not None or retry_count:
            raise ValueError("cache hits cannot record cost or retries")
        usage_source, retry_count = "unknown", 0
    elif usage_source == "provider" and (input_tokens is None or output_tokens is None):
        raise ValueError("provider usage requires input_tokens and output_tokens")
    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        total_tokens = max(input_tokens or 0, 0) + max(output_tokens or 0, 0)
    row = LiteTokenUsage(
        id=str(uuid4()),
        project_id=project_id,
        paper_id=paper_id,
        document_version_id=document_version_id,
        section_id=section_id,
        task_run_id=task_run_id,
        task_kind=task_kind,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        retry_count=max(retry_count, 0),
        cache_hit=cache_hit,
        usage_source=usage_source,
        cost_estimate=cost_estimate,
        status=status,
        reason_code=reason_code,
        extra=extra or {},
        created_at=created_at or now(),
    )
    session.add(row)
    return row


_CACHE_FIELDS = (
    "project_id",
    "paper_id",
    "document_version_id",
    "section_id",
    "task_kind",
    "input_fingerprint",
    "prompt_version",
    "schema_version",
    "provider",
    "model",
    "config_fingerprint",
    "source_hash",
)


def _validate_source_scope(
    session: Session,
    project_id: str,
    paper_id: str,
    document_version_id: str,
    section_id: str | None = None,
    source_hash: str | None = None,
) -> None:
    paper = session.get(Paper, paper_id)
    version = session.get(AttachmentRevision, document_version_id)
    section = session.get(Section, section_id) if section_id is not None else None
    if paper is None or paper.project_id != project_id:
        raise ValueError("paper does not belong to this project")
    if version is None or version.paper_id != paper_id:
        raise ValueError("document version does not belong to this paper")
    if source_hash is not None and source_hash != version.sha256:
        raise ValueError("source hash does not match the document version")
    if section_id is not None and (
        section is None or section.document_version_id != document_version_id
    ):
        raise ValueError("section does not belong to this document version")


def cache_key(payload: dict[str, Any]) -> str:
    """Build a deterministic, source/version-scoped cache key."""

    required = tuple(field for field in _CACHE_FIELDS if field != "section_id")
    for field in required:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"cache key requires non-empty {field}")
    if set(payload) - set(_CACHE_FIELDS):
        raise ValueError("cache key contains unsupported fields; hash scoped inputs first")
    if "section_id" in payload and payload["section_id"] is not None:
        if not isinstance(payload["section_id"], str) or not payload["section_id"].strip():
            raise ValueError("cache key section_id must be non-empty when present")

    identity = {field: payload.get(field) for field in _CACHE_FIELDS}
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cache_matches(
    row: LiteCacheEntry,
    *,
    project_id: str,
    paper_id: str,
    document_version_id: str,
    task_kind: str | None = None,
    section_id: str | None = None,
) -> bool:
    return (
        row.project_id == project_id
        and row.paper_id == paper_id
        and row.document_version_id == document_version_id
        and (task_kind is None or row.task_kind == task_kind)
        and row.section_id == section_id
    )


def read_cache(
    session: Session,
    key: str,
    *,
    project_id: str,
    paper_id: str,
    document_version_id: str,
    task_kind: str | None = None,
    section_id: str | None = None,
    allow_stale: bool = False,
) -> LiteCacheEntry | None:
    row = session.get(LiteCacheEntry, key)
    if row is None or not _cache_matches(
        row,
        project_id=project_id,
        paper_id=paper_id,
        document_version_id=document_version_id,
        task_kind=task_kind,
        section_id=section_id,
    ):
        return None
    if row.state != "fresh" and not allow_stale:
        return None
    _validate_source_scope(
        session, project_id, paper_id, document_version_id, section_id, row.source_hash
    )
    identity = {field: getattr(row, field) for field in _CACHE_FIELDS}
    if cache_key(identity) != key:
        raise ValueError("cache entry identity does not match its key")
    return row


def write_cache(
    session: Session,
    *,
    cache_key_value: str,
    project_id: str,
    task_kind: str,
    input_fingerprint: str,
    response: dict[str, Any] | None,
    paper_id: str,
    document_version_id: str,
    prompt_version: str,
    schema_version: str,
    provider: str,
    model: str,
    config_fingerprint: str,
    source_hash: str,
    section_id: str | None = None,
) -> LiteCacheEntry:
    timestamp = now()
    identity = dict(
        project_id=project_id,
        paper_id=paper_id,
        document_version_id=document_version_id,
        section_id=section_id,
        task_kind=task_kind,
        input_fingerprint=input_fingerprint,
        prompt_version=prompt_version,
        schema_version=schema_version,
        provider=provider,
        model=model,
        config_fingerprint=config_fingerprint,
        source_hash=source_hash,
    )
    if cache_key(identity) != cache_key_value:
        raise ValueError("cache key does not match the supplied identity")
    _validate_source_scope(
        session, project_id, paper_id, document_version_id, section_id, source_hash
    )
    row = session.get(LiteCacheEntry, cache_key_value)
    if row is not None and not _cache_matches(
        row,
        project_id=project_id,
        paper_id=paper_id,
        document_version_id=document_version_id,
        task_kind=task_kind,
        section_id=section_id,
    ):
        raise ValueError("cache key identity conflicts with existing entry")
    values = dict(
        project_id=project_id,
        task_kind=task_kind,
        input_fingerprint=input_fingerprint,
        response=response,
        paper_id=paper_id,
        document_version_id=document_version_id,
        section_id=section_id,
        prompt_version=prompt_version,
        schema_version=schema_version,
        provider=provider,
        model=model,
        config_fingerprint=config_fingerprint,
        source_hash=source_hash,
        state="fresh",
        stale_reason=None,
        updated_at=timestamp,
    )
    if row is None:
        row = LiteCacheEntry(
            cache_key=cache_key_value,
            created_at=timestamp,
            hit_count=0,
            **values,
        )
        session.add(row)
    else:
        if any(getattr(row, field) != value for field, value in identity.items()):
            raise ValueError("cache key identity conflicts with existing entry")
        if row.response != response:
            raise ValueError("cache entry is immutable; use a new result identity")
    return row


def mark_cache_stale(
    session: Session,
    key: str,
    reason: str,
    *,
    project_id: str,
    paper_id: str,
    document_version_id: str,
    task_kind: str | None = None,
    section_id: str | None = None,
) -> bool:
    row = session.get(LiteCacheEntry, key)
    if row is None or not _cache_matches(
        row,
        project_id=project_id,
        paper_id=paper_id,
        document_version_id=document_version_id,
        task_kind=task_kind,
        section_id=section_id,
    ):
        return False
    _validate_source_scope(session, project_id, paper_id, document_version_id, section_id)
    row.state, row.stale_reason, row.updated_at = "stale", reason[:120], now()
    return True


def register_lite_usage_api(app: FastAPI, engine: Callable[[], Engine]) -> None:
    """Register the read-only Lite usage endpoint.

    ``engine`` is the app's callable engine provider, matching existing API
    registration functions.  GET never increments cache hits or writes usage.
    """

    @app.get("/api/v1/projects/{project_id}/lite/usage", response_model=LiteUsageView)
    def usage(project_id: str, paper_id: str | None = Query(default=None)) -> LiteUsageView:
        with Session(engine()) as session:
            from researchgraph.models import Project

            project = session.get(Project, project_id)
            if project is None:
                from researchgraph.knowledge_store import KnowledgeError

                raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")
            if paper_id is not None:
                from researchgraph.models import Paper

                paper = session.get(Paper, paper_id)
                if paper is None or paper.project_id != project_id:
                    from researchgraph.knowledge_store import KnowledgeError

                    raise KnowledgeError("PAPER_NOT_FOUND", "文献不存在")
            return aggregate_usage(session, project_id, paper_id)
