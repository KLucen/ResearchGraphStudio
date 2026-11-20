"""API mutation/idempotency/report metadata integration, with no real provider."""

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient
from researchgraph.knowledge_connection_models import KnowledgeConnectionRun
from researchgraph.knowledge_connections import run_knowledge_connect
from researchgraph.knowledge_extraction_models import KnowledgeExtractionRun
from researchgraph.knowledge_library_api import register_knowledge_library_api
from researchgraph.knowledge_tasks import run_knowledge_extract
from researchgraph.knowledge_workflow_api import register_knowledge_workflow_api
from researchgraph.models import Job
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_knowledge_connections import ConnectionProvider, built_papers, queue_connection
from test_knowledge_extraction import SNAPSHOT, FixtureProvider, draft, model_fixture


def client_for(engine, tmp_path, monkeypatch):
    monkeypatch.setattr("researchgraph.knowledge_workflow_api.snapshot_for", lambda *_: SNAPSHOT)
    app = FastAPI()
    register_knowledge_library_api(app, lambda: engine, tmp_path)
    register_knowledge_workflow_api(app, lambda: engine, tmp_path)
    return TestClient(app)


def test_extract_api_idempotency_and_private_run_fields(tmp_path, monkeypatch):
    values = model_fixture(tmp_path)
    engine, paper, source = values
    client = client_for(engine, tmp_path, monkeypatch)
    options = client.get("/api/v1/knowledge/source-options").json()["items"]
    assert options[0]["paper_id"] == paper
    assert options[0]["sources"][0]["source_id"] == source
    body = {
        "paper_id": paper,
        "source_kind": "model_parse",
        "source_id": source,
        "allow_network": True,
    }
    headers = {"Idempotency-Key": "knowledge-extract-one"}
    first = client.post("/api/v1/knowledge/extract", json=body, headers=headers)
    assert first.status_code == 200, first.text
    again = client.post("/api/v1/knowledge/extract", json=body, headers=headers)
    assert again.json()["id"] == first.json()["id"]
    conflict = client.post(
        "/api/v1/knowledge/extract", json={**body, "allow_network": False}, headers=headers
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"
    asyncio.run(
        run_knowledge_extract(engine, first.json()["id"], tmp_path, provider=FixtureProvider())
    )
    runs = client.get("/api/v1/knowledge/runs").json()
    assert runs["total"] == 1 and runs["items"][0]["status"] == "succeeded"
    assert all(
        name not in runs["items"][0]
        for name in ("raw_response", "source_manifest", "model_snapshot", "policy_json")
    )
    with Session(engine) as db:
        assert db.query(KnowledgeExtractionRun).count() == 1


def test_connect_api_report_read_pinned_note_and_idempotency(tmp_path, monkeypatch):
    engine, versions, _ = built_papers(tmp_path)
    client = client_for(engine, tmp_path, monkeypatch)
    monkeypatch.setattr("researchgraph.knowledge_connections.snapshot_for", lambda *_: SNAPSHOT)
    path = f"/api/v1/knowledge/versions/{versions[1]}/connect"
    headers = {"Idempotency-Key": "knowledge-connect-one"}
    first = client.post(path, json={"allow_network": True}, headers=headers)
    assert first.status_code == 200, first.text
    assert (
        client.post(path, json={"allow_network": True}, headers=headers).json()["id"]
        == first.json()["id"]
    )
    asyncio.run(
        run_knowledge_connect(engine, first.json()["id"], tmp_path, provider=ConnectionProvider())
    )
    reports = client.get("/api/v1/knowledge/reports").json()
    assert reports["total"] == reports["unread"] == 1
    report = reports["items"][0]
    response = client.patch(
        f"/api/v1/knowledge/reports/{report['id']}",
        json={"read": True, "pinned": True, "note": "个人补充观点"},
        headers={"Idempotency-Key": "knowledge-report-edit"},
    )
    assert response.status_code == 200, response.text
    saved = client.get(f"/api/v1/knowledge/reports/{report['id']}").json()
    assert saved["read"] and saved["pinned"] and saved["note"] == "个人补充观点"
    assert saved["relations"] == report["relations"]
    assert client.get("/api/v1/knowledge/reports").json()["unread"] == 0
    assert client.get("/api/v1/knowledge/reports/missing").status_code == 404


def test_failed_run_explicit_retry_api_creates_one_successor(tmp_path, monkeypatch):
    engine, versions, _ = built_papers(tmp_path)
    client = client_for(engine, tmp_path, monkeypatch)
    monkeypatch.setattr("researchgraph.knowledge_connections.snapshot_for", lambda *_: SNAPSHOT)
    first = queue_connection(engine, versions[1])
    asyncio.run(
        run_knowledge_connect(engine, first, tmp_path, provider=ConnectionProvider("invalid JSON"))
    )
    runs = client.get("/api/v1/knowledge/runs").json()["items"]
    failed = next(item for item in runs if item["job_id"] == first)
    path = f"/api/v1/knowledge/runs/{failed['id']}/retry"
    headers = {"Idempotency-Key": "knowledge-retry-one"}
    response = client.post(path, json={"allow_network": True}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["id"] != first
    assert (
        client.post(path, json={"allow_network": True}, headers=headers).json()["id"]
        == response.json()["id"]
    )
    with Session(engine) as db:
        assert db.query(KnowledgeConnectionRun).count() == 2
    asyncio.run(
        run_knowledge_connect(
            engine, response.json()["id"], tmp_path, provider=ConnectionProvider()
        )
    )
    final = client.get("/api/v1/knowledge/runs").json()["items"]
    assert next(item for item in final if item["job_id"] == first)["status"] == "failed"
    assert (
        next(item for item in final if item["job_id"] == response.json()["id"])["status"]
        == "succeeded"
    )


def test_received_extraction_retry_api_uses_valid_job_stage_and_zero_network(tmp_path, monkeypatch):
    import json

    engine, paper, source = model_fixture(tmp_path)
    client = client_for(engine, tmp_path, monkeypatch)
    body = {
        "paper_id": paper,
        "source_kind": "model_parse",
        "source_id": source,
        "allow_network": True,
    }
    first = client.post(
        "/api/v1/knowledge/extract", json=body, headers={"Idempotency-Key": "received-extract"}
    )
    with Session(engine) as db, db.begin():
        run = db.scalar(
            select(KnowledgeExtractionRun).where(
                KnowledgeExtractionRun.job_id == first.json()["id"]
            )
        )
        run_id = run.id
        run.request_sent, run.status = True, "received"
        run.raw_response = json.dumps(draft(run.source_manifest))
        db.get(Job, first.json()["id"]).status = "interrupted"
    response = client.post(
        f"/api/v1/knowledge/runs/{run_id}/retry",
        json={"allow_network": False},
        headers={"Idempotency-Key": "received-extract-retry"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["stage"] == "checking"
    assert response.json()["id"] == first.json()["id"]
    provider = FixtureProvider(RuntimeError("No network"))
    asyncio.run(run_knowledge_extract(engine, response.json()["id"], tmp_path, provider=provider))
    assert provider.calls == 0
