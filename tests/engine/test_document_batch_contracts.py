"""Offline validation of batch wire format and safe diagnostic projection."""

import json

import pytest
from researchgraph.document_batch_contracts import (
    BatchValidationError,
    validate_batch,
    validate_boundary,
)


def _batch():
    return {
        "version": "document-batch-1",
        "page_start": 5,
        "page_end": 8,
        "segments": [
            {
                "chapter_ref": "intro",
                "chapter_title": "Introduction",
                "kind": "paragraph",
                "text": "Anonymous synthetic text",
                "page_start": 5,
                "page_end": 5,
            }
        ],
        "warnings": ["Anonymous fixture pages6-8 unavailable"],
        "unavailable_pages": [6, 7, 8],
    }


def test_valid_batch_preserves_source_pages_and_continuations():
    source = _batch()
    source["segments"][0]["continues_before"] = True
    source["warnings"] = ["Anonymous fixture pages6-8 unavailable"]
    parsed = validate_batch(json.dumps(source), 5, 8)
    assert parsed.segments[0].page_start == 5
    assert parsed.segments[0].continues_before
    assert not parsed.segments[0].continues_after


@pytest.mark.parametrize(
    "raw,code",
    [
        ('{"version":"document-batch-1","version":"x"}', "duplicate_key"),
        ('{"unknown-secret":NaN}', "nonfinite_number"),
        ('{"unknown-secret":Infinity}', "nonfinite_number"),
        ('{"unknown-secret":1e9999}', "nonfinite_number"),
        ("```json\n{}\n```", "json_invalid"),
        ("[{}]", "model_type"),
    ],
)
def test_invalid_json_is_bounded_without_echo(raw, code):
    with pytest.raises(BatchValidationError) as error:
        validate_batch(raw, 5, 8)
    assert error.value.safe_errors == [{"path": "$", "code": code}]
    assert "unknown-secret" not in str(error.value)


def test_unknown_field_and_value_are_absent_from_safe_errors():
    batch = _batch()
    batch["segments"][0]["private-paper-text"] = "credential-like-private-data"
    batch["segments"][0]["kind"] = "private-kind-text"
    with pytest.raises(BatchValidationError) as error:
        validate_batch(json.dumps(batch), 5, 8)
    serialized = json.dumps(error.value.safe_errors)
    assert "private" not in serialized and "credential" not in serialized
    assert {"path": "segments[0].kind", "code": "literal_error"} in error.value.safe_errors
    assert {"path": "segments[0]", "code": "extra_forbidden"} in error.value.safe_errors


@pytest.mark.parametrize(
    "change",
    [
        {"page_start": 4},
        {"page_end": 9},
        {"page_start": 8, "page_end": 5},
        {"kind": "formula", "text": None},
        {"kind": "table", "text": None},
    ],
)
def test_invalid_material_or_source_range_is_rejected(change):
    batch = _batch()
    batch["segments"][0].update(change)
    with pytest.raises(BatchValidationError):
        validate_batch(json.dumps(batch), 5, 8)


def test_batch_range_must_match_frozen_core_pages():
    with pytest.raises(BatchValidationError) as error:
        validate_batch(json.dumps(_batch()), 1, 4)
    assert error.value.safe_errors[0]["code"] == "page_range_mismatch"


def test_nested_locator_cannot_contradict_authoritative_batch_pages():
    batch = _batch()
    batch["segments"][0]["locator"] = {"page_start": 1, "page_end": 2}
    with pytest.raises(BatchValidationError):
        validate_batch(batch, 5, 8)


def test_batch_numeric_and_boolean_fields_require_correct_json_types():
    batch = _batch()
    batch["segments"][0]["page_start"] = "5"
    batch["segments"][0]["continues_after"] = "false"
    with pytest.raises(BatchValidationError) as error:
        validate_batch(json.dumps(batch), 5, 8)
    assert {"path": "segments[0].page_start", "code": "int_type"} in error.value.safe_errors
    assert {"path": "segments[0].continues_after", "code": "bool_type"} in error.value.safe_errors


def test_empty_pages_require_warning():
    batch = _batch()
    batch["segments"] = []
    with pytest.raises(BatchValidationError):
        validate_batch(json.dumps(batch), 5, 8)
    batch["warnings"] = ["No readable material on these anonymous fixture pages"]
    batch["unavailable_pages"] = [5, 6, 7, 8]
    assert validate_batch(json.dumps(batch), 5, 8).segments == []


@pytest.mark.parametrize("unavailable", [[], [6, 7], [5, 6, 7, 8], [6, 7, 8, 9], [6, 7, 8, 8]])
def test_coverage_is_complete_disjoint_and_inside_core_range(unavailable):
    batch = _batch()
    batch["unavailable_pages"] = unavailable
    batch["warnings"] = ["Some anonymous fixture pages unreadable"]
    with pytest.raises(BatchValidationError) as error:
        validate_batch(json.dumps(batch), 5, 8)
    assert {"path": "$", "code": "value_error"} in error.value.safe_errors


def test_crosspage_segment_can_cover_every_core_page_without_unavailable_pages():
    batch = _batch()
    batch["segments"][0]["page_end"] = 8
    batch["unavailable_pages"] = []
    parsed = validate_batch(json.dumps(batch), 5, 8)
    assert parsed.segments[0].page_end == 8 and parsed.unavailable_pages == []


def test_unavailable_pages_require_warnings_and_strict_integer_items():
    batch = _batch()
    batch["warnings"] = []
    with pytest.raises(BatchValidationError):
        validate_batch(json.dumps(batch), 5, 8)
    batch["warnings"] = ["Some pages unavailable"]
    batch["unavailable_pages"] = ["6", 7, 8]
    with pytest.raises(BatchValidationError) as error:
        validate_batch(json.dumps(batch), 5, 8)
    assert {"path": "unavailable_pages[0]", "code": "int_type"} in error.value.safe_errors


def test_unbounded_model_page_spans_are_rejected_before_coverage_expansion():
    batch = _batch()
    batch["page_end"] = 10**15
    batch["segments"][0]["page_end"] = 10**15
    with pytest.raises(BatchValidationError) as error:
        validate_batch(json.dumps(batch), 5, 8)
    assert any(item["code"] == "less_than_equal" for item in error.value.safe_errors)


def test_segment_count_and_order_are_bounded():
    batch = _batch()
    batch["segments"] *= 1001
    with pytest.raises(BatchValidationError):
        validate_batch(json.dumps(batch), 5, 8)
    batch = _batch()
    first = batch["segments"][0]
    batch["segments"] = [dict(first, page_start=6, page_end=6), first]
    with pytest.raises(BatchValidationError):
        validate_batch(json.dumps(batch), 5, 8)


def test_boundary_only_returns_decision_never_rewritten_content():
    raw = {
        "version": "document-boundary-1",
        "action": "merge",
        "separator": "space",
        "reason": "continuation",
    }
    assert validate_boundary(json.dumps(raw)).action == "merge"
    raw["rewritten_text"] = "forbidden model text"
    with pytest.raises(BatchValidationError) as error:
        validate_boundary(json.dumps(raw))
    assert "rewritten_text" not in json.dumps(error.value.safe_errors)


def test_boundary_reason_is_enum_and_not_model_rationale():
    raw = {
        "version": "document-boundary-1",
        "action": "uncertain",
        "separator": "none",
        "reason": "private free-form rationale",
    }
    with pytest.raises(BatchValidationError) as error:
        validate_boundary(json.dumps(raw))
    assert error.value.safe_errors == [{"path": "reason", "code": "literal_error"}]
