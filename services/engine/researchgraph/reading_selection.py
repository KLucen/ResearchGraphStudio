"""Validated unit paths and compare-and-swap publication, independent of layout."""

import re
from typing import Any

from sqlalchemy import select

from researchgraph.graph_models import SourceAssertion
from researchgraph.knowledge_models import EvidenceSpan, NodeEvidence
from researchgraph.knowledge_store import KnowledgeError, digest, stable_id, validate_evidence
from researchgraph.models import now
from researchgraph.reading_contracts import (
    CoreSelectionProposal,
    PaperIntegrationProposal,
    check_relation,
)
from researchgraph.reading_models import (
    CandidateMetadata,
    ReadingHead,
    ReadingMember,
    ReadingPreference,
    ReadingSelection,
    ReadingUnit,
)
from researchgraph.reading_scope import SCOPE
from researchgraph.reading_store import POLICY, ReadingMutations
from researchgraph.reading_support import reachable_supports, support_paths, validate_member_paths

FRAGMENT_EVIDENCE_REASON = "引用仅含公式/标记碎片，缺少可解释原文上下文"


def _fragment_only(text: str) -> bool:
    """Recognize only obvious marker-only quotes, never scientific entailment.

    A word or a short CJK phrase is enough to leave this conservative filter.
    Formulae remain valid evidence when any cited span also supplies readable
    context. There is no source truncation or minimum paragraph size.
    """
    text = re.sub(r"\\(?:begin|end)\s*\{[^{}]*\}", " ", text)
    text = re.sub(r"\\[A-Za-z]+\*?", " ", text)
    return not any(len(word) > 1 for word in re.findall(r"[^\W\d_]+", text))


def _fragment_claim(store: ReadingMutations, node_id: str) -> bool:
    quotes = list(
        store.session.scalars(
            select(EvidenceSpan.quote)
            .join(NodeEvidence, NodeEvidence.evidence_id == EvidenceSpan.id)
            .where(NodeEvidence.node_id == node_id)
        )
    )
    return bool(quotes) and all(_fragment_only(quote) for quote in quotes)


