"""Project graph pages cover multiple synthetic papers without losing source context."""

import copy
from collections import Counter

import pytest
import test_knowledge
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeNode, ModelRun
from researchgraph.knowledge_store import KnowledgeStore
from researchgraph.models import AttachmentRevision, Chunk, Job, Paper, now
from researchgraph.reading_models import ReadingSelection
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_engine import post
from test_reading_extraction import candidate_batch

URL = "/projects/project/graph/projection"
BODY = {"view": "paper_backbone", "include_test_data": True, "limit": 60}


@pytest.fixture
def published_papers(seeded):
    api, engine, _ = seeded
    expected = {}
    for index, paper_id in enumerate(("paper", "paper-2", "paper-3")):
        version = "version" if not index else f"version-{index}"
        run_id = "run" if not index else f"run-{index}"
        job_id = "job" if not index else f"job-{index}"
        with Session(engine) as session, session.begin():
            if index:
                session.add(
                    Paper(id=paper_id, project_id="project", title=paper_id, created_at=now())
                )
                session.flush()
                session.add(
                    AttachmentRevision(
                        id=version,
                        paper_id=paper_id,
                        sha256=str(index) * 64,
                        parser_version="synthetic",
                        page_count=1,
                        warnings=[],
                        created_at=now(),
                    )
                )
                session.flush()
                session.add(
                    Chunk(
                        id=f"paragraph-{index}",
                        revision_id=version,
                        page_index=0,
                        page_label="1",
                        block_index=0,
                        text="Synthetic source for project graph pagination.",
                        bbox=[0.0, 0.0, 100.0, 100.0],
                    )
                )
                session.add(
                    Job(
                        id=job_id,
                        kind="knowledge_extract",
                        project_id="project",
                        status="succeeded",
                        created_at=now(),
                        updated_at=now(),
                    )
                )
                session.flush()
                session.add(
                    ModelRun(
                        id=run_id,
                        job_id=job_id,
                        document_version_id=version,
                        provider="mock",
                        model="synthetic",
                        prompt_name="P02_reading_extract",
                        prompt_hash="b" * 64,
                        schema_version="reading-1.0",
                        input_hash="c" * 64,
                        parameters={},
                        status="received",
                        raw_output='{"synthetic":true}',
                        created_at=now(),
                    )
                )
            run = session.get(ModelRun, run_id)
            run.prompt_name, run.schema_version = "P02_reading_extract", "reading-1.0"
            job = session.get(Job, job_id)
            job.status = "succeeded"
            job.payload = {"document_version_id": version, "pipeline": "paper-reading-v1"}
            job.result = {"completed_batches": 1, "total_batches": 1}
            store = KnowledgeStore(session)
            store.ensure_document(version)
            session.flush()
            eid = session.scalar(
                select(EvidenceSpan.id).where(EvidenceSpan.document_version_id == version)
            )
            data = candidate_batch(eid, version)
            for number in range(65):
                method = copy.deepcopy(data["items"][1])
                method["local_ref"] = f"method-{number}"
                method["label"]["original"] = f"Synthetic method {number:03d}"
                data["items"].append(method)
                data["links"].append(
                    dict(
                        source_local_ref="c",
                        target_local_ref=method["local_ref"],
                        relation="ASSOCIATED_METHOD",
                        evidence_ids=[eid],
                    )
                )
            reading = store.reading()
            created = reading.apply_candidates(
                candidate=data,
                version_id=version,
                paper_id=paper_id,
                chunk_id="chunk",
                allowed={eid},
                run_id=run_id,
                key=f"candidates-{paper_id}",
            )
            expected[paper_id] = {paper_id, *created["node_ids"]}
            snapshot = reading.snapshot(version)
            formed = reading.form_units(version, snapshot, f"units-{paper_id}")
            root = next(n.id for n in reading.nodes(version) if n.kind == "claim")
            reading.publish(
                version_id=version,
                snapshot=snapshot,
                unit_ids=formed["unit_ids"],
                proposal={
                    "document_version_id": version,
                    "input_revision": int(snapshot[:12], 16),
                    "recommendations": [
                        {
                            "root_claim_id": root,
                            "recommendation": "suggest_core",
                            "reasons": ["main_contribution"],
                            "rationale": "Synthetic pagination fixture",
                        }
                    ],
                },
                density="standard",
                expected_revision=0,
                key=f"publish-{paper_id}",
            )
    return api, engine, expected


