"""Bounded paper integration and selection, recoverable without PDF re-extraction."""

import json
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.extraction import PROMPT_DIR, call_model, mark_run, reusable_model_run, stage
from researchgraph.extraction_repair import validation_message
from researchgraph.graph_models import SourceAssertion
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeDependency, ModelRun, NodeEvidence
from researchgraph.knowledge_store import KnowledgeStore, digest, text_hash
from researchgraph.models import Job, now
from researchgraph.providers import Provider
from researchgraph.reading_contracts import CoreSelectionProposal, PaperIntegrationProposal
from researchgraph.reading_models import ReadingMember, ReadingUnit


async def model_stage(
    engine: Engine,
    job_id: str,
    provider: Provider,
    prompt: str,
    schema: type[BaseModel],
    data: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    manifest = {"pipeline": "paper-reading-v1", "schema_hash": digest(schema.model_json_schema())}
    cached = reusable_model_run(engine, job_id, provider, prompt, data, manifest)
    run_id, raw = cached or await call_model(
        engine,
        job_id,
        data["document_version_id"],
        provider,
        prompt,
        data,
        schema.model_json_schema(),
        manifest,
        adaptive_timeout=True,
    )
    try:
        value = schema.model_validate_json(raw).model_dump(mode="json")
    except ValueError as error:
        mark_run(engine, run_id, "validation_failed", validation_message(error))
        raise ValueError(validation_message(error)) from None
    return run_id, value


async def finish_reading(engine: Engine, job_id: str, provider: Provider) -> None:
    stage(engine, job_id, "integrating")
    with Session(engine, expire_on_commit=False) as session, session.begin():
        job = session.get(Job, job_id)
        assert job and job.payload
        version_id = job.payload["document_version_id"]
        reading = KnowledgeStore(session).reading()
        reading.adapt(version_id)
        snapshot = reading.snapshot(version_id)
        _, paper = reading.source(version_id)
        current = reading.current(paper.id)
        plan = job.payload.get("reading_finish_plan")
        signature = digest(
            {
                "prompts": {
                    p: text_hash((PROMPT_DIR / (p + ".md")).read_text(encoding="utf-8"))
                    for p in ["P12_reading_integration", "P13_reading_selection"]
                },
                "schemas": [
                    PaperIntegrationProposal.model_json_schema(),
                    CoreSelectionProposal.model_json_schema(),
                ],
                "provider": provider.name,
                "model": provider.model,
                "parameters": getattr(provider, "parameters", {}),
                "endpoint": getattr(provider, "base_url", "offline"),
            }
        )
        if plan and plan.get("signature") != signature:
            raise ValueError("整合模型、Prompt 或 Schema 已改变，请创建新构建")
        if plan and plan["snapshot"] != snapshot:
            raise ValueError("候选快照已变化；请启动新构建，已保存候选不会丢失")
        if not plan:
            plan = {
                "snapshot": snapshot,
                "signature": signature,
                "expected_revision": current.revision if current else 0,
            }
            job.payload = {**job.payload, "reading_finish_plan": plan}
        expected = plan["expected_revision"]
        density = job.payload.get("density", "standard")
        extraction_gaps = list((job.result or {}).get("coverage_gaps", []))
        nodes = {n.id: n for n in reading.nodes(version_id)}
        edges = [
            {
                "source_id": a.source_id,
                "target_id": a.target_id,
                "relation": a.relation,
                "evidence_ids": a.evidence_ids,
            }
            for a in session.scalars(
                select(SourceAssertion).where(
                    SourceAssertion.source_id.in_(nodes), SourceAssertion.target_id.in_(nodes)
                )
            )
        ]
        edges += [
            {"source_id": d.node_id, "target_id": d.dependee_id, "relation": d.role}
            for d in session.scalars(
                select(KnowledgeDependency).where(
                    KnowledgeDependency.node_id.in_(nodes),
                    KnowledgeDependency.dependee_id.in_(nodes),
                )
            )
        ]
        evidence = {
            e.id: e.quote
            for e in session.scalars(
                select(EvidenceSpan).where(EvidenceSpan.document_version_id == version_id)
            )
        }
        by_node = {
            nid: list(
                session.scalars(select(NodeEvidence.evidence_id).where(NodeEvidence.node_id == nid))
            )
            for nid in nodes
        }
    roots = [n.id for n in nodes.values() if n.kind == "claim"]
    # Bound each semantic window; retain all candidates and disclose coverage limitations.
    windows: list[dict[str, Any]] = []
    gaps: list[str] = extraction_gaps
    for start in range(0, len(roots), 8):
        group = roots[start : start + 8]
        selected = set(group)
        for _ in range(4):
            selected.update(e["target_id"] for e in edges if e["source_id"] in selected)
        shared_evidence = {eid for nid in selected for eid in by_node[nid]}
        selected.update(nid for nid in nodes if shared_evidence.intersection(by_node[nid]))
        # Include cross-batch candidates when the full paper fits the bounded context.
        extras = [nid for nid in nodes if nid not in selected]
        selected_order = sorted(selected) + extras
        entries: list[dict[str, Any]] = []
        size = 0
        for nid in selected_order:
            entry = {
                "id": nid,
                "kind": nodes[nid].kind,
                "content": nodes[nid].payload,
                "text": nodes[nid].text,
                "authorship": nodes[nid].authorship,
                "evidence_ids": by_node[nid],
            }
            length = len(json.dumps(entry, ensure_ascii=False))
            if size + length > 26000 or len(entries) >= 60:
                if nid in selected:
                    gaps.append("整合上下文超出单窗口预算；部分支撑保留为可检索候选")
                continue
            entries.append(entry)
            size += length
        ids = {e["id"] for e in entries}
        if not set(group) <= ids:
            raise ValueError("核心候选单条内容超过整合预算；保留已抽取内容，未发布新图")
        eids = {eid for nid in ids for eid in by_node[nid]}
        if sum(len(evidence[eid]) for eid in eids) > 24000:
            gaps.append("整合证据超过窗口预算，仅提供完整根证据及已验证关联")
            eids = {eid for nid in group for eid in by_node[nid]}
        if sum(len(evidence[eid]) for eid in eids) > 24000:
            raise ValueError("结论原文超出整合预算，已保留候选；未截断证据或发布新图")
        windows.append(
            {
                "document_version_id": version_id,
                "input_revision": int(snapshot[:12], 16),
                "paper_type": "unknown",
                "root_claim_ids": group,
                "candidates": entries,
                "existing_associations": [
                    e for e in edges if e["source_id"] in ids and e["target_id"] in ids
                ],
                "allowed_evidence": [{"id": eid, "text": evidence[eid]} for eid in sorted(eids)],
                "coverage_gaps": list(dict.fromkeys(gaps)),
            }
        )
    if len(windows) > 20:
        raise ValueError("论文候选超过 20 个整合窗口；候选已保留，未自动产生更多模型费用")
    with Session(engine) as session, session.begin():
        current_job = session.get(Job, job_id)
        assert current_job and current_job.payload
        frozen = current_job.payload.get("reading_windows")
        if frozen is not None:
            windows, gaps = frozen["windows"], frozen["gaps"]
        else:
            current_job.payload = {
                **current_job.payload,
                "reading_windows": {"windows": windows, "gaps": list(gaps)},
            }
    unit_ids: list[str] = []
    for index, data in enumerate(windows):
        stage(engine, job_id, "integrating")
        stage_key = "reading:integration:" + digest([snapshot, signature, data])
        with Session(engine) as session:
            cached = KnowledgeStore(session).reading().checkpoint(stage_key, digest(data))
        if cached is not None:
            unit_ids.extend(cached["unit_ids"])
            gaps.extend(cached["warnings"])
            continue
        run_id, value = await model_stage(
            engine,
            job_id,
            provider,
            "P12_reading_integration",
            PaperIntegrationProposal,
            data,
        )
        allowed_ids = {n["id"] for n in data["candidates"]}
        if {u["root_claim_id"] for u in value["units"]} != set(data["root_claim_ids"]):
            raise ValueError("P12 必须逐一返回本窗口的根结论，不得跨窗口增删")
        if any(i not in allowed_ids for u in value["units"] for i in u["member_ids"]):
            raise ValueError("P12 引用了窗口外候选")
        if any(
            a["source_id"] not in allowed_ids or a["target_id"] not in allowed_ids
            for a in value["associations"]
        ):
            raise ValueError("P12 关联端点不属于当前白名单")
        if any(set(d["candidate_ids"]) - allowed_ids for d in value["duplicates"]):
            raise ValueError("P12 重复组包含窗口外候选")
        allowed_evidence = {e["id"] for e in data["allowed_evidence"]}
        if any(set(a["evidence_ids"]) - allowed_evidence for a in value["associations"]):
            raise ValueError("P12 引用了窗口外证据")
        with Session(engine) as session, session.begin():
            current_job = session.get(Job, job_id)
            if not current_job or current_job.status != "running":
                raise ValueError("任务已取消，原始模型结果保留")
            reading = KnowledgeStore(session).reading()
            result = reading.integrate(
                proposal=value,
                version_id=version_id,
                snapshot=snapshot,
                run_id=run_id,
                key=stage_key + ":apply",
            )
            reading.save_checkpoint(stage_key, version_id, "integrating", digest(data), result)
            run = session.get(ModelRun, run_id)
            assert run
            run.status = "succeeded"
            unit_ids.extend(result["unit_ids"])
            current_job.result = {
                **(current_job.result or {}),
                "integrated_windows": index + 1,
                "integration_windows": len(windows),
            }
        gaps.extend(result["warnings"])
    recommendations = []
    for index in range(0, len(unit_ids), 8):
        stage(engine, job_id, "selecting")
        with Session(engine) as session:
            units = [session.get(ReadingUnit, uid) for uid in unit_ids[index : index + 8]]
            unit_data = []
            for unit in units:
                assert unit
                members = list(
                    session.scalars(select(ReadingMember).where(ReadingMember.unit_id == unit.id))
                )
                unit_data.append(
                    {
                        "root_claim_id": unit.root_claim_id,
                        "root": nodes[unit.root_claim_id].payload,
                        "rationale": unit.rationale,
                        "members": [
                            {"id": m.node_id, "content": nodes[m.node_id].payload} for m in members
                        ],
                    }
                )
        data = {
            "document_version_id": version_id,
            "input_revision": int(snapshot[:12], 16),
            "units": unit_data,
            "density": density,
            "coverage_gaps": list(dict.fromkeys(gaps)),
        }
        if len(json.dumps(data, ensure_ascii=False)) > 48000:
            raise ValueError("选择上下文超过预算，保留整合检查点；未截断必要支撑")
        stage_key = "reading:selection:" + digest([snapshot, signature, data])
        with Session(engine) as session:
            value = KnowledgeStore(session).reading().checkpoint(stage_key, digest(data))
        if value is None:
            run_id, value = await model_stage(
                engine,
                job_id,
                provider,
                "P13_reading_selection",
                CoreSelectionProposal,
                data,
            )
            if (
                {r["root_claim_id"] for r in value["recommendations"]}
                != {u["root_claim_id"] for u in unit_data}
                or value["document_version_id"] != version_id
                or value["input_revision"] != int(snapshot[:12], 16)
            ):
                raise ValueError("P13 选择结果与窗口白名单或版本不符")
            with Session(engine) as session, session.begin():
                current_job = session.get(Job, job_id)
                if not current_job or current_job.status != "running":
                    raise ValueError("任务已取消")
                KnowledgeStore(session).reading().save_checkpoint(
                    stage_key,
                    version_id,
                    "selecting",
                    digest(data),
                    value,
                )
                run = session.get(ModelRun, run_id)
                assert run
                run.status = "succeeded"
        recommendations.extend(value["recommendations"])
        gaps.extend(value["coverage_gaps"])
    stage(engine, job_id, "publishing")
    with Session(engine) as session, session.begin():
        current_job = session.get(Job, job_id)
        assert current_job and current_job.status == "running"
        result = (
            KnowledgeStore(session)
            .reading()
            .publish(
                version_id=version_id,
                snapshot=snapshot,
                unit_ids=unit_ids,
                proposal={
                    "document_version_id": version_id,
                    "input_revision": int(snapshot[:12], 16),
                    "recommendations": recommendations,
                    "coverage_gaps": list(dict.fromkeys(gaps)),
                },
                density=density,
                expected_revision=expected,
                key=f"reading:{job_id}:publish",
            )
        )
        runs = list(session.scalars(select(ModelRun).where(ModelRun.job_id == job_id)))
        usage: dict[str, int] = {}
        for run in runs:
            for name, amount in run.parameters.get("usage", {}).items():
                if isinstance(amount, int):
                    usage[name] = usage.get(name, 0) + amount
        current_job.result = {
            **(current_job.result or {}),
            "build_state": result["build_state"],
            "coverage_gaps": result["coverage_gaps"],
            "published_units": len(result["units"]),
            "selection_revision": result["selection_revision"],
            "model_calls": sum(len(r.parameters.get("attempts", [{}])) for r in runs),
            "usage": usage,
            "cost": None,
            "cost_status": "provider_not_reported",
        }
        current_job.status, current_job.stage, current_job.updated_at = (
            "succeeded",
            "publishing",
            now(),
        )
