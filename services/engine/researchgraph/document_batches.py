"""Sequential document batches with durable dispatch slots and conservative assembly."""

from __future__ import annotations

import asyncio
import base64
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from researchgraph.document_batch_contracts import (
    BatchResult,
    BatchSegment,
    BatchValidationError,
    BoundaryResult,
    validate_batch,
    validate_boundary,
)
from researchgraph.document_batch_models import (
    LlmDocumentBatch,
    LlmDocumentBatchFailure,
    LlmDocumentBatchRun,
)
from researchgraph.document_batch_recovery import (
    BOUNDARY_PROMPT_VERSION,
    legacy_boundary_recovery,
    publication_retry_available,
)
from researchgraph.document_batch_transport import (
    assert_source_version,
    prepare_document,
    slice_pdf,
)
from researchgraph.document_transport import (
    DocumentRenderCancelled,
    DocumentRenderDeadline,
    DocumentRenderError,
)
from researchgraph.import_plan_models import ImportSession
from researchgraph.model_document_contracts import ModelDocumentParseInput
from researchgraph.models import Job, now
from researchgraph.providers import ConfiguredProvider, DocumentRequestCancelled, ProviderError
from researchgraph.storage import read_session


def _rows(db: Session, run_id: str) -> list[LlmDocumentBatch]:
    return list(
        db.scalars(
            select(LlmDocumentBatch)
            .where(LlmDocumentBatch.run_id == run_id)
            .order_by(LlmDocumentBatch.ordinal, LlmDocumentBatch.kind)
        ).all()
    )


def _integrity_failure_diagnostics(engine: Engine, exc: IntegrityError) -> dict[str, Any]:
    """Return only stable driver codes; SQL text and bound values are excluded."""

    name = getattr(exc.orig, "sqlite_errorname", None)
    allowed = {
        "SQLITE_CONSTRAINT",
        "SQLITE_CONSTRAINT_CHECK",
        "SQLITE_CONSTRAINT_FOREIGNKEY",
        "SQLITE_CONSTRAINT_NOTNULL",
        "SQLITE_CONSTRAINT_PRIMARYKEY",
        "SQLITE_CONSTRAINT_UNIQUE",
        "SQLITE_CONSTRAINT_ROWID",
        "SQLITE_CONSTRAINT_DATATYPE",
        "SQLITE_CONSTRAINT_TRIGGER",
    }
    safe_name = name if isinstance(name, str) and name in allowed else None
    category = {
        "SQLITE_CONSTRAINT_CHECK": "check",
        "SQLITE_CONSTRAINT_FOREIGNKEY": "foreign_key",
        "SQLITE_CONSTRAINT_NOTNULL": "not_null",
        "SQLITE_CONSTRAINT_PRIMARYKEY": "primary_key",
        "SQLITE_CONSTRAINT_UNIQUE": "unique",
    }.get(safe_name or "", "constraint")
    code = getattr(exc.orig, "sqlite_errorcode", None)
    return {
        "database_dialect": engine.dialect.name,
        **({"sqlite_errorcode": code} if type(code) is int else {}),
        **({"sqlite_errorname": safe_name} if safe_name else {}),
        "constraint_category": category,
    }


def _progress(
    db: Session,
    job: Job,
    run: LlmDocumentBatchRun,
    *,
    current: LlmDocumentBatch | None = None,
    phase: str = "extracting",
) -> None:
    rows = _rows(db, run.id)
    extracts = [r for r in rows if r.kind == "extract"]
    boundaries = [r for r in rows if r.kind == "boundary"]
    data: dict[str, Any] = {
        "total": len(extracts),
        "completed": sum(r.status == "validated" for r in extracts),
        "requests_sent": sum(r.request_count for r in rows),
        "request_budget": run.settings["request_budget"],
        "repairs_used": sum(r.repair_attempts for r in rows),
        "boundaries_completed": sum(r.status == "validated" for r in boundaries),
        "boundaries_total": max(0, len(extracts) - 1),
        "phase": phase,
    }
    if current is not None:
        data.update(
            current=current.ordinal + 1,
            page_start=current.page_start,
            page_end=current.page_end,
            validation_errors=current.validation_errors,
            current_kind=current.kind,
        )
    job.result = {**(job.result or {}), "document_batches": data}
    job.updated_at = run.updated_at = now()


def _load_plan(engine: Engine, job_id: str) -> tuple[dict[str, Any], dict[str, Any], int]:
    with read_session(engine) as db:
        job = db.get(Job, job_id)
        if job is None or job.status != "running":
            raise DocumentRequestCancelled
        payload = dict(job.payload or {})
        session = db.get(ImportSession, str(payload.get("import_session_id", "")))
        if session is None:
            raise ProviderError("batch", "模型解析导入会话不存在")
        return payload, dict(session.plan), job.attempt


