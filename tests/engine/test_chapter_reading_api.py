"""Model-first reading progress is local, versioned and retained across restarts."""

import sqlite3
from uuid import uuid4

from researchgraph.chapter_reading_models import ModelChapterReadingState
from researchgraph.model_document_api import materialize_document_parse
from researchgraph.model_document_contracts import ModelDocumentParseInput
from researchgraph.models import Paper, now
from researchgraph.storage import DATABASE_NAME
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_engine import client, post


def _parse(api, session_id):
    body = ModelDocumentParseInput.model_validate(
        {
            "parse_version": "llm-document-1",
            "segments": [
                {
                    "chapter_ref": ref,
                    "chapter_title": ref,
                    "chapter_order": index,
                    "chapter_level": level,
                    "kind": "paragraph",
                    "text": "Synthetic text.",
                }
                for index, (ref, level) in enumerate(
                    [("intro", 1), ("background", 2), ("results", 1)]
                )
            ],
        }
    )
    with Session(api.app.state.engine) as db, db.begin():
        parse = materialize_document_parse(db, session_id, body)
        return parse.id


def _fixture(api):
    project = post(api, "/projects", {"name": "Chapter reading fixture"}).json()
    paper_id = str(uuid4())
    with Session(api.app.state.engine) as db, db.begin():
        db.add(
            Paper(id=paper_id, project_id=project["id"], title="Synthetic paper", created_at=now())
        )
    imported = post(
        api,
        f"/projects/{project['id']}/import-sessions",
        {
            "selection_id": "synthetic",
            "source_snapshot": {"paper_id": paper_id},
            "plan": {"overview": False, "reading": False},
        },
        key=f"chapter-reading-{paper_id}",
    ).json()
    return project["id"], paper_id, imported["id"], _parse(api, imported["id"])


def test_major_chapter_progress_persists_without_model_and_cleanup_keeps_it(tmp_path):
    with client(tmp_path) as api:
        project_id, paper_id, session_id, parse_id = _fixture(api)
        path = f"/api/v1/import-sessions/{session_id}/chapter-reading-states"
        initial = api.get(path).json()
        assert [row["chapter_ref"] for row in initial["items"]] == ["intro", "results"]
        assert all(row["progress"] == "NOT_STARTED" for row in initial["items"])
        body = {"parse_id": parse_id, "chapter_ref": "intro", "progress": "COMPLETED"}
        result = api.put(path, json=body)
        assert result.status_code == 200, result.text
        saved = result.json()
        assert saved["updated_at"]
        assert api.put(path, json=body).json() == saved
        archived_cleanup = api.delete(f"/api/v1/papers/{paper_id}/legacy-content")
        assert archived_cleanup.status_code == 200, archived_cleanup.text
        cleanup = api.delete(f"/api/v1/archive/{archived_cleanup.json()['archive_item_id']}")
        assert cleanup.status_code == 200, cleanup.text
        assert api.get(path).json()["items"][0] == saved
        usage = api.get(f"/api/v1/projects/{project_id}/lite/usage").json()
        assert usage["calls"] == 0
    with client(tmp_path) as reopened:
        assert reopened.get(path).json()["items"][0] == saved
        archived = reopened.delete(f"/api/v1/papers/{paper_id}")
        assert archived.status_code == 200, archived.text
        for response in (
            reopened.get(path),
            reopened.put(path, json={**body, "progress": "READING"}),
        ):
            assert response.status_code == 409, response.text
            assert response.json()["error"]["code"] == "PAPER_ARCHIVED"
        restored = post(reopened, f"/archive/{archived.json()['archive_item_id']}/restore")
        assert restored.status_code == 200, restored.text
        assert reopened.get(path).json()["items"][0] == saved


