from uuid import uuid4

import pytest
from researchgraph.document_batch_models import LlmDocumentBatch, LlmDocumentBatchRun
from researchgraph.import_plan_models import ImportPlanItem, ImportSession
from researchgraph.models import Job, now
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_engine import client, post


def seed(api, *, http_status=400, corrected=False, kind="boundary"):
    engine = api.app.state.engine
    project = post(api, "/projects", {"name": "Anonymous recovery"}).json()["id"]
    sid, jid, rid = (str(uuid4()) for _ in range(3))
    with Session(engine) as db, db.begin():
        db.add(
            ImportSession(
                id=sid,
                project_id=project,
                source_kind="pdf",
                selection_id="synthetic",
                source_snapshot={},
                plan={"document_batching": True},
                status="failed",
                created_at=now(),
                updated_at=now(),
            )
        )
        db.add(
            Job(
                id=jid,
                project_id=project,
                kind="pdf_import",
                status="failed",
                attempt=3,
                payload={"import_session_id": sid},
                result={"document_batches": {"completed": 1}},
                created_at=now(),
                updated_at=now(),
            )
        )
        db.flush()
        db.add(
            ImportPlanItem(
                id=str(uuid4()),
                session_id=sid,
                job_id=jid,
                item_kind="document_parse",
                status="failed",
                config={},
                attempt=2,
                created_at=now(),
                updated_at=now(),
            )
        )
        db.add(
            LlmDocumentBatchRun(
                id=rid,
                import_session_id=sid,
                job_id=jid,
                source_version={},
                settings={"version": "document-batch-1"},
                page_count=2,
                status="failed",
                created_at=now(),
                updated_at=now(),
            )
        )
        db.flush()
        for ordinal, row_kind, status in [(0, "extract", "validated"), (0, kind, "uncertain")]:
            # Failure-kind test uses a second extraction ordinal.
            db.add(
                LlmDocumentBatch(
                    id=str(uuid4()),
                    run_id=rid,
                    ordinal=ordinal if row_kind == "boundary" or status == "validated" else 1,
                    kind=row_kind,
                    page_start=1,
                    page_end=2,
                    send_start=1,
                    send_end=2,
                    status=status,
                    attempts=3,
                    repair_attempts=0,
                    request_count=3,
                    result_json={} if status == "validated" else None,
                    request_metadata={"http_status": http_status},
                    usage={"requests": [{"boundary_prompt_version": 2}] if corrected else []},
                    validation_errors=[],
                    created_at=now(),
                    updated_at=now(),
                )
            )
    return engine, project, sid, jid


def test_legacy_recovery_get_is_derived_and_does_not_write(tmp_path):
    with client(tmp_path) as api:
        engine, project, _, jid = seed(api)
        for _ in range(2):
            response = api.get(f"/api/v1/jobs/{jid}").json()
            assert response["result"]["document_batches"]["compatibility_retry_available"] is True
            assert response["result"]["document_batches"]["current_kind"] == "boundary"
        listed = api.get(f"/api/v1/projects/{project}/jobs").json()["items"][0]
        assert listed["result"]["document_batches"]["compatibility_retry_available"] is True
        all_jobs = api.get("/api/v1/jobs").json()
        global_job = next(job for job in all_jobs if job["id"] == jid)
        assert global_job["result"]["document_batches"]["compatibility_retry_available"] is True
        with Session(engine) as db:
            job = db.get(Job, jid)
            assert job.result == {"document_batches": {"completed": 1}}
            assert job.attempt == 3 and job.status == "failed"


@pytest.mark.parametrize("via_item", [False, True])
def test_explicit_legacy_recovery_requeues_without_resetting_ledger(tmp_path, via_item):
    with client(tmp_path) as api:
        engine, _, sid, jid = seed(api)
        path = (
            f"/api/v1/import-sessions/{sid}/items/document_parse/retry"
            if via_item
            else f"/api/v1/jobs/{jid}/retry"
        )
        response = api.post(path, headers={"Idempotency-Key": "legacy-recovery-key"})
        assert response.status_code == 200, response.text
        assert (
            api.post(path, headers={"Idempotency-Key": "legacy-recovery-key"}).json()
            == response.json()
        )
        with Session(engine) as db:
            job = db.get(Job, jid)
            assert job.attempt == 3 and job.status == "queued"
            rows = list(db.scalars(select(LlmDocumentBatch)))
            assert all(row.request_count == row.attempts == 3 for row in rows)


@pytest.mark.parametrize(
    "options", [{"corrected": True}, {"http_status": 500}, {"kind": "extract"}]
)
@pytest.mark.parametrize("via_item", [False, True])
def test_ineligible_exhausted_jobs_reject_recovery_without_requeue(tmp_path, options, via_item):
    with client(tmp_path) as api:
        engine, _, sid, jid = seed(api, **options)
        path = (
            f"/api/v1/import-sessions/{sid}/items/document_parse/retry"
            if via_item
            else f"/api/v1/jobs/{jid}/retry"
        )
        assert api.post(path, headers={"Idempotency-Key": "ineligible-recovery"}).status_code == 409
        with Session(engine) as db:
            assert db.get(Job, jid).status == "failed"
