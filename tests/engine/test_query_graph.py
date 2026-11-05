"""Query graph tests use synthetic production-labelled rows, never a real provider."""

import copy
import json

import pytest
import test_knowledge
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeNode, ModelRun, NodeEvidence
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest
from researchgraph.models import AttachmentRevision, Chunk, Job, Paper, Project, now
from researchgraph.query_graph import eligible_nodes, expand_graph
from researchgraph.reading_models import CandidateMetadata, ReadingPreference
from researchgraph.reasoning_context import model_context, node_context
from researchgraph.reasoning_contracts import ComparabilityReport, RelationInference
from researchgraph.reasoning_models import ReasoningAttempt, RelationAssertion
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_reading_extraction import candidate_batch, save

seeded = test_knowledge.seeded


def production(engine, eid, data=None):
    save(engine, eid, data)
    with Session(engine) as session, session.begin():
        session.get(ModelRun, "run").provider = "synthetic-production-no-network"
        return {n.payload["local_ref"]: n.id for n in session.scalars(select(KnowledgeNode))}


def second_paper(engine, *, condition=None, citation=False):
    with Session(engine) as session, session.begin():
        session.add(Paper(id="paper2", project_id="project", title="Synthetic2", created_at=now()))
        session.flush()
        session.add(
            AttachmentRevision(
                id="version2",
                paper_id="paper2",
                sha256="d" * 64,
                parser_version="synthetic",
                page_count=1,
                warnings=[],
                created_at=now(),
            )
        )
        session.flush()
        original = session.get(Chunk, "paragraph")
        session.add(
            Chunk(
                id="paragraph2",
                revision_id="version2",
                page_index=0,
                page_label="1",
                block_index=0,
                text=original.text,
                bbox=original.bbox,
            )
        )
        session.add(
            Job(
                id="job2",
                kind="knowledge_extract",
                project_id="project",
                status="succeeded",
                attempt=1,
                created_at=now(),
                updated_at=now(),
            )
        )
        session.flush()
        KnowledgeStore(session).ensure_document("version2")
        eid = session.scalar(
            select(EvidenceSpan.id).where(EvidenceSpan.document_version_id == "version2")
        )
        session.add(
            ModelRun(
                id="run2",
                job_id="job2",
                document_version_id="version2",
                provider="synthetic-production-no-network",
                model="synthetic",
                prompt_name="P02_reading_extract",
                prompt_hash="b" * 64,
                schema_version="reading-1.0",
                input_hash="c" * 64,
                parameters={},
                status="succeeded",
                raw_output="{}",
                created_at=now(),
            )
        )
        session.flush()
        data = candidate_batch(eid, "version2", "chunk2")
        if condition:
            data["items"][-1].update(condition)
        if citation:
            for item in data["items"]:
                item["origin"] = "citation_report"
        KnowledgeStore(session).reading().apply_candidates(
            candidate=data,
            version_id="version2",
            paper_id="paper2",
            chunk_id="chunk2",
            allowed={eid},
            run_id="run2",
            key="second-synthetic-paper",
        )
        return {
            n.payload["local_ref"]: n.id
            for n in session.scalars(
                select(KnowledgeNode).where(KnowledgeNode.paper_id == "paper2")
            )
        }


def test_all_candidates_ignore_canvas_selection_and_mock_default_is_excluded(seeded):
    _, engine, eid = seeded
    save(engine, eid)
    with Session(engine) as session:
        assert eligible_nodes(session, "project", []) == []
    with Session(engine) as session, session.begin():
        session.get(ModelRun, "run").provider = "synthetic-production-no-network"
        nid = session.scalar(select(KnowledgeNode.id))
        session.add(ReadingPreference(node_id=nid, action="exclude_core", reason="synthetic"))
    with Session(engine) as session:
        assert len(eligible_nodes(session, "project", [])) == 4
        result = expand_graph(session, "project", [], [], ["paragraph"])
        assert len(result["nodes"]) == 4 and not session.new and not session.dirty
        assert result["comparison"] == []


