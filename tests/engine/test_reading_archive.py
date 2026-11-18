"""Persisted reading views remain local and readable while a writer is busy."""

import sqlite3
from copy import deepcopy

import pymupdf
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from researchgraph.core import text_hash
from researchgraph.models import AttachmentRevision, Chunk, EvidenceSpan
from researchgraph.reading_document_api import register_reading_document_api
from researchgraph.reading_document_models import ReadingDocumentProjection
from researchgraph.reading_projection import (
    build_reading_document,
    prepare_reading_document,
    publish_reading_document,
)
from researchgraph.storage import DATABASE_NAME, make_engine, read_session
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session
from test_reading_projection import store, textbox


def archived_fixture(tmp_path):
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        page.insert_text((40, 90), "1 Methods", fontsize=15, fontname="hebo")
        textbox(page, 40, 150, "A saved paragraph remains available without reopening its PDF.")
        source, paper, revision = store(document, tmp_path)
    # The application's WAL/BEGIN policy matters here; an in-memory SQLite
    # fixture without make_engine would miss the original lock conflict.
    with source.raw_connection() as connection:
        with sqlite3.connect(tmp_path / DATABASE_NAME) as target:
            connection.driver_connection.backup(target)
    source.dispose()
    return make_engine(tmp_path), paper, revision


def forbid_rebuild(*_args, **_kwargs):
    raise AssertionError("a warm local archive must not reassemble or reopen the PDF")


def test_archive_survives_restart_without_reassembly_or_writer_lock(tmp_path, monkeypatch):
    engine, paper, revision = archived_fixture(tmp_path)
    with Session(engine) as session, session.begin():
        saved = build_reading_document(session, paper, revision)
        row = session.scalar(select(ReadingDocumentProjection))
        original = deepcopy(row.data), row.updated_at
    engine.dispose()
    engine = make_engine(tmp_path)
    (tmp_path / "anonymous.pdf").unlink()
    monkeypatch.setattr("researchgraph.reading_projection._assemble", forbid_rebuild)
    monkeypatch.setattr("researchgraph.reading_projection._scan_pdf", forbid_rebuild)
    app = FastAPI()
    register_reading_document_api(app, lambda: engine, tmp_path)
    statements = []
    # A committed local archive must still open while another connection owns
    # an uncommitted write, instead of competing for BEGIN IMMEDIATE.
    with Session(engine) as writer, writer.begin():
        writer.execute(text("UPDATE papers SET title='uncommitted' WHERE id=:id"), {"id": paper})

        def capture(_connection, _cursor, statement, _parameters, _context, _many):
            statements.append(statement.strip().upper())

        event.listen(engine, "before_cursor_execute", capture)
        try:
            response = TestClient(app).get(f"/api/v1/papers/{paper}/reading-document")
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        assert response.status_code == 200
        assert response.json() == saved.model_dump()
        assert "BEGIN IMMEDIATE" not in statements
        assert not any(
            statement.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "DROP"))
            for statement in statements
        )
    with read_session(engine) as session:
        row = session.scalar(select(ReadingDocumentProjection))
        assert (row.data, row.updated_at) == original


def test_readonly_cold_fallback_never_writes_or_reads_external_pdf(tmp_path, monkeypatch):
    engine, paper, revision = archived_fixture(tmp_path)
    monkeypatch.setattr("researchgraph.reading_projection._scan_pdf", forbid_rebuild)
    with Session(engine) as writer, writer.begin():
        writer.execute(text("UPDATE papers SET title='pending' WHERE id=:id"), {"id": paper})
        with read_session(engine) as session:
            view = build_reading_document(session, paper, revision)
            assert any(unit.kind == "paragraph" for unit in view.units)
            assert session.scalar(select(ReadingDocumentProjection)) is None
    with read_session(engine) as session:
        assert session.scalar(select(ReadingDocumentProjection)) is None


