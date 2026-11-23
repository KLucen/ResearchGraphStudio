"""Paper metadata edits and explicit per-paper data removal."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable
from pathlib import Path
from stat import S_ISREG
from typing import Any, cast
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import Field
from sqlalchemy import Engine, bindparam, delete, func, select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from researchgraph.archive_models import archived_target
from researchgraph.chapter_reading_models import ModelChapterReadingState
from researchgraph.close_reading_models import (
    SectionCloseReadingResult,
    UnderstandingCheckResult,
)
from researchgraph.core import StrictModel
from researchgraph.document_batch_models import LlmDocumentBatch, LlmDocumentBatchRun
from researchgraph.import_plan_models import ImportPlanItem, ImportSession
from researchgraph.keyword_models import LiteKeywordRecord
from researchgraph.lite_models import LiteCacheEntry, LiteTokenUsage
from researchgraph.lite_usage import preserve_paper_usage
from researchgraph.model_document_models import (
    LlmDocumentOutput,
    LlmDocumentParse,
    LlmDocumentSegment,
)
from researchgraph.models import (
    AttachmentRevision,
    Chunk,
    Event,
    EvidenceSpan,
    Idempotency,
    Job,
    Paper,
    PaperSource,
    Section,
    ZoteroLink,
)
from researchgraph.paper_overview_models import (
    PaperGraphLayout,
    PaperGraphViewport,
    PaperOverviewResult,
)
from researchgraph.paper_reading_models import PaperReadingResult
from researchgraph.qa_models import LiteQARecord
from researchgraph.reading_document_models import ReadingDocumentProjection
from researchgraph.reading_state_models import ConceptUnderstanding, ReadingState
from researchgraph.section_guide_models import SectionGuideResult
from researchgraph.storage import backup_database
from researchgraph.structure_models import DocumentParse
from researchgraph.structure_upgrade import mark_local_content_cleared
from researchgraph.translation_models import PDFTranslation


class PaperTitleUpdate(StrictModel):
    title: str = Field(min_length=1, max_length=500)


class PaperManagementResult(StrictModel):
    ok: bool = True
    paper_id: str
    archive_item_id: str | None = None
    backup_file: str | None = None
    removed: dict[str, int] = Field(default_factory=dict)
    retained_personal_metadata: int = 0
    retained_managed_files: int = 0


def _failure(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


def _contains_any(value: Any, identities: set[str]) -> bool:
    if isinstance(value, str):
        return value in identities
    if isinstance(value, dict):
        return any(
            _contains_any(key, identities) or _contains_any(item, identities)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_any(item, identities) for item in value)
    return False


def _paper_context(db: Session, paper_id: str) -> dict[str, Any]:
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise _failure(404, "PAPER_NOT_FOUND", "论文不存在")
    revisions = list(
        db.scalars(select(AttachmentRevision).where(AttachmentRevision.paper_id == paper_id)).all()
    )
    sources = list(db.scalars(select(PaperSource).where(PaperSource.paper_id == paper_id)).all())
    revision_ids = {row.id for row in revisions}
    source_ids = {row.id for row in sources}
    record_job_ids: set[str] = set()
    for model in (
        PaperReadingResult,
        PaperOverviewResult,
        SectionGuideResult,
        SectionCloseReadingResult,
        UnderstandingCheckResult,
        LiteQARecord,
        LiteKeywordRecord,
        PDFTranslation,
    ):
        record_job_ids.update(
            job_id
            for job_id in db.scalars(
                select(model.job_id).where(model.paper_id == paper_id, model.job_id.is_not(None))
            ).all()
            if job_id
        )
    project_jobs = list(db.scalars(select(Job).where(Job.project_id == paper.project_id)).all())
    jobs = [
        job
        for job in project_jobs
        if job.id in record_job_ids
        or _contains_any(
            {"payload": job.payload or {}, "result": job.result or {}},
            {paper_id, *revision_ids, *source_ids},
        )
    ]
    sessions = list(
        db.scalars(select(ImportSession).where(ImportSession.project_id == paper.project_id)).all()
    )
    import_sessions = [
        row
        for row in sessions
        if row.source_snapshot.get("paper_id") == paper_id
        or any((job.payload or {}).get("import_session_id") == row.id for job in jobs)
    ]
    session_ids = {row.id for row in import_sessions}
    plan_items = (
        list(
            db.scalars(
                select(ImportPlanItem).where(ImportPlanItem.session_id.in_(session_ids))
            ).all()
        )
        if session_ids
        else []
    )
    related_job_ids = {job.id for job in jobs} | {item.job_id for item in plan_items if item.job_id}
    return {
        "paper": paper,
        "revisions": revisions,
        "revision_ids": revision_ids,
        "sources": sources,
        "source_ids": source_ids,
        "jobs": jobs,
        "job_ids": related_job_ids,
        "sessions": import_sessions,
        "session_ids": session_ids,
        "plan_items": plan_items,
    }


def _is_model_first_job(job: Job, context: dict[str, Any]) -> bool:
    payload = job.payload or {}
    return (
        job.kind in {"llm_document_parse", "llm_document_postprocess"}
        or bool(payload.get("model_first") or payload.get("model_first_source"))
        or payload.get("import_session_id") in context["session_ids"]
    )


def _ensure_no_running_jobs(
    context: dict[str, Any],
    *,
    preserve_model_first: bool = False,
    reject_queued_legacy: bool = False,
) -> None:
    blocked_statuses = {"running", "queued"} if reject_queued_legacy else {"running"}
    if any(
        job.status in blocked_statuses
        and not (preserve_model_first and _is_model_first_job(job, context))
        for job in context["jobs"]
    ):
        raise _failure(
            409,
            "PAPER_TASK_RUNNING",
            "该论文仍有运行或排队中的本地任务，请先等待任务结束后再操作",
        )


def _backup_database(engine: Engine, data_dir: Path, paper_id: str, action: str) -> str:
    source_path = Path(str(engine.url.database or ""))
    if not source_path.is_file():
        raise _failure(500, "PAPER_BACKUP_FAILED", "未能定位本地数据库，删除操作已取消")
    backup_dir = data_dir / "backups"
    filename = f"before-paper-{action}-{paper_id}-{uuid4()}.sqlite3"
    destination = backup_dir / filename
    try:
        backup_database(source_path, destination)
    except (OSError, sqlite3.Error):
        raise _failure(500, "PAPER_BACKUP_FAILED", "数据库备份失败，删除操作已取消") from None
    return destination.relative_to(data_dir).as_posix()


def _delete_rows(db: Session, model: Any, column: Any, values: Iterable[str]) -> int:
    selected = tuple(set(values))
    if not selected:
        return 0
    result = cast(CursorResult[Any], db.execute(delete(model).where(column.in_(selected))))
    return int(result.rowcount or 0)


def _delete_fts_rows(db: Session, revision_ids: Iterable[str]) -> int:
    selected = tuple(set(revision_ids))
    if not selected:
        return 0
    statement = text("DELETE FROM chunk_fts WHERE document_version_id IN :revision_ids").bindparams(
        bindparam("revision_ids", expanding=True)
    )
    result = cast(CursorResult[Any], db.execute(statement, {"revision_ids": selected}))
    return int(result.rowcount or 0)


def _managed_file_candidate(path_value: str | None, data_dir: Path) -> Path | None:
    if not path_value:
        return None
    data_root = data_dir.resolve()
    attachment_root = data_root / "attachments"
    original = Path(path_value)
    try:
        root = attachment_root.resolve(strict=True)
        if root != attachment_root or not root.is_dir():
            return None
        if original.is_symlink():
            return None
        candidate = original.resolve(strict=False)
        if candidate.parent != root or candidate.suffix.lower() != ".pdf":
            return None
        if not candidate.is_relative_to(root):
            return None
        try:
            return candidate if S_ISREG(candidate.stat().st_mode) else None
        except FileNotFoundError:
            return candidate
    except (FileNotFoundError, RuntimeError, ValueError):
        return None


def _remove_legacy_content(db: Session, context: dict[str, Any]) -> dict[str, int]:
    revision_ids = context["revision_ids"]
    if not revision_ids:
        return {"legacy_revisions": 0}
    paper_id = context["paper"].id
    counts: dict[str, int] = {}
    counts["fts_rows"] = _delete_fts_rows(db, revision_ids)
    counts["reading_documents"] = _delete_rows(
        db, ReadingDocumentProjection, ReadingDocumentProjection.document_version_id, revision_ids
    )
    counts["document_parses"] = _delete_rows(
        db, DocumentParse, DocumentParse.document_version_id, revision_ids
    )
    counts["cache_entries"] = _delete_rows(db, LiteCacheEntry, LiteCacheEntry.paper_id, (paper_id,))
    counts["evidence_spans"] = _delete_rows(
        db, EvidenceSpan, EvidenceSpan.document_version_id, revision_ids
    )
    counts["chunks"] = _delete_rows(db, Chunk, Chunk.revision_id, revision_ids)
    for revision in context["revisions"]:
        mark_local_content_cleared(revision)
    counts["revision_cleanup_markers"] = len(context["revisions"])
    # Keep section IDs and all generated reading/overview/QA notes intact. They
    # are user-visible records and may still be referenced by personal state.
    counts["notes_preserved"] = sum(
        db.scalar(select(func.count()).select_from(model).where(model.paper_id == paper_id)) or 0
        for model in (
            PaperReadingResult,
            PaperOverviewResult,
            SectionGuideResult,
            SectionCloseReadingResult,
            UnderstandingCheckResult,
            LiteQARecord,
            LiteKeywordRecord,
            PDFTranslation,
        )
    )
    counts["source_revisions_preserved"] = len(revision_ids)
    counts["personal_metadata_retained"] = int(
        db.scalar(
            select(func.count()).select_from(ReadingState).where(ReadingState.paper_id == paper_id)
        )
        or 0
    ) + int(
        db.scalar(
            select(func.count())
            .select_from(ConceptUnderstanding)
            .where(ConceptUnderstanding.paper_id == paper_id)
        )
        or 0
    )
    return counts


def _delete_paper_data(db: Session, context: dict[str, Any]) -> tuple[dict[str, int], list[str]]:
    paper_id = context["paper"].id
    revision_ids = context["revision_ids"]
    section_ids = (
        {
            row.id
            for row in db.scalars(
                select(Section).where(Section.document_version_id.in_(revision_ids))
            ).all()
        }
        if revision_ids
        else set()
    )
    session_ids = context["session_ids"]
    job_ids = context["job_ids"]
    source_ids = context["source_ids"]
    managed_paths = {source.managed_path for source in context["sources"] if source.managed_path}
    managed_candidates = [path for value in managed_paths if (path := value)]
    counts: dict[str, int] = {}
    preserve_paper_usage(db, context["paper"], job_ids)

    # Respect FK order. Keep global Provider configuration and the parent Project.
    paper_deletions: tuple[tuple[Any, Any], ...] = (
        (LiteTokenUsage, LiteTokenUsage.paper_id),
        (LiteCacheEntry, LiteCacheEntry.paper_id),
        (ReadingState, ReadingState.paper_id),
        (ConceptUnderstanding, ConceptUnderstanding.paper_id),
        (PaperGraphLayout, PaperGraphLayout.paper_id),
        (PaperReadingResult, PaperReadingResult.paper_id),
        (SectionGuideResult, SectionGuideResult.paper_id),
        (SectionCloseReadingResult, SectionCloseReadingResult.paper_id),
        (UnderstandingCheckResult, UnderstandingCheckResult.paper_id),
        (LiteQARecord, LiteQARecord.paper_id),
        (LiteKeywordRecord, LiteKeywordRecord.paper_id),
        (PDFTranslation, PDFTranslation.paper_id),
    )
    for model, column in paper_deletions:
        counts[model.__tablename__] = _delete_rows(db, model, column, (paper_id,))

    overview_ids = {
        row.id
        for row in db.scalars(
            select(PaperOverviewResult).where(PaperOverviewResult.paper_id == paper_id)
        ).all()
    }
    counts["paper_graph_viewports"] = _delete_rows(
        db, PaperGraphViewport, PaperGraphViewport.overview_result_id, overview_ids
    )
    counts["paper_overview_results"] = _delete_rows(
        db, PaperOverviewResult, PaperOverviewResult.paper_id, (paper_id,)
    )

    if revision_ids:
        counts["chunk_fts"] = _delete_fts_rows(db, revision_ids)
    revision_deletions: tuple[tuple[Any, Any], ...] = (
        (ReadingDocumentProjection, ReadingDocumentProjection.document_version_id),
        (DocumentParse, DocumentParse.document_version_id),
        (EvidenceSpan, EvidenceSpan.document_version_id),
        (Chunk, Chunk.revision_id),
    )
    for model, column in revision_deletions:
        counts[model.__tablename__] = _delete_rows(db, model, column, revision_ids)

    if section_ids:
        # Drop self-links before removing nested Section rows.
        db.execute(update(Section).where(Section.id.in_(section_ids)).values(parent_id=None))
        counts["sections"] = _delete_rows(db, Section, Section.id, section_ids)

    counts["paper_sources"] = _delete_rows(db, PaperSource, PaperSource.paper_id, (paper_id,))
    counts["zotero_links"] = _delete_rows(db, ZoteroLink, ZoteroLink.paper_id, (paper_id,))
    counts["attachment_revisions"] = _delete_rows(
        db, AttachmentRevision, AttachmentRevision.paper_id, (paper_id,)
    )

    counts["import_plan_items"] = _delete_rows(
        db, ImportPlanItem, ImportPlanItem.session_id, session_ids
    )
    batch_run_ids = (
        set(
            db.scalars(
                select(LlmDocumentBatchRun.id).where(
                    LlmDocumentBatchRun.import_session_id.in_(session_ids)
                )
            ).all()
        )
        if session_ids
        else set()
    )
    counts["llm_document_batches"] = _delete_rows(
        db, LlmDocumentBatch, LlmDocumentBatch.run_id, batch_run_ids
    )
    counts["llm_document_batch_runs"] = _delete_rows(
        db, LlmDocumentBatchRun, LlmDocumentBatchRun.id, batch_run_ids
    )
    parse_ids = (
        {
            row.id
            for row in db.scalars(
                select(LlmDocumentParse).where(LlmDocumentParse.import_session_id.in_(session_ids))
            ).all()
        }
        if session_ids
        else set()
    )
    counts["llm_document_outputs"] = _delete_rows(
        db, LlmDocumentOutput, LlmDocumentOutput.import_session_id, session_ids
    )
    counts["llm_chapter_reading_states"] = _delete_rows(
        db, ModelChapterReadingState, ModelChapterReadingState.parse_id, parse_ids
    )
    counts["llm_document_segments"] = _delete_rows(
        db, LlmDocumentSegment, LlmDocumentSegment.parse_id, parse_ids
    )
    counts["llm_document_parses"] = _delete_rows(
        db, LlmDocumentParse, LlmDocumentParse.import_session_id, session_ids
    )
    counts["import_sessions"] = _delete_rows(db, ImportSession, ImportSession.id, session_ids)
    counts["jobs"] = _delete_rows(db, Job, Job.id, job_ids)

    events = list(
        db.scalars(select(Event).where(Event.project_id == context["paper"].project_id)).all()
    )
    identity_set = {paper_id, *revision_ids, *source_ids, *session_ids, *job_ids}
    event_ids = [row.event_id for row in events if _contains_any(row.payload, identity_set)]
    counts["events"] = _delete_rows(db, Event, Event.event_id, event_ids)

    idempotency = list(db.scalars(select(Idempotency)).all())
    idempotency_keys = [row.key for row in idempotency if _contains_any(row.response, identity_set)]
    counts["idempotency_keys"] = _delete_rows(db, Idempotency, Idempotency.key, idempotency_keys)
    counts["papers"] = _delete_rows(db, Paper, Paper.id, (paper_id,))
    return counts, managed_candidates


def _purge_unreferenced_managed_files(
    db: Session, data_dir: Path, candidates: Iterable[str]
) -> tuple[int, list[str]]:
    referenced: set[Path] = set()
    for row in db.execute(select(PaperSource.path, PaperSource.managed_path)):
        for raw_source in row:
            if raw_source:
                try:
                    referenced.add(Path(raw_source).resolve())
                except (OSError, RuntimeError, ValueError):
                    referenced.add(Path(raw_source))
    retained = 0
    pending: list[str] = []
    for raw_path in sorted(set(candidates)):
        try:
            path = _managed_file_candidate(raw_path, data_dir)
            if path is None or path in referenced:
                retained += 1
                continue
            path.unlink(missing_ok=True)
        except OSError:
            pending.append(raw_path)
    return retained, pending


def register_paper_management_api(
    app: FastAPI, get_engine: Callable[[], Engine], data_dir: Path
) -> None:
    @app.patch("/api/v1/papers/{paper_id}", response_model=PaperManagementResult)
    def update_paper(paper_id: str, body: PaperTitleUpdate) -> PaperManagementResult:
        title = body.title.strip()
        if not title:
            raise _failure(422, "INVALID_PAPER_TITLE", "论文标题不能为空")
        with Session(get_engine()) as db, db.begin():
            paper = db.get(Paper, paper_id)
            if paper is None or archived_target(db, "paper", paper.id):
                raise _failure(404, "PAPER_NOT_FOUND", "论文不存在")
            paper.title = title
        return PaperManagementResult(ok=True, paper_id=paper_id)

    @app.delete("/api/v1/papers/{paper_id}/legacy-content", response_model=PaperManagementResult)
    def clear_legacy_content(paper_id: str) -> PaperManagementResult:
        from researchgraph.archive_api import archive_target

        with Session(get_engine()) as db, db.begin():
            item = archive_target(db, "paper_legacy_content", paper_id)
            return PaperManagementResult(paper_id=paper_id, archive_item_id=item.id)

    @app.delete("/api/v1/papers/{paper_id}", response_model=PaperManagementResult)
    def delete_paper(paper_id: str) -> PaperManagementResult:
        from researchgraph.archive_api import archive_target

        with Session(get_engine()) as db, db.begin():
            item = archive_target(db, "paper", paper_id)
            return PaperManagementResult(paper_id=paper_id, archive_item_id=item.id)
