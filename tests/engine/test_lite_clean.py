from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from researchgraph.app import create_app
from researchgraph.core import KnowledgeError
from researchgraph.models import AttachmentRevision, Job, Paper, ZoteroLink, now
from researchgraph.storage import DATABASE_NAME, SCHEMA_HEAD
from sqlalchemy import text
from sqlalchemy.orm import Session

TOKEN = "lite-test-token-" * 3


def client(path: Path, worker: bool = False):
    return TestClient(
        create_app(path, TOKEN, start_worker=worker), headers={"Authorization": f"Bearer {TOKEN}"}
    )


def test_fresh_database_is_lite_only():
    with TemporaryDirectory() as raw:
        data = Path(raw)
        with client(data) as api:
            assert api.get("/api/v1/health").json()["schema_version"] == SCHEMA_HEAD == "lite0008"
            response = api.post(
                "/api/v1/projects",
                json={"name": "Lite"},
                headers={"Idempotency-Key": "project-key-1"},
            )
            assert response.status_code == 201 and response.json()["experience_mode"] == "lite"
        assert (data / DATABASE_NAME).exists()
        with api.app.state.engine.connect() as connection:
            names = {
                row[0]
                for row in connection.execute(
                    text("select name from sqlite_master where type='table'")
                )
            }
            assert (
                "knowledge_nodes" not in names
                and "paper_overview_results" in names
                and "lite_section_guides" in names
            )


def test_legacy_database_name_is_not_opened_or_upgraded(tmp_path):
    (tmp_path / "researchgraph.sqlite3").write_bytes(b"legacy placeholder")
    with client(tmp_path) as api:
        assert api.get("/api/v1/health").status_code == 200
    assert (tmp_path / "researchgraph.sqlite3").read_bytes() == b"legacy placeholder"


def test_local_job_api_and_usage_are_available(tmp_path):
    with client(tmp_path) as api:
        project = api.post(
            "/api/v1/projects", json={"name": "L"}, headers={"Idempotency-Key": "project-key-2"}
        ).json()["id"]
        assert api.get(f"/api/v1/projects/{project}/lite/usage").json()["calls"] == 0
        job = api.post(
            "/api/v1/jobs", json={"kind": "diagnostics"}, headers={"Idempotency-Key": "job-key-1"}
        ).json()
        assert job["status"] == "queued"


def test_old_routes_are_not_registered(tmp_path):
    with client(tmp_path) as api:
        assert api.get("/api/v1/lint/runs").status_code == 404
        assert api.post("/api/v1/knowledge/extract").status_code == 404
        assert api.get("/api/v1/projects/x/query/runs").status_code == 404


def test_zotero_status_and_collections_routes_are_read_only(tmp_path, monkeypatch):
    calls: list[str] = []

    def fake_get(_adapter, route: str):
        calls.append(route)
        return [
            {
                "key": "COLL1234",
                "data": {"name": "Reading", "parentCollection": False},
            }
        ]

    monkeypatch.setattr("researchgraph.integrations.ZoteroAdapter.get", fake_get)
    with client(tmp_path) as api:
        status = api.get("/api/v1/integrations/zotero/status")
        assert status.status_code == 200
        assert status.json() == {"connected": True, "error": None}

        collections = api.get(
            "/api/v1/integrations/zotero/collections",
            params={"library": "users/0", "start": 0},
        )
        assert collections.status_code == 200
        assert collections.json() == [
            {"key": "COLL1234", "data": {"name": "Reading", "parentCollection": False}}
        ]

        assert (
            api.get(
                "/api/v1/integrations/zotero/status", params={"library": "users/not-a-number"}
            ).status_code
            == 422
        )
        assert (
            api.get(
                "/api/v1/integrations/zotero/collections", params={"library": "users/not-a-number"}
            ).status_code
            == 422
        )

    assert calls == ["/users/0/collections?limit=1", "/users/0/collections?limit=50&start=0"]


def test_zotero_status_hides_unavailable_details(tmp_path, monkeypatch):
    def unavailable(_adapter, _route: str):
        raise KnowledgeError("ZOTERO_UNAVAILABLE", "Zotero Local API 未启动、未授权或响应无效")

    monkeypatch.setattr("researchgraph.integrations.ZoteroAdapter.get", unavailable)
    with client(tmp_path) as api:
        response = api.get("/api/v1/integrations/zotero/status")
        assert response.status_code == 200
        assert response.json() == {
            "connected": False,
            "error": "Zotero Local API 未启动、未授权或响应无效",
        }


