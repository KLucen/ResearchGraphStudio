import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from researchgraph import model_document_api
from researchgraph.import_plan_models import ImportPlanItem, ImportSession
from researchgraph.model_document_api import (
    _DocumentRequestProgress,
    _safe_document_request_metadata,
    execute_document_parse,
)
from researchgraph.model_document_models import LlmDocumentParse, LlmDocumentSegment
from researchgraph.models import Base, Job, Project, now
from researchgraph.providers import ConfiguredProvider, DocumentRequestCancelled, ProviderError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def document_job(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'diagnostics.sqlite3').as_posix()}")
    Base.metadata.create_all(engine)
    project_id, session_id, job_id = (str(uuid4()) for _ in range(3))
    timestamp = now()
    with Session(engine) as db, db.begin():
        db.add(Project(id=project_id, name="fixture", description="", created_at=timestamp))
        db.add(
            ImportSession(
                id=session_id,
                project_id=project_id,
                source_kind="pdf",
                selection_id="synthetic-selection",
                source_snapshot={"file_name": "synthetic.pdf"},
                plan={"modality": "pdf"},
                status="queued",
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        db.add(
            ImportPlanItem(
                id=str(uuid4()),
                session_id=session_id,
                item_kind="document_parse",
                status="queued",
                config={"modality": "pdf"},
                job_id=job_id,
                attempt=0,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        db.add(
            Job(
                id=job_id,
                kind="llm_document_parse",
                project_id=project_id,
                payload={"import_session_id": session_id, "modality": "pdf"},
                status="running",
                attempt=1,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
    return engine, session_id, job_id


class DiagnosticProvider(ConfiguredProvider):
    def __init__(self, *, failure=None, invalid=False):
        super().__init__(
            base_url="https://example.invalid/v1",
            model="synthetic-vision",
            provider_name="compatible",
            key="synthetic-credential",
            parameters={
                "timeout_seconds": 90,
                "capabilities": {
                    "document_input": "pdf",
                    "document_transport": "chat_file",
                },
            },
        )
        self.failure = failure
        self.invalid = invalid
        self.calls = 0

    async def complete_document(self, payload, schema=None, *, before_send=None, on_progress=None):
        assert before_send is not None and before_send()
        assert on_progress is not None
        self.calls += 1
        self.request_metadata = {
            "transport": "chat-file-v1",
            "phase": "response_headers",
            "request_bytes": 1500,
            "response_bytes": 0,
            "request_sent_seconds": 0.1,
            "read_timeout_seconds": 600,
            "total_timeout_seconds": 1800,
            "connect_timeout_seconds": 15,
            "path": "/private/synthetic-credential.pdf",
            "file_name": "private-synthetic-credential.pdf",
            "body": {"file_data": "synthetic-credential"},
            "started_at": "synthetic-credential",
        }
        on_progress("document_uploading", self.request_metadata)
        on_progress("document_waiting", self.request_metadata)
        await asyncio.sleep(0)
        if self.failure:
            self.request_metadata.update(
                timeout_phase=self.failure,
                timeout_type="ReadTimeout" if self.failure != "total" else "TimeoutError",
                elapsed_seconds=600.1,
            )
            if self.failure == "unexpected":
                raise RuntimeError("private synthetic-credential")
            raise ProviderError(
                "timeout", "等待模型文档响应超时（600 秒）", timeout_phase=self.failure
            )
        self.request_metadata.update(phase="completed", response_bytes=1234, elapsed_seconds=0.2)
        on_progress("document_receiving", self.request_metadata)
        if self.invalid:
            return "invalid synthetic-credential JSON"
        return json.dumps(
            {
                "parse_version": "llm-document-1",
                "modality": "pdf",
                "segments": [
                    {
                        "chapter_ref": "intro",
                        "chapter_title": "Introduction",
                        "kind": "paragraph",
                        "text": "Anonymous fixture.",
                    }
                ],
            }
        )


@pytest.mark.parametrize("failure_phase", ["response_headers", "response_body", "total"])
def test_timeout_failure_retains_safe_request_diagnostics(tmp_path, failure_phase):
    engine, session_id, job_id = document_job(tmp_path)
    provider = DiagnosticProvider(failure=failure_phase)
    with pytest.raises(ProviderError, match="600 秒"):
        asyncio.run(execute_document_parse(engine, job_id, tmp_path, provider=provider))

    with Session(engine) as db:
        job = db.get(Job, job_id)
        assert job.status == "failed"
        details = job.result["document_request"]
        assert details["timeout_phase"] == failure_phase
        assert details["elapsed_seconds"] == 600.1
        assert details["read_timeout_seconds"] == 600
        assert details["request_bytes"] == 1500
        assert datetime.fromisoformat(details["started_at"]).tzinfo is not None
        assert "synthetic-credential" not in json.dumps(job.result)
        assert {"body", "path", "file_name"}.isdisjoint(details)
        parse = db.query(LlmDocumentParse).one()
        assert parse.provider_id == "compatible" and parse.model_id == "synthetic-vision"
        assert parse.started_at == details["started_at"]
        assert parse.started_at <= parse.finished_at
        assert parse.error_code == "MODEL_DOCUMENT_PROVIDER_ERROR"
        assert parse.raw_response is None
        assert db.get(ImportSession, session_id).status == "failed"
        assert db.query(LlmDocumentSegment).count() == 0
    # Wrapper's fallback must not overwrite the original error or add a second parse.
    asyncio.run(execute_document_parse(engine, job_id, tmp_path, provider=provider))
    assert provider.calls == 1
    with Session(engine) as db:
        assert db.query(LlmDocumentParse).count() == 1


def test_success_keeps_final_diagnostics_beside_parse_result(tmp_path):
    engine, _, job_id = document_job(tmp_path)
    provider = DiagnosticProvider()
    asyncio.run(execute_document_parse(engine, job_id, tmp_path, provider=provider))
    with Session(engine) as db:
        job = db.get(Job, job_id)
        details = job.result["document_request"]
        assert job.status == "succeeded" and job.result["segment_count"] == 1
        assert job.result["parse_id"] == db.query(LlmDocumentParse).one().id
        assert details["response_bytes"] == 1234 and details["phase"] == "completed"
        assert "synthetic-credential" not in json.dumps(job.result)
        assert db.query(LlmDocumentParse).one().started_at == details["started_at"]


@pytest.mark.parametrize("failure_step", ["provider", "schema", "publication"])
def test_unexpected_or_schema_failure_keeps_completed_transport_metadata(
    tmp_path, monkeypatch, failure_step
):
    engine, _, job_id = document_job(tmp_path)
    provider = DiagnosticProvider(
        failure="unexpected" if failure_step == "provider" else None,
        invalid=failure_step == "schema",
    )
    if failure_step == "publication":

        def fail(*args, **kwargs):
            raise OSError("private synthetic-credential")

        monkeypatch.setattr(model_document_api, "materialize_document_parse", fail)
    with pytest.raises((RuntimeError, ProviderError, OSError)):
        asyncio.run(execute_document_parse(engine, job_id, tmp_path, provider=provider))
    with Session(engine) as db:
        job = db.get(Job, job_id)
        assert job.status == "failed"
        assert job.result["document_request"]["request_bytes"] == 1500
        assert "synthetic-credential" not in json.dumps(job.result)
        assert "synthetic-credential" not in job.error
        assert db.query(LlmDocumentParse).count() == 1


def test_progress_throttles_same_stage_and_cannot_overwrite_terminal_state(tmp_path, monkeypatch):
    engine, _, job_id = document_job(tmp_path)
    ticks = iter([10.0, 10.1, 10.2, 11.3, 11.4])
    monkeypatch.setattr(model_document_api, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    progress = _DocumentRequestProgress(engine, job_id)
    progress("document_rendering", {"rendered_pages": 0, "page_count": 3})
    progress("document_rendering", {"rendered_pages": 1, "page_count": 3})
    with Session(engine) as db:
        assert db.get(Job, job_id).result["document_request"]["rendered_pages"] == 0
    progress("document_waiting", {"rendered_pages": 3, "page_count": 3})
    with Session(engine) as db:
        assert db.get(Job, job_id).stage == "document_waiting"
        assert db.get(Job, job_id).result["document_request"]["rendered_pages"] == 3
    progress("document_waiting", {"elapsed_seconds": 1.2})
    with Session(engine) as db, db.begin():
        job = db.get(Job, job_id)
        job.status, job.stage = "cancelled", "cancelled"
        original = job.result
    with pytest.raises(DocumentRequestCancelled):
        progress("document_receiving", {"response_bytes": 100})
    with Session(engine) as db:
        job = db.get(Job, job_id)
        assert job.status == "cancelled" and job.stage == "cancelled"
        assert job.result == original


def test_progress_cancelled_after_send_does_not_publish_partial_material(tmp_path):
    engine, _, job_id = document_job(tmp_path)

    class CancelledProvider(DiagnosticProvider):
        async def complete_document(
            self, payload, schema=None, *, before_send=None, on_progress=None
        ):
            assert before_send()
            on_progress("document_waiting", {"request_bytes": 1500})
            with Session(engine) as db, db.begin():
                job = db.get(Job, job_id)
                job.status, job.stage = "cancelled", "cancelled"
            on_progress("document_receiving", {"response_bytes": 10})
            raise AssertionError("terminal callback should stop processing")

    asyncio.run(execute_document_parse(engine, job_id, tmp_path, provider=CancelledProvider()))
    with Session(engine) as db:
        assert db.get(Job, job_id).status == "cancelled"
        assert db.query(LlmDocumentParse).count() == 0
        assert db.query(LlmDocumentSegment).count() == 0


def test_diagnostics_allowlist_rejects_private_strings_and_nonfinite_counters():
    assert _safe_document_request_metadata(
        {
            "transport": "chat-images-v1",
            "phase": "response_headers",
            "total_pages": 3,
            "rendered_pages": 2,
            "response_bytes": True,
            "request_bytes": -1,
            "elapsed_seconds": float("nan"),
            "read_timeout_seconds": float("inf"),
            "total_timeout_seconds": "private string",
            "timeout_type": "private string",
            "started_at": "private string",
            "path": "private string",
            "file_data": "private string",
        }
    ) == {
        "transport": "chat-images-v1",
        "phase": "response_headers",
        "page_count": 3,
        "rendered_pages": 2,
    }


@pytest.mark.parametrize(
    "stage",
    [
        "document_rendering",
        "document_connecting",
        "document_uploading",
        "document_waiting",
        "document_receiving",
    ],
)
def test_document_transport_stages_are_readable_through_job_api(tmp_path, stage):
    from test_engine import client, post

    with client(tmp_path) as api:
        project_id = post(api, "/projects", {"name": "Stage fixture"}).json()["id"]
        job_id = str(uuid4())
        timestamp = now()
        with Session(api.app.state.engine) as db, db.begin():
            db.add(
                Job(
                    id=job_id,
                    kind="llm_document_parse",
                    project_id=project_id,
                    payload={},
                    status="running",
                    stage=stage,
                    attempt=1,
                    error=None,
                    result={"document_request": {"read_timeout_seconds": 600}},
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
        response = api.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200, response.text
        assert response.json()["stage"] == stage
        assert response.json()["result"]["document_request"]["read_timeout_seconds"] == 600
