"""Bounded, resumable project-level P07 execution; never writes scientific knowledge.

Each QueryModelRun is a durable dispatch slot committed before network I/O.
A missing/failed response never permits that slot to be resent. Only an explicit
continuation can reserve the second slot. Complete received raw is revalidated
before either publishing it or considering another paid request.
"""

from __future__ import annotations

import asyncio
import copy
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import uuid4

from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest, text_hash
from researchgraph.model_settings import from_snapshot
from researchgraph.models import Job, now
from researchgraph.providers import Provider, ProviderError
from researchgraph.query_answer_contracts import QueryAnswerView, QueryModelExecutionView
from researchgraph.query_answer_wire import (
    LAYOUT_PROMPT,
    POLICY,
    PROMPT,
    assert_prompt_contract,
    bind_answer,
    display_normalization,
    model_input,
    output_schema,
)
from researchgraph.query_context import validate_context
from researchgraph.query_contracts import QueryAnswer
from researchgraph.query_models import QueryAnswerVersion, QueryModelRun, QueryOperation, QueryRun
from researchgraph.storage import read_session

MAX_REQUESTS = 2
PROMPT_PATH = Path(__file__).parent / "prompts" / (PROMPT + ".md")
LAYOUT_PROMPT_PATH = Path(__file__).parent / "prompts" / (LAYOUT_PROMPT + ".md")
_CONTEXT_ERRORS = {
    "QUERY_CONTEXT_CHANGED",
    "QUERY_PERMISSION_CHANGED",
    "QUERY_DOCUMENT_INVALID",
    "QUERY_SOURCE_INVALID",
    "QUERY_SOURCE_EXCLUDED",
    "QUERY_PARSE_INVALID",
    "QUERY_MANIFEST_INVALID",
    "QUERY_SCOPE_MISMATCH",
    "QUERY_SCOPE_INVALID",
    "QUERY_SEED_INVALID",
    "QUERY_PROTOCOL_CHANGED",
    "QUERY_RESPONSE_CHANGED",
    "PROJECT_NOT_FOUND",
    "INVALID_ANCHOR",
    "INVALID_SECTION",
    "INVALID_TABLE",
    "PARSE_SOURCE_MISMATCH",
    "PARSE_ANCHOR_MISMATCH",
    "ROOT_NOT_AUTHORIZED",
}
_NONRETRYABLE = _CONTEXT_ERRORS | {
    "QUERY_MODEL_CONFIGURATION",
    "QUERY_PURPOSE_REQUIRED",
    "QUERY_MODEL_NOT_CONFIGURED",
    "QUERY_MODEL_CLIENT",
    "QUERY_MODEL_REFUSED",
    "QUERY_MODEL_CONTEXT_LIMIT",
    "QUERY_CREDENTIAL_IN_OUTPUT",
    "QUERY_NUMERIC_LAYOUT_UNRESOLVED",
}


class StopSignal(Protocol):
    def is_set(self) -> bool: ...


@dataclass(frozen=True)
class Plan:
    prompt_name: str
    prompt: str
    schema: dict[str, Any]
    wire: dict[str, Any]
    manifest: dict[str, Any]
    signature: str


def _checked_query(session: Session, project_id: str, query_id: str) -> QueryRun:
    query = session.get(QueryRun, query_id)
    if not query or query.project_id != project_id:
        raise KnowledgeError("QUERY_NOT_FOUND", "项目中不存在该查询")
    context = query.snapshot.get("context", {})
    if (
        query.input_hash != context.get("input_hash")
        or query.snapshot.get("request") != query.request
        or context.get("project_id") != project_id
        or any(
            context.get("request", {}).get(k) != query.request.get(k)
            for k in ("question", "purpose", "include_personal")
        )
    ):
        raise KnowledgeError("QUERY_MANIFEST_INVALID", "查询来源清单或请求身份已变化")
    validate_context(
        session, context, query.snapshot["retrieval"], model_snapshot=query.snapshot.get("model")
    )
    return query


def _purpose(query: QueryRun) -> None:
    if query.request.get("purpose") != "model":
        raise KnowledgeError("QUERY_PURPOSE_REQUIRED", "请明确选择模型用途并重新准备证据上下文")