@pytest.mark.parametrize("role", ["references", "header", "footer", "page_header", "page_footer"])
def test_reference_and_running_material_candidates_are_excluded_before_ranking(seeded, role):
    from researchgraph.knowledge_models import Section
    from researchgraph.query_retrieval import retrieve

    _, engine, eid = seeded
    production(engine, eid)
    with Session(engine) as session, session.begin():
        span = session.get(EvidenceSpan, eid)
        session.get(Section, span.section_id).role = role
    with Session(engine) as session, session.begin():
        assert eligible_nodes(session, "project", []) == []
        result = retrieve(session, "project", "accuracy", [])
        assert not any(h["source_kind"] == "knowledge" for h in result["hits"])
        assert result["graph"]["nodes"] == []


@pytest.mark.parametrize("excluded_level", ["block", "ancestor_section"])
def test_structured_parse_exclusion_also_filters_knowledge_and_support(seeded, excluded_level):
    from researchgraph.structure_models import DocumentParse
    from test_query_security import source_parse

    _, engine, eid = seeded
    production(engine, eid)
    artifact_id = source_parse(engine)
    with Session(engine) as session, session.begin():
        artifact = session.get(DocumentParse, artifact_id)
        data = copy.deepcopy(artifact.data)
        if excluded_level == "block":
            data["blocks"][0]["excluded"] = True
        else:
            data["sections"][0]["parent_id"] = "parent"
            data["sections"].append(
                {
                    "id": "parent",
                    "parent_id": None,
                    "title": "References",
                    "role": "references",
                    "level": 0,
                    "excluded": True,
                }
            )
        artifact.data = data
    with Session(engine) as session:
        assert eligible_nodes(session, "project", []) == []


@pytest.mark.parametrize(
    "fault", ["quarantined", "rejected", "superseded", "old", "quote", "extra", "paper"]
)
def test_invalid_candidates_are_excluded_before_expansion(seeded, fault):
    _, engine, eid = seeded
    ids = production(engine, eid)
    with Session(engine) as session, session.begin():
        node = session.get(KnowledgeNode, ids["c"])
        if fault == "quarantined":
            session.get(CandidateMetadata, node.id).validation_status = "quarantined"
        elif fault in {"rejected", "superseded"}:
            node.review_status = fault
        elif fault == "old":
            node.issues = ["new_document_version_available"]
        elif fault == "quote":
            session.get(EvidenceSpan, eid).quote = "forged quote"
        elif fault == "extra":
            node.payload = {**node.payload, "unexpected": "not a valid candidate"}
        else:
            session.add(Paper(id="wrong", project_id="project", title="wrong", created_at=now()))
            session.flush()
            node.paper_id = "wrong"
    with Session(engine) as session:
        assert ids["c"] not in {n.id for n in eligible_nodes(session, "project", [])}
        with pytest.raises(KnowledgeError) as error:
            expand_graph(session, "project", [], [ids["c"]], [])
        assert error.value.code == "QUERY_SEED_INVALID"


def test_scope_errors_and_unrelated_chunk_never_infer_membership(seeded):
    _, engine, eid = seeded
    production(engine, eid)
    with Session(engine) as session, session.begin():
        session.add(Project(id="other", name="other", description="", created_at=now()))
        session.add(
            Chunk(
                id="unrelated",
                revision_id="version",
                page_index=0,
                page_label="1",
                block_index=1,
                text="same method",
                bbox=[0, 0, 1, 1],
            )
        )
    with Session(engine) as session:
        with pytest.raises(KnowledgeError, match="论文不属于"):
            eligible_nodes(session, "other", ["paper"])
        assert not expand_graph(session, "project", [], [], ["unrelated"])["nodes"]


def test_shared_member_returns_all_roots_without_creating_units(seeded):
    _, engine, eid = seeded
    data = candidate_batch(eid)
    extra = copy.deepcopy(data["items"][0])
    extra.update(
        local_ref="c2", statement={"original": "A distinct author conclusion", "language": "en"}
    )
    data["items"].append(extra)
    data["links"].append(
        dict(
            source_local_ref="c2",
            target_local_ref="m",
            relation="ASSOCIATED_METHOD",
            evidence_ids=[eid],
        )
    )
    ids = production(engine, eid, data)
    with Session(engine) as session:
        result = expand_graph(session, "project", [], [ids["m"]], [])
        assert {p["root_id"] for p in result["paths"]} == {ids["c"], ids["c2"]}
        assert {p["node_id"] for p in result["paths"] if p["root_id"] == ids["c"]} == set(
            ids.values()
        ) - {ids["c2"]}
        assert all(p["unit_ids"] == [] for p in result["paths"])
        assert not session.new and not session.dirty


