"""Bounded, project-scoped retrieval and current source/condition snapshots."""

import re
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from researchgraph.graph_models import SourceAssertion
from researchgraph.knowledge_contracts import EvidenceView, NodeView
from researchgraph.knowledge_models import (
    EvidenceSpan,
    KnowledgeDependency,
    KnowledgeNode,
    NodeEvidence,
)
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest, validate_evidence
from researchgraph.models import Paper
from researchgraph.reasoning_contracts import CandidateList, CandidateRequest


def usable(node: KnowledgeNode) -> bool:
    return (
        node.review_status not in {"rejected", "superseded"}
        and "new_document_version_available" not in node.issues
    )


def require_node(session: Session, node_id: str) -> KnowledgeNode:
    node = session.get(KnowledgeNode, node_id)
    if node is None:
        raise KnowledgeError("NODE_NOT_FOUND", "知识节点不存在")
    if node.kind not in {"claim", "concept", "method"} or not usable(node):
        raise KnowledgeError("NODE_NOT_ELIGIBLE", "请选择当前来源版本且未驳回的主张、概念或方法")
    return node


def candidates(session: Session, body: CandidateRequest) -> CandidateList:
    source = require_node(session, body.source_id)
    paper = session.get(Paper, source.paper_id)
    assert paper
    stop = {
        "the",
        "and",
        "that",
        "with",
        "from",
        "this",
        "have",
        "their",
        "which",
        "for",
        "are",
        "was",
        "were",
        "has",
        "our",
        "can",
        "not",
        "authors",
    }
    terms = list(
        dict.fromkeys(
            t.lower()
            for t in re.findall(r"[\w]+", body.query or source.text)
            if len(t) > 2 and t.lower() not in stop
        )
    )[:16]
    ids = []
    if terms:
        ids = list(
            session.scalars(
                text("""SELECT n.id FROM knowledge_fts f
            JOIN knowledge_nodes n ON n.id=f.node_id JOIN papers p ON p.id=n.paper_id
            WHERE knowledge_fts MATCH :query AND p.project_id=:project AND n.paper_id != :paper
            AND n.kind=:kind AND n.review_status NOT IN ('rejected','superseded')
            AND (:include_test OR n.revision>1 OR n.review_status='accepted' OR NOT EXISTS
                (SELECT 1 FROM model_runs m WHERE m.id=n.model_run_id AND m.provider='mock'))
            ORDER BY bm25(knowledge_fts), n.id LIMIT :limit"""),
                {
                    "query": " OR ".join('"' + t + '"' for t in terms),
                    "project": paper.project_id,
                    "paper": paper.id,
                    "kind": source.kind,
                    "include_test": body.include_test_data,
                    "limit": body.top_k * 5,
                },
            )
        )
    nodes = [session.get(KnowledgeNode, i) for i in ids]
    return CandidateList(
        items=[NodeView.model_validate(n) for n in nodes if n and usable(n)][: body.top_k],
        graph_revision=KnowledgeStore(session).graph_revision(paper.project_id),
    )


