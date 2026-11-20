from pathlib import Path
from uuid import uuid4

import pytest
from researchgraph.document_batch_models import LlmDocumentBatch, LlmDocumentBatchRun
from researchgraph.document_batch_recovery import PUBLICATION_RECOVERY_VERSION
from researchgraph.import_plan_models import ImportPlanItem, ImportSession
from researchgraph.models import Job, Paper, now
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session
from test_engine import client, post


def make_project(api) -> str:
    response = post(api, "/projects", {"name": f"import-plan-{uuid4()}"})
    assert response.status_code == 201
    return response.json()["id"]


def create_session(api, project_id: str, *, key: str = "session-key"):
    return api.post(
        f"/api/v1/projects/{project_id}/import-sessions",
        json={
            "selection_id": "opaque-selection-1",
            "source_snapshot": {"file_name": "fixture.pdf"},
            "plan": {
                "overview": True,
                "reading": True,
                "translation_mode": "full",
                "modality": "pdf",
            },
        },
        headers={"Idempotency-Key": key},
    )


def test_import_session_persists_selected_post_processing_items(tmp_path):
    with client(tmp_path) as api:
        project_id = make_project(api)
        response = create_session(api, project_id)
        assert response.status_code == 202, response.text
        value = response.json()
        assert value["plan"]["translation_mode"] == "full"
        assert [item["item_kind"] for item in value["items"]] == [
            "document_parse",
            "paper_overview",
            "paper_reading",
            "translation",
        ]
        assert api.get(f"/api/v1/import-sessions/{value['id']}").json() == value
        assert len(api.get(f"/api/v1/projects/{project_id}/import-sessions").json()) == 1


def test_import_session_creation_is_idempotent_and_validates_choices(tmp_path):
    with client(tmp_path) as api:
        project_id = make_project(api)
        first = create_session(api, project_id)
        second = create_session(api, project_id)
        assert first.status_code == second.status_code == 202
        assert first.json() == second.json()
        invalid_translation = api.post(
            f"/api/v1/projects/{project_id}/import-sessions",
            json={"selection_id": "selection-2", "plan": {"translation_mode": "full"}},
            headers={"Idempotency-Key": "invalid-key"},
        )
        assert invalid_translation.status_code == 422
        invalid_multimodal = api.post(
            f"/api/v1/projects/{project_id}/import-sessions",
            json={
                "selection_id": "selection-3",
                "plan": {"modality": "text", "require_multimodal": True},
            },
            headers={"Idempotency-Key": "invalid-key-2"},
        )
        assert invalid_multimodal.status_code == 422


@pytest.mark.parametrize("link", ["valid", "job_project", "paper_project", "session"])
def test_legacy_pdf_session_projects_verified_paper_identity_without_database_write(tmp_path, link):
    with client(tmp_path) as api:
        project_id = make_project(api)
        other_project = post(api, "/projects", {"name": "Other project"}, "other-project").json()[
            "id"
        ]
        session_id = create_session(api, project_id, key="legacy-pdf-session").json()["id"]
        paper_id, job_id = str(uuid4()), str(uuid4())
        with Session(api.app.state.engine) as db, db.begin():
            db.add(
                Paper(
                    id=paper_id,
                    project_id=other_project if link == "paper_project" else project_id,
                    title="Anonymous legacy PDF",
                    created_at=now(),
                )
            )
            db.add(
                Job(
                    id=job_id,
                    project_id=other_project if link == "job_project" else project_id,
                    kind="pdf_import",
                    status="succeeded",
                    attempt=1,
                    created_at=now(),
                    updated_at=now(),
                    payload={
                        "paper_id": paper_id,
                        "import_session_id": "different-session"
                        if link == "session"
                        else session_id,
                    },
                )
            )
            db.flush()
            item = db.scalar(
                select(ImportPlanItem).where(
                    ImportPlanItem.session_id == session_id,
                    ImportPlanItem.item_kind == "document_parse",
                )
            )
            item.job_id, item.status = job_id, "succeeded"
            original = dict(db.get(ImportSession, session_id).source_snapshot)
        detail = api.get(f"/api/v1/import-sessions/{session_id}").json()
        listing = api.get(f"/api/v1/projects/{project_id}/import-sessions").json()
        listed = next(value for value in listing if value["id"] == session_id)
        expected = paper_id if link == "valid" else None
        assert detail["source_snapshot"]["paper_id"] == expected
        assert listed["source_snapshot"]["paper_id"] == expected
        # The desktop filters by this projected identity to select the model panel.
        matches = [
            value["id"] for value in listing if value["source_snapshot"]["paper_id"] == paper_id
        ]
        assert matches == ([session_id] if link == "valid" else [])
        with Session(api.app.state.engine) as db:
            assert db.get(ImportSession, session_id).source_snapshot == original
            assert db.get(Job, job_id).status == "succeeded"