def _prepare_run(
    engine: Engine,
    job_id: str,
    payload: dict[str, Any],
    plan: dict[str, Any],
    version: dict[str, Any],
    ranges: list[dict[str, int]],
    attempt: int,
) -> str:
    with Session(engine) as db, db.begin():
        job = db.get(Job, job_id)
        if job is None or job.status != "running":
            raise DocumentRequestCancelled
        run = db.scalar(
            select(LlmDocumentBatchRun).where(
                LlmDocumentBatchRun.import_session_id == payload["import_session_id"]
            )
        )
        if run is None:
            count = len(ranges)
            settings = {
                k: plan.get(k, default)
                for k, default in (
                    ("pages_per_batch", 5),
                    ("allow_format_repair", False),
                    ("allow_boundary_review", True),
                )
            }
            settings.update(
                version="document-batch-1",
                provider_snapshot=payload.get("provider_snapshot"),
                ranges=ranges,
                job_attempt=attempt,
                request_budget=count
                + (count if settings["allow_format_repair"] else 0)
                + (max(0, count - 1) if settings["allow_boundary_review"] else 0),
            )
            run = LlmDocumentBatchRun(
                id=str(uuid4()),
                import_session_id=payload["import_session_id"],
                job_id=job_id,
                source_version=version,
                settings=settings,
                page_count=version["page_count"],
                status="running",
                created_at=now(),
                updated_at=now(),
            )
            db.add(run)
            db.flush()
            for r in ranges:
                db.add(
                    LlmDocumentBatch(
                        id=str(uuid4()),
                        run_id=run.id,
                        ordinal=r["index"],
                        kind="extract",
                        page_start=r["page_start"],
                        page_end=r["page_end"],
                        send_start=r["send_start"],
                        send_end=r["send_end"],
                        status="pending",
                        attempts=0,
                        repair_attempts=0,
                        request_count=0,
                        result_json=None,
                        validation_errors=[],
                        usage={},
                        request_metadata={},
                        created_at=now(),
                        updated_at=now(),
                    )
                )
            db.flush()
        else:
            if run.source_version != version or run.job_id != job_id:
                raise ProviderError(
                    "batch_source", "源 PDF 版本或任务身份变化，已停止续接；请创建新解析"
                )
            if (
                run.settings.get("version") != "document-batch-1"
                or run.settings.get("provider_snapshot") != payload.get("provider_snapshot")
                or run.settings.get("ranges") != ranges
            ):
                raise ProviderError(
                    "batch_source", "模型快照、协议或批次范围变化，已停止复用检查点"
                )
            for key, default in (
                ("pages_per_batch", 5),
                ("allow_format_repair", False),
                ("allow_boundary_review", True),
            ):
                if run.settings.get(key) != plan.get(key, default):
                    raise ProviderError("batch_source", "批次计划已变化，请使用新的模型解析任务")
            rows = _rows(db, run.id)
            actual_ranges = [
                {
                    "index": r.ordinal,
                    "page_start": r.page_start,
                    "page_end": r.page_end,
                    "send_start": r.send_start,
                    "send_end": r.send_end,
                }
                for r in rows
                if r.kind == "extract"
            ]
            if actual_ranges != ranges:
                raise ProviderError("batch_source", "批次检查点范围不一致，已停止发送")
            unfinished = [r for r in rows if r.status != "validated" and r.attempts]
            if unfinished and attempt <= run.settings.get("job_attempt", attempt):
                raise ProviderError(
                    "batch_resume", "有已发送但未完成的批次；请显式继续，可能产生额外费用"
                )
            if unfinished:
                # Only an explicit new parent attempt authorizes another dispatch.
                run.settings = {
                    **run.settings,
                    "job_attempt": attempt,
                    "request_budget": run.settings["request_budget"] + len(unfinished),
                }
                for row in unfinished:
                    if row.attempts >= 3 and not legacy_boundary_recovery(row):
                        raise ProviderError(
                            "batch_budget", "该批次已达到3次显式执行上限，请检查配置后创建新任务"
                        )
                    row.status = "pending"
                    row.error_code = None
            run.status = "running"
        _progress(db, job, run, phase="planned")
        job.stage = "document_batching"
        return run.id


def _checkpoint(engine: Engine, batch_id: str) -> dict[str, Any]:
    with read_session(engine) as db:
        row = db.get(LlmDocumentBatch, batch_id)
        if row is None:
            raise ProviderError("batch", "批次检查点不存在")
        return {
            k: getattr(row, k)
            for k in (
                "id",
                "ordinal",
                "kind",
                "page_start",
                "page_end",
                "send_start",
                "send_end",
                "status",
                "result_json",
                "repair_attempts",
            )
        }


