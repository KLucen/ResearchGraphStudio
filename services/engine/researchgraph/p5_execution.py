"""One committed dispatch per explicit P5 attempt; no automatic paid retries."""

import asyncio
import copy
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest, text_hash
from researchgraph.model_settings import from_snapshot
from researchgraph.models import Job, now
from researchgraph.p5_models import P5ModelRun, P5Workflow
from researchgraph.p5_transport import PROMPTS, load_prompt, make_wire, output_schema
from researchgraph.p5_workflows import (
    WorkflowInputError,
    checked,
    runs,
    validate_run,
    validate_workflow,
)
from researchgraph.providers import Provider
from researchgraph.query_answers import _provider_error, _safe_metadata
from researchgraph.storage import read_session


def _active(session: Session, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if not job or job.status != "running":
        raise KnowledgeError("P5_CANCELLED", "任务已取消或中断，未自动重发")
    return job


def _record_io(
    engine: Engine,
    run_id: str,
    provider: Provider,
    started: float,
    *,
    raw: str | None,
    complete: bool,
    status: str,
    error: KnowledgeError | None = None,
) -> None:
    secret = getattr(provider, "key", "")
    if secret and raw is not None and secret in raw:
        raw, complete = None, False
        error = KnowledgeError("P5_CREDENTIAL_IN_OUTPUT", "响应含凭据，拒绝保存")
    with Session(engine) as session, session.begin():
        row = session.get(P5ModelRun, run_id)
        assert row
        row.raw_output, row.status, row.finished_at = raw, "failed" if error else status, now()
        row.error = str(error) if error else None
        row.parameters = {
            **row.parameters,
            "raw_complete": complete,
            "raw_sha256": text_hash(raw) if raw is not None else None,
            "usage": {
                k: v for k, v in getattr(provider, "usage", {}).items() if type(v) is int and v >= 0
            },
            "duration_seconds": round(time.monotonic() - started, 3),
            "request_metadata": _safe_metadata(
                copy.deepcopy(getattr(provider, "request_metadata", {})), secret
            ),
            "error_code": error.code if error else None,
            "cost_known": False,
        }
    if error and error.code == "P5_CREDENTIAL_IN_OUTPUT":
        raise error


def _failure(
    engine: Engine,
    job_id: str,
    error: KnowledgeError,
    run_id: str | None = None,
    *,
    status: str = "failed",
) -> None:
    with Session(engine) as session, session.begin():
        job = session.get(Job, job_id)
        if not job:
            return
        workflow = session.get(P5Workflow, (job.payload or {}).get("workflow_id"))
        if job.status == "running":
            job.status, job.error, job.updated_at = status, str(error), now()
            job.result = {**(job.result or {}), "error_code": error.code}
        if workflow and workflow.job_id == job.id and workflow.status != "succeeded":
            workflow.status = job.status
            workflow.error, workflow.error_code, workflow.updated_at = str(error), error.code, now()
        if run_id:
            run = session.get(P5ModelRun, run_id)
            if run and run.status in {"received", "succeeded"}:
                if isinstance(error, WorkflowInputError):
                    run.parameters = {
                        **run.parameters,
                        "reuse_diagnostic": {"code": error.code, "checked_at": now()},
                    }
                else:
                    run.status, run.error, run.finished_at = "validation_failed", str(error), now()
                    run.parameters = {**run.parameters, "error_code": error.code}


def _publish(session: Session, job: Job, workflow: P5Workflow, recorded: P5ModelRun) -> None:
    result = validate_run(session, workflow, recorded)
    workflow.result, workflow.status = result, "succeeded"
    workflow.error, workflow.error_code, workflow.updated_at = None, None, now()
    recorded.status, recorded.error = "succeeded", None
    recorded.parameters = {**recorded.parameters, "validated_result_hash": digest(result)}
    job.status, job.stage, job.updated_at, job.error = "succeeded", "saving", now(), None
    job.result = {
        "workflow_id": workflow.id,
        "model_run_id": recorded.id,
        "request_count": len(runs(session, workflow.id)),
        "error_code": None,
    }
    KnowledgeStore(session).audit_event(
        workflow.project_id,
        "p5.generated",
        {"workflow_id": workflow.id, "kind": workflow.kind, "model_run_id": recorded.id},
    )


async def execute(engine: Engine, job_id: str, *, testing_provider: Provider | None = None) -> None:
    run_id: str | None = None
    provider = testing_provider
    try:
        with Session(engine) as session, session.begin():
            job = _active(session, job_id)
            payload = dict(job.payload or {})
            if job.kind != "p5_workflow" or not payload.get("allow_network") or not job.project_id:
                raise KnowledgeError("P5_PURPOSE_REQUIRED", "任务缺少明确的模型用途授权")
            workflow = checked(session, job.project_id, payload["workflow_id"])
            validate_workflow(session, workflow, require_head=True)
            if payload.get("input_hash") != workflow.input_hash:
                raise KnowledgeError("P5_PROTOCOL_CHANGED", "调度输入与冻结工作流不一致")
            for old in runs(session, workflow.id):
                if old.parameters.get("raw_complete"):
                    try:
                        validate_run(session, workflow, old)
                    except WorkflowInputError:
                        raise
                    except KnowledgeError as exc:
                        old.parameters = {**old.parameters, "last_validation_code": exc.code}
                    else:
                        _publish(session, job, workflow, old)
                        return
            previous = runs(session, workflow.id)
            if len(previous) >= min(2, payload["request_budget"]):
                raise KnowledgeError("P5_REQUEST_LIMIT", "已发送请求槽位不会重复使用")
            snapshot = copy.deepcopy(workflow.snapshot)
            workflow_id, project_id = workflow.id, workflow.project_id
        if provider is None:
            try:
                provider = await asyncio.to_thread(
                    from_snapshot, snapshot["model"], Path(str(engine.url.database)).parent, True
                )
            except Exception:
                raise KnowledgeError(
                    "P5_MODEL_CONFIGURATION", "冻结模型配置不可用，请检查全局设置"
                ) from None
        with Session(engine) as session, session.begin():
            job = _active(session, job_id)
            workflow = checked(session, project_id, workflow_id)
            validate_workflow(session, workflow, require_head=True)
            recorded = runs(session, workflow.id)
            if len(recorded) >= min(2, payload["request_budget"]):
                raise KnowledgeError("P5_REQUEST_LIMIT", "请求槽位已使用，停止重复发送")
            run_id = str(uuid4())
            session.add(
                P5ModelRun(
                    id=run_id,
                    workflow_id=workflow_id,
                    job_id=job_id,
                    sequence=len(recorded) + 1,
                    prompt_name=PROMPTS[workflow.kind],
                    prompt_hash=snapshot["prompt_hash"],
                    input_hash=snapshot["wire_hash"],
                    parameters={
                        "model_snapshot": snapshot["model"],
                        "workflow_hash": workflow.input_hash,
                        "schema_hash": snapshot["schema_hash"],
                        "dispatch_policy": "persist-before-io-no-resend-1",
                        "raw_complete": False,
                        "cost_known": False,
                        "usage": {},
                    },
                    status="running",
                    created_at=now(),
                )
            )
            workflow.status, workflow.updated_at = "running", now()
            job.stage, job.updated_at = "reasoning", now()
            kind = workflow.kind
        prompt = load_prompt(kind)
        wire = make_wire(
            kind, snapshot["context"], snapshot["base"], snapshot["targets"], snapshot["lint"]
        )
        schema = output_schema(kind, snapshot["context"], list(snapshot["targets"]))
        started = time.monotonic()
        task = asyncio.create_task(provider.complete(prompt, wire, schema))
        try:
            while not task.done():
                await asyncio.wait({task}, timeout=0.1)
                with read_session(engine) as session:
                    _active(session, job_id)
                if time.monotonic() - started > min(
                    float(getattr(provider, "total_timeout", 180)), 300
                ):
                    raise TimeoutError
            raw = await task
        except asyncio.CancelledError:
            _record_io(
                engine,
                run_id,
                provider,
                started,
                raw=getattr(provider, "partial_output", None),
                complete=False,
                status="interrupted",
            )
            raise
        except KnowledgeError:
            _record_io(
                engine,
                run_id,
                provider,
                started,
                raw=getattr(provider, "partial_output", None),
                complete=False,
                status="cancelled",
            )
            raise
        except Exception as exc:
            error = _provider_error(exc)
            error = KnowledgeError(error.code.replace("QUERY_", "P5_", 1), str(error))
            _record_io(
                engine,
                run_id,
                provider,
                started,
                raw=getattr(provider, "partial_output", None),
                complete=False,
                status="failed",
                error=error,
            )
            _failure(engine, job_id, error)
            return
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        _record_io(engine, run_id, provider, started, raw=raw, complete=True, status="received")
        with Session(engine) as session, session.begin():
            job = _active(session, job_id)
            workflow = checked(session, project_id, workflow_id)
            validate_workflow(session, workflow, require_head=True)
            run = session.get(P5ModelRun, run_id)
            assert run
            _publish(session, job, workflow, run)
    except asyncio.CancelledError:
        _failure(
            engine,
            job_id,
            KnowledgeError("P5_INTERRUPTED", "应用退出，已发送请求保留且不自动重发"),
            status="interrupted",
        )
        raise
    except KnowledgeError as exc:
        _failure(
            engine,
            job_id,
            exc,
            run_id,
            status="cancelled" if exc.code == "P5_CANCELLED" else "failed",
        )
    except Exception:
        _failure(
            engine,
            job_id,
            KnowledgeError("P5_EXECUTION_FAILED", "任务执行失败，原始记录保留；请查看运行状态"),
        )
