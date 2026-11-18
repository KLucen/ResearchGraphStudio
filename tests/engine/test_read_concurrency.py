"""Read-only API routes keep working while a SQLite writer is active."""

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from researchgraph.app import create_app
from researchgraph.core import text_hash
from researchgraph.lite_models import LiteCacheEntry, LiteTokenUsage
from researchgraph.models import AttachmentRevision, Chunk, EvidenceSpan, Job, Paper, Section, now
from researchgraph.paper_reading_api import (
    _configuration,
    _hash,
    _identity,
    build_paper_reading_input,
    paper_reading_budget,
)
from researchgraph.paper_reading_contracts import PROMPT_VERSION, SCHEMA_VERSION
from researchgraph.paper_reading_models import PaperReadingResult
from researchgraph.reading_document_models import ReadingDocumentProjection
from researchgraph.storage import make_engine, read_session
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

TOKEN = "read-concurrency-test-token-" * 2
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _client(path: Path) -> TestClient:
    return TestClient(create_app(path, TOKEN, start_worker=False), headers=AUTH)


def _post(api: TestClient, path: str, body: dict, key: str) -> dict:
    response = api.post(
        "/api/v1" + path,
        json=body,
        headers={**AUTH, "Idempotency-Key": key},
    )
    assert response.status_code < 300, response.text
    return response.json()


def _seed_paper(engine, project_id: str) -> tuple[str, str]:
    paper_id, revision_id = str(uuid4()), str(uuid4())
    with Session(engine) as session, session.begin():
        session.add(
            Paper(id=paper_id, project_id=project_id, title="Concurrent paper", created_at=now())
        )
        session.flush()
        session.add(
            AttachmentRevision(
                id=revision_id,
                paper_id=paper_id,
                sha256="a" * 64,
                parser_version="test",
                page_count=1,
                warnings=[],
                created_at=now(),
            )
        )
        session.flush()
        session.add(
            Chunk(
                id=str(uuid4()),
                revision_id=revision_id,
                page_index=0,
                page_label="1",
                block_index=0,
                text="A local paragraph.",
                bbox=[0.0, 0.0, 100.0, 20.0],
            )
        )
    return paper_id, revision_id


def test_read_routes_use_wal_snapshot_while_writer_holds_reserved_lock(tmp_path):
    with _client(tmp_path) as api:
        project = _post(api, "/projects", {"name": "Read project"}, "project-read-lock")
        project_id = project["id"]
        job = _post(api, "/jobs", {"kind": "diagnostics"}, "job-read-lock")
        paper_id, revision_id = _seed_paper(api.app.state.engine, project_id)
        engine = api.app.state.engine
        with Session(engine) as session, session.begin():
            session.get(Job, job["id"]).project_id = project_id
        paths = [
            "/api/v1/projects",
            "/api/v1/jobs",
            f"/api/v1/projects/{project_id}/jobs",
            f"/api/v1/jobs/{job['id']}",
            f"/api/v1/projects/{project_id}/papers",
            f"/api/v1/papers/{paper_id}",
            f"/api/v1/revisions/{revision_id}/chunks",
        ]
        snapshots = {}
        for path in paths:
            response = api.get(path)
            assert response.status_code == 200, (path, response.text)
            snapshots[path] = response.json()
        with Session(engine) as writer:
            # Keep a real, uncommitted write open. Concurrent readers must see
            # the last committed data and never acquire a writer reservation.
            writer.execute(
                text("UPDATE projects SET name='Not committed' WHERE id=:id"),
                {"id": project_id},
            )
            writer.execute(
                text("UPDATE papers SET title='Not committed' WHERE id=:id"),
                {"id": paper_id},
            )
            for path in paths:
                response = api.get(path)
                assert response.status_code == 200, (path, response.text)
                assert response.json() == snapshots[path]
            writer.rollback()


def test_read_session_is_query_only(tmp_path):
    engine = make_engine(tmp_path)
    with read_session(engine) as session:
        assert session.scalar(text("PRAGMA query_only")) == 1
        with pytest.raises(OperationalError) as caught:
            session.execute(text("CREATE TABLE should_not_exist (id INTEGER)"))
        assert getattr(caught.value.orig, "sqlite_errorcode", None) == 8
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='should_not_exist'")
            )
            is None
        )
    with engine.begin() as connection:
        assert connection.scalar(text("PRAGMA query_only")) == 0
        connection.exec_driver_sql("CREATE TABLE writer_still_works (id INTEGER)")
    engine.dispose()


