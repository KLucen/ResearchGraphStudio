"""Versioned model reading contracts bind real model segment identities."""

import json
from copy import deepcopy

import pytest
from researchgraph.model_document_reading import (
    reading_context,
    reading_schema,
    translation_schema,
    validate_reading_output,
    validate_translation_output,
)


@pytest.fixture
def segments():
    # Identical text in distinct chapters must retain two independent slots.
    return [
        {
            "id": "p1",
            "kind": "paragraph",
            "chapter_ref": "intro",
            "text": "A result follows.",
            "ordinal": 0,
        },
        {
            "id": "p2",
            "kind": "paragraph",
            "chapter_ref": "results",
            "text": "A result follows.",
            "ordinal": 1,
        },
        {"id": "f1", "kind": "formula", "chapter_ref": "results", "latex": "x^2", "status": "ok"},
        {
            "id": "t1",
            "kind": "table",
            "chapter_ref": "results",
            "table_data": {"columns": ["x"], "rows": [["2"]]},
            "status": "degraded",
        },
    ]


def reading_payload(segments):
    return {
        "schema_version": "model-document-reading-1",
        "item_kind": "paper_reading",
        "paragraphs": [
            {
                "paragraph_id": segment["id"],
                "translation_zh": None,
                "paragraph_function": "PRESENT_EVIDENCE",
                "logic_role_zh": "呈现作者给出的结果。",
                "critical_note_zh": "",
                "reading_question_zh": None,
                "highlights": [{"type": "EVIDENCE", "quote_en": "result", "occurrence_index": 0}],
                "related_graph_node_ids": [],
            }
            for segment in segments
            if segment["kind"] == "paragraph"
        ],
        "paper_argument": {
            "logic_chain_zh": ["提出问题", "陈述结果"],
            "core_claim_zh": None,
            "strong_point_zh": None,
            "question_to_verify_zh": None,
        },
    }


def translation_payload(segments):
    return {
        "schema_version": "model-document-translation-1",
        "item_kind": "translation",
        "translations": [
            {
                "paragraph_id": segment["id"],
                "chapter_ref": segment["chapter_ref"],
                "source_text": segment["text"],
                "translation_zh": "接下来给出一个结果。",
            }
            for segment in segments
            if segment["kind"] == "paragraph"
        ],
    }


def test_reading_source_ids_quotes_and_materials_roundtrip(segments):
    context = reading_context(segments)
    assert [item["paragraph_id"] for item in context["paragraphs"]] == ["p1", "p2"]
    assert {item["id"] for item in context["materials"]} == {"f1", "t1"}
    assert context["materials"][1]["table_data"]["rows"] == [["2"]]
    result = validate_reading_output(json.dumps(reading_payload(segments)), segments)
    assert result.paragraphs[1].highlights[0].quote_en == "result"
    assert result.paragraphs[1].translation_zh is None
    assert reading_schema()["additionalProperties"] is False
    assert translation_schema()["additionalProperties"] is False


@pytest.mark.parametrize("change", ["missing", "duplicate", "unknown", "order"])
def test_reading_rejects_incomplete_ambiguous_or_reordered_paragraphs(segments, change):
    payload = reading_payload(segments)
    if change == "missing":
        payload["paragraphs"].pop()
    elif change == "duplicate":
        payload["paragraphs"][1]["paragraph_id"] = "p1"
    elif change == "unknown":
        payload["paragraphs"][1]["paragraph_id"] = "invented"
    else:
        payload["paragraphs"].reverse()
    with pytest.raises(ValueError, match="COVERAGE_OR_ORDER"):
        validate_reading_output(payload, segments)


@pytest.mark.parametrize("change", ["quote", "occurrence", "graph", "extra", "translation"])
def test_reading_rejects_invalid_annotation_instead_of_silently_dropping_it(segments, change):
    payload = reading_payload(segments)
    paragraph = payload["paragraphs"][0]
    if change == "quote":
        paragraph["highlights"][0]["quote_en"] = "fabricated text"
    elif change == "occurrence":
        paragraph["highlights"][0]["occurrence_index"] = 1
    elif change == "graph":
        paragraph["related_graph_node_ids"] = ["invented-local-node"]
    elif change == "extra":
        paragraph["extra"] = "not allowed"
    else:
        paragraph["translation_zh"] = "未获用户选择的额外翻译"
    with pytest.raises(ValueError):
        validate_reading_output(payload, segments)


def test_reading_translation_mode_is_explicit(segments):
    payload = reading_payload(segments)
    with pytest.raises(ValueError, match="REQUIRED"):
        validate_reading_output(payload, segments, "full")
    for paragraph in payload["paragraphs"]:
        paragraph["translation_zh"] = "接下来给出一个结果。"
    assert validate_reading_output(payload, segments, "full").paragraphs[0].translation_zh


def test_strict_json_rejects_duplicate_keys_and_nonfinite_values(segments):
    raw = json.dumps(reading_payload(segments))
    duplicate = raw.replace(
        '"item_kind": "paper_reading"', '"item_kind":"translation","item_kind":"paper_reading"'
    )
    with pytest.raises(ValueError):
        validate_reading_output(duplicate, segments)
    nonfinite = raw.replace('"occurrence_index": 0', '"occurrence_index": NaN')
    with pytest.raises(ValueError):
        validate_reading_output(nonfinite, segments)


def test_translation_binding_does_not_merge_identical_source_text(segments):
    payload = translation_payload(segments)
    assert len(validate_translation_output(payload, segments).translations) == 2
    payload["translations"].pop()
    with pytest.raises(ValueError, match="COVERAGE_OR_ORDER"):
        validate_translation_output(payload, segments)


@pytest.mark.parametrize(
    "field,value",
    [
        ("chapter_ref", "wrong"),
        ("source_text", "Wrong source."),
        ("translation_zh", "A result follows."),
    ],
)
def test_translation_exact_id_chapter_text_and_non_echo_checks(segments, field, value):
    payload = deepcopy(translation_payload(segments))
    payload["translations"][0][field] = value
    with pytest.raises(ValueError):
        validate_translation_output(payload, segments)