def test_job_cancel_and_retry_keep_import_plan_and_session_in_sync(tmp_path):
    with client(tmp_path) as api:
        project_id = make_project(api)
        session_id = create_session(api, project_id).json()["id"]
        job_id = str(uuid4())
        with Session(api.app.state.engine) as db, db.begin():
            db.add(
                Job(
                    id=job_id,
                    project_id=project_id,
                    kind="llm_document_parse",
                    status="queued",
                    payload={"import_session_id": session_id},
                    attempt=0,
                    created_at="2026-11-18T00:00:00Z",
                    updated_at="2026-11-18T00:00:00Z",
                )
            )
            item = db.scalar(
                select(ImportPlanItem).where(
                    ImportPlanItem.session_id == session_id,
                    ImportPlanItem.item_kind == "document_parse",
                )
            )
            item.status, item.job_id = "queued", job_id
        cancelled = api.post(
            f"/api/v1/jobs/{job_id}/cancel", headers={"Idempotency-Key": "import-cancel"}
        )
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
        value = api.get(f"/api/v1/import-sessions/{session_id}").json()
        assert value["status"] == value["items"][0]["status"] == "interrupted"
        retried = api.post(
            f"/api/v1/jobs/{job_id}/retry", headers={"Idempotency-Key": "import-retry"}
        )
        assert retried.status_code == 200 and retried.json()["status"] == "queued"
        value = api.get(f"/api/v1/import-sessions/{session_id}").json()
        assert value["status"] == value["items"][0]["status"] == "queued"
        assert value["error"] is None and value["items"][0]["error"] is None
        assert value["items"][0]["attempt"] == 1


def test_startup_repairs_stale_import_session_after_old_job_failure(tmp_path):
    with client(tmp_path) as api:
        project_id = make_project(api)
        session_id = create_session(api, project_id).json()["id"]
        job_id = str(uuid4())
        with Session(api.app.state.engine) as db, db.begin():
            db.add(
                Job(
                    id=job_id,
                    project_id=project_id,
                    kind="llm_document_parse",
                    status="failed",
                    payload={"import_session_id": session_id},
                    error="old DetachedInstanceError",
                    attempt=1,
                    created_at="2026-11-18T00:00:00Z",
                    updated_at="2026-11-18T00:00:00Z",
                )
            )
            item = db.scalar(
                select(ImportPlanItem).where(
                    ImportPlanItem.session_id == session_id,
                    ImportPlanItem.item_kind == "document_parse",
                )
            )
            item.status, item.job_id = "running", job_id
            db.get(ImportSession, session_id).status = "running"
    with client(tmp_path) as reopened:
        value = reopened.get(f"/api/v1/import-sessions/{session_id}").json()
        assert value["status"] == value["items"][0]["status"] == "failed"
        assert value["error"] == "old DetachedInstanceError"
        assert reopened.get(f"/api/v1/jobs/{job_id}").json()["status"] == "failed"