def _no_call_reason(query: QueryRun) -> list[str] | None:
    context = query.snapshot["context"]
    if context.get("scope_coverage", {}).get("missing_paper_ids"):
        return ["显式选定论文未全部找到可验证的正文根证据；保留已找到来源，未调用模型"]
    if not context.get("capacity", {}).get("sufficient", True):
        return ["完整证据上下文超过当前已知模型容量；未调用模型或截断必要支撑"]
    if not any(ref["type"] in {"chunk", "evidence", "note"} for ref in context["references"]):
        return ["当前范围未找到可验证的原始论文证据或授权个人资料；未调用模型"]
    return None


def _plan(query: QueryRun) -> Plan:
    prompt_name = LAYOUT_PROMPT if "numeric_layout" in query.snapshot["context"] else PROMPT
    prompt = (LAYOUT_PROMPT_PATH if prompt_name == LAYOUT_PROMPT else PROMPT_PATH).read_text(
        encoding="utf-8"
    )
    assert_prompt_contract(prompt)
    context = query.snapshot["context"]
    schema = output_schema([ref["ref"] for ref in context["references"]])
    wire = model_input(context)
    manifest = {
        "policy": POLICY,
        "query_id": query.id,
        "project_id": query.project_id,
        "query_input_hash": query.input_hash,
        "context": context,
        "model_snapshot_hash": digest(query.snapshot.get("model")),
        "wire_hash": digest(wire),
        "schema_hash": digest(schema),
        "prompt_hash": text_hash(prompt),
    }
    return Plan(prompt_name, prompt, schema, wire, manifest, digest(manifest))


def _state(session: Session, query: QueryRun, plan: Plan) -> QueryOperation | None:
    state = session.get(QueryOperation, "query-answer-state:" + query.id)
    if state and (state.request_hash != plan.signature or state.response.get("policy") != POLICY):
        raise KnowledgeError("QUERY_PROTOCOL_CHANGED", "回答协议或冻结输入已变化，请重新准备查询")
    return state


def _runs(session: Session, query_id: str) -> list[QueryModelRun]:
    return list(
        session.scalars(
            select(QueryModelRun)
            .where(QueryModelRun.query_run_id == query_id)
            .order_by(QueryModelRun.created_at, QueryModelRun.id)
        )
    )


def _latest_answer(session: Session, query_id: str) -> QueryAnswerVersion | None:
    return session.scalar(
        select(QueryAnswerVersion)
        .where(QueryAnswerVersion.query_run_id == query_id)
        .order_by(QueryAnswerVersion.revision.desc())
        .limit(1)
    )


def _validate_run(
    session: Session, query: QueryRun, run: QueryModelRun, plan: Plan, sequence: int
) -> None:
    snapshot = query.snapshot.get("model") or {}
    dispatch_id = run.parameters.get("dispatch", {}).get("job_id")
    dispatch_job = session.get(Job, dispatch_id) if dispatch_id else None
    if (
        run.query_run_id != query.id
        or run.project_id != query.project_id
        or run.provider != snapshot.get("provider")
        or run.model != snapshot.get("model")
        or run.prompt_name != plan.prompt_name
        or run.prompt_hash != text_hash(plan.prompt)
        or run.schema_version != POLICY
        or run.input_hash != digest(plan.wire)
        or run.manifest != plan.manifest
        or run.parameters.get("model_snapshot") != snapshot
        or run.parameters.get("dispatch", {}).get("sequence") != sequence
        or not dispatch_job
        or dispatch_job.kind != "query_answer"
        or dispatch_job.project_id != query.project_id
        or (dispatch_job.payload or {}).get("query_id") != query.id
        or (dispatch_job.payload or {}).get("plan_signature") != plan.signature
    ):
        raise KnowledgeError("QUERY_RESPONSE_CHANGED", "回答模型记录或请求谱系已变化，停止复用")
    if run.raw_output is not None and run.parameters.get("raw_sha256") != text_hash(run.raw_output):
        raise KnowledgeError("QUERY_RESPONSE_CHANGED", "回答原始响应哈希已变化，停止复用")


def _recoverable(session: Session, query: QueryRun, plan: Plan, runs: list[QueryModelRun]) -> bool:
    for sequence, run in enumerate(runs, 1):
        _validate_run(session, query, run, plan, sequence)
        if run.raw_output is not None and run.parameters.get("raw_complete"):
            try:
                bind_answer(
                    run.raw_output,
                    query.snapshot["context"],
                    query_id=query.id,
                    answer_id="recovery-validation",
                    revision=1,
                )
            except KnowledgeError:
                continue
            return True
    return False


