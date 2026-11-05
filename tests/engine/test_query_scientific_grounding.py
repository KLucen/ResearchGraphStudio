"""P07 v3 source grouping uses self-created data; no scientific quality claims."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
import test_knowledge
from researchgraph import query_answers as answers
from researchgraph.knowledge_store import KnowledgeError, digest
from researchgraph.query_answer_wire import (
    LAYOUT_PROMPT,
    SCIENTIFIC_PROMPT,
    assert_prompt_contract,
    bind_answer,
    scientific_binding,
)
from researchgraph.query_context import build_context, validate_context
from researchgraph.query_models import QueryModelRun, QueryRun
from researchgraph.query_retrieval import retrieve
from researchgraph.query_scientific_grounding import (
    BACKGROUND_NOTICE,
    EXPANSION_NOTICE,
    POLICY,
    citation_closure,
    freeze_guidance,
)
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_query_answers import OfflineProvider, configure, enqueue, prepare, run, view
from test_query_graph import production
from test_query_retrieval import request, science_rows
from test_query_tables import table_source
from test_reading_extraction import candidate_batch

seeded = test_knowledge.seeded


def complete_context(session, *, question="accuracy", kinds=None):
    body = request(question)
    found = retrieve(session, "project", question, [], source_kinds=kinds)
    if kinds:
        body["source_kinds"] = kinds
    return (
        build_context(
            session,
            body,
            found,
            include_layout=True,
            include_scientific_guidance=True,
        ),
        found,
    )


def raw_answer(ref, *, attribution="model_synthesis", text="所述条件下的有据说明。"):
    return json.dumps(
        {
            "passages": [
                {
                    "text": text,
                    "attribution": attribution,
                    "source_refs": [ref],
                    "limitations": [],
                }
            ],
            "limitations": [],
        },
        ensure_ascii=False,
    )


def test_node_only_citation_binds_full_verified_roots_without_changing_raw_or_science(seeded):
    _, engine, eid = seeded
    ids = production(engine, eid)
    with Session(engine) as session:
        before = science_rows(session)
        context, found = complete_context(session)
        assert context["scientific_guidance"]["policy"] == POLICY
        node_ref = next(r["ref"] for r in context["references"] if r["id"] == ids["c"])
        raw = raw_answer(node_ref)
        original = raw
        bound = bind_answer(raw, context, query_id="q", answer_id="a", revision=1)
        refs = {r["ref"]: r for r in context["references"]}
        actual = bound.passages[0].source_refs
        assert actual[0] == node_ref and {refs[r]["type"] for r in actual} == {
            "node",
            "evidence",
            "chunk",
        }
        assert EXPANSION_NOTICE in bound.passages[0].caveats
        assert bound.passages[0].text == json.loads(raw)["passages"][0]["text"]
        audit = scientific_binding(raw, context, bound)
        assert audit["passages"][0]["original_source_refs"] == [node_ref]
        assert audit["passages"][0]["bound_source_refs"] == actual
        assert citation_closure(actual, context) == actual
        assert raw == original and science_rows(session) == before
        assert validate_context(session, context, found)["valid"]


def test_table_row_citation_includes_its_detected_header_group(seeded):
    _, engine, eid = seeded
    table_source(engine, eid)
    with Session(engine) as session:
        context, _ = complete_context(session, question="rowmarker", kinds=["chunk"])
        table = context["scientific_guidance"]["table_groups"][0]
        assert table["status"] == "resolved"
        assert table["header_names"] == ["Method", "Pressure (kPa)"]
        row = next(r["ref"] for r in context["references"] if r["id"] == "paragraph")
        answer = bind_answer(
            raw_answer(row, text="该合成表格报告对应行的压力。"),
            context,
            query_id="q",
            answer_id="a",
            revision=1,
        )
        assert set(answer.passages[0].source_refs) == set(table["source_refs"])
        assert len(table["source_refs"]) == 2


def test_raw_only_source_does_not_invent_table_or_author_roles(seeded):
    _, engine, _ = seeded
    with Session(engine) as session:
        context, _ = complete_context(session, kinds=["chunk"])
        guidance = context["scientific_guidance"]
        assert not guidance["table_groups"] and not guidance["source_roles"]
        assert guidance["undetected_tables"].startswith("unknown")
        assert guidance["formula_meaning"].startswith("not_proved")


def test_background_statement_is_allowed_with_explicit_non_contribution_caveat(seeded):
    _, engine, eid = seeded
    batch = candidate_batch(eid)
    batch["items"][0]["contribution_type"] = "background"
    ids = production(engine, eid, batch)
    with Session(engine) as session:
        context, _ = complete_context(session)
        node_ref = next(r["ref"] for r in context["references"] if r["id"] == ids["c"])
        answer = bind_answer(
            raw_answer(node_ref, attribution="paper_author", text="作者在背景中介绍了这一概念。"),
            context,
            query_id="q",
            answer_id="a",
            revision=1,
        )
        assert answer.passages[0].attribution == "paper_author"
        assert BACKGROUND_NOTICE in answer.passages[0].caveats


@pytest.mark.parametrize("fault", ["role", "table_ref", "unknown_ref"])
def test_guidance_tampering_is_rejected_even_with_rehashed_manifest(seeded, fault):
    _, engine, eid = seeded
    production(engine, eid)
    with Session(engine) as session:
        context, found = complete_context(session)
        changed = deepcopy(context)
        guidance = changed["scientific_guidance"]
        if fault == "role":
            guidance["source_roles"][0]["authorship"] = "unknown"
        elif fault == "table_ref":
            guidance["table_groups"].append({"source_refs": [context["references"][0]["ref"]]})
        else:
            guidance["root_links"][0]["source_refs"].append("S99999")
        changed.pop("input_hash")
        changed["input_hash"] = digest(changed)
        with pytest.raises(KnowledgeError, match="已变化"):
            validate_context(session, changed, found)


def test_unknown_group_ref_cannot_be_bound_to_a_legal_answer(seeded):
    _, engine, eid = seeded
    production(engine, eid)
    with Session(engine) as session:
        context, _ = complete_context(session)
        context["scientific_guidance"]["root_links"][0]["source_refs"].append("S99999")
        with pytest.raises(KnowledgeError, match="来源分组"):
            citation_closure([context["references"][0]["ref"]], context)


def test_validated_node_root_roles_do_not_require_a_graph_projection_entry(seeded):
    _, engine, eid = seeded
    production(engine, eid)
    with Session(engine) as session:
        context, _ = complete_context(session)
        original = context["scientific_guidance"]
        independent_roots = deepcopy(context)
        independent_roots["graph"]["nodes"] = []
        assert freeze_guidance(session, independent_roots) == original
        node = next(r for r in independent_roots["references"] if r["type"] == "node")
        node["payload_hash"] = "0" * 64
        with pytest.raises(KnowledgeError, match="来源分组"):
            freeze_guidance(session, independent_roots)


def test_independent_table_groups_do_not_merge_on_a_shared_header_word():
    context = {
        "references": [{"ref": r} for r in ["row1", "header1", "row2", "header2"]],
        "scientific_guidance": {
            "policy": POLICY,
            "root_links": [],
            "table_groups": [
                {"header_names": ["Method"], "source_refs": ["row1", "header1"]},
                {"header_names": ["Method"], "source_refs": ["row2", "header2"]},
            ],
        },
    }
    assert citation_closure(["row1"], context) == ["row1", "header1"]
    assert citation_closure(["row2"], context) == ["row2", "header2"]


def test_v3_prompt_contract_and_semantic_rules_are_independent_of_legacy_prompts():
    folder = Path(answers.SCIENTIFIC_PROMPT_PATH).parent
    prompt = answers.SCIENTIFIC_PROMPT_PATH.read_text(encoding="utf-8")
    assert_prompt_contract(prompt)
    for marker in (
        "rounds with proposals",
        "not a new",
        "No detected table group means structure is unknown",
        "missing exponent",
        "untested transfer",
    ):
        assert marker in prompt
    assert "scientific_guidance" not in (folder / "P07_query_grounded_v1.md").read_text()
    assert "scientific_guidance" not in (folder / "P07_query_grounded_v2.md").read_text()


def test_v3_execution_audit_is_rederived_and_tamper_rejected(seeded):
    api, engine, eid = seeded
    ids = production(engine, eid)
    configure(engine)
    qid = prepare(api)

    def response(data):
        ref = next(r["ref"] for r in data["evidence_context"]["references"] if r["id"] == ids["c"])
        return raw_answer(ref)

    provider = OfflineProvider(engine, output=response)
    run(engine, enqueue(engine, qid), provider)
    assert view(engine, qid).status == "succeeded" and provider.calls == 1
    with Session(engine) as session, session.begin():
        model = session.scalar(select(QueryModelRun))
        assert model.prompt_name == SCIENTIFIC_PROMPT
        assert model.parameters["scientific_binding"]["passages"][0]["bound_source_refs"]
        params = deepcopy(model.parameters)
        params["scientific_binding"]["passages"][0]["bound_source_refs"] = []
        model.parameters = params
    with Session(engine) as session, pytest.raises(KnowledgeError, match="来源补齐审计"):
        answers.validate_answer(session, "project", qid)
    assert provider.calls == 1


def test_historical_v2_plan_raw_hash_and_zero_call_replay_remain_unchanged(seeded):
    api, engine, eid = seeded
    production(engine, eid)
    configure(engine)
    qid = prepare(api)
    with Session(engine) as session, session.begin():
        query = session.get(QueryRun, qid)
        snapshot = deepcopy(query.snapshot)
        snapshot["context"] = build_context(
            session,
            query.request,
            snapshot["retrieval"],
            model_snapshot=snapshot["model"],
            include_layout=True,
        )
        assert "scientific_guidance" not in snapshot["context"]
        query.snapshot = snapshot
        query.input_hash = snapshot["context"]["input_hash"]
    provider = OfflineProvider(engine)
    run(engine, enqueue(engine, qid), provider)
    before = view(engine, qid).answer.model_dump(mode="json")
    with Session(engine) as session:
        model = session.scalar(select(QueryModelRun))
        assert model.prompt_name == LAYOUT_PROMPT and "scientific_binding" not in model.parameters
        frozen = deepcopy((model.raw_output, model.parameters, model.manifest, model.input_hash))
    enqueue(engine, qid, "v2-replay", continuing=True)
    assert view(engine, qid).answer.model_dump(mode="json") == before and provider.calls == 1
    with Session(engine) as session:
        model = session.scalar(select(QueryModelRun))
        assert (model.raw_output, model.parameters, model.manifest, model.input_hash) == frozen