def test_retry_changes_only_failed_item_and_is_idempotent(tmp_path):
    with client(tmp_path) as api:
        project_id = make_project(api)
        session = create_session(api, project_id).json()
        with Session(api.app.state.engine) as db, db.begin():
            item = db.scalar(
                select(ImportPlanItem).where(
                    ImportPlanItem.session_id == session["id"],
                    ImportPlanItem.item_kind == "document_parse",
                )
            )
            assert item is not None
            item.status = "failed"
            item.error = "fixture failure"
        path = f"/api/v1/import-sessions/{session['id']}/items/document_parse/retry"
        first = api.post(path, headers={"Idempotency-Key": "retry-key"})
        assert first.status_code == 200
        item = next(x for x in first.json()["items"] if x["item_kind"] == "document_parse")
        assert item["status"] == "queued" and item["attempt"] == 1 and item["error"] is None
        assert api.post(path, headers={"Idempotency-Key": "retry-key"}).json() == first.json()
        assert api.post(path, headers={"Idempotency-Key": "retry-key-2"}).status_code == 409


def test_retry_requeues_terminal_worker_job_for_model_item(tmp_path):
    with client(tmp_path) as api:
        project_id = make_project(api)
        session = create_session(api, project_id, key="job-retry-session").json()
        with Session(api.app.state.engine) as db, db.begin():
            item = db.scalar(
                select(ImportPlanItem).where(
                    ImportPlanItem.session_id == session["id"],
                    ImportPlanItem.item_kind == "paper_overview",
                )
            )
            assert item is not None
            job = Job(
                id=str(uuid4()),
                kind="llm_document_postprocess",
                project_id=project_id,
                payload={
                    "import_session_id": session["id"],
                    "item_kind": "paper_overview",
                },
                status="failed",
                stage="failed",
                error="fixture failure",
                attempt=1,
                created_at="2026-01-01T00:00:00+00:00",
                updated_at="2026-01-01T00:00:00+00:00",
            )
            job_id = job.id
            db.add(job)
            db.flush()
            item.job_id = job.id
            item.status = "failed"
            item.error = "fixture failure"
        response = api.post(
            f"/api/v1/import-sessions/{session['id']}/items/paper_overview/retry",
            headers={"Idempotency-Key": "job-retry-key"},
        )
        assert response.status_code == 200, response.text
        with Session(api.app.state.engine) as db:
            retried = db.get(Job, job_id)
            assert retried is not None
            assert retried.status == "queued"
            assert retried.stage is None
            assert retried.error is None


