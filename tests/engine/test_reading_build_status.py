import asyncio

import pytest
import test_knowledge
from researchgraph import model_settings, unified_extraction
from researchgraph.knowledge_models import KnowledgeNode, ModelRun
from researchgraph.models import Job
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_engine import post
from test_reading_extraction import save

seeded = test_knowledge.seeded


def test_failed_extraction_retains_candidates_and_can_build_an_explicit_partial_graph(
    seeded, monkeypatch
):
    api, engine, eid = seeded
    save(engine, eid)
    with Session(engine) as session, session.begin():
        old = session.get(Job, "job")
        old.status = "failed"
        old.payload = {"document_version_id": "version", "pipeline": "paper-reading-v1"}
        old.result = {"completed_batches": "6", "total_batches": "12"}
        before = {n.id: n.payload for n in session.scalars(select(KnowledgeNode))}
    status = api.get("/api/v1/papers/paper/graph-selection").json()
    assert status["build"]["candidate_count"] == 4 and status["build"]["published_units"] == 0
    assert status["build"]["extraction_status"] == "failed"
    projection = post(
        api,
        "/projects/project/graph/projection",
        {"view": "paper_backbone", "include_test_data": True},
    ).json()
    assert projection["paper_builds"][0]["candidate_count"] == 4
    assert len(projection["nodes"]) == 1 and projection["coverage_gaps"]
    monkeypatch.setattr(model_settings, "snapshot_for", lambda *args: {"provider": "mock"})
    rebuild = post(
        api,
        "/papers/paper/graph-selection/rebuild",
        {
            "document_version_id": "version",
            "expected_revision": 0,
            "allow_network": True,
        },
        "partial-rebuild",
    )
    assert rebuild.status_code == 202, rebuild.json()
    jid = rebuild.json()["id"]
    with Session(engine) as session, session.begin():
        session.get(Job, jid).status = "running"
    asyncio.run(unified_extraction.run_unified_extraction(engine, jid, reading=True))
    current = api.get("/api/v1/papers/paper/graph-selection").json()
    assert current["units"] and current["build_state"] == "partial"
    assert any("6/12" in gap for gap in current["coverage_gaps"])
    projection = post(
        api,
        "/projects/project/graph/projection",
        {"view": "paper_backbone", "include_test_data": True},
    ).json()
    assert len(projection["nodes"]) > 1
    with Session(engine) as session:
        assert {n.id: n.payload for n in session.scalars(select(KnowledgeNode))} == before
        assert session.get(Job, "job").status == "failed"
        assert all(
            r.prompt_name.startswith(("P12", "P13"))
            for r in session.scalars(select(ModelRun).where(ModelRun.job_id == jid))
        )


@pytest.mark.parametrize("active", [True, False])
def test_rebuild_rejects_active_work_or_empty_candidates(seeded, active):
    api, engine, _ = seeded
    with Session(engine) as session, session.begin():
        job = session.get(Job, "job")
        job.payload = {"document_version_id": "version"}
        job.status = "running" if active else "failed"
    response = post(
        api,
        "/papers/paper/graph-selection/rebuild",
        {
            "document_version_id": "version",
            "expected_revision": 0,
            "allow_network": True,
        },
        "blocked-rebuild",
    )
    assert response.status_code >= 400
    assert ("BUILD_IN_PROGRESS" if active else "NO_CANDIDATES") in response.text