class _Dispatch:
    def __init__(
        self,
        engine: Engine,
        job_id: str,
        batch_id: str,
        purpose: str,
        path: Path,
        version: dict[str, Any],
        repair_raw: str | None = None,
    ) -> None:
        from researchgraph.model_document_api import _DocumentRequestProgress

        self.engine, self.job_id, self.batch_id = engine, job_id, batch_id
        self.purpose, self.path, self.version = purpose, path, version
        self.repair_raw = repair_raw
        self.sent = False
        self.progress = _DocumentRequestProgress(engine, job_id)

    def before_send(self) -> bool:
        from researchgraph.model_document_api import _document_job_running

        assert_source_version(self.path, self.version)
        return _document_job_running(self.engine, self.job_id)

    def __call__(self, stage: str, metadata: dict[str, Any]) -> None:
        if stage == "document_connecting" and not self.sent:
            if not self.before_send():
                raise DocumentRequestCancelled
            with Session(self.engine) as db, db.begin():
                job, row = db.get(Job, self.job_id), db.get(LlmDocumentBatch, self.batch_id)
                if job is None or job.status != "running" or row is None:
                    raise DocumentRequestCancelled
                run = db.get(LlmDocumentBatchRun, row.run_id)
                assert run is not None
                if (
                    sum(r.request_count for r in _rows(db, run.id))
                    >= run.settings["request_budget"]
                ):
                    raise ProviderError("batch_budget", "已达到本次授权的模型请求预算")
                if self.purpose == "repair":
                    from researchgraph.document_format_repair import (
                        explicit_repair_authorized,
                        has_format_repair_intent,
                    )

                    explicit = explicit_repair_authorized(db, job, row)
                    retained = db.get(LlmDocumentBatchFailure, row.id)
                    if (
                        not (run.settings["allow_format_repair"] or explicit)
                        or row.repair_attempts >= 1
                        or (has_format_repair_intent(job) and not explicit)
                        or (
                            explicit
                            and (retained is None or retained.raw_response != self.repair_raw)
                        )
                    ):
                        raise ProviderError("batch_budget", "本批格式修复未授权或已经使用一次")
                    row.repair_attempts += 1
                    failure = db.get(LlmDocumentBatchFailure, row.id)
                    if failure is not None:
                        failure.state, failure.updated_at = "sent", now()
                else:
                    row.attempts += 1
                row.request_count += 1
                row.status = "sent"
                entries = list((row.usage or {}).get("requests", []))
                entry: dict[str, Any] = {
                    "purpose": self.purpose,
                    "status": "unknown",
                    "usage_source": "unknown",
                    "started_at": now(),
                }
                if self.purpose == "boundary":
                    # Persist use of the corrected request before POST, including
                    # crashes/timeouts. Never reset the three historical attempts.
                    entry["boundary_prompt_version"] = BOUNDARY_PROMPT_VERSION
                    row.request_metadata = {
                        **(row.request_metadata or {}),
                        "boundary_prompt_version": BOUNDARY_PROMPT_VERSION,
                    }
                entries.append(entry)
                row.usage = {"requests": entries}
                row.updated_at = now()
                _progress(
                    db,
                    job,
                    run,
                    current=row,
                    phase="repairing"
                    if self.purpose == "repair"
                    else "boundary"
                    if row.kind == "boundary"
                    else "extracting",
                )
            self.sent = True
        self.progress(stage, metadata)

    def finish(self, provider: Any, status: str) -> None:
        from researchgraph.model_document_api import _safe_document_request_metadata

        metadata = self.progress.summary(provider)
        with Session(self.engine) as db, db.begin():
            row = db.get(LlmDocumentBatch, self.batch_id)
            if row is None:
                return
            if self.sent:
                row.request_metadata = _safe_document_request_metadata(metadata)
                entries = list((row.usage or {}).get("requests", []))
                entry = dict(entries[-1])
                usage = getattr(provider, "usage", {})
                safe = (
                    {
                        k: v
                        for k, v in usage.items()
                        if k in {"prompt_tokens", "completion_tokens", "total_tokens"}
                        and type(v) is int
                        and v >= 0
                    }
                    if isinstance(usage, dict)
                    else {}
                )
                entry.update(
                    status=status,
                    usage=safe,
                    usage_source="provider"
                    if {"prompt_tokens", "completion_tokens"} <= safe.keys()
                    else "unknown",
                )
                entries[-1] = entry
                row.usage = {"requests": entries}
                failure = db.get(LlmDocumentBatchFailure, row.id)
                if self.purpose == "repair" and failure is not None and status != "received":
                    failure.state, failure.updated_at = "failed", now()
        try:
            self.progress.flush(provider)
        except DocumentRequestCancelled:
            pass