def validate_answer(
    session: Session,
    project_id: str,
    query_id: str,
    answer_version_id: str | None = None,
) -> QueryAnswerVersion:
    """GET/save boundary: revalidate current permissions and the complete raw lineage."""
    query = _checked_query(session, project_id, query_id)
    _purpose(query)
    answer = (
        session.get(QueryAnswerVersion, answer_version_id)
        if answer_version_id
        else (_latest_answer(session, query_id))
    )
    if not answer or answer.query_run_id != query_id or answer.project_id != project_id:
        raise KnowledgeError("QUERY_ANSWER_NOT_FOUND", "当前项目不存在该回答版本")
    plan = _plan(query)
    if _state(session, query, plan) is None:
        raise KnowledgeError("QUERY_RESPONSE_CHANGED", "回答缺少冻结执行账本")
    raw = None
    model = None
    deterministic = _no_call_reason(query)
    if answer.model_run_id:
        runs = _runs(session, query_id)
        model = next((run for run in runs if run.id == answer.model_run_id), None)
        if not model:
            raise KnowledgeError("QUERY_RESPONSE_CHANGED", "回答原始模型记录不存在")
        _validate_run(session, query, model, plan, runs.index(model) + 1)
        if not model.parameters.get("raw_complete") or model.raw_output is None:
            raise KnowledgeError("QUERY_RESPONSE_CHANGED", "回答没有完整的原始模型响应")
        raw = model.raw_output
    elif deterministic is None:
        raise KnowledgeError("QUERY_RESPONSE_CHANGED", "回答缺少模型响应或确定性不足依据")
    expected = bind_answer(
        raw,
        query.snapshot["context"],
        query_id=query_id,
        answer_id=answer.id,
        revision=answer.revision,
        deterministic_limitations=deterministic,
    )
    if model and model.parameters.get("display_normalization") != display_normalization(
        raw, query.snapshot["context"], expected
    ):
        raise KnowledgeError("QUERY_RESPONSE_CHANGED", "回答的程序展示替换审计与原始响应不一致")
    if (
        answer.state != "validated"
        or answer.input_hash != query.input_hash
        or answer.data != expected.model_dump(mode="json")
    ):
        raise KnowledgeError("QUERY_RESPONSE_CHANGED", "回答版本与已验证原始响应不一致")
    return answer


def enqueue(
    session: Session, query_id: str, project_id: str, key: str, *, continue_requested: bool = False
) -> Job:
    # Acquire the SQLite writer before selecting shared state. This no-op update
    # serializes duplicate local submissions without advancing any version.
    session.execute(
        update(QueryRun)
        .where(QueryRun.id == query_id, QueryRun.project_id == project_id)
        .values(updated_at=QueryRun.updated_at)
    )
    query = _checked_query(session, project_id, query_id)
    _purpose(query)
    model = query.snapshot.get("model")
    if _no_call_reason(query) is None and (not model or model.get("provider") == "mock"):
        raise KnowledgeError(
            "QUERY_MODEL_NOT_CONFIGURED", "请配置真实全局 Reasoning 模型后准备新查询"
        )
    plan = _plan(query)
    state = _state(session, query, plan)
    request_hash = digest({"query_id": query_id, "continue_requested": continue_requested})
    op_key = f"query-answer-enqueue:{project_id}:{key}"
    previous = session.get(QueryOperation, op_key)
    if previous:
        if previous.request_hash != request_hash:
            raise KnowledgeError("IDEMPOTENCY_CONFLICT", "同一请求标识不能用于不同回答操作")
        job = session.get(Job, previous.response["job_id"])
        if not job or job.project_id != project_id:
            raise KnowledgeError("QUERY_JOB_NOT_FOUND", "回答任务不存在")
        return job

    def remembered_result(job: Job) -> Job:
        session.add(
            QueryOperation(key=op_key, request_hash=request_hash, response={"job_id": job.id})
        )
        return job

    latest = session.get(Job, state.response.get("latest_job_id")) if state else None
    if _latest_answer(session, query_id):
        validate_answer(session, project_id, query_id)
        if latest:
            return remembered_result(latest)
    if latest and (latest.status in {"queued", "running", "succeeded"} or not continue_requested):
        return remembered_result(latest)
    runs = _runs(session, query_id)
    recoverable = _recoverable(session, query, plan, runs)
    recovery_only = bool(
        latest
        and (latest.result or {}).get("error_code") == "QUERY_NUMERIC_LAYOUT_UNRESOLVED"
        and recoverable
    )
    if runs and state is None:
        raise KnowledgeError("QUERY_RESPONSE_CHANGED", "模型请求缺少冻结执行账本")
    if len(runs) >= MAX_REQUESTS and not recoverable:
        raise KnowledgeError("QUERY_REQUEST_LIMIT", "本次查询已达两次请求上限；不会重发已发送槽位")
    if latest and (latest.result or {}).get("error_code") in _NONRETRYABLE and not recovery_only:
        raise KnowledgeError("QUERY_CONTEXT_CHANGED", "来源或配置冲突，请重新准备查询而非追加调用")
    job = Job(
        id=str(uuid4()),
        kind="query_answer",
        project_id=project_id,
        status="queued",
        attempt=0,
        payload={
            "query_id": query_id,
            "answer_policy": POLICY,
            "plan_signature": plan.signature,
            "allow_network": True,
            "continue_requested": continue_requested,
            "request_budget": len(runs)
            if recovery_only
            else min(len(runs) + 1, MAX_REQUESTS)
            if continue_requested
            else 1,
            **(
                {
                    "recovery_only": True,
                    "recovery_runs": [
                        {"id": run.id, "raw_sha256": run.parameters.get("raw_sha256")}
                        for run in runs
                    ],
                }
                if recovery_only
                else {}
            ),
        },
        created_at=now(),
        updated_at=now(),
    )
    session.add(job)
    session.flush()
    if state is None:
        state = QueryOperation(
            key="query-answer-state:" + query_id,
            request_hash=plan.signature,
            response={"policy": POLICY, "latest_job_id": job.id},
        )
        session.add(state)
    else:
        state.response = {**state.response, "latest_job_id": job.id}
    session.add(QueryOperation(key=op_key, request_hash=request_hash, response={"job_id": job.id}))
    KnowledgeStore(session).audit_event(
        project_id,
        "query.answer_queued",
        {
            "query_id": query_id,
            "job_id": job.id,
            "continue_requested": continue_requested,
        },
    )
    return job


