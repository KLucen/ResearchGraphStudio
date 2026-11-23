"""Claim, supervise and dispatch durable tasks independently of the HTTP routes."""

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import Engine, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from researchgraph.ingest import run_file_job
from researchgraph.models import Job, now
from researchgraph.retired_tasks import retire_translation_jobs
from researchgraph.storage import database_busy, diagnostics, read_session
from researchgraph.task_runtime import ClaimedJob, Lane, ModelWaitCancelled, TaskRuntime

logger = logging.getLogger(__name__)


def claim_queued_job(engine: Engine) -> tuple[str, str] | None:
    job = _claim_queued_job(engine)
    return (job.job_id, job.kind) if job else None


def _claim_queued_job(engine: Engine, lane: Lane | None = None) -> ClaimedJob | None:
    pending = select(Job.id).where(Job.status == "queued").order_by(Job.created_at, Job.id).limit(1)
    if lane == "diagnostics":
        pending = pending.where(Job.kind == "diagnostics")
    elif lane == "jobs":
        pending = pending.where(Job.kind != "diagnostics")
    with read_session(engine) as session:
        candidate = session.scalar(pending)
    if candidate is None:
        return None
    with Session(engine) as session, session.begin():
        # A cancel or another claimant can win after the read-only poll.
        job = session.get(Job, candidate)
        if job is None or job.status != "queued":
            return None
        if job.kind == "pdf_translation":
            retire_translation_jobs(session, job.id)
            return None
        job.status, job.updated_at = "running", now()
        job.stage = "diagnostics" if job.kind == "diagnostics" else "starting"
        job.attempt += 1
        return ClaimedJob(job.id, job.kind, job.attempt)


def finish_diagnostic(
    engine: Engine, job_id: str, result: dict[str, str | bool] | None, error: str | None
) -> None:
    with Session(engine) as session, session.begin():
        current = session.get(Job, job_id)
        if current and current.status == "running":
            current.status = "failed" if error else "succeeded"
            if result is not None:
                current.result = result
            current.error, current.updated_at = error, now()
            from researchgraph.model_document_api import synchronize_import_job

            synchronize_import_job(session, current)


def after_knowledge_job(engine: Engine, job_id: str) -> None:
    """Queue only newly completed work under the user's saved library policy."""
    from researchgraph.knowledge_automation import dispatch_collection_events
    from researchgraph.knowledge_connection_models import KnowledgeAnalysisEvent
    from researchgraph.knowledge_connections import queue_auto_connections

    with Session(engine) as session, session.begin():
        job = session.get(Job, job_id)
        if job is None or job.status != "succeeded":
            return
        if job.kind == "knowledge_extract":
            version_id = (job.result or {}).get("knowledge_version_id")
            if version_id and session.get(KnowledgeAnalysisEvent, version_id) is not None:
                queue_auto_connections(session, version_id)
        else:
            dispatch_collection_events(session)


def dispatch_pending_knowledge(engine: Engine) -> None:
    """Avoid acquiring a writer on ordinary idle polls or disabled policies."""
    from researchgraph.knowledge_automation import dispatch_collection_events
    from researchgraph.knowledge_connection_models import (
        KnowledgeAnalysisEvent,
        KnowledgeCollectionEvent,
    )
    from researchgraph.knowledge_connections import dispatch_pending_analysis
    from researchgraph.knowledge_library import PERSONAL_LIBRARY_ID, library_view
    from researchgraph.knowledge_library_models import KnowledgeLibrary

    with read_session(engine) as session:
        settings = library_view(session.get(KnowledgeLibrary, PERSONAL_LIBRARY_ID)).settings
        pending = session.scalar(
            select(KnowledgeAnalysisEvent.version_id)
            .where(KnowledgeAnalysisEvent.state == "pending")
            .limit(1)
        )
        collection_pending = session.scalar(
            select(KnowledgeCollectionEvent.job_id)
            .where(KnowledgeCollectionEvent.state == "pending")
            .limit(1)
        )
        if not settings.allow_network or not (
            settings.auto_connect
            and pending is not None
            or settings.auto_collect
            and collection_pending is not None
        ):
            return
    with Session(engine) as session, session.begin():
        dispatch_collection_events(session)
        dispatch_pending_analysis(session)


