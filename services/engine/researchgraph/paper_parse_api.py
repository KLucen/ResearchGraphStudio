"""Explicit local parsing or a fresh model parse of an existing paper."""

from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.import_plan_api import create_import_session_record, normalize_post_import_plan
from researchgraph.model_settings import snapshot_for
from researchgraph.models import Job, Paper, PaperSource, now
from researchgraph.schemas import JobView, PaperParseRequest, SourceSnapshot


def _source_payload(db: Session, paper: Paper, data_dir: Path) -> dict[str, Any]:
    from researchgraph.app import failure

    sources = db.scalars(
        select(PaperSource)
        .where(PaperSource.paper_id == paper.id)
        .order_by(PaperSource.generation.desc(), PaperSource.id)
    ).all()
    for source in sources:
        if source.mode == "managed" and source.managed_path:
            managed = Path(source.managed_path)
            if (
                managed.is_file()
                and managed.suffix.lower() == ".pdf"
                and managed.resolve().is_relative_to((data_dir / "attachments").resolve())
            ):
                return {
                    "path": source.path,
                    "parse_path": str(managed.resolve()),
                    "mode": source.mode,
                }
        path = Path(source.path)
        if path.is_absolute() and path.suffix.lower() == ".pdf" and path.is_file():
            return {"path": str(path), "mode": source.mode}
    # Model-only imports do not have a legacy PaperSource. Reuse only an
    # existing job's engine-held source for this exact paper, never a UI path.
    jobs = db.scalars(
        select(Job)
        .where(Job.project_id == paper.project_id)
        .order_by(Job.created_at.desc(), Job.id.desc())
    ).all()
    for job in jobs:
        payload = job.payload or {}
        if payload.get("paper_id") != paper.id and (job.result or {}).get("paper_id") != paper.id:
            continue
        if job.kind not in {"pdf_import", "zotero_import", "llm_document_parse"}:
            continue
        path = Path(str(payload.get("parse_path") or payload.get("path") or ""))
        if path.is_absolute() and path.suffix.lower() == ".pdf" and path.is_file():
            return {"path": str(path), "mode": payload.get("mode", "reference")}
        if all(
            payload.get(key) for key in ("library", "item_key", "attachment_key", "collection_key")
        ):
            return {
                **{
                    key: payload[key]
                    for key in ("library", "item_key", "attachment_key", "collection_key")
                },
                "mode": payload.get("mode", "reference"),
            }
    raise failure(409, "PAPER_SOURCE_UNAVAILABLE", "没有可读取的已登记 PDF，请检查源文件或重新导入")


def register_paper_parse_api(app: FastAPI, engine: Callable[[], Engine], data_dir: Path) -> None:
    from researchgraph.app import Key, failure, remember, remembered

    @app.post("/api/v1/papers/{paper_id}/parse", response_model=JobView, status_code=202)
    def parse_paper(paper_id: str, body: PaperParseRequest, idempotency_key: Key) -> JobView:
        request = {"paper_id": paper_id, **body.model_dump()}
        key = "paper-parse:" + idempotency_key
        with Session(engine()) as db, db.begin():
            paper = db.get(Paper, paper_id)
            if paper is None:
                raise failure(404, "PAPER_NOT_FOUND", "论文不存在")
            previous = remembered(db, key, request)
            if previous:
                return JobView.model_validate(previous)
            active = db.scalars(
                select(Job).where(
                    Job.project_id == paper.project_id, Job.status.in_(["queued", "running"])
                )
            ).all()
            if any(
                (job.payload or {}).get("paper_id") == paper_id
                and job.kind
                in {"pdf_import", "zotero_import", "llm_document_parse", "llm_document_postprocess"}
                for job in active
            ):
                raise failure(
                    409, "PAPER_PARSE_ACTIVE", "这篇论文仍有解析或生成任务，请等待完成或先取消"
                )
            payload = {
                **_source_payload(db, paper, data_dir),
                "paper_id": paper.id,
                "project_id": paper.project_id,
                "title": paper.title,
            }
            kind = "zotero_import" if "library" in payload else "pdf_import"
            job = Job(
                id=str(uuid4()),
                project_id=paper.project_id,
                kind=kind,
                payload=payload,
                status="queued",
                stage="queued",
                attempt=0,
                created_at=now(),
                updated_at=now(),
            )
            db.add(job)
            db.flush()
            if body.mode == "model":
                plan = normalize_post_import_plan(body.post_import_plan)
                assert plan is not None
                snapshot = snapshot_for(db, paper.project_id, "document_parse")
                session, items = create_import_session_record(
                    db,
                    project_id=paper.project_id,
                    source_kind="zotero" if kind == "zotero_import" else "pdf",
                    selection_id="paper-parse:" + job.id,
                    source_snapshot=SourceSnapshot(
                        paper_id=paper.id,
                        file_name=Path(str(payload.get("path", "paper.pdf"))).name,
                    ),
                    plan=plan,
                )
                job.payload = {
                    **payload,
                    "path": payload.get("parse_path", payload.get("path")),
                    "model_first": True,
                    "import_session_id": session.id,
                    "allow_network": True,
                    "provider_snapshot": snapshot,
                    "modality": plan.modality,
                    "require_multimodal": plan.require_multimodal,
                }
                item = next(item for item in items if item.item_kind == "document_parse")
                item.job_id, item.status = job.id, "queued"
                session.status = "queued"
            response = JobView.model_validate(job)
            remember(db, key, request, response.model_dump())
            return response
