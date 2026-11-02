"""P03 and P04→P05 tasks sharing providers, cancellation and KnowledgeStore."""

from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from researchgraph.extraction import PROMPT_DIR, call_model, mark_run, stage
from researchgraph.knowledge_models import KnowledgeOperation
from researchgraph.knowledge_store import KnowledgeStore, digest, text_hash
from researchgraph.model_settings import from_snapshot
from researchgraph.models import Job, now
from researchgraph.providers import MockProvider
from researchgraph.reasoning_context import model_context, pair_context
from researchgraph.reasoning_contracts import (
    ComparabilityReport,
    EntityAlignmentBatch,
    RelationInference,
)
from researchgraph.reasoning_store import validate_comparison


def resolve_ids(value: Any, aliases: dict[str, str]) -> Any:
    if isinstance(value, list):
        return [resolve_ids(v, aliases) for v in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in {"evidence_ids", "evidence_span_ids"}:
                if not set(item) <= aliases.keys():
                    raise ValueError("模型引用了本批白名单之外的证据编号")
                result[key] = [aliases[i] for i in item]
            else:
                result[key] = resolve_ids(item, aliases)
        return result
    return value


async def run_reasoning(engine: Engine, job_id: str) -> None:
    with Session(engine) as session:
        job = session.get(Job, job_id)
        assert job and job.payload
        payload = job.payload
        mode = payload["mode"]
        snapshot = pair_context(session, payload["source_id"], payload["target_id"], mode)
    provider = (
        from_snapshot(
            payload["model_snapshot"],
            Path(str(engine.url.database)).parent,
            payload["allow_network"],
        )
        if payload.get("model_snapshot")
        else MockProvider()
    )
    names = (
        ["P04_compare_conditions", "P05_infer_relation"]
        if mode == "relation"
        else ["P03_normalize_entities"]
    )
    operation = "reasoning:" + digest(
        {
            "snapshot": snapshot,
            "mode": mode,
            "prompts": [
                text_hash((PROMPT_DIR / (p + ".md")).read_text(encoding="utf-8")) for p in names
            ],
            "provider": provider.name,
            "model": provider.model,
            "parameters": getattr(provider, "parameters", {}),
            "endpoint": getattr(provider, "base_url", "offline"),
            "contract": "p3-v1",
        }
    )
    with Session(engine) as session:
        previous = session.get(KnowledgeOperation, operation)
        cached = previous.response if previous else None
    data, aliases = model_context(snapshot)
    run_ids = []
    comparison = None
    active_run = None
    source = next(n for n in snapshot["source"]["nodes"] if n["id"] == payload["source_id"])
    if cached is None:
        try:
            if mode == "relation":
                stage(engine, job_id, "comparing")
                data["required_dimensions"] = sorted(
                    set(snapshot["source"]["dimensions"]) | set(snapshot["target"]["dimensions"])
                )
                active_run, raw = await call_model(
                    engine,
                    job_id,
                    source["document_version_id"],
                    provider,
                    names[0],
                    data,
                    ComparabilityReport.model_json_schema(),
                    {"evidence_aliases": aliases, "snapshot_hash": digest(snapshot)},
                )
                original_report = ComparabilityReport.model_validate_json(raw).model_dump(
                    mode="json"
                )
                report = ComparabilityReport.model_validate(resolve_ids(original_report, aliases))
                validate_comparison(report, snapshot)
                comparison = report.model_dump(mode="json")
                run_ids.append(active_run)
                mark_run(engine, active_run, "succeeded")
                active_run = None
                stage(engine, job_id, "reasoning")
                data["comparability_report"] = original_report
                active_run, raw = await call_model(
                    engine,
                    job_id,
                    source["document_version_id"],
                    provider,
                    names[1],
                    data,
                    RelationInference.model_json_schema(),
                    {"evidence_aliases": aliases, "snapshot_hash": digest(snapshot)},
                )
                output = RelationInference.model_validate_json(raw).model_dump(mode="json")
            else:
                stage(engine, job_id, "resolving")
                data["new_entities"] = [{"source_local_ref": "source", **data["claim_a"]}]
                data["indexed_candidates"] = [data["claim_b"]]
                active_run, raw = await call_model(
                    engine,
                    job_id,
                    source["document_version_id"],
                    provider,
                    names[0],
                    data,
                    EntityAlignmentBatch.model_json_schema(),
                    {"evidence_aliases": aliases, "snapshot_hash": digest(snapshot)},
                )
                output = EntityAlignmentBatch.model_validate_json(raw).model_dump(mode="json")
            run_ids.append(active_run)
            stage(engine, job_id, "saving")
            with Session(engine) as session, session.begin():
                job = session.get(Job, job_id)
                if job is None or job.status != "running":
                    raise ValueError("任务已取消，不再写入候选")
                cached = KnowledgeStore(session).apply_reasoning(
                    mode=mode,
                    snapshot=snapshot,
                    output=resolve_ids(output, aliases),
                    comparison=comparison,
                    run_ids=run_ids,
                    key=operation,
                )
            mark_run(engine, active_run, "succeeded")
        except BaseException:
            if active_run:
                mark_run(
                    engine,
                    active_run,
                    "validation_failed",
                    "推理 Schema、条件或证据校验失败；未生成候选",
                )
            raise
    with Session(engine) as session, session.begin():
        job = session.get(Job, job_id)
        if job and job.status == "running":
            job.status, job.updated_at = "succeeded", now()
            job.result = {
                "attempt_id": cached["attempt_id"],
                "proposal_id": cached["proposal_id"] or "",
                "reused": not bool(run_ids),
            }
