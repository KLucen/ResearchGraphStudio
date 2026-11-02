"""Quarantine invalid navigation suggestions without inventing replacement edges."""

import json
from typing import Any

from pydantic import TypeAdapter

from researchgraph.reading_contracts import (
    Candidate,
    GraphLinkCandidate,
    KnowledgeExtractionBatch,
    check_relation,
)


def validate_batch(
    raw: str, allowed: set[str]
) -> tuple[KnowledgeExtractionBatch, list[dict[str, Any]]]:
    from researchgraph.unified_store import evidence_ids

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Reading batch must be an object")
    # Full field validation precedes the one narrowly allowed quarantine operation.
    items = TypeAdapter(list[Candidate]).validate_python(data.get("items", []))
    if evidence_ids(data) - allowed:
        raise ValueError("Reading output referenced evidence outside the input whitelist")
    kinds = {i.local_ref: i.kind for i in items}
    kept, quarantined = [], []
    for index, raw_edge in enumerate(data.get("links", [])):
        edge = GraphLinkCandidate.model_validate(raw_edge)
        source, target = kinds.get(edge.source_local_ref), kinds.get(edge.target_local_ref)
        try:
            if not source or not target:
                raise ValueError("unknown local reference")
            check_relation(source, target, edge.relation)
        except ValueError:
            quarantined.append(
                {
                    "index": index,
                    "source_kind": source,
                    "target_kind": target,
                    "relation": edge.relation,
                    "reason": "invalid_endpoint_types_or_reference",
                }
            )
        else:
            kept.append(raw_edge)
    if quarantined:
        data = {
            **data,
            "links": kept,
            "warnings": [
                *data.get("warnings", []),
                f"{len(quarantined)} 条模型关联未通过端点规则，已隔离；候选和原始响应保留",
            ],
        }
    return KnowledgeExtractionBatch.model_validate(data), quarantined
