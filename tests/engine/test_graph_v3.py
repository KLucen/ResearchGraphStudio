"""v3 compatibility: existing knowledge, bounded projections, independent layouts and recovery."""

import asyncio
import json

import pymupdf
import pytest
import test_knowledge
from researchgraph import extraction
from researchgraph.graph_models import KnowledgeDisplay, SourceAssertion
from researchgraph.knowledge_models import KnowledgeNode
from researchgraph.knowledge_store import KnowledgeStore
from researchgraph.models import Job, Project, now
from researchgraph.providers import MockProvider, ProviderError
from researchgraph.unified_mock import complete
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_engine import client, post
from test_ingest import queue, wait_job
from test_knowledge import apply, batch

seeded = test_knowledge.seeded


def unified(eid):
    return complete(
        {
            "document_version_id": "version",
            "chunk_id": "chunk",
            "allowed_evidence": [
                {
                    "id": eid,
                    "text": "Our method improves accuracy. Research question: can memory help?",
                }
            ],
        }
    )


def save_unified(engine, eid, value=None, key="unified-test"):
    with Session(engine) as session, session.begin():
        return KnowledgeStore(session).apply_unified(
            candidate=value or unified(eid),
            version_id="version",
            paper_id="paper",
            chunk_id="chunk",
            allowed={eid},
            run_id="run",
            key=key,
        )


def test_projection_old_data_is_visible_without_review_or_llm(seeded):
    api, engine, eid = seeded
    apply(engine, batch(eid), eid)
    result = post(api, "/projects/project/graph/projection", {}).json()
    assert {n["kind"] for n in result["nodes"]} == {"Paper", "Concept", "Method", "Claim"}
    assert all("payload" not in n and "quote" not in n for n in result["nodes"])
    claim = next(n for n in result["nodes"] if n["kind"] == "Claim")
    assert claim["review_status"] == "needs_review"
    detail = api.get(claim["detail_ref"]).json()
    assert detail["evidence"] and {n["kind"] for n in detail["related"]} >= {
        "condition",
        "experiment",
        "method",
    }
    seen = set()
    body = {"limit": 2}
    while True:
        page = post(api, "/projects/project/graph/projection", body).json()
        ids = {n["id"] for n in page["nodes"]}
        assert not seen.intersection(ids)
        seen.update(ids)
        if not page["next_cursor"]:
            break
        body["cursor"] = page["next_cursor"]
    assert seen == {n["id"] for n in result["nodes"]}
    focus = post(
        api, "/projects/project/graph/projection", {"focus_id": "paper", "depth": 1, "limit": 3}
    ).json()
    assert len(focus["nodes"]) == 3 and focus["has_more"]


def test_unified_preserves_full_details_and_unknowns(seeded):
    api, engine, eid = seeded
    data = unified(eid)
    claim = next(x for x in data["items"] if x["kind"] == "Claim")
    claim["claim_detail"]["experiments"] = [
        {
            "label": "test protocol",
            "evidence_ids": [eid],
            "findings": [
                {
                    "finding_en": "Accuracy is 81%.",
                    "reported_value": "81",
                    "unit": "%",
                    "metric_en": "accuracy",
                    "evidence_ids": [eid],
                }
            ],
        }
    ]
    first = save_unified(engine, eid, data)
    assert save_unified(engine, eid, data)["node_ids"] == first["node_ids"]
    with Session(engine) as session:
        assert {n.kind for n in session.scalars(select(KnowledgeNode))} >= {
            "claim",
            "method",
            "concept",
            "research_question",
            "condition",
            "experiment",
            "finding",
            "metric",
        }
        assert session.scalar(select(func.count()).select_from(SourceAssertion)) == 1
    graph = post(api, "/projects/project/graph/projection", {}).json()
    assert {n["kind"] for n in graph["nodes"]} == {
        "Paper",
        "Method",
        "Concept",
        "Claim",
        "ResearchQuestion",
    }
    assert any(e["relation"] == "USES_METHOD" and not e["is_dashed"] for e in graph["edges"])
    assert not any(n["review_status"] == "accepted" for n in graph["nodes"])