@pytest.mark.parametrize("via_item", [False, True])
@pytest.mark.parametrize("legacy_fk", [False, True])
def test_exhausted_document_job_can_retry_only_when_all_batches_are_publishable(
    tmp_path, via_item, legacy_fk
):
    with client(tmp_path) as api:
        project_id = make_project(api)
        session_id = create_session(api, project_id, key="publication-session").json()["id"]
        job_id = str(uuid4())
        run_id = str(uuid4())
        with Session(api.app.state.engine) as db, db.begin():
            session = db.get(ImportSession, session_id)
            session.status = "failed"
            session.plan = {**session.plan, "document_batching": True}
            item = db.scalar(
                select(ImportPlanItem).where(
                    ImportPlanItem.session_id == session_id,
                    ImportPlanItem.item_kind == "document_parse",
                )
            )
            item.status = "failed"
            db.add(
                Job(
                    id=job_id,
                    project_id=project_id,
                    kind="pdf_import",
                    status="failed",
                    stage="failed",
                    payload={"import_session_id": session_id},
                    result={
                        **(
                            {
                                "publication_recovery_attempts": 2,
                                "failure_diagnostics": {
                                    "database_dialect": "sqlite",
                                    "sqlite_errorcode": 787,
                                    "sqlite_errorname": "SQLITE_CONSTRAINT_FOREIGNKEY",
                                    "constraint_category": "foreign_key",
                                },
                            }
                            if legacy_fk
                            else {}
                        ),
                        "document_batches": {
                            "total": 1,
                            "completed": 1,
                            "phase": "publication_failed",
                            "current_kind": "boundary",
                        },
                    },
                    error="publication failure",
                    attempt=4,
                    created_at=now(),
                    updated_at=now(),
                )
            )
            db.flush()
            item.job_id = job_id
            db.add(
                LlmDocumentBatchRun(
                    id=run_id,
                    import_session_id=session_id,
                    job_id=job_id,
                    source_version={"size": 1},
                    settings={
                        "version": "document-batch-1",
                        "ranges": [
                            {
                                "index": 0,
                                "page_start": 1,
                                "page_end": 1,
                                "send_start": 1,
                                "send_end": 1,
                            }
                        ],
                    },
                    page_count=1,
                    status="failed",
                    created_at=now(),
                    updated_at=now(),
                )
            )
            db.flush()
            db.add(
                LlmDocumentBatch(
                    id=str(uuid4()),
                    run_id=run_id,
                    ordinal=0,
                    kind="extract",
                    page_start=1,
                    page_end=1,
                    send_start=1,
                    send_end=1,
                    status="validated",
                    attempts=1,
                    repair_attempts=0,
                    request_count=1,
                    result_json={"validated": True},
                    validation_errors=[],
                    usage={},
                    request_metadata={},
                    created_at=now(),
                    updated_at=now(),
                )
            )

        if legacy_fk:
            with Session(api.app.state.engine) as db:
                saved_result = dict(db.get(Job, job_id).result)
            invalid_legacy_results = (
                [
                    {**saved_result, "publication_recovery_attempts": value}
                    for value in (True, 2.0, -1, 3)
                ]
                + [
                    {**saved_result, "publication_recovery_version": value}
                    for value in (None, "unknown-version", PUBLICATION_RECOVERY_VERSION)
                ]
                + [
                    {**saved_result, "failure_diagnostics": {"constraint_category": "unique"}},
                    {**saved_result, "document_batches": {"phase": "failed"}},
                ]
            )
            for invalid in invalid_legacy_results:
                with Session(api.app.state.engine) as db, db.begin():
                    db.get(Job, job_id).result = invalid
                unavailable = api.get(f"/api/v1/jobs/{job_id}")
                assert not unavailable.json()["result"]["document_batches"][
                    "publication_retry_available"
                ]
            with Session(api.app.state.engine) as db, db.begin():
                db.get(Job, job_id).result = saved_result
        projected = api.get(f"/api/v1/jobs/{job_id}")
        assert projected.status_code == 200
        assert projected.json()["result"]["document_batches"]["publication_retry_available"]
        assert projected.json()["result"]["document_batches"]["current_kind"] == "publication"
        with Session(api.app.state.engine) as db:
            assert "publication_recovery_version" not in db.get(Job, job_id).result
        path = (
            f"/api/v1/import-sessions/{session_id}/items/document_parse/retry"
            if via_item
            else f"/api/v1/jobs/{job_id}/retry"
        )
        headers = {"Idempotency-Key": "publication-only-retry"}
        retried = api.post(path, headers=headers)
        assert retried.status_code == 200, retried.text
        assert retried.json()["status"] == "queued"
        assert api.post(path, headers=headers).json() == retried.json()
        with Session(api.app.state.engine) as db:
            task = db.get(Job, job_id)
            assert task.attempt == 4
            assert task.result["publication_recovery_attempts"] == (3 if legacy_fk else 1)
            assert task.result["publication_recovery_version"] == PUBLICATION_RECOVERY_VERSION
            assert task.result["publication_recovery_only"] is True
            assert db.get(ImportSession, session_id).status == "queued"
        if legacy_fk:
            for state in ("failed", "cancelled", "interrupted"):
                with Session(api.app.state.engine) as db, db.begin():
                    db.get(Job, job_id).status = state
                    item = db.scalar(
                        select(ImportPlanItem).where(
                            ImportPlanItem.session_id == session_id,
                            ImportPlanItem.item_kind == "document_parse",
                        )
                    )
                    item.status = "failed"
                assert (
                    api.post(
                        path, headers={"Idempotency-Key": f"used-fk-recovery-{state}"}
                    ).status_code
                    == 409
                )