def test_complete_closure_more_than_100_nodes_and_retrieval_only_units(seeded):
    _, engine, eid = seeded
    for batch_number in range(2):
        data = candidate_batch(eid)
        data["items"] = [data["items"][0]] + [
            dict(
                local_ref=f"m{i}",
                kind="Method",
                label={"original": f"method {batch_number}-{i}", "language": "en"},
                summary={"original": f"method {batch_number}-{i}", "language": "en"},
                origin="paper_author",
                evidence_ids=[eid],
                method_role="used",
            )
            for i in range(60)
        ]
        data["links"] = [
            dict(
                source_local_ref="c",
                target_local_ref=f"m{i}",
                relation="ASSOCIATED_METHOD",
                evidence_ids=[eid],
            )
            for i in range(60)
        ]
        save(engine, eid, data, key=f"large-{batch_number}")
    with Session(engine) as session, session.begin():
        session.get(ModelRun, "run").provider = "synthetic-production-no-network"
        reading = KnowledgeStore(session).reading()
        reading.form_units("version", reading.snapshot("version"), "synthetic-form-units")
    with Session(engine) as session:
        claim = session.scalar(select(KnowledgeNode.id).where(KnowledgeNode.kind == "claim"))
        result = expand_graph(session, "project", [], [claim], [])
        assert len(result["nodes"]) == 121 and len(result["associations"]) == 120
        assert len(result["paths"]) == 121 and all(p["unit_ids"] for p in result["paths"])


@pytest.mark.parametrize("state", ["known", "unknown", "not_applicable", "conflicting"])
def test_condition_four_states_and_missing_values_remain_conservative(seeded, state):
    _, engine, eid = seeded
    a = production(engine, eid)
    condition = {"state": state, "value": None, "unit": None}
    if state == "known":
        condition["value"] = {"original": "3", "language": "en"}
    elif state == "conflicting":
        condition["alternatives"] = [
            {"value": {"original": v, "language": "en"}, "evidence_ids": []} for v in ("3", "4")
        ]
    if state == "conflicting":
        # Construct after second paper records exist, then amend exact valid DTO/source refs.
        b = second_paper(engine)
        with Session(engine) as session, session.begin():
            node = session.get(KnowledgeNode, b["d"])
            refs = list(
                session.scalars(
                    select(NodeEvidence.evidence_id).where(NodeEvidence.node_id == node.id)
                )
            )
            condition["alternatives"] = [
                {"value": {"original": v, "language": "en"}, "evidence_ids": refs}
                for v in ("3", "4")
            ]
            node.payload = {**node.payload, **condition}
            node.known_state, node.value = state, None
    else:
        b = second_paper(engine, condition=condition)
    with Session(engine) as session:
        result = expand_graph(session, "project", [], [a["c"], b["c"]], [])
        actual = next(c for c in result["conditions"] if c["node_id"] == b["d"])
        assert actual["state"] == state
        assert result["comparison"][0]["overall"] == "unknown"
        assert result["comparison"][0]["dimensions"][0]["comparison"] == (
            "same" if state == "known" else "unknown"
        )
        if state in {"unknown", "not_applicable"}:
            assert actual["value"] is actual["unit"] is None


def test_units_and_attribution_are_not_silently_normalized(seeded):
    _, engine, eid = seeded
    a = production(engine, eid)
    b = second_paper(engine, condition={"unit": "cm"}, citation=True)
    with Session(engine) as session:
        result = expand_graph(session, "project", [], [a["c"], b["c"]], [])
        assert result["comparison"][0]["authorship_match"] is False
        dimension = result["comparison"][0]["dimensions"][0]
        assert (
            dimension["comparison"] == "unknown"
            and dimension["reason"] == "unit_mismatch_no_conversion"
        )
        assert {n["authorship"] for n in result["nodes"]} == {"paper_author", "cited_other"}


