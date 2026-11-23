"""Anonymous exact-evidence and immutable saved-output card contract tests."""

import copy
import json
from typing import get_args

import pytest
from researchgraph.core import text_hash
from researchgraph.paper_card_set_contracts import (
    ANCHORED_PROMPT_VERSION,
    CARD_KIND_DESCRIPTIONS,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    SYSTEM_PROMPT,
    CardKind,
    anchored_model_input,
    model_input,
    paper_card_set_schema,
    validate_anchored_card_set,
    validate_paper_card_set,
    validate_saved_paper_card_set,
)


def source_manifest():
    text = "The authors propose a synthetic method. It reduces runtime by 12%."
    return {
        "paper_id": "paper-synthetic",
        "paper_title": "Anonymous synthetic paper",
        "source_kind": "local_revision",
        "source_id": "revision-synthetic",
        "source_fingerprint": "frozen-synthetic-source",
        "warnings": ["Synthetic fixture, not a scientific result."],
        "sources": [
            {
                "ref": "s1",
                "text": text,
                "text_hash": text_hash(text),
                "kind": "paragraph",
                "chapter_ref": "section-methods",
                "chapter_title": "Methods",
                "page_start": 4,
                "page_end": 4,
                "origin": {
                    "unit_id": "reading-unit-synthetic",
                    "sources": [
                        {
                            "text": text,
                            "text_hash": text_hash(text),
                            "chunk_id": "chunk-synthetic",
                            "span_ids": ["span-synthetic"],
                            "page": 4,
                            "start_offset": 20,
                        }
                    ],
                },
            }
        ],
    }


def card_payload():
    return {
        "schema_version": SCHEMA_VERSION,
        "article_overview_zh": "合成文章介绍一种方法及其运行时间结果。",
        "overview_card_ids": ["c1", "c2"],
        "card_set_intro_zh": "本组包含作者贡献和模型分析卡。",
        "coverage_notes": ["只包含软件测试材料，未声明作者局限。"],
        "cards": [
            {
                "id": "c1",
                "kind": "core_contribution",
                "attribution": "AUTHOR",
                "title_zh": "作者提出的方法",
                "title_en": "Synthetic method",
                "body_zh": "作者提出一种合成方法。",
                "reading_guide_zh": "关注其适用条件。",
                "evidence": [
                    {
                        "source_id": "s1",
                        "quote_en": "The authors propose a synthetic method.",
                        "occurrence_index": 0,
                        "translation_zh": "作者提出一种合成方法。",
                    }
                ],
            },
            {
                "id": "c2",
                "kind": "strength",
                "attribution": "ANALYSIS",
                "title_zh": "可测量的改进",
                "title_en": None,
                "body_zh": "该结果显示运行时间有所下降。",
                "reading_guide_zh": "核对对照条件。",
                "evidence": [
                    {
                        "source_id": "s1",
                        "quote_en": "It reduces runtime by 12%.",
                        "occurrence_index": 0,
                        "translation_zh": None,
                    }
                ],
            },
        ],
    }


def test_new_card_set_binds_each_exact_quote_translation_and_owned_location():
    manifest, wire = source_manifest(), card_payload()
    result = validate_paper_card_set(json.dumps(wire, ensure_ascii=False), manifest)
    assert result["schema_version"] == "paper-card-set-2"
    assert result["prompt_version"] == PROMPT_VERSION
    assert result["evidence_status"] == "grounded"
    assert result["semantic_accuracy"] == "unverified"
    assert result["wire_draft"] == wire
    author, analysis = result["cards"]
    assert result["overview_card_ids"] == [author["id"], analysis["id"]]
    assert author["id"] != "c1" and author["attribution"] == "AUTHOR"
    first = author["evidence"][0]
    assert first["quote_en"] == wire["cards"][0]["evidence"][0]["quote_en"]
    assert first["translation_status"] == "auxiliary"
    assert first["position"]["chapter_ref"] == "section-methods"
    assert first["position"]["page_start"] == first["position"]["page_end"] == 4
    assert first["position"]["source_offset_start"] == 0
    assert first["position"]["local_offsets"] == [
        {
            "chunk_id": "chunk-synthetic",
            "span_ids": ["span-synthetic"],
            "page": 4,
            "start_offset": 20,
            "end_offset": 20 + len(first["quote_en"]),
        }
    ]
    assert first["position"]["granularity"] == "local_fragments"
    assert analysis["evidence"][0]["translation_status"] == "not_provided"
    assert validate_saved_paper_card_set(result, manifest) == result