def _model_view(run: QueryModelRun) -> QueryModelExecutionView:
    params = run.parameters
    return QueryModelExecutionView(
        id=run.id,
        sequence=params.get("dispatch", {}).get("sequence", 0),
        status=run.status,
        usage=params.get("usage", {}),
        duration_seconds=params.get("duration_seconds"),
        finish_reason=params.get("request_metadata", {}).get("finish_reason"),
        error_code=params.get("error_code"),
        error=run.error,
    )


def get_answer(session: Session, project_id: str, query_id: str) -> QueryAnswerView:
    query = _checked_query(session, project_id, query_id)
    plan = _plan(query)
    state = _state(session, query, plan)
    latest = session.get(Job, state.response.get("latest_job_id")) if state else None
    runs = _runs(session, query_id)
    for index, run in enumerate(runs, 1):
        _validate_run(session, query, run, plan, index)
    if runs and state is None:
        raise KnowledgeError("QUERY_RESPONSE_CHANGED", "模型请求缺少冻结执行账本")
    answer = _latest_answer(session, query_id)
    parsed = None
    if answer:
        answer = validate_answer(session, project_id, query_id, answer.id)
        parsed = QueryAnswer.model_validate(answer.data)
    code = (latest.result or {}).get("error_code") if latest else None
    status = (
        "insufficient"
        if parsed and parsed.knowledge_status == "insufficient"
        else "succeeded"
        if parsed
        else latest.status
        if latest
        else "not_started"
    )
    return QueryAnswerView(
        query_id=query_id,
        status=cast(Any, status),
        job_id=latest.id if latest else None,
        answer=parsed,
        model_runs=[_model_view(run) for run in runs],
        can_continue=bool(
            latest
            and latest.status in {"failed", "interrupted", "cancelled"}
            and (
                code not in _NONRETRYABLE
                or (
                    code == "QUERY_NUMERIC_LAYOUT_UNRESOLVED"
                    and _recoverable(session, query, plan, runs)
                )
            )
            and not answer
            and (len(runs) < MAX_REQUESTS or _recoverable(session, query, plan, runs))
        ),
        error_code=code,
        error=latest.error if latest else None,
        request_count=len(runs),
    )


