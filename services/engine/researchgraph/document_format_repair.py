"""Explicit one-request recovery of a retained invalid document batch response."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.document_batch_contracts import BatchResult, BatchValidationError, _decode
from researchgraph.document_batch_models import (
    LlmDocumentBatch,
    LlmDocumentBatchFailure,
    LlmDocumentBatchRun,
)
from researchgraph.document_batch_transport import assert_source_version
from researchgraph.document_transport import DocumentRenderError
from researchgraph.import_plan_models import ImportPlanItem, ImportSession
from researchgraph.model_document_models import LlmDocumentParse
from researchgraph.models import Job, now
from researchgraph.providers import (
    MAX_DOCUMENT_RESPONSE_BYTES,
    DocumentRequestCancelled,
    ProviderError,
)
from researchgraph.storage import read_session

REPAIR_VERSION = "document-explicit-format-repair-1"


class DocumentFormatRepairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    allow_network: bool


class DocumentFormatRepairView(BaseModel):
    available: bool
    batch_id: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    reason_code: str
    repair_attempts: int = 0
    request_count: int = 0


def retain_failed_response(engine: Engine, job_id: str, batch_id: str, raw: str) -> None:
    """Retain source material privately; diagnostics never receive its text."""
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_DOCUMENT_RESPONSE_BYTES:
        return
    with Session(engine) as db, db.begin():
        job, row = db.get(Job, job_id), db.get(LlmDocumentBatch, batch_id)
        if (
            job is None
            or job.status != "running"
            or row is None
            or row.status != "schema_failed"
            or row.request_count < 1
            or row.repair_attempts
        ):
            return
        run = db.get(LlmDocumentBatchRun, row.run_id)
        if run is None or run.job_id != job_id:
            return
        failure = db.get(LlmDocumentBatchFailure, batch_id)
        if failure is None:
            failure = LlmDocumentBatchFailure(
                batch_id=batch_id,
                raw_response=raw,
                source_request_count=row.request_count,
                state="available",
                created_at=now(),
                updated_at=now(),
            )
            db.add(failure)
        elif failure.state == "available":
            failure.raw_response = raw
            failure.source_request_count = row.request_count
            failure.updated_at = now()


def _decodable_material(raw: str) -> bool:
    try:
        value = _decode(raw)
    except (ValueError, RecursionError):
        return False
    return isinstance(value.get("segments"), list) and all(
        isinstance(item, dict) for item in value["segments"]
    )


def _repair_candidate(
    db: Session, job: Job
) -> tuple[LlmDocumentBatchRun, LlmDocumentBatch, LlmDocumentBatchFailure] | None:
    if job.kind not in {"pdf_import", "zotero_import", "llm_document_parse"}:
        return None
    if job.status != "failed" or not isinstance(job.payload, dict):
        return None
    session_id = job.payload.get("import_session_id")
    run = db.scalar(select(LlmDocumentBatchRun).where(LlmDocumentBatchRun.job_id == job.id))
    if (
        run is None
        or run.import_session_id != session_id
        or run.settings.get("version") != "document-batch-1"
        or run.settings.get("provider_snapshot") != job.payload.get("provider_snapshot")
    ):
        return None
    session = db.get(ImportSession, str(session_id))
    item = db.scalar(
        select(ImportPlanItem).where(
            ImportPlanItem.session_id == session_id,
            ImportPlanItem.item_kind == "document_parse",
            ImportPlanItem.job_id == job.id,
        )
    )
    if (
        session is None
        or session.plan.get("document_batching") is not True
        or item is None
        or item.status != "failed"
        or db.scalar(
            select(LlmDocumentParse.id).where(
                LlmDocumentParse.import_session_id == session_id,
                LlmDocumentParse.status == "succeeded",
            )
        )
        is not None
    ):
        return None
    rows = list(
        db.scalars(
            select(LlmDocumentBatch).where(
                LlmDocumentBatch.run_id == run.id,
                LlmDocumentBatch.status == "schema_failed",
            )
        )
    )
    if len(rows) != 1:
        return None
    row = rows[0]
    failure = db.get(LlmDocumentBatchFailure, row.id)
    if (
        row.kind != "extract"
        or row.error_code != "MODEL_BATCH_SCHEMA_INVALID"
        or row.repair_attempts != 0
        or failure is None
        or failure.state != "available"
        or failure.source_request_count != row.request_count
        or not failure.raw_response
    ):
        return None
    return run, row, failure


def format_repair_view(db: Session, job: Job) -> DocumentFormatRepairView:
    candidate = _repair_candidate(db, job)
    if candidate is None:
        return DocumentFormatRepairView(available=False, reason_code="NO_REPAIRABLE_RESPONSE")
    _run, row, failure = candidate
    available = _decodable_material(failure.raw_response)
    return DocumentFormatRepairView(
        available=available,
        batch_id=row.id,
        page_start=row.page_start,
        page_end=row.page_end,
        reason_code="FORMAT_REPAIR_AVAILABLE" if available else "RAW_JSON_NOT_DECODABLE",
        repair_attempts=row.repair_attempts,
        request_count=row.request_count,
    )


def has_format_repair_intent(job: Job) -> bool:
    return (job.result or {}).get("document_format_repair_only") is True


def ordinary_document_attempts(job: Job) -> int:
    """A text repair worker attempt does not consume a PDF extraction retry."""
    if job.kind not in {"pdf_import", "zotero_import", "llm_document_parse"}:
        return job.attempt
    values = (job.result or {}).get("document_format_repair_worker_attempts", [])
    if not isinstance(values, list):
        return job.attempt
    counted = {value for value in values if type(value) is int and 0 < value <= job.attempt}
    return max(0, job.attempt - len(counted))


def clear_format_repair_intent(job: Job) -> None:
    if has_format_repair_intent(job):
        job.result = {**(job.result or {}), "document_format_repair_only": False}


def authorize_format_repair(db: Session, job: Job, *, allow_network: bool) -> str:
    """Bind a new explicit action to this exact response and the next worker attempt."""
    from researchgraph.app import failure as api_failure

    if allow_network is not True:
        raise api_failure(422, "NETWORK_AUTHORIZATION_REQUIRED", "格式修复需要明确联网授权")
    candidate = _repair_candidate(db, job)
    if candidate is None or not _decodable_material(candidate[2].raw_response):
        raise api_failure(
            409,
            "DOCUMENT_FORMAT_REPAIR_UNAVAILABLE",
            "没有可无损修复的已保存响应，或本批已使用一次格式修复；未发送请求",
        )
    run, row, failure = candidate
    failure.state = "authorized"
    failure.authorized_attempt = job.attempt + 1
    failure.updated_at = now()
    run.settings = {**run.settings, "request_budget": run.settings["request_budget"] + 1}
    job.result = {
        **(job.result or {}),
        "document_format_repair_only": True,
        "document_format_repair": {
            "version": REPAIR_VERSION,
            "batch_id": row.id,
            "source_request_count": failure.source_request_count,
            "authorized_attempt": failure.authorized_attempt,
        },
    }
    return row.id


def explicit_repair_authorized(db: Session, job: Job, row: LlmDocumentBatch) -> bool:
    """Revalidate the frozen intent immediately before the request slot is consumed."""
    data = (job.result or {}).get("document_format_repair")
    failure = db.get(LlmDocumentBatchFailure, row.id)
    run = db.get(LlmDocumentBatchRun, row.run_id)
    return bool(
        has_format_repair_intent(job)
        and isinstance(data, dict)
        and data.get("version") == REPAIR_VERSION
        and data.get("batch_id") == row.id
        and type(data.get("source_request_count")) is int
        and data.get("source_request_count") == row.request_count
        and data.get("authorized_attempt") == job.attempt
        and failure is not None
        and failure.state == "authorized"
        and failure.source_request_count == row.request_count
        and failure.authorized_attempt == job.attempt
        and row.kind == "extract"
        and row.status == "schema_failed"
        and row.error_code == "MODEL_BATCH_SCHEMA_INVALID"
        and row.repair_attempts == 0
        and run is not None
        and run.job_id == job.id
        and run.import_session_id == (job.payload or {}).get("import_session_id")
        and run.settings.get("provider_snapshot") == (job.payload or {}).get("provider_snapshot")
    )


async def execute_authorized_format_repair(engine: Engine, job_id: str, provider: Any) -> bool:
    """Consume only the explicit text repair; never read or transmit PDF content."""
    from researchgraph.document_batch_contracts import validate_batch
    from researchgraph.document_batches import (
        _progress,
        _repair_preserves_material,
        _request,
        _save,
    )
    from researchgraph.model_document_api import _record_document_failure

    with read_session(engine) as db:
        job = db.get(Job, job_id)
        if job is None or not has_format_repair_intent(job):
            return False
        intent = (job.result or {}).get("document_format_repair")
        batch_id = intent.get("batch_id") if isinstance(intent, dict) else None
        row = db.get(LlmDocumentBatch, batch_id) if isinstance(batch_id, str) else None
        if job.status != "running" or row is None or not explicit_repair_authorized(db, job, row):
            raise ProviderError(
                "batch_repair", "本批格式修复授权已变化或请求已使用；未发送模型请求"
            )
        failure = db.get(LlmDocumentBatchFailure, row.id)
        run = db.get(LlmDocumentBatchRun, row.run_id)
        assert failure is not None and run is not None
        if not _decodable_material(failure.raw_response):
            raise ProviderError("batch_repair", "原始JSON无法无损核对；未发送模型请求")
        path = Path(
            str((job.payload or {}).get("parse_path") or (job.payload or {}).get("path", ""))
        )
        if not path.is_absolute() or path.suffix.lower() != ".pdf":
            raise ProviderError("batch_source", "缺少有效的PDF来源版本；未发送模型请求")
        version, raw = dict(run.source_version), failure.raw_response
        start, end, errors = row.page_start, row.page_end, list(row.validation_errors)
        run_id, batch_id = run.id, row.id
    with Session(engine) as db, db.begin():
        job, row = db.get(Job, job_id), db.get(LlmDocumentBatch, batch_id)
        if job is None or job.status != "running" or row is None:
            raise DocumentRequestCancelled
        if not explicit_repair_authorized(db, job, row):
            raise ProviderError("batch_repair", "本批格式修复授权已变化；未发送模型请求")
        attempts = (job.result or {}).get("document_format_repair_worker_attempts", [])
        valid_attempts = (
            [value for value in attempts if type(value) is int and value > 0]
            if isinstance(attempts, list)
            else []
        )
        job.result = {
            **(job.result or {}),
            "document_format_repair_worker_attempts": sorted({*valid_attempts, job.attempt}),
        }
    assert_source_version(path, version)
    try:
        repaired = await _request(
            engine,
            job_id,
            batch_id,
            provider,
            path,
            version,
            {},
            BatchResult.model_json_schema(),
            repair=(raw, errors),
        )
        with Session(engine) as db, db.begin():
            failure = db.get(LlmDocumentBatchFailure, batch_id)
            if failure is not None:
                failure.repair_response = repaired
                failure.updated_at = now()
        result = validate_batch(repaired, start, end)
        if not _repair_preserves_material(raw, result):
            raise BatchValidationError([{"path": "segments", "code": "value_error"}])
        assert_source_version(path, version)
        _save(engine, job_id, batch_id, result=result.model_dump())
        message = "本批格式已修复并保存；请继续未完成批次以完成章节发布（可能另行请求模型）"
        with Session(engine) as db, db.begin():
            job, run = db.get(Job, job_id), db.get(LlmDocumentBatchRun, run_id)
            failure = db.get(LlmDocumentBatchFailure, batch_id)
            if job is None or job.status != "running" or run is None:
                raise DocumentRequestCancelled
            if failure is not None:
                failure.state, failure.updated_at = "succeeded", now()
            run.status = "failed"
            _progress(
                db, job, run, current=db.get(LlmDocumentBatch, batch_id), phase="format_repaired"
            )
            job.result = {
                **(job.result or {}),
                "document_format_repair_only": False,
                "document_format_repair_completed": True,
            }
            job.status, job.stage, job.error, job.updated_at = (
                "failed",
                "paused",
                message,
                now(),
            )
            item = db.scalar(
                select(ImportPlanItem).where(
                    ImportPlanItem.job_id == job_id,
                    ImportPlanItem.item_kind == "document_parse",
                )
            )
            if item is not None:
                item.status, item.error, item.updated_at = "failed", message, now()
            session = db.get(ImportSession, run.import_session_id)
            if session is not None:
                session.status, session.error, session.updated_at = "failed", message, now()
        return True
    except DocumentRequestCancelled:
        return True
    except (BatchValidationError, ProviderError, DocumentRenderError) as exc:
        with Session(engine) as db, db.begin():
            failure = db.get(LlmDocumentBatchFailure, batch_id)
            if failure is not None and failure.state == "sent":
                failure.state, failure.updated_at = "failed", now()
        if isinstance(exc, BatchValidationError):
            _save(engine, job_id, batch_id, errors=exc.safe_errors, status="schema_failed")
        _record_document_failure(
            engine,
            job_id,
            code="MODEL_BATCH_FORMAT_REPAIR_FAILED",
            message="本批格式修复未通过，原始响应与已成功批次保留；未自动重发",
        )
        raise


def register_document_format_repair_api(app: FastAPI, engine: Callable[[], Engine]) -> None:
    from researchgraph.app import Key, failure, remember, remembered
    from researchgraph.schemas import JobView

    def session_job(db: Session, session_id: str) -> Job:
        if db.get(ImportSession, session_id) is None:
            raise failure(404, "IMPORT_SESSION_NOT_FOUND", "导入会话不存在")
        item = db.scalar(
            select(ImportPlanItem).where(
                ImportPlanItem.session_id == session_id,
                ImportPlanItem.item_kind == "document_parse",
            )
        )
        job = db.get(Job, item.job_id) if item is not None and item.job_id else None
        if job is None:
            raise failure(404, "DOCUMENT_PARSE_JOB_NOT_FOUND", "模型解析任务不存在")
        return job

    @app.get(
        "/api/v1/import-sessions/{session_id}/document-parse/format-repair",
        response_model=DocumentFormatRepairView,
    )
    def get_format_repair(session_id: str) -> DocumentFormatRepairView:
        with read_session(engine()) as db:
            return format_repair_view(db, session_job(db, session_id))

    @app.post(
        "/api/v1/import-sessions/{session_id}/document-parse/format-repair",
        response_model=JobView,
        status_code=202,
    )
    def request_format_repair(
        session_id: str, body: DocumentFormatRepairRequest, idempotency_key: Key
    ) -> JobView:
        request = {"session_id": session_id, **body.model_dump()}
        key = "document-format-repair:" + idempotency_key
        with Session(engine()) as db, db.begin():
            job = session_job(db, session_id)
            previous = remembered(db, key, request)
            if previous:
                return JobView.model_validate(previous)
            authorize_format_repair(db, job, allow_network=body.allow_network)
            timestamp = now()
            job.status, job.stage, job.error, job.updated_at = (
                "queued",
                "document_repairing",
                None,
                timestamp,
            )
            item = db.scalar(
                select(ImportPlanItem).where(
                    ImportPlanItem.session_id == session_id,
                    ImportPlanItem.item_kind == "document_parse",
                )
            )
            assert item is not None
            item.status, item.error, item.updated_at = "queued", None, timestamp
            item.attempt += 1
            session = db.get(ImportSession, session_id)
            assert session is not None
            session.status, session.error, session.updated_at = "queued", None, timestamp
            response = JobView.model_validate(job)
            remember(db, key, request, response.model_dump())
            return response