def _seed_completed_notes(engine, project_id: str) -> tuple[str, str, str, str]:
    paper_id, revision_id = _seed_paper(engine, project_id)
    section_id, notes_id = str(uuid4()), str(uuid4())
    with Session(engine) as session, session.begin():
        section = Section(
            id=section_id,
            document_version_id=revision_id,
            title="Method",
            ordinal=0,
            role="method",
            parser="fixture",
            parent_id=None,
            level=1,
            start_page=0,
            end_page=0,
            excluded=False,
        )
        session.add(section)
        session.flush()
        chunk = session.scalar(select(Chunk).where(Chunk.revision_id == revision_id))
        session.add(
            EvidenceSpan(
                id=str(uuid4()),
                document_version_id=revision_id,
                section_id=section_id,
                paragraph_id=chunk.id,
                page_index=chunk.page_index,
                start_offset=0,
                end_offset=len(chunk.text),
                quote=chunk.text,
                text_sha256=text_hash(chunk.text),
                normalization="identity-v1",
                bbox_list=[chunk.bbox],
            )
        )
        session.flush()
        # Use the production projection/input builder: this is specifically a
        # regression for _view -> _stale -> build_paper_reading_input, not a mock.
        paper, revision, context = build_paper_reading_input(session, paper_id, revision_id)
        snapshot = {
            "provider": "synthetic",
            "model": "fixture-model",
            "base_url": "https://provider.invalid/v1",
            "parameters": {},
        }
        key, identity = _identity(paper, revision, context, snapshot)
        session.add(
            PaperReadingResult(
                id=notes_id,
                project_id=project_id,
                paper_id=paper_id,
                document_version_id=revision_id,
                projection_version=context["projection_version"],
                projection_hash=context["projection_hash"],
                source_hash=revision.sha256,
                input_hash=_hash(context),
                cache_key=key,
                schema_version=SCHEMA_VERSION,
                prompt_version=PROMPT_VERSION,
                provider_id="synthetic",
                model_id="fixture-model",
                status="COMPLETED",
                analysis_json={
                    "schema_version": SCHEMA_VERSION,
                    "paragraphs": [
                        {
                            "paragraph_id": paragraph["paragraph_id"],
                            "translation_zh": "一段本地正文。",
                            "paragraph_function": "EXPLAIN_METHOD",
                            "logic_role_zh": "介绍方法。",
                            "critical_note_zh": "",
                            "reading_question_zh": None,
                            "highlights": [],
                            "related_graph_node_ids": [],
                        }
                        for paragraph in context["paragraphs"]
                    ],
                    "paper_argument": {
                        "logic_chain_zh": ["介绍局部方法", "需要回看原文核对"],
                        "core_claim_zh": None,
                        "strong_point_zh": None,
                        "question_to_verify_zh": None,
                    },
                },
                missing_paragraph_ids=[],
                warnings_json=[],
                usage_json={},
                request_metadata={
                    "source_context": context,
                    "estimated": paper_reading_budget(
                        context, snapshot, enforce=False
                    ).model_dump(),
                    "configuration": _configuration(snapshot),
                    "config_fingerprint": identity["config_fingerprint"],
                },
                created_at=now(),
                updated_at=now(),
            )
        )
    return paper_id, revision_id, section_id, notes_id


def _reading_store_snapshot(engine) -> tuple:
    with read_session(engine) as session:
        counts = tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (Job, LiteTokenUsage, LiteCacheEntry)
        )
        projections = [
            (row.id, row.updated_at, row.source_hash, row.projection_hash, row.data)
            for row in session.scalars(
                select(ReadingDocumentProjection).order_by(ReadingDocumentProjection.id)
            )
        ]
        return counts, projections


def test_reading_routes_keep_completed_notes_and_archive_under_writer(tmp_path):
    with _client(tmp_path) as api:
        project_id = _post(
            api, "/projects", {"name": "Reading snapshot"}, "reading-snapshot-project"
        )["id"]
        engine = api.app.state.engine
        paper_id, revision_id, section_id, notes_id = _seed_completed_notes(engine, project_id)
        paper_path = f"/api/v1/papers/{paper_id}"
        section_path = f"{paper_path}/sections/{section_id}"
        paths = [
            f"{paper_path}/reading-document",
            f"{paper_path}/reading-notes",
            f"{paper_path}/reading-notes?result_id={notes_id}",
            f"{paper_path}/section-guides",
            f"{section_path}/guide",
            f"{paper_path}/qa",
            f"{paper_path}/qa/keywords",
            f"{paper_path}/overview",
            f"{paper_path}/overview/graph",
            f"{paper_path}/concept-understanding",
            f"{section_path}/reading-state",
            f"{section_path}/paragraphs",
            f"{section_path}/close-reading",
            f"{section_path}/understanding-check",
            "/api/v1/settings/models",
            f"/api/v1/projects/{project_id}/models",
            "/api/v1/lite/usage",
            f"/api/v1/projects/{project_id}/lite/usage",
            f"/api/v1/projects/{project_id}/lite/usage?paper_id={paper_id}",
        ]
        before = _reading_store_snapshot(engine)
        assert len(before[1]) == 1
        snapshots = {}
        for path in paths:
            response = api.get(path)
            assert response.status_code == 200, (path, response.text)
            snapshots[path] = response.json()
        assert snapshots[f"{paper_path}/reading-notes"]["status"] == "COMPLETED"
        assert snapshots[f"{paper_path}/reading-notes"]["paragraph_count"] == 1
        assert snapshots[f"{section_path}/paragraphs"]["paragraphs"][0]["text_en"]
        assert _reading_store_snapshot(engine) == before
        with Session(engine) as writer:
            writer.execute(
                text("UPDATE projects SET name='Uncommitted reading task' WHERE id=:id"),
                {"id": project_id},
            )
            for path in paths:
                response = api.get(path)
                assert response.status_code == 200, (path, response.text)
                assert response.json() == snapshots[path]
            writer.rollback()
        assert _reading_store_snapshot(engine) == before