@pytest.mark.parametrize(
    "question,expected_kinds,expected_roots",
    [
        ("pressuremarker", {"condition", "method", "experiment"}, 2),
        ("metricmarker", {"metric", "finding", "experiment"}, 1),
        ("rootmarker", {"experiment", "finding", "metric", "limitation"}, 1),
        ("limitationmarker", {"limitation", "condition", "method"}, 2),
        ("methodmarker", {"method", "condition", "limitation"}, 2),
        ("citedmarker", {"method", "condition", "limitation"}, 1),
    ],
)
def test_six_fixed_questions_compare_text_seeds_with_complete_graph_support(
    seeded, question, expected_kinds, expected_roots
):
    """Six explicit graph gold cases, not an estimate of real scientific accuracy."""
    from researchgraph.query_retrieval import retrieve

    _, engine, eid = seeded
    data = candidate_batch(eid)

    def source(word):
        return {"original": word, "language": "en"}

    for item, marker in zip(
        data["items"],
        ["rootmarker", "methodmarker", "findingmarker", "pressuremarker"],
        strict=True,
    ):
        item["label"] = item["summary"] = source(marker)
    data["items"][0]["statement"] = source("rootmarker")
    data["items"][2]["result"] = source("findingmarker")
    for ref, kind, marker, extra in [
        ("e", "Experiment", "protocolmarker", {"protocol": source("protocolmarker")}),
        ("metric", "Metric", "metricmarker", {"unit": "%"}),
        ("limit", "Limitation", "limitationmarker", {"limitation_type": "scope"}),
        (
            "c2",
            "Claim",
            "citedmarker",
            {
                "statement": source("citedmarker"),
                "contribution_type": "background",
                "modality": "asserted",
            },
        ),
    ]:
        data["items"].append(
            dict(
                local_ref=ref,
                kind=kind,
                label=source(marker),
                summary=source(marker),
                origin="citation_report" if ref == "c2" else "paper_author",
                evidence_ids=[eid],
                **extra,
            )
        )
    data["links"] = [
        dict(source_local_ref=a, target_local_ref=b, relation=kind, evidence_ids=[eid])
        for a, b, kind in [
            ("c", "e", "SUPPORTED_BY"),
            ("e", "m", "ASSOCIATED_METHOD"),
            ("e", "f", "REPORTS_FINDING"),
            ("f", "metric", "MEASURED_WITH"),
            ("m", "d", "HAS_CONDITION"),
            ("m", "limit", "LIMITED_BY"),
            ("c2", "m", "ASSOCIATED_METHOD"),
        ]
    ]
    ids = production(engine, eid, data)
    with Session(engine) as session, session.begin():
        result = retrieve(session, "project", question, [])
        text_seeds = {h["object_id"] for h in result["hits"] if h["source_kind"] == "knowledge"}
        graph = result["graph"]
        assert len(text_seeds) == 1
        assert expected_kinds <= {n["kind"] for n in graph["nodes"]}
        assert len({p["root_id"] for p in graph["paths"]}) == expected_roots
        assert len(graph["nodes"]) > len(text_seeds)
        if question == "rootmarker":
            metric_path = next(p for p in graph["paths"] if p["node_id"] == ids["metric"])
            assert len(metric_path["association_ids"]) == 3
        if question == "citedmarker":
            root = next(n for n in graph["nodes"] if n["id"] == ids["c2"])
            assert (
                root["authorship"] == "cited_other"
                and root["payload"]["origin"] == "citation_report"
            )
        assert graph["conditions"]


