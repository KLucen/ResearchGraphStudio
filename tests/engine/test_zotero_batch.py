import hashlib
from pathlib import Path

import pytest
from researchgraph.integrations import ZoteroAdapter
from researchgraph.knowledge_models import ModelRun, ZoteroLink
from researchgraph.models import AttachmentRevision, Paper
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_engine import client, post
from test_ingest import wait_job


@pytest.fixture
def zotero(monkeypatch, tmp_path):
    path = tmp_path / "authorized.pdf"
    path.write_bytes((Path(__file__).parents[1] / "fixtures/pdf/two-pages.pdf").read_bytes())
    item = {
        "key": "PAPER001",
        "data": {
            "title": "Synthetic Zotero paper",
            "itemType": "journalArticle",
            "collections": ["COLLECT1"],
        },
    }
    attachment = {
        "key": "ATTACH01",
        "data": {
            "itemType": "attachment",
            "parentItem": "PAPER001",
            "contentType": "application/pdf",
            "filename": "fixture.pdf",
        },
    }

    def get(self, route):
        if "/items/top?" in route:
            return [item]
        if "/children?" in route:
            return [attachment]
        if route.endswith("ATTACH01"):
            return attachment
        return item

    monkeypatch.setattr(ZoteroAdapter, "get", get)
    monkeypatch.setattr(ZoteroAdapter, "attachment_path", lambda *_: path)
    monkeypatch.setattr(ZoteroAdapter, "read_annotations", lambda *_: (item, [], path))
    return path


def body(collection="COLLECT1"):
    return {
        "collection_key": collection,
        "selections": [{"item_key": "PAPER001", "attachment_key": "ATTACH01"}],
    }


def test_browse_import_dedup_and_restart(tmp_path, zotero):
    original = hashlib.sha256(zotero.read_bytes()).hexdigest()
    with client(tmp_path / "data", worker=True) as api:
        project = post(api, "/projects", {"name": "Batch"}).json()["id"]
        page = post(api, "/integrations/zotero/browse", {"collection_key": "COLLECT1"})
        assert page.status_code == 200, page.text
        assert page.json()["items"][0]["attachments"][0]["available"]
        route = f"/projects/{project}/zotero-imports"
        result = post(api, route, body(), "first-batch")
        assert result.status_code == 202, result.text
        first = wait_job(api, result.json()[0]["job"])
        assert first["status"] == "succeeded", first
        assert post(api, route, body(), "first-batch").json() == result.json()
        second = post(api, route, body(), "second-batch")
        second_job = wait_job(api, second.json()[0]["job"])
        assert second_job["status"] == "succeeded" and second_job["result"]["reused"]
        with Session(api.app.state.engine) as session:
            assert session.scalar(select(func.count()).select_from(Paper)) == 1
            assert session.scalar(select(func.count()).select_from(AttachmentRevision)) == 1
            assert session.scalar(select(func.count()).select_from(ZoteroLink)) == 1
        assert hashlib.sha256(zotero.read_bytes()).hexdigest() == original
    with client(tmp_path / "data") as reopened:
        assert len(reopened.get("/api/v1" + route).json()) == 2


def test_lite_zotero_selection_forces_local_only(tmp_path, zotero):
    with client(tmp_path / "data", worker=True) as api:
        project = post(
            api,
            "/projects",
            {"name": "Lite local", "experience_mode": "lite"},
        ).json()["id"]
        route = f"/projects/{project}/zotero-imports"
        result = post(
            api,
            route,
            {**body(), "extract_after_parse": True, "allow_network": True},
            "lite-local-only",
        )
        assert result.status_code == 202, result.text
        completed = wait_job(api, result.json()[0]["job"])
        assert completed["status"] == "succeeded", completed
        assert "extraction_job_id" not in completed["result"]
        with Session(api.app.state.engine) as session:
            assert session.scalar(select(func.count()).select_from(ModelRun)) == 0


def test_collection_mismatch_fails_without_ingest_and_retry_recovers(tmp_path, zotero, monkeypatch):
    with client(tmp_path / "data", worker=True) as api:
        project = post(api, "/projects", {"name": "Batch"}).json()["id"]
        result = post(api, f"/projects/{project}/zotero-imports", body("OTHER001"))
        job = wait_job(api, result.json()[0]["job"])
        assert job["status"] == "failed" and "分类" in job["error"]
        with Session(api.app.state.engine) as session:
            assert session.scalar(select(func.count()).select_from(Paper)) == 0
        monkeypatch.setattr(
            ZoteroAdapter,
            "read_annotations",
            lambda *_: (
                {"key": "PAPER001", "data": {"title": "Fixture", "collections": ["OTHER001"]}},
                [],
                zotero,
            ),
        )
        assert post(api, f"/jobs/{job['id']}/retry").status_code == 200
        assert wait_job(api, job)["status"] == "succeeded"
