"""Explicit ranking-protocol successors with revalidated, zero-call P12 adoption."""

import json
from copy import deepcopy
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.extraction import PROMPT_DIR
from researchgraph.knowledge_models import ModelRun
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest, text_hash
from researchgraph.models import Job, now
from researchgraph.reading_finish_wire import (
    INTEGRATION_PROMPT,
    POLICY,
    bind_integration,
    schema_for,
)
from researchgraph.reading_stage_validation import (
    StageValidation,
    StageValidationError,
    validate_stage,
)
from researchgraph.reading_support import support_context
from researchgraph.reading_transport import loads

UPGRADE_POLICY = "reading-ranking-protocol-successor-1"
_OLD_PROMPTS = {"P13_reading_ranking_v1", "P13_reading_ranking_v2"}
_MAX_ADOPTION_DEPTH = 16


def available(job: Any) -> bool:
    payload = getattr(job, "payload", None) or {}
    plan = payload.get("reading_finish_plan") or {}
    failure = (getattr(job, "result", None) or {}).get("stage_failure") or {}
    failed_stage = failure.get("stage", getattr(job, "stage", None))
    return bool(
        getattr(job, "kind", None) == "knowledge_extract"
        and getattr(job, "status", None) in {"failed", "interrupted", "cancelled"}
        and payload.get("pipeline") == "paper-reading-v1"
        and plan.get("flow_policy") == POLICY
        and plan.get("ranking_prompt", "P13_reading_ranking_v1") in _OLD_PROMPTS
        and failed_stage == "selecting"
    )


def _validate_source(session: Session, source: Job) -> dict[str, Any]:
    payload = source.payload or {}
    plan = payload.get("reading_finish_plan") or {}
    version_id = payload.get("document_version_id")
    if not isinstance(version_id, str):
        raise KnowledgeError("UPGRADE_CONTEXT_UNAVAILABLE", "原任务缺少文献版本，无法安全续接")
    reading = KnowledgeStore(session).reading()
    _, paper = reading.source(version_id)
    if paper.project_id != source.project_id or reading.snapshot(version_id) != plan.get(
        "snapshot"
    ):
        raise KnowledgeError(
            "READING_INPUT_CHANGED", "原任务候选或来源已变化，请基于当前候选新建图谱"
        )
    nodes = {node.id: node for node in reading.nodes(version_id) if reading.source_valid(node)}
    current_support = support_context(reading, version_id, nodes)
    frozen_support = plan.get("support_context")
    if frozen_support is not None and current_support != frozen_support:
        raise KnowledgeError(
            "SUPPORT_CONTEXT_CHANGED", "原任务支撑关联已变化，请基于当前候选新建图谱"
        )
    frozen = plan.get("integration_input")
    if not isinstance(frozen, dict) or set(frozen) != {"wire", "canonical", "context"}:
        raise KnowledgeError(
            "UPGRADE_CONTEXT_UNAVAILABLE", "原任务缺少完整整合检查点，无法安全续接"
        )
    if frozen_support is None:
        # Old plans have no relation manifest. Their persisted unit checkpoint
        # must still pass the current complete closure/path checks without writes.
        key = "reading:semantic-integration:" + digest(
            [plan["snapshot"], plan["signature"], frozen["wire"]]
        )
        if (
            reading.checkpoint(
                key + ":units", digest([version_id, plan["snapshot"], "support-closure-1"])
            )
            is None
        ):
            raise KnowledgeError("UPGRADE_CONTEXT_UNAVAILABLE", "原任务缺少可核验的完整支撑检查点")
        reading.form_units(version_id, plan["snapshot"], key + ":units")
    return frozen


