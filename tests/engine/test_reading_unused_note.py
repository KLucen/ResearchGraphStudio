"""An exact empty provider placeholder never relaxes semantic/source validation."""

import copy
import json

import pytest
from pydantic import ValidationError
from researchgraph.reading_validation import validate_batch
from researchgraph.reading_wire import compact_fixture
from test_reading_extraction import candidate_batch


def test_empty_claim_note_is_audited_without_mutating_raw_or_skipping_sources():
    data = compact_fixture(candidate_batch("ev1"))
    data["items"][0]["kind_note_unused"] = None
    raw = json.dumps(data)
    audit = []
    batch, quarantined = validate_batch(raw, {"ev1"}, compact=True, wire_changes=audit)
    assert not quarantined and len(batch.items) == 4
    assert {"path": "items.0.kind_note_unused", "rule": "empty-unused-claim-note-v1"} in audit
    assert json.loads(raw)["items"][0]["kind_note_unused"] is None
    assert "kind_note_unused" not in batch.items[0].model_dump()
    with pytest.raises(ValueError, match="whitelist"):
        validate_batch(raw, {"different"}, compact=True)


@pytest.mark.parametrize("value", ["content", {}, [], False, 0])
def test_nonempty_or_wrong_type_note_remains_invalid(value):
    data = candidate_batch("ev1")
    data["items"][0]["kind_note_unused"] = value
    with pytest.raises(ValidationError, match="extra_forbidden"):
        validate_batch(json.dumps(data), {"ev1"})


def test_other_kinds_and_other_unknown_fields_stay_invalid():
    data = candidate_batch("ev1")
    data["items"][1]["kind_note_unused"] = None
    with pytest.raises(ValidationError, match="extra_forbidden"):
        validate_batch(json.dumps(data), {"ev1"})
    data = candidate_batch("ev1")
    data["items"][0]["another_note_unused"] = None
    with pytest.raises(ValidationError, match="extra_forbidden"):
        validate_batch(json.dumps(data), {"ev1"})


def test_raw_duplicates_are_not_equated_after_placeholder_removal():
    data = candidate_batch("ev1")
    duplicate = copy.deepcopy(data["items"][0])
    duplicate["kind_note_unused"] = None
    data["items"].append(duplicate)
    with pytest.raises(ValueError, match="内容不同"):
        validate_batch(json.dumps(data), {"ev1"})
