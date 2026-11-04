"""R1 migration checks operate only on synthetic, isolated databases."""

import sqlite3
from pathlib import Path

import test_knowledge
from alembic import command
from alembic.config import Config
from researchgraph.knowledge_models import KnowledgeNode, ModelRun
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore
from researchgraph.storage import make_engine, migrate
from sqlalchemy.orm import Session
from test_knowledge import apply, batch


def test_0011_preserves_all_old_tables_and_backup(tmp_path):
    engine = make_engine(tmp_path)
    config = Config()
    config.set_main_option(
        "script_location", str(Path("services/engine/researchgraph/migrations").resolve())
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0009")
        connection.exec_driver_sql("INSERT INTO projects VALUES ('p','Synthetic','', 'now')")
    path = tmp_path / "researchgraph.sqlite3"
    with sqlite3.connect(path) as db:
        tables = [
            r[0]
            for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version'"
            )
        ]
        before = {t: db.execute(f'SELECT * FROM "{t}"').fetchall() for t in tables}
    migrate(engine, tmp_path)
    with sqlite3.connect(path) as db:
        assert {t: db.execute(f'SELECT * FROM "{t}"').fetchall() for t in tables} == before
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0011",)
    with sqlite3.connect(next((tmp_path / "backups").glob("*.sqlite3"))) as backup:
        assert backup.execute("SELECT version_num FROM alembic_version").fetchone() == ("0009",)
        assert backup.execute("SELECT * FROM projects").fetchall() == before["projects"]
    migrate(engine, tmp_path)
    assert len(list((tmp_path / "backups").glob("*.sqlite3"))) == 1
    engine.dispose()


def test_adaptation_preserves_legacy_content_and_checkpoint_identity(seeded):
    _, engine, eid = seeded
    result = apply(engine, batch(eid), eid)
    with Session(engine) as session, session.begin():
        reading = KnowledgeStore(session).reading()
        node = session.get(KnowledgeNode, result["node_ids"][0])
        before = (node.id, node.payload, node.review_status, node.revision)
        raw = session.get(ModelRun, "run").raw_output
        assert reading.adapt("version") == 0
        assert reading.nodes("version") == []  # Legacy graph is history, not new candidates.
        assert reading.adapt("version") == 0
        assert before == (node.id, node.payload, node.review_status, node.revision)
        assert raw == session.get(ModelRun, "run").raw_output
        reading.save_checkpoint("test", "version", "indexing", "a", {"ok": True})
        session.flush()
        assert reading.checkpoint("test", "a") == {"ok": True}
        try:
            reading.checkpoint("test", "b")
        except KnowledgeError as error:
            assert error.code == "READING_INPUT_CHANGED"
        else:
            raise AssertionError("changed input accepted")


# Explicit alias keeps the shared fixture registered when lint removes unused imports.
seeded = test_knowledge.seeded
