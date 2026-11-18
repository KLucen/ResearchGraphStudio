"""Durable local formula OCR jobs; HTTP requests never wait for inference."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, Header
from sqlalchemy import Engine, Select, select
from sqlalchemy.orm import Session

from researchgraph.core import KnowledgeError
from researchgraph.formula_api import FormulaRecognitionRequest
from researchgraph.models import AttachmentRevision, Idempotency, Job, Paper, now
from researchgraph.schemas import JobView
from researchgraph.storage import read_session

TASK_KIND = "formula_recognition"


def _job_query(revision_id: str) -> Select[Job]:
    return (
        select(Job)
        .where(Job.kind == TASK_KIND, Job.payload["revision_id"].as_string() == revision_id)
        .order_by(Job.created_at.desc(), Job.id.desc())
    )


def register_formula_jobs_api(app: FastAPI, get_engine: Callable[[], Engine]) -> None:
    @app.get(
        "/api/v1/revisions/{revision_id}/formulas/recognize/jobs", response_model=JobView | None
    )
    def latest_formula_job(revision_id: str) -> JobView | None:
        with read_session(get_engine()) as session:
            if session.get(AttachmentRevision, revision_id) is None:
                raise KnowledgeError("DOCUMENT_NOT_FOUND", "文献版本不存在")
            row = session.scalar(_job_query(revision_id).limit(1))
            return JobView.model_validate(row) if row is not None else None

    @app.post(
        "/api/v1/revisions/{revision_id}/formulas/recognize/jobs",
        response_model=JobView,
        status_code=202,
    )
    def queue_formula_job(
        revision_id: str,
        body: FormulaRecognitionRequest,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=1, max_length=120)
        ],
    ) -> JobView:
        payload = {"revision_id": revision_id, **body.model_dump()}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        key = f"formula-ocr:{idempotency_key}"
        # The existing IMMEDIATE writer serializes duplicate enqueue attempts.
        # No PDF, model import or inference is performed in this short request.
        with Session(get_engine()) as session, session.begin():
            revision = session.get(AttachmentRevision, revision_id)
            if revision is None:
                raise KnowledgeError("DOCUMENT_NOT_FOUND", "文献版本不存在")
            paper = session.get(Paper, revision.paper_id)
            if paper is None:
                raise KnowledgeError("PAPER_NOT_FOUND", "论文不存在")
            previous = session.get(Idempotency, key)
            if previous is not None:
                if previous.request_hash != digest:
                    raise KnowledgeError("IDEMPOTENCY_CONFLICT", "请求标识已用于不同公式范围")
                row = session.get(Job, previous.response["job_id"])
                if row is not None:
                    return JobView.model_validate(row)
            active: Job | None = session.scalar(
                _job_query(revision_id).where(Job.status.in_(["queued", "running"])).limit(1)
            )
            if active is not None:
                row = active
            else:
                row = Job(
                    id=str(uuid4()),
                    kind=TASK_KIND,
                    project_id=paper.project_id,
                    payload=payload,
                    status="queued",
                    stage="queued",
                    attempt=0,
                    result={
                        "revision_id": revision_id,
                        "processed": 0,
                        "total": None,
                        "model_calls": 0,
                    },
                    created_at=now(),
                    updated_at=now(),
                )
            session.add(row)
            session.flush()
            session.add(
                Idempotency(key=key, request_hash=digest, response={"job_id": row.id})
            )
            return JobView.model_validate(row)


async def execute_formula_recognition(engine: Engine, job_id: str, data_dir: Path) -> None:
    from researchgraph.formula_api import recognize_revision_formulas
    from researchgraph.formula_ocr import configured_formula_recognizer

    stop = Event()

    def cancelled() -> bool:
        if stop.is_set():
            return True
        with read_session(engine) as session:
            row = session.get(Job, job_id)
            return row is None or row.status != "running"

    def progress(processed: int, total: int) -> None:
        with Session(engine) as session, session.begin():
            row = session.get(Job, job_id)
            if row is not None and row.status == "running":
                row.stage = "recognizing"
                row.result = {**(row.result or {}), "processed": processed, "total": total}
                row.updated_at = now()

    def run() -> None:
        with read_session(engine) as session:
            row = session.get(Job, job_id)
            if row is None or row.status != "running":
                return
            payload = dict(row.payload or {})
        revision_id = str(payload.pop("revision_id"))
        try:
            result = recognize_revision_formulas(
                engine,
                revision_id,
                FormulaRecognitionRequest.model_validate(payload),
                data_dir,
                configured_formula_recognizer(data_dir),
                progress=progress,
                cancelled=cancelled,
            )
            with Session(engine) as session, session.begin():
                row = session.get(Job, job_id)
                if row is not None and row.status == "running" and not stop.is_set():
                    row.result = {
                        **result.model_dump(),
                        "processed": len(result.items),
                        "total": len(result.items),
                    }
                    failed = result.status in {"failed", "unavailable"}
                    row.status = "failed" if failed else "succeeded"
                    row.stage = "failed" if failed else "completed"
                    row.error = (
                        next((item.message for item in result.items if item.error_code), None)
                        if failed
                        else None
                    )
                    row.updated_at = now()
        except Exception as error:
            with Session(engine) as session, session.begin():
                row = session.get(Job, job_id)
                if row is not None and row.status == "running" and not stop.is_set():
                    row.status, row.stage = "failed", "failed"
                    row.error = (
                        f"{error.code} · {error}"
                        if isinstance(error, KnowledgeError)
                        else f"本地公式识别失败：{type(error).__name__}"
                    )
                    row.updated_at = now()

    inference = asyncio.create_task(asyncio.to_thread(run))
    try:
        await asyncio.shield(inference)
    except asyncio.CancelledError:
        # An in-progress CPU crop cannot be interrupted mid-ONNX call. Wait
        # for that crop, prevent publication, then let normal recovery mark it
        # interrupted. Never dispose the DB underneath an inference thread.
        stop.set()
        await inference
        raise
