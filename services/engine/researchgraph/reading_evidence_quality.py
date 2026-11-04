"""Read-only typographic cautions, never a replacement for immutable evidence."""

import math
from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

from researchgraph.document_structure import SCHEMA, current_structure
from researchgraph.knowledge_models import EvidenceSpan
from researchgraph.knowledge_store import KnowledgeError, validate_evidence
from researchgraph.models import AttachmentRevision, Chunk

POLICY = "reading-layout-context-1"


def _box(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(type(v) in {int, float} and math.isfinite(v) for v in value)
        and value[0] <= value[2]
        and value[1] <= value[3]
    )


def _risk_lines(block: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Return raw risky lines, or unknown when rich layout cannot be checked."""
    lines = block.get("lines")
    if not isinstance(lines, list) or not lines:
        return None
    result = []
    for line in lines:
        if not isinstance(line, dict) or not _box(line.get("bbox")):
            return None
        spans = line.get("spans")
        if not isinstance(spans, list) or not spans:
            return None
        for span in spans:
            if (
                not isinstance(span, dict)
                or not isinstance(span.get("text"), str)
                or type(span.get("size")) not in {int, float}
                or not math.isfinite(span["size"])
                or span["size"] <= 0
                or not _box(span.get("bbox"))
            ):
                return None
        if line.get("text") != "".join(span["text"] for span in spans):
            return None
        visible = [(index, span) for index, span in enumerate(spans) if span["text"].strip()]
        pairs = []
        for (left_index, left), (right_index, right) in zip(visible[:-1], visible[1:], strict=True):
            # Adjacency is local to a stored line, never inferred across pages.
            if not (left["text"].rstrip()[-1].isdigit() or right["text"].lstrip()[0].isdigit()):
                continue
            larger, smaller = max(left["size"], right["size"]), min(left["size"], right["size"])
            gap = right["bbox"][0] - left["bbox"][2]
            if not -larger <= gap <= larger * 0.5:
                continue
            size_change = larger - smaller >= max(0.75, larger * 0.15)
            vertical_shift = abs(left["bbox"][3] - right["bbox"][3]) >= max(1.0, smaller * 0.2)
            if size_change or vertical_shift:
                pairs.append(
                    {
                        "left_span": left_index,
                        "right_span": right_index,
                        "size_change": size_change,
                        "vertical_shift": vertical_shift,
                    }
                )
        if pairs:
            result.append(
                {
                    "text": line["text"],
                    "bbox": list(line["bbox"]),
                    "spans": [
                        {"text": s["text"], "size": s["size"], "bbox": list(s["bbox"])}
                        for s in spans
                    ],
                    "risk_pairs": pairs,
                }
            )
    return result


def layout_context(
    session: Session, version_id: str, evidence_ids: Iterable[str]
) -> dict[str, Any]:
    """Report layout risks only after exact parse/paragraph/anchor matching.

    Adjacent numeric text with conspicuous size or vertical variation may have
    lost a superscript/subscript in plain text. This function preserves that
    text and geometry, and does not infer an exponent, unit or corrected value.
    Missing layout is explicitly unknown, rather than evidence of safe numbers.
    """
    requested = sorted(set(evidence_ids))
    result: dict[str, Any] = {
        "policy_version": POLICY,
        "document_version_id": version_id,
        "parse_artifact_id": None,
        "status": "not_requested" if not requested else "unknown",
        "checked_evidence_count": 0,
        "risk_blocks": [],
        "unresolved_evidence": [],
    }
    if not requested:
        return result
    version = session.get(AttachmentRevision, version_id)
    artifact = current_structure(session, version_id) if version else None
    unavailable = (
        "document_unavailable"
        if not version
        else "parse_unavailable"
        if not artifact
        else "parse_source_mismatch"
        if artifact.source_sha256 != version.sha256 or artifact.data.get("schema_version") != SCHEMA
        else None
    )
    if unavailable:
        result["unresolved_evidence"] = [
            {"evidence_id": eid, "reason": unavailable} for eid in requested
        ]
        return result
    assert artifact
    result["parse_artifact_id"] = artifact.id
    blocks: dict[str, list[dict[str, Any]]] = {}
    for block in artifact.data.get("blocks", []):
        if isinstance(block, dict) and isinstance(block.get("chunk_id"), str):
            blocks.setdefault(block["chunk_id"], []).append(block)
    risky: dict[str, dict[str, Any]] = {}
    assessed: dict[str, list[dict[str, Any]] | None] = {}
    for eid in requested:
        span = session.get(EvidenceSpan, eid)
        reason = None
        if not span or span.document_version_id != version_id:
            reason = "evidence_version_mismatch" if span else "evidence_unavailable"
        elif len(blocks.get(span.paragraph_id, [])) != 1:
            reason = "paragraph_mapping_unavailable"
        else:
            chunk = session.get(Chunk, span.paragraph_id)
            block = blocks[span.paragraph_id][0]
            if (
                not chunk
                or chunk.revision_id != version_id
                or chunk.text != block.get("text")
                or chunk.bbox != block.get("bbox")
                or chunk.page_index != block.get("page_index")
                or not isinstance(block.get("ref"), str)
            ):
                reason = "paragraph_mapping_mismatch"
            else:
                try:
                    validate_evidence(session, span, version_id)
                except KnowledgeError:
                    reason = "evidence_anchor_invalid"
                if reason is None:
                    if chunk.id not in assessed:
                        assessed[chunk.id] = _risk_lines(block)
                    lines = assessed[chunk.id]
                    if lines is None:
                        reason = "rich_layout_unavailable"
                    else:
                        result["checked_evidence_count"] += 1
                        if lines:
                            if chunk.id not in risky:
                                risky[chunk.id] = {
                                    "paragraph_id": chunk.id,
                                    "block_ref": block["ref"],
                                    "evidence_ids": [],
                                    "risk": "numeric_script_layout",
                                    "lines": lines,
                                }
                            risky[chunk.id]["evidence_ids"].append(eid)
        if reason:
            result["unresolved_evidence"].append({"evidence_id": eid, "reason": reason})
    result["risk_blocks"] = list(risky.values())
    if result["checked_evidence_count"]:
        result["status"] = "partial" if result["unresolved_evidence"] else "checked"
    return result
