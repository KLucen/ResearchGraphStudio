"""Reference validation, not application or real-model acceptance."""

import copy
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "schemas"))
import contracts as c  # noqa: E402


def load(name):
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("sample", load("index.json"), ids=lambda x: x["file"])
def test_all_synthetic_examples(sample):
    getattr(c, sample["contract"]).model_validate(load(sample["file"]))


def records():
    request = c.IntegrationRequest.model_validate(load("integration_request.json"))
    return {r.id: r for r in request.candidates}


def test_extraction_whitelist_and_original_language_fallback():
    batch = c.KnowledgeExtractionBatch.model_validate(load("extraction_batch.json"))
    request = c.ExtractionRequest.model_validate(load("extraction_request.json"))
    c.require_allowed_evidence(batch, request)
    assert batch.items[1].label.zh is None and batch.items[1].label.original
    assert batch.items[4].origin == "citation_report"


@pytest.mark.parametrize("field", ["evidence", "version", "chunk"])
def test_extraction_rejects_cross_context(field):
    data = load("extraction_batch.json")
    if field == "evidence":
        data["items"][0]["evidence_ids"] = ["other-batch"]
    else:
        data["document_version_id" if field == "version" else "chunk_id"] = "other"
    with pytest.raises(ValueError):
        c.require_allowed_evidence(
            c.KnowledgeExtractionBatch.model_validate(data),
            c.ExtractionRequest.model_validate(load("extraction_request.json")),
        )


@pytest.mark.parametrize("field", ["id", "review_status", "page_index", "findings_placeholder"])
def test_model_cannot_emit_server_fields_or_placeholders(field):
    data = load("extraction_batch.json")
    data["items"][0][field] = None
    with pytest.raises(ValidationError):
        c.KnowledgeExtractionBatch.model_validate(data)


@pytest.mark.parametrize("mutation", ["unknown_endpoint", "wrong_kind", "duplicate_local_ref"])
def test_extraction_link_and_identity_constraints(mutation):
    data = load("extraction_batch.json")
    if mutation == "unknown_endpoint":
        data["links"][0]["target_local_ref"] = "missing"
    elif mutation == "wrong_kind":
        data["links"][0]["target_local_ref"] = "finding-a"
    else:
        data["items"].append(copy.deepcopy(data["items"][0]))
    with pytest.raises(ValidationError):
        c.KnowledgeExtractionBatch.model_validate(data)


@pytest.mark.parametrize("state", ["unknown", "not_applicable", "conflicting"])
def test_condition_states_cannot_silently_assert_known_value(state):
    data = load("extraction_batch.json")
    data["items"][3]["state"] = state
    with pytest.raises(ValidationError):
        c.KnowledgeExtractionBatch.model_validate(data)


def test_conflicting_condition_retains_alternatives_and_checks_evidence():
    data = load("extraction_batch.json")
    condition = data["items"][3]
    condition.update(
        state="conflicting",
        value=None,
        alternatives=[
            {"value": {"original": "20", "language": "en"}, "evidence_ids": ["ev-1"]},
            {"value": {"original": "30", "language": "en"}, "evidence_ids": ["foreign"]},
        ],
    )
    batch = c.KnowledgeExtractionBatch.model_validate(data)
    with pytest.raises(ValueError, match="out-of-scope"):
        c.require_allowed_evidence(
            batch, c.ExtractionRequest.model_validate(load("extraction_request.json"))
        )


def test_exact_span_includes_hash_and_bounds():
    span = c.EvidenceSpan.model_validate(load("evidence_span.json"))
    source = load("extraction_request.json")["allowed_evidence"][0]["text"]
    assert c.verify_span_exact(span, source)
    assert not c.verify_span_exact(span, source + " changed")
    assert not c.verify_span_exact(span.model_copy(update={"end_offset": len(source) + 1}), source)


def test_partial_table_requires_unresolved_reason():
    data = load("source_table.json")
    data["unresolved_reason"] = None
    with pytest.raises(ValidationError):
        c.SourceTable.model_validate(data)


@pytest.mark.parametrize("kind", ["methodological", "theoretical", "review"])
def test_non_empirical_papers_do_not_require_invented_experiments(kind):
    batch = c.KnowledgeExtractionBatch.model_validate(load(f"extraction_{kind}.json"))
    assert "Claim" in {i.kind for i in batch.items}
    assert not {"Experiment", "Finding"} & {i.kind for i in batch.items}


def test_integration_and_shared_unit_membership():
    proposal = c.PaperIntegrationProposal.model_validate(load("integration_proposal.json"))
    r = records()
    c.validate_integration_context(proposal, r, {"ev-1", "ev-2", "ev-3"}, 7)
    associations = {
        f"assoc-{i}": c.SourceAssociation(
            **a.model_dump(), id=f"assoc-{i}", document_version_id="dv-demo"
        )
        for i, a in enumerate(proposal.associations)
    }
    selection = c.GraphSelection.model_validate(load("graph_selection.json"))
    for unit in selection.units:
        c.validate_unit_memberships(unit, r, associations)
    assert sum("method-a" in {m.member_id for m in u.memberships} for u in selection.units) == 2
    c.validate_selection_context(selection, r)


