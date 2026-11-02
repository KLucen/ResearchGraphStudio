"""Explicit adapter adoption in a successor job, retaining the original batch ledger."""

from copy import deepcopy
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.knowledge_store import KnowledgeError
from researchgraph.model_adapters import TENCENT_DEEPSEEK, tencent_deepseek
from researchgraph.models import Job, now


def adapter_available(job: Any) -> bool:
    payload = getattr(job, "payload", None) or {}
    snapshot = payload.get("model_snapshot") or {}
    parameters = snapshot.get("parameters") or {}
    return bool(
        getattr(job, "kind", None) == "knowledge_extract"
        and getattr(job, "status", None) in {"failed", "interrupted", "cancelled"}
        and payload.get("pipeline") == "paper-reading-v1"
        and payload.get("unified_plan", {}).get("signature")
        and not payload.get("reading_only")
        and not payload.get("reading_finish_plan")
        and not payload.get("resume_adapter")
        and not parameters.get("adapter_policy")
        and parameters.get("reasoning_effort") is None
        and payload.get("allow_network")
        and tencent_deepseek(snapshot.get("base_url", ""), snapshot.get("model", ""))
    )


def resume_with_adapter(session: Session, original: Job) -> Job:
    if not adapter_available(original):
        raise KnowledgeError("ADAPTER_NOT_AVAILABLE", "该任务无需转换续接，请使用普通重试")
    jid = str(uuid5(NAMESPACE_URL, f"reading-resume:{original.id}:{TENCENT_DEEPSEEK}"))
    existing = session.get(Job, jid)
    if existing:
        return existing
    payload = deepcopy(original.payload or {})
    for other in session.scalars(
        select(Job).where(
            Job.project_id == original.project_id,
            Job.kind == "knowledge_extract",
            Job.status.in_(["queued", "running"]),
        )
    ):
        if (other.payload or {}).get("document_version_id") == payload["document_version_id"]:
            raise KnowledgeError("BUILD_IN_PROGRESS", "该论文仍有任务运行，请等待结束或取消")
    # The original signature/config/leaf identities stay unchanged. The explicit
    # execution policy is applied only after validating that frozen source plan.
    payload.update(resume_adapter=TENCENT_DEEPSEEK, resumed_from=original.id)
    result = deepcopy(original.result or {})
    result.update(
        resumed_from=original.id,
        resume_adapter=TENCENT_DEEPSEEK,
        model_activity=None,
        model_calls=0,
        usage={},
        cost=None,
        cost_status="provider_not_reported",
    )
    job = Job(
        id=jid,
        kind=original.kind,
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
