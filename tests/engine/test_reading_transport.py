"""The model emits semantics; immutable source identity comes only from trusted input."""

import copy
import json
from pathlib import Path

import pytest
from researchgraph import reading_transport as transport
from researchgraph import reading_wire
from researchgraph.reading_contracts import KnowledgeExtractionBatch
from researchgraph.reading_prompt_contract import BEGIN
from researchgraph.reading_validation import validate_batch
from test_reading_extraction import candidate_batch

CONTEXT = {"document_version_id": "version", "chunk_id": "chunk", "source_language": "en"}


def validate(wire, context=None, allowed=None):
    changes = []
    bound = transport.bind(
        transport.loads(json.dumps(wire, ensure_ascii=False)),
        **(context or CONTEXT),
        changes=changes,
    )
    batch, isolated = validate_batch(json.dumps(bound), allowed or {"ev"})
    return batch, isolated, changes


def test_semantic_transport_has_no_model_owned_source_envelope_and_keeps_domain_schema():
    before = reading_wire.current_output_schema()
    schema = transport.output_schema()
    assert set(schema["properties"]) == {"items", "links", "warnings"}
    assert set(schema["required"]) == {"items", "links"}
    assert not schema["additionalProperties"]
    assert schema["title"] == "ReadingSemanticBatch"
    assert all(field not in schema["properties"] for field in transport.BOUND_FIELDS)
    assert schema["properties"]["items"] == before["properties"]["items"]
    assert schema["properties"]["links"] == before["properties"]["links"]
    assert schema["$defs"]["ConditionCandidate"] == before["$defs"]["ConditionCandidate"]
    schema["$defs"]["ClaimCandidate"]["properties"]["invented"] = {}
    assert reading_wire.current_output_schema() == before  # No mutation of frozen old wire.


def test_source_binding_expands_only_defaults_and_preserves_science_translation_and_links():
    canonical = candidate_batch("ev")
    canonical["items"][0]["summary"] = copy.deepcopy(canonical["items"][0]["statement"])
    canonical["items"][0]["statement"]["zh"] = "仅在三个智能体条件下达到81%。"
    canonical["items"][0]["summary"] = copy.deepcopy(canonical["items"][0]["statement"])
    canonical["items"][2]["baseline"] = {"original": "对照实验72.00%", "language": "zh"}
    wire = transport.fixture(canonical)
    assert not set(wire) & transport.BOUND_FIELDS
    assert "summary" not in wire["items"][0]
    wire["items"][-1]["value"] = "3"  # SourceText shorthand keeps the exact original string.
    original = copy.deepcopy(wire)
    batch, isolated, changes = validate(wire)
    assert batch == KnowledgeExtractionBatch.model_validate(canonical)
    assert not isolated and wire == original
    assert batch.items[0].statement.zh == "仅在三个智能体条件下达到81%。"
    assert batch.items[2].baseline.language == "zh"
    assert {
        c["path"] for c in changes if c["rule"] == "engine-bound-source-v1"
    } == transport.BOUND_FIELDS
    assert {"path": "items.0.summary", "rule": "copy-statement"} in changes
    assert {"path": "items.3.value", "rule": "source-text-string"} in changes
    assert all("version" not in c.values() and "chunk" not in c.values() for c in changes)


@pytest.mark.parametrize("field", sorted(transport.BOUND_FIELDS) + ["metadata", "waiver"])
def test_model_cannot_supply_trusted_context_or_other_envelope_fields(field):
    wire = transport.fixture(candidate_batch("ev"))
    wire[field] = "arbitrary-model-output"
    with pytest.raises(ValueError, match="仅允许"):
        validate(wire)


@pytest.mark.parametrize(
    "fault",
    [
        "missing_items",
        "missing_links",
        "null_items",
        "object_links",
        "null_warnings",
        "item_extra",
        "missing_statement",
        "numeric_source",
        "unknown_evidence",
        "unknown_condition_with_value",
        "conflicting_missing_evidence",
        "null_language",
    ],
)
def test_semantic_protocol_never_weakens_domain_fields_types_or_evidence(fault):
    wire = transport.fixture(candidate_batch("ev"))
    if fault.startswith("missing_") and fault in {"missing_items", "missing_links"}:
        del wire[fault.removeprefix("missing_")]
    elif fault == "null_items":
        wire["items"] = None
    elif fault == "object_links":
        wire["links"] = {}
    elif fault == "null_warnings":
        wire["warnings"] = None
    elif fault == "item_extra":
        wire["items"][0]["unknown_science"] = None
    elif fault == "missing_statement":
        del wire["items"][0]["statement"]
    elif fault == "numeric_source":
        wire["items"][2]["result"] = 81
    elif fault == "unknown_evidence":
        wire["items"][0]["evidence_ids"] = ["outside"]
    elif fault == "unknown_condition_with_value":
        wire["items"][-1]["state"] = "unknown"
    elif fault == "conflicting_missing_evidence":
        condition = wire["items"][-1]
        condition.pop("value")
        condition.update(
            state="conflicting",
            alternatives=[
                {"value": "3", "evidence_ids": ["ev"]},
                {"value": "4", "evidence_ids": ["outside"]},
            ],
        )
    else:
        wire["items"][0]["statement"]["language"] = None
    with pytest.raises(ValueError):
        validate(wire)


