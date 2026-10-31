import hashlib
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

import pymupdf
import pytest
from alembic import command
from alembic.config import Config
from researchgraph import ingest
from researchgraph.models import AttachmentRevision, Chunk, Event, Paper, PaperSource
from researchgraph.storage import make_engine, migrate
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_engine import client, post

FIXTURES = Path(__file__).parents[1] / "fixtures/pdf"


def wait_job(api, job):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        result = api.get(f"/api/v1/jobs/{job['id']}").json()
        if result["status"] not in {"queued", "running"}:
            return result
        time.sleep(0.05)
    raise AssertionError("job timed out")


def queue(api, project, path, key, mode="reference"):
    response = post(
        api, f"/projects/{project}/papers/import/pdf", {"path": str(path), "mode": mode}, key
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_import_dedup_revisions_and_immutable_text(tmp_path):
    source = tmp_path / "中文 source.pdf"
    shutil.copyfile(FIXTURES / "two-pages.pdf", source)
    data = tmp_path / "data"
    with client(data, worker=True) as api:
        project = post(api, "/projects", {"name": "PDF tests"}).json()["id"]
        first = queue(api, project, source, "import-first")
        assert queue(api, project, source, "import-first")["id"] == first["id"]
        completed = wait_job(api, first)
        assert completed["status"] == "succeeded", completed
        paper_id, revision_id = (completed["result"][k] for k in ("paper_id", "revision_id"))
        details = api.get(f"/api/v1/papers/{paper_id}").json()
        assert details["revisions"][0]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
        blocks = api.get(f"/api/v1/revisions/{revision_id}/chunks").json()["items"]
        assert {b["page_index"] for b in blocks} == {0, 1}
        assert blocks[0]["page_label"] == "S-1"
        assert "72%" in "".join(b["text"] for b in blocks)
        assert all(len(b["bbox"]) == 4 and b["bbox"][2] > b["bbox"][0] for b in blocks)
        page = api.get(f"/api/v1/revisions/{revision_id}/chunks?limit=1").json()
        assert page["next_cursor"] == 1
        duplicate = tmp_path / "moved.pdf"
        shutil.copyfile(source, duplicate)
        second = wait_job(api, queue(api, project, duplicate, "import-copy", "managed"))
        assert second["result"] == {
            "paper_id": paper_id,
            "revision_id": revision_id,
            "reused": True,
        }
        assert len(api.get(f"/api/v1/papers/{paper_id}").json()["sources"]) == 2
        with Session(api.app.state.engine) as session:
            managed = session.scalar(select(PaperSource).where(PaperSource.mode == "managed"))
            assert Path(managed.managed_path).read_bytes() == source.read_bytes()
        # Same source, changed content: append a revision without overwriting old blocks.
        with pymupdf.open() as document:
            document.new_page().insert_text((50, 60), "Changed accuracy: 90%")
            document.save(source)
        third = wait_job(api, queue(api, project, source, "import-changed"))
        assert third["result"]["paper_id"] == paper_id
        assert third["result"]["revision_id"] != revision_id
        assert api.get(f"/api/v1/revisions/{revision_id}/chunks").json()["items"] == blocks
        assert len(api.get(f"/api/v1/papers/{paper_id}").json()["revisions"]) == 2
    with client(data) as api:
        assert len(api.get(f"/api/v1/projects/{project}/papers").json()["items"]) == 1
        assert api.get(f"/api/v1/revisions/{revision_id}/chunks").json()["items"] == blocks
    assert not [p for p in (data / "import-work").iterdir() if p.suffix != ".lock"]


@pytest.mark.parametrize("filename", ["broken.pdf", "encrypted.pdf", "missing.pdf"])
def test_bad_pdf_fails_without_partial_objects(tmp_path, filename):
    with client(tmp_path, worker=True) as api:
        project = post(api, "/projects", {"name": "failure"}).json()["id"]
        job = wait_job(api, queue(api, project, FIXTURES / filename, "bad-file-key"))
        assert job["status"] == "failed" and job["error"]
        with Session(api.app.state.engine) as session:
            for model in (Paper, PaperSource, AttachmentRevision, Chunk):
                assert session.scalar(select(model)) is None


def test_image_pdf_reports_limit_and_project_isolation(tmp_path):
    with client(tmp_path, worker=True) as api:
        p1 = post(api, "/projects", {"name": "one"}, "project-one").json()["id"]
        p2 = post(api, "/projects", {"name": "two"}, "project-two").json()["id"]
        first = wait_job(api, queue(api, p1, FIXTURES / "image-only.pdf", "image-first"))
        second = wait_job(api, queue(api, p2, FIXTURES / "image-only.pdf", "image-second"))
        assert first["status"] == second["status"] == "succeeded"
        assert first["result"]["paper_id"] != second["result"]["paper_id"]
        details = api.get(f"/api/v1/papers/{first['result']['paper_id']}").json()
        assert any("OCR" in warning for warning in details["revisions"][0]["warnings"])
        assert (
            api.get(f"/api/v1/revisions/{first['result']['revision_id']}/chunks").json()["items"]
            == []
        )


def test_queued_pdf_survives_restart_cancel_and_retry(tmp_path):
    with client(tmp_path) as api:
        project = post(api, "/projects", {"name": "recovery"}).json()["id"]
        job = queue(api, project, FIXTURES / "two-pages.pdf", "retry-pdf-key")
        assert (
            post(api, f"/jobs/{job['id']}/cancel", key="cancel-pdf").json()["status"] == "cancelled"
        )
    with client(tmp_path, worker=True) as api:
        retried = post(api, f"/jobs/{job['id']}/retry", key="retry-pdf").json()
        assert wait_job(api, retried)["status"] == "succeeded"
        with Session(api.app.state.engine) as session:
            assert (
                len(session.scalars(select(Event).where(Event.event_type == "PDF_IMPORTED")).all())
                == 1
            )


def test_upgrade_0001_preserves_project_and_backup(tmp_path):
    engine = make_engine(tmp_path)
    config = Config()
    config.set_main_option(
        "script_location",
        str(Path(__file__).parents[2] / "services/engine/researchgraph/migrations"),
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0001")
        connection.exec_driver_sql(
            "INSERT INTO projects VALUES ('p','Keep project','question','now')"
        )
        connection.exec_driver_sql(
            "INSERT INTO jobs VALUES ('j','diagnostics','succeeded',1,NULL,NULL,'now','now')"
        )
    migrate(engine, tmp_path)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT name FROM projects")) == "Keep project"
        assert connection.scalar(text("SELECT status FROM jobs")) == "succeeded"
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0004"
    (backup,) = (tmp_path / "backups").glob("*.sqlite3")
    with sqlite3.connect(backup) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0001"
    engine.dispose()


@pytest.mark.parametrize("action", ["cancel", "shutdown"])
@pytest.mark.parametrize("kind", ["pdf_import", "source_check", "source_relocate"])
def test_running_parser_is_terminated_without_publishing(tmp_path, monkeypatch, action, kind):
    if kind != "pdf_import":
        with client(tmp_path, worker=True) as api:
            project = post(api, "/projects", {"name": "source lifecycle"}).json()["id"]
            imported = wait_job(
                api, queue(api, project, FIXTURES / "two-pages.pdf", "initial-import")
            )
            source = api.get(f"/api/v1/papers/{imported['result']['paper_id']}").json()["sources"][
                0
            ]
    original = subprocess.Popen
    children = []

    def slow_child(command, **kwargs):
        # Exercise lifecycle termination deterministically, independent of PDF size/speed.
        process = original([command[0], "-c", "import time; time.sleep(60)"], **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(ingest.subprocess, "Popen", slow_child)
    with client(tmp_path, worker=True) as api:
        if kind == "pdf_import":
            project = post(api, "/projects", {"name": "cancel running"}).json()["id"]
            job = queue(api, project, FIXTURES / "two-pages.pdf", "running-key")
        else:
            body = {"expected_generation": source["generation"]}
            if kind == "source_relocate":
                body["path"] = str(FIXTURES / "two-pages.pdf")
            job = post(
                api, f"/sources/{source['id']}/{kind.removeprefix('source_')}", body, "running-key"
            ).json()
        deadline = time.monotonic() + 5
        while not children and time.monotonic() < deadline:
            time.sleep(0.01)
        assert children
        if action == "cancel":
            assert post(api, f"/jobs/{job['id']}/cancel", key="cancel-running").status_code == 200
            deadline = time.monotonic() + 5
            while children[0].poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            assert children[0].poll() is not None
    assert children[0].poll() is not None
    with client(tmp_path) as api:
        assert api.get(f"/api/v1/jobs/{job['id']}").json()["status"] == (
            "cancelled" if action == "cancel" else "interrupted"
        )
        papers = api.get(f"/api/v1/projects/{project}/papers").json()["items"]
        if kind == "pdf_import":
            assert papers == []
        else:
            assert len(papers) == 1
            assert api.get(f"/api/v1/papers/{papers[0]['id']}").json()["sources"][0] == source