def _save(
    engine: Engine,
    job_id: str,
    batch_id: str,
    *,
    result: dict[str, Any] | None = None,
    errors: list[dict[str, str]] | None = None,
    status: str = "validated",
) -> None:
    with Session(engine) as db, db.begin():
        job, row = db.get(Job, job_id), db.get(LlmDocumentBatch, batch_id)
        if job is None or job.status != "running" or row is None:
            raise DocumentRequestCancelled
        row.status, row.result_json = status, result
        row.validation_errors = errors or []
        row.error_code = "MODEL_BATCH_SCHEMA_INVALID" if errors else None
        row.updated_at = now()
        failure = db.get(LlmDocumentBatchFailure, row.id)
        if failure is not None and row.repair_attempts:
            failure.state = "succeeded" if status == "validated" else "failed"
            failure.updated_at = now()
        db.flush()
        run = db.get(LlmDocumentBatchRun, row.run_id)
        assert run is not None
        _progress(
            db, job, run, current=row, phase="validating" if status == "validated" else "failed"
        )


def _repair_preserves_material(raw: str, fixed: BatchResult) -> bool:
    from researchgraph.document_batch_contracts import _decode

    try:
        original = _decode(raw)
    except (ValueError, RecursionError):
        return False
    before = original.get("segments")
    after = fixed.model_dump()["segments"]
    if not isinstance(before, list) or len(before) != len(after):
        return False
    for key in ("page_start", "page_end"):
        if key not in original or str(original[key]) != str(getattr(fixed, key)):
            return False
    for left, right in zip(before, after, strict=True):
        if not isinstance(left, dict):
            return False
        for key in (
            "text",
            "latex",
            "mathml",
            "raw_table_text",
            "table_data",
            "locator",
            "chapter_ref",
            "chapter_title",
            "kind",
        ):
            if left.get(key) != right.get(key):
                return False
        for key in ("page_start", "page_end", "chapter_level", "chapter_order", "ordinal"):
            default = 1 if key == "chapter_level" else 0
            old = left.get(key, default)
            if isinstance(old, bool) or str(old) != str(right[key]):
                return False
        for key in ("continues_before", "continues_after"):
            if left.get(key, False) != right[key]:
                return False
        if left.get("status", "ok") != right.get("status"):
            return False
        if left.get("confidence") != right.get("confidence"):
            return False
        if left.get("warnings", []) != right.get("warnings", []):
            return False
    return bool(
        original.get("unavailable_pages", []) == fixed.model_dump().get("unavailable_pages", [])
        and original.get("warnings", []) == fixed.warnings
    )


async def _request(
    engine: Engine,
    job_id: str,
    batch_id: str,
    provider: Any,
    path: Path,
    version: dict[str, Any],
    payload: dict[str, Any],
    schema: dict[str, Any],
    *,
    repair: tuple[str, list[dict[str, str]]] | None = None,
) -> str:
    dispatch = _Dispatch(
        engine,
        job_id,
        batch_id,
        "repair"
        if repair
        else "boundary"
        if payload.get("document_boundary_context")
        else "extract",
        path,
        version,
        repair_raw=repair[0] if repair else None,
    )
    try:
        if not dispatch.before_send():
            raise DocumentRequestCancelled
        if not isinstance(provider, ConfiguredProvider):
            dispatch("document_connecting", {})
        if repair is not None:
            method = getattr(provider, "repair_document_format", None)
            if method is None:
                raise ProviderError("batch_repair", "当前模型接口不支持本批格式修复")
            raw = await method(
                repair[0], schema, repair[1], before_send=dispatch.before_send, on_progress=dispatch
            )
        else:
            raw = await provider.complete_document(
                payload, schema, before_send=dispatch.before_send, on_progress=dispatch
            )
        if not dispatch.before_send():
            raise DocumentRequestCancelled
        dispatch.finish(provider, "received")
        return str(raw)
    except BaseException:
        dispatch.finish(provider, "uncertain" if dispatch.sent else "not_sent")
        with Session(engine) as db, db.begin():
            row = db.get(LlmDocumentBatch, batch_id)
            if row is not None and row.status != "validated":
                row.status = "uncertain" if dispatch.sent else "failed"
                row.updated_at = now()
        raise


def _subset_payload(
    raw: bytes, row: dict[str, Any], page_count: int, payload: dict[str, Any], task: str = "extract"
) -> dict[str, Any]:
    subset = slice_pdf(raw, row["send_start"], row["send_end"])
    return {
        "modality": "pdf",
        "require_multimodal": bool(payload.get("require_multimodal", False)),
        "document_base64": base64.b64encode(subset).decode("ascii"),
        "file_name": "document-pages.pdf",
        "document_batch_context": {
            "version": "document-batch-1",
            "task": task,
            "page_start": row["page_start"],
            "page_end": row["page_end"],
            "send_start": row["send_start"],
            "send_end": row["send_end"],
            "document_pages": page_count,
        },
    }