@pytest.mark.parametrize(
    "field,value",
    [
        ("document_version_id", ""),
        ("chunk_id", ""),
        ("source_language", ""),
        ("source_language", None),
        ("source_language", "x"),
        ("document_version_id", 7),
    ],
)
def test_binding_rejects_invalid_trusted_context(field, value):
    wire = transport.fixture(candidate_batch("ev"))
    with pytest.raises(ValueError, match="可信抽取上下文"):
        transport.bind(wire, **{**CONTEXT, field: value})


@pytest.mark.parametrize(
    "raw",
    [
        '{"items":[],"items":[],"links":[]}',
        '{"items":[],"it\\u0065ms":[],"links":[]}',
        '{"items":[{"kind":"Claim","kind":"Method"}],"links":[]}',
        '{"items":[],"links":[],"warnings":[NaN]}',
        '{"items":[],"links":[],"warnings":[Infinity]}',
        '{"items":[],"links":[],"warnings":[-Infinity]}',
        '{"items":[],"links":[]',
        '```json\n{"items":[],"links":[]}\n```',
        "[]",
    ],
)
def test_protocol_strict_json_does_not_repair_or_drop_tokens(raw):
    with pytest.raises(ValueError):
        transport.loads(raw)


def test_default_language_is_script_heuristic_with_explicit_source_text_override():
    assert transport.detect_language("The reported result is 81%.") == "en"
    assert transport.detect_language("该结果在指定实验条件下成立。") == "zh"
    assert transport.detect_language("123.4 ± 0.2 %") == "und"
    canonical = candidate_batch("ev")
    canonical["items"][0]["statement"]["language"] = "de"
    wire = transport.fixture(canonical)
    bound = transport.bind(wire, **{**CONTEXT, "source_language": "zh"})
    assert bound["items"][0]["label"]["language"] == "zh"
    assert bound["items"][0]["statement"]["language"] == "de"


@pytest.mark.parametrize("difference", ["explicit_summary", "explicit_language", "changed_text"])
def test_distinct_raw_same_reference_never_becomes_an_exact_duplicate_after_binding(difference):
    canonical = candidate_batch("ev")
    canonical["items"][0]["summary"] = copy.deepcopy(canonical["items"][0]["statement"])
    wire = transport.fixture(canonical)
    duplicate = copy.deepcopy(wire["items"][0])
    if difference == "explicit_summary":
        duplicate["summary"] = copy.deepcopy(duplicate["statement"])
    elif difference == "explicit_language":
        duplicate["statement"]["language"] = "en"
    else:
        duplicate["statement"]["original"] = "Different scientific content"
    wire["items"].append(duplicate)
    with pytest.raises(ValueError, match="原始候选内容不同"):
        transport.bind(wire, **CONTEXT)


def test_only_identical_raw_duplicates_continue_to_full_validation_and_audited_dedup():
    wire = transport.fixture(candidate_batch("ev"))
    wire["items"].append(copy.deepcopy(wire["items"][0]))
    original = copy.deepcopy(wire)
    bound = transport.bind(wire, **CONTEXT)
    removed = []
    batch, isolated = validate_batch(json.dumps(bound), {"ev"}, removed_duplicates=removed)
    assert len(batch.items) == 4 and not isolated
    assert removed == [{"kept_index": 0, "removed_index": 4}]
    assert wire == original
    # Identical duplicates cannot hide a bad original evidence reference.
    bound["items"][0]["evidence_ids"] = ["outside"]
    bound["items"][-1]["evidence_ids"] = ["outside"]
    with pytest.raises(ValueError, match="whitelist"):
        validate_batch(json.dumps(bound), {"ev"}, removed_duplicates=[])


def test_prompt_generated_contract_matches_runtime_schema_and_detects_drift(monkeypatch):
    transport.assert_prompt_contract()
    path = Path("services/engine/researchgraph/prompts") / (transport.PROMPT + ".md")
    prompt = path.read_text(encoding="utf-8")
    assert transport.generated_contract() in prompt
    with pytest.raises(ValueError, match="不一致"):
        transport.assert_prompt_contract(prompt.replace("local_ref*", "invented*", 1))
    with pytest.raises(ValueError, match="唯一"):
        transport.assert_prompt_contract(prompt + BEGIN)
    original = transport.output_schema

    def changed_schema():
        schema = original()
        schema["$defs"]["MethodCandidate"]["required"].append("unreviewed_new_field")
        return schema

    monkeypatch.setattr(transport, "output_schema", changed_schema)
    with pytest.raises(ValueError, match="不一致"):
        transport.assert_prompt_contract(prompt)