def primary_ids(graph):
    return {n["id"] for n in graph["nodes"]} - set(graph["context_node_ids"])


def assert_closed(graph):
    ids = {n["id"] for n in graph["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in graph["edges"])
    for node in graph["nodes"]:
        if node["graph_role"] == "supporting":
            assert node["paper_id"] in ids
            assert any(e["target"] == node["id"] for e in graph["edges"])


def state(engine):
    with Session(engine) as session:
        return (
            [(n.id, n.revision, n.payload) for n in session.scalars(select(KnowledgeNode))],
            [(s.id, s.snapshot_hash, s.data) for s in session.scalars(select(ReadingSelection))],
            KnowledgeStore(session).graph_revision("project"),
        )


def test_all_papers_share_first_page_and_every_primary_appears_once(published_papers):
    api, engine, expected = published_papers
    assert all(len(ids) > 60 for ids in expected.values())
    original = state(engine)
    graph = post(api, URL, BODY).json()
    assert graph == post(api, URL, BODY).json()
    assert {n["id"] for n in graph["nodes"] if n["kind"] == "Paper"} == expected.keys()
    assert {n["paper_id"] for n in graph["nodes"] if n["graph_role"] == "core"} == expected.keys()
    assert {
        n["paper_id"] for n in graph["nodes"] if n["graph_role"] == "supporting"
    } == expected.keys()
    assert Counter(n["paper_id"] for n in graph["nodes"]) == dict.fromkeys(expected, 20)
    seen = set()
    while True:
        page = primary_ids(graph)
        assert len(page) <= BODY["limit"]
        assert not (page & seen)
        seen |= page
        assert_closed(graph)
        assert graph["build_state"] == "complete" and graph["coverage_gaps"] == []
        assert set(graph["selections"]) == expected.keys()
        assert {b["paper_id"] for b in graph["paper_builds"]} == expected.keys()
        assert graph["has_more"] == bool(graph["next_cursor"])
        if not graph["next_cursor"]:
            break
        graph = post(api, URL, {**BODY, "cursor": graph["next_cursor"]}).json()
    assert seen == set.union(*expected.values())
    assert state(engine) == original


def test_single_paper_pages_and_support_search_keep_parent_context(published_papers):
    api, _, expected = published_papers
    body = {**BODY, "paper_id": "paper-2", "limit": 17}
    graph = post(api, URL, body).json()
    seen = set()
    while True:
        assert {n["paper_id"] for n in graph["nodes"]} == {"paper-2"}
        page = primary_ids(graph)
        assert not seen & page
        seen |= page
        assert_closed(graph)
        if not graph["next_cursor"]:
            break
        graph = post(api, URL, {**body, "cursor": graph["next_cursor"]}).json()
        assert "paper-2" in graph["context_node_ids"]
        assert any(
            n["graph_role"] == "core" and n["id"] in graph["context_node_ids"]
            for n in graph["nodes"]
        )
    assert seen == expected["paper-2"]
    found = post(api, URL, {**body, "kinds": ["Method"], "search": "Synthetic method 060"}).json()
    assert len(primary_ids(found)) == 1 and len(found["nodes"]) == 3
    assert {n["kind"] for n in found["nodes"]} == {"Method", "Claim", "Paper"}
    assert_closed(found)


def test_project_cursor_rejects_filters_and_changed_graph_revision(published_papers):
    api, engine, _ = published_papers
    first = post(api, URL, BODY).json()
    cursor = first["next_cursor"]
    assert cursor
    for change in ({"paper_id": "paper-2"}, {"search": "Synthetic"}, {"limit": 20}):
        response = post(api, URL, {**BODY, **change, "cursor": cursor})
        assert response.status_code == 422 and "CURSOR_STALE" in response.text
    with Session(engine) as session, session.begin():
        KnowledgeStore(session).event("project", "synthetic.graph_changed", {})
    response = post(api, URL, {**BODY, "cursor": cursor})
    assert response.status_code == 422 and "CURSOR_STALE" in response.text


seeded = test_knowledge.seeded
