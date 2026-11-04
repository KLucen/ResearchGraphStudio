"""One observed P13 syntax omission, without rewriting any JSON value or key."""

import json
import re
from typing import Any

from researchgraph.knowledge_store import text_hash


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key; syntax normalization refused")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("Non-JSON constant; syntax normalization refused")


def _space(raw: str, index: int) -> int:
    match = re.compile(r"[ \t\r\n]*").match(raw, index)
    assert match
    return match.end()


def _missing_gaps_close(raw: str, position: int) -> int | None:
    """Recognize only a complete final string list before the existing root `}`.

    No EOF completion, generic bracket balancing, comma insertion, text escaping,
    field removal or model rewrite is permitted. Decode all earlier members and
    list strings strictly, so braces/quotes in their content are never scanned as
    structure. The final full Schema/ID/source checks remain the caller's job.
    """
    decoder = json.JSONDecoder(object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    index = _space(raw, 0)
    if raw[index : index + 1] != "{":
        return None
    index = _space(raw, index + 1)
    keys: set[str] = set()
    while index < len(raw):
        key, index = decoder.raw_decode(raw, index)
        if not isinstance(key, str) or key in keys:
            return None
        keys.add(key)
        index = _space(raw, index)
        if raw[index : index + 1] != ":":
            return None
        index = _space(raw, index + 1)
        if key == "coverage_gaps":
            if raw[index : index + 1] != "[":
                return None
            index = _space(raw, index + 1)
            while index < len(raw):
                # At least one complete string; never supply a missing item.
                value, index = decoder.raw_decode(raw, index)
                if not isinstance(value, str):
                    return None
                index = _space(raw, index)
                if index == position and raw[index:].strip() == "}":
                    return index
                if raw[index : index + 1] != ",":
                    return None
                index = _space(raw, index + 1)
            return None
        _, index = decoder.raw_decode(raw, index)
        index = _space(raw, index)
        if raw[index : index + 1] != ",":
            return None
        index = _space(raw, index + 1)
    return None


def load_selection(raw: str, audit: list[dict[str, str]]) -> Any:
    """Preserve raw_output; repair only the observed final coverage_gaps `]`."""
    try:
        return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except json.JSONDecodeError as error:
        if error.msg != "Expecting ',' delimiter":
            raise
        try:
            position = _missing_gaps_close(raw, error.pos)
        except (ValueError, TypeError, RecursionError):
            position = None
        if position is None:
            raise
        normalized = raw[:position] + "]" + raw[position:]
        try:
            data = json.loads(
                normalized, object_pairs_hook=_unique_object, parse_constant=_reject_constant
            )
        except (ValueError, TypeError, RecursionError):
            raise error from None
        audit.append(
            {
                "path": "coverage_gaps",
                "rule": "close-final-selection-gaps-array-v1",
                "offset": str(position),
                "inserted": "]",
                "raw_sha256": text_hash(raw),
                "normalized_sha256": text_hash(normalized),
            }
        )
        return data
