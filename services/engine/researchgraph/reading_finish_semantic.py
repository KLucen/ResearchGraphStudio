"""Program-owned units with semantic association and advisory ranking stages."""

import json
from typing import Any, Literal

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from researchgraph.extraction import PROMPT_DIR, call_model, reusable_model_run, stage
from researchgraph.graph_models import SourceAssertion
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeNode, ModelRun, NodeEvidence
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest, text_hash
from researchgraph.models import Job, now
from researchgraph.providers import Provider, ProviderError
from researchgraph.reading_finish_wire import (
    INTEGRATION_PROMPT,
    LEGACY_RANKING_PROMPT,
    POLICY,
    RANKING_PROMPT,
    assert_prompt_contract,
    bind_integration,
    bind_ranking,
    generated_rules,
    schema_for,
)
from researchgraph.reading_models import ReadingMember, ReadingUnit
from researchgraph.reading_ranking_wire import PROMPT as KEYED_RANKING_PROMPT
from researchgraph.reading_ranking_wire import output_schema as keyed_ranking_schema
from researchgraph.reading_stage_validation import (
    StageValidation,
    StageValidationError,
    record_validation_failure,
    validate_ranking_input,
    validate_stage,
)
from researchgraph.reading_support import support_context
from researchgraph.reading_transport import loads
from researchgraph.unified_store import evidence_ids

DEFAULT_RANKING_PROMPT = KEYED_RANKING_PROMPT


def _paper_context(session: Session, version_id: str) -> dict[str, str]:
    version, paper = KnowledgeStore(session).reading().source(version_id)
    return {
        "title": paper.title,
        "pdf_sha256": version.sha256,
        "parser_version": version.parser_version,
    }


def _check_paper_context(session: Session, canonical: dict[str, Any]) -> None:
    if "paper_context" in canonical and canonical["paper_context"] != _paper_context(
        session, canonical["document_version_id"]
    ):
        raise StageValidationError(
            "context",
            "PAPER_CONTEXT_CHANGED",
            "论文来源上下文已变化，请创建新构建",
            response_invalid=False,
        )
    for nid, issues in canonical.get("issue_context", {}).items():
        node = session.get(KnowledgeNode, nid)
        if node is None or node.issues != issues:
            raise StageValidationError(
                "context",
                "RANKING_INPUT_CHANGED",
                "排序输入的未解疑点已变化，请创建新构建",
                response_invalid=False,
            )
    if "evidence_layout_context" in canonical:
        from researchgraph.reading_evidence_quality import layout_context

        current_layout = layout_context(
            session, canonical["document_version_id"], canonical["layout_evidence_ids"]
        )
        if current_layout != canonical["evidence_layout_context"]:
            raise StageValidationError(
                "context",
                "EVIDENCE_LAYOUT_CONTEXT_CHANGED",
                "证据排版上下文已变化，请创建新构建",
                response_invalid=False,
            )


def _layout_wire(context: dict[str, Any], aliases: dict[str, str]) -> dict[str, Any]:
    """Bind source layout to request-local evidence aliases; omit persistent IDs."""
    return {
        "policy_version": context["policy_version"],
        "status": context["status"],
        "checked_evidence_count": context["checked_evidence_count"],
        "risk_blocks": [
            {
                "block_ref": block["block_ref"],
                "evidence_refs": [aliases[eid] for eid in block["evidence_ids"]],
                "risk": block["risk"],
                "lines": block["lines"],
            }
            for block in context["risk_blocks"]
        ],
        "unresolved_evidence": [
            {"evidence_ref": aliases[entry["evidence_id"]], "reason": entry["reason"]}
            for entry in context["unresolved_evidence"]
        ],
    }


