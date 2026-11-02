"""Deterministic offline fixtures, explicitly not scientific model judgements."""

import re
from typing import Any


def complete(title: str, data: dict[str, Any]) -> dict[str, Any]:
    a, b = data["claim_a"], data["claim_b"]
    ids = list(dict.fromkeys(a["evidence_ids"] + b["evidence_ids"]))
    reason = "Offline Mock workflow fixture; requires human scientific review."
    if title == "EntityAlignmentBatch":
        return {
            "alignments": [
                {
                    "source_local_ref": "source",
                    "candidate_concept_id": b["id"],
                    "decision": "same_as"
                    if a["text"].casefold() == b["text"].casefold()
                    else "insufficient",
                    "rationale": reason,
                    "evidence_span_ids": ids,
                }
            ]
        }
    if title == "ComparabilityReport":
        dimensions = []
        for name in data["required_dimensions"]:
            x, y = [
                s["dimensions"].get(name, {"known_state": "unknown", "value": None}) for s in (a, b)
            ]
            comparison = "unknown"
            if x["known_state"] == y["known_state"] == "known":
                comparison = (
                    "same"
                    if (x["value"], x.get("unit")) == (y["value"], y.get("unit"))
                    else "different"
                )
            elif x["known_state"] == y["known_state"] == "not_applicable":
                comparison = "not_applicable"
            dimensions.append(
                {
                    "name": name,
                    "source_value": x["value"],
                    "target_value": y["value"],
                    "comparison": comparison,
                    "impact": "unknown" if comparison == "unknown" else "neutral",
                    "evidence_ids": ids,
                }
            )
        unknown = [d["name"] for d in dimensions if d["comparison"] == "unknown"]
        different = any(d["comparison"] == "different" for d in dimensions)
        return {
            "source_claim_id": a["id"],
            "target_claim_id": b["id"],
            "topic_overlap": "related",
            "overall": "limited" if unknown or different else "comparable",
            "dimensions": dimensions,
            "unknown_dimensions": unknown,
            "rationale": reason,
        }
    words = [set(re.findall(r"[a-z]{4,}", s["text"].lower())) for s in (a, b)]
    proposed = len(words[0] & words[1]) >= 2
    return {
        "source_claim_id": a["id"],
        "target_claim_id": b["id"],
        "decision": "PROPOSE_RELATION" if proposed else "NO_DECISION",
        "relation_type": "RELATED" if proposed else None,
        "reason": reason,
        "evidence_ids": ids,
        "unresolved_questions": ["Mock does not establish semantic support or contradiction."],
        "suggested_review": "inspect_original_evidence",
    }