def test_progress_rejects_foreign_subchapter_and_stale_parse(tmp_path):
    with client(tmp_path) as api:
        _project_id, _paper_id, session_id, parse_id = _fixture(api)
        path = f"/api/v1/import-sessions/{session_id}/chapter-reading-states"
        body = {"parse_id": parse_id, "chapter_ref": "background", "progress": "READING"}
        assert api.put(path, json=body).status_code == 422
        assert api.put(path, json={**body, "chapter_ref": "unknown"}).status_code == 422
        assert api.put(path, json={**body, "progress": "INVENTED"}).status_code == 422
        assert (
            api.put(
                path, json={**body, "chapter_ref": "intro", "parse_id": str(uuid4())}
            ).status_code
            == 409
        )
        assert api.put(path, json={**body, "chapter_ref": "intro"}).status_code == 200
        new_parse_id = _parse(api, session_id)
        assert new_parse_id != parse_id
        current = api.get(path).json()
        assert current["parse_id"] == new_parse_id
        assert all(row["progress"] == "NOT_STARTED" for row in current["items"])
        assert api.put(path, json={**body, "chapter_ref": "intro"}).status_code == 409
        with Session(api.app.state.engine) as db:
            old_state = db.scalar(
                select(ModelChapterReadingState).where(
                    ModelChapterReadingState.parse_id == parse_id
                )
            )
            assert old_state is not None and old_state.progress == "READING"
            assert (
                db.scalar(
                    select(ModelChapterReadingState).where(
                        ModelChapterReadingState.parse_id == new_parse_id
                    )
                )
                is None
            )


def test_foreign_parse_cannot_mark_or_delete_another_papers_progress(tmp_path):
    with client(tmp_path) as api:
        _project, paper_id, session_id, parse_id = _fixture(api)
        _other_project, other_paper_id, other_session_id, other_parse_id = _fixture(api)
        path = f"/api/v1/import-sessions/{session_id}/chapter-reading-states"
        other_path = f"/api/v1/import-sessions/{other_session_id}/chapter-reading-states"
        foreign_body = {
            "parse_id": other_parse_id,
            "chapter_ref": "intro",
            "progress": "COMPLETED",
        }
        assert api.put(path, json=foreign_body).status_code == 409
        assert all(row["progress"] == "NOT_STARTED" for row in api.get(path).json()["items"])
        assert api.put(path, json={**foreign_body, "parse_id": parse_id}).status_code == 200
        other_saved = api.put(other_path, json=foreign_body).json()
        assert other_saved["progress"] == "COMPLETED"

        archived = api.delete(f"/api/v1/papers/{paper_id}")
        assert archived.status_code == 200, archived.text
        assert api.get(other_path).json()["items"][0] == other_saved
        deleted = api.delete(f"/api/v1/archive/{archived.json()['archive_item_id']}")
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["removed"]["llm_chapter_reading_states"] == 1
        assert api.get(path).status_code == 404
        assert api.get(f"/api/v1/papers/{other_paper_id}").status_code == 200
        assert api.get(other_path).json()["items"][0] == other_saved
        with Session(api.app.state.engine) as db:
            remaining = list(db.scalars(select(ModelChapterReadingState)))
            assert [(row.parse_id, row.chapter_ref) for row in remaining] == [
                (other_parse_id, "intro")
            ]


def test_lite0011_upgrade_preserves_existing_rows_and_creates_progress_table(tmp_path):
    with client(tmp_path) as api:
        _project, _paper, session_id, parse_id = _fixture(api)
    # Simulate the previous schema in an isolated database: its model-document
    # rows remain byte-for-byte intact while only the new table is absent.
    database = tmp_path / DATABASE_NAME
    with sqlite3.connect(database) as db:
        old_rows = db.execute("SELECT * FROM llm_document_segments ORDER BY id").fetchall()
        db.execute("DROP TABLE llm_chapter_reading_states")
        db.execute("UPDATE alembic_version SET version_num='lite0011'")
    with client(tmp_path) as api:
        assert api.get("/api/v1/health").json()["schema_version"] == "lite0020"
        response = api.get(f"/api/v1/import-sessions/{session_id}/chapter-reading-states")
        assert response.status_code == 200 and response.json()["parse_id"] == parse_id
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT * FROM llm_document_segments ORDER BY id").fetchall() == old_rows
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert list((tmp_path / "backups").glob("before-migration-*.sqlite3"))