async def _extract(
    engine: Engine,
    job_id: str,
    batch_id: str,
    provider: Any,
    path: Path,
    version: dict[str, Any],
    raw_pdf: bytes,
    payload: dict[str, Any],
    repair: bool,
) -> BatchResult:
    row = _checkpoint(engine, batch_id)
    if row["status"] == "validated":
        return validate_batch(row["result_json"], row["page_start"], row["page_end"])
    batch_payload = _subset_payload(raw_pdf, row, version["page_count"], payload)
    raw = await _request(
        engine,
        job_id,
        batch_id,
        provider,
        path,
        version,
        batch_payload,
        BatchResult.model_json_schema(),
    )
    try:
        result = validate_batch(raw, row["page_start"], row["page_end"])
    except BatchValidationError as exc:
        _save(engine, job_id, batch_id, errors=exc.safe_errors, status="schema_failed")
        from researchgraph.document_format_repair import _decodable_material, retain_failed_response

        retain_failed_response(engine, job_id, batch_id, raw)
        if not repair or row["repair_attempts"] >= 1 or not _decodable_material(raw):
            raise
        fixed = await _request(
            engine,
            job_id,
            batch_id,
            provider,
            path,
            version,
            {},
            BatchResult.model_json_schema(),
            repair=(raw, exc.safe_errors),
        )
        with Session(engine) as db, db.begin():
            failure = db.get(LlmDocumentBatchFailure, batch_id)
            if failure is not None:
                failure.repair_response, failure.updated_at = fixed, now()
        try:
            result = validate_batch(fixed, row["page_start"], row["page_end"])
            if not _repair_preserves_material(raw, result):
                raise BatchValidationError([{"path": "segments", "code": "value_error"}])
        except BatchValidationError as final:
            _save(engine, job_id, batch_id, errors=final.safe_errors, status="schema_failed")
            raise
    assert_source_version(path, version)
    _save(engine, job_id, batch_id, result=result.model_dump())
    return result


def _boundary_row(engine: Engine, run_id: str, ordinal: int, start: int, end: int) -> str:
    with Session(engine) as db, db.begin():
        row = db.scalar(
            select(LlmDocumentBatch).where(
                LlmDocumentBatch.run_id == run_id,
                LlmDocumentBatch.kind == "boundary",
                LlmDocumentBatch.ordinal == ordinal,
            )
        )
        if row is None:
            row = LlmDocumentBatch(
                id=str(uuid4()),
                run_id=run_id,
                ordinal=ordinal,
                kind="boundary",
                page_start=start,
                page_end=end,
                send_start=start,
                send_end=end,
                status="pending",
                attempts=0,
                repair_attempts=0,
                request_count=0,
                result_json=None,
                validation_errors=[],
                usage={},
                request_metadata={},
                created_at=now(),
                updated_at=now(),
            )
            db.add(row)
        return row.id


async def _review(
    engine: Engine,
    job_id: str,
    batch_id: str,
    left: BatchSegment | None,
    right: BatchSegment | None,
    provider: Any,
    path: Path,
    version: dict[str, Any],
    raw_pdf: bytes,
    payload: dict[str, Any],
    allow: bool,
) -> BoundaryResult:
    row = _checkpoint(engine, batch_id)
    if row["status"] == "validated":
        return validate_boundary(row["result_json"])
    needs = bool(left and right and (left.continues_after or right.continues_before))
    if not needs or not allow:
        decision = BoundaryResult(
            version="document-boundary-1",
            action="uncertain" if needs else "separate",
            separator="newline",
            reason="uncertain" if needs else "distinct_content",
        )
    else:
        context = _subset_payload(raw_pdf, row, version["page_count"], payload, "boundary")
        assert left is not None and right is not None
        context["document_boundary_context"] = {
            "left": left.model_dump(),
            "right": right.model_dump(),
        }
        raw = await _request(
            engine,
            job_id,
            batch_id,
            provider,
            path,
            version,
            context,
            BoundaryResult.model_json_schema(),
        )
        try:
            decision = validate_boundary(raw)
        except BatchValidationError as exc:
            _save(engine, job_id, batch_id, errors=exc.safe_errors, status="schema_failed")
            raise
    _save(engine, job_id, batch_id, result=decision.model_dump())
    return decision