@pytest.mark.parametrize("error", ["missing", "cross_document", "stale", "non_claim_root"])
def test_integration_context_boundaries(error):
    proposal = c.PaperIntegrationProposal.model_validate(load("integration_proposal.json"))
    r = records()
    revision = 7
    if error == "missing":
        r.pop("method-a")
    elif error == "cross_document":
        r["method-a"].document_version_id = "other"
    elif error == "stale":
        revision = 8
    else:
        proposal.units[0].root_claim_id = "method-a"
    with pytest.raises(ValueError):
        c.validate_integration_context(proposal, r, {"ev-1", "ev-2", "ev-3"}, revision)


def test_membership_requires_resolvable_paths():
    unit = c.KnowledgeUnit.model_validate(load("knowledge_unit.json"))
    with pytest.raises(ValueError, match="unknown unit association"):
        c.validate_unit_memberships(unit, records(), {})


@pytest.mark.parametrize(
    "failure", ["source", "quarantine", "duplicate", "evidence", "blocking", "legacy", "relevance"]
)
def test_automatic_core_quality_gates(failure):
    r = records()
    record = r["claim-a"]
    if failure == "source":
        record.source_status = "invalid_anchor"
    elif failure == "quarantine":
        record.validation_status = "quarantined"
    elif failure == "duplicate":
        record.quality.duplicate_status = "unresolved"
    elif failure == "evidence":
        record.quality.evidence_completeness = "insufficient"
    elif failure == "blocking":
        record.quality.blocking_issues = ["uncertain numerical attribution"]
    elif failure == "legacy":
        record.legacy_review_status = "rejected"
    else:
        record.quality.relevance = "context"
    with pytest.raises(ValueError):
        c.validate_selection_context(
            c.GraphSelection.model_validate(load("graph_selection.json")), r
        )


def test_limited_evidence_needs_caveat_without_human_review():
    r = records()
    r["claim-a"].quality.evidence_completeness = "limited"
    selection = c.GraphSelection.model_validate(load("graph_selection.json"))
    with pytest.raises(ValueError, match="visible caveats"):
        c.validate_selection_context(selection, r)
    r["claim-a"].quality.caveats = ["Only the reported temperature is supported."]
    c.validate_selection_context(selection, r)
    assert r["claim-a"].legacy_review_status is None


def test_unselected_candidate_remains_in_complete_selection_snapshot():
    data = load("graph_selection.json")
    data["entries"] = [e for e in data["entries"] if e["candidate_id"] != "background-a"]
    with pytest.raises(ValueError, match="complete input"):
        c.validate_selection_context(c.GraphSelection.model_validate(data), records())


def test_selection_hint_coverage_and_source():
    request = c.SelectionRequest.model_validate(load("selection_request.json"))
    proposal = c.CoreSelectionProposal.model_validate(load("selection_proposal.json"))
    c.validate_selection_proposal(proposal, request)
    proposal.recommendations.pop()
    with pytest.raises(ValueError):
        c.validate_selection_proposal(proposal, request)


def test_orphan_support_cannot_enter_selection():
    data = load("graph_selection.json")
    data["units"][0]["memberships"] = data["units"][0]["memberships"][:-1]
    with pytest.raises(ValidationError, match="supporting candidates require"):
        c.GraphSelection.model_validate(data)


@pytest.mark.parametrize(
    "mutation", ["paper_support", "orphan", "collapsed_member", "fake_science", "hidden_candidate"]
)
def test_projection_rejects_flat_graph_and_invalid_navigation(mutation):
    data = load("graph_expanded.json")
    if mutation == "paper_support":
        data["edges"][2]["source"] = "paper-demo"
    elif mutation == "orphan":
        data["edges"] = [e for e in data["edges"] if e["target"] != "finding-a"]
    elif mutation == "collapsed_member":
        data["expanded_unit_ids"] = []
    elif mutation == "fake_science":
        data["edges"][0]["epistemic_status"] = "source_reported"
    else:
        data["nodes"][-1]["role"] = "retrieval_only"
    with pytest.raises(ValidationError):
        c.GraphProjection.model_validate(data)


def test_expanded_graph_shares_one_method_without_paper_edge():
    graph = c.GraphProjection.model_validate(load("graph_expanded.json"))
    assert sum(n.id == "method-a" for n in graph.nodes) == 1
    assert sum(e.target == "method-a" for e in graph.edges) == 2
    assert all(e.relation == "HAS_CORE_CLAIM" for e in graph.edges if e.source == "paper-demo")


def test_no_decision_is_not_a_science_relation():
    data = load("relation_no_decision.json")
    data["relation_type"] = "CONTRADICTS"
    with pytest.raises(ValidationError):
        c.RelationInference.model_validate(data)