def test_invalid_zotero_collection_and_selection_never_read_the_library(tmp_path, monkeypatch):
    def unexpected_get(*_args):
        raise AssertionError("invalid input must not reach Zotero")

    monkeypatch.setattr("researchgraph.integrations.ZoteroAdapter.get", unexpected_get)
    with client(tmp_path) as api:
        assert (
            api.post(
                "/api/v1/integrations/zotero/browse",
                json={"library": "users/0", "collection_key": "../../etc"},
            ).status_code
            == 422
        )
        assert (
            api.post(
                "/api/v1/integrations/zotero/browse",
                json={"library": "bad", "collection_key": "COLL1234"},
            ).status_code
            == 422
        )
        assert (
            api.post(
                "/api/v1/projects/not-a-project/zotero-imports",
                json={
                    "library": "users/0",
                    "collection_key": "COLL1234",
                    "selections": [{"item_key": "bad", "attachment_key": "ATTACH12"}],
                },
                headers={"Idempotency-Key": "invalid-zotero-selection"},
            ).status_code
            == 422
        )


def test_zotero_browse_returns_pdf_choices_without_model_calls(tmp_path, monkeypatch):
    attachment = tmp_path / "synthetic.pdf"
    attachment.write_bytes(b"local-only-synthetic-attachment")
    routes: list[str] = []

    def fake_get(_adapter, route):
        routes.append(route)
        if "/collections/" in route:
            return [
                {"key": "PAPER123", "data": {"title": "Synthetic", "itemType": "journalArticle"}}
            ]
        return [
            {
                "key": "ATTACH12",
                "data": {
                    "itemType": "attachment",
                    "contentType": "application/pdf",
                    "title": "PDF",
                    "filename": "synthetic.pdf",
                },
            }
        ]

    monkeypatch.setattr("researchgraph.integrations.ZoteroAdapter.get", fake_get)
    monkeypatch.setattr(
        "researchgraph.integrations.ZoteroAdapter.attachment_path", lambda *_: attachment
    )
    with client(tmp_path / "data") as api:
        result = api.post(
            "/api/v1/integrations/zotero/browse",
            json={"library": "users/0", "collection_key": "COLL1234", "search": "method"},
        )
        assert result.status_code == 200
        assert result.json() == {
            "items": [
                {
                    "key": "PAPER123",
                    "title": "Synthetic",
                    "item_type": "journalArticle",
                    "attachments": [
                        {
                            "key": "ATTACH12",
                            "title": "PDF",
                            "filename": "synthetic.pdf",
                            "available": True,
                        }
                    ],
                }
            ],
            "next_start": None,
        }
        assert api.get("/api/v1/jobs").json() == []
    assert routes == [
        "/users/0/collections/COLL1234/items/top?limit=10&start=0&q=method&qmode=titleCreatorYear",
        "/users/0/items/PAPER123/children?limit=100",
    ]


@pytest.mark.parametrize(
    ("status", "stage"),
    [
        ("queued", "queued"),
        ("running", "generating"),
        ("succeeded", "completed"),
        ("failed", "failed"),
        ("interrupted", "interrupted"),
    ],
)
def test_overview_job_stages_are_visible_in_job_routes(tmp_path, status, stage):
    with client(tmp_path) as api:
        project = api.post(
            "/api/v1/projects",
            json={"name": "Stages"},
            headers={"Idempotency-Key": "stage-project"},
        ).json()["id"]
        job_id = str(uuid4())
        with Session(api.app.state.engine) as session, session.begin():
            session.add(
                Job(
                    id=job_id,
                    project_id=project,
                    kind="paper_overview",
                    status=status,
                    stage=stage,
                    attempt=1,
                    created_at=now(),
                    updated_at=now(),
                )
            )
        for path in (f"/api/v1/jobs/{job_id}", "/api/v1/jobs", f"/api/v1/projects/{project}/jobs"):
            response = api.get(path)
            assert response.status_code == 200, response.text
            body = response.json()
            selected = (
                body[0] if isinstance(body, list) else body["items"][0] if "items" in body else body
            )
            assert selected["stage"] == stage


@pytest.mark.parametrize(
    ("library", "native_scope"),
    [("users/0", "library"), ("users/123", "library"), ("groups/42", "groups/42")],
)
def test_paper_details_use_valid_native_zotero_urls(tmp_path, library, native_scope):
    with client(tmp_path) as api:
        project = api.post(
            "/api/v1/projects",
            json={"name": "Links"},
            headers={"Idempotency-Key": "link-project"},
        ).json()["id"]
        paper_id, revision_id = str(uuid4()), str(uuid4())
        with Session(api.app.state.engine) as session, session.begin():
            session.add(Paper(id=paper_id, project_id=project, title="Synthetic", created_at=now()))
            session.flush()
            session.add(
                AttachmentRevision(
                    id=revision_id,
                    paper_id=paper_id,
                    sha256="a" * 64,
                    parser_version="synthetic",
                    page_count=1,
                    warnings=[],
                    created_at=now(),
                )
            )
            session.flush()
            session.add(
                ZoteroLink(
                    id=str(uuid4()),
                    paper_id=paper_id,
                    document_version_id=revision_id,
                    library_id=library,
                    item_key="PAPER123",
                    attachment_key="ATTACH12",
                    metadata_snapshot={},
                )
            )
        response = api.get(f"/api/v1/papers/{paper_id}")
        assert response.status_code == 200
        assert (
            response.json()["zotero_links"][0]["url"]
            == f"zotero://select/{native_scope}/items/PAPER123"
        )