def _merge(
    left: BatchSegment, right: BatchSegment, decision: BoundaryResult
) -> BatchSegment | None:
    if (
        left.kind != right.kind
        or left.chapter_title.strip() != right.chapter_title.strip()
        or left.chapter_level != right.chapter_level
    ):
        return None
    values = left.model_dump()
    separator = {"space": " ", "newline": "\n", "none": ""}[decision.separator]
    if left.kind == "table":
        a, b = left.table_data, right.table_data
        if not (
            isinstance(a, dict)
            and isinstance(b, dict)
            and a.get("columns")
            and a.get("columns") == b.get("columns")
            and isinstance(a.get("rows"), list)
            and isinstance(b.get("rows"), list)
            and set(a) == set(b) == {"columns", "rows"}
        ):
            return None
        right_rows = b["rows"]
        if (
            decision.reason == "table_header_repeat"
            and right_rows
            and right_rows[0] == a["columns"]
        ):
            right_rows = right_rows[1:]
        values["table_data"] = {"columns": a["columns"], "rows": a["rows"] + right_rows}
    for field in ("text", "latex", "mathml", "raw_table_text"):
        a, b = getattr(left, field), getattr(right, field)
        if a and b:
            values[field] = a + separator + b
        elif b:
            values[field] = b
    values.update(
        page_end=right.page_end,
        continues_after=right.continues_after,
        warnings=list(dict.fromkeys(left.warnings + right.warnings))[:32],
        locator={
            "page_start": left.page_start,
            "page_end": right.page_end,
            "source_parts": [
                {"page_start": left.page_start, "page_end": left.page_end},
                {"page_start": right.page_start, "page_end": right.page_end},
            ],
        },
    )
    rank = {"ok": 0, "degraded": 1, "needs_review": 2, "unavailable": 3, "failed": 4}
    values["status"] = max((left.status, right.status), key=lambda item: rank[item])
    values["confidence"] = (
        min(left.confidence, right.confidence)
        if left.confidence is not None and right.confidence is not None
        else None
    )
    try:
        return BatchSegment.model_validate(values)
    except ValidationError:
        # Preserve separate valid fragments if their concatenation exceeds the contract.
        return None


def assemble_batches(
    batches: list[BatchResult], decisions: list[BoundaryResult]
) -> ModelDocumentParseInput:
    material: list[BatchSegment] = []
    warnings: list[str] = []
    for index, batch in enumerate(batches):
        parts = [s.model_copy(deep=True) for s in batch.segments]
        warnings.extend(batch.warnings)
        missing = batch.model_dump().get("unavailable_pages", [])
        if missing:
            warnings.append("以下原始页无法完整转录，需核对源PDF：" + ",".join(map(str, missing)))
        if index and material and parts:
            decision = decisions[index - 1]
            merged = (
                _merge(material[-1], parts[0], decision) if decision.action == "merge" else None
            )
            if merged is not None:
                material[-1] = merged
                parts.pop(0)
            elif decision.action in {"merge", "uncertain"} or (
                material[-1].continues_after or parts[0].continues_before
            ):
                warnings.append(
                    f"原始第{batch.page_start - 1}–{batch.page_start}页续接不确定，保留两个原始片段"
                )
                for fragment in (material[-1], parts[0]):
                    if fragment.status in {"ok", "degraded"}:
                        fragment.status = "needs_review"
        material.extend(parts)
    segments: list[dict[str, Any]] = []
    chapter: tuple[str, int] | None = None
    order = -1
    ordinal = 0
    for segment in material:
        key = (segment.chapter_title.strip(), segment.chapter_level)
        if key != chapter:
            chapter, order, ordinal = key, order + 1, 0
        values = segment.model_dump(
            exclude={"page_start", "page_end", "continues_before", "continues_after"}
        )
        values.update(
            chapter_ref=f"chapter-{order + 1}",
            chapter_order=order,
            ordinal=ordinal,
            locator={
                **(segment.locator or {}),
                "page_start": segment.page_start,
                "page_end": segment.page_end,
                "source_mode": "model_batch",
            },
        )
        segments.append(values)
        ordinal += 1
    if not segments:
        raise ProviderError("batch_empty", "所有批次均未获得可读材料；保留批次警告，未发布空解析")
    try:
        return ModelDocumentParseInput.model_validate(
            {
                "parse_version": "llm-document-batched-1",
                "modality": "pdf",
                "segments": segments,
                "warnings": list(dict.fromkeys(warnings))[:128],
            }
        )
    except ValidationError:
        raise BatchValidationError([{"path": "segments", "code": "value_error"}]) from None