def test_legacy_archive_upgrades_once_and_ordinary_reads_reuse_it(tmp_path, monkeypatch):
    engine, paper, revision = archived_fixture(tmp_path)
    with Session(engine) as session, session.begin():
        expected = build_reading_document(session, paper, revision)
        row = session.scalar(select(ReadingDocumentProjection))
        row.data = {key: value for key, value in row.data.items() if not key.startswith("archive_")}
    monkeypatch.setattr("researchgraph.reading_projection._scan_pdf", forbid_rebuild)
    with read_session(engine) as session:
        prepared = prepare_reading_document(session, paper, revision)
        assert prepared.needs_write
        assert prepared.view == expected
    with Session(engine) as session, session.begin():
        assert publish_reading_document(session, prepared)
    monkeypatch.setattr("researchgraph.reading_projection._assemble", forbid_rebuild)
    with read_session(engine) as session:
        assert build_reading_document(session, paper, revision) == expected


@pytest.mark.parametrize("part", ["view", "source", "layout", "span_bbox"])
def test_changed_archive_or_source_is_not_trusted(tmp_path, monkeypatch, part):
    engine, paper, revision = archived_fixture(tmp_path)
    with Session(engine) as session, session.begin():
        expected = build_reading_document(session, paper, revision)
        row = session.scalar(select(ReadingDocumentProjection))
        if part == "view":
            modified = deepcopy(row.data)
            modified["view"]["units"][0]["text"] = "damaged persisted text"
            row.data = modified
        elif part == "source":
            chunk = session.scalar(select(Chunk).where(Chunk.revision_id == revision))
            span = session.scalar(select(EvidenceSpan).where(EvidenceSpan.paragraph_id == chunk.id))
            chunk.text = chunk.text.replace("Methods", "Changed")
            span.quote = chunk.text
            span.end_offset = len(chunk.text)
            span.text_sha256 = text_hash(chunk.text)
        elif part == "span_bbox":
            span = session.scalar(select(EvidenceSpan))
            span.bbox_list = [[0.0, 0.0, 1.0, 1.0]]
        else:
            from researchgraph.document_structure import current_structure

            artifact = current_structure(session, revision)
            changed = deepcopy(artifact.data)
            changed.setdefault("warnings", []).append("new local layout warning")
            artifact.data = changed
    calls = []
    from researchgraph import reading_projection

    assemble = reading_projection._assemble

    def observed(*args, **kwargs):
        calls.append(True)
        return assemble(*args, **kwargs)

    monkeypatch.setattr(reading_projection, "_assemble", observed)
    with read_session(engine) as session:
        if part in {"source", "span_bbox"}:
            from researchgraph.core import KnowledgeError

            with pytest.raises(KnowledgeError):
                build_reading_document(session, paper, revision)
        else:
            actual = build_reading_document(session, paper, revision)
            assert calls
            assert actual.units == expected.units


def test_prepared_archive_cannot_overwrite_a_newer_published_view(tmp_path):
    engine, paper, revision = archived_fixture(tmp_path)
    with read_session(engine) as session:
        prepared = prepare_reading_document(session, paper, revision)
    with Session(engine) as session, session.begin():
        assert publish_reading_document(session, prepared)
        row = session.scalar(select(ReadingDocumentProjection))
        published = deepcopy(row.data)
    with Session(engine) as session, session.begin():
        assert not publish_reading_document(session, prepared)
        assert session.scalar(select(ReadingDocumentProjection)).data == published


def test_explicit_refresh_rebuilds_once_and_replaces_only_the_derived_archive(
    tmp_path, monkeypatch
):
    engine, paper, revision = archived_fixture(tmp_path)
    from researchgraph import reading_projection

    scans, assemblies = [], []
    scan, assemble = reading_projection._scan_pdf, reading_projection._assemble

    def observed_scan(*args, **kwargs):
        scans.append(True)
        return scan(*args, **kwargs)

    def observed_assemble(*args, **kwargs):
        assemblies.append(True)
        return assemble(*args, **kwargs)

    monkeypatch.setattr(reading_projection, "_scan_pdf", observed_scan)
    monkeypatch.setattr(reading_projection, "_assemble", observed_assemble)
    with Session(engine) as session, session.begin():
        first = build_reading_document(session, paper, revision)
    assert len(scans) == 0 and len(assemblies) == 1
    with Session(engine) as session, session.begin():
        refreshed = build_reading_document(
            session, paper, revision, refresh=True, data_dir=tmp_path
        )
    assert len(scans) == 1 and len(assemblies) == 2
    assert refreshed.projection_hash == first.projection_hash
    assert refreshed.refreshed_at
    monkeypatch.setattr(reading_projection, "_scan_pdf", forbid_rebuild)
    monkeypatch.setattr(reading_projection, "_assemble", forbid_rebuild)
    with read_session(engine) as session:
        assert build_reading_document(session, paper, revision) == refreshed


