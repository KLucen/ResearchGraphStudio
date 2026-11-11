import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

SCHEMA_HEAD = "lite0008"
DATABASE_NAME = "researchgraph-lite.sqlite3"


def make_engine(data_dir: Path) -> Engine:
    data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{(data_dir / DATABASE_NAME).as_posix()}",
        hide_parameters=True,
        poolclass=NullPool,
    )

    @event.listens_for(engine, "connect")
    def connect(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.isolation_level = None
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.execute("PRAGMA busy_timeout=5000")
        # Readers need a committed snapshot while indexing/Store holds a writer.
        # FULL synchronous durability remains at SQLite's default; no schema changes.
        mode = dbapi_connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if mode != "wal":
            raise RuntimeError("本地数据库无法启用并发读取模式")

    @event.listens_for(engine, "begin")
    def begin(connection: Any) -> None:
        readonly = connection.get_execution_options().get("sqlite_readonly", False)
        connection.exec_driver_sql("PRAGMA query_only=ON" if readonly else "PRAGMA query_only=OFF")
        connection.exec_driver_sql("BEGIN" if readonly else "BEGIN IMMEDIATE")

    @event.listens_for(engine, "checkin")
    def reset_readonly(dbapi_connection: Any, _record: Any) -> None:
        if dbapi_connection is not None:
            dbapi_connection.execute("PRAGMA query_only=OFF")

    return engine


def read_session(engine: Engine) -> Session:
    """A guarded snapshot for audited read paths; writers keep IMMEDIATE isolation."""
    return Session(engine.execution_options(sqlite_readonly=True), autoflush=False)


def database_busy(exc: OperationalError) -> bool:
    """Recognize SQLite lock codes without inspecting possibly private driver text."""
    code = getattr(exc.orig, "sqlite_errorcode", None)
    return isinstance(code, int) and code & 0xFF in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}


def migrate(engine: Engine, data_dir: Path, script_location: Path | None = None) -> None:
    database = data_dir / DATABASE_NAME
    # This is a separate database family. Never stamp/upgrade a full-system
    # database (even if it has been renamed to the Lite filename).
    if database.exists() and database.stat().st_size:
        with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as existing:
            tables = {
                row[0]
                for row in existing.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            current = (
                existing.execute("SELECT version_num FROM alembic_version").fetchone()
                if "alembic_version" in tables
                else None
            )
            if current and current[0] == SCHEMA_HEAD and script_location is None:
                return
            if tables and (not current or not str(current[0]).startswith("lite")):
                raise RuntimeError(
                    "该数据库不是 Lite 数据库；请使用新的 Lite 数据目录，旧数据不会迁移"
                )
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