def test_anchor_context_preserves_source_and_expands_the_selected_repeated_excerpt():
    manifest = source_manifest()
    source = manifest["sources"][0]
    source["text"] = "Repeated. Repeated.\r\n\n" + ("A" * 1300) + " Last sentence."
    source["text_hash"] = text_hash(source["text"])
    context_source = anchored_model_input(manifest)["sources"][0]
    assert "text" not in context_source
    excerpts = context_source["excerpts"]
    assert "".join(item["text"] for item in excerpts) == source["text"]
    assert all(len(item["text"]) <= 1200 for item in excerpts)
    assert len({item["excerpt_id"] for item in excerpts}) == len(excerpts)

    wire = card_payload()
    wire["cards"][0]["evidence"] = [{"excerpt_id": "q2", "translation_zh": None}]
    wire["cards"][1]["evidence"] = [{"excerpt_id": "q3", "translation_zh": None}]
    result = validate_anchored_card_set(json.dumps(wire), manifest)
    repeated = result["cards"][0]["evidence"][0]
    assert repeated["source_id"] == "s1" and repeated["quote_en"] == "Repeated."
    assert repeated["occurrence_index"] == 1
    assert repeated["position"]["source_offset_start"] == len("Repeated. ")
    assert result["prompt_version"] == ANCHORED_PROMPT_VERSION
    assert (
        validate_saved_paper_card_set(result, manifest, prompt_version=ANCHORED_PROMPT_VERSION)
        == result
    )
    wire["cards"][0]["evidence"][0]["quote_en"] = "Model cannot replace original wording."
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        validate_anchored_card_set(json.dumps(wire), manifest)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["cards"][0]["evidence"][0].update(source_id="s99"),
        lambda p: p["cards"][0]["evidence"][0].update(quote_en="invented quote"),
        lambda p: p["cards"][0]["evidence"][0].update(occurrence_index=1),
        lambda p: p["cards"][0]["evidence"][0].update(occurrence_index=True),
        lambda p: p["cards"][0]["evidence"][0].update(occurrence_index="0"),
        lambda p: p["cards"][0]["evidence"][0].update(position={"page": 1}),
        lambda p: p["cards"][0]["evidence"][0].update(author_statement="not an exact quote"),
        lambda p: p["cards"][0].update(source_refs=[]),
        lambda p: p["cards"][0].update(extra="forbidden"),
        lambda p: p["cards"][0].update(kind="CLAIM"),
        lambda p: p["cards"][0].update(attribution="FACT"),
        lambda p: p["cards"][1].update(attribution="AUTHOR"),
        lambda p: p["cards"][0].update(kind="author_limitation", attribution="ANALYSIS"),
        lambda p: p["cards"][0].update(title_zh="  "),
        lambda p: p["cards"][0].update(title_en=" "),
        lambda p: p["cards"][0].update(body_zh="\n "),
        lambda p: p["cards"][0].update(reading_guide_zh=""),
        lambda p: p["cards"][0]["evidence"][0].update(translation_zh=" "),
        lambda p: p["cards"][0]["evidence"][0].update(quote_en=" "),
        lambda p: p.update(article_overview_zh=" "),
        lambda p: p.update(card_set_intro_zh=" "),
        lambda p: p.update(coverage_notes=[" "]),
        lambda p: p.update(overview_card_ids=["c99"]),
        lambda p: p.update(overview_card_ids=["c1", "c1"]),
        lambda p: p.update(graph={"nodes": [], "edges": []}),
        lambda p: p["cards"][0]["evidence"].append(copy.deepcopy(p["cards"][0]["evidence"][0])),
    ],
)
def test_invalid_or_unbound_card_evidence_is_rejected(mutation):
    payload = card_payload()
    mutation(payload)
    with pytest.raises(ValueError):
        validate_paper_card_set(payload, source_manifest())