def _integration_run(session: Session, source: Job, frozen: dict[str, Any]) -> ModelRun:
    """Resolve only explicit, fully revalidated zero-call adoption provenance."""
    source_payload = source.payload or {}
    source_plan = source_payload["reading_finish_plan"]
    prompt_hash = text_hash((PROMPT_DIR / (INTEGRATION_PROMPT + ".md")).read_text(encoding="utf-8"))
    manifest = {
        "pipeline": "paper-reading-v1",
        "schema_hash": digest(schema_for("P12")),
        "semantic_context": frozen["context"],
    }
    visited: set[str] = set()
    cursor, required_run_id = source, None
    for _ in range(_MAX_ADOPTION_DEPTH):
        if cursor.id in visited:
            break
        visited.add(cursor.id)
        cursor_payload = cursor.payload or {}
        plan = cursor_payload.get("reading_finish_plan") or {}
        if (
            cursor.project_id != source.project_id
            or cursor_payload.get("pipeline") != "paper-reading-v1"
            or plan.get("flow_policy") != POLICY
            or cursor_payload.get("document_version_id") != source_payload["document_version_id"]
            or plan.get("snapshot") != source_plan["snapshot"]
            or plan.get("support_context") != source_plan.get("support_context")
            or _validate_source(session, cursor) != frozen
        ):
            break
        query = select(ModelRun).where(
            ModelRun.job_id == cursor.id,
            ModelRun.prompt_name == INTEGRATION_PROMPT,
            ModelRun.document_version_id == source_payload["document_version_id"],
            ModelRun.schema_version == "reading-1.0",
            ModelRun.prompt_hash == prompt_hash,
            ModelRun.input_hash == digest(frozen["wire"]),
            ModelRun.status == "succeeded",
        )
        if required_run_id is not None:
            query = query.where(ModelRun.id == required_run_id)
        for run in session.scalars(query.order_by(ModelRun.created_at.desc())):
            if (run.parameters or {}).get("input_manifest") == manifest and run.raw_output:
                return run

        # New successors keep their immediate source in result; historical
        # independent continuations recorded this explicit P12 adoption in payload.
        adoption = (cursor.result or {}).get("integration_adopted")
        if adoption is None:
            adoption = cursor_payload.get("adopted_stage")
            if not isinstance(adoption, dict) or adoption.get("stage") != "P12":
                break
        if (
            not isinstance(adoption, dict)
            or not isinstance(adoption.get("source_job_id"), str)
            or not isinstance(adoption.get("source_model_run_id"), str)
            or adoption.get("input_hash") != digest(frozen["wire"])
            or type(adoption.get("new_requests")) is not int
            or adoption.get("new_requests") != 0
            or adoption.get("terminal_revalidated") is not True
            or (required_run_id is not None and adoption["source_model_run_id"] != required_run_id)
        ):
            break
        required_run_id = adoption["source_model_run_id"]
        ancestor = session.get(Job, adoption["source_job_id"])
        if ancestor is None:
            break
        cursor = ancestor
    raise KnowledgeError(
        "UPGRADE_CONTEXT_UNAVAILABLE", "找不到可核验的原整合模型记录，停止自动续接"
    )


def _validated_integration(
    session: Session, source: Job
) -> tuple[dict[str, Any], ModelRun, StageValidation]:
    frozen = _validate_source(session, source)
    plan = (source.payload or {})["reading_finish_plan"]
    run = _integration_run(session, source, frozen)
    assert run.raw_output is not None

    def bind(raw: str) -> str:
        return json.dumps(bind_integration(loads(raw), frozen["context"]), ensure_ascii=False)

    try:
        validated = validate_stage(
            session,
            "P12",
            run.raw_output,
            frozen["canonical"],
            snapshot=plan["snapshot"],
            wire_validator=bind,
        )
    except StageValidationError:
        # An explicit successor never mutates historical status/error/raw.
        raise KnowledgeError(
            "UPGRADE_CONTEXT_UNAVAILABLE", "原整合响应未通过当前完整校验，停止自动续接"
        ) from None
    return frozen, run, validated


