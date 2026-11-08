"""0011 upgrade preserves every old column/row and exact pre-upgrade recovery backup."""

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from researchgraph.storage import SCHEMA_HEAD, make_engine, migrate


def rows(db, tables):
    return {
        table: (
            db.execute(f'PRAGMA table_info("{table}")').fetchall(),
            db.execute(f'SELECT * FROM "{table}"').fetchall(),
        )
        for table in tables
    }


def test_0011_additive_upgrade_preserves_old_sources_model_raw_and_tasks(tmp_path):
    engine = make_engine(tmp_path)
    config = Config()
    config.set_main_option(
        "script_location", str(Path("services/engine/researchgraph/migrations").resolve())
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0011")
        connection.exec_driver_sql("INSERT INTO projects VALUES ('p','Synthetic','','now')")
        connection.exec_driver_sql("INSERT INTO papers VALUES ('paper','p','Synthetic','now')")
        connection.exec_driver_sql(
            """INSERT INTO attachment_revisions VALUES
            ('v','paper',:sha,'synthetic',1,'[]','now')""",
            {"sha": "a" * 64},
        )
        connection.exec_driver_sql("""INSERT INTO jobs
            (id,kind,project_id,payload,status,stage,attempt,error,result,created_at,updated_at)
            VALUES ('j','knowledge_extract','p','{"signature":"original"}','failed',
                    'extracting',1,'old error','{}','now','now')""")
        connection.exec_driver_sql(
            """INSERT INTO model_runs VALUES
            ('m','j','v','compatible','synthetic','P02_reading_extract_compact_v4',:hash,
             'reading-1.0',:hash,'{"unchanged":true}','validation_failed',
             '{"old_raw":"preserved"}','old error','now','now')""",
            {"hash": "b" * 64},
        )
    database = tmp_path / "researchgraph.sqlite3"
    with sqlite3.connect(database) as db:
        tables = [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name!='alembic_version'"
            )
        ]
        before = rows(db, tables)
    migrate(engine, tmp_path)
    with sqlite3.connect(database) as db:
        assert rows(db, tables) == before
        assert (
            db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == SCHEMA_HEAD
            == "0020"
        )
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT count(*) FROM query_runs").fetchone() == (0,)
        assert db.execute("SELECT count(*) FROM query_documents").fetchone() == (0,)
        db.execute("INSERT INTO query_fts VALUES ('entry','p','中文 Query synthetic','method')")
        assert db.execute(
            "SELECT entry_id FROM query_fts WHERE query_fts MATCH 'synthetic'"
        ).fetchall() == [("entry",)]
    backups = list((tmp_path / "backups").glob("*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0011",)
        assert rows(db, tables) == before
    migrate(engine, tmp_path)
    assert list((tmp_path / "backups").glob("*.sqlite3")) == backups
    engine.dispose()