def test_duplicate_json_keys_nonfinite_constants_and_duplicate_card_ids_are_rejected():
    manifest = source_manifest()
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        validate_paper_card_set('{"schema_version":"x","schema_version":"bad"}', manifest)
    for constant in ["NaN", "Infinity", "-Infinity"]:
        with pytest.raises(ValueError, match="Non-finite"):
            validate_paper_card_set('{"unexpected":' + constant + "}", manifest)
    payload = card_payload()
    payload["cards"][1]["id"] = payload["cards"][0]["id"]
    with pytest.raises(ValueError, match="Duplicate card ID"):
        validate_paper_card_set(payload, manifest)


def test_required_overview_evidence_references_and_translation_field_are_in_schema():
    schema = paper_card_set_schema()
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    assert set(schema["required"]) == {
        "schema_version",
        "article_overview_zh",
        "overview_card_ids",
        "card_set_intro_zh",
        "coverage_notes",
        "cards",
    }
    evidence = schema["$defs"]["PaperCardEvidence"]
    assert set(evidence["required"]) == {
        "source_id",
        "quote_en",
        "occurrence_index",
        "translation_zh",
    }
    assert evidence["additionalProperties"] is False
    assert set(CARD_KIND_DESCRIPTIONS) == set(get_args(CardKind))
    for kind in get_args(CardKind):
        assert kind in SYSTEM_PROMPT
    assert "author_statement" in SYSTEM_PROMPT and "source_refs" in SYSTEM_PROMPT


def test_model_input_sends_complete_sources_once_without_private_anchors_or_schema_copy():
    manifest = source_manifest()
    text = "long-synthetic-" * 15000
    manifest["sources"][0]["text"] = text
    manifest["sources"][0]["text_hash"] = text_hash(text)
    result = model_input(manifest)
    assert result["sources"][0]["text"] == text
    assert list(result["sources"][0]) == ["source_id", "text", "kind", "chapter_title", "quality"]
    assert len(result["sources"]) == 1
    encoded = json.dumps(result)
    assert encoded.count(text) == 1
    assert "origin" not in encoded and "output_schema" not in result
    assert "chunk-synthetic" not in encoded
    result["source_warnings"].append("Caller edit")
    assert len(manifest["warnings"]) == 1


def test_repeated_local_fragments_map_the_requested_occurrence_by_order():
    manifest, wire = source_manifest(), card_payload()
    text = "Repeat. Repeat."
    source = manifest["sources"][0]
    source.update(text=text, text_hash=text_hash(text), page_start=4, page_end=5)
    source["origin"]["sources"] = [
        {
            "text": "Repeat.",
            "chunk_id": "first",
            "span_ids": ["p4"],
            "page": 4,
            "start_offset": 100,
        },
        {
            "text": "Repeat.",
            "chunk_id": "second",
            "span_ids": ["p5"],
            "page": 5,
            "start_offset": 200,
        },
    ]
    for card in wire["cards"]:
        card["evidence"][0].update(quote_en="Repeat.", occurrence_index=1)
    result = validate_paper_card_set(wire, manifest)
    position = result["cards"][0]["evidence"][0]["position"]
    assert position["source_offset_start"] == 8
    assert position["local_offsets"] == [
        {
            "chunk_id": "second",
            "span_ids": ["p5"],
            "page": 5,
            "start_offset": 200,
            "end_offset": 207,
        }
    ]