def test_product_hides_untouched_mock_but_retains_history_and_human_work(seeded):
    api, engine, eid = seeded
    result = save_unified(engine, eid)
    with Session(engine) as session:
        original_ids = set(session.scalars(select(KnowledgeNode.id)))
    graph = post(api, "/projects/project/graph/projection", {"include_test_data": False}).json()
    assert all(n["kind"] == "Paper" for n in graph["nodes"])
    node_id = result["node_ids"][0]
    assert api.get(f"/api/v1/knowledge/nodes/{node_id}").status_code == 200
    with Session(engine) as session, session.begin():
        node = session.get(KnowledgeNode, node_id)
        node.review_status = "accepted"
    graph = post(api, "/projects/project/graph/projection", {"include_test_data": False}).json()
    assert node_id in {n["id"] for n in graph["nodes"]}
    with Session(engine) as session:
        assert set(session.scalars(select(KnowledgeNode.id))) == original_ids


def test_context_papers_do_not_change_primary_cursor_or_infer_science(seeded):
    api, engine, eid = seeded
    save_unified(engine, eid)
    page = post(api, "/projects/project/graph/projection", {"limit": 2}).json()
    context = post(
        api, "/projects/project/graph/projection", {"limit": 2, "include_paper_context": True}
    ).json()
    primary = {n["id"] for n in context["nodes"]} - set(context["context_node_ids"])
    assert primary == {n["id"] for n in page["nodes"]}
    assert len(context["nodes"]) <= 26
    assert all(e["relation"] != "CONTRADICTS" for e in context["edges"])


@pytest.mark.parametrize(
    "attack", ["evidence", "local_ref", "source", "unknown_condition", "origin"]
)
def test_unified_invalid_batch_is_atomic(seeded, attack):
    _, engine, eid = seeded
    data = unified(eid)
    if attack == "evidence":
        data["items"][0]["evidence_ids"] = ["fabricated"]
    elif attack == "local_ref":
        data["links"][0]["target_local_ref"] = "missing"
    elif attack == "source":
        data["document_version_id"] = "another-version"
    elif attack == "origin":
        data["items"][0]["origin"] = "user"
    else:
        next(i for i in data["items"] if i["kind"] == "Claim")["claim_detail"]["conditions"] = [
            {"dimension": "dataset", "state": "unknown", "value_en": "invented"}
        ]
    with pytest.raises(ValueError):
        save_unified(engine, eid, data)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeNode)) == 0
        assert session.scalar(select(func.count()).select_from(KnowledgeDisplay)) == 0


def test_layout_conflicts_scope_and_revision_independence(seeded):
    api, engine, eid = seeded
    save_unified(engine, eid)
    graph = post(api, "/projects/project/graph/projection", {}).json()
    node_id = graph["nodes"][0]["id"]
    body = {
        "expected_version": 0,
        "positions": [{"node_id": node_id, "x": 42, "y": 88, "pinned": True}],
        "zoom": 0.7,
        "pan_x": 20,
        "pan_y": -10,
    }
    saved = post(api, "/projects/project/graph/layout", body)
    assert saved.status_code == 200 and saved.json()["version"] == 1
    assert post(api, "/projects/project/graph/layout", body).status_code == 409
    assert (
        post(api, "/projects/project/graph/projection", {}).json()["graph_revision"]
        == graph["graph_revision"]
    )
    assert api.get("/api/v1/projects/project/graph/layout").json() == saved.json()
    with Session(engine) as session, session.begin():
        session.add(Project(id="other", name="other", description="", created_at=now()))
    assert post(api, "/projects/other/graph/layout", body).status_code == 404
    assert api.get(f"/api/v1/projects/other/graph/nodes/{node_id}").status_code == 404
    assert post(api, "/projects/other/graph/projection", {"focus_id": node_id}).status_code == 404
    body["expected_version"] = 1
    body["positions"].append(dict(body["positions"][0]))
    assert post(api, "/projects/project/graph/layout", body).status_code == 422