def integrate(
    store: ReadingMutations,
    *,
    proposal: dict[str, Any],
    version_id: str,
    snapshot: str,
    run_id: str,
    key: str,
) -> dict[str, Any]:
    value = PaperIntegrationProposal.model_validate(proposal)
    fingerprint = digest([proposal, snapshot])
    cached = store.checkpoint(key, fingerprint)
    if cached is not None:
        return cached
    _, paper = store.source(version_id)
    run = store.require_run(run_id, version_id)
    if (
        value.document_version_id != version_id
        or store.snapshot(version_id) != snapshot
        or value.input_revision != int(snapshot[:12], 16)
    ):
        raise KnowledgeError("INTEGRATION_CONTEXT_STALE", "候选快照已改变")
    nodes = {n.id: n for n in store.nodes(version_id)}
    integration_warnings = list(value.warnings)
    references = {i for u in value.units for i in [u.root_claim_id, *u.member_ids]}
    references.update(i for a in value.associations for i in [a.source_id, a.target_id])
    references.update(i for d in value.duplicates for i in d.candidate_ids)
    if references - nodes.keys():
        raise KnowledgeError("UNKNOWN_CANDIDATE", "整合引用了其他文献或不存在的候选")
    quarantined: list[dict[str, Any]] = []
    for index, edge in enumerate(value.associations):
        left, right = nodes[edge.source_id], nodes[edge.target_id]
        for eid in edge.evidence_ids:
            span = store.session.get(EvidenceSpan, eid)
            if span is None:
                raise KnowledgeError("EVIDENCE_REF_INVALID", "整合证据不存在")
            validate_evidence(store.session, span, version_id)
        try:
            check_relation(
                "ResearchQuestion" if left.kind == "research_question" else left.kind.title(),
                "ResearchQuestion" if right.kind == "research_question" else right.kind.title(),
                edge.relation,
            )
        except ValueError:
            quarantined.append({"index": index, "reason": "invalid_endpoint_types"})
            continue
        aid = stable_id(
            "reading-association",
            digest(
                [
                    edge.source_id,
                    edge.target_id,
                    edge.relation,
                    sorted(edge.evidence_ids),
                ]
            ),
        )
        if not store.session.get(SourceAssertion, aid):
            store.session.add(
                SourceAssertion(
                    id=aid,
                    project_id=paper.project_id,
                    source_id=edge.source_id,
                    target_id=edge.target_id,
                    relation=edge.relation,
                    evidence_ids=edge.evidence_ids,
                    model_run_id=run_id,
                )
            )
    if quarantined:
        integration_warnings.append(
            f"{len(quarantined)} 条整合关联不符合端点类型，已隔离；未改写关系"
        )
        run.parameters = {**run.parameters, "quarantined_integration_associations": quarantined}
    store.session.flush()
    associations = list(
        store.session.scalars(
            select(SourceAssertion).where(
                SourceAssertion.source_id.in_(nodes),
                SourceAssertion.target_id.in_(nodes),
            )
        )
    )
    paths = support_paths(store, version_id, nodes)
    unit_ids = []
    for unit in value.units:
        if nodes[unit.root_claim_id].kind != "claim":
            raise KnowledgeError("INVALID_UNIT_ROOT", "结论单元必须以 Claim 为根")
        reached = reachable_supports(unit.root_claim_id, nodes, paths)
        unreachable = set(unit.member_ids) - reached.keys()
        if unreachable:
            integration_warnings.append(
                f"结论单元有 {len(unreachable)} 个成员缺少关联路径，已保留为可检索候选"
            )
        uid = stable_id("reading-unit", digest([snapshot, unit.model_dump(), reached]))
        if not store.session.get(ReadingUnit, uid):
            store.session.add(
                ReadingUnit(
                    id=uid,
                    document_version_id=version_id,
                    root_claim_id=unit.root_claim_id,
                    snapshot_hash=snapshot,
                    model_run_id=run_id,
                    rationale=unit.rationale,
                )
            )
            store.session.flush()
            for mid in sorted(reached):
                if mid == unit.root_claim_id:
                    continue
                store.session.add(
                    ReadingMember(unit_id=uid, node_id=mid, association_ids=reached[mid])
                )
        unit_ids.append(uid)
    store.adapt(version_id)
    # A duplicate suggestion affects visibility only. It cannot delete/merge source objects.
    rejected_duplicates: list[dict[str, Any]] = []
    for index, duplicate in enumerate(value.duplicates):
        roots = [nodes[i] for i in duplicate.candidate_ids]
        signatures = {(n.kind, n.authorship, n.payload.get("modality")) for n in roots}
        conditions = {
            n.id: sorted(
                a.target_id
                for a in associations
                if a.source_id == n.id and a.relation in {"HAS_CONDITION", "SUPPORTED_BY"}
            )
            for n in roots
        }
        if len(signatures) != 1 or len({tuple(c) for c in conditions.values()}) != 1:
            rejected_duplicates.append({"index": index, "reason": "scope_or_attribution_conflict"})
            integration_warnings.append("重复建议涉及不同归属或条件，已拒绝折叠；候选独立保留")
            continue
        for node in roots:
            metadata = store.session.get(CandidateMetadata, node.id)
            assert metadata
            if node.id != duplicate.representative_id:
                metadata.canonical_id = duplicate.representative_id
    if rejected_duplicates:
        run.parameters = {**run.parameters, "rejected_integration_duplicates": rejected_duplicates}
    response = {"unit_ids": unit_ids, "warnings": integration_warnings}
    store.store.event(
        paper.project_id, "paper.integration_committed", response, model_run_id=run_id
    )
    return store.save_checkpoint(key, version_id, "integrating", fingerprint, response)


