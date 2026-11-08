"""Populated genuine 0019 upgrade: immutable science, Lint history and exact backup."""

import asyncio
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from researchgraph.knowledge_store import KnowledgeStore
from researchgraph.lint_models import LintOperation
from researchgraph.lint_service import LintStore
from researchgraph.models import Chunk
from researchgraph.providers import MockProvider
from researchgraph.reading_pipeline import finish_reading
from researchgraph.storage import SCHEMA_HEAD, make_engine, migrate
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_engine import client
from test_knowledge import seeded as seeded
from test_lint import scan, start, step
from test_p5_migration import snapshot
from test_query_graph import production
from test_reading_selection import setup_job


def old_lint_database(seeded, tmp_path):
    """Transfer validated donor values only into columns present in real 0019.

    There is no downgrade or dropped telemetry column masquerading as an old
    schema. The target is created by Alembic's actual 0019 chain, and all current
    Lint operation responses have their two new presentation fields removed.
    """
    _, source_engine, eid = seeded
    production(source_engine, eid)
    setup_job(source_engine)
    asyncio.run(finish_reading(source_engine, "job", MockProvider()))
    completed = scan(source_engine, project_id="project", key="migration-completed")
    stale = start(source_engine, project_id="project", key="migration-stale")
    with Session(source_engine) as session, session.begin():
        session.get(Chunk, "paragraph").text = "Changed synthetic input before old migration."
    stale = step(source_engine, stale, 1)
    active = start(source_engine, project_id="project", key="migration-active")
    active = step(source_engine, active, 1)
    queued = start(source_engine, project_id="project", key="migration-queued")
    cancelled = start(source_engine, project_id="project", key="migration-cancelled")
    with Session(source_engine) as session, session.begin():
        cancelled = LintStore(KnowledgeStore(session)).cancel(
            "project", cancelled["id"], "migration-cancel"
        )
        for operation in session.scalars(select(LintOperation)):
            operation.response = {
                key: value
                for key, value in operation.response.items()
                if key not in {"phase", "timings"}
            }
    runs = {run["id"]: run for run in (completed, stale, active, queued, cancelled)}
    assert {run["status"] for run in runs.values()} == {
        "completed",
        "input_stale",
        "running",
        "queued",
        "cancelled",
    }
    data = tmp_path / "upgrade-lint-0019"
    engine = make_engine(data)
    config = Config()
    config.set_main_option(
        "script_location", str(Path("services/engine/researchgraph/migrations").resolve())
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0019")
    engine.dispose()
    source_database = Path(source_engine.url.database)
    database = data / "researchgraph.sqlite3"
    with sqlite3.connect(source_database) as source, sqlite3.connect(database) as target:
        tables = [
            name
            for _, name, kind, *_ in target.execute("PRAGMA table_list")
            if name not in {"alembic_version", "sqlite_schema", "sqlite_temp_schema"}
            and kind in {"table", "virtual"}
        ]
        for table in tables:
            columns = [row[1] for row in target.execute(f'PRAGMA table_info("{table}")')]
            quoted = ",".join(f'"{column}"' for column in columns)
            values = source.execute(f'SELECT {quoted} FROM "{table}"').fetchall()
            target.execute(f'DELETE FROM "{table}"')
            if values:
                placeholders = ",".join("?" for _ in columns)
                target.executemany(
                    f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})', values
                )
        assert target.execute("SELECT version_num FROM alembic_version").fetchone() == ("0019",)
        assert target.execute("PRAGMA foreign_key_check").fetchall() == []
        assert target.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        columns = {row[1] for row in target.execute("PRAGMA table_info(lint_runs)")}
        assert not {"phase", "timings"} & columns
        for name in (
            "ix_paper_sources_revision_id",
            "ix_reading_members_node",
            "ix_reading_units_root_version",
        ):
            assert (
                target.execute("SELECT name FROM sqlite_master WHERE name=?", (name,)).fetchall()
                == []
            )
    before = snapshot(database)
    for table in (
        "lint_runs",
        "lint_issues",
        "lint_operations",
        "dependency_index",
        "dependency_cursors",
        "knowledge_nodes",
        "reading_units",
        "reading_members",
        "reading_selections",
        "graph_revisions",
        "model_runs",
    ):
        assert before[table][1], table
    return data, before, runs, active["id"]


