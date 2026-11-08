"""Additive migration, display-only writes and continued Zotero workflows."""

import asyncio
import hashlib
import sqlite3
from pathlib import Path

import pytest
import test_knowledge
import test_reasoning
import test_zotero_batch
from alembic import command
from alembic.config import Config
from researchgraph.graph_projection import display_data
from researchgraph.knowledge_models import KnowledgeNode, ModelRun
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest
from researchgraph.models import Job, PaperSource
from researchgraph.storage import make_engine, migrate
from researchgraph.translation import run_translation
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_engine import client, post
from test_graph_v3 import save_unified
from test_ingest import wait_job

seeded = test_knowledge.seeded
paired = test_reasoning.paired
zotero = test_zotero_batch.zotero


def test_0009_migration_preserves_every_old_row_and_backup(tmp_path):
    engine = make_engine(tmp_path)
    config = Config()
    config.set_main_option(
        "script_location", str(Path("services/engine/researchgraph/migrations").resolve())
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0008")
    dbfile = tmp_path / "researchgraph.sqlite3"
    with sqlite3.connect(dbfile) as db:
        db.execute(
            "insert into projects values ('old-project','Kept','Original description','2026-01-01')"
        )
        db.commit()
        tables = [
            r[0]
            for r in db.execute(
                "select name from sqlite_master where type='table' and name != 'alembic_version'"
            )
        ]
        before = {t: db.execute(f'SELECT * FROM "{t}" ORDER BY 1').fetchall() for t in tables}
    migrate(engine, tmp_path)
    with sqlite3.connect(dbfile) as db:
        assert db.execute("select version_num from alembic_version").fetchone()[0] == "0020"
        assert all(
            db.execute(f'SELECT * FROM "{t}" ORDER BY 1').fetchall() == rows
            for t, rows in before.items()
        )
        assert db.execute("pragma integrity_check").fetchone()[0] == "ok"
        assert not db.execute("pragma foreign_key_check").fetchall()
    backup = next((tmp_path / "backups").glob("*.sqlite3"))
    with sqlite3.connect(backup) as db:
        assert db.execute("select version_num from alembic_version").fetchone()[0] == "0008"
        assert db.execute("select name from projects").fetchone()[0] == "Kept"
    engine.dispose()


def test_translation_does_not_change_accepted_science_or_original_run(seeded):
    api, engine, eid = seeded
    result = save_unified(engine, eid)
    nid = result["node_ids"][0]
    with Session(engine) as session, session.begin():
        node = session.get(KnowledgeNode, nid)
        node.review_status = "accepted"
        before = (node.text, node.payload, node.revision, node.model_run_id)
        original = session.get(ModelRun, "run").raw_output
    queued = post(api, "/projects/project/graph/translate", {"node_ids": [nid]})
    assert queued.status_code == 202, queued.text
    with Session(engine) as session, session.begin():
        session.get(Job, queued.json()["id"]).status = "running"
    asyncio.run(run_translation(engine, queued.json()["id"]))
    with Session(engine) as session:
        node = session.get(KnowledgeNode, nid)
        assert before == (node.text, node.payload, node.revision, node.model_run_id)
        assert node.review_status == "accepted"
        assert session.get(ModelRun, "run").raw_output == original
        assert display_data(session, node)["translation_status"] == "machine_unreviewed"
    assert (
        post(
            api, "/projects/other/graph/translate", {"node_ids": [nid]}, "foreign-translation"
        ).status_code
        == 404
    )


def test_translation_rejects_stale_or_forged_targets_atomically(seeded):
    _, engine, eid = seeded
    nid = save_unified(engine, eid)["node_ids"][0]
    with Session(engine) as session:
        node = session.get(KnowledgeNode, nid)
        snapshot = {
            "n": {
                "id": nid,
                "revision": node.revision,
                "hash": digest(node.payload),
                "display_hash": digest(display_data(session, node)),
            }
        }
    with Session(engine) as session, session.begin():
        session.get(KnowledgeNode, nid).revision += 1
    with (
        Session(engine) as session,
        session.begin(),
        pytest.raises(KnowledgeError, match="原文知识已更新"),
    ):
        KnowledgeStore(session).apply_translation(
            {"items": [{"node_ref": "n", "label_zh": "译名", "summary_zh": "译文"}]},
            snapshot,
            "run",
            "stale",
        )


def test_zotero_parse_directly_queues_unified_extraction_without_copy(tmp_path, zotero):
    before = hashlib.sha256(zotero.read_bytes()).hexdigest()
    with client(tmp_path / "data", worker=True) as api:
        project = post(api, "/projects", {"name": "One-step graph"}).json()["id"]
        body = {**test_zotero_batch.body(), "extract_after_parse": True, "provider": "mock"}
        job = post(api, f"/projects/{project}/zotero-imports", body).json()[0]["job"]
        imported = wait_job(api, job)
        assert imported["status"] == "succeeded", imported
        child = wait_job(api, {"id": imported["result"]["extraction_job_id"]})
        assert child["status"] == "succeeded", child
        assert child["result"]["pipeline"] == "paper-reading-v1"
        with Session(api.app.state.engine) as session:
            assert all(s.managed_path is None for s in session.scalars(select(PaperSource)))
            child_count = len(
                list(session.scalars(select(Job).where(Job.kind == "knowledge_extract")))
            )
            assert child_count == 1
        assert hashlib.sha256(zotero.read_bytes()).hexdigest() == before


def test_projection_ai_edges_dashed_until_review_and_hidden_when_rejected(paired):
    api, project, nodes, _ = paired
    inferred = test_reasoning.infer(api, nodes)
    relation_id = inferred["result"]["proposal_id"]
    route = f"/projects/{project}/graph/projection"
    edge = next(e for e in post(api, route, {}).json()["edges"] if e["id"] == relation_id)
    assert edge["is_dashed"] and edge["epistemic_status"] == "model_inferred"
    assert relation_id not in {
        e["id"] for e in post(api, route, {"include_ai_candidates": False}).json()["edges"]
    }
    for revision, action in [(1, "accept"), (2, "reject")]:
        reviewed = post(
            api,
            "/knowledge/semantic-reviews",
            {
                "kind": "relation",
                "proposal_id": relation_id,
                "expected_revision": revision,
                "action": action,
                "reason": "Synthetic workflow",
            },
            key=f"review-projection-{revision}",
        )
        assert reviewed.status_code == 200
        edges = {e["id"]: e for e in post(api, route, {}).json()["edges"]}
        if action == "accept":
            assert not edges[relation_id]["is_dashed"]
        else:
            assert relation_id not in edges