def publish(
    store: ReadingMutations,
    *,
    version_id: str,
    snapshot: str,
    unit_ids: list[str],
    proposal: dict[str, Any],
    density: str,
    expected_revision: int,
    key: str,
    selection_mode: str = "ranked",
    contribution_order: list[str] | None = None,
) -> dict[str, Any]:
    hint = CoreSelectionProposal.model_validate(proposal)
    identity = [version_id, snapshot, unit_ids, proposal, density, expected_revision]
    if selection_mode != "ranked":
        identity.append(selection_mode)
    if contribution_order is not None:
        identity.append({"contribution_order": contribution_order})
    fingerprint = digest(identity)
    cached = store.checkpoint(key, fingerprint)
    _, paper = store.source(version_id)
    current = store.current(paper.id)
    if cached is None and (current.revision if current else 0) != expected_revision:
        raise KnowledgeError("SELECTION_REVISION_CONFLICT", "选择已更新，请刷新后再试")
    if (
        store.snapshot(version_id) != snapshot
        or hint.document_version_id != version_id
        or hint.input_revision != int(snapshot[:12], 16)
    ):
        raise KnowledgeError("INTEGRATION_CONTEXT_STALE", "候选或来源已改变，请重新整合")
    if density not in {"concise", "standard", "detailed"}:
        raise KnowledgeError("INVALID_DENSITY", "未知图谱密度")
    if selection_mode not in {"ranked", "provisional"}:
        raise KnowledgeError("INVALID_SELECTION_MODE", "未知选择模式")
    nodes = {n.id: n for n in store.nodes(version_id)}
    units: dict[str, ReadingUnit] = {}
    for uid in unit_ids:
        unit = store.session.get(ReadingUnit, uid)
        if not unit or unit.document_version_id != version_id or unit.snapshot_hash != snapshot:
            raise KnowledgeError("INVALID_UNIT", "结论单元不属于当前快照")
        if unit.root_claim_id in units:
            raise KnowledgeError("DUPLICATE_UNIT", "结论存在多个单元")
        units[unit.root_claim_id] = unit
    paths = support_paths(store, version_id, nodes)
    unit_members = {
        unit.id: list(
            store.session.scalars(select(ReadingMember).where(ReadingMember.unit_id == unit.id))
        )
        for unit in units.values()
    }
    for root, unit in units.items():
        validate_member_paths(
            store,
            version_id,
            root,
            [(m.node_id, m.association_ids) for m in unit_members[unit.id]],
            nodes,
            paths,
        )
    if cached is not None:
        if any(
            entry["graph_role"] == "core" and _fragment_claim(store, entry["candidate_id"])
            for entry in cached["entries"]
        ):
            raise KnowledgeError("CORE_EVIDENCE_CONTEXT_REQUIRED", FRAGMENT_EVIDENCE_REASON)
        return cached
    hints = {h.root_claim_id: h for h in hint.recommendations}
    if set(hints) != set(units):
        raise KnowledgeError("SELECTION_INCOMPLETE", "选择必须逐一说明所有结论单元")
    if contribution_order is not None and (
        len(contribution_order) != len(units) or set(contribution_order) != set(units)
    ):
        raise KnowledgeError("INVALID_CONTRIBUTION_ORDER", "贡献排序必须唯一覆盖全部结论单元")
    ranks = (
        {root: index for index, root in enumerate(contribution_order, 1)}
        if contribution_order is not None
        else {}
    )
    store.adapt(version_id)
    entries: dict[str, dict[str, Any]] = {
        nid: {
            "candidate_id": nid,
            "graph_role": "retrieval_only",
            "selected_by": "automatic",
            "reason": "未选入主图；候选与证据保留",
        }
        for nid in nodes
    }
    selected = []
    gaps = list(hint.coverage_gaps)
    for root in contribution_order if contribution_order is not None else units:
        unit = units[root]
        node = nodes[root]
        metadata = store.session.get(CandidateMetadata, root)
        preference = store.session.get(ReadingPreference, root)
        assert metadata
        h = hints[root]
        members = unit_members[unit.id]
        caveats = list(
            dict.fromkeys(
                [
                    *node.issues,
                    *(
                        f"支撑 {member.node_id}：{issue}"
                        for member in members
                        for issue in nodes[member.node_id].issues
                    ),
                ]
            )
        )
        blocked = []
        if not store.source_valid(node) or any(
            not store.source_valid(nodes[m.node_id]) for m in members
        ):
            blocked.append("来源或历史状态不允许主图展示")
        if (
            node.authorship not in {"paper_author", "author"}
            or node.origin
            in {
                "cited_claim",
                "background",
                "unknown",
            }
            or node.payload.get("origin")
            in {"citation_report", "cited_claim", "background", "unknown"}
        ):
            blocked.append("转述或未知归属不是本文结论")
        if metadata.canonical_id:
            blocked.append("已有同范围结论代表")
        fragment_evidence = _fragment_claim(store, root)
        if fragment_evidence:
            blocked.append(FRAGMENT_EVIDENCE_REASON)
        if selection_mode == "provisional" and (
            node.payload.get("contribution_type") in {None, "background"}
            or node.payload.get("modality") in {"speculative", "unknown"}
            or node.issues
        ):
            blocked.append("自动贡献排序尚未完成，暂不展示背景、归属不明或有未解疑点的结论")
        if not members:
            caveats.append("仅有直接原文依据，尚无独立支撑成员")
        if h.recommendation == "needs_context":
            blocked.append("证据上下文不足")
        relevance = (
            "unresolved"
            if selection_mode == "provisional"
            else "main_contribution"
            if h.recommendation == "suggest_core"
            else "context"
        )
        metadata.quality = {
            "relevance": relevance,
            "evidence_completeness": (
                "insufficient"
                if fragment_evidence
                or h.recommendation == "needs_context"
                or "insufficient_support" in h.reasons
                else "limited"
                if caveats
                else "sufficient"
            ),
            "duplicate_status": "duplicate" if metadata.canonical_id else "distinct",
            "blocking_issues": blocked,
            "caveats": caveats,
            "rationale": h.rationale,
            "assessed_by": "rules" if selection_mode == "provisional" else "model_assisted",
            "policy_version": POLICY,
        }
        include = h.recommendation == "suggest_core"
        if density == "concise":
            include = include and bool(
                set(h.reasons) & {"main_contribution", "necessary_limitation", "negative_result"}
            )
        if density == "detailed":
            include = include or "answers_paper_question" in h.reasons
        if preference:
            if preference.action == "include_core":
                include = True
            elif preference.action == "exclude_core":
                include = False
        if blocked:
            include = False
        entries[root]["reason"] = "；".join(blocked) if blocked else h.rationale
        if ranks:
            entries[root]["contribution_rank"] = ranks[root]
        if not include:
            continue
        entries[root].update(
            graph_role="core",
            selected_by=(
                "user_preference"
                if preference and preference.action == "include_core"
                else "automatic"
            ),
        )
        member_data = []
        for member in members:
            entries[member.node_id].update(graph_role="supporting", reason="核心结论的有据支撑")
            member_data.append(
                {"member_id": member.node_id, "association_ids": member.association_ids}
            )
        selected.append(
            {
                "id": unit.id,
                "root_claim_id": root,
                "memberships": member_data,
                "rationale": unit.rationale,
                "caveats": caveats,
                **({"contribution_rank": ranks[root]} if ranks else {}),
            }
        )
    if not selected:
        gaps.append("没有满足自动门槛的核心结论；候选仍可检索")
    revision = expected_revision + 1
    sid = stable_id("reading-selection", digest([paper.id, revision, fingerprint]))
    data = {
        "candidate_scope": SCOPE,
        "contract_version": "reading-selection-1.0",
        "id": sid,
        "paper_id": paper.id,
        "document_version_id": version_id,
        "selection_revision": revision,
        "knowledge_revision": store.store.graph_revision(paper.project_id),
        "density": density,
        "policy_version": POLICY,
        "build_state": "partial" if gaps else "complete",
        "coverage_gaps": list(dict.fromkeys(gaps)),
        "entries": list(entries.values()),
        "units": selected,
        "integration_unit_ids": unit_ids,
        "selection_proposal": proposal,
    }
    if selection_mode == "provisional":
        data.update(selection_mode="provisional", ranking_status="pending", build_state="partial")
    if contribution_order is not None:
        data["contribution_order"] = list(contribution_order)
    store.session.add(
        ReadingSelection(
            id=sid,
            paper_id=paper.id,
            document_version_id=version_id,
            revision=revision,
            snapshot_hash=snapshot,
            data=data,
            created_at=now(),
        )
    )
    store.session.flush()
    head = store.session.get(ReadingHead, paper.id)
    if head:
        head.selection_id, head.revision = sid, revision
    else:
        store.session.add(ReadingHead(paper_id=paper.id, selection_id=sid, revision=revision))
    store.store.event(
        paper.project_id,
        "graph.selection_published",
        {
            "selection_id": sid,
            "selection_revision": revision,
            "build_state": data["build_state"],
        },
    )
    return store.save_checkpoint(key, version_id, "publishing", fingerprint, data)