def test_pdf_import_captures_model_first_plan_without_content_hash_gate(tmp_path):
    pdf = Path(tmp_path) / "fixture.pdf"
    pdf.write_bytes(b"%PDF-fixture")
    with client(tmp_path) as api:
        project_id = make_project(api)
        response = post(
            api,
            f"/projects/{project_id}/papers/import/pdf",
            {
                "path": str(pdf),
                "mode": "reference",
                "selection_id": str(uuid4()),
                "post_import_plan": {
                    "parse": True,
                    "overview": True,
                    "reading": True,
                    "translation_mode": "none",
                    "modality": "auto",
                    "extract_formulas": True,
                    "extract_tables": True,
                },
            },
            "pdf-plan-key",
        )
        assert response.status_code == 202, response.text
        job = response.json()
        with Session(api.app.state.engine) as db:
            saved_job = db.get(Job, job["id"])
            assert saved_job is not None and saved_job.payload is not None
            session_id = saved_job.payload["import_session_id"]
            session = db.get(ImportSession, session_id)
            assert session is not None
            assert session.source_snapshot["file_name"] == "fixture.pdf"
            assert session.source_snapshot.get("paper_id") == saved_job.payload.get("paper_id")
            assert "sha256" not in session.source_snapshot
            assert session.plan["modality"] == "pdf"
            assert session.plan["require_multimodal"] is False
        with api.app.state.engine.connect() as connection:
            assert inspect(connection).has_table("llm_document_parses")


def test_model_document_result_endpoint_materializes_formula_and_table(tmp_path):
    with client(tmp_path) as api:
        project_id = make_project(api)
        response = create_session(api, project_id, key="document-session-key")
        session_id = response.json()["id"]
        result = api.post(
            f"/api/v1/import-sessions/{session_id}/document-parse/result",
            json={
                "parse_version": "llm-document-1",
                "modality": "text",
                "provider_id": "fixture",
                "model_id": "fixture-model",
                "segments": [
                    {
                        "chapter_ref": "ch-1",
                        "chapter_title": "Introduction",
                        "kind": "paragraph",
                        "text": "A paragraph.",
                    },
                    {
                        "chapter_ref": "ch-1",
                        "chapter_title": "Introduction",
                        "kind": "formula",
                        "ordinal": 1,
                        "text": "E = mc^2",
                        "status": "needs_review",
                    },
                    {
                        "chapter_ref": "ch-1",
                        "chapter_title": "Introduction",
                        "kind": "table",
                        "ordinal": 2,
                        "raw_table_text": "A | B\\n1 | 2",
                        "status": "degraded",
                    },
                ],
            },
            headers={"Idempotency-Key": "document-result-key"},
        )
        assert result.status_code == 201, result.text
        payload = result.json()
        assert payload["status"] == "succeeded"
        assert [segment["kind"] for segment in payload["segments"]] == [
            "paragraph",
            "formula",
            "table",
        ]
        fetched = api.get(f"/api/v1/import-sessions/{session_id}/document-parse")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == payload["id"]


@pytest.mark.parametrize("item_kind", ["unknown", "translation"])
def test_retry_rejects_missing_or_unavailable_item(tmp_path, item_kind):
    with client(tmp_path) as api:
        project_id = make_project(api)
        session = create_session(api, project_id).json()
        response = api.post(
            f"/api/v1/import-sessions/{session['id']}/items/{item_kind}/retry",
            headers={"Idempotency-Key": f"retry-{item_kind}"},
        )
        assert response.status_code in {404, 409, 422}
