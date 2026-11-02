"""P3 mutation implementation, invoked exclusively through KnowledgeStore."""

from typing import Any
from uuid import uuid4

from researchgraph.knowledge_models import KnowledgeOperation, ModelRun
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest
from researchgraph.models import now
from researchgraph.reasoning_context import current_hash
from researchgraph.reasoning_contracts import (
    ComparabilityReport,
    EntityAlignmentBatch,
    ProposalView,
    RelationInference,
    SemanticReviewRequest,
)
from researchgraph.reasoning_models import (
    AlignmentCandidate,
    ReasoningAttempt,
    RelationAssertion,
    SemanticReview,
)


def validate_comparison(report: ComparabilityReport, snapshot: dict[str, Any]) -> None:
    a, b = snapshot["source"], snapshot["target"]
    if (report.source_claim_id, report.target_claim_id) != (a["root_id"], b["root_id"]):
        raise KnowledgeError("PAIR_MISMATCH", "模型返回了本次输入之外的主张")
    dimensions = {d.name: d for d in report.dimensions}
    required = set(a["dimensions"]) | set(b["dimensions"])
    if len(dimensions) != len(report.dimensions) or not required <= dimensions.keys():
        raise KnowledgeError("CONDITION_MISSING", "比较报告缺少当前条件维度或包含重复维度")
    allowed = {e["id"] for s in (a, b) for e in s["evidence"]}
    unknown = False
    for name, d in dimensions.items():
        if not set(d.evidence_ids) <= allowed:
            raise KnowledgeError("UNKNOWN_EVIDENCE", "比较报告包含未提供证据")
        states = [
            s["dimensions"].get(name, {"known_state": "unknown", "value": None, "unit": None})
            for s in (a, b)
        ]
        if any(s["known_state"] in {"unknown", "conflicting"} for s in states):
            unknown = True
            if d.comparison != "unknown":
                raise KnowledgeError(
                    "UNKNOWN_CONDITION", "未知或冲突条件不能被模型判为相同、不同或不适用"
                )
        if d.comparison == "not_applicable" and not all(
            s["known_state"] == "not_applicable" for s in states
        ):
            raise KnowledgeError("UNKNOWN_CONDITION", "不适用必须由双方当前条件明确记录")
        if d.comparison in {"same", "different"} and (
            not d.evidence_ids or not all(s["known_state"] == "known" for s in states)
        ):
            raise KnowledgeError("NEEDS_EVIDENCE", "确定的条件比较需要双方已知条件与证据")
        if name in required and (d.source_value, d.target_value) != (
            states[0]["value"],
            states[1]["value"],
        ):
            raise KnowledgeError("CONDITION_VALUE_MISMATCH", "比较报告修改了当前条件值")
        if d.comparison == "same" and states[0]["unit"] != states[1]["unit"]:
            raise KnowledgeError("UNIT_MISMATCH", "单位不同不能直接判为相同条件")
    if unknown and report.overall == "comparable":
        raise KnowledgeError("UNKNOWN_CONDITION", "条件缺失时不能声明完全可比")


def validate_inference(
    output: RelationInference, report: ComparabilityReport, snapshot: dict[str, Any]
) -> None:
    a, b = snapshot["source"], snapshot["target"]
    if (output.source_claim_id, output.target_claim_id) != (a["root_id"], b["root_id"]):
        raise KnowledgeError("PAIR_MISMATCH", "关系端点不属于本次输入")
    ids = set(output.evidence_ids)
    allowed = {e["id"] for s in (a, b) for e in s["evidence"]}
    if not ids <= allowed:
        raise KnowledgeError("UNKNOWN_EVIDENCE", "关系引用了本次输入之外的证据")
    if output.decision == "PROPOSE_RELATION" and not all(
        ids & set(s["root_evidence_ids"]) for s in (a, b)
    ):
        raise KnowledgeError("BOTH_SIDES_REQUIRED", "候选关系必须引用双方主张的直接证据")
    if output.relation_type == "CONTRADICTS":
        comparable = report.overall == "comparable" and report.topic_overlap == "same"
        for dimension in ("task_type", "metric"):
            x, y = a["dimensions"][dimension], b["dimensions"][dimension]
            comparable = (
                comparable
                and x["known_state"] == y["known_state"] == "known"
                and str(x["value"]).strip().casefold() == str(y["value"]).strip().casefold()
                and x["unit"] == y["unit"]
            )
        if not comparable:
            raise KnowledgeError("NOT_COMPARABLE", "任务、指标或单位未对齐，不能建立直接矛盾关系")


