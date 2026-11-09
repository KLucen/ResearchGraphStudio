"""Additive parser publication/reparse checks on isolated synthetic sources."""

import asyncio
import sqlite3
from pathlib import Path

import pymupdf
import pytest
from alembic import command
from alembic.config import Config
from researchgraph.document_structure import current_structure, section_entries
from researchgraph.ingest import ensure_structured_source
from researchgraph.knowledge_models import EvidenceSpan
from researchgraph.models import Chunk, Job
from researchgraph.storage import make_engine, migrate
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_engine import client, post
from test_ingest import queue, wait_job


def synthetic(path):
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((50, 90), "1 Methods", fontsize=16, fontname="hebo")
        page.insert_text((50, 125), "The method compares two treatments.", fontsize=11)
        page = doc.new_page()
        page.insert_text((50, 90), "The method continues across a page boundary.", fontsize=11)
        page.insert_text((50, 180), "References", fontsize=16, fontname="hebo")
        page.insert_text((50, 215), "[1] A cited work, 2025.", fontsize=11)
        doc.save(path)


def test_import_publishes_tree_and_reference_spans_without_sending_references(tmp_path):
    source = tmp_path / "structured.pdf"
    synthetic(source)
    with client(tmp_path / "data", worker=True) as api:
        project = post(api, "/projects", {"name": "Synthetic"}).json()["id"]
        done = wait_job(api, queue(api, project, source, "structure-import"))
        assert done["status"] == "succeeded", done
        version = done["result"]["revision_id"]
        structure = api.get(f"/api/v1/revisions/{version}/structure").json()
        assert structure["structured_document"]["schema_version"] == "pdf-structure-1"
        method = next(s for s in structure["sections"] if s["title"] == "1 Methods")
        ids = {e["section_id"] for e in structure["evidence"] if "method" in e["quote"]}
        assert ids == {method["id"]}
        assert any("cited work" in e["quote"] for e in structure["evidence"])
        with Session(api.app.state.engine) as session:
            artifact = current_structure(session, version)
            spans = list(session.scalars(select(EvidenceSpan)))
            entries, metadata = section_entries(artifact, spans)
            assert not any("cited work" in e["text"] for e in entries)
            assert len(entries) < len(spans)
            assert all(metadata[e["id"]]["section_path"] for e in entries)
        assert source.is_file()
        assert not (tmp_path / "data" / "attachments").exists()


def test_lazy_reparse_preserves_existing_rows_and_source_hash(tmp_path):
    source = tmp_path / "structured.pdf"
    synthetic(source)
    data = tmp_path / "data"
    with client(data, worker=True) as api:
        project = post(api, "/projects", {"name": "Synthetic"}).json()["id"]
        done = wait_job(api, queue(api, project, source, "lazy-reparse"))
        version = done["result"]["revision_id"]
        engine = api.app.state.engine
        with Session(engine) as session, session.begin():
            artifact = current_structure(session, version)
            session.delete(artifact)
            job = Job(
                id="reparse",
                project_id=project,
                kind="knowledge_extract",
                payload={},
                status="running",
                attempt=1,
                created_at="now",
                updated_at="now",
            )
            session.add(job)
            before = [(e.id, e.quote, e.section_id) for e in session.scalars(select(EvidenceSpan))]
            blocks = [(c.id, c.text, c.bbox) for c in session.scalars(select(Chunk))]
        asyncio.run(ensure_structured_source(engine, "reparse", version, data))
        with Session(engine) as session:
            assert current_structure(session, version)
            assert before == [
                (e.id, e.quote, e.section_id) for e in session.scalars(select(EvidenceSpan))
            ]
            assert blocks == [(c.id, c.text, c.bbox) for c in session.scalars(select(Chunk))]
        # Changed source cannot be attached to an old version.
        with Session(engine) as session, session.begin():
            session.delete(current_structure(session, version))
        source.write_bytes(b"%PDF-invalid")
        with pytest.raises(ValueError, match="原版本 PDF"):
            asyncio.run(ensure_structured_source(engine, "reparse", version, data))
        with Session(engine) as session:
            assert current_structure(session, version) is None


def test_0010_to_0011_is_additive_and_backed_up(tmp_path):
    engine = make_engine(tmp_path)
    config = Config()
    config.set_main_option(
        "script_location", str(Path("services/engine/researchgraph/migrations").resolve())
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0010")
        connection.exec_driver_sql(
            "INSERT INTO projects (id, name, description, created_at) VALUES "
            "('p','Synthetic','', 'now')"
        )
    database = tmp_path / "researchgraph.sqlite3"
    with sqlite3.connect(database) as db:
        tables = [
            r[0]
            for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name!='alembic_version'"
            )
        ]
        before = {
            t: db.execute(
                'SELECT id, name, description, created_at FROM "projects"'
                if t == "projects"
                else f'SELECT * FROM "{t}"'
            ).fetchall()
            for t in tables
        }
    migrate(engine, tmp_path)
    with sqlite3.connect(database) as db:
        after = {
            t: db.execute(
                'SELECT id, name, description, created_at FROM "projects"'
                if t == "projects"
                else f'SELECT * FROM "{t}"'
            ).fetchall()
            for t in tables
        }
        assert before == after
        from researchgraph.storage import SCHEMA_HEAD

        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (SCHEMA_HEAD,)
        assert db.execute("SELECT * FROM document_parses").fetchall() == []
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    with sqlite3.connect(next((tmp_path / "backups").glob("*.sqlite3"))) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0010",)
    engine.dispose()