def _model_accounting(session: Session, job_id: str) -> dict[str, Any]:
    """Count persisted attempts, including failed stages, without charging cached rows."""
    usage: dict[str, int] = {}
    calls, unrecorded = 0, 0
    for run in session.scalars(select(ModelRun).where(ModelRun.job_id == job_id)):
        attempts = run.parameters.get("attempts")
        if isinstance(attempts, list):
            calls += sum(isinstance(attempt, dict) for attempt in attempts)
        else:
            # Old/imported ModelRuns do not prove how many requests were made.
            unrecorded += 1
        recorded = run.parameters.get("usage", {})
        if isinstance(recorded, dict):
            for name in ("prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens"):
                amount = recorded.get(name)
                if type(amount) is int and amount >= 0:
                    usage[name] = usage.get(name, 0) + amount
    return {
        "model_calls": calls,
        "model_calls_unrecorded_runs": unrecorded,
        "model_calls_status": "known_attempts_only" if unrecorded else "recorded",
        "usage": usage,
        "cost": None,
        "cost_status": "provider_not_reported",
    }


def _refresh_model_accounting(engine: Engine, job_id: str) -> None:
    with Session(engine) as session, session.begin():
        job = session.get(Job, job_id)
        if job:
            job.result = {**(job.result or {}), **_model_accounting(session, job_id)}


def _wire_content(value: Any, evidence: dict[str, str]) -> Any:
    if isinstance(value, list):
        return [_wire_content(v, evidence) for v in value]
    if isinstance(value, dict):
        return {
            key: [evidence[eid] for eid in child]
            if key == "evidence_ids"
            else _wire_content(child, evidence)
            for key, child in value.items()
            if key != "local_ref"
        }
    return value


async def semantic_stage(
    engine: Engine,
    job_id: str,
    provider: Provider,
    name: Literal["P12", "P13"],
    wire: dict[str, Any],
    canonical: dict[str, Any],
    context: dict[str, Any],
    snapshot: str,
) -> tuple[str, StageValidation]:
    prompt = (
        INTEGRATION_PROMPT if name == "P12" else context.get("prompt_name", LEGACY_RANKING_PROMPT)
    )
    if name == "P13" and prompt not in {LEGACY_RANKING_PROMPT, RANKING_PROMPT}:
        raise StageValidationError(
            "context",
            "RANKING_PROMPT_UNKNOWN",
            "冻结排序协议未知，请创建新构建",
            response_invalid=False,
        )
    assert_prompt_contract(name, (PROMPT_DIR / (prompt + ".md")).read_text(encoding="utf-8"))
    schema = schema_for(name)
    manifest = {
        "pipeline": "paper-reading-v1",
        "schema_hash": digest(schema),
        "semantic_context": context,
    }

    def validate(raw: str) -> StageValidation:
        def bind(text: str) -> str:
            value = loads(text)
            bound = (
                bind_integration(value, context) if name == "P12" else bind_ranking(value, context)
            )
            return json.dumps(bound, ensure_ascii=False)

        with Session(engine) as session:
            if name == "P13":
                _check_paper_context(session, canonical)
            return validate_stage(
                session, name, raw, canonical, snapshot=snapshot, wire_validator=bind
            )

    try:
        cached = reusable_model_run(
            engine,
            job_id,
            provider,
            prompt,
            wire,
            manifest,
            include_invalid=True,
            validator=validate,
        )
        if cached is None and name == "P13":
            with Session(engine) as session:
                _check_paper_context(session, canonical)
                validate_ranking_input(session, canonical, snapshot=snapshot)
        run_id, raw = cached or await call_model(
            engine,
            job_id,
            context["document_version_id"],
            provider,
            prompt,
            wire,
            schema,
            manifest,
            adaptive_timeout=True,
        )
    finally:
        _refresh_model_accounting(engine, job_id)
    try:
        result = validate(raw)
    except StageValidationError as error:
        record_validation_failure(engine, run_id, error, wire, raw)
        raise
    with Session(engine) as session, session.begin():
        run = session.get(ModelRun, run_id)
        assert run
        run.parameters = {
            **run.parameters,
            "integration_normalization": [
                {"path": "envelope", "rule": "engine-bound-stage-context-v1"},
                *result.normalization,
            ],
            **(
                {"integration_context_quarantine": result.quarantined} if result.quarantined else {}
            ),
        }
    return run_id, result


