"""Clearly labelled offline extractive fixtures; never evidence of real model quality."""

import re
from typing import Any


def complete(data: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    links = []
    for i, source in enumerate(data["allowed_evidence"][:8]):
        text, eid = source["text"].strip(), source["id"]
        if len(text) < 10:
            continue
        origin = (
            "citation_report"
            if re.search(r"prior work|et al|previous work", text, re.I)
            else "paper_author"
        )
        common = {"summary_en": text, "summary_zh": "", "origin": origin, "evidence_ids": [eid]}
        if re.search(r"method|algorithm|framework|approach", text, re.I):
            items.append(
                {
                    **common,
                    "local_ref": f"m{i}",
                    "kind": "Method",
                    "label_en": text[:80],
                    "label_zh": "离线方法摘录",
                    "method_detail": {"mechanism_en": text},
                }
            )
            items.append(
                {
                    **common,
                    "local_ref": f"c{i}",
                    "kind": "Concept",
                    "label_en": "method (offline excerpt)",
                    "label_zh": "离线术语摘录",
                }
            )
            links.append(
                {
                    "source_local_ref": f"cl{i}",
                    "target_local_ref": f"m{i}",
                    "relation": "USES_METHOD",
                    "evidence_ids": [eid],
                }
            )
        detail: dict[str, Any] = {
            "statement_en": text,
            "statement_zh": "",
            "modality": "unknown",
            "conditions": [],
        }
        if re.search(r"result|accuracy|achiev|score", text, re.I):
            detail["findings"] = [{"finding_en": text, "finding_zh": "", "evidence_ids": [eid]}]
        items.append(
            {
                **common,
                "local_ref": f"cl{i}",
                "kind": "Claim",
                "label_en": text[:80],
                "label_zh": "离线主张摘录",
                "claim_detail": detail,
            }
        )
        if "?" in text or re.search(r"research question|open question|future work", text, re.I):
            items.append(
                {
                    **common,
                    "local_ref": f"q{i}",
                    "kind": "ResearchQuestion",
                    "label_en": text[:80],
                    "label_zh": "离线问题摘录",
                }
            )
    return {
        "document_version_id": data["document_version_id"],
        "chunk_id": data["chunk_id"],
        "items": items,
        "links": links,
        "warnings": ["Mock 原文摘录，仅验证流程，不代表科学抽取或真实翻译"],
    }