def _active(session: Session, job_id: str, stop_event: StopSignal | None = None) -> Job:
    job = session.get(Job, job_id)
    if not job or job.status != "running" or (stop_event and stop_event.is_set()):
        raise KnowledgeError("QUERY_CANCELLED", "回答任务已取消；未发布未验证内容")
    return job


def _publish(session: Session, job: Job, query: QueryRun, raw_run: QueryModelRun | None) -> None:
    # A fresh context check is mandatory even when the model returned valid JSON.
    _checked_query(session, query.project_id, query.id)
    existing = _latest_answer(session, query.id)
    if existing:
        answer = validate_answer(session, query.project_id, query.id, existing.id)
    else:
        answer_id = str(uuid4())
        answer_data = bind_answer(
            raw_run.raw_output if raw_run else None,
            query.snapshot["context"],
            query_id=query.id,
            answer_id=answer_id,
            revision=1,
            deterministic_limitations=_no_call_reason(query),
        )
        answer = QueryAnswerVersion(
            id=answer_id,
            project_id=query.project_id,
            query_run_id=query.id,
            model_run_id=raw_run.id if raw_run else None,
            revision=1,
            state="validated",
            data=answer_data.model_dump(mode="json"),
            input_hash=query.input_hash,
            created_at=now(),
        )
        session.add(answer)
        if raw_run:
            normalization = display_normalization(
                raw_run.raw_output, query.snapshot["context"], answer_data
            )
            if normalization:
                raw_run.parameters = {
                    **raw_run.parameters,
                    "display_normalization": normalization,
                    **(
                        {
                            "recovered_validation": {
                                "status": raw_run.status,
                                "error": raw_run.error,
                                "error_code": raw_run.parameters.get("error_code"),
                                "finished_at": raw_run.finished_at,
                            }
                        }
                        if raw_run.status == "validation_failed"
                        else {}
                    ),
                    "error_code": None,
                }
            raw_run.status, raw_run.error = "succeeded", None
        KnowledgeStore(session).audit_event(
            query.project_id,
            "query.answered",
            {
                "query_id": query.id,
                "answer_version_id": answer.id,
            },
        )
    job.status, job.stage, job.error, job.updated_at = "succeeded", None, None, now()
    job.result = {
        "query_id": query.id,
        "answer_version_id": answer.id,
        "knowledge_status": answer.data["knowledge_status"],
        "error_code": None,
    }


def _safe_metadata(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return {k: _safe_metadata(v, key) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe_metadata(v, key) for v in value]
    return value.replace(key, "[redacted]") if key and isinstance(value, str) else value


def _record_io(
    engine: Engine,
    run_id: str,
    provider: Provider,
    started: float,
    *,
    raw: str | None = None,
    complete: bool = False,
    error: KnowledgeError | None = None,
    status: str = "received",
) -> None:
    key = getattr(provider, "key", "")
    if raw is not None and key and key in raw:
        raw, complete = None, False
        error = KnowledgeError("QUERY_CREDENTIAL_IN_OUTPUT", "模型输出包含凭据，已拒绝保存")
    with Session(engine) as session, session.begin():
        run = session.get(QueryModelRun, run_id)
        assert run
        run.raw_output, run.finished_at = raw, now()
        run.status = status if error is None else "failed"
        run.error = str(error) if error else None
        run.parameters = {
            **run.parameters,
            "duration_seconds": round(time.monotonic() - started, 3),
            "usage": {
                k: v for k, v in getattr(provider, "usage", {}).items() if type(v) is int and v >= 0
            },
            "request_metadata": _safe_metadata(
                copy.deepcopy(getattr(provider, "request_metadata", {})), key
            ),
            "raw_sha256": text_hash(raw) if raw is not None else None,
            "raw_complete": complete,
            "error_code": error.code if error else None,
            "cost_known": False,
        }
    if error and error.code == "QUERY_CREDENTIAL_IN_OUTPUT":
        raise error


def _failure(
    engine: Engine,
    job_id: str,
    error: KnowledgeError,
    *,
    run_id: str | None = None,
    status: str = "failed",
) -> None:
    with Session(engine) as session, session.begin():
        job = session.get(Job, job_id)
        if job and job.status == "running":
            job.status, job.error, job.updated_at = status, str(error), now()
            job.result = {**(job.result or {}), "error_code": error.code}
        if run_id:
            run = session.get(QueryModelRun, run_id)
            if run:
                if error.code in _CONTEXT_ERRORS:
                    # The old raw remains historical received/succeeded data.
                    # A changed permission/source is not a bad model response.
                    run.parameters = {
                        **run.parameters,
                        "reuse_diagnostic": {
                            "code": error.code,
                            "checked_at": now(),
                        },
                    }
                elif error.code == "QUERY_CANCELLED":
                    run.status, run.error = "cancelled", str(error)
                    run.parameters = {**run.parameters, "error_code": error.code}
                else:
                    run.status, run.error, run.finished_at = "validation_failed", str(error), now()
                    run.parameters = {**run.parameters, "error_code": error.code}


async def _call(
    engine: Engine, job_id: str, provider: Provider, plan: Plan, stop_event: StopSignal | None
) -> str:
    task = asyncio.create_task(provider.complete(plan.prompt, plan.wire, plan.schema))
    timeout = min(float(getattr(provider, "total_timeout", 180)), 300)
    started = time.monotonic()
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=0.1)
            with read_session(engine) as session:
                _active(session, job_id, stop_event)
            if time.monotonic() - started > timeout:
                raise TimeoutError
        return await task
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


