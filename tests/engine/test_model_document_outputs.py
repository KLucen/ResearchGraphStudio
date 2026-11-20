"""Postprocess dispatch, source guards and explicit bounded repair integration."""

import asyncio
import json
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from researchgraph.import_plan_models import ImportSession
from researchgraph.lite_usage import aggregate_usage
from researchgraph.model_document_api import (
    execute_document_postprocess,
    queue_model_document_output,
    register_model_document_api,
    synchronize_import_job,
)
from researchgraph.model_document_models import (
    LlmDocumentOutput,
    LlmDocumentParse,
    LlmDocumentSegment,
)
from researchgraph.models import Job, Paper, now
from researchgraph.providers import ProviderError
from researchgraph.storage import read_session
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_model_document_overview import EXAMPLE, _fixture


class Provider:
    name = "synthetic"
    model = "synthetic"
    usage = {"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10}

    def __init__(self, response=None, action=None):
        self.response = EXAMPLE.read_text(encoding="utf-8") if response is None else response
        self.action = action
        self.calls = []

    async def complete(self, prompt, data, schema):
        self.calls.append({"prompt": prompt, "data": data, "schema": schema})
        if self.action:
            self.action()
        return self.response


def _setup(tmp_path, monkeypatch):
    engine, _api, paper_id, parse_id, session_id = _fixture(tmp_path)
    monkeypatch.setattr(
        "researchgraph.model_settings.snapshot_for",
        lambda *args: {"provider": "synthetic", "model": "synthetic", "parameters": {}},
    )
    app = FastAPI()
    register_model_document_api(app, lambda: engine)
    with Session(engine) as db, db.begin():
        job = queue_model_document_output(
            db, session_id, "paper_overview", allow_network=True, parse_id=parse_id
        )
        job_id, output_id = job.id, job.payload["output_id"]
    return engine, TestClient(app), paper_id, parse_id, session_id, job_id, output_id


@pytest.mark.parametrize(
    "field", ["import_session_id", "llm_document_parse_id", "paper_id", "output_id"]
)
def test_worker_rejects_cross_source_payload_before_network_and_preserves_peer(
    tmp_path, monkeypatch, field
):
    engine, _api, _paper_id, _parse_id, session_id, job_id, output_id = _setup(
        tmp_path, monkeypatch
    )
    with Session(engine) as db, db.begin():
        source = db.get(ImportSession, session_id)
        paper2, session2, parse2 = (str(uuid4()) for _ in range(3))
        db.add(Paper(id=paper2, project_id=source.project_id, title="Peer", created_at=now()))
        db.flush()
        db.add(
            ImportSession(
                id=session2,
                project_id=source.project_id,
                source_kind="pdf",
                selection_id="peer",
                source_snapshot={"paper_id": paper2},
                plan={},
                status="succeeded",
                created_at=now(),
                updated_at=now(),
            )
        )
        db.flush()
        db.add(
            LlmDocumentParse(
                id=parse2,
                import_session_id=session2,
                parse_version="llm-document-1",
                modality="text",
                status="succeeded",
                warnings=[],
                created_at=now(),
                updated_at=now(),
            )
        )
        db.flush()
        peer = queue_model_document_output(
            db, session2, "paper_overview", allow_network=True, parse_id=parse2
        )
        peer_output = peer.payload["output_id"]
        peer_job = peer.id
        job = db.get(Job, job_id)
        replacement = {
            "import_session_id": session2,
            "llm_document_parse_id": parse2,
            "paper_id": paper2,
            "output_id": peer_output,
        }[field]
        job.payload = {**job.payload, field: replacement}
    provider = Provider()
    with pytest.raises(ProviderError):
        asyncio.run(execute_document_postprocess(engine, job_id, tmp_path, provider=provider))
    assert provider.calls == []
    with Session(engine) as db:
        assert db.get(Job, job_id).status == "failed"
        assert db.get(Job, peer_job).status == "queued"
        assert db.get(LlmDocumentOutput, peer_output).status == "pending"
        assert not (db.get(LlmDocumentOutput, output_id).usage or {}).get("requests")


def test_source_edit_during_request_preserves_raw_usage_and_blocks_format_repair(
    tmp_path, monkeypatch
):
    engine, api, _paper_id, parse_id, session_id, job_id, output_id = _setup(tmp_path, monkeypatch)

    def edit():
        with Session(engine) as db, db.begin():
            segment = db.scalar(
                select(LlmDocumentSegment).where(
                    LlmDocumentSegment.parse_id == parse_id, LlmDocumentSegment.kind == "paragraph"
                )
            )
            segment.text = "Edited source"
            db.get(LlmDocumentParse, parse_id).updated_at = now()

    provider = Provider(action=edit)
    with pytest.raises(ProviderError):
        asyncio.run(execute_document_postprocess(engine, job_id, tmp_path, provider=provider))
    with Session(engine) as db:
        output = db.get(LlmDocumentOutput, output_id)
        assert output.status == "failed"
        assert output.error_code == "DOCUMENT_OUTPUT_SOURCE_CHANGED"
        assert output.raw_response == provider.response
        assert output.usage["requests"][0]["status"] == "received"
        usage = aggregate_usage(db, db.get(Job, job_id).project_id)
        assert usage.calls == 1 and usage.total_tokens == 10
    response = api.post(
        f"/api/v1/import-sessions/{session_id}/document-outputs/{output_id}/format-repair",
        json={"allow_network": True},
        headers={"Idempotency-Key": "source-edit-repair"},
    )
    assert response.status_code == 409
    assert len(provider.calls) == 1


@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_contract_failure_gets_one_explicit_text_only_repair_with_idempotency(
    tmp_path, monkeypatch, repair_succeeds
):
    engine, api, _paper_id, _parse_id, session_id, job_id, output_id = _setup(tmp_path, monkeypatch)
    invalid = '{"schema_version":"paper_overview_graph.v1","paper_card":{},"graph":{}}'
    provider = Provider(response=invalid)
    with pytest.raises(ProviderError):
        asyncio.run(execute_document_postprocess(engine, job_id, tmp_path, provider=provider))
    endpoint = f"/api/v1/import-sessions/{session_id}/document-outputs/{output_id}/format-repair"
    with Session(engine) as db:
        source = db.get(LlmDocumentOutput, output_id)
        assert source.status == "failed" and source.raw_response == invalid
        assert source.error_code == "MODEL_DOCUMENT_POSTPROCESS_CONTRACT_FAILED"
        assert "paper_card" in json.dumps(source.usage["validation_errors"])
        assert "Test paper" not in json.dumps(source.usage["validation_errors"])
    listed = api.get(f"/api/v1/import-sessions/{session_id}/document-outputs").json()
    assert (
        next(item for item in listed if item["id"] == output_id)["format_repair_available"] is True
    )
    assert (
        api.post(
            endpoint,
            json={"allow_network": False},
            headers={"Idempotency-Key": "repair-without-consent"},
        ).status_code
        == 422
    )
    headers = {"Idempotency-Key": "repair-explicit-once"}
    queued = api.post(endpoint, json={"allow_network": True}, headers=headers)
    assert queued.status_code == 202, queued.text
    listed = api.get(f"/api/v1/import-sessions/{session_id}/document-outputs").json()
    assert (
        next(item for item in listed if item["id"] == output_id)["format_repair_available"] is False
    )
    assert api.post(endpoint, json={"allow_network": True}, headers=headers).json() == queued.json()
    assert (
        api.post(
            endpoint,
            json={"allow_network": True},
            headers={"Idempotency-Key": "repair-second-click"},
        ).status_code
        == 409
    )
    repair_job_id = queued.json()["id"]
    repair = Provider(response=None if repair_succeeds else invalid)
    if repair_succeeds:
        asyncio.run(execute_document_postprocess(engine, repair_job_id, tmp_path, provider=repair))
    else:
        with pytest.raises(ProviderError):
            asyncio.run(
                execute_document_postprocess(engine, repair_job_id, tmp_path, provider=repair)
            )
    assert len(repair.calls) == 1
    sent = repair.calls[0]["data"]
    assert sent["failed_response"] == invalid
    assert "source_context" in sent and "pdf" not in sent
    with Session(engine) as db:
        source = db.get(LlmDocumentOutput, output_id)
        assert source.raw_response == invalid and source.status == "failed"
        child = db.get(LlmDocumentOutput, db.get(Job, repair_job_id).payload["output_id"])
        child_id = child.id
        assert child.status == ("succeeded" if repair_succeeds else "failed")
        assert len(child.usage["requests"]) == 1
        assert child.usage["requests"][0]["purpose"] == "repair"
        usage = aggregate_usage(db, db.get(Job, job_id).project_id)
        assert usage.calls == 2 and usage.retry_count == 1 and usage.total_tokens == 20
    assert (
        api.post(
            endpoint,
            json={"allow_network": True},
            headers={"Idempotency-Key": "repair-after-completion"},
        ).status_code
        == 409
    )
    if not repair_succeeds:
        listed = api.get(f"/api/v1/import-sessions/{session_id}/document-outputs").json()
        assert (
            next(item for item in listed if item["id"] == child_id)["format_repair_available"]
            is False
        )
        child_endpoint = endpoint.replace(output_id, child_id)
        assert (
            api.post(
                child_endpoint,
                json={"allow_network": True},
                headers={"Idempotency-Key": "repair-cannot-chain"},
            ).status_code
            == 409
        )
    with Session(engine) as db:
        assert db.query(Job).count() == 2


def test_cancelled_request_keeps_one_usage_receipt_and_does_not_publish(tmp_path, monkeypatch):
    engine, _api, _paper_id, _parse_id, _session_id, job_id, output_id = _setup(
        tmp_path, monkeypatch
    )

    def cancel():
        with Session(engine) as db, db.begin():
            job = db.get(Job, job_id)
            job.status = "cancelled"
            synchronize_import_job(db, job)

    provider = Provider(action=cancel)
    asyncio.run(execute_document_postprocess(engine, job_id, tmp_path, provider=provider))
    with read_session(engine) as db:
        output = db.get(LlmDocumentOutput, output_id)
        assert db.get(Job, job_id).status == "cancelled"
        assert output.status == "failed" and output.output_json is None
        assert output.raw_response == provider.response
        assert output.usage["requests"][0]["status"] == "received"
        before = aggregate_usage(db, None).model_dump()
        assert before["calls"] == 1 and before["total_tokens"] == 10
        assert aggregate_usage(db, None).model_dump() == before
        assert not db.dirty
    asyncio.run(execute_document_postprocess(engine, job_id, tmp_path, provider=provider))
    assert len(provider.calls) == 1