@pytest.mark.parametrize(
    "fault", ["client", "timeout", "rate_limit", "invalid_json", "missing_evidence"]
)
def test_unified_seven_batches_resume_without_duplicate_calls(tmp_path, monkeypatch, fault):
    from researchgraph.unified_extraction import plan_sections

    # Seven independently committed chunks; page packing has a separate regression.
    monkeypatch.setattr(
        "researchgraph.unified_extraction.plan_sections",
        lambda spans, **kwargs: plan_sections(spans, budget=1),
    )
    pdf = tmp_path / "seven.pdf"
    with pymupdf.open() as doc:
        for i in range(7):
            page = doc.new_page()
            page.insert_text(
                (40, 60),
                f"Our method uses memory in experiment {i}. Research question: does memory help?",
            )
        doc.save(pdf)
    calls = []

    class Fault(MockProvider):
        fail = True

        async def complete(self, prompt, data, schema):
            assert schema["title"] == "KnowledgeExtractionBatch"
            calls.append(data["chunk_id"])
            if self.fail and len(set(calls)) == 2:
                if fault == "invalid_json":
                    return "not JSON"
                if fault == "missing_evidence":
                    value = complete(data)
                    value["items"][0]["evidence_ids"] = ["invented"]
                    return json.dumps(value)
                raise ProviderError(fault, "Injected failure")
            return await super().complete(prompt, data, schema)

    provider = Fault()
    monkeypatch.setattr(extraction, "provider_for", lambda *_: provider)
    monkeypatch.setattr("researchgraph.unified_extraction.provider_for", lambda *_: provider)
    with client(tmp_path / "data", worker=True) as api:
        project = post(api, "/projects", {"name": "Seven sections"}).json()["id"]
        imported = wait_job(api, queue(api, project, pdf, "seven-import"))
        version = imported["result"]["revision_id"]
        request = {"document_version_id": version, "pipeline": "unified-v3"}
        failed = wait_job(api, post(api, "/knowledge/extract", request, "seven-extract").json())
        assert failed["status"] == "failed", failed
        assert (
            failed["result"]["completed_batches"] == "1"
            and failed["result"]["total_batches"] == "7"
        )
        assert failed["result"]["batches"][1]["retryable"] is (fault in {"timeout", "rate_limit"})
        before = post(api, f"/projects/{project}/graph/projection", {}).json()
        assert len(before["nodes"]) > 1
        provider.fail = False
        resumed = wait_job(api, post(api, f"/jobs/{failed['id']}/retry", key="resume-seven").json())
        assert resumed["status"] == "succeeded" and resumed["result"]["completed_batches"] == "7", (
            resumed
        )
        assert calls.count(calls[0]) == 1 and len(calls) == (
            10 if fault in {"timeout", "rate_limit"} else 8
        )
        repeat = wait_job(api, post(api, "/knowledge/extract", request, "repeat-seven").json())
        assert repeat["status"] == "succeeded" and len(calls) == (
            10 if fault in {"timeout", "rate_limit"} else 8
        )
        graph = post(api, f"/projects/{project}/graph/projection", {}).json()
        ids = {n["id"] for n in graph["nodes"]}
        layout = {
            "expected_version": 0,
            "positions": [{"node_id": next(iter(ids)), "x": 10, "y": 22, "pinned": True}],
            "zoom": 0.8,
            "pan_x": 0,
            "pan_y": 10,
        }
        assert post(api, f"/projects/{project}/graph/layout", layout).status_code == 200
    with client(tmp_path / "data") as api:
        assert {
            n["id"] for n in post(api, f"/projects/{project}/graph/projection", {}).json()["nodes"]
        } == ids
        assert (
            api.get(f"/api/v1/projects/{project}/graph/layout").json()["positions"]
            == layout["positions"]
        )


def test_received_unified_response_can_resume_without_model_call(seeded, monkeypatch):
    _, engine, eid = seeded
    from researchgraph.unified_extraction import run_unified_extraction

    original = KnowledgeStore.apply_unified

    def crash(*args, **kwargs):
        raise asyncio.CancelledError()

    calls = []

    class Count(MockProvider):
        async def complete(self, prompt, data, schema):
            calls.append(1)
            return await super().complete(prompt, data, schema)

    monkeypatch.setattr("researchgraph.unified_extraction.provider_for", lambda *_: Count())
    with Session(engine) as session, session.begin():
        job = session.get(Job, "job")
        job.payload = {
            "document_version_id": "version",
            "provider": "mock",
            "allow_network": False,
            "pipeline": "unified-v3",
        }
    monkeypatch.setattr(KnowledgeStore, "apply_unified", crash)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run_unified_extraction(engine, "job"))
    monkeypatch.setattr(KnowledgeStore, "apply_unified", original)
    asyncio.run(run_unified_extraction(engine, "job"))
    assert len(calls) == 1
    with Session(engine) as session:
        assert session.get(Job, "job").status == "succeeded"
