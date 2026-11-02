"""Lossless, allowlisted transport compatibility; domain Schema remains strict."""

import json
from typing import Any

from pydantic import ValidationError

from researchgraph.unified_contracts import KnowledgeExtractionBatch


def normalize_empty_placeholders(raw: str) -> tuple[str, list[str]]:
    """Drop only the observed null marker, never an unknown scientific value."""
    try:
        value: Any = json.loads(raw)
    except (ValueError, TypeError):
        return raw, []
    paths = []
    if isinstance(value, dict) and isinstance(value.get("items"), list):
        for i, item in enumerate(value["items"]):
            if not isinstance(item, dict) or item.get("kind") != "Claim":
                continue
            detail = item.get("claim_detail")
            if (
                isinstance(detail, dict)
                and "findings_placeholder" in detail
                and detail["findings_placeholder"] is None
            ):
                del detail["findings_placeholder"]
                paths.append(f"items.{i}.claim_detail.findings_placeholder")
    return (json.dumps(value, ensure_ascii=False), paths) if paths else (raw, [])


def reusable_invalid_output(raw: str) -> bool:
    normalized, paths = normalize_empty_placeholders(raw)
    try:
        KnowledgeExtractionBatch.model_validate_json(normalized)
        return bool(paths)
    except ValidationError as error:
        return all(e["type"] == "local_ref_missing" for e in error.errors())
