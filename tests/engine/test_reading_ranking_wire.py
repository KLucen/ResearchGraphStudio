"""Keyed P13 contracts and private recovery, using anonymous synthetic claims."""

import copy
import json
from pathlib import Path

import pytest
from researchgraph.knowledge_store import digest
from researchgraph.reading_contracts import SelectionHint
from researchgraph.reading_ranking_wire import (
    PROMPT,
    RankingWireError,
    assert_prompt_contract,
    bind_ranking,
    generated_rules,
    output_schema,
    split_validate,
)
from researchgraph.structured_output import strict_schema


def assessment(priority=50):
    return {
        "recommendation": "suggest_core",
        "reasons": ["main_contribution"],
        "rationale": "The supplied source states this contribution.",
        "priority": priority,
    }


def response(assessments, warnings=None):
    return json.dumps({"assessments": assessments, "warnings": warnings or []})


def context(refs):
    return {
        "claim_aliases": {ref: f"persisted-{ref}" for ref in refs},
        "document_version_id": "test-version",
        "input_revision": 3,
        "coverage_gaps": ["Existing source gap."],
    }


@pytest.mark.parametrize("count", [1, 38, 105])
def test_schema_encodes_exact_coverage_in_keyed_properties_for_observed_scales(count):
    refs = [f"c{i:04d}" for i in range(1, count + 1)]
    schema = output_schema(refs)
    slots = schema["properties"]["assessments"]
    assert list(slots["properties"]) == slots["required"] == refs
    assert slots["additionalProperties"] is False
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["assessments", "warnings"]
    assert "claim_ref" not in schema["$defs"]["ContributionAssessment"]["properties"]
    strict, _ = strict_schema(schema)
    assert strict["properties"]["assessments"]["required"] == refs
    checked = split_validate(response({ref: assessment() for ref in refs}), refs)
    assert checked.complete
    assert list(checked.assessments) == refs
    assert len(bind_ranking(checked.assessments, context(refs))["recommendations"]) == count


def test_dispositions_reasons_and_text_constraints_are_derived_from_domain_dto():
    fields = output_schema()["$defs"]["ContributionAssessment"]["properties"]
    domain = SelectionHint.model_json_schema()["properties"]
    for key in ("recommendation", "reasons", "rationale"):
        assert fields[key] == domain[key]
    assert fields["priority"]["minimum"] == 0
    assert fields["priority"]["maximum"] == 100
    assert fields["priority"]["type"] == "integer"


def test_runtime_rules_hash_exact_request_schema_and_static_prompt_are_checked():
    assert_prompt_contract()
    refs = ["c0003", "c0001"]
    assert digest(output_schema(refs)) in generated_rules(refs)
    prompt = (Path("services/engine/researchgraph/prompts") / (PROMPT + ".md")).read_text(
        encoding="utf-8"
    )
    with pytest.raises(ValueError, match="不一致"):
        assert_prompt_contract(prompt.replace("output_schema_sha256:", "stale:"))
    assert output_schema(refs) != output_schema(list(reversed(refs)))


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (
            '{"assessments":{},"warnings":[],"warnings_note":"private-note"}',
            "RANKING_ENVELOPE_INVALID",
        ),
        ('{"assessments":{},"warnings":[],"warnings":[]}', "RANKING_DUPLICATE_KEY"),
        ('{"assessments":{"c0001":{},"c0001":{}},"warnings":[]}', "RANKING_DUPLICATE_KEY"),
        ('{"assessments":{"c9999":{}},"warnings":[]}', "RANKING_ALIAS_UNKNOWN"),
        ('{"assessments":{},"warnings":[123]}', "RANKING_ENVELOPE_INVALID"),
        ('{"assessments":[],"warnings":[]}', "RANKING_ENVELOPE_INVALID"),
        ('{"assessments":{}}', "RANKING_ENVELOPE_INVALID"),
        ('{"assessments":{},"warnings":[NaN]}', "RANKING_INVALID_JSON"),
        ('{"assessments":', "RANKING_INVALID_JSON"),
        ("[]", "RANKING_INVALID_JSON"),
    ],
)
def test_unsafe_envelopes_have_no_partial_recovery(raw, code):
    with pytest.raises(RankingWireError) as raised:
        split_validate(raw, ["c0001"])
    assert raised.value.code == code
    assert "private-note" not in str(raised.value)
    assert "warnings_note" not in str(raised.value)


@pytest.mark.parametrize(
    ("change", "path", "error_type"),
    [
        ({"priority": 101}, "priority", "less_than_equal"),
        ({"priority": -1}, "priority", "greater_than_equal"),
        ({"priority": 1.2}, "priority", "int_type"),
        ({"priority": True}, "priority", "int_type"),
        ({"priority": "50"}, "priority", "int_type"),
        ({"recommendation": "private-choice"}, "recommendation", "literal_error"),
        ({"reasons": []}, "reasons", "too_short"),
        ({"rationale": ""}, "rationale", "string_too_short"),
        ({"claim_ref": "c0001"}, "<unknown>", "extra_forbidden"),
        ({"private-key-name": "private-text"}, "<unknown>", "extra_forbidden"),
    ],
)
def test_known_slot_errors_remain_private_and_keep_independent_good_slots(change, path, error_type):
    good, bad = assessment(), {**assessment(), **change}
    raw = response({"c0001": good, "c0002": bad})
    checked = split_validate(raw, ["c0001", "c0002", "c0003"])
    assert not checked.complete
    assert checked.assessments == {"c0001": good}
    assert checked.errors["c0002"] == [{"path": path, "type": error_type}]
    assert checked.errors["c0003"] == [{"path": "$", "type": "missing"}]
    assert "private" not in json.dumps(checked.errors)
    with pytest.raises(RankingWireError) as raised:
        bind_ranking(checked.assessments, context(["c0001", "c0002", "c0003"]))
    assert raised.value.code == "RANKING_INCOMPLETE"
    assert raw == response({"c0001": good, "c0002": bad})


def test_repair_revalidates_full_aggregate_and_never_overwrites_good_slots_implicitly():
    refs = ["c0001", "c0002", "c0003"]
    first = split_validate(response({"c0001": assessment(), "c0002": {}}), refs)
    first_copy = copy.deepcopy(first.assessments)
    second = split_validate(response({"c0002": assessment(90), "c0003": assessment()}), refs[1:])
    aggregate = {**first.assessments, **second.assessments}
    bound = bind_ranking(aggregate, context(refs), warnings=["Existing source gap.", "New gap."])
    assert [item["root_claim_id"] for item in bound["recommendations"]] == [
        "persisted-c0002",
        "persisted-c0001",
        "persisted-c0003",
    ]
    assert bound["coverage_gaps"] == ["Existing source gap.", "New gap."]
    assert all(
        "priority" not in item and "claim_ref" not in item for item in bound["recommendations"]
    )
    assert first.assessments == first_copy
    aggregate["c0003"]["priority"] = 200
    with pytest.raises(RankingWireError) as raised:
        bind_ranking(aggregate, context(refs))
    assert raised.value.code == "RANKING_INVALID_ASSESSMENT"


@pytest.mark.parametrize("refs", [[], ["c0001", "c0001"], ["persisted-database-id"], ["c1"]])
def test_only_unique_program_owned_request_aliases_are_accepted(refs):
    with pytest.raises(RankingWireError) as raised:
        output_schema(refs)
    assert raised.value.code == "RANKING_CONTEXT_INVALID"
