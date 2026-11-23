"""Lite usage accounting and source-scoped cache primitives.

Provider requests are represented by LiteTokenUsage rows or the model-document
batch dispatch ledger. Model-only imports do not require AttachmentRevision
rows, so their persisted dispatch slots are aggregated directly, without
writing synthetic document versions or counting both ledgers. Removed full-graph,
Query, Lint and Wiki jobs are not adapted. Credentials and raw prompts are never
returned here.
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

from researchgraph.document_batch_models import LlmDocumentBatch, LlmDocumentBatchRun
from researchgraph.import_plan_models import ImportPlanItem, ImportSession
from researchgraph.lite_models import ArchivedPaperUsage, LiteCacheEntry, LiteTokenUsage
from researchgraph.model_document_models import LlmDocumentOutput, LlmDocumentParse
from researchgraph.models import AttachmentRevision, Job, Paper, Section, now
from researchgraph.storage import read_session


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
    calls_known: bool = True

    def merge_summary(self, other: UsageKindView) -> None:
        self.calls += other.calls
        self.retry_count += other.retry_count
        self.cache_hits += other.cache_hits
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.total_tokens += other.total_tokens
        self.unknown_usage_calls += other.unknown_usage_calls
        self.unrecorded_runs += other.unrecorded_runs
        self.unattributed_runs += other.unattributed_runs
        self.estimated_usage_calls += other.estimated_usage_calls
        self.calls_known = self.calls_known and other.calls_known
        self.cost_known = self.cost_known and other.cost_known
        self.cost_estimate = (self.cost_estimate or 0.0) + (other.cost_estimate or 0.0)

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
        if unrecorded_runs or unattributed_runs:
            self.calls_known = False
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
    session: Session,
    project_id: str | None,
    paper_id: str | None = None,
    *,
    include_knowledge: bool = True,
    document_job_ids: set[str] | None = None,
) -> LiteUsageView:
    filters = []
    if project_id is not None:
        filters.append(LiteTokenUsage.project_id == project_id)
    if paper_id is not None:
        filters.append(LiteTokenUsage.paper_id == paper_id)
    rows = session.scalars(select(LiteTokenUsage).where(*filters)).all()
    model_outputs = _model_output_usage(session, project_id, paper_id)
    output_identities = {
        kind: {
            identity
            for output, requests, _unknown in model_outputs
            if output.item_kind == kind
            for identity in ([output.id] + [str(request["job_id"]) for request in requests])
            if requests
        }
        for kind in {output.item_kind for output, _requests, _unknown in model_outputs}
    }
    batch_filters = []
    if project_id is not None:
        batch_filters.append(Job.project_id == project_id)
    batch_rows = session.execute(
        select(LlmDocumentBatch, LlmDocumentBatchRun, Job)
        .join(LlmDocumentBatchRun, LlmDocumentBatch.run_id == LlmDocumentBatchRun.id)
        .join(Job, LlmDocumentBatchRun.job_id == Job.id)
        .where(*batch_filters)
    ).all()
    scoped_batches = [
        (batch, run, job)
        for batch, run, job in batch_rows
        if (
            job.id in document_job_ids
            if document_job_ids is not None
            else paper_id is None
            or (isinstance(job.payload, dict) and job.payload.get("paper_id") == paper_id)
        )
    ]
    # Batch checkpoints are the authoritative ledger for this task kind. A
    # separately recorded row with the exact same run/batch/job identity must
    # not count the same dispatch twice. Unrelated historical rows stay intact.
    batch_requests = [(batch, _batch_requests(batch)) for batch, _run, _job in scoped_batches]
    dispatched_ids = {batch.id for batch, requests in batch_requests if requests}
    batch_identities = {
        identity
        for batch, run, job in scoped_batches
        if batch.id in dispatched_ids
        for identity in (batch.id, run.id, job.id)
    }
    bucket: dict[str, _Usage] = {}
    totals = _Usage("all")
    for row in rows:
        if row.status == "not_sent" and (row.extra or {}).get("generation_request_sent") is False:
            # A deterministic ConfiguredProvider preflight can fail after the
            # send slot was reserved. Preserve that slot, but it sent no generation.
            continue
        if _duplicates_batch_usage(row, batch_identities) or _duplicates_output_usage(
            row, output_identities
        ):
            continue
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
    for _batch, requests in batch_requests:
        if not requests:
            continue
        item = bucket.setdefault("llm_document_parse", _Usage("llm_document_parse"))
        for request in requests:
            usage = request.get("usage")
            safe = (
                {
                    key: value
                    for key, value in usage.items()
                    if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                    and type(value) is int
                    and value >= 0
                }
                if isinstance(usage, dict)
                else {}
            )
            source = (
                "provider"
                if request.get("usage_source") == "provider"
                and {"prompt_tokens", "completion_tokens"} <= safe.keys()
                else "unknown"
            )
            for target in (item, totals):
                target.add(
                    calls=1,
                    retries=int(request.get("purpose") == "repair"),
                    input_tokens=safe.get("prompt_tokens"),
                    output_tokens=safe.get("completion_tokens"),
                    total_tokens=safe.get("total_tokens"),
                    usage_source=source,
                    # The batch ledger has no price receipt. Token counts are
                    # not a basis for inventing zero or estimated charges.
                    cost_estimate=None,
                )
    for output, requests, unknown in model_outputs:
        if not requests and not unknown:
            continue
        item = bucket.setdefault(output.item_kind, _Usage(output.item_kind))
        for request in requests:
            usage = request.get("usage")
            safe = (
                {
                    key: value
                    for key, value in usage.items()
                    if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                    and type(value) is int
                    and value >= 0
                }
                if isinstance(usage, dict)
                else {}
            )
            source = (
                "provider"
                if request.get("usage_source") == "provider"
                and {"prompt_tokens", "completion_tokens"} <= safe.keys()
                else "unknown"
            )
            for target in (item, totals):
                target.add(
                    calls=1,
                    retries=int(request.get("purpose") == "repair" or request["attempt"] > 1),
                    input_tokens=safe.get("prompt_tokens"),
                    output_tokens=safe.get("completion_tokens"),
                    total_tokens=safe.get("total_tokens"),
                    usage_source=source,
                    cost_estimate=None,
                )
        if unknown:
            for target in (item, totals):
                target.add(unrecorded_runs=1, cost_estimate=None)
    if paper_id is None:
        archived = select(ArchivedPaperUsage.by_kind)
        if project_id is not None:
            archived = archived.where(ArchivedPaperUsage.project_id == project_id)
        for summaries in session.scalars(archived):
            for summary in summaries:
                received = UsageKindView.model_validate(summary)
                bucket.setdefault(received.task_kind, _Usage(received.task_kind)).merge_summary(
                    received
                )
                totals.merge_summary(received)
    if include_knowledge:
        _add_knowledge_usage(session, bucket, totals, project_id, paper_id)
    values = {
        **totals.__dict__,
        "cost_estimate": totals.cost_estimate if totals.cost_known else None,
    }
    values.pop("task_kind")
    return LiteUsageView(
        project_id=project_id or "all",
        paper_id=paper_id,
        **values,
        by_kind=[
            UsageKindView.model_validate(
                {**item.__dict__, "cost_estimate": item.cost_estimate if item.cost_known else None}
            )
            for item in sorted(bucket.values(), key=lambda x: x.task_kind)
        ],
    )


def preserve_paper_usage(session: Session, paper: Paper, document_job_ids: set[str]) -> None:
    """Freeze deduplicated counters in the transaction that deletes their owners."""
    view = aggregate_usage(
        session,
        paper.project_id,
        paper.id,
        include_knowledge=False,
        document_job_ids=document_job_ids,
    )
    if view.by_kind:
        session.add(
            ArchivedPaperUsage(
                id=str(uuid4()),
                project_id=paper.project_id,
                by_kind=[item.model_dump() for item in view.by_kind],
            )
        )


def _add_knowledge_usage(
    session: Session,
    bucket: dict[str, _Usage],
    totals: _Usage,
    project_id: str | None,
    paper_id: str | None,
) -> None:
    from researchgraph.knowledge_connection_models import (
        KnowledgeConnectionRequest,
        KnowledgeConnectionRun,
        KnowledgeUsageTombstone,
    )
    from researchgraph.knowledge_extraction_models import KnowledgeExtractionRun

    receipts: list[tuple[str, str | None, str | None, dict[str, Any], int, int]] = []
    for extraction in session.scalars(select(KnowledgeExtractionRun)):
        receipts.append(
            (
                "knowledge_extract",
                extraction.source_project_id,
                extraction.paper_id,
                extraction.usage_json,
                int(extraction.request_sent),
                int(extraction.usage_json.get("cache_hit", False)),
            )
        )
    for request, run in session.execute(
        select(KnowledgeConnectionRequest, KnowledgeConnectionRun).join(
            KnowledgeConnectionRun, KnowledgeConnectionRun.id == KnowledgeConnectionRequest.run_id
        )
    ):
        receipts.append(
            (
                "knowledge_connect",
                run.project_id,
                run.source_paper_id,
                {**request.usage_json, "retry_count": int(run.previous_run_id is not None)},
                int(request.sent_at is not None),
                0,
            )
        )
    for tombstone in session.scalars(select(KnowledgeUsageTombstone)):
        receipts.append((tombstone.task_kind, None, None, tombstone.usage_json, 1, 0))
    for kind, source_project, source_paper, usage, calls, cache_hits in receipts:
        if (
            (project_id is not None and source_project != project_id)
            or (paper_id is not None and source_paper != paper_id)
            or not (calls or cache_hits)
        ):
            continue
        normalized = {
            **usage,
            "prompt_tokens": usage.get("prompt_tokens", usage.get("input_tokens")),
            "completion_tokens": usage.get("completion_tokens", usage.get("output_tokens")),
        }
        safe = {
            k: v
            for k, v in normalized.items()
            if k in {"prompt_tokens", "completion_tokens", "total_tokens"}
            and type(v) is int
            and v >= 0
        }
        item = bucket.setdefault(kind, _Usage(kind))
        for target in (item, totals):
            target.add(
                calls=calls,
                retries=int(usage.get("retry_count", 0)),
                cache_hits=cache_hits,
                input_tokens=safe.get("prompt_tokens"),
                output_tokens=safe.get("completion_tokens"),
                total_tokens=safe.get("total_tokens"),
                usage_source="provider"
                if {"prompt_tokens", "completion_tokens"} <= safe.keys()
                else "unknown",
                cost_estimate=None,
            )


def aggregate_knowledge_usage(session: Session) -> LiteUsageView:
    bucket: dict[str, _Usage] = {}
    totals = _Usage("all")
    _add_knowledge_usage(session, bucket, totals, None, None)
    values = {
        **totals.__dict__,
        "cost_estimate": totals.cost_estimate if totals.cost_known else None,
    }
    values.pop("task_kind")
    return LiteUsageView(
        project_id="library:personal",
        **values,
        by_kind=[
            UsageKindView.model_validate(
                {**item.__dict__, "cost_estimate": item.cost_estimate if item.cost_known else None}
            )
            for item in sorted(bucket.values(), key=lambda item: item.task_kind)
        ],
    )


def _duplicates_output_usage(row: LiteTokenUsage, identities: dict[str, set[str]]) -> bool:
    if row.cache_hit:
        return False
    candidates = (
        set().union(*identities.values())
        if row.task_kind == "llm_document_postprocess"
        else identities.get(row.task_kind, set())
    )
    if row.task_run_id in candidates:
        return True
    extra = row.extra if isinstance(row.extra, dict) else {}
    return any(
        isinstance(extra.get(key), str) and extra[key] in candidates
        for key in ("model_document_output_id", "document_output_id", "output_id", "job_id")
    )


def _model_output_usage(
    db: Session, project_id: str | None, paper_id: str | None
) -> list[tuple[LlmDocumentOutput, list[dict[str, Any]], bool]]:
    """Read concrete postprocess dispatches without inventing legacy calls.

    A receipt is attributed through its actual Job and persisted source, never
    through model-returned IDs. Duplicate sent/received snapshots of one slot
    count once. Legacy outputs without receipts report an unknown run count.
    """
    rows = db.execute(
        select(LlmDocumentOutput, LlmDocumentParse, ImportSession)
        .join(LlmDocumentParse, LlmDocumentOutput.parse_id == LlmDocumentParse.id)
        .join(ImportSession, LlmDocumentOutput.import_session_id == ImportSession.id)
        .where(*([ImportSession.project_id == project_id] if project_id else []))
    ).all()
    jobs = {
        job.id: job
        for job in db.scalars(
            select(Job).where(
                Job.kind == "llm_document_postprocess",
                *([Job.project_id == project_id] if project_id else []),
            )
        ).all()
    }
    result: list[tuple[LlmDocumentOutput, list[dict[str, Any]], bool]] = []
    for output, parse, source in rows:
        if parse.import_session_id != source.id or output.item_kind not in {
            "paper_overview",
            "paper_reading",
            "translation",
        }:
            continue
        owner_id = source.source_snapshot.get("paper_id")
        if not owner_id:
            item = db.scalar(
                select(ImportPlanItem).where(
                    ImportPlanItem.session_id == source.id,
                    ImportPlanItem.item_kind == "document_parse",
                )
            )
            parent = db.get(Job, item.job_id) if item and item.job_id else None
            owner_id = (parent.payload or {}).get("paper_id") if parent else None
        owner = db.get(Paper, owner_id) if isinstance(owner_id, str) and owner_id else None
        if (
            owner is None
            or owner.project_id != source.project_id
            or (paper_id is not None and owner.id != paper_id)
        ):
            continue
        metadata = output.usage if isinstance(output.usage, dict) else {}
        raw = metadata.get("requests")
        slots: dict[tuple[str, int, str], dict[str, Any]] = {}
        suspicious = False
        for entry in raw if isinstance(raw, list) else []:
            if not isinstance(entry, dict) or entry.get("status") == "not_sent":
                continue
            job_id = entry.get("job_id")
            attempt, purpose = entry.get("attempt"), entry.get("purpose")
            job = jobs.get(job_id) if isinstance(job_id, str) else None
            payload = job.payload if job and isinstance(job.payload, dict) else {}
            if (
                job is None
                or job.project_id != source.project_id
                or payload.get("import_session_id") != source.id
                or payload.get("llm_document_parse_id") != parse.id
                or payload.get("item_kind") != output.item_kind
                or (payload.get("output_id") is not None and payload["output_id"] != output.id)
                or payload.get("paper_id") != owner.id
                or type(attempt) is not int
                or attempt < 0
                or purpose not in {"generate", "repair"}
                or entry.get("status") not in {"sent", "received", "failed"}
            ):
                suspicious = True
                continue
            slot = (job.id, attempt, purpose)
            # A crash/recovery snapshot may contain the same dispatch twice.
            # Prefer the last completed receipt over an unfinished sent marker.
            previous = slots.get(slot)
            if previous is None or entry.get("status") != "sent":
                slots[slot] = entry
        has_legacy_response = bool(output.raw_response) or any(
            key in metadata
            for key in ("prompt_tokens", "completion_tokens", "input_tokens", "output_tokens")
        )
        unknown = suspicious or (not slots and has_legacy_response)
        result.append((output, list(slots.values()), unknown))
    return result


def _duplicates_batch_usage(row: LiteTokenUsage, identities: set[str]) -> bool:
    if row.task_kind != "llm_document_parse" or row.cache_hit or not identities:
        return False
    if row.task_run_id in identities:
        return True
    metadata = row.extra if isinstance(row.extra, dict) else {}
    return any(
        isinstance(metadata.get(key), str) and metadata[key] in identities
        for key in (
            "document_batch_id",
            "document_batch_run_id",
            "batch_id",
            "batch_run_id",
            "job_id",
        )
    )


def _batch_requests(batch: LlmDocumentBatch) -> list[dict[str, Any]]:
    """Read concrete dispatch receipts, retaining unknown in-flight slots."""

    usage = batch.usage if isinstance(batch.usage, dict) else {}
    raw = usage.get("requests")
    entries = (
        [
            entry
            for entry in raw
            if isinstance(entry, dict)
            and entry.get("purpose") in {"extract", "repair", "boundary"}
            and entry.get("status") in {"unknown", "received", "uncertain"}
        ]
        if isinstance(raw, list)
        else []
    )
    # request_count is committed at dispatch before network I/O. If a crash
    # left an incomplete usage receipt, count that slot with unknown usage.
    count = batch.request_count if type(batch.request_count) is int else 0
    not_sent = (
        sum(isinstance(entry, dict) and entry.get("status") == "not_sent" for entry in raw)
        if isinstance(raw, list)
        else 0
    )
    missing = max(0, count - not_sent - len(entries))
    repairs = batch.repair_attempts if type(batch.repair_attempts) is int else 0
    missing_repairs = max(0, repairs - sum(entry.get("purpose") == "repair" for entry in entries))
    for index in range(missing):
        entries.append(
            {
                "usage_source": "unknown",
                "purpose": "repair" if index < missing_repairs else batch.kind,
            }
        )
    return entries


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

    @app.get("/api/v1/lite/usage", response_model=LiteUsageView)
    def global_usage() -> LiteUsageView:
        with read_session(engine()) as session:
            return aggregate_usage(session, None)

    @app.get("/api/v1/projects/{project_id}/lite/usage", response_model=LiteUsageView)
    def usage(project_id: str, paper_id: str | None = Query(default=None)) -> LiteUsageView:
        with read_session(engine()) as session:
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
