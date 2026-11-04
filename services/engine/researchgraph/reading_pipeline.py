"""Complete paper integration and selection, recoverable without PDF re-extraction."""

from typing import Any

from pydantic import BaseModel
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.extraction import PROMPT_DIR, call_model, reusable_model_run, stage
from researchgraph.graph_models import SourceAssertion
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeDependency, ModelRun, NodeEvidence
from researchgraph.knowledge_store import KnowledgeStore, digest, text_hash
from researchgraph.models import Job, now
from researchgraph.providers import Provider
from researchgraph.reading_contracts import CoreSelectionProposal, PaperIntegrationProposal
from researchgraph.reading_models import ReadingMember, ReadingUnit
from researchgraph.reading_validation import isolate_integration_proposals


async def model_stage(
    engine: Engine,
    job_id: str,
    provider: Provider,
    prompt: str,
    schema: type[BaseModel],
    data: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    from researchgraph.reading_stage_validation import (
        StageValidationError,
        record_validation_failure,
        validate_stage,
    )

    manifest = {"pipeline": "paper-reading-v1", "schema_hash": digest(schema.model_json_schema())}

    def terminal(raw: str) -> Any:
        with Session(engine) as session:
            return validate_stage(
                session, "P12" if schema is PaperIntegrationProposal else "P13", raw, data
            )

    cached = reusable_model_run(
        engine, job_id, provider, prompt, data, manifest, include_invalid=True, validator=terminal
    )
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
        # The shared terminal validator includes the historical decoder and its
        # allowed normalization, identically for live and cached responses.
        result = terminal(raw)
        value, audit = result.value, result.normalization
        if audit:
            with Session(engine) as session, session.begin():
                run = session.get(ModelRun, run_id)
                assert run
                run.parameters = {**run.parameters, "integration_normalization": audit}
    except StageValidationError as error:
        record_validation_failure(engine, run_id, error, data, raw)
        raise
    return run_id, value


async def finish_reading(engine: Engine, job_id: str, provider: Provider) -> None:
    from researchgraph.reading_finish_wire import POLICY

    with Session(engine) as session:
        target = session.get(Job, job_id)
        payload = (target.payload or {}) if target else {}
        plan = payload.get("reading_finish_plan")
        semantic = (
            plan.get("flow_policy") == POLICY
            if plan
            else payload.get("reading_flow_policy") == POLICY
        )
    if semantic:
        from researchgraph.reading_finish_semantic import finish_semantic_reading

        await finish_semantic_reading(engine, job_id, provider)
        return
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
        context_policy = plan.get("context_policy") if plan else "complete-context-v1"
        if context_policy not in {None, "complete-context-v1"}:
            raise ValueError("整合上下文策略未知，已保存计划保持不变")
        frozen = job.payload.get("reading_windows")
        prompts = (
            plan.get("prompts", ["P12_reading_integration", "P13_reading_selection"])
            if plan
            else ["P12_reading_integration_v2", "P13_reading_selection_v3"]
        )
        signature = digest(
            {
                "prompts": {
                    p: text_hash((PROMPT_DIR / (p + ".md")).read_text(encoding="utf-8"))
                    for p in prompts
                },
                "schemas": [
                    PaperIntegrationProposal.model_json_schema(),
                    CoreSelectionProposal.model_json_schema(),
                ],
                "provider": provider.name,
                "model": provider.model,
                "parameters": getattr(provider, "parameters", {}),
                "endpoint": getattr(provider, "base_url", "offline"),
                **({"context_policy": context_policy} if context_policy else {}),
            }
        )
        if plan and plan.get("signature") != signature:
            raise ValueError("整合模型、Prompt 或 Schema 已改变，请创建新构建")
        if plan and plan["snapshot"] != snapshot:
            raise ValueError("候选快照已变化；请启动新构建，已保存候选不会丢失")
        if not plan:
            plan = {
                "prompts": prompts,
                "snapshot": snapshot,
                "signature": signature,
                "expected_revision": current.revision if current else 0,
                "context_policy": context_policy,
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
    # Read frozen inputs before planning anything. In particular, a retry must
    # reuse old integration checkpoints even when their complete units are large.
    if frozen is not None:
        windows, gaps = frozen["windows"], list(frozen["gaps"])
    else:
        roots = [n.id for n in nodes.values() if n.kind == "claim"]
        gaps = extraction_gaps
        entries = [
            {
                "id": nid,
                "kind": nodes[nid].kind,
                "content": nodes[nid].payload,
                "text": nodes[nid].text,
                "authorship": nodes[nid].authorship,
                "evidence_ids": by_node[nid],
            }
            for nid in roots + sorted(set(nodes) - set(roots))
        ]
        ids = {e["id"] for e in entries}
        eids = {eid for nid in ids for eid in by_node[nid]}
        # No application character/token/count budget: send the complete paper
        # candidate snapshot and all its referenced evidence once. Actual endpoint
        # failures retain this input and all earlier work for an explicit retry.
        windows = (
            [
                {
                    "document_version_id": version_id,
                    "input_revision": int(snapshot[:12], 16),
                    "paper_type": "unknown",
                    "root_claim_ids": roots,
                    "integration_rules": {
                        "required_roots": (
                            "Return exactly one unit per root_claim_ids entry, "
                            "even without support."
                        ),
                        "members": (
                            "Exclude the root itself. Only cite supplied candidate IDs; "
                            "do not emit another root as this window's root."
                        ),
                        "empty_support": (
                            "Use empty member_ids if support cannot be established; "
                            "do not invent a member or edge."
                        ),
                    },
                    "candidates": entries,
                    "existing_associations": [
                        e for e in edges if e["source_id"] in ids and e["target_id"] in ids
                    ],
                    "allowed_evidence": [
                        {"id": eid, "text": evidence[eid]} for eid in sorted(eids)
                    ],
                    "coverage_gaps": list(dict.fromkeys(gaps)),
                }
            ]
            if roots
            else []
        )
        with Session(engine) as session, session.begin():
            current_job = session.get(Job, job_id)
            if not current_job or current_job.status != "running":
                raise ValueError("任务已取消，未保存整合输入")
            assert current_job.payload
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
            prompts[0],
            PaperIntegrationProposal,
            data,
        )
        allowed_ids = {n["id"] for n in data["candidates"]}
        quarantined = isolate_integration_proposals(value, data)
        if quarantined:
            with Session(engine) as session, session.begin():
                run = session.get(ModelRun, run_id)
                assert run
                run.parameters = {**run.parameters, "integration_context_quarantine": quarantined}
        returned = {u["root_claim_id"] for u in value["units"]}
        # Missing organization must not discard a validated author claim. Retain a
        # direct-evidence-only unit, explicitly disclose the missing integration;
        # do not synthesize support, relationships or scientific content.
        for missing in sorted(set(data["root_claim_ids"]) - returned):
            local_ref = "unintegrated-" + missing
            if any(u["local_ref"] == local_ref for u in value["units"]):
                raise ValueError("P12 单元编号冲突")
            value["units"].append(
                {
                    "local_ref": local_ref,
                    "root_claim_id": missing,
                    "member_ids": [],
                    "rationale": "模型未返回该结论的整合，仅保留直接原文依据",
                }
            )
            value["warnings"].append("部分结论尚无模型整合结果，仅保留直接原文依据")
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
            run.error, run.finished_at = None, now()
            unit_ids.extend(result["unit_ids"])
            current_job.result = {
                **(current_job.result or {}),
                "integrated_windows": index + 1,
                "integration_windows": len(windows),
            }
        gaps.extend(result["warnings"])
    recommendations = []
    # Legacy plans keep the exact P13 grouping/input hashes so completed selection
    # checkpoints remain reusable. New plans select across all complete units.
    selection_size = (len(unit_ids) or 1) if context_policy else 8
    for index in range(0, len(unit_ids), selection_size):
        stage(engine, job_id, "selecting")
        with Session(engine) as session:
            units = [
                session.get(ReadingUnit, uid) for uid in unit_ids[index : index + selection_size]
            ]
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
        stage_key = "reading:selection:" + digest([snapshot, signature, data])
        with Session(engine) as session:
            value = KnowledgeStore(session).reading().checkpoint(stage_key, digest(data))
        if value is None:
            run_id, value = await model_stage(
                engine,
                job_id,
                provider,
                prompts[1],
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
                run.status, run.error, run.finished_at = "succeeded", None, now()
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
