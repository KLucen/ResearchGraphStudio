"""Anonymized excerpt binding and frozen knowledge wire contract regressions."""

import json

import pytest
from pydantic import ValidationError
from researchgraph.core import KnowledgeError, digest, text_hash
from researchgraph.paper_knowledge import (
    LEGACY_PROMPT_VERSION,
    PREVIOUS_PROMPT_VERSION,
    PROMPT_VERSION,
    isolate_invalid_knowledge_relations,
    knowledge_contract,
    knowledge_model_input,
    validate_knowledge_response,
)


def manifest(*texts: str) -> dict:
    return {
        "paper_title": "Synthetic title",
        "source_kind": "model_parse",
        "sources": [
            {
                "ref": f"s{index}",
                "text": value,
                "text_hash": text_hash(value),
                "kind": "paragraph",
                "chapter_ref": "ch1",
                "chapter_title": "Methods",
                "page_start": None,
                "page_end": None,
                "origin": {"status": "verified", "warnings": ["fixture"]},
            }
            for index, value in enumerate(texts, 1)
        ],
        "warnings": ["synthetic warning"],
        "paper_id": "paper1",
        "source_fingerprint": "fingerprint",
    }


def response(*excerpt_ids: str) -> dict:
    return {
        "schema_version": "paper-knowledge-1",
        "paper_card": {
            "research_question": "",
            "motivation": "",
            "method_summary": "合成方法",
            "contributions": [],
            "main_findings": [],
            "limitations": [],
        },
        "graph": {
            "nodes": [
                {
                    "id": "n1",
                    "type": "METHOD",
                    "label_zh": "合成方法",
                    "label_en": "Synthetic method",
                    "description_zh": "处理匿名夹具的数据。",
                    "basis": "EXPLICIT",
                    "source_refs": [{"excerpt_id": identity} for identity in excerpt_ids],
                }
            ],
            "edges": [],
        },
    }


@pytest.mark.parametrize(
    ("version", "contract_hash", "input_hash"),
    [
        (
            LEGACY_PROMPT_VERSION,
            "70ad2a4d3481191a7040f4d6080698c55871e04ad51fd2c0e04ccfde22f99364",
            "26dd7ab7cc8c74b388ce5939f9e9084980b25b3e2a6f3590dde94576760cd84e",
        ),
        (
            PREVIOUS_PROMPT_VERSION,
            "fc57851e57b5448522355dc464a30f36274f777681e5ba20c252cd0ce5458eca",
            "b25a07790d355350c5f004dc339aacb8393a678c5ccfb247ce80f02f06c54881",
        ),
    ],
)
def test_frozen_earlier_contract_and_input_preserve_hashes(version, contract_hash, input_hash):
    assert knowledge_contract(version)["contract_hash"] == contract_hash
    assert (
        digest(knowledge_model_input(manifest("First line.\nSecond line."), version)) == input_hash
    )


def test_request_sends_verbatim_text_once_and_binds_overlapping_occurrence():
    pages = manifest("A" * 1203, "\u00e9.\n\u00e9.")
    context = knowledge_model_input(pages)
    for source, row in zip(pages["sources"], context["sources"], strict=True):
        assert "text" not in row and "text_hash" not in row
        assert "".join(excerpt["text"] for excerpt in row["excerpts"]) == source["text"]
        assert all(len(excerpt["text"]) <= 1200 for excerpt in row["excerpts"])
    assert context["sources"][0]["excerpts"][-1] == {"excerpt_id": "q2", "text": "AAA"}
    assert context["sources"][1]["excerpts"][-1] == {"excerpt_id": "q4", "text": "\n\u00e9."}
    schema = knowledge_contract()["schema"]
    assert set(schema["$defs"]["KnowledgeExcerptRef"]["properties"]) == {"excerpt_id"}

    raw = response("q2", "q4")
    published = validate_knowledge_response(json.dumps(raw), pages, prompt_version=PROMPT_VERSION)
    refs = published["graph"]["nodes"][1]["source_refs"]
    assert refs == [
        {"source_id": "s1", "quote": "AAA", "occurrence_index": 1200},
        {"source_id": "s2", "quote": "\u00e9.", "occurrence_index": 1},
    ]
    raw["graph"]["nodes"][0]["source_refs"] = refs
    assert validate_knowledge_response(json.dumps(raw), pages) == published


@pytest.mark.parametrize(
    ("ids", "code"),
    [
        (("q99",), "KNOWLEDGE_SOURCE_REF_INVALID"),
        (("q3",), "KNOWLEDGE_SOURCE_REF_INVALID"),
        (("q1", "q1"), "KNOWLEDGE_SOURCE_REF_DUPLICATE"),
    ],
)
def test_v3_rejects_unknown_blank_and_duplicate_excerpts(ids, code):
    pages = manifest("First line.\nSecond line.\n")
    with pytest.raises(KnowledgeError) as raised:
        validate_knowledge_response(
            json.dumps(response(*ids)), pages, prompt_version=PROMPT_VERSION
        )
    assert raised.value.code == code


def test_v3_rejects_mixed_quote_fields_and_changed_frozen_text():
    pages = manifest("Synthetic method.")
    raw = response("q1")
    raw["graph"]["nodes"][0]["source_refs"][0]["quote"] = "Synthetic method."
    with pytest.raises(ValidationError):
        validate_knowledge_response(json.dumps(raw), pages, prompt_version=PROMPT_VERSION)

    pages["sources"][0]["text"] += " Edited."
    with pytest.raises(KnowledgeError) as raised:
        validate_knowledge_response(
            json.dumps(response("q1")), pages, prompt_version=PROMPT_VERSION
        )
    assert raised.value.code == "KNOWLEDGE_SOURCE_CHANGED"


def test_structural_relation_recovery_can_read_new_excerpt_wire():
    pages = manifest("Synthetic method improves retrieval.")
    payload = response("q1")
    graph = payload["graph"]
    graph["nodes"].append(
        {**graph["nodes"][0], "id": "n2", "type": "FINDING", "label_zh": "合成结果"}
    )
    graph["edges"].append(
        {
            "id": "e1",
            "source": "n2",
            "target": "n1",
            "type": "YIELDS",
            "basis": "EXPLICIT",
            "source_refs": [{"excerpt_id": "q1"}],
        }
    )
    raw = json.dumps(payload)
    with pytest.raises(ValidationError):
        validate_knowledge_response(raw, pages, prompt_version=PROMPT_VERSION)

    sanitized, issues = isolate_invalid_knowledge_relations(raw, prompt_version=PROMPT_VERSION)
    assert [issue["path"] for issue in issues] == ["graph.edges[0].type"]
    result = validate_knowledge_response(sanitized, pages, prompt_version=PROMPT_VERSION)
    assert len(result["graph"]["nodes"]) == 3  # Includes the application-owned root.
    assert all(edge["type"] == "HAS_KNOWLEDGE" for edge in result["graph"]["edges"])
