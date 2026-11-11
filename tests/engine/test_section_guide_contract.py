import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from researchgraph.section_guide_contracts import (
    Depth,
    GuideGenerate,
    ReadingGuideDraft,
    guide_schema,
    strict_json,
    validate_response,
)

EXAMPLE = Path("docs/researchgraph_lite_ABD/examples/reading_guide_fictional.json")


def _raw(**updates: object) -> str:
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    payload.update(updates)
    return json.dumps(payload, ensure_ascii=False)


def test_schema_keeps_core_fields_required_and_optional_fields_bounded() -> None:
    schema = guide_schema()
    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "section_id",
        "overview_zh",
        "key_points",
        "reading_questions",
    ]
    assert schema["properties"]["difficult_terms"]["maxItems"] == 3
    assert schema["properties"]["evidence_span_ids"]["maxItems"] == 8
    assert schema["properties"]["caveats"]["maxItems"] == 4


def test_valid_guide_accepts_optional_fields_and_preserves_depth_rules() -> None:
    guide = validate_response(
        _raw(),
        requested_section_id="sec-03",
        allowed_span_ids={"sp-2"},
        depth="standard",
    )
    assert isinstance(guide, ReadingGuideDraft)
    assert guide.section_id == "sec-03"
    assert guide.evidence_span_ids == ["sp-2"]

    quick = validate_response(
        _raw(key_points=["只保留重点一", "只保留重点二"]),
        requested_section_id="sec-03",
        allowed_span_ids={"sp-2"},
        depth="quick",
    )
    assert len(quick.key_points) == 2


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"section_id": "sec-other"}, "section_id"),
        ({"evidence_span_ids": ["sp-not-allowed"]}, "span IDs"),
        (
            {"key_points": ["一", "二", "三"]},
            "at most two",
        ),
        ({"reading_questions": [" ", "问题二"]}, "must not be blank"),
    ],
)
def test_validation_rejects_wrong_scope_unknown_spans_quick_overflow_and_blank_items(
    updates: dict[str, object], message: str
) -> None:
    with pytest.raises((ValueError, ValidationError), match=message):
        validate_response(
            _raw(**updates),
            requested_section_id="sec-03",
            allowed_span_ids={"sp-2"},
            depth="quick",
        )


def test_strict_json_rejects_duplicate_keys_and_non_finite_values() -> None:
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        strict_json('{"section_id":"sec-03","section_id":"other"}')
    with pytest.raises(ValueError, match="Non-finite JSON constant"):
        strict_json('{"section_id":"sec-03","value":NaN}')


def test_generate_defaults_are_explicit_and_depth_is_limited() -> None:
    request = GuideGenerate(section_id="sec-03")
    assert request.depth == "standard"
    assert request.allow_network is False
    assert request.retry_failed is False
    assert request.force_regenerate is False

    for depth in ("quick", "standard", "deep"):
        assert GuideGenerate(section_id="sec-03", depth=depth).depth == depth
    with pytest.raises(ValidationError):
        GuideGenerate(section_id="sec-03", depth="full")  # type: ignore[arg-type]


def test_contract_depth_alias_is_the_expected_literal_set() -> None:
    # Keep this as a type-level documentation test without invoking a provider.
    assert set(Depth.__args__) == {"quick", "standard", "deep"}
