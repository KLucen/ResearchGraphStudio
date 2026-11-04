"""Explicit successor plans: current extraction, immutable previous jobs and results."""

import json
from copy import deepcopy
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph import reading_transport, reading_wire
from researchgraph.knowledge_models import KnowledgeOperation, ModelRun
from researchgraph.knowledge_store import KnowledgeError
from researchgraph.model_adapters import new_task_parameters
from researchgraph.models import Job, now
from researchgraph.reading_scope import current_nodes
from researchgraph.reading_validation import validate_batch


def upgrade_available(job: Any) -> bool:
    payload = getattr(job, "payload", None) or {}
    plan = payload.get("unified_plan") or {}
    return bool(
        getattr(job, "kind", None) == "knowledge_extract"
        and getattr(job, "status", None) in {"failed", "interrupted", "cancelled"}
        and payload.get("pipeline") in {"paper-reading-v1", "unified-v3", "baseline-v2"}
        and (payload.get("pipeline") == "paper-reading-v1" or payload.get("provider") != "mock")
        and not payload.get("reading_only")
        and not payload.get("reading_finish_plan")
        and plan.get("prompt_name")
        and plan["prompt_name"] not in {reading_wire.PROMPT, reading_transport.PROMPT}
    )


def upgrade_job(session: Session, original: Job) -> Job:
    if not upgrade_available(original):
        raise KnowledgeError("UPGRADE_NOT_AVAILABLE", "该任务已使用当前抽取协议")
    jid = str(uuid5(NAMESPACE_URL, f"reading-upgrade:{original.id}:{reading_wire.PROMPT}"))
    existing = session.get(Job, jid)
    if existing:
        return existing
    payload = deepcopy(original.payload or {})
    version_id = payload["document_version_id"]
    for active in session.scalars(
        select(Job).where(
            Job.project_id == original.project_id,
            Job.kind == "knowledge_extract",
            Job.status.in_(["queued", "running"]),
        )
    ):
        if (active.payload or {}).get("document_version_id") == version_id:
            raise KnowledgeError("BUILD_IN_PROGRESS", "该论文仍有任务运行")
    old_plan = payload.pop("unified_plan")
    leaves = []
    reusable_ids = {n.id for n in current_nodes(session, version_id)}
    if payload.get("pipeline") == "paper-reading-v1":
        runs = list(
            session.scalars(
                select(ModelRun)
                .where(
                    ModelRun.document_version_id == version_id,
                    ModelRun.schema_version == "reading-1.0",
                    ModelRun.status.in_(["received", "validation_failed", "succeeded"]),
                )
                .order_by(ModelRun.created_at.desc())
            )
        )
        for old in old_plan["leaves"]:
            leaf = {k: deepcopy(old[k]) for k in ("key", "depth", "ids", "chunk_id")}
            leaf["status"] = "pending"
            key = (
                old.get("committed_operation_key")
                or f"reading-extract:{old_plan['config']}:{old['key']}"
            )
            operation = session.get(KnowledgeOperation, key)
            if operation and set(operation.response["node_ids"]) <= reusable_ids:
                leaf.update(status="succeeded", committed_operation_key=key)
            else:
                for run in runs:
                    aliases = run.parameters.get("input_manifest", {}).get("evidence_aliases", {})
                    if list(aliases.values()) != leaf["ids"] or not run.raw_output:
                        continue
                    try:
                        data = json.loads(run.raw_output)
                        batch, _ = validate_batch(
                            run.raw_output, set(aliases), compact="wire_format" in data
                        )
                        if (batch.document_version_id, batch.chunk_id) != (
                            version_id,
                            leaf["chunk_id"],
                        ):
                            continue
                    except (ValueError, TypeError):
                        continue
                    leaf["response_run_id"] = run.id
                    break
            leaves.append(leaf)
    snapshot = payload.get("model_snapshot")
    if snapshot:
        snapshot["parameters"] = new_task_parameters(
            snapshot["base_url"], snapshot["model"], snapshot["parameters"], "extraction"
        )
    payload.pop("resume_adapter", None)
    payload.update(
        pipeline="paper-reading-v1",
        resumed_from=original.id,
        reading_upgrade={"prompt_name": reading_wire.PROMPT, "leaves": leaves},
    )
    result = {
        "completed_batches": str(sum(leaf["status"] == "succeeded" for leaf in leaves)),
        "total_batches": str(len(leaves)),
        "model_calls": 0,
        "usage": {},
        "resumed_from": original.id,
        "schema_upgrade": True,
    }
    job = Job(
        id=jid,
        kind="knowledge_extract",
        project_id=original.project_id,
        payload=payload,
        result=result,
        status="queued",
        attempt=0,
        created_at=now(),
        updated_at=now(),
    )
    session.add(job)
    session.flush()
    return job


def reuse_response(session: Session, run_id: str, job_id: str) -> tuple[str, str]:
    source = session.get(ModelRun, run_id)
    if not source or not source.raw_output:
        raise KnowledgeError("RESPONSE_UNAVAILABLE", "待续用响应不可用")
    rid = str(uuid5(NAMESPACE_URL, f"reading-response:{job_id}:{source.id}"))
    if not session.get(ModelRun, rid):
        session.add(
            ModelRun(
                id=rid,
                job_id=job_id,
                document_version_id=source.document_version_id,
                provider=source.provider,
                model=source.model,
                prompt_name=source.prompt_name,
                prompt_hash=source.prompt_hash,
                schema_version=source.schema_version,
                input_hash=source.input_hash,
                raw_output=source.raw_output,
                status="received",
                parameters={
                    **source.parameters,
                    "response_reused_from": source.id,
                    "attempts": [],
                    "usage": {},
                    "duration_seconds": 0,
                },
                created_at=now(),
                finished_at=now(),
            )
        )
    return rid, source.raw_output