def relation_fixture(engine, a, b):
    with Session(engine) as session, session.begin():
        snapshot = {
            "project_id": "project",
            "source": node_context(session, session.get(KnowledgeNode, a["c"])),
            "target": node_context(session, session.get(KnowledgeNode, b["c"])),
        }
        eids = sorted(
            {e["id"] for side in ("source", "target") for e in snapshot[side]["evidence"]}
        )
        report = dict(
            source_claim_id=a["c"],
            target_claim_id=b["c"],
            topic_overlap="related",
            overall="limited",
            dimensions=[
                dict(
                    name="agents",
                    source_value="3",
                    target_value="3",
                    comparison="same",
                    impact="neutral",
                    evidence_ids=eids,
                )
            ],
            unknown_dimensions=[],
            rationale="synthetic",
        )
        output = dict(
            source_claim_id=a["c"],
            target_claim_id=b["c"],
            decision="PROPOSE_RELATION",
            relation_type="RELATED",
            reason="synthetic",
            evidence_ids=eids,
        )
        wire, aliases = model_context(snapshot)
        reverse = {eid: short for short, eid in aliases.items()}
        original_report = ComparabilityReport.model_validate(report).model_dump(mode="json")
        for dimension in original_report["dimensions"]:
            dimension["evidence_ids"] = [reverse[e] for e in dimension["evidence_ids"]]
        original_output = RelationInference.model_validate(output).model_dump(mode="json")
        original_output["evidence_ids"] = [reverse[e] for e in output["evidence_ids"]]
        wire["required_dimensions"] = sorted(snapshot["source"]["dimensions"])
        for rid, prompt in [("cmp", "P04_compare_conditions"), ("rel", "P05_infer_relation")]:
            if rid == "rel":
                wire["comparability_report"] = original_report
            session.add(
                ModelRun(
                    id=rid,
                    job_id="job",
                    document_version_id="version",
                    provider="synthetic-production-no-network",
                    model="synthetic",
                    prompt_name=prompt,
                    prompt_hash="b" * 64,
                    schema_version="reasoning-1",
                    input_hash=digest(wire),
                    parameters={
                        "input_manifest": {
                            "evidence_aliases": aliases,
                            "snapshot_hash": digest(snapshot),
                        }
                    },
                    status="succeeded",
                    raw_output=json.dumps(original_report if rid == "cmp" else original_output),
                    created_at=now(),
                )
            )
        session.flush()
        session.add(
            ReasoningAttempt(
                id="attempt",
                project_id="project",
                source_id=a["c"],
                target_id=b["c"],
                mode="relation",
                comparison=report,
                output=output,
                snapshot=snapshot,
                snapshot_hash=digest(snapshot),
                model_run_ids=["cmp", "rel"],
                created_at=now(),
            )
        )
        session.flush()
        session.add(
            RelationAssertion(
                id="relation",
                attempt_id="attempt",
                project_id="project",
                source_id=a["c"],
                target_id=b["c"],
                relation_type="RELATED",
                rationale="synthetic",
                evidence_ids=eids,
                review_status="proposed",
                revision=1,
                created_at=now(),
            )
        )


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "NO_DECISION",
        "navigation",
        "revision",
        "evidence",
        "raw_hash",
        "foreign_project",
        "mock",
        "model_raw",
        "model_input",
        "model_source",
    ],
)
def test_scientific_relations_revalidate_frozen_sources_and_never_use_navigation(seeded, fault):
    _, engine, eid = seeded
    a = production(engine, eid)
    b = second_paper(engine)
    relation_fixture(engine, a, b)
    if fault:
        with Session(engine) as session, session.begin():
            relation = session.get(RelationAssertion, "relation")
            if fault in {"NO_DECISION", "navigation"}:
                relation.relation_type = "NO_DECISION" if fault == "NO_DECISION" else "UNIT_MEMBER"
            elif fault == "revision":
                session.get(KnowledgeNode, b["d"]).revision += 1
            elif fault == "evidence":
                relation.evidence_ids = ["unknown"]
            elif fault == "raw_hash":
                session.get(ReasoningAttempt, "attempt").snapshot_hash = "f" * 64
            elif fault == "foreign_project":
                session.add(Project(id="other", name="other", description="", created_at=now()))
                session.flush()
                relation.project_id = "other"
            elif fault == "mock":
                session.get(ModelRun, "rel").provider = "mock"
            elif fault == "model_raw":
                session.get(ModelRun, "rel").raw_output = '{"decision":"NO_DECISION"}'
            elif fault == "model_input":
                session.get(ModelRun, "rel").input_hash = "f" * 64
            else:
                session.get(ModelRun, "rel").document_version_id = "version2"
    with Session(engine) as session:
        result = expand_graph(session, "project", ["paper", "paper2"], [a["c"]], [])
        if fault:
            assert result["relations"] == []
            assert {n["paper_id"] for n in result["nodes"]} == {"paper"}
        else:
            assert result["relations"][0]["id"] == "relation"
            assert {n["paper_id"] for n in result["nodes"]} == {"paper", "paper2"}
        restricted = expand_graph(session, "project", ["paper"], [a["c"]], [])
        assert not restricted["relations"]
        assert not session.new and not session.dirty