def proposal_view(
    store: KnowledgeStore, proposal: RelationAssertion | AlignmentCandidate
) -> ProposalView:
    attempt = store.session.get(ReasoningAttempt, proposal.attempt_id)
    assert attempt
    return ProposalView.model_validate(proposal).model_copy(
        update={
            "stale": current_hash(store.session, attempt.snapshot, attempt.mode)
            != attempt.snapshot_hash
        }
    )


class ReasoningMutations:
    def __init__(self, store: KnowledgeStore):
        self.store, self.session = store, store.session

    def apply(
        self,
        *,
        mode: str,
        snapshot: dict[str, Any],
        output: dict[str, Any],
        comparison: dict[str, Any] | None,
        run_ids: list[str],
        key: str,
    ) -> dict[str, Any]:
        request_hash = digest(
            {"mode": mode, "snapshot": snapshot, "output": output, "comparison": comparison}
        )
        previous = self.session.get(KnowledgeOperation, key)
        if previous:
            if previous.request_hash != request_hash:
                raise KnowledgeError("IDEMPOTENCY_CONFLICT", "同一推理标识不能写入不同内容")
            return previous.response
        if current_hash(self.session, snapshot, mode) != digest(snapshot):
            raise KnowledgeError("STALE_INPUT", "推理期间主张、条件或证据已变化，请重新运行")
        source = next(
            n for n in snapshot["source"]["nodes"] if n["id"] == snapshot["source"]["root_id"]
        )
        expected_prompts = (
            ["P04_compare_conditions", "P05_infer_relation"]
            if mode == "relation"
            else ["P03_normalize_entities"]
        )
        if len(run_ids) != len(expected_prompts):
            raise KnowledgeError("MODEL_RUN_MISMATCH", "推理调用记录不完整")
        for rid, prompt in zip(run_ids, expected_prompts, strict=True):
            run = self.session.get(ModelRun, rid)
            if (
                run is None
                or run.document_version_id != source["document_version_id"]
                or run.prompt_name != prompt
                or run.status not in {"received", "succeeded"}
            ):
                raise KnowledgeError("MODEL_RUN_MISMATCH", "推理调用来源不匹配")
        proposal_data: tuple[str, str, list[str]] | None = None
        if mode == "relation":
            report = ComparabilityReport.model_validate(comparison)
            inference = RelationInference.model_validate(output)
            validate_comparison(report, snapshot)
            validate_inference(inference, report, snapshot)
            if inference.decision == "PROPOSE_RELATION":
                assert inference.relation_type
                proposal_data = (inference.relation_type, inference.reason, inference.evidence_ids)
        else:
            batch = EntityAlignmentBatch.model_validate(output)
            for alignment in batch.alignments:
                if (
                    alignment.source_local_ref != "source"
                    or alignment.candidate_concept_id != snapshot["target"]["root_id"]
                ):
                    raise KnowledgeError("ENTITY_MISMATCH", "对齐对象不在本次候选中")
                ids = set(alignment.evidence_span_ids)
                allowed = {e["id"] for s in ("source", "target") for e in snapshot[s]["evidence"]}
                if not ids <= allowed or not all(
                    ids & set(snapshot[s]["root_evidence_ids"]) for s in ("source", "target")
                ):
                    raise KnowledgeError("BOTH_SIDES_REQUIRED", "实体判断必须提供双方可回查证据")
                proposal_data = (
                    alignment.decision,
                    alignment.rationale,
                    alignment.evidence_span_ids,
                )
        attempt = ReasoningAttempt(
            id=str(uuid4()),
            project_id=snapshot["project_id"],
            source_id=snapshot["source"]["root_id"],
            target_id=snapshot["target"]["root_id"],
            mode=mode,
            comparison=comparison,
            output=output,
            snapshot=snapshot,
            snapshot_hash=digest(snapshot),
            model_run_ids=run_ids,
            created_at=now(),
        )
        self.session.add(attempt)
        self.session.flush()
        proposal_id = None
        if proposal_data:
            kind, rationale, evidence_ids = proposal_data
            proposal_id = str(uuid4())
            cls = RelationAssertion if mode == "relation" else AlignmentCandidate
            self.session.add(
                cls(
                    id=proposal_id,
                    attempt_id=attempt.id,
                    project_id=attempt.project_id,
                    source_id=attempt.source_id,
                    target_id=attempt.target_id,
                    relation_type=kind,
                    rationale=rationale,
                    evidence_ids=evidence_ids,
                    review_status="proposed",
                    revision=1,
                    created_at=now(),
                )
            )
        revision = self.store.event(
            attempt.project_id,
            "RELATION_INFERRED" if mode == "relation" else "ENTITY_ALIGNMENT_PROPOSED",
            {
                "attempt_id": attempt.id,
                "proposal_id": proposal_id,
                "decision": output,
                "dependencies_hash": attempt.snapshot_hash,
            },
            actor="model",
            model_run_id=run_ids[-1],
            trigger="reasoning",
        )
        result = {"attempt_id": attempt.id, "proposal_id": proposal_id, "graph_revision": revision}
        self.session.add(KnowledgeOperation(key=key, request_hash=request_hash, response=result))
        return result

    def review(self, body: SemanticReviewRequest, key: str) -> ProposalView:
        request_hash = digest(body.model_dump(mode="json"))
        previous = self.session.get(KnowledgeOperation, key)
        if previous:
            if previous.request_hash != request_hash:
                raise KnowledgeError("IDEMPOTENCY_CONFLICT", "审核标识已用于其他请求")
            return ProposalView.model_validate(previous.response)
        proposal = (
            self.session.get(RelationAssertion, body.proposal_id)
            if body.kind == "relation"
            else self.session.get(AlignmentCandidate, body.proposal_id)
        )
        if proposal is None:
            raise KnowledgeError("PROPOSAL_NOT_FOUND", "候选不存在")
        before = proposal_view(self.store, proposal)
        if proposal.revision != body.expected_revision:
            raise KnowledgeError("REVISION_CONFLICT", "候选已更新，请刷新后审核")
        if body.action == "accept" and before.stale:
            raise KnowledgeError("STALE_INPUT", "主张、条件或证据已变化，须重新推理后再接受")
        proposal.review_status = "accepted" if body.action == "accept" else "rejected"
        proposal.revision += 1
        after = proposal_view(self.store, proposal)
        self.session.add(
            SemanticReview(
                id=str(uuid4()),
                relation_id=proposal.id if body.kind == "relation" else None,
                alignment_id=proposal.id if body.kind == "alignment" else None,
                action=body.action,
                reason=body.reason,
                before=before.model_dump(mode="json"),
                after=after.model_dump(mode="json"),
                created_at=now(),
            )
        )
        self.store.event(
            proposal.project_id,
            "SEMANTIC_PROPOSAL_REVIEWED",
            {
                "kind": body.kind,
                "before": before.model_dump(mode="json"),
                "after": after.model_dump(mode="json"),
                "reason": body.reason,
            },
            actor="user",
            trigger="human_review",
        )
        self.session.add(
            KnowledgeOperation(
                key=key, request_hash=request_hash, response=after.model_dump(mode="json")
            )
        )
        return after
