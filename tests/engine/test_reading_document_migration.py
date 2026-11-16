"""The reading layer is additive; original text and old notes stay byte-for-byte."""

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from researchgraph import storage
from researchgraph.close_reading_models import SectionCloseReadingResult
from researchgraph.models import AttachmentRevision, Chunk, Paper, Project, Section, now
from researchgraph.paper_reading_models import PaperReadingResult
from researchgraph.reading_document_models import ReadingDocumentProjection
from sqlalchemy import text
from sqlalchemy.orm import Session


def _snapshot(path: Path) -> dict[str, list[tuple]]:
    with sqlite3.connect(path) as connection:
        names = [
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if row[0] != "alembic_version"
        ]
        return {
            name: connection.execute('SELECT * FROM "' + name.replace('"', '""') + '"').fetchall()
            for name in names
        }


def test_real_lite0009_upgrade_preserves_every_existing_row_and_backup(tmp_path):
    engine = storage.make_engine(tmp_path)
    config = Config()
    config.set_main_option("script_location", str(Path(storage.__file__).parent / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "lite0009")
        # 0001's shared Base may know future imports in this test process.
        # Drop the empty new tables to model an actual pre-0010 deployment.
        for model in (PaperReadingResult, ReadingDocumentProjection):
            model.__table__.drop(connection, checkfirst=True)
    with Session(engine) as session, session.begin():
        session.add(Project(id="project", name="keep", description="", created_at=now()))
        session.flush()
        session.add(Paper(id="paper", project_id="project", title="Anonymous", created_at=now()))
        session.flush()
        session.add(
            AttachmentRevision(
                id="revision",
                paper_id="paper",
                sha256="a" * 64,
                parser_version="old-parser",
                page_count=2,
                warnings=[],
                created_at=now(),
            )
        )
        session.flush()
        session.add(
            Chunk(
                id="raw-block",
                revision_id="revision",
                page_index=0,
                page_label="1",
                block_index=0,
                text="Unmodified original\n58.0",
                bbox=[1, 2, 3, 4],
            )
        )
        session.add(
            Section(
                id="old-section",
                document_version_id="revision",
                title="Method",
                ordinal=0,
                role="method",
                parser="old-parser",
            )
        )
        session.flush()
        session.add(
            SectionCloseReadingResult(
                id="old-notes",
                project_id="project",
                paper_id="paper",
                document_version_id="revision",
                section_id="old-section",
                paragraph_ids=["raw-block"],
                range_hash="b" * 64,
                source_hash="a" * 64,
                input_hash="c" * 64,
                cache_key="d" * 64,
                schema_version="section_reading_analysis.v1",
                prompt_version="A02_bilingual_argument_annotation_v1",
                provider_id="synthetic",
                model_id="old-fixture",
                status="INCOMPLETE",
                raw_output='{"original":"保留未完成输出"}',
                analysis_json={"paragraphs": []},
                usage_json={"calls": 1, "input_tokens": 17},
                request_metadata={"original_snapshot": "immutable"},
            )
        )
    original = _snapshot(tmp_path / storage.DATABASE_NAME)
    assert SectionCloseReadingResult.__tablename__ in original
    assert len(original[SectionCloseReadingResult.__tablename__]) == 1
    storage.migrate(engine, tmp_path)
    after = _snapshot(tmp_path / storage.DATABASE_NAME)
    for table, rows in original.items():
        assert after[table] == rows, table
    assert set(after) - set(original) == {"lite_paper_readings", "lite_reading_documents"}
    assert after["chunks"][0][5] == "Unmodified original\n58.0"
    backups = list((tmp_path / "backups").glob("before-migration-*.sqlite3"))
    assert len(backups) == 1 and _snapshot(backups[0]) == original
    with sqlite3.connect(backups[0]) as connection:
        assert (
            connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == "lite0009"
        )
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "lite0010"
    assert storage.diagnostics(engine)["integrity"] == "ok"
    engine.dispose()
