"""Deterministic support closure over explicit, source-validated reading paths."""

from collections import deque
from typing import Any

from sqlalchemy import select

from researchgraph.graph_models import SourceAssertion
from researchgraph.knowledge_models import (
    EvidenceSpan,
    KnowledgeDependency,
    KnowledgeNode,
    NodeEvidence,
)
from researchgraph.knowledge_store import KnowledgeError, validate_evidence
from researchgraph.reading_contracts import check_relation
from researchgraph.reading_store import ReadingMutations
from researchgraph.unified_store import evidence_ids


def valid_support_node(store: ReadingMutations, version_id: str, node: KnowledgeNode) -> bool:
    """Check identity and every link, including dangling NodeEvidence rows."""
    _, paper = store.source(version_id)
    kind = "ResearchQuestion" if node.kind == "research_question" else node.kind.title()
    linked = set(
        store.session.scalars(
            select(NodeEvidence.evidence_id).where(NodeEvidence.node_id == node.id)
        )
    )
    if (
        node.document_version_id != version_id
        or node.paper_id != paper.id
        or node.payload.get("kind") != kind
        or not linked
        or evidence_ids(node.payload) - linked
        or not store.source_valid(node)
    ):
        return False
    try:
        for eid in linked:
            span = store.session.get(EvidenceSpan, eid)
            if span is None:
                return False
            validate_evidence(store.session, span, version_id)
    except KnowledgeError:
        return False
    return True


def support_context(
    store: ReadingMutations, version_id: str, nodes: dict[str, KnowledgeNode]
) -> dict[str, Any]:
    """Engine-owned relation manifest; never added to the model transport."""
    nodes = {
        nid: node for nid, node in nodes.items() if valid_support_node(store, version_id, node)
    }
    return {
        "policy": "reading-support-context-1",
        "document_version_id": version_id,
        "assertions": [
            [e.id, e.project_id, e.source_id, e.target_id, e.relation, sorted(e.evidence_ids)]
            for e in store.session.scalars(
                select(SourceAssertion)
                .where(SourceAssertion.source_id.in_(nodes), SourceAssertion.target_id.in_(nodes))
                .order_by(SourceAssertion.id)
            )
        ],
        "dependencies": sorted(
            [d.node_id, d.dependee_id, d.role]
            for d in store.session.scalars(
                select(KnowledgeDependency).where(
                    KnowledgeDependency.node_id.in_(nodes),
                    KnowledgeDependency.dependee_id.in_(nodes),
                )
            )
        ),
    }


def support_paths(
    store: ReadingMutations,
    version_id: str,
    nodes: dict[str, KnowledgeNode],
    *,
    prevalidated: bool = False,
) -> list[tuple[str, str, str]]:
    """Never infer membership from shared evidence or proximity in the paper."""
    _, paper = store.source(version_id)
    # Query's eligible_nodes has already checked every endpoint, link, source and
    # payload in bulk in this transaction. Other callers retain full validation.
    valid = (
        set(nodes)
        if prevalidated
        else {nid for nid, node in nodes.items() if valid_support_node(store, version_id, node)}
    )
    paths = []
    for edge in store.session.scalars(
        select(SourceAssertion)
        .where(SourceAssertion.source_id.in_(valid), SourceAssertion.target_id.in_(valid))
        .order_by(SourceAssertion.id)
    ):
        if not edge.evidence_ids or edge.project_id != paper.project_id:
            continue
        left, right = nodes[edge.source_id], nodes[edge.target_id]
        try:
            check_relation(
                "ResearchQuestion" if left.kind == "research_question" else left.kind.title(),
                "ResearchQuestion" if right.kind == "research_question" else right.kind.title(),
                edge.relation,
            )
            for eid in edge.evidence_ids:
                span = store.session.get(EvidenceSpan, eid)
                if span is None:
                    raise KnowledgeError("EVIDENCE_REF_INVALID", "关联证据不存在")
                validate_evidence(store.session, span, version_id)
        except (KnowledgeError, KeyError, ValueError):
            continue
        paths.append((edge.source_id, edge.target_id, edge.id))
    # Dependencies already carry explicit membership semantics; their endpoints must
    # still be current reading candidates with valid evidence in the same version.
    dependency_types = {
        "USES_METHOD": ({"claim", "experiment"}, {"method"}),
        "IN_EXPERIMENT": ({"claim", "finding"}, {"experiment"}),
        "HAS_CONDITION": ({"claim", "experiment"}, {"condition"}),
        "MEASURES": ({"finding"}, {"metric"}),
    }
    for d in store.session.scalars(
        select(KnowledgeDependency).where(
            KnowledgeDependency.node_id.in_(valid), KnowledgeDependency.dependee_id.in_(valid)
        )
    ):
        allowed = dependency_types.get(d.role)
        if (
            allowed
            and nodes[d.node_id].kind in allowed[0]
            and nodes[d.dependee_id].kind in allowed[1]
        ):
            paths.append(
                (d.node_id, d.dependee_id, f"dependency:{d.node_id}:{d.dependee_id}:{d.role}")
            )
    return sorted(set(paths))


def validate_member_paths(
    store: ReadingMutations,
    version_id: str,
    root: str,
    members: list[tuple[str, list[str]]],
    nodes: dict[str, KnowledgeNode],
    paths: list[tuple[str, str, str]],
) -> None:
    """Revalidate persisted full paths rather than trusting an input hash."""
    if (
        root not in nodes
        or nodes[root].kind != "claim"
        or not valid_support_node(store, version_id, nodes[root])
    ):
        raise KnowledgeError("SUPPORT_CONTEXT_CHANGED", "结论来源或类型已变化，请创建新构建")
    by_id = {aid: (source, target) for source, target, aid in paths}
    seen_members: set[str] = set()
    for member, associations in members:
        if (
            member in seen_members
            or member == root
            or not isinstance(associations, list)
            or not associations
            or any(not isinstance(aid, str) for aid in associations)
        ):
            raise KnowledgeError("SUPPORT_CONTEXT_CHANGED", "结论支撑成员或路径不合法")
        seen_members.add(member)
        cursor, visited = root, {root}
        for aid in associations:
            edge = by_id.get(aid)
            if (
                edge is None
                or edge[0] != cursor
                or edge[1] in visited
                or nodes[edge[1]].kind == "claim"
            ):
                raise KnowledgeError("SUPPORT_CONTEXT_CHANGED", "结论支撑路径已变化，请创建新构建")
            cursor = edge[1]
            visited.add(cursor)
        if cursor != member:
            raise KnowledgeError("SUPPORT_CONTEXT_CHANGED", "结论支撑路径未到达成员")


def reachable_supports(
    root: str, nodes: dict[str, KnowledgeNode], paths: list[tuple[str, str, str]]
) -> dict[str, list[str]]:
    """Return shortest deterministic paths without crossing another Claim."""
    outgoing: dict[str, list[tuple[str, str]]] = {}
    for source, target, association in paths:
        if nodes[target].kind != "claim":
            outgoing.setdefault(source, []).append((target, association))
    reached: dict[str, list[str]] = {root: []}
    pending = deque([root])
    while pending:
        source = pending.popleft()
        for target, association in outgoing.get(source, []):
            if target not in reached:
                reached[target] = [*reached[source], association]
                pending.append(target)
    return reached
