"""Read-only projection and one bounded recovery for the old boundary JSON prompt."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.document_batch_models import LlmDocumentBatch, LlmDocumentBatchRun
from researchgraph.import_plan_models import ImportPlanItem
from researchgraph.model_document_models import LlmDocumentParse
from researchgraph.models import Job

BOUNDARY_PROMPT_VERSION = 2
MAX_PUBLICATION_RECOVERIES = 2
PUBLICATION_RECOVERY_VERSION = "foreign-key-order-1"


def legacy_boundary_recovery(row: LlmDocumentBatch) -> bool:
    metadata = row.request_metadata or {}
    entries = (row.usage or {}).get("requests", [])
    return bool(
        row.kind == "boundary"
        and row.status != "validated"
        and 0 < row.attempts <= 3
        and metadata.get("http_status") == 400
        and metadata.get("boundary_prompt_version", 0) != BOUNDARY_PROMPT_VERSION
        and not any(
            isinstance(entry, dict)
            and entry.get("boundary_prompt_version") == BOUNDARY_PROMPT_VERSION
            for entry in entries
        )
    )


def compatibility_retry_available(db: Session, job: Job) -> bool:
    if job.status not in {"failed", "interrupted", "cancelled", "paused"}:
        return False
    run = db.scalar(select(LlmDocumentBatchRun).where(LlmDocumentBatchRun.job_id == job.id))
    if run is None or run.settings.get("version") != "document-batch-1":
        return False
    rows = list(db.scalars(select(LlmDocumentBatch).where(LlmDocumentBatch.run_id == run.id)))
    extracts = [row for row in rows if row.kind == "extract"]
    unfinished = [row for row in rows if row.status != "validated"]
    return bool(
        extracts
        and all(row.status == "validated" for row in extracts)
        and unfinished
        and all(legacy_boundary_recovery(row) for row in unfinished)
    )


def publication_retry_available(db: Session, job: Job) -> bool:
    """Allow a bounded retry that only publishes already validated checkpoints."""

    if job.kind not in {"pdf_import", "zotero_import", "llm_document_parse"}:
        return False
    if job.status not in {"failed", "interrupted", "cancelled", "paused", "running"}:
        return False
    result = job.result or {}
    recovery_count = result.get("publication_recovery_attempts", 0)
    if type(recovery_count) is not int or recovery_count < 0:
        return False
    diagnostics = result.get("failure_diagnostics")
    legacy_fk_failure = bool(
        recovery_count == MAX_PUBLICATION_RECOVERIES
        and "publication_recovery_version" not in result
        and isinstance(diagnostics, dict)
        and diagnostics.get("database_dialect") == "sqlite"
        and type(diagnostics.get("sqlite_errorcode")) is int
        and diagnostics.get("sqlite_errorcode") == 787
        and diagnostics.get("sqlite_errorname") == "SQLITE_CONSTRAINT_FOREIGNKEY"
        and diagnostics.get("constraint_category") == "foreign_key"
        and isinstance(result.get("document_batches"), dict)
        and result["document_batches"].get("phase") == "publication_failed"
    )
    corrected_attempt_running = bool(
        job.status == "running"
        and recovery_count == MAX_PUBLICATION_RECOVERIES + 1
        and result.get("publication_recovery_version") == PUBLICATION_RECOVERY_VERSION
        and result.get("publication_recovery_only") is True
    )
    if not (
        recovery_count < MAX_PUBLICATION_RECOVERIES
        or (job.status == "running" and recovery_count == MAX_PUBLICATION_RECOVERIES)
        or legacy_fk_failure
        or corrected_attempt_running
    ):
        return False
    session_id = str((job.payload or {}).get("import_session_id", ""))
    if not session_id:
        return False
    run = db.scalar(select(LlmDocumentBatchRun).where(LlmDocumentBatchRun.job_id == job.id))
    if (
        run is None
        or run.import_session_id != session_id
        or run.settings.get("version") != "document-batch-1"
        or run.status not in {"running", "failed"}
    ):
        return False
    item = db.scalar(
        select(ImportPlanItem).where(
            ImportPlanItem.session_id == session_id,
            ImportPlanItem.item_kind == "document_parse",
            ImportPlanItem.job_id == job.id,
        )
    )
    if item is None or item.status not in {
        "failed",
        "interrupted",
        "cancelled",
        "paused",
        "queued",
        "running",
    }:
        return False
    if (
        db.scalar(
            select(LlmDocumentParse.id).where(
                LlmDocumentParse.import_session_id == session_id,
                LlmDocumentParse.status == "succeeded",
            )
        )
        is not None
    ):
        return False
    rows = list(db.scalars(select(LlmDocumentBatch).where(LlmDocumentBatch.run_id == run.id)))
    extracts = sorted((row for row in rows if row.kind == "extract"), key=lambda row: row.ordinal)
    boundaries = sorted(
        (row for row in rows if row.kind == "boundary"), key=lambda row: row.ordinal
    )
    ranges = run.settings.get("ranges")
    if (
        not extracts
        or not isinstance(ranges, list)
        or len(ranges) != len(extracts)
        or len(boundaries) != len(extracts) - 1
        or any(row.status != "validated" or not isinstance(row.result_json, dict) for row in rows)
    ):
        return False
    for index, (row, item_range) in enumerate(zip(extracts, ranges, strict=True)):
        if not isinstance(item_range, dict) or any(
            row_value != item_range.get(key)
            for key, row_value in (
                ("index", row.ordinal),
                ("page_start", row.page_start),
                ("page_end", row.page_end),
                ("send_start", row.send_start),
                ("send_end", row.send_end),
            )
        ):
            return False
        if row.ordinal != index:
            return False
    return all(row.ordinal == index for index, row in enumerate(boundaries))


def authorize_publication_retry(job: Job) -> None:
    result = dict(job.result or {})
    count = result.get("publication_recovery_attempts", 0)
    if type(count) is int and 0 <= count <= MAX_PUBLICATION_RECOVERIES:
        result["publication_recovery_attempts"] = count + 1
        result["publication_recovery_version"] = PUBLICATION_RECOVERY_VERSION
        result["publication_recovery_only"] = True
        job.result = result


def project_batch_recovery(db: Session, job: Job) -> dict[str, Any] | None:
    """Annotate legacy GET views without changing the stored Job or checkpoints."""
    result = job.result
    if not isinstance(result, dict) or not isinstance(result.get("document_batches"), dict):
        return result
    data = dict(result["document_batches"])
    available = compatibility_retry_available(db, job)
    publication_available = publication_retry_available(db, job)
    data["compatibility_retry_available"] = available
    data["publication_retry_available"] = publication_available
    if available:
        data["current_kind"] = "boundary"
    elif publication_available or data.get("phase") == "publication_failed":
        data["current_kind"] = "publication"
    return {**result, "document_batches": data}