def _expected(job: Job, current: Any, initial: int) -> int:
    preview = (job.result or {}).get("preview_selection_revision")
    if preview and current and current.revision == preview:
        return int(preview)
    return initial


def _fallback(
    engine: Engine, job_id: str, version_id: str, snapshot: str, expected: int, error: Exception
) -> None:
    """First builds remain usable; an existing selected graph is never replaced."""
    with Session(engine) as session, session.begin():
        job = session.get(Job, job_id)
        if not job or job.status != "running":
            return
        reading = KnowledgeStore(session).reading()
        _, paper = reading.source(version_id)
        current = reading.current(paper.id)
        result = {**(job.result or {}), **_model_accounting(session, job_id)}
        category = getattr(error, "category", "schema")
        next_action = {
            "context": (
                "输入或来源不一致时停止重复请求；检查来源状态，必要时基于已保存候选创建新构建"
            ),
            "evidence": "检查来源和证据状态；有效知识保留，不通过重抽覆盖证据问题",
            "structured_output_unsupported": (
                "当前模型或接口不支持此输出协议；调整全局模型配置后基于已保存候选创建新构建"
            ),
            "structured_output_refused": (
                "服务商拒绝了本次输出；查看模型配置及服务限制，已保存知识保留"
            ),
            "client": "检查接口配置、额度或请求兼容性；修正后基于已保存候选继续构建",
        }.get(category, "继续未完成阶段；已保存知识和成功检查点保留")
        failure = {
            "stage": job.stage,
            "category": category,
            "code": getattr(error, "code", getattr(error, "category", "INVALID_RESPONSE")),
            "next_action": next_action,
        }
        result["stage_failure"] = failure
        result["ranking_status"] = "pending"
        # A stale source/snapshot cannot become trustworthy through a fallback.
        if isinstance(error, StageValidationError) and not error.response_invalid:
            job.result = result
            return
        if current or reading.snapshot(version_id) != snapshot:
            result["previous_graph_retained"] = bool(current)
            job.result = result
            return
        units = reading.form_units(version_id, snapshot, f"reading:{job_id}:base-units")
        roots = []
        for uid in units["unit_ids"]:
            unit = session.get(ReadingUnit, uid)
            assert unit
            roots.append(unit.root_claim_id)
        proposal = {
            "document_version_id": version_id,
            "input_revision": int(snapshot[:12], 16),
            "recommendations": [
                {
                    "root_claim_id": root,
                    "recommendation": "suggest_core",
                    "reasons": ["answers_paper_question"],
                    "rationale": "仅展示有来源的明确贡献候选；核心贡献排序尚未完成",
                }
                for root in roots
            ],
            "coverage_gaps": list(
                dict.fromkeys(
                    [
                        *result.get("coverage_gaps", []),
                        "核心贡献排序未完成；当前为通过来源门槛的结论候选及已有支撑，不代表最终核心图谱",
                    ]
                )
            ),
        }
        published = reading.publish(
            version_id=version_id,
            snapshot=snapshot,
            unit_ids=units["unit_ids"],
            proposal=proposal,
            density=(job.payload or {}).get("density", "standard"),
            expected_revision=expected,
            key=f"reading:{job_id}:preview",
            selection_mode="provisional",
        )
        job.result = {
            **result,
            "preview_selection_revision": published["selection_revision"],
            "selection_revision": published["selection_revision"],
            "published_units": len(published["units"]),
            "build_state": "partial",
            "coverage_gaps": published["coverage_gaps"],
        }