def upgrade_job(session: Session, original: Job) -> Job:
    if not available(original):
        raise KnowledgeError("UPGRADE_NOT_AVAILABLE", "该任务不需要升级排序协议")
    jid = str(uuid5(NAMESPACE_URL, f"{UPGRADE_POLICY}:{original.id}"))
    existing = session.get(Job, jid)
    if existing is not None:
        return existing
    payload = original.payload or {}
    version_id = payload["document_version_id"]
    for active in session.scalars(
        select(Job).where(
            Job.project_id == original.project_id,
            Job.kind == "knowledge_extract",
            Job.status.in_(["queued", "running"]),
        )
    ):
        if (active.payload or {}).get("document_version_id") == version_id:
            raise KnowledgeError("BUILD_IN_PROGRESS", "该论文仍有任务运行，请等待结束或取消")
    _, run, _ = _validated_integration(session, original)
    source_plan = payload["reading_finish_plan"]
    successor_payload = deepcopy(payload)
    for field in ("reading_finish_plan", "unified_plan", "reading_windows", "resume_adapter"):
        successor_payload.pop(field, None)
    successor_payload.update(
        reading_only=True,
        reading_flow_policy=POLICY,
        resumed_from=original.id,
        semantic_finish_upgrade={
            "policy": UPGRADE_POLICY,
            "source_job_id": original.id,
            "snapshot": source_plan["snapshot"],
            "source_signature": source_plan["signature"],
            "source_model_run_id": run.id,
        },
    )
    job = Job(
        id=jid,
        kind=original.kind,
        project_id=original.project_id,
        payload=successor_payload,
        result={
            "resumed_from": original.id,
            "coverage_gaps": deepcopy(source_plan.get("extraction_coverage_gaps", [])),
            "model_calls": 0,
            "usage": {},
            "ranking_protocol_upgraded": True,
        },
        status="queued",
        stage="integrating",
        attempt=0,
        created_at=now(),
        updated_at=now(),
    )
    session.add(job)
    session.flush()
    return job


def _source_job(session: Session, job: Job) -> Job | None:
    marker = (job.payload or {}).get("semantic_finish_upgrade")
    if marker is None:
        return None
    source = session.get(Job, marker.get("source_job_id"))
    plan = (source.payload or {}).get("reading_finish_plan", {}) if source else {}
    if (
        source is None
        or marker.get("policy") != UPGRADE_POLICY
        or source.project_id != job.project_id
        or (source.payload or {}).get("document_version_id")
        != (job.payload or {}).get("document_version_id")
        or marker.get("snapshot") != plan.get("snapshot")
        or marker.get("source_signature") != plan.get("signature")
    ):
        raise KnowledgeError("UPGRADE_CONTEXT_UNAVAILABLE", "排序续接来源不一致，停止自动请求")
    return source


def integration_input(session: Session, job: Job) -> dict[str, Any] | None:
    source = _source_job(session, job)
    if source is None:
        return None
    frozen, _, _ = _validated_integration(session, source)
    return deepcopy(frozen)


def adopt_integration(
    session: Session,
    job: Job,
    wire: dict[str, Any],
    canonical: dict[str, Any],
    context: dict[str, Any],
    snapshot: str,
    integration_key: str,
) -> dict[str, Any] | None:
    source = _source_job(session, job)
    if source is None:
        return None
    frozen, run, validated = _validated_integration(session, source)
    marker = (job.payload or {})["semantic_finish_upgrade"]
    if (
        marker.get("source_model_run_id") != run.id
        or marker["snapshot"] != snapshot
        or frozen != {"wire": wire, "canonical": canonical, "context": context}
    ):
        raise KnowledgeError(
            "UPGRADE_CONTEXT_UNAVAILABLE", "排序续接的冻结整合输入不一致，停止自动请求"
        )
    reading = KnowledgeStore(session).reading()
    historical_parameters = deepcopy(run.parameters)
    store_diagnostics: dict[str, Any] = {}
    try:
        integrated: dict[str, Any] = reading.integrate(
            proposal=validated.value,
            version_id=(job.payload or {})["document_version_id"],
            snapshot=snapshot,
            run_id=run.id,
            key=integration_key + ":apply",
        )
    finally:
        # The Store still validates and applies normally. Diagnostics produced by
        # this adoption belong to the successor, never to the historical call.
        store_diagnostics = {
            key: deepcopy(value)
            for key, value in (run.parameters or {}).items()
            if key not in historical_parameters or historical_parameters[key] != value
        }
        run.parameters = historical_parameters
    reading.save_checkpoint(
        integration_key,
        (job.payload or {})["document_version_id"],
        "integrating",
        digest(wire),
        integrated,
    )
    job.result = {
        **(job.result or {}),
        "integration_adopted": {
            "source_job_id": source.id,
            "source_model_run_id": run.id,
            "input_hash": digest(wire),
            "terminal_revalidated": True,
            "new_requests": 0,
            "stage_quarantined": deepcopy(validated.quarantined),
            "store_diagnostics": store_diagnostics,
        },
    }
    return integrated