def test_first_get_persists_archive_and_second_get_never_reassembles(tmp_path, monkeypatch):
    engine, paper, _revision = archived_fixture(tmp_path)
    app = FastAPI()
    register_reading_document_api(app, lambda: engine, tmp_path)
    client = TestClient(app)
    monkeypatch.setattr("researchgraph.reading_projection._scan_pdf", forbid_rebuild)
    with read_session(engine) as session:
        assert session.scalar(select(ReadingDocumentProjection)) is None
    first = client.get(f"/api/v1/papers/{paper}/reading-document")
    assert first.status_code == 200
    with read_session(engine) as session:
        row = session.scalar(select(ReadingDocumentProjection))
        assert row.data["view"] == first.json()
        assert row.data["archive_fingerprint"] and row.data["archive_view_hash"]
    monkeypatch.setattr("researchgraph.reading_projection._assemble", forbid_rebuild)
    second = client.get(f"/api/v1/papers/{paper}/reading-document")
    assert second.status_code == 200 and second.json() == first.json()


def test_cold_get_remains_readable_and_defers_archive_when_writer_is_busy(tmp_path, monkeypatch):
    engine, paper, _revision = archived_fixture(tmp_path)
    app = FastAPI()
    register_reading_document_api(app, lambda: engine, tmp_path)
    client = TestClient(app)
    monkeypatch.setattr("researchgraph.reading_projection._scan_pdf", forbid_rebuild)
    with Session(engine) as writer, writer.begin():
        writer.execute(text("UPDATE papers SET title='pending' WHERE id=:id"), {"id": paper})
        first = client.get(f"/api/v1/papers/{paper}/reading-document")
        assert first.status_code == 200
        with read_session(engine) as session:
            assert session.scalar(select(ReadingDocumentProjection)) is None
    second = client.get(f"/api/v1/papers/{paper}/reading-document")
    assert second.status_code == 200 and second.json() == first.json()
    with read_session(engine) as session:
        assert session.scalar(select(ReadingDocumentProjection)).data["view"] == second.json()


def test_refresh_pdf_scan_runs_without_holding_the_writer_transaction(tmp_path, monkeypatch):
    engine, paper, _revision = archived_fixture(tmp_path)
    app = FastAPI()
    register_reading_document_api(app, lambda: engine, tmp_path)
    from researchgraph import reading_document_api

    scan = reading_document_api._scan_pdf
    writable_during_scan = []

    def observed_scan(*args, **kwargs):
        with (
            Session(engine.execution_options(sqlite_busy_timeout_ms=0)) as writer,
            writer.begin(),
        ):
            writer.execute(
                text("UPDATE papers SET title='changed while scanning' WHERE id=:id"),
                {"id": paper},
            )
            writable_during_scan.append(True)
        return scan(*args, **kwargs)

    monkeypatch.setattr(reading_document_api, "_scan_pdf", observed_scan)
    response = TestClient(app).post(f"/api/v1/papers/{paper}/reading-document/refresh", json={})
    assert response.status_code == 200
    assert response.json()["refreshed_at"]
    assert writable_during_scan == [True]


def test_refresh_rechecks_source_after_outside_transaction_scan(tmp_path, monkeypatch):
    engine, paper, revision = archived_fixture(tmp_path)
    app = FastAPI()
    register_reading_document_api(app, lambda: engine, tmp_path)
    from researchgraph import reading_document_api
    from researchgraph.core import KnowledgeError

    scan = reading_document_api._scan_pdf

    def changed_source(*args, **kwargs):
        result = scan(*args, **kwargs)
        with Session(engine) as writer, writer.begin():
            writer.get(AttachmentRevision, revision).sha256 = "0" * 64
        return result

    monkeypatch.setattr(reading_document_api, "_scan_pdf", changed_source)
    with pytest.raises(KnowledgeError) as failure:
        TestClient(app).post(f"/api/v1/papers/{paper}/reading-document/refresh", json={})
    assert failure.value.code == "READING_SOURCE_CHANGED"
    with read_session(engine) as session:
        assert session.scalar(select(ReadingDocumentProjection)) is None