async def finish_semantic_reading(engine: Engine, job_id: str, provider: Provider) -> None:
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
        existing = job.payload.get("reading_finish_plan")
        ranking_prompt = (
            existing.get("ranking_prompt", LEGACY_RANKING_PROMPT)
            if existing
            else DEFAULT_RANKING_PROMPT
        )
        if ranking_prompt not in {LEGACY_RANKING_PROMPT, RANKING_PROMPT, KEYED_RANKING_PROMPT}:
            raise KnowledgeError("READING_INPUT_CHANGED", "冻结排序协议未知，请创建新构建")
        paper_context = _paper_context(session, version_id)
        signature = digest(
            {
                "policy": POLICY,
                "prompts": {
                    p: text_hash((PROMPT_DIR / (p + ".md")).read_text(encoding="utf-8"))
                    for p in (INTEGRATION_PROMPT, ranking_prompt)
                },
                "schemas": [
                    schema_for("P12"),
                    keyed_ranking_schema()
                    if ranking_prompt == KEYED_RANKING_PROMPT
                    else schema_for("P13"),
                ],
                "provider": provider.name,
                "model": provider.model,
                "parameters": getattr(provider, "parameters", {}),
                "endpoint": getattr(provider, "base_url", "offline"),
            }
        )
        if existing and (
            existing.get("flow_policy") != POLICY
            or existing.get("signature") != signature
            or existing.get("snapshot") != snapshot
        ):
            raise KnowledgeError("READING_INPUT_CHANGED", "阶段输入或模型协议已改变，请创建新构建")
        plan = existing or {
            "flow_policy": POLICY,
            "context_policy": "complete-context-v1",
            "ranking_prompt": ranking_prompt,
            "signature": signature,
            "snapshot": snapshot,
            "expected_revision": current.revision if current else 0,
            "extraction_coverage_gaps": list((job.result or {}).get("coverage_gaps", [])),
        }
        expected = _expected(job, current, plan["expected_revision"])
        if (current.revision if current else 0) != expected:
            raise KnowledgeError("SELECTION_REVISION_CONFLICT", "展示或选择已更新，请创建新构建")
        nodes = {n.id: n for n in reading.nodes(version_id) if reading.source_valid(n)}
        by_node = {
            nid: sorted(
                session.scalars(select(NodeEvidence.evidence_id).where(NodeEvidence.node_id == nid))
            )
            for nid in nodes
        }
        evidence = {}
        for eid in {eid for ids in by_node.values() for eid in ids}:
            span = session.get(EvidenceSpan, eid)
            assert span
            evidence[eid] = span.quote
        aliases = {f"n{i:04d}": nid for i, nid in enumerate(sorted(nodes), 1)}
        ealiases = {f"e{i:04d}": eid for i, eid in enumerate(sorted(evidence), 1)}
        inverse, einverse = {v: k for k, v in aliases.items()}, {v: k for k, v in ealiases.items()}
        roots = [nid for nid, n in nodes.items() if n.kind == "claim"]
        canonical = {
            "document_version_id": version_id,
            "input_revision": int(snapshot[:12], 16),
            "candidates": [
                {"id": nid, "content": n.payload, "evidence_ids": by_node[nid]}
                for nid, n in nodes.items()
            ],
            "root_claim_ids": roots,
            "allowed_evidence": [{"id": eid, "text": text} for eid, text in evidence.items()],
        }
        edges = list(
            session.scalars(
                select(SourceAssertion).where(
                    SourceAssertion.source_id.in_(nodes), SourceAssertion.target_id.in_(nodes)
                )
            )
        )
        wire = {
            "contract_rules": generated_rules("P12"),
            "candidates": [
                {"candidate_ref": ref, "content": _wire_content(nodes[nid].payload, einverse)}
                for ref, nid in aliases.items()
            ],
            "allowed_evidence": [
                {"evidence_ref": ref, "text": evidence[eid]} for ref, eid in ealiases.items()
            ],
            "existing_associations": [
                {
                    "source_ref": inverse[e.source_id],
                    "target_ref": inverse[e.target_id],
                    "relation": e.relation,
                    "evidence_refs": [einverse[eid] for eid in e.evidence_ids],
                }
                for e in edges
                if set(e.evidence_ids) <= einverse.keys()
            ],
        }
        context = {
            "document_version_id": version_id,
            "input_revision": canonical["input_revision"],
            "candidate_aliases": aliases,
            "evidence_aliases": ealiases,
        }
        if ranking_prompt == KEYED_RANKING_PROMPT:
            from researchgraph.reading_finish_upgrade import integration_input

            adopted_input = integration_input(session, job)
            if adopted_input is not None:
                wire, canonical, context = (
                    adopted_input["wire"],
                    adopted_input["canonical"],
                    adopted_input["context"],
                )
        frozen_input = plan.get("integration_input")
        if frozen_input is not None:
            wire, canonical, context = (
                frozen_input["wire"],
                frozen_input["canonical"],
                frozen_input["context"],
            )
        else:
            plan = {
                **plan,
                "integration_input": {"wire": wire, "canonical": canonical, "context": context},
            }
            job.payload = {**job.payload, "reading_finish_plan": plan}
        density = job.payload.get("density", "standard")
        gaps = list(plan.get("extraction_coverage_gaps", []))
    if not roots:
        stage(engine, job_id, "publishing")
        with Session(engine) as session, session.begin():
            job = session.get(Job, job_id)
            assert job and job.status == "running"
            published = (
                KnowledgeStore(session)
                .reading()
                .publish(
                    version_id=version_id,
                    snapshot=snapshot,
                    unit_ids=[],
                    proposal={
                        "document_version_id": version_id,
                        "input_revision": int(snapshot[:12], 16),
                        "recommendations": [],
                        "coverage_gaps": gaps,
                    },
                    density=density,
                    expected_revision=expected,
                    key=f"reading:{job_id}:publish",
                )
            )
            job.result = {
                **(job.result or {}),
                "published_units": 0,
                "selection_revision": published["selection_revision"],
                "coverage_gaps": published["coverage_gaps"],
                "build_state": published["build_state"],
                "ranking_status": "not_applicable",
                "stage_failure": None,
                **_model_accounting(session, job_id),
            }
            job.status, job.error, job.updated_at = "succeeded", None, now()
        return
    try:
        integration_key = "reading:semantic-integration:" + digest([snapshot, signature, wire])
        with Session(engine) as session:
            integrated = KnowledgeStore(session).reading().checkpoint(integration_key, digest(wire))
        if integrated is None:
            from researchgraph.reading_finish_upgrade import adopt_integration

            with Session(engine) as session, session.begin():
                job = session.get(Job, job_id)
                assert job
                integrated = adopt_integration(
                    session, job, wire, canonical, context, snapshot, integration_key
                )
        if integrated is None:
            run_id, proposal = await semantic_stage(
                engine, job_id, provider, "P12", wire, canonical, context, snapshot
            )
            with Session(engine) as session, session.begin():
                job = session.get(Job, job_id)
                if not job or job.status != "running":
                    raise ValueError("任务已取消，模型原响应保留")
                reading = KnowledgeStore(session).reading()
                integrated = reading.integrate(
                    proposal=proposal.value,
                    version_id=version_id,
                    snapshot=snapshot,
                    run_id=run_id,
                    key=integration_key + ":apply",
                )
                reading.save_checkpoint(
                    integration_key, version_id, "integrating", digest(wire), integrated
                )
                run = session.get(ModelRun, run_id)
                assert run
                run.status, run.error, run.finished_at = "succeeded", None, now()
        gaps.extend(integrated["warnings"])
        with Session(engine) as session, session.begin():
            job = session.get(Job, job_id)
            assert job and job.status == "running"
            reading = KnowledgeStore(session).reading()
            # Include the actual association snapshot: a failed ranking retry must
            # not reuse a pre-integration base unit checkpoint from its preview.
            units_result = reading.form_units(version_id, snapshot, integration_key + ":units")
            live_support = support_context(reading, version_id, nodes)
            if plan.get("support_context", live_support) != live_support:
                raise StageValidationError(
                    "context",
                    "SUPPORT_CONTEXT_CHANGED",
                    "结论关联已变化，请创建新构建",
                    response_invalid=False,
                )
            if "support_context" not in plan:
                plan = {**plan, "support_context": live_support}
                job.payload = {**(job.payload or {}), "reading_finish_plan": plan}
            unit_ids = units_result["unit_ids"]
            unit_data = []
            for uid in unit_ids:
                unit = session.get(ReadingUnit, uid)
                assert unit
                members = list(
                    session.scalars(select(ReadingMember).where(ReadingMember.unit_id == uid))
                )
                unit_data.append(
                    {
                        "root_claim_id": unit.root_claim_id,
                        "root": nodes[unit.root_claim_id].payload,
                        "rationale": unit.rationale,
                        "members": [
                            {
                                "id": m.node_id,
                                "content": nodes[m.node_id].payload,
                                "association_ids": m.association_ids,
                            }
                            for m in members
                        ],
                    }
                )
            job.result = {**(job.result or {}), "integrated_windows": 1, "integration_windows": 1}
        stage(engine, job_id, "selecting")
        claims = {f"c{i:04d}": u["root_claim_id"] for i, u in enumerate(unit_data, 1)}
        ranking_wire = {
            "contract_rules": generated_rules("P13"),
            "density": density,
            "units": [
                {
                    "claim_ref": ref,
                    "claim": _wire_content(unit["root"], einverse),
                    "support": [_wire_content(m["content"], einverse) for m in unit["members"]],
                }
                for (ref, _), unit in zip(claims.items(), unit_data, strict=True)
            ],
            "coverage_gaps": list(dict.fromkeys(gaps)),
        }
        ranking_context = {
            "document_version_id": version_id,
            "input_revision": canonical["input_revision"],
            "claim_aliases": claims,
            "coverage_gaps": list(dict.fromkeys(gaps)),
        }
        ranking_input = {
            "document_version_id": version_id,
            "input_revision": canonical["input_revision"],
            "units": unit_data,
            "support_context": live_support,
        }
        if ranking_prompt in {RANKING_PROMPT, KEYED_RANKING_PROMPT}:
            for wire_unit, unit_input in zip(ranking_wire["units"], unit_data, strict=True):
                wire_unit["claim_issues"] = list(nodes[unit_input["root_claim_id"]].issues)
                wire_unit["support_issues"] = [
                    {"support_index": index, "issues": list(nodes[member["id"]].issues)}
                    for index, member in enumerate(unit_input["members"])
                    if nodes[member["id"]].issues
                ]
            cited = evidence_ids(ranking_wire["units"])
            ranking_wire.update(
                paper_context=paper_context,
                allowed_evidence=[
                    {"evidence_ref": ref, "text": evidence[eid]}
                    for ref, eid in ealiases.items()
                    if ref in cited
                ],
            )
            ranking_context["prompt_name"] = ranking_prompt
            ranking_input["paper_context"] = paper_context
            ranking_input["issue_context"] = {
                nid: list(nodes[nid].issues)
                for entry in unit_data
                for nid in [entry["root_claim_id"], *[member["id"] for member in entry["members"]]]
            }
            from researchgraph.reading_evidence_quality import layout_context

            layout_ids = sorted(ealiases[ref] for ref in cited)
            with Session(engine) as session:
                layout = layout_context(session, version_id, layout_ids)
            ranking_wire["evidence_layout_context"] = _layout_wire(layout, einverse)
            ranking_input["evidence_layout_context"] = layout
            ranking_input["layout_evidence_ids"] = layout_ids
        if ranking_prompt == KEYED_RANKING_PROMPT:
            from researchgraph.reading_ranking_wire import generated_rules as keyed_rules

            ranking_wire["contract_rules"] = keyed_rules(claims)
            ranking_wire["assessment_refs"] = list(claims)
        ranking_key = "reading:semantic-ranking:" + digest([snapshot, signature, ranking_wire])
        with Session(engine) as session, session.begin():
            if ranking_prompt in {RANKING_PROMPT, KEYED_RANKING_PROMPT}:
                job = session.get(Job, job_id)
                assert job and job.status == "running"
                frozen_ranking = plan.get("ranking_input")
                live_ranking = {
                    "wire": ranking_wire,
                    "canonical": ranking_input,
                    "context": ranking_context,
                }
                if frozen_ranking is not None and frozen_ranking != live_ranking:
                    raise StageValidationError(
                        "context",
                        "RANKING_INPUT_CHANGED",
                        "冻结排序上下文已变化，请创建新构建",
                        response_invalid=False,
                    )
                if frozen_ranking is None:
                    plan = {**plan, "ranking_input": live_ranking}
                    job.payload = {**(job.payload or {}), "reading_finish_plan": plan}
                _check_paper_context(session, ranking_input)
            validate_ranking_input(session, ranking_input, snapshot=snapshot)
            selected = (
                KnowledgeStore(session).reading().checkpoint(ranking_key, digest(ranking_wire))
            )
        if selected is None:
            if ranking_prompt == KEYED_RANKING_PROMPT:
                from researchgraph.reading_ranking import rank_claims

                try:
                    run_id, ranking = await rank_claims(
                        engine,
                        job_id,
                        provider,
                        ranking_wire,
                        ranking_input,
                        ranking_context,
                        snapshot,
                        _check_paper_context,
                    )
                finally:
                    _refresh_model_accounting(engine, job_id)
            else:
                run_id, ranking = await semantic_stage(
                    engine,
                    job_id,
                    provider,
                    "P13",
                    ranking_wire,
                    ranking_input,
                    ranking_context,
                    snapshot,
                )
            selected = ranking.value
            with Session(engine) as session, session.begin():
                job = session.get(Job, job_id)
                if not job or job.status != "running":
                    raise ValueError("任务已取消，模型原响应保留")
                KnowledgeStore(session).reading().save_checkpoint(
                    ranking_key, version_id, "selecting", digest(ranking_wire), selected
                )
                run = session.get(ModelRun, run_id)
                assert run
                run.status, run.error, run.finished_at = "succeeded", None, now()
        stage(engine, job_id, "publishing")
        with Session(engine) as session, session.begin():
            job = session.get(Job, job_id)
            assert job and job.status == "running"
            reading = KnowledgeStore(session).reading()
            if ranking_prompt in {RANKING_PROMPT, KEYED_RANKING_PROMPT}:
                _check_paper_context(session, ranking_input)
            _, paper = reading.source(version_id)
            current = reading.current(paper.id)
            published = reading.publish(
                version_id=version_id,
                snapshot=snapshot,
                unit_ids=unit_ids,
                proposal=selected,
                density=density,
                expected_revision=_expected(job, current, plan["expected_revision"]),
                key=f"reading:{job_id}:publish",
                contribution_order=[r["root_claim_id"] for r in selected["recommendations"]],
            )
            job.result = {
                **(job.result or {}),
                "selection_revision": published["selection_revision"],
                "published_units": len(published["units"]),
                "build_state": published["build_state"],
                "coverage_gaps": published["coverage_gaps"],
                "selected_windows": 1,
                "selection_windows": 1,
                "ranking_status": "complete",
                "stage_failure": None,
                **_model_accounting(session, job_id),
            }
            job.status, job.error, job.updated_at = "succeeded", None, now()
    except (StageValidationError, ProviderError) as error:
        _fallback(engine, job_id, version_id, snapshot, expected, error)
        raise
    except KnowledgeError as error:
        if error.code != "SUPPORT_CONTEXT_CHANGED":
            raise
        conflict = StageValidationError("context", error.code, str(error), response_invalid=False)
        _fallback(engine, job_id, version_id, snapshot, expected, conflict)
        raise conflict from None
