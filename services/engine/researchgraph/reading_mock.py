"""Offline orchestration fixture only; never a product model or scientific evaluator."""

from typing import Any


def semantic_complete(title: str, data: dict[str, Any]) -> dict[str, Any]:
    """Explicit offline fixture; never advertises model quality or API support."""
    if title == "SemanticIntegration":
        return {"associations": [], "duplicates": [], "warnings": []}
    if title == "KeyedContributionRanking":
        return {
            "assessments": {
                ref: {
                    "recommendation": "suggest_core",
                    "reasons": ["main_contribution"],
                    "rationale": "Synthetic keyed assessment fixture",
                    "priority": 50,
                }
                for ref in data["assessment_refs"]
            },
            "warnings": [],
        }
    if title == "ContributionRanking":
        return {
            "ranked_claims": [
                {
                    "claim_ref": unit["claim_ref"],
                    "recommendation": "suggest_core",
                    "reasons": ["main_contribution"],
                    "rationale": "Synthetic ranking fixture",
                }
                for unit in data["units"]
            ],
            "warnings": [],
        }
    from researchgraph.reading_transport import fixture

    candidate = complete(
        "KnowledgeExtractionBatch",
        {**data, "document_version_id": "fixture-version", "chunk_id": "fixture-chunk"},
    )
    return fixture(candidate, data.get("source_language", "en"))


def complete(title: str, data: dict[str, Any]) -> dict[str, Any]:
    version = data["document_version_id"]
    if title == "PaperIntegrationProposal":
        roots = data["root_claim_ids"]
        edges = data["existing_associations"]
        units = []
        for root in roots:
            reached = {root}
            for _ in range(len(data["candidates"])):
                reached.update(e["target_id"] for e in edges if e["source_id"] in reached)
            units.append(
                {
                    "local_ref": "unit-" + root,
                    "root_claim_id": root,
                    "member_ids": sorted(reached - {root}),
                    "rationale": "Synthetic path fixture",
                }
            )
        return {
            "contract_version": "reading-integration-1.0",
            "document_version_id": version,
            "input_revision": data["input_revision"],
            "units": units,
            "associations": [],
            "duplicates": [],
            "warnings": [],
        }
    if title == "CoreSelectionProposal":
        return {
            "document_version_id": version,
            "input_revision": data["input_revision"],
            "recommendations": [
                {
                    "root_claim_id": u["root_claim_id"],
                    "recommendation": "suggest_core",
                    "reasons": ["main_contribution"],
                    "rationale": "Synthetic selection fixture",
                }
                for u in data["units"]
            ],
            "coverage_gaps": [],
        }
    span = data["allowed_evidence"][0]
    source = {"original": span["text"], "language": "en", "zh": None}
    common = {
        "label": source,
        "summary": source,
        "origin": "paper_author",
        "evidence_ids": [span["id"]],
    }
    return {
        "contract_version": "reading-extraction-1.0",
        "document_version_id": version,
        "chunk_id": data["chunk_id"],
        "items": [
            {
                **common,
                "local_ref": "c",
                "kind": "Claim",
                "statement": source,
                "contribution_type": "empirical_result",
                "modality": "unknown",
            },
            {**common, "local_ref": "m", "kind": "Method", "method_role": "unknown"},
        ],
        "links": [
            {
                "source_local_ref": "c",
                "target_local_ref": "m",
                "relation": "ASSOCIATED_METHOD",
                "evidence_ids": [span["id"]],
            }
        ],
        "warnings": [],
    }