def recover_validated_document_batches(engine: Engine, job_id: str) -> bool:
    """Publish validated checkpoints without initializing a provider or dispatching requests."""

    with read_session(engine) as db:
        job = db.get(Job, job_id)
        if job is None or not publication_retry_available(db, job):
            return False
        payload = dict(job.payload or {})
        run = db.scalar(select(LlmDocumentBatchRun).where(LlmDocumentBatchRun.job_id == job_id))
        if run is None:
            return False
        run_id = run.id
        session_id = run.import_session_id
        source_version = dict(run.source_version)
        settings = dict(run.settings)
        started_at = run.created_at
        rows = [
            {
                key: getattr(row, key)
                for key in (
                    "id",
                    "ordinal",
                    "kind",
                    "page_start",
                    "page_end",
                    "status",
                    "result_json",
                )
            }
            for row in _rows(db, run.id)
        ]

    path_value = payload.get("path") or payload.get("parse_path")
    path = Path(str(path_value or ""))
    if not path.is_absolute() or path.suffix.lower() != ".pdf":
        raise ProviderError("batch_source", "已校验批次缺少可验证的 PDF 来源；未发送模型请求")
    assert_source_version(path, source_version)

    extract_rows = sorted(
        (row for row in rows if row["kind"] == "extract"), key=lambda r: r["ordinal"]
    )
    boundary_rows = sorted(
        (row for row in rows if row["kind"] == "boundary"), key=lambda r: r["ordinal"]
    )
    ranges = settings.get("ranges")
    if not isinstance(ranges, list) or len(ranges) != len(extract_rows):
        raise ProviderError("batch_source", "已校验批次范围不完整；未发送模型请求")
    results: list[BatchResult] = []
    for index, (row, expected) in enumerate(zip(extract_rows, ranges, strict=True)):
        if (
            row["status"] != "validated"
            or row["ordinal"] != index
            or not isinstance(expected, dict)
            or expected.get("index") != row["ordinal"]
            or any(row[key] != expected.get(key) for key in ("page_start", "page_end"))
        ):
            raise ProviderError("batch_source", "已校验批次与冻结页码范围不一致；未发送模型请求")
        results.append(validate_batch(row["result_json"], row["page_start"], row["page_end"]))
    if len(boundary_rows) != max(0, len(results) - 1):
        raise ProviderError("batch_source", "跨批边界检查点不完整；未发送模型请求")
    decisions: list[BoundaryResult] = []
    for index, row in enumerate(boundary_rows):
        if row["status"] != "validated" or row["ordinal"] != index:
            raise ProviderError("batch_source", "跨批边界尚未全部校验；未发送模型请求")
        decisions.append(validate_boundary(row["result_json"]))
    body = assemble_batches(results, decisions)

    from researchgraph.model_document_api import (
        _record_document_failure,
        materialize_document_parse,
    )

    try:
        with Session(engine) as db, db.begin():
            job = db.get(Job, job_id)
            run = db.get(LlmDocumentBatchRun, run_id)
            if job is None or job.status != "running" or run is None:
                raise DocumentRequestCancelled
            if not publication_retry_available(db, job):
                raise ProviderError("batch_recovery", "发布恢复条件已变化；未发送模型请求")
            assert_source_version(path, source_version)
            current_rows = _rows(db, run_id)
            current = {row.id: (row.status, row.result_json) for row in current_rows}
            if any(current.get(row["id"]) != ("validated", row["result_json"]) for row in rows):
                raise ProviderError("batch_recovery", "批次检查点已变化；未发送模型请求")
            provider_snapshot = (job.payload or {}).get("provider_snapshot") or {}
            provider_id = provider_snapshot.get("provider")
            model_id = provider_snapshot.get("model")
            parse = materialize_document_parse(
                db,
                session_id,
                body,
                provider_id=provider_id if isinstance(provider_id, str) else None,
                model_id=model_id if isinstance(model_id, str) else None,
                started_at=started_at,
            )
            run.status = "succeeded"
            _progress(db, job, run, phase="completed")
            job.status, job.stage, job.error = "succeeded", "completed", None
            job.result = {
                **(job.result or {}),
                "parse_id": parse.id,
                "segment_count": len(body.segments),
                "publication_recovered": True,
            }
            job.updated_at = run.updated_at = now()
            from researchgraph.knowledge_automation import note_parsed

            note_parsed(db, job)
        return True
    except IntegrityError as exc:
        with Session(engine) as db, db.begin():
            job = db.get(Job, job_id)
            run = db.get(LlmDocumentBatchRun, run_id)
            if job is not None and job.status == "running" and run is not None:
                run.status = "failed"
                _progress(db, job, run, phase="publication_failed")
        _record_document_failure(
            engine,
            job_id,
            code="MODEL_DOCUMENT_PUBLISH_INTEGRITY_ERROR",
            message="章节解析发布时数据库完整性检查失败；已保留全部已校验批次，请查看安全数据库诊断",
            failure_diagnostics=_integrity_failure_diagnostics(engine, exc),
        )
        raise


