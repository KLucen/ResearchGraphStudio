"""The desktop engine exposes the library and treats model slots as durable work."""

import asyncio
from contextlib import suppress
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from researchgraph.app import create_app, worker
from researchgraph.knowledge_connection_models import (
    KnowledgeConnectionRequest,
    KnowledgeConnectionRun,
)
from researchgraph.knowledge_extraction_models import KnowledgeExtractionRun
from researchgraph.models import Base, Job, now
from researchgraph.storage import make_engine
from sqlalchemy.orm import Session


def _job(kind, **values):
    return Job(
        id=str(uuid4()),
        kind=kind,
        project_id=None,
        payload={},
        status="queued",
        created_at=now(),
        updated_at=now(),
        **values,
    )


def test_app_registers_library_read_paths_and_cancel_preserves_sent_request_accounting(tmp_path):
    token = "k" * 40
    app = create_app(tmp_path, token, start_worker=False)
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as client:
        assert client.get("/api/v1/health").json()["schema_version"] == "lite0018"
        for path in (
            "library",
            "papers",
            "collections",
            "layout",
            "export",
            "source-options",
            "reports",
            "runs",
            "usage",
        ):
            response = client.get("/api/v1/knowledge/" + path)
            assert response.status_code == 200, (path, response.text)
        engine = app.state.engine
        with Session(engine) as db, db.begin():
            assert db.query(Job).count() == 0
            extraction_job, connection_job = _job("knowledge_extract"), _job("knowledge_connect")
            db.add_all([extraction_job, connection_job])
            db.flush()
            db.add(
                KnowledgeExtractionRun(
                    id=str(uuid4()),
                    job_id=extraction_job.id,
                    source_project_id="removed-project",
                    paper_id="source-paper",
                    source_kind="local_revision",
                    source_id="revision",
                    source_manifest={},
                    input_hash="a" * 64,
                    model_snapshot={},
                    cache_key="b" * 64,
                    request_sent=True,
                    raw_response="kept raw",
                )
            )
            connection = KnowledgeConnectionRun(
                id=str(uuid4()),
                job_id=connection_job.id,
                library_paper_id="library-paper",
                version_id="version",
                input_hash="a" * 64,
                input_json={},
                model_snapshot={},
                policy_json={},
            )
            db.add(connection)
            db.flush()
            db.add_all(
                [
                    KnowledgeConnectionRequest(
                        id=str(uuid4()),
                        run_id=connection.id,
                        ordinal=index,
                        input_json={},
                        status=status,
                        raw_response="receipt" if index else None,
                    )
                    for index, status in enumerate(("planned", "sent"))
                ]
            )
            job_ids = [extraction_job.id, connection_job.id]
        for identity in job_ids:
            result = client.post(
                f"/api/v1/jobs/{identity}/cancel", headers={"Idempotency-Key": str(uuid4())}
            )
            assert result.status_code == 200, result.text
            assert result.json()["status"] == "cancelled"
            retry = client.post(
                f"/api/v1/jobs/{identity}/retry", headers={"Idempotency-Key": str(uuid4())}
            )
            assert retry.status_code == 409
        with Session(engine) as db:
            extraction = db.query(KnowledgeExtractionRun).one()
            assert extraction.status == "cancelled" and extraction.request_sent
            assert extraction.raw_response == "kept raw"
            requests = (
                db.query(KnowledgeConnectionRequest)
                .order_by(KnowledgeConnectionRequest.ordinal)
                .all()
            )
            assert [request.status for request in requests] == ["cancelled", "sent"]
            assert requests[1].raw_response == "receipt"


@pytest.mark.parametrize("kind", ["knowledge_extract", "knowledge_connect"])
def test_worker_dispatches_new_job_kinds_once_without_a_provider(tmp_path, monkeypatch, kind):
    import researchgraph.app as app_module
    import researchgraph.knowledge_connections as connection_module
    import researchgraph.knowledge_tasks as extraction_module

    engine = make_engine(tmp_path)
    Base.metadata.create_all(engine)
    with Session(engine) as db, db.begin():
        job = _job(kind)
        db.add(job)
        db.flush()
        identity = job.id
    seen = []

    async def scenario():
        finished = asyncio.Event()

        async def execute(actual_engine, job_id, data_dir):
            seen.append((actual_engine, job_id, data_dir))
            with Session(engine) as db, db.begin():
                current = db.get(Job, job_id)
                current.status, current.stage = "succeeded", "completed"
            finished.set()

        monkeypatch.setattr(extraction_module, "run_knowledge_extract", execute)
        monkeypatch.setattr(connection_module, "run_knowledge_connect", execute)
        monkeypatch.setattr(app_module, "after_knowledge_job", lambda *_: None)
        monkeypatch.setattr(app_module, "dispatch_pending_knowledge", lambda *_: None)
        task = asyncio.create_task(worker(engine, tmp_path))
        try:
            await asyncio.wait_for(finished.wait(), timeout=3)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    asyncio.run(scenario())
    assert seen == [(engine, identity, tmp_path)]
    with Session(engine) as db:
        assert db.get(Job, identity).attempt == 1