def test_cross_fragment_quote_has_both_original_fragments_without_inventing_separator_offset():
    manifest, wire = source_manifest(), card_payload()
    source = manifest["sources"][0]
    source.update(text="AAA BBB", text_hash=text_hash("AAA BBB"), page_start=4, page_end=5)
    source["origin"]["sources"] = [
        {"text": "AAA", "chunk_id": "first", "span_ids": [], "page": 4, "start_offset": 5},
        {"text": "BBB", "chunk_id": "second", "span_ids": [], "page": 5, "start_offset": 9},
    ]
    for card in wire["cards"]:
        card["evidence"][0].update(quote_en="AA BB", occurrence_index=0)
    position = validate_paper_card_set(wire, manifest)["cards"][0]["evidence"][0]["position"]
    assert position["local_offsets"] == [
        {"chunk_id": "first", "span_ids": [], "page": 4, "start_offset": 6, "end_offset": 8},
        {"chunk_id": "second", "span_ids": [], "page": 5, "start_offset": 9, "end_offset": 11},
    ]


def test_normalized_or_ambiguous_local_fragments_keep_source_unit_location_only():
    manifest, wire = source_manifest(), card_payload()
    source = manifest["sources"][0]
    source["origin"]["sources"][0]["text"] = source["text"].replace(" ", "\n", 1)
    source["origin"]["sources"][0].pop("text_hash")
    position = validate_paper_card_set(wire, manifest)["cards"][0]["evidence"][0]["position"]
    assert position["local_offsets"] == []
    assert position["page_start"] == position["page_end"] == 4
    assert position["unit_id"] == "reading-unit-synthetic"
    assert position["granularity"] == "reading_unit"


def test_model_segment_location_preserves_missing_page_without_guessing_from_locator():
    manifest = source_manifest()
    source = manifest["sources"][0]
    manifest["source_kind"] = "model_parse"
    source.update(page_start=None, page_end=None)
    source["origin"] = {"segment_id": "model-segment", "locator": {"model_page": 12}}
    result = validate_paper_card_set(card_payload(), manifest)
    position = result["cards"][0]["evidence"][0]["position"]
    assert position["page_start"] is None and position["page_end"] is None
    assert position["segment_id"] == "model-segment"
    assert position["locator"] == {"model_page": 12}
    assert position["local_offsets"] == [] and position["granularity"] == "model_segment"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(article_overview_zh="Forged overview"),
        lambda p: p["cards"][0].update(body_zh="Forged meaning"),
        lambda p: p["cards"][0].update(id="forged-id"),
        lambda p: p["cards"][0]["evidence"][0]["position"].update(page_start=99),
        lambda p: p["cards"][0]["evidence"][0].update(translation_zh="Forged translation"),
        lambda p: p.update(evidence_status="verified"),
        lambda p: p.update(extra="unapproved"),
        lambda p: p.update(content_hash="rehashed-tampering"),
    ],
)
def test_saved_cards_are_rebuilt_and_do_not_trust_saved_positions_or_rehashed_content(mutation):
    manifest = source_manifest()
    result = validate_paper_card_set(card_payload(), manifest)
    mutation(result)
    with pytest.raises(ValueError, match="differs"):
        validate_saved_paper_card_set(result, manifest)


def test_saved_card_set_revalidates_current_source_and_rejects_missing_wire_draft():
    manifest = source_manifest()
    result = validate_paper_card_set(card_payload(), manifest)
    changed = copy.deepcopy(manifest)
    changed["source_fingerprint"] = "different-source-version"
    with pytest.raises(ValueError, match="differs"):
        validate_saved_paper_card_set(result, changed)
    changed = copy.deepcopy(manifest)
    changed["sources"][0]["text"] += " changed"
    with pytest.raises(ValueError, match="hash"):
        validate_saved_paper_card_set(result, changed)
    result.pop("wire_draft")
    with pytest.raises(ValueError, match="no validated wire draft"):
        validate_saved_paper_card_set(result, manifest)
