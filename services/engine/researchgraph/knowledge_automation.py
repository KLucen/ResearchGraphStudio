"""Atomic post-parse receipts; only these new events may schedule automatic models."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.core import KnowledgeError
from researchgraph.knowledge_connection_models import KnowledgeCollectionEvent
from researchgraph.knowledge_extraction_models import KnowledgeExtractionRun
from researchgraph.knowledge_library import PERSONAL_LIBRARY_ID, library_view
from researchgraph.knowledge_library_models import KnowledgeLibrary
from researchgraph.knowledge_sources import build_knowledge_sources
from researchgraph.model_settings import snapshot_for
from researchgraph.models import Job


def _source(db: Session, job: Job) -> tuple[str, str, str] | None:
    from researchgraph.model_document_models import LlmDocumentOutput, LlmDocumentParse
    from researchgraph.model_document_overview import model_document_paper
    from researchgraph.paper_overview_models import PaperOverviewResult

    payload, result = job.payload or {}, job.result or {}
    parse_id = result.get("parse_id") or payload.get("llm_document_parse_id")
    output = db.get(LlmDocumentOutput, result["output_id"]) if result.get("output_id") else None
    if output:
        parse_id = output.parse_id
    if parse_id:
        parse = db.get(LlmDocumentParse, parse_id)
        owner = model_document_paper(db, parse) if parse else None
        return (owner.id, "model_parse", str(parse_id)) if owner else None
    paper_id = payload.get("paper_id") or result.get("paper_id")
    source_id = (
        payload.get("document_version_id")
        or result.get("revision_id")
        or result.get("document_version_id")
    )
    overview = (
        db.get(PaperOverviewResult, result["overview_result_id"])
        if result.get("overview_result_id")
        else None
    )
    if overview:
        paper_id, source_id = overview.paper_id, overview.document_version_id
    return (str(paper_id), "local_revision", str(source_id)) if paper_id and source_id else None


def note_parsed(db: Session, job: Job) -> None:
    """Call inside the successful source-publication transaction; never call a provider."""
    if job.status != "succeeded" or job.kind not in {
        "pdf_import",
        "zotero_import",
        "llm_document_parse",
        "llm_document_postprocess",
        "paper_overview",
    }:
        return
    if db.get(KnowledgeCollectionEvent, job.id) is not None:
        return
    library = db.get(KnowledgeLibrary, PERSONAL_LIBRARY_ID)
    settings = library_view(library).settings
    if not settings.auto_collect or not settings.allow_network:
        return
    identity = _source(db, job)
    if identity is None:
        return
    paper_id, source_kind, source_id = identity
    event = KnowledgeCollectionEvent(
        job_id=job.id,
        paper_id=paper_id,
        source_kind=source_kind,
        source_id=source_id,
        policy_json=settings.model_dump(),
        model_snapshot={},
        state="pending",
    )
    db.add(event)
    try:
        db.flush()
        manifest = build_knowledge_sources(db, paper_id, source_kind, source_id)
        event.source_fingerprint = manifest["source_fingerprint"]
        event.model_snapshot = snapshot_for(db, None, "knowledge_extract")
    except KnowledgeError as error:
        event.reason = error.code
        if event.source_fingerprint is None:
            event.state = "failed"
    job.result = {
        **(job.result or {}),
        "knowledge_followup": {
            "status": event.state,
            "reason": event.reason,
            "event_id": event.job_id,
        },
    }


def dispatch_collection_events(db: Session) -> None:
    """Recover explicit receipts without scanning historical papers or reparsing PDFs."""
    from researchgraph.knowledge_tasks import queue_knowledge_extract

    settings = library_view(db.get(KnowledgeLibrary, PERSONAL_LIBRARY_ID)).settings
    if not settings.auto_collect or not settings.allow_network:
        return
    for event in db.scalars(
        select(KnowledgeCollectionEvent)
        .where(KnowledgeCollectionEvent.state == "pending")
        .order_by(KnowledgeCollectionEvent.created_at, KnowledgeCollectionEvent.job_id)
    ):
        # Any prior automatic or manual attempt for this exact source consumes
        # the receipt. Failed/sent slots are never retried by an idle poll.
        prior = db.scalar(
            select(KnowledgeExtractionRun)
            .where(
                KnowledgeExtractionRun.paper_id == event.paper_id,
                KnowledgeExtractionRun.source_kind == event.source_kind,
                KnowledgeExtractionRun.source_id == event.source_id,
            )
            .order_by(KnowledgeExtractionRun.created_at.desc())
            .limit(1)
        )
        if prior:
            event.state, event.extraction_job_id, event.reason = "queued", prior.job_id, None
            continue
        try:
            with db.begin_nested():
                manifest = build_knowledge_sources(
                    db, event.paper_id, event.source_kind, event.source_id
                )
                if manifest["source_fingerprint"] != event.source_fingerprint:
                    raise KnowledgeError(
                        "KNOWLEDGE_SOURCE_CHANGED", "解析完成后的来源已改变；未自动生成"
                    )
                snapshot: dict[str, Any] = event.model_snapshot or snapshot_for(
                    db, None, "knowledge_extract"
                )
                job = queue_knowledge_extract(
                    db,
                    paper_id=event.paper_id,
                    source_kind=event.source_kind,
                    source_version_id=event.source_id,
                    model_snapshot=snapshot,
                    allow_network=True,
                    auto_connect=bool(
                        event.policy_json.get("auto_connect") and settings.auto_connect
                    ),
                    policy_snapshot=event.policy_json,
                )
                event.state, event.extraction_job_id, event.reason = "queued", job.id, None
        except KnowledgeError as error:
            event.reason = error.code
            if error.code not in {
                "KNOWLEDGE_TOTAL_BUDGET_EXHAUSTED",
                "KNOWLEDGE_BUDGET_EXHAUSTED",
                "MODEL_NOT_CONFIGURED",
            }:
                event.state = "failed"
        origin = db.get(Job, event.job_id)
        if origin:
            origin.result = {
                **(origin.result or {}),
                "knowledge_followup": {
                    "status": event.state,
                    "reason": event.reason,
                    "event_id": event.job_id,
                    "job_id": event.extraction_job_id,
                },
            }
