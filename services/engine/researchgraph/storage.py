import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event, text

SCHEMA_HEAD = "0004"


def make_engine(data_dir: Path) -> Engine:
    data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{(data_dir / 'researchgraph.sqlite3').as_posix()}")

    @event.listens_for(engine, "connect")
    def connect(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.isolation_level = None
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.execute("PRAGMA busy_timeout=5000")

    @event.listens_for(engine, "begin")
    def begin(connection: Any) -> None:
        connection.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


def migrate(engine: Engine, data_dir: Path, script_location: Path | None = None) -> None:
    database = data_dir / "researchgraph.sqlite3"
    # A consistent SQLite backup precedes any schema mutation, including failed upgrades.
    if database.exists() and database.stat().st_size:
        with engine.connect() as connection:
            tables = connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE name='alembic_version'"
            ).fetchall()
            current = (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                if tables
                else None
            )
        if current == SCHEMA_HEAD and script_location is None:
            return
        backups = data_dir / "backups"
        backups.mkdir(exist_ok=True)
        with (
            sqlite3.connect(database) as source,
            sqlite3.connect(backups / f"before-migration-{uuid4()}.sqlite3") as target,
        ):
            source.backup(target)
    config = Config()
    config.set_main_option(
        "script_location", str(script_location or Path(__file__).parent / "migrations")
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def diagnostics(engine: Engine) -> dict[str, str | bool]:
    with engine.connect() as connection:
        integrity = str(connection.scalar(text("PRAGMA quick_check")))
        foreign_key_errors = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        connection.exec_driver_sql("CREATE VIRTUAL TABLE temp.fts_probe USING fts5(content)")
        connection.exec_driver_sql("INSERT INTO temp.fts_probe VALUES ('research graph')")
        matches = connection.exec_driver_sql(
            "SELECT count(*) FROM temp.fts_probe WHERE fts_probe MATCH 'research'"
        ).scalar()
        connection.exec_driver_sql("DROP TABLE temp.fts_probe")
        if integrity != "ok" or foreign_key_errors or matches != 1:
            raise RuntimeError("数据库完整性或 FTS5 检查失败")
        return {"integrity": integrity, "foreign_keys": True, "fts5": True}
