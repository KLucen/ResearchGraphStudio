import asyncio
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from researchgraph.import_plan_models import ImportSession
from researchgraph.ingest import run_file_job
from researchgraph.models import AttachmentRevision, Chunk, Job, Paper, now
from researchgraph.structure_upgrade import local_content_was_cleared
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_engine import client, post


def import_local(api, tmp_path):
    project = post(api, "/projects", {"name": "Local parse"}).json()["id"]
    path = tmp_path / "source.pdf"
    shutil.copyfile(Path(__file__).parent.parent / "fixtures/pdf/two-pages.pdf", path)
    job = post(api, f"/projects/{project}/papers/import/pdf", {"path": str(path)}).json()
    run_local(api, job["id"], tmp_path)
    result = api.get("/api/v1/jobs/" + job["id"]).json()
    return project, result["result"]["paper_id"], path, job["id"]


def run_local(api, job_id, tmp_path):
    with Session(api.app.state.engine) as db, db.begin():
        job = db.get(Job, job_id)
        job.status = "running"
    asyncio.run(run_file_job(api.app.state.engine, job_id, tmp_path))


def test_local_import_clear_and_explicit_reparse_preserve_paper(tmp_path):
    with client(tmp_path) as api:
        project, paper_id, path, original_job = import_local(api, tmp_path)
        revision = api.get(f"/api/v1/papers/{paper_id}").json()["revisions"][0]["id"]
        assert api.delete(f"/api/v1/papers/{paper_id}/legacy-content").status_code == 200
        route = f"/papers/{paper_id}/parse"
        queued = post(api, route, {"mode": "local"}, "local-parse-one")
        assert queued.status_code == 202, queued.text
        assert post(api, route, {"mode": "local"}, "local-parse-one").json() == queued.json()
        assert post(api, route, {"mode": "local"}, "local-parse-busy").status_code == 409
        run_local(api, queued.json()["id"], tmp_path)
        with Session(api.app.state.engine) as db:
            assert db.scalar(select(func.count()).select_from(Paper)) == 1
            assert (
                db.scalar(
                    select(func.count()).select_from(Chunk).where(Chunk.revision_id == revision)
                )
                > 0
            )
            assert not local_content_was_cleared(db.get(AttachmentRevision, revision))
            assert db.get(Job, original_job).status == "succeeded"
            assert not db.get(Job, queued.json()["id"]).payload.get("provider_snapshot")
        assert path.is_file()
        usage = api.get(f"/api/v1/projects/{project}/lite/usage").json()
        assert usage["calls"] == 0


def test_fresh_model_parse_freezes_current_document_role_and_keeps_local(tmp_path):
    with client(tmp_path) as api:
        _, paper_id, _, _ = import_local(api, tmp_path)
        profile = post(
            api,
            "/settings/models",
            {
                "name": "PDF fixture",
                "provider": "compatible",
                "base_url": "https://models.example/v1",
                "model": "file-model",
                "parameters": {
                    "capabilities": {"document_input": "pdf", "document_transport": "chat_file"}
                },
            },
            "parse-profile",
        ).json()
        post(api, "/settings/model-roles", {"document_parse": profile["id"]}, "parse-role")
        queued = post(
            api,
            f"/papers/{paper_id}/parse",
            {"mode": "model", "post_import_plan": {"parse": True, "allow_network": True}},
            "fresh-model-job",
        )
        assert queued.status_code == 202, queued.text
        with Session(api.app.state.engine) as db:
            payload = db.get(Job, queued.json()["id"]).payload
            assert payload["model_first"] and payload["allow_network"]
            assert payload["provider_snapshot"]["id"] == profile["id"]
            assert (
                payload["provider_snapshot"]["parameters"]["capabilities"]["document_input"]
                == "pdf"
            )
            assert (
                db.get(ImportSession, payload["import_session_id"]).source_snapshot["paper_id"]
                == paper_id
            )
            assert db.scalar(select(func.count()).select_from(Chunk)) > 0
            assert db.scalar(select(func.count()).select_from(Paper)) == 1


@pytest.mark.parametrize(
    "body",
    [
        {"mode": "model"},
        {"mode": "model", "post_import_plan": {"allow_network": False}},
        {"mode": "local", "post_import_plan": {"allow_network": True}},
        {"mode": "local", "path": "C:/untrusted.pdf"},
    ],
)
def test_parse_mode_requires_explicit_consent_and_no_ui_path(tmp_path, body):
    with client(tmp_path) as api:
        assert post(api, f"/papers/{uuid4()}/parse", body).status_code == 422


def test_model_only_failed_paper_can_parse_locally_and_retry(tmp_path):
    with client(tmp_path) as api:
        project = post(api, "/projects", {"name": "Failed model"}).json()["id"]
        path = tmp_path / "source.pdf"
        shutil.copyfile(Path(__file__).parent.parent / "fixtures/pdf/two-pages.pdf", path)
        paper_id = str(uuid4())
        with Session(api.app.state.engine) as db, db.begin():
            db.add(Paper(id=paper_id, project_id=project, title="Original title", created_at=now()))
            db.flush()
            db.add(
                Job(
                    id=str(uuid4()),
                    kind="pdf_import",
                    project_id=project,
                    payload={
                        "paper_id": paper_id,
                        "path": str(path),
                        "mode": "reference",
                        "model_first": True,
                    },
                    status="failed",
                    attempt=1,
                    created_at=now(),
                    updated_at=now(),
                )
            )
        queued = post(
            api, f"/papers/{paper_id}/parse", {"mode": "local"}, "local-from-failed"
        ).json()
        with Session(api.app.state.engine) as db, db.begin():
            db.get(Job, queued["id"]).status = "failed"
        retried = post(api, f"/jobs/{queued['id']}/retry", key="retry-local-failure")
        assert retried.status_code == 200 and retried.json()["status"] == "queued"
        run_local(api, queued["id"], tmp_path)
        with Session(api.app.state.engine) as db:
            assert db.scalar(select(func.count()).select_from(Paper)) == 1
            assert db.get(Paper, paper_id).title == "Original title"
            assert db.scalar(select(func.count()).select_from(Chunk)) > 0
