"""Read-only build diagnostics shared by graph, candidate controls and partial rebuilds."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.graph_contracts import PaperBuildStatus
from researchgraph.knowledge_store import KnowledgeStore
from researchgraph.models import AttachmentRevision, Job, Paper
from researchgraph.reading_scope import current_nodes, current_selection


def build_status(session: Session, paper: Paper, version_id: str | None = None) -> PaperBuildStatus:
    current = KnowledgeStore(session).reading().current(paper.id)
    if version_id is None:
        version_id = (
            current.document_version_id
            if current
            else session.scalar(
                select(AttachmentRevision.id)
                .where(AttachmentRevision.paper_id == paper.id)
                .order_by(AttachmentRevision.created_at.desc(), AttachmentRevision.id.desc())
                .limit(1)
            )
        )
    jobs = [
        j
        for j in session.scalars(
            select(Job)
            .where(Job.project_id == paper.project_id, Job.kind == "knowledge_extract")
            .order_by(Job.created_at.desc(), Job.id.desc())
        )
        if (j.payload or {}).get("document_version_id") == version_id
    ]
    extraction = next(
        (
            j
            for j in jobs
            if not (j.payload or {}).get("reading_only")
            and (j.payload or {}).get("pipeline") == "paper-reading-v1"
        ),
        None,
    )
    result = (extraction.result or {}) if extraction else {}
    completed, total = int(result.get("completed_batches", 0)), int(result.get("total_batches", 0))
    count = len(current_nodes(session, version_id)) if version_id else 0
    return PaperBuildStatus(
        paper_id=paper.id,
        title=paper.title,
        document_version_id=version_id,
        candidate_count=count,
        published_units=len(current.data["units"])
        if current_selection(current) and current and current.document_version_id == version_id
        else 0,
        extraction_job_id=extraction.id if extraction else None,
        extraction_status=extraction.status if extraction else None,
        completed_batches=completed,
        total_batches=total,
        extraction_incomplete=not total or completed < total,
        active=any(j.status in {"queued", "running"} for j in jobs),
        ranking_status=current.data.get("ranking_status", "complete")
        if current_selection(current) and current
        else "unknown",
        selection_mode=current.data.get("selection_mode", "ranked")
        if current_selection(current) and current
        else "ranked",
    )


def coverage_note(status: PaperBuildStatus) -> list[str]:
    if not status.extraction_incomplete:
        return []
    progress = (
        f"{status.completed_batches}/{status.total_batches} 批"
        if status.total_batches
        else "范围未确认"
    )
    return [f"原文抽取尚未完整完成（{progress}）；此图仅基于已保存候选，不能代表全文覆盖"]
