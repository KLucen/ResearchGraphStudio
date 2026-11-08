"""Lint scope discovery includes damaged/draft documents without exposing private titles."""

from researchgraph.knowledge_store import KnowledgeStore
from researchgraph.models import Chunk
from researchgraph.query_documents import read_passages
from researchgraph.query_models import QueryPassage
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_engine import client
from test_query_documents import add_note
from test_query_documents import engine as engine
from test_wiki_documents import draft, passage


def test_lint_document_catalogue_includes_drafts_and_broken_sources(engine, tmp_path):
    view = draft(engine)
    with Session(engine) as session, session.begin():
        session.get(Chunk, "c").text = "Changed source, intentionally invalid."
    with client(tmp_path / "data") as api:
        response = api.get("/api/v1/projects/p/lint/documents?page_size=1")
        assert response.status_code == 200
        assert response.json() == {
            "items": [
                {
                    "id": view["page_id"],
                    "title": "Synthetic Wiki",
                    "kind": "wiki",
                    "status": "draft",
                    "current_version_id": None,
                    "latest_version_id": view["version_id"],
                }
            ],
            "total": 1,
            "page": 1,
            "page_size": 1,
        }
        assert api.get("/api/v1/projects/p/lint/documents?page=2&page_size=1").json()["items"] == []
        assert api.get("/api/v1/projects/other/lint/documents").json()["total"] == 0
        assert api.get("/api/v1/projects/missing/lint/documents").status_code == 404
        assert api.get("/api/v1/projects/p/lint/documents?page_size=101").status_code == 422
    with Session(engine) as session:
        assert read_passages(session, "p") == []
        assert len(list(session.scalars(select(QueryPassage)))) == 2


def test_private_document_scope_metadata_requires_current_permission(engine, tmp_path):
    with Session(engine) as session, session.begin():
        root, note, _ = add_note(session, tmp_path)
        root_id, note_id, note_hash = root.id, note.id, note.sha256
    view = draft(
        engine,
        [
            passage(
                "Personal opinion.",
                attribution="user_view",
                dependencies=[{"type": "note", "id": note_id, "sha256": note_hash}],
            )
        ],
    )
    with client(tmp_path / "data") as api:
        assert api.get("/api/v1/projects/p/lint/documents").json()["items"] == []
        allowed = api.get("/api/v1/projects/p/lint/documents?include_personal=true").json()
        assert [row["id"] for row in allowed["items"]] == [view["page_id"]]
        with Session(engine) as session, session.begin():
            KnowledgeStore(session).query().set_note_grant("p", root_id, False, False)
        denied = api.get("/api/v1/projects/p/lint/documents?include_personal=true")
        assert denied.status_code == 200 and denied.json()["items"] == []
        assert "Synthetic Wiki" not in denied.text


def test_external_document_scope_keeps_missing_file_but_hides_revoked_title(engine, tmp_path):
    with Session(engine) as session, session.begin():
        root, note, path = add_note(session, tmp_path)
        root_id, sha256 = root.id, note.sha256
    original = path.read_bytes()
    with client(tmp_path / "data") as api:
        registered = api.post(
            "/api/v1/projects/p/external-documents?include_personal=true",
            json={
                "root_id": root_id,
                "relative_path": "note.md",
                "expected_sha256": sha256,
                "title": "External private title",
                "attribution": "external_source",
            },
            headers={"Idempotency-Key": "lint-external-register"},
        )
        assert registered.status_code == 200, registered.text
        document_id = registered.json()["document_id"]
        assert path.read_bytes() == original
        assert api.get("/api/v1/projects/p/lint/documents").json()["items"] == []
        path.unlink()  # Only this generated temporary fixture; keep the snapshot for diagnosis.
        scope = api.get("/api/v1/projects/p/lint/documents?include_personal=true").json()
        assert scope["total"] == 1 and scope["items"][0]["id"] == document_id
        assert scope["items"][0]["kind"] == "external"
        with Session(engine) as session, session.begin():
            KnowledgeStore(session).query().set_note_grant("p", root_id, False, False)
        assert (
            api.get("/api/v1/projects/p/lint/documents?include_personal=true").json()["items"] == []
        )
