"""Prompt catalogues and schema fingerprints share one runtime-derived generator."""

import copy
from pathlib import Path

import pytest
from researchgraph import reading_finish_wire, reading_transport
from researchgraph.reading_contracts import KnowledgeExtractionBatch, check_relation
from researchgraph.reading_prompt_contract import BEGIN, END


@pytest.mark.parametrize("stage", ["P02", "P12", "P13"])
def test_all_new_prompt_contract_blocks_exactly_match_their_runtime_schema(stage):
    if stage == "P02":
        reading_transport.assert_prompt_contract()
        name = reading_transport.PROMPT
        rules = reading_transport.generated_contract()
        schema = reading_transport.output_schema()
    else:
        reading_finish_wire.assert_prompt_contract(stage)
        name = (
            reading_finish_wire.INTEGRATION_PROMPT
            if stage == "P12"
            else reading_finish_wire.RANKING_PROMPT
        )
        rules = reading_finish_wire.generated_rules(stage)
        schema = reading_finish_wire.schema_for(stage)
    prompt = (Path("services/engine/researchgraph/prompts") / (name + ".md")).read_text(
        encoding="utf-8"
    )
    assert prompt.count(BEGIN) == prompt.count(END) == 1
    assert rules in prompt
    assert "Top-level allowed keys: " + ", ".join(schema["properties"]) + "." in rules
    assert "Top-level required keys: " + ", ".join(schema.get("required", [])) + "." in rules
    assert schema == (
        reading_transport.output_schema()
        if stage == "P02"
        else reading_finish_wire.schema_for(stage)
    )


@pytest.mark.parametrize("stage", ["P12", "P13"])
def test_finish_prompt_drift_or_runtime_schema_drift_fails_before_a_model_request(
    stage, monkeypatch
):
    name = (
        reading_finish_wire.INTEGRATION_PROMPT
        if stage == "P12"
        else reading_finish_wire.RANKING_PROMPT
    )
    prompt = (Path("services/engine/researchgraph/prompts") / (name + ".md")).read_text(
        encoding="utf-8"
    )
    with pytest.raises(ValueError, match="不一致"):
        reading_finish_wire.assert_prompt_contract(
            stage, prompt.replace("output_schema_sha256:", "stale:")
        )
    with pytest.raises(ValueError, match="唯一"):
        reading_finish_wire.assert_prompt_contract(stage, prompt + BEGIN)
    original = reading_finish_wire.schema_for

    def changed_schema(requested_stage):
        schema = copy.deepcopy(original(requested_stage))
        schema["properties"]["forbidden_new_field"] = {"type": "string"}
        return schema

    monkeypatch.setattr(reading_finish_wire, "schema_for", changed_schema)
    with pytest.raises(ValueError, match="不一致"):
        reading_finish_wire.assert_prompt_contract(stage, prompt)


def test_relation_matrix_for_both_semantic_association_stages_comes_from_domain_validator():
    definitions = KnowledgeExtractionBatch.model_json_schema()["$defs"]
    kinds = [
        definition["properties"]["kind"]["const"]
        for definition in definitions.values()
        if "const" in definition.get("properties", {}).get("kind", {})
    ]
    relations = definitions["GraphLinkCandidate"]["properties"]["relation"]["enum"]
    for rules in (
        reading_transport.generated_contract(),
        reading_finish_wire.generated_rules("P12"),
    ):
        for relation in relations:
            line = next(
                line for line in rules.splitlines() if line.startswith("- " + relation + ":")
            )
            for source in kinds:
                for target in kinds:
                    try:
                        check_relation(source, target, relation)
                    except ValueError:
                        assert source + "→" + target not in line
                    else:
                        assert source + "→" + target in line


def test_ranking_disposition_and_reason_enums_are_generated_from_selection_contract():
    rules = reading_finish_wire.generated_rules("P13")
    properties = reading_finish_wire.schema_for("P13")["$defs"]["ContributionHint"]["properties"]
    for value in properties["recommendation"]["enum"]:
        assert value in rules
    for value in properties["reasons"]["items"]["enum"]:
        assert value in rules
    assert "claim_ref*" in rules and "root_claim_id" not in rules


def test_unknown_semantic_stage_cannot_silently_pick_a_different_prompt():
    with pytest.raises(ValueError, match="未知"):
        reading_finish_wire.generated_rules("P14")