def assert_old_values(database, before):
    with sqlite3.connect(database) as connection:
        for table, (metadata, rows) in before.items():
            current_metadata = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
            assert current_metadata[: len(metadata)] == metadata, table
            names = ",".join(f'"{column[1]}"' for column in metadata)
            current_rows = sorted(
                connection.execute(f'SELECT {names} FROM "{table}"').fetchall(), key=repr
            )
            assert current_rows == rows, table


def test_0019_lint_upgrade_backup_defaults_indexes_restart_and_idempotency(
    seeded, tmp_path, monkeypatch
):
    data, before, runs, active_id = old_lint_database(seeded, tmp_path)
    database = data / "researchgraph.sqlite3"
    engine = make_engine(data)
    migrate(engine, data)
    assert SCHEMA_HEAD == "0020"
    assert_old_values(database, before)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == ("0020",)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        for run_id, status, phase, timings in connection.execute(
            "SELECT id,status,phase,timings FROM lint_runs"
        ):
            assert status == runs[run_id]["status"]
            assert phase == ("scanning" if status in {"queued", "running"} else "finished")
            assert timings == "{}"
        plans = [
            (
                "SELECT id FROM paper_sources WHERE revision_id=?",
                ("version",),
                "ix_paper_sources_revision_id",
            ),
            (
                "SELECT unit_id FROM reading_members WHERE node_id=?",
                ("synthetic",),
                "ix_reading_members_node",
            ),
            (
                "SELECT id FROM reading_units WHERE root_claim_id=? AND document_version_id=?",
                ("synthetic", "version"),
                "ix_reading_units_root_version",
            ),
        ]
        for sql, params, index in plans:
            plan = connection.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
            assert index in "\n".join(row[-1] for row in plan), plan
    backups = list((data / "backups").glob("*.sqlite3"))
    assert len(backups) == 1
    assert snapshot(backups[0]) == before
    with sqlite3.connect(backups[0]) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == ("0019",)
    migrated = snapshot(database)
    migrate(engine, data)
    assert snapshot(database) == migrated
    assert list((data / "backups").glob("*.sqlite3")) == backups
    engine.dispose()
    sends = []

    def forbidden_provider(*args, **kwargs):
        sends.append("provider")
        raise AssertionError("A read-only Lint restart must not load a provider")

    async def forbidden_network(*args, **kwargs):
        sends.append("network")
        raise AssertionError("A read-only Lint restart must not send a model request")

    monkeypatch.setattr("researchgraph.p5_execution.from_snapshot", forbidden_provider)
    monkeypatch.setattr("researchgraph.query_answers.from_snapshot", forbidden_provider)
    monkeypatch.setattr("httpx.AsyncClient.send", forbidden_network)
    for _ in range(2):
        with client(data, worker=True) as api:
            assert api.get("/api/v1/health").json()["schema_version"] == "0020"
            for run_id, original in runs.items():
                response = api.get(f"/api/v1/projects/project/lint/runs/{run_id}")
                assert response.status_code == 200, response.text
                observed = response.json()
                assert observed["status"] == original["status"]
                assert observed["processed"] == original["processed"]
                assert observed["input_hash"] == original["input_hash"]
                assert observed["timings"] == {}
            replay = api.post(
                "/api/v1/projects/project/lint/runs",
                json={},
                headers={"Idempotency-Key": "migration-active"},
            )
            assert replay.status_code == 200 and replay.json()["id"] == active_id, replay.text
            assert snapshot(database) == migrated
            assert_old_values(database, before)
            assert sends == []
    assert list((data / "backups").glob("*.sqlite3")) == backups
