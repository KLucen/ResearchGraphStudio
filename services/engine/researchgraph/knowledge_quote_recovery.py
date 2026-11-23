"""Isolate unverifiable quotes from a complete legacy knowledge draft."""

import json
from typing import Any

from researchgraph.core import KnowledgeError
from researchgraph.paper_knowledge import (
    KnowledgeDraft,
    KnowledgeEdge,
    KnowledgeNode,
    _quote_offset,
)
from researchgraph.paper_overview_contracts import PaperCard, strict_json


def _first_bad_quote(item: KnowledgeNode | KnowledgeEdge, sources: dict[str, str]) -> int | None:
    first = None
    seen: set[tuple[str, str, int]] = set()
    for index, ref in enumerate(item.source_refs):
        text = sources.get(ref.source_id)
        if text is None:
            raise KnowledgeError("KNOWLEDGE_SOURCE_REF_INVALID", "知识图谱引用了请求之外的来源")
        identity = (ref.source_id, ref.quote, ref.occurrence_index)
        if identity in seen:
            raise KnowledgeError("KNOWLEDGE_SOURCE_REF_DUPLICATE", "同一知识对象含重复引文")
        seen.add(identity)
        if ref.quote.strip():
            try:
                _quote_offset(text, ref.quote, ref.occurrence_index)
                continue
            except KnowledgeError:
                pass
        if first is None:
            first = index
    return first


def isolate_unmatched_quotes(
    raw: str, manifest: dict[str, Any]
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Only quote mismatches and their incident edges may be isolated."""
    draft = KnowledgeDraft.model_validate(strict_json(raw), strict=True)
    texts = {source["ref"]: source["text"] for source in manifest["sources"]}
    node_types = {node.id: node.type for node in draft.graph.nodes}
    good_nodes, good_edges = [], []
    excluded_nodes, excluded_edges = [], []
    removed_ids: set[str] = set()
    quote_reason = "引文无法在本次指定的解析原文位置核验。"
    for index, node in enumerate(draft.graph.nodes):
        bad_quote = _first_bad_quote(node, texts)
        if bad_quote is None:
            good_nodes.append(node)
            continue
        removed_ids.add(node.id)
        excluded_nodes.append(
            {
                "index": index,
                "path": f"graph.nodes[{index}].source_refs[{bad_quote}].quote",
                "code": "quote_mismatch",
                "node_type": node.type,
                "reason": quote_reason,
            }
        )
    for index, edge in enumerate(draft.graph.edges):
        bad_quote = _first_bad_quote(edge, texts)
        if bad_quote is None and edge.source not in removed_ids and edge.target not in removed_ids:
            good_edges.append(edge)
            continue
        path = f"graph.edges[{index}]"
        excluded_edges.append(
            {
                "index": index,
                "path": path if bad_quote is None else f"{path}.source_refs[{bad_quote}].quote",
                "code": "depends_on_excluded_node" if bad_quote is None else "quote_mismatch",
                "relation_type": edge.type,
                "source_type": node_types[edge.source],
                "target_type": node_types[edge.target],
                "message": "该关系依赖未通过引文校验的节点。"
                if bad_quote is None
                else quote_reason,
            }
        )
    if not good_nodes or not (excluded_nodes or excluded_edges):
        raise KnowledgeError(
            "KNOWLEDGE_LOCAL_RECOVERY_UNAVAILABLE", "引文隔离后没有可发布的知识，或未发现引文不匹配"
        )
    # The free-form overview does not map its claims to individual graph nodes.
    card = PaperCard(
        research_question="",
        motivation="",
        method_summary="",
        contributions=[],
        main_findings=[],
        limitations=[],
    )
    result = {
        "schema_version": draft.schema_version,
        "paper_card": card.model_dump(),
        "graph": {
            "nodes": [node.model_dump() for node in good_nodes],
            "edges": [edge.model_dump() for edge in good_edges],
        },
    }
    return json.dumps(result, ensure_ascii=False), excluded_nodes, excluded_edges