def _provider_error(error: Exception) -> KnowledgeError:
    category = (
        error.category
        if isinstance(error, ProviderError)
        else ("timeout" if isinstance(error, TimeoutError) else "failure")
    )
    mapping = {
        "timeout": ("QUERY_MODEL_TIMEOUT", "模型请求超时；未自动重发，供应商费用未知"),
        "client": ("QUERY_MODEL_CLIENT", "模型拒绝请求，请检查配置或额度并准备新查询"),
        "structured_output_refused": ("QUERY_MODEL_REFUSED", "模型拒绝本次回答，未自动重发"),
        "output_limit": ("QUERY_MODEL_OUTPUT_LIMIT", "模型响应被截断，未发布或自动重发"),
        "context_limit": (
            "QUERY_MODEL_CONTEXT_LIMIT",
            "服务商实际上下文容量不足，请缩小来源范围后准备新查询",
        ),
    }
    code, message = mapping.get(
        category, ("QUERY_MODEL_FAILURE", "模型调用失败；原始记录保留，未自动重发，供应商费用未知")
    )
    return KnowledgeError(code, message)


async def execute(
    engine: Engine,
    job_id: str,
    stop_event: StopSignal | None = None,
    *,
    testing_provider: Provider | None = None,
) -> None:
    """Worker entry. Explicit testing injection never appears in production API."""
    active_run_id = None
    provider = testing_provider
    started = time.monotonic()
    try:
        with Session(engine) as session, session.begin():
            job = _active(session, job_id, stop_event)
            payload = dict(job.payload or {})
            if job.kind != "query_answer" or not job.project_id or not payload.get("allow_network"):
                raise KnowledgeError("QUERY_PURPOSE_REQUIRED", "任务缺少明确的模型发送授权")
            query = _checked_query(session, job.project_id, payload["query_id"])
            _purpose(query)
            plan = _plan(query)
            if payload.get("plan_signature") != plan.signature:
                raise KnowledgeError(
                    "QUERY_PROTOCOL_CHANGED", "任务协议或上下文已变化，请准备新查询"
                )
            _state(session, query, plan)
            if _latest_answer(session, query.id) or _no_call_reason(query):
                _publish(session, job, query, None)
                return
            runs = _runs(session, query.id)
            if payload.get("recovery_only") and payload.get("recovery_runs") != [
                {"id": run.id, "raw_sha256": run.parameters.get("raw_sha256")} for run in runs
            ]:
                raise KnowledgeError(
                    "QUERY_RESPONSE_CHANGED", "待恢复的原始响应已变化，停止零调用恢复"
                )
            for sequence, recorded in enumerate(runs, 1):
                _validate_run(session, query, recorded, plan, sequence)
                if recorded.raw_output is not None and recorded.parameters.get("raw_complete"):
                    try:
                        bind_answer(
                            recorded.raw_output,
                            query.snapshot["context"],
                            query_id=query.id,
                            answer_id="validation-only",
                            revision=1,
                        )
                    except KnowledgeError as error:
                        if error.code in _CONTEXT_ERRORS:
                            raise
                        recorded.status, recorded.error = "validation_failed", str(error)
                        recorded.parameters = {**recorded.parameters, "error_code": error.code}
                    else:
                        _publish(session, job, query, recorded)
                        return
            if payload.get("recovery_only"):
                raise KnowledgeError(
                    "QUERY_RESPONSE_CHANGED", "原始响应未通过完整重验；本任务仅恢复，不追加模型请求"
                )
            if len(runs) >= MAX_REQUESTS or len(runs) >= payload.get("request_budget", 1):
                raise KnowledgeError(
                    "QUERY_REQUEST_LIMIT", "已发送槽位不会重发；请明确继续或准备新的查询"
                )
            snapshot = copy.deepcopy(query.snapshot.get("model"))
            if not snapshot or snapshot.get("provider") == "mock":
                raise KnowledgeError(
                    "QUERY_MODEL_NOT_CONFIGURED", "新回答需要真实全局 Reasoning 模型"
                )
            query_id, project_id = query.id, query.project_id
        if provider is None:
            try:
                provider = from_snapshot(snapshot, Path(str(engine.url.database)).parent, True)
            except Exception:
                raise KnowledgeError(
                    "QUERY_MODEL_CONFIGURATION", "冻结模型配置不可用，请检查设置并准备新查询"
                ) from None
        # Recheck after provider construction and immediately before reserving a
        # dispatch slot; the committed row precedes every possible network send.
        with Session(engine) as session, session.begin():
            job = _active(session, job_id, stop_event)
            query = _checked_query(session, project_id, query_id)
            runs = _runs(session, query_id)
            if len(runs) >= min(payload.get("request_budget", 1), MAX_REQUESTS):
                raise KnowledgeError("QUERY_REQUEST_LIMIT", "回答请求槽位已使用，不重复发送")
            active_run_id = str(uuid4())
            recorded = QueryModelRun(
                id=active_run_id,
                query_run_id=query_id,
                project_id=project_id,
                provider=snapshot["provider"],
                model=snapshot["model"],
                prompt_name=plan.prompt_name,
                prompt_hash=text_hash(plan.prompt),
                schema_version=POLICY,
                input_hash=digest(plan.wire),
                manifest=plan.manifest,
                parameters={
                    "model_snapshot": snapshot,
                    "dispatch": {
                        "sequence": len(runs) + 1,
                        "job_id": job_id,
                        "reserved_at": now(),
                        "policy": "persist-before-io-no-resend-1",
                    },
                    "raw_complete": False,
                    "usage": {},
                    "cost_known": False,
                },
                status="running",
                created_at=now(),
            )
            session.add(recorded)
            job.stage, job.updated_at = "reasoning", now()
            job.result = {
                "query_id": query_id,
                "request_count": len(runs) + 1,
                "request_limit": MAX_REQUESTS,
                "error_code": None,
            }
        started = time.monotonic()
        try:
            raw = await _call(engine, job_id, provider, plan, stop_event)
        except asyncio.CancelledError:
            _record_io(
                engine,
                active_run_id,
                provider,
                started,
                raw=getattr(provider, "partial_output", None),
                status="interrupted",
            )
            raise
        except KnowledgeError:
            _record_io(
                engine,
                active_run_id,
                provider,
                started,
                raw=getattr(provider, "partial_output", None),
                status="cancelled",
            )
            raise
        except Exception as error:
            safe = _provider_error(error)
            _record_io(
                engine,
                active_run_id,
                provider,
                started,
                raw=getattr(provider, "partial_output", None),
                error=safe,
            )
            # Transport failures are immutable consumed dispatches, not Schema failures.
            _failure(engine, job_id, safe)
            return
        # Durable received raw allows a crash here to recover without a new call.
        _record_io(engine, active_run_id, provider, started, raw=raw, complete=True)
        with Session(engine) as session, session.begin():
            job = _active(session, job_id, stop_event)
            query = _checked_query(session, project_id, query_id)
            received_run = session.get(QueryModelRun, active_run_id)
            assert received_run
            _validate_run(session, query, received_run, plan, len(_runs(session, query_id)))
            _publish(session, job, query, received_run)
    except asyncio.CancelledError:
        _failure(
            engine,
            job_id,
            KnowledgeError("QUERY_INTERRUPTED", "应用退出或执行中断；已发送请求不自动重发"),
            status="interrupted",
        )
        raise
    except KnowledgeError as error:
        _failure(
            engine,
            job_id,
            error,
            run_id=active_run_id,
            status="cancelled" if error.code == "QUERY_CANCELLED" else "failed",
        )
    except Exception:
        _failure(
            engine,
            job_id,
            KnowledgeError("QUERY_EXECUTION_FAILED", "回答执行失败，记录保留；未发布或自动重发"),
        )