def node_context(session: Session, node: KnowledgeNode) -> dict[str, Any]:
    nodes = {node.id: node}
    links = []
    frontier = {node.id}
    # Conditions/methods/experiment context are current nodes, never stale embedded DTOs.
    for _ in range(3):
        next_ids = set()
        for association in session.scalars(
            select(SourceAssertion).where(SourceAssertion.source_id.in_(frontier))
        ):
            dependency = session.get(KnowledgeNode, association.target_id)
            if not dependency or dependency.document_version_id != node.document_version_id:
                raise KnowledgeError("INVALID_DEPENDENCY", "关联超出当前来源版本")
            if not usable(dependency):
                raise KnowledgeError("INVALID_DEPENDENCY", "关联来源已失效")
            links.append([association.source_id, association.target_id, association.relation])
            if dependency.id not in nodes:
                nodes[dependency.id] = dependency
                next_ids.add(dependency.id)
        for edge in session.scalars(
            select(KnowledgeDependency)
            .where(KnowledgeDependency.node_id.in_(frontier))
            .order_by(KnowledgeDependency.dependee_id, KnowledgeDependency.role)
        ):
            links.append([edge.node_id, edge.dependee_id, edge.role])
            if edge.dependee_id not in nodes:
                dependency = session.get(KnowledgeNode, edge.dependee_id)
                if (
                    dependency is None
                    or dependency.document_version_id != node.document_version_id
                    or not usable(dependency)
                ):
                    raise KnowledgeError(
                        "INVALID_DEPENDENCY", "实验或条件依赖已失效，请先修订源知识"
                    )
                nodes[dependency.id] = dependency
                next_ids.add(dependency.id)
        frontier = next_ids
        if not frontier:
            break
    if len(nodes) > 100:
        raise KnowledgeError("CONTEXT_TOO_LARGE", "该节点实验上下文超过 100 项限制")
    evidence = {}
    root_evidence = []
    for link in session.scalars(
        select(NodeEvidence)
        .where(NodeEvidence.node_id.in_(nodes))
        .order_by(NodeEvidence.evidence_id)
    ):
        span = session.get(EvidenceSpan, link.evidence_id)
        if span is None:
            raise KnowledgeError("UNKNOWN_EVIDENCE", "节点证据不存在")
        validate_evidence(session, span, node.document_version_id)
        evidence[span.id] = EvidenceView.model_validate(span).model_dump(mode="json")
        if link.node_id == node.id:
            root_evidence.append(span.id)
    if not root_evidence:
        raise KnowledgeError("NEEDS_EVIDENCE", "主张或实体没有可回查原文")
    dimensions: dict[str, dict[str, Any]] = {}
    conditions = [n for n in nodes.values() if n.kind == "condition"]
    defaults = set() if "label" in node.payload else {"task_type", "dataset", "metric"}
    for name in sorted(defaults | {n.dimension for n in conditions if n.dimension}):
        values = [n for n in conditions if n.dimension == name]
        # An absent Claim condition does not contradict explicit experiment context.
        # Only values already stored with provenance may supply the missing dimension.
        signatures = {
            (n.known_state, n.value, n.unit) for n in values if n.known_state != "unknown"
        }
        state, value, unit = (
            next(iter(signatures))
            if len(signatures) == 1
            else ("conflicting" if signatures else "unknown", None, None)
        )
        dimensions[name] = {"known_state": state, "value": value, "unit": unit}
    return {
        "root_id": node.id,
        "nodes": [NodeView.model_validate(nodes[i]).model_dump(mode="json") for i in sorted(nodes)],
        "dependencies": sorted(links),
        "dimensions": dimensions,
        "root_evidence_ids": sorted(set(root_evidence)),
        "evidence": [evidence[i] for i in sorted(evidence)],
    }


def pair_context(session: Session, source_id: str, target_id: str, mode: str) -> dict[str, Any]:
    a, b = require_node(session, source_id), require_node(session, target_id)
    pa, pb = session.get(Paper, a.paper_id), session.get(Paper, b.paper_id)
    assert pa and pb
    if pa.project_id != pb.project_id or pa.id == pb.id:
        raise KnowledgeError("PAIR_SCOPE_MISMATCH", "只允许同项目的不同论文进行比较")
    if (mode == "relation" and (a.kind != "claim" or b.kind != "claim")) or (
        mode == "alignment" and (a.kind not in {"concept", "method"} or a.kind != b.kind)
    ):
        raise KnowledgeError("PAIR_KIND_MISMATCH", "关系需要两条主张；实体对齐需要同类概念或方法")
    context: dict[str, Any] = {
        "project_id": pa.project_id,
        "source": node_context(session, a),
        "target": node_context(session, b),
    }
    if (
        sum(len(e["quote"]) for side in ("source", "target") for e in context[side]["evidence"])
        > 48000
    ):
        raise KnowledgeError(
            "CONTEXT_TOO_LARGE", "证据上下文超过 48000 字符，请选择范围更小的知识节点"
        )
    return context


def current_hash(session: Session, snapshot: dict[str, Any], mode: str) -> str | None:
    try:
        return digest(
            pair_context(
                session, snapshot["source"]["root_id"], snapshot["target"]["root_id"], mode
            )
        )
    except KnowledgeError:
        return None


def model_context(snapshot: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Short references have a frozen manifest; full audit snapshots stay in SQLite."""
    spans = {e["id"]: e for side in ("source", "target") for e in snapshot[side]["evidence"]}
    aliases = {f"ev{i + 1:04d}": key for i, key in enumerate(sorted(spans))}
    reverse = {value: key for key, value in aliases.items()}
    data: dict[str, Any] = {
        "allowed_evidence_ids": list(aliases),
        "evidence_texts": [
            {"id": alias, "quote": spans[key]["quote"]} for alias, key in aliases.items()
        ],
    }
    for side, name in (("source", "claim_a"), ("target", "claim_b")):
        context = snapshot[side]
        node = next(n for n in context["nodes"] if n["id"] == context["root_id"])
        data[name] = {
            "id": node["id"],
            "text": node["text"],
            "origin": node["origin"],
            "review_status": node["review_status"],
            "dimensions": context["dimensions"],
            "evidence_ids": [reverse[i] for i in context["root_evidence_ids"]],
            "context": [
                {
                    "kind": n["kind"],
                    "text": n["text"],
                    "value": n["value"],
                    "unit": n["unit"],
                    "known_state": n["known_state"],
                }
                for n in context["nodes"]
                if n["id"] != node["id"]
            ],
        }
    return data, aliases
