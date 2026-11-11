import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from researchgraph import storage
from researchgraph.lite_models import LiteTokenUsage
from researchgraph.models import AttachmentRevision, Job, Paper, Project, now
from researchgraph.translation_models import PDFTranslation, PDFTranslationSettings
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session


def test_lite0005_upgrade_preserves_sources_usage_and_creates_backup(tmp_path):
    engine = storage.make_engine(tmp_path)
    config = Config()
    config.set_main_option(
        "script_location",
        str(Path(storage.__file__).parent / "migrations"),
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "lite0005")
        # lite0001's shared metadata can see imported future models in this
        # process. Remove only the new empty tables to reproduce a true 0005 DB.
        PDFTranslation.__table__.drop(connection, checkfirst=True)
        PDFTranslationSettings.__table__.drop(connection, checkfirst=True)
    project_id, paper_id, revision_id, usage_id = (str(uuid4()) for _ in range(4))
    with Session(engine) as session, session.begin():
        session.add(Project(id=project_id, name="preserve", description="old", created_at=now()))
        session.flush()
        session.add(
            Paper(id=paper_id, project_id=project_id, title="Keep source", created_at=now())
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
            LiteTokenUsage(
                id=usage_id,
                project_id=project_id,
                paper_id=paper_id,
                document_version_id=revision_id,
                task_kind="paper_overview",
                input_tokens=12,
                output_tokens=8,
                total_tokens=20,
                retry_count=0,
                cache_hit=False,
                usage_source="provider",
                status="succeeded",
                extra={},
                created_at=now(),
            )
        )
    storage.migrate(engine, tmp_path)
    assert list((tmp_path / "backups").glob("before-migration-*.sqlite3"))
    with Session(engine) as session:
        assert session.get(Paper, paper_id).title == "Keep source"
        assert session.get(AttachmentRevision, revision_id).sha256 == "a" * 64
        assert session.get(LiteTokenUsage, usage_id).total_tokens == 20
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "lite0008"
    assert {"pdf_translations", "pdf_translation_settings"} <= set(
        inspect(engine).get_table_names()
    )
    assert storage.diagnostics(engine)["integrity"] == "ok"
    engine.dispose()


@pytest.mark.parametrize("initial", ["lite0006", "lite0007"])
def test_upgrade_keeps_records_and_switches_only_future_runtime(tmp_path, initial):
    engine = storage.make_engine(tmp_path)
    config = Config()
    config.set_main_option("script_location", str(Path(storage.__file__).parent / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, initial)
    project_id, paper_id, revision_id, job_id = (str(uuid4()) for _ in range(4))
    timestamp = now()
    with Session(engine) as session, session.begin():
        session.add(
            Project(id=project_id, name="keep project", description="", created_at=timestamp)
        )
        session.flush()
        session.add(
            Paper(id=paper_id, project_id=project_id, title="keep paper", created_at=timestamp)
        )
        session.flush()
        session.add(
            AttachmentRevision(
                id=revision_id,
                paper_id=paper_id,
                sha256="b" * 64,
                parser_version="test",
                page_count=2,
                warnings=[],
                created_at=timestamp,
            )
        )
        session.add(
            Job(
                id=job_id,
                project_id=project_id,
                kind="pdf_translation",
                payload={},
                status="succeeded",
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        session.flush()
        session.add(
            PDFTranslationSettings(
                id="global",
                enabled=False,
                service_url="http://127.0.0.1:8999",
                launch_mode="managed",
                python_path="C:/synthetic/python.exe",
                server_path="C:/synthetic/server.py",
            )
        )
        session.add(
            PDFTranslation(
                id=job_id,
                project_id=project_id,
                paper_id=paper_id,
                document_version_id=revision_id,
                source_hash="b" * 64,
                profile_id=str(uuid4()),
                model_id="synthetic",
                model_snapshot={"model": "synthetic", "credential_ref": None},
                runtime_snapshot={
                    "launch_mode": "manual",
                    "python_path": None,
                    "server_path": None,
                },
                cache_key="c" * 64,
                service_url="http://127.0.0.1:8999",
                engine_version="test",
                status="COMPLETED",
                page_start=1,
                page_end=2,
                page_count=2,
                progress=100,
                stage="completed",
                job_id=job_id,
                external_state="completed",
                warnings=["keep warning"],
                artifacts=[{"kind": "mono", "sha256": "d" * 64}],
                max_calls=100,
                max_input_tokens=200000,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
    with engine.begin() as connection:
        # Shared metadata sees future columns; remove only additive fields in
        # this isolated fixture to model an actual pre-0007 deployed database.
        if initial == "lite0006":
            for column in ("launch_mode", "python_path", "server_path"):
                connection.exec_driver_sql(
                    f"ALTER TABLE pdf_translation_settings DROP COLUMN {column}"
                )
            connection.exec_driver_sql("ALTER TABLE pdf_translations DROP COLUMN runtime_snapshot")
        connection.exec_driver_sql("ALTER TABLE pdf_translations DROP COLUMN output_mode")
        old_settings = dict(
            connection.execute(text("SELECT * FROM pdf_translation_settings")).mappings().one()
        )
        old_translation = dict(
            connection.execute(text("SELECT * FROM pdf_translations")).mappings().one()
        )
    storage.migrate(engine, tmp_path)
    with engine.connect() as connection:
        settings = dict(
            connection.execute(text("SELECT * FROM pdf_translation_settings")).mappings().one()
        )
        translation = dict(
            connection.execute(text("SELECT * FROM pdf_translations")).mappings().one()
        )
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "lite0008"
        if initial == "lite0006":
            assert settings.pop("launch_mode") == "bundled"
            assert settings.pop("python_path") is None
            assert settings.pop("server_path") is None
            assert translation.pop("runtime_snapshot") == "{}"
        else:
            assert settings["python_path"] == "C:/synthetic/python.exe"
            assert settings["server_path"] == "C:/synthetic/server.py"
        assert translation.pop("output_mode") == "both"
        expected_settings = {**old_settings, "enabled": 1}
        if initial == "lite0007":
            expected_settings["launch_mode"] = "bundled"
        assert settings == expected_settings and translation == old_translation
        assert (
            connection.scalar(text("SELECT title FROM papers WHERE id=:id"), {"id": paper_id})
            == "keep paper"
        )
    backups = list((tmp_path / "backups").glob("before-migration-*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(f"file:{backups[0].as_posix()}?mode=ro", uri=True) as backup:
        backup.row_factory = sqlite3.Row
        assert backup.execute("SELECT version_num FROM alembic_version").fetchone()[0] == initial
        assert (
            dict(backup.execute("SELECT * FROM pdf_translation_settings").fetchone())
            == old_settings
        )
        assert dict(backup.execute("SELECT * FROM pdf_translations").fetchone()) == old_translation
        if initial == "lite0006":
            assert "runtime_snapshot" not in {
                row["name"] for row in backup.execute("PRAGMA table_info(pdf_translations)")
            }
        assert "output_mode" not in {
            row["name"] for row in backup.execute("PRAGMA table_info(pdf_translations)")
        }
    storage.migrate(engine, tmp_path)
    assert len(list((tmp_path / "backups").glob("before-migration-*.sqlite3"))) == 1
    assert storage.diagnostics(engine)["integrity"] == "ok"
    engine.dispose()
