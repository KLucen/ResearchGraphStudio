"""Read-only PDF layout cautions frozen only by new Query preparations."""

import re
import unicodedata
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from researchgraph.document_structure import SCHEMA, current_structure
from researchgraph.knowledge_store import KnowledgeError, text_hash
from researchgraph.models import AttachmentRevision, Chunk
from researchgraph.reading_evidence_quality import _risk_lines, layout_context

POLICY = "query-numeric-layout-1"
RISK_WARNING = (
    "原文含上下标或字号位移，纯文本数字可能失真；数值待核对 PDF，不得按普通整数使用或猜测修正。"
)
UNKNOWN_WARNING = "数值版式尚无法完整核验；这不代表数字安全，缺失的指数、单位或条件不得猜测。"
DISPLAY_RULE = "query-layout-caution-display-1"
NUMERIC_PLACEHOLDER = "[版式歧义数值，见原文]"
DISPLAY_NOTICE = (
    "程序已将限制说明中的版式歧义数值替换为占位提示；原始模型响应保留，未推断正确数值。"
)


def _collapsed_tokens(lines: list[dict[str, Any]]) -> list[str]:
    tokens = set()
    for line in lines:
        spans = line["spans"]
        for pair in line["risk_pairs"]:
            left = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*$", spans[pair["left_span"]]["text"])
            right = re.match(r"\s*([0-9]+(?:\.[0-9]+)?)", spans[pair["right_span"]]["text"])
            if left and right:
                tokens.add(left[1] + right[1])
    return sorted(tokens)


def freeze_layout(session: Session, references: list[dict[str, Any]]) -> dict[str, Any]:
    """Reuse evidence layout checks and check exact chunk-only mappings too.

    No PDF is opened, no exponent is inferred and no source is rewritten.
    Unknown/partial layout stays explicit. Maps live only in this invocation.
    """
    by_version: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ref in references:
        if ref["type"] in {"chunk", "evidence", "node"}:
            by_version[ref["document_version_id"]].append(ref)
    sources = []
    for version_id in sorted(by_version):
        refs = by_version[version_id]
        source = layout_context(
            session,
            version_id,
            sorted(
                {r["id"] for r in refs if r["type"] == "evidence"}
                | {eid for r in refs if r["type"] == "node" for eid in r.get("evidence_ids", [])}
            ),
        )
        version = session.get(AttachmentRevision, version_id)
        artifact = current_structure(session, version_id)
        blocks: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if (
            artifact
            and version
            and artifact.source_sha256 == version.sha256
            and artifact.data.get("schema_version") == SCHEMA
        ):
            for block in artifact.data.get("blocks", []):
                if isinstance(block, dict) and isinstance(block.get("chunk_id"), str):
                    blocks[block["chunk_id"]].append(block)
        risks = {b["paragraph_id"]: b for b in source["risk_blocks"]}
        checks = []
        for ref in (r for r in refs if r["type"] == "chunk"):
            cid = ref["id"]
            chunk = session.get(Chunk, cid)
            matches = blocks.get(cid, [])
            block = matches[0] if len(matches) == 1 else None
            lines = None
            if (
                chunk
                and block
                and chunk.revision_id == version_id
                and chunk.text == block.get("text") == ref["quote"]
                and chunk.bbox == block.get("bbox")
                and chunk.page_index == block.get("page_index")
                and isinstance(block.get("ref"), str)
            ):
                lines = _risk_lines(block)
            checks.append(
                {
                    "reference": ref["ref"],
                    "paragraph_id": cid,
                    "status": "unknown" if lines is None else "checked",
                }
            )
            if lines and cid not in risks:
                risks[cid] = {
                    "paragraph_id": cid,
                    "block_ref": block["ref"],
                    "evidence_ids": [],
                    "risk": "numeric_script_layout",
                    "lines": lines,
                }
        for cid, risk in risks.items():
            evidence_ids = set(risk["evidence_ids"])
            risk["source_refs"] = sorted(
                r["ref"]
                for r in refs
                if (r["type"] == "chunk" and r["id"] == cid)
                or (r["type"] == "evidence" and r["paragraph_id"] == cid)
                or (r["type"] == "node" and evidence_ids.intersection(r.get("evidence_ids", [])))
            )
            risk["collapsed_numeric_tokens"] = _collapsed_tokens(risk["lines"])
        unknown = bool(source["unresolved_evidence"]) or any(
            c["status"] == "unknown" for c in checks
        )
        checked = bool(source["checked_evidence_count"]) or any(
            c["status"] == "checked" for c in checks
        )
        sources.append(
            {
                **source,
                "status": "partial"
                if unknown and checked
                else "unknown"
                if unknown
                else "checked"
                if checked
                else "not_requested",
                "reference_refs": sorted(r["ref"] for r in refs),
                "chunk_checks": checks,
                "risk_blocks": [risks[cid] for cid in sorted(risks)],
            }
        )
    return {"policy": POLICY, "sources": sources}