def test_query_searches_unselected_valid_candidates_but_not_invalid_sources():
    hit = c.RetrievalHit.model_validate(load("retrieval_hit.json"))
    assert hit.graph_role == "retrieval_only"
    assert c.eligible_query_hits([hit]) == [hit]
    assert c.eligible_query_hits([hit.model_copy(update={"legacy_excluded": True})]) == []
    assert c.eligible_query_hits([hit.model_copy(update={"source_status": "invalid_anchor"})]) == []


def test_query_and_wiki_require_paragraph_dependencies():
    for name, contract in [
        ("query_answer.json", c.QueryAnswer),
        ("reading_synthesis.json", c.ReadingSynthesisDraft),
    ]:
        data = load(name)
        data["passages"][0]["dependencies"] = []
        with pytest.raises(ValidationError):
            contract.model_validate(data)
    data = load("query_answer.json")
    data["save"] = True
    with pytest.raises(ValidationError):
        c.QueryAnswer.model_validate(data)


def test_note_opinion_is_separate_from_paper_evidence():
    data = load("query_answer.json")["passages"][0]
    data.update(attribution="user_view", evidence_ids=[])
    with pytest.raises(ValidationError, match="note snapshot"):
        c.GroundedPassage.model_validate(data)
    data["dependencies"] = [
        {"ref_id": "note", "revision": 1, "source_kind": "note", "snapshot_id": "snapshot"}
    ]
    passage = c.GroundedPassage.model_validate(data)
    assert passage.dependencies[0].document_version_id is None


@pytest.mark.parametrize("error", ["stale", "other_source", "missing_evidence"])
def test_future_answers_require_matching_dependency_versions(error):
    passage = c.GroundedPassage.model_validate(load("query_answer.json")["passages"][0])
    allowed = copy.deepcopy(passage.dependencies)
    evidence = {"ev-1": "dv-demo"}
    c.validate_passage_context(passage, allowed, evidence)
    if error == "stale":
        allowed[0].revision += 1
    elif error == "other_source":
        evidence["ev-1"] = "other-document"
    else:
        evidence.clear()
    with pytest.raises(ValueError):
        c.validate_passage_context(passage, allowed, evidence)


def test_committed_stage_requires_checkpoint():
    with pytest.raises(ValidationError):
        c.JobBatchRecord(
            job_id="j",
            batch_id="b",
            input_hash="0" * 64,
            document_version_id="v",
            prompt_version="p",
            schema_version="s",
            model_id="m",
            stage="integrating",
            state="committed",
        )


def test_schema_exports_and_prompt_contracts_agree():
    exported = {p.stem.removesuffix(".schema") for p in (ROOT / "schemas/generated").glob("*.json")}
    assert exported == {contract.__name__ for contract in c.CONTRACTS}
    for contract in c.CONTRACTS:
        actual = json.loads(
            (ROOT / "schemas/generated" / f"{contract.__name__}.schema.json").read_text()
        )
        assert actual == contract.model_json_schema()
    prompts = list((ROOT / "prompts").glob("*.md"))
    assert len(prompts) == 13
    for prompt in prompts:
        content = prompt.read_text(encoding="utf-8")
        output = re.search(r"`output_contract`: `([^`]+)`", content)[1]
        assert output in exported
        assert "`version`: `reading-1.0`" in content


def test_reference_sql_preserves_shared_members_and_published_version_fk():
    db = sqlite3.connect(":memory:")
    db.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE knowledge_nodes(id TEXT PRIMARY KEY);
        CREATE TABLE attachment_revisions(id TEXT PRIMARY KEY);
        CREATE TABLE model_runs(id TEXT PRIMARY KEY);
        INSERT INTO attachment_revisions VALUES('v1'),('v2');
        INSERT INTO knowledge_nodes VALUES('claim-a'),('claim-b'),('method');
    """)
    db.executescript((ROOT / "schemas/sqlite_reference.sql").read_text())
    for unit, claim in [("u1", "claim-a"), ("u2", "claim-b")]:
        db.execute("INSERT INTO reading_unit_versions VALUES(?,1,'v1',?,NULL)", (unit, claim))
        db.execute("INSERT INTO reading_unit_members VALUES(?,1,'method','[\"a\"]')", (unit,))
    assert (
        db.execute("SELECT count(*) FROM reading_unit_members WHERE member_id='method'").fetchone()[
            0
        ]
        == 2
    )
    db.execute("INSERT INTO reading_selections VALUES('s','v1',1,1,'p','standard','complete','[]')")
    db.execute("INSERT INTO reading_active_selections VALUES('v1','s')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO reading_active_selections VALUES('v2','s')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM knowledge_nodes WHERE id='method'")
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert not db.execute("SELECT name FROM sqlite_master WHERE name LIKE '%review%'").fetchall()
    db.close()