async def _worker_call[**P, T](operation: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    task = asyncio.create_task(asyncio.to_thread(operation, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # A thread may still commit after cancellation. Its DB work must finish
        # before shutdown marks interrupted jobs and releases the workspace lock.
        with suppress(Exception):
            await task
        raise


async def _run_job(engine: Engine, job: ClaimedJob, data_dir: Path) -> dict[str, str | bool] | None:
    if not await _worker_call(_job_is_running, engine, job):
        return None
    job_id, kind = job.job_id, job.kind
    if kind == "knowledge_extract":
        from researchgraph.knowledge_tasks import run_knowledge_extract

        await run_knowledge_extract(engine, job_id, data_dir)
    elif kind == "knowledge_connect":
        from researchgraph.knowledge_connections import run_knowledge_connect

        await run_knowledge_connect(engine, job_id, data_dir)
    elif kind == "formula_recognition":
        from researchgraph.formula_jobs import execute_formula_recognition

        await execute_formula_recognition(engine, job_id, data_dir)
    elif kind == "llm_document_parse":
        from researchgraph.model_document_api import execute_document_parse

        await execute_document_parse(engine, job_id, data_dir)
    elif kind == "llm_document_postprocess":
        from researchgraph.model_document_api import execute_document_postprocess

        await execute_document_postprocess(engine, job_id, data_dir)
    elif kind == "paper_overview":
        from researchgraph.paper_overview_api import execute_overview

        await execute_overview(engine, job_id, data_dir)
    elif kind == "section_guide":
        from researchgraph.section_guide_api import execute_section_guide

        await execute_section_guide(engine, job_id, data_dir)
    elif kind == "section_close_reading":
        from researchgraph.close_reading_api import execute_close_reading

        await execute_close_reading(engine, job_id, data_dir)
    elif kind == "paper_reading_notes":
        from researchgraph.paper_reading_api import execute_paper_reading

        await execute_paper_reading(engine, job_id, data_dir)
    elif kind == "understanding_check":
        from researchgraph.close_reading_api import execute_understanding_check

        await execute_understanding_check(engine, job_id, data_dir)
    elif kind == "grounded_qa":
        from researchgraph.qa_api import execute_qa

        await execute_qa(engine, job_id, data_dir)
    elif kind == "search_keywords":
        from researchgraph.keyword_api import execute_keyword_expansion

        await execute_keyword_expansion(engine, job_id, data_dir)
    elif kind in {"pdf_import", "zotero_import", "source_check", "source_relocate"}:
        with read_session(engine) as read_db:
            queued_job = read_db.get(Job, job_id)
            model_first = bool(queued_job and (queued_job.payload or {}).get("model_first"))
        if kind in {"pdf_import", "zotero_import"} and model_first:
            # A model-first import only tries the frozen model transport.
            from researchgraph.model_document_api import execute_document_parse

            await execute_document_parse(engine, job_id, data_dir)
        else:
            await run_file_job(engine, job_id, data_dir)
    elif kind == "diagnostics":
        return await _worker_call(diagnostics, engine)
    else:
        raise ValueError("任务类型不受当前 Lite 版本支持")

    if kind in {
        "knowledge_extract",
        "llm_document_parse",
        "llm_document_postprocess",
        "paper_overview",
        "pdf_import",
        "zotero_import",
    }:
        await _worker_call(after_knowledge_job, engine, job_id)
    return None


def _job_is_running(engine: Engine, job: ClaimedJob) -> bool:
    with read_session(engine) as session:
        row = session.get(Job, job.job_id)
        return row is not None and row.status == "running" and row.attempt == job.attempt


def _interrupt_claim(engine: Engine, job: ClaimedJob) -> None:
    with Session(engine) as session, session.begin():
        session.execute(
            update(Job)
            .where(Job.id == job.job_id, Job.attempt == job.attempt, Job.status == "running")
            .values(
                status="interrupted",
                error="任务结果保存中断，未自动重发；请查看任务记录",
                updated_at=now(),
            )
        )


def _worker_failure(runtime: TaskRuntime, lane: Lane, error: Exception) -> None:
    code = (
        "DATABASE_BUSY"
        if isinstance(error, OperationalError) and database_busy(error)
        else "WORKER_RECOVERING"
    )
    if code == "WORKER_RECOVERING" and runtime.lanes[lane] != ("recovering", code):
        logger.warning("Task worker recovered from %s in %s", type(error).__name__, lane)
    runtime.set_status(lane, "recovering", code)


async def _persist_job_outcome(
    engine: Engine,
    runtime: TaskRuntime,
    lane: Lane,
    job: ClaimedJob,
    result: dict[str, str | bool] | None,
    error: str | None,
) -> None:
    interrupted = False
    while True:
        try:
            if interrupted:
                await _worker_call(_interrupt_claim, engine, job)
            else:
                await _worker_call(finish_diagnostic, engine, job.job_id, result, error)
            return
        except Exception as exc:
            _worker_failure(runtime, lane, exc)
            if not isinstance(exc, OperationalError) or not database_busy(exc):
                interrupted = True
            # Retry only the terminal write. Never execute this claim again.
            await asyncio.sleep(0.25)


async def _work_lane(engine: Engine, data_dir: Path, runtime: TaskRuntime, lane: Lane) -> None:
    next_dispatch = 0.0
    while True:
        if runtime.paused():
            await asyncio.sleep(0.15)
            continue
        runtime.claiming += 1
        try:
            loop_time = runtime.loop.time()
            dispatch_failed = False
            if lane == "jobs" and loop_time >= next_dispatch:
                try:
                    await _worker_call(dispatch_pending_knowledge, engine)
                except Exception as exc:
                    _worker_failure(runtime, lane, exc)
                    dispatch_failed = True
                next_dispatch = loop_time + (1 if dispatch_failed else 30)
            job = await _worker_call(_claim_queued_job, engine, lane)
        except Exception as exc:
            _worker_failure(runtime, lane, exc)
            await asyncio.sleep(0.25)
            continue
        finally:
            runtime.claiming -= 1
        if job is None:
            if not dispatch_failed:
                runtime.set_status(lane, "idle")
            await asyncio.sleep(0.15)
            continue

        runtime.set_status(lane, "running")
        try:
            result = await runtime.execute(job, _run_job(engine, job, data_dir))
        except ModelWaitCancelled:
            continue
        except Exception as exc:
            error = (
                "模型输出未通过 Schema 校验，请查看模型运行记录"
                if isinstance(exc, ValidationError)
                else str(exc)
                if lane == "jobs" and isinstance(exc, (ValueError, RuntimeError))
                else f"任务失败：{type(exc).__name__}，请检查文件或数据库权限"
            )
            await _persist_job_outcome(engine, runtime, lane, job, None, error)
        else:
            if result is not None:
                await _persist_job_outcome(engine, runtime, lane, job, result, None)


async def worker(engine: Engine, data_dir: Path, runtime: TaskRuntime | None = None) -> None:
    runtime = runtime or TaskRuntime(enabled=True)

    async def supervise(lane: Lane) -> None:
        try:
            while True:
                try:
                    await _work_lane(engine, data_dir, runtime, lane)
                except Exception as exc:
                    _worker_failure(runtime, lane, exc)
                    await asyncio.sleep(0.25)
        finally:
            runtime.set_status(lane, "stopped", "WORKER_STOPPED")

    async with asyncio.TaskGroup() as group:
        group.create_task(supervise("jobs"))
        group.create_task(supervise("diagnostics"))