def warnings_by_reference(layout: dict[str, Any]) -> dict[str, list[str]]:
    warnings: dict[str, list[str]] = defaultdict(list)
    for source in layout.get("sources", []):
        if source["status"] in {"unknown", "partial", "not_requested"}:
            for ref in source.get("reference_refs", []):
                warnings[ref].append(UNKNOWN_WARNING)
        for block in source.get("risk_blocks", []):
            for ref in block["source_refs"]:
                warnings[ref].append(RISK_WARNING)
        for check in source.get("chunk_checks", []):
            if check["status"] == "unknown":
                warnings[check["reference"]].append(UNKNOWN_WARNING)
    return {ref: list(dict.fromkeys(values)) for ref, values in warnings.items()}


def numeric_matches(value: str, layout: dict[str, Any]) -> list[dict[str, Any]]:
    """Find risky numbers using a matching buffer, preserving original Unicode spans.

    Normalization is never applied to the displayed string. Attached units do
    not hide a number, and a zero decimal suffix belongs to its original span.
    """
    tokens = {
        token
        for source in layout.get("sources", [])
        for block in source.get("risk_blocks", [])
        for token in block["collapsed_numeric_tokens"]
    }
    if not tokens:
        return []
    normalized, offsets = [], []
    for index, char in enumerate(value):
        part = unicodedata.normalize("NFKC", char)
        normalized.append(part)
        offsets.extend([index] * len(part))
    pattern = (
        r"(?<![0-9.])(?:"
        + "|".join(re.escape(token) for token in sorted(tokens, key=lambda t: (-len(t), t)))
        + r")(?:\.0+)?(?![0-9.])"
    )
    matches = []
    for match in re.finditer(pattern, "".join(normalized)):
        start, end = offsets[match.start()], offsets[match.end() - 1] + 1
        matches.append({"start": start, "end": end, "token_sha256": text_hash(value[start:end])})
    return matches


def normalize_caution(value: str, layout: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    matches = numeric_matches(value, layout)
    for match in reversed(matches):
        value = value[: match["start"]] + NUMERIC_PLACEHOLDER + value[match["end"] :]
    return value, matches


def validate_numeric_layout(
    passages: list[Any],
    layout: dict[str, Any],
    limitations: list[str] | None = None,
    *,
    include_cautions: bool = True,
) -> None:
    """Reject a known flattened numeric token as a standalone answer value.

    This deliberately does not guess the corrected exponent or unit. No guard
    is retroactively attached to historical v1 answers lacking this manifest.
    """
    texts = list(limitations or []) if include_cautions else []
    for passage in passages:
        texts.append(passage.text)
        if include_cautions:
            texts.extend(getattr(passage, "limitations", getattr(passage, "caveats", [])))
    for value in texts:
        if numeric_matches(value, layout):
            raise KnowledgeError(
                "QUERY_NUMERIC_LAYOUT_UNRESOLVED",
                "回答将有上下标版式歧义的数字作为普通数值使用；"
                "已保留原始响应，未自动重发，请核对 PDF 后准备新查询",
            )