async def execute_document_batches(engine: Engine, job_id: str, provider: Any) -> None:
    from researchgraph.model_document_api import (
        _document_provider_identity,
        _document_stage,
        _record_document_failure,
        materialize_document_parse,
    )

    run_id: str | None = None
    try:
        payload, plan, attempt = _load_plan(engine, job_id)
        if not payload.get("allow_network", plan.get("allow_network", False)):
            raise ProviderError("document_capability", "分页解析需要明确联网授权")
        path = Path(str(payload.get("path", "")))
        if not path.is_absolute() or path.suffix.lower() != ".pdf":
            raise ProviderError("batch_source", "没有有效的已登记 PDF 来源")
        if not _document_stage(engine, job_id, "document_batching"):
            return
        from researchgraph.model_document_api import _document_job_running

        deadline = time.monotonic() + float(getattr(provider, "document_total_timeout", 1800))

        def continue_preparation() -> bool:
            if time.monotonic() >= deadline:
                raise DocumentRenderDeadline
            return _document_job_running(engine, job_id)

        try:
            raw, version, ranges = await asyncio.to_thread(
                prepare_document,
                path,
                int(plan.get("pages_per_batch", 5)),
                provider,
                should_continue=continue_preparation,
            )
        except DocumentRenderCancelled:
            raise DocumentRequestCancelled from None
        except DocumentRenderDeadline:
            raise ProviderError("timeout", "批次准备达到总时限，未发送模型请求") from None
        run_id = _prepare_run(engine, job_id, payload, plan, version, ranges, attempt)
        with read_session(engine) as db:
            ids = [r.id for r in _rows(db, run_id) if r.kind == "extract"]
            run = db.get(LlmDocumentBatchRun, run_id)
            assert run is not None
            started_at = run.created_at
        results: list[BatchResult] = []
        for batch_id in ids:
            results.append(
                await _extract(
                    engine,
                    job_id,
                    batch_id,
                    provider,
                    path,
                    version,
                    raw,
                    payload,
                    bool(plan.get("allow_format_repair", False)),
                )
            )
        decisions: list[BoundaryResult] = []
        for index in range(1, len(results)):
            left = results[index - 1].segments[-1] if results[index - 1].segments else None
            right = results[index].segments[0] if results[index].segments else None
            page = results[index].page_start
            batch_id = _boundary_row(engine, run_id, index - 1, max(1, page - 1), page)
            decisions.append(
                await _review(
                    engine,
                    job_id,
                    batch_id,
                    left,
                    right,
                    provider,
                    path,
                    version,
                    raw,
                    payload,
                    bool(plan.get("allow_boundary_review", True)),
                )
            )
        assert_source_version(path, version)
        body = assemble_batches(results, decisions)
        if not _document_stage(engine, job_id, "saving_document"):
            return
        provider_id, model_id = _document_provider_identity(provider)
        try:
            with Session(engine) as db, db.begin():
                job, run = db.get(Job, job_id), db.get(LlmDocumentBatchRun, run_id)
                if job is None or job.status != "running" or run is None:
                    return
                assert_source_version(path, version)
                parse = materialize_document_parse(
                    db,
                    str(payload["import_session_id"]),
                    body,
                    provider_id=provider_id,
                    model_id=model_id,
                    started_at=started_at,
                )
                run.status = "succeeded"
                _progress(db, job, run, phase="completed")
                job.status, job.stage, job.error = "succeeded", "completed", None
                job.result = {
                    **(job.result or {}),
                    "parse_id": parse.id,
                    "segment_count": len(body.segments),
                }
                from researchgraph.knowledge_automation import note_parsed

                note_parsed(db, job)
        except IntegrityError as exc:
            with Session(engine) as db, db.begin():
                job, run = db.get(Job, job_id), db.get(LlmDocumentBatchRun, run_id)
                if job is not None and job.status == "running" and run is not None:
                    run.status = "failed"
                    _progress(db, job, run, phase="publication_failed")
            _record_document_failure(
                engine,
                job_id,
                code="MODEL_DOCUMENT_PUBLISH_INTEGRITY_ERROR",
                message="章节解析发布时数据库完整性检查失败；已保留全部已校验批次，请查看安全数据库诊断",
                failure_diagnostics=_integrity_failure_diagnostics(engine, exc),
                provider_id=provider_id,
                model_id=model_id,
            )
            raise
    except DocumentRequestCancelled:
        return
    except (BatchValidationError, ProviderError, DocumentRenderError) as exc:
        if run_id:
            with Session(engine) as db, db.begin():
                job, run = db.get(Job, job_id), db.get(LlmDocumentBatchRun, run_id)
                if run is not None:
                    run.status = "failed"
                if job is not None and job.status == "running" and run is not None:
                    previous = (job.result or {}).get("document_batches", {})
                    current_id = next(
                        (
                            r.id
                            for r in _rows(db, run.id)
                            if r.status in {"schema_failed", "uncertain", "failed"}
                        ),
                        None,
                    )
                    current = db.get(LlmDocumentBatch, current_id) if current_id else None
                    _progress(db, job, run, current=current, phase="failed")
                    if current is None and previous.get("validation_errors"):
                        job.result = {
                            **(job.result or {}),
                            "document_batches": {
                                **(job.result or {})["document_batches"],
                                "validation_errors": previous["validation_errors"],
                            },
                        }
        provider_id, model_id = _document_provider_identity(provider)
        code = (
            "MODEL_BATCH_SCHEMA_INVALID"
            if isinstance(exc, BatchValidationError)
            else "MODEL_BATCH_FAILED"
        )
        _record_document_failure(
            engine,
            job_id,
            code=code,
            message=str(exc) + "；已通过的批次保留，未自动重发",
            provider_id=provider_id,
            model_id=model_id,
        )
        raise
