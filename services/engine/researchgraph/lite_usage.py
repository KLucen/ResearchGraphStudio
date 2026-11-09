"""Lite usage accounting and source-scoped cache primitives.

Every provider request is represented by one ``LiteTokenUsage`` row.  The
module intentionally has no legacy ledger adapters: Lite's usage endpoint is
derived only from its own rows and therefore cannot silently count removed
full-graph, Query, Lint, or Wiki jobs.  Credentials and raw prompts are never
stored here.
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

from researchgraph.lite_models import LiteCacheEntry, LiteTokenUsage
from researchgraph.models import AttachmentRevision, Paper, Section, now


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
            if calls or unrecorded_runs or unattributed_runs:
                self.cost_known = False
        else:
            self.cost_estimate = (self.cost_estimate or 0.0) + max(cost_estimate, 0.0)


def aggregate_usage(
    session: Session, project_id: str, paper_id: str | None = None
) -> LiteUsageView:
    rows = session.scalars(
        select(LiteTokenUsage).where(
            LiteTokenUsage.project_id == project_id,
            *([LiteTokenUsage.paper_id == paper_id] if paper_id else []),
        )
    ).all()
    bucket: dict[str, _Usage] = {}
    totals = _Usage("all")
    for row in rows:
        item = bucket.setdefault(row.task_kind, _Usage(row.task_kind))
        for target in (item, totals):
            target.add(
                calls=0 if row.cache_hit else 1,
                retries=row.retry_count,
                cache_hits=int(row.cache_hit),
                input_tokens=row.input_tokens,
                output_tokens=row.output_tokens,
                total_tokens=row.total_tokens,
                usage_source=row.usage_source,
                cost_estimate=row.cost_estimate,
            )
    values = {
        **totals.__dict__,
        "cost_estimate": totals.cost_estimate if totals.cost_known else None,
    }
    values.pop("task_kind")
    return LiteUsageView(
        project_id=project_id,
        paper_id=paper_id,
        **values,
        by_kind=[
            UsageKindView.model_validate(
                {**item.__dict__, "cost_estimate": item.cost_estimate if item.cost_known else None}
            )
            for item in sorted(bucket.values(), key=lambda x: x.task_kind)
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
                from researchgraph.core import KnowledgeError

                raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")
            if paper_id is not None:
                from researchgraph.models import Paper

                paper = session.get(Paper, paper_id)
                if paper is None or paper.project_id != project_id:
                    from researchgraph.core import KnowledgeError

                    raise KnowledgeError("PAPER_NOT_FOUND", "文献不存在")
            return aggregate_usage(session, project_id, paper_id)
