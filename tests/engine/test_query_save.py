"""Explicit Query saves on isolated synthetic data; no model, vault or original-PDF writes."""

import asyncio
import copy
import importlib
import json
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

import pytest
import test_knowledge
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from researchgraph.knowledge_models import AuthorizedRoot, KnowledgeNode
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest
from researchgraph.models import Chunk, Event, Job, Project, now
from researchgraph.query_context import build_context, validate_context
from researchgraph.query_contracts import QueryAnswer, QueryDependency, QueryRequest
from researchgraph.query_documents import read_passages
from researchgraph.query_models import (
    QueryAnswerVersion,
    QueryDocument,
    QueryDocumentVersion,
    QueryModelRun,
    QueryPassage,
    QueryRun,
)
from researchgraph.query_retrieval import retrieve
from researchgraph.query_save import derived_graph, get_saved, list_saved
from researchgraph.query_saved_models import QuerySavedKnowledge
from researchgraph.storage import SCHEMA_HEAD, make_engine, migrate
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from test_query_graph import production
from test_query_retrieval import document, notes

seeded = test_knowledge.seeded


@pytest.fixture(autouse=True)
def answer_validation_boundary(monkeypatch, request):
    """Q07 component tests retain context validation; Q05 tests cover raw-model lineage."""
    if getattr(request, "param", True) is False:
        return
    try:
        module = importlib.import_module("researchgraph.query_answers")
    except ModuleNotFoundError:
        module = ModuleType("researchgraph.query_answers")
        monkeypatch.setitem(sys.modules, "researchgraph.query_answers", module)

    def validated(session, project_id, query_id, answer_version_id=None):
        run = session.get(QueryRun, query_id)
        assert run.project_id == project_id
        validate_context(session, run.snapshot["context"], run.snapshot["retrieval"])
        return session.get(QueryAnswerVersion, answer_version_id)

    monkeypatch.setattr(module, "validate_answer", validated, raising=False)


def prepared(engine, *, personal=False, kind="evidence", answer_id="answer", query_id="query"):
    with Session(engine) as session, session.begin():
        request = QueryRequest(
            project_id="project",
            question="accuracy",
            include_personal=personal,
            purpose="model",
        ).model_dump()
        found = retrieve(
            session, "project", "accuracy", [], include_personal=personal, purpose="model"
        )
        context = build_context(session, request, found)
        reference = next(r for r in context["references"] if r["type"] == kind)
        run = QueryRun(
            id=query_id,
            project_id="project",
            request=request,
            snapshot={"context": context, "retrieval": found, "model": None},
            input_hash=context["input_hash"],
            status="answered",
            error=None,
            created_at=now(),
            updated_at=now(),
        )
        session.add(run)
        session.flush()
        data = QueryAnswer(
            answer_version_id=answer_id,
            query_run_id=query_id,
            revision=1,
            input_hash=context["input_hash"],
            status="validated",
            knowledge_status="mixed_sources" if kind == "note" else "source_grounded",
            passages=[
                {
                    "local_ref": "A00001",
                    "text": "Accuracy is supported under the stated conditions.",
                    "attribution": "user_view" if kind == "note" else "model_synthesis",
                    "source_refs": [reference["ref"]],
                    "caveats": ["Synthetic test only."],
                },
                {
                    "local_ref": "A00002",
                    "text": "Accuracy requires the complete evidence context.",
                    "attribution": "user_view" if kind == "note" else "model_synthesis",
                    "source_refs": [reference["ref"]],
                    "caveats": [],
                },
            ],
        ).model_dump()
        answer = QueryAnswerVersion(
            id=answer_id,
            project_id="project",
            query_run_id=query_id,
            model_run_id=None,
            revision=1,
            state="validated",
            data=data,
            input_hash=context["input_hash"],
            created_at=now(),
        )
        session.add(answer)
    return {
        "source_query_id": query_id,
        "answer_version_id": answer_id,
        "selected_passage_refs": ["A00001"],
        "expected_input_hash": context["input_hash"],
        "kind": "synthesis",
    }


def save(engine, body, key="save-first"):
    with Session(engine) as session, session.begin():
        return KnowledgeStore(session).save_query(body, key, project_id="project")


def rows(session, *, graph=False):
    tables = [
        "knowledge_nodes",
        "node_evidence_links",
        "reading_selections",
        "reading_heads",
        "graph_layouts",
        "model_runs",
        "chunks",
        "evidence_spans",
        "query_answer_versions",
        "query_model_runs",
    ]
    if graph:
        tables.append("graph_revisions")
    return {t: list(session.execute(text(f'SELECT * FROM "{t}"'))) for t in tables}


def test_explicit_save_restarts_and_never_rewrites_paper_answer_or_model_history(seeded):
    _, engine, eid = seeded
    production(engine, eid)
    body = prepared(engine, kind="node")
    with Session(engine) as session:
        before = rows(session)
        revision = KnowledgeStore(session).graph_revision("project")
    first = save(engine, body)
    assert first["kind"] == "synthesis"
    assert first["content_state"] == "valid" and first["file_state"] == "not_exported"
    assert first["paper_ids"] == ["paper"]
    assert first["passages"][0]["paper_ids"] == ["paper"]
    assert first["graph_revision"] == revision + 1
    assert len(first["passages"]) == 1 and first["passages"][0]["caveats"]
    with Session(engine) as session:
        assert rows(session) == before
        saved = session.get(QuerySavedKnowledge, first["saved_id"])
        assert saved.manifest["transformation"] == "validated_passage_copy"
        assert saved.manifest["model_calls"] == 0
        assert get_saved(session, "project", first["saved_id"]) == first
        assert list_saved(session, "project") == [first]
        event = session.scalar(select(Event).where(Event.event_type == "QUERY_KNOWLEDGE_SAVED"))
        assert event.before_revision == revision and event.after_revision == revision + 1
    with Session(engine) as session, session.begin():
        found = retrieve(session, "project", "Accuracy", [], source_kinds=["synthesis"])
        assert found["hits"] and found["hits"][0]["source_kind"] == "synthesis"
        graph = derived_graph(session, "project")
        assert first["saved_id"] in {n["id"] for n in graph["nodes"]}
        assert {n["kind"] for n in graph["nodes"]} >= {"synthesis", "paper", "evidence"}
        assert any(n["kind"] in {"claim", "condition", "method"} for n in graph["nodes"])
        assert all(e["relation"] == "DERIVED_FROM" for e in graph["edges"])
        assert all(e["epistemic_status"] == "derived_reference" for e in graph["edges"])
        assert rows(session) == before


def test_same_key_new_key_reordered_selection_and_restart_do_not_double_save(seeded):
    _, engine, eid = seeded
    production(engine, eid)
    body = prepared(engine)
    body["selected_passage_refs"] = ["A00002", "A00001"]
    first = save(engine, body)
    assert save(engine, body) == first
    body["selected_passage_refs"].reverse()
    assert save(engine, body, "new-key") == first
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(QuerySavedKnowledge)) == 1
        assert session.scalar(select(func.count()).select_from(QueryDocumentVersion)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.event_type == "QUERY_KNOWLEDGE_SAVED")
            )
            == 1
        )
    body["kind"] = "insight"
    with pytest.raises(KnowledgeError, match="相同操作键"):
        save(engine, body)
    insight = save(engine, body, "insight-key")
    assert insight["kind"] == "insight" and insight["saved_id"] != first["saved_id"]


def test_explicit_target_appends_keeps_old_snapshot_and_requires_baseline(seeded):
    _, engine, eid = seeded
    production(engine, eid)
    target = document(engine)
    body = prepared(engine, kind="passage")
    body.update(target_document_id=target["document_id"], base_version_id=target["version_id"])
    with Session(engine) as session:
        old = copy.deepcopy(session.get(QueryPassage, target["passage_ids"][0]).__dict__)
    first = save(engine, body)
    assert first["document_id"] == target["document_id"] and first["revision"] == 2
    assert first["content_state"] == "valid"
    assert first["passages"][0]["lineage_dependencies"][0]["type"] == "passage"
    assert all(d["type"] != "passage" for d in first["passages"][0]["dependencies"])
    with Session(engine) as session:
        original = session.get(QueryPassage, target["passage_ids"][0])
        assert {k: v for k, v in original.__dict__.items() if k != "_sa_instance_state"} == {
            k: v for k, v in old.items() if k != "_sa_instance_state"
        }
        current = list(
            session.scalars(
                select(QueryPassage).where(QueryPassage.version_id == first["version_id"])
            )
        )
        assert len(current) == 2 and current[0].text == "Saved accuracy explanation"
    # The source Wiki head changed through this very save. Recovery returns the
    # immutable saved object after dependency/lineage checks, without re-appending.
    assert save(engine, body) == first
    assert save(engine, body, "another-key") == first
    body["selected_passage_refs"] = ["A00002"]
    with pytest.raises(KnowledgeError):
        save(engine, body, "stale-target")


@pytest.mark.parametrize("problem", ["project", "answer", "draft", "incomplete", "hash", "passage"])
def test_bad_cross_project_draft_incomplete_or_changed_answer_does_not_write(seeded, problem):
    _, engine, eid = seeded
    production(engine, eid)
    body = prepared(engine)
    with Session(engine) as session, session.begin():
        answer = session.get(QueryAnswerVersion, "answer")
        if problem == "project":
            session.add(Project(id="other", name="Other", description="", created_at=now()))
            session.flush()
            answer.project_id = "other"
        elif problem == "answer":
            body["answer_version_id"] = "forged"
        elif problem == "draft":
            answer.state = "draft"
        elif problem == "incomplete":
            answer.data = {
                **answer.data,
                "status": "incomplete",
                "knowledge_status": "insufficient",
                "limitations": ["Incomplete"],
            }
        elif problem == "hash":
            body["expected_input_hash"] = "f" * 64
        else:
            body["selected_passage_refs"] = ["not-in-answer"]
    with Session(engine) as session:
        before = rows(session, graph=True)
    with pytest.raises(KnowledgeError):
        save(engine, body)
    with Session(engine) as session:
        assert rows(session, graph=True) == before
        assert not list_saved(session, "project")
        assert session.scalar(select(func.count()).select_from(QueryDocument)) == 0


def test_revocation_blocks_new_save_cached_save_get_graph_and_index(seeded, tmp_path):
    _, engine, eid = seeded
    production(engine, eid)
    vault = notes(engine, tmp_path)
    with Session(engine) as session, session.begin():
        KnowledgeStore(session).query().set_note_grant("project", "root", True, True)
    body = prepared(engine, personal=True, kind="note")
    first = save(engine, body)
    assert (vault / "reading.md").read_text(encoding="utf-8").startswith("Private synthetic")
    with Session(engine) as session:
        assert list_saved(session, "project") == []
        assert list_saved(session, "project", True)[0]["saved_id"] == first["saved_id"]
    with Session(engine) as session, session.begin():
        session.get(AuthorizedRoot, "root").active = False
    for key in ("save-first", "new-key"):
        with pytest.raises(KnowledgeError):
            save(engine, body, key)
    body["kind"] = "insight"
    with pytest.raises(KnowledgeError):
        save(engine, body, "insight")
    with Session(engine) as session, session.begin():
        assert list_saved(session, "project", True) == []
        with pytest.raises(KnowledgeError):
            get_saved(session, "project", first["saved_id"], True)
        assert derived_graph(session, "project", True) == {"nodes": [], "edges": []}
        assert (
            retrieve(
                session,
                "project",
                "Accuracy",
                [],
                include_personal=True,
                source_kinds=["synthesis"],
            )["hits"]
            == []
        )


def test_selected_source_hash_changes_block_save_and_hide_stale_text(seeded):
    _, engine, eid = seeded
    production(engine, eid)
    body = prepared(engine)
    first = save(engine, body)
    with Session(engine) as session, session.begin():
        session.get(Chunk, "paragraph").text += " changed"
    with pytest.raises(KnowledgeError):
        save(engine, body, "new-key")
    with Session(engine) as session:
        saved = get_saved(session, "project", first["saved_id"])
        assert saved["content_state"] == "invalid"
        assert saved["passages"][0]["text"] == ""
        assert derived_graph(session, "project") == {"nodes": [], "edges": []}


def test_answer_history_mutation_and_cross_project_saved_lookup_rejected(seeded):
    _, engine, eid = seeded
    production(engine, eid)
    body = prepared(engine)
    first = save(engine, body)
    with Session(engine) as session:
        with pytest.raises(KnowledgeError):
            get_saved(session, "another", first["saved_id"])
    with Session(engine) as session, session.begin():
        answer = session.get(QueryAnswerVersion, "answer")
        data = copy.deepcopy(answer.data)
        data["passages"][0]["text"] = "Silently altered answer"
        answer.data = data
    with pytest.raises(KnowledgeError, match="谱系"):
        save(engine, body)


def test_payload_guard_is_node_only_and_old_dependency_hash_shape_is_unchanged():
    old = {
        "type": "node",
        "id": "node",
        "sha256": None,
        "revision": 1,
        "start": None,
        "end": None,
        "quote": None,
    }
    assert QueryDependency.model_validate(old).model_dump() == old
    guarded = QueryDependency.model_validate({**old, "payload_sha256": "a" * 64})
    assert guarded.model_dump()["payload_sha256"] == "a" * 64
    with pytest.raises(ValidationError):
        QueryDependency.model_validate(
            {"type": "evidence", "id": "e", "sha256": "a" * 64, "payload_sha256": "b" * 64}
        )


@pytest.mark.parametrize("wrapper", [False, True])
def test_saved_node_payload_drift_without_revision_invalidates_every_read_and_replay(
    seeded, wrapper
):
    _, engine, eid = seeded
    ids = production(engine, eid)
    if wrapper:
        # Old saved document dependencies remain readable without a new hash.
        # A new explicit save must still bind their current semantic payload.
        with Session(engine) as session, session.begin():
            node = session.get(KnowledgeNode, ids["c"])
            legacy = (
                KnowledgeStore(session)
                .query()
                .save_document(
                    {
                        "project_id": "project",
                        "kind": "wiki",
                        "title": "Legacy accuracy wrapper",
                        "passages": [
                            {
                                "local_ref": "old",
                                "text": "Legacy accuracy reading.",
                                "attribution": "model_synthesis",
                                "dependencies": [
                                    {"type": "node", "id": node.id, "revision": node.revision}
                                ],
                            }
                        ],
                    },
                    "legacy-node-wrapper",
                )
            )
            assert read_passages(session, "project")[0]["content_state"] == "valid"
            assert (
                "payload_sha256"
                not in session.get(QueryPassage, legacy["passage_ids"][0]).dependencies[0]
            )
    body = prepared(engine, kind="passage" if wrapper else "node")
    first = save(engine, body)
    dep = next(d for d in first["passages"][0]["dependencies"] if d["type"] == "node")
    with Session(engine) as session, session.begin():
        node = session.get(KnowledgeNode, dep["id"])
        assert dep["payload_sha256"] == digest(node.payload)
        revision, source_text = node.revision, node.text
        payload = copy.deepcopy(node.payload)
        payload["uncertainties"] = [*payload.get("uncertainties", []), "Unrecorded semantic change"]
        node.payload = payload
    with Session(engine) as session, session.begin():
        node = session.get(KnowledgeNode, dep["id"])
        assert node.revision == revision and node.text == source_text
        saved = get_saved(session, "project", first["saved_id"])
        assert saved["content_state"] == "invalid" and saved["passages"][0]["text"] == ""
        assert "QUERY_PAYLOAD_CHANGED" in saved["passages"][0]["issues"]
        assert list_saved(session, "project")[0]["content_state"] == "invalid"
        reading = next(
            p for p in read_passages(session, "project") if p["document_id"] == first["document_id"]
        )
        assert reading["content_state"] == "invalid" and reading["text"] == ""
        assert (
            retrieve(session, "project", "accuracy", [], source_kinds=["synthesis"])["hits"] == []
        )
        assert derived_graph(session, "project") == {"nodes": [], "edges": []}
        answer_before = copy.deepcopy(session.get(QueryAnswerVersion, "answer").data)
    for key in ("save-first", "new-key-after-payload-drift"):
        with pytest.raises(KnowledgeError):
            save(engine, body, key)
    with Session(engine) as session:
        assert session.get(QueryAnswerVersion, "answer").data == answer_before
        assert session.scalar(select(func.count()).select_from(QuerySavedKnowledge)) == 1


@pytest.mark.parametrize("answer_validation_boundary", [False], indirect=True)
def test_integrated_p07_raw_execution_save_same_wiki_replay_and_retrieval(seeded):
    from researchgraph.query_answers import enqueue, execute, get_answer, validate_answer

    _, engine, eid = seeded
    production(engine, eid)
    target = document(engine)
    model = {
        "provider": "compatible",
        "model": "synthetic-no-network",
        "base_url": "http://127.0.0.1:9/v1",
        "parameters": {},
    }
    with Session(engine) as session, session.begin():
        request = QueryRequest(
            project_id="project", question="accuracy", source_kinds=["wiki"], purpose="model"
        ).model_dump()
        found = retrieve(session, "project", "accuracy", [], source_kinds=["wiki"], purpose="model")
        context = build_context(session, request, found, model_snapshot=model)
        session.add(
            QueryRun(
                id="integrated-query",
                project_id="project",
                request=request,
                snapshot={
                    "request": request,
                    "context": context,
                    "retrieval": found,
                    "model": model,
                },
                input_hash=context["input_hash"],
                status="prepared",
                error=None,
                created_at=now(),
                updated_at=now(),
            )
        )
        session.flush()
        job = enqueue(session, "integrated-query", "project", "enqueue-integrated")
        job.status = "running"
        job_id = job.id

    class OfflineAnswer:
        name = "test-only"
        model = "synthetic-no-network"
        calls = 0
        usage = {"prompt_tokens": 31, "completion_tokens": 17, "total_tokens": 48}
        request_metadata = {"finish_reason": "stop"}

        async def complete(self, prompt, data, schema):
            self.calls += 1
            passage = next(
                r for r in data["evidence_context"]["references"] if r["type"] == "passage"
            )
            return json.dumps(
                {
                    "passages": [
                        {
                            "text": "Accuracy is explained by the saved reading synthesis.",
                            "attribution": "model_synthesis",
                            "source_refs": [passage["ref"]],
                            "limitations": ["Synthetic deterministic fixture."],
                        }
                    ],
                    "limitations": [],
                }
            )

    provider = OfflineAnswer()
    asyncio.run(execute(engine, job_id, testing_provider=provider))
    assert provider.calls == 1
    with Session(engine) as session:
        job = session.get(Job, job_id)
        assert job.status == "succeeded", (job.error, job.result)
        view = get_answer(session, "project", "integrated-query")
        assert view.answer.knowledge_status == "source_grounded"
        answer = validate_answer(session, "project", "integrated-query")
        raw = session.get(QueryModelRun, answer.model_run_id).raw_output
        before = rows(session)
        body = {
            "source_query_id": "integrated-query",
            "answer_version_id": answer.id,
            "selected_passage_refs": ["A00001"],
            "expected_input_hash": context["input_hash"],
            "kind": "synthesis",
            "target_document_id": target["document_id"],
            "base_version_id": target["version_id"],
        }
    first = save(engine, body)
    assert first["content_state"] == "valid" and first["revision"] == 2
    assert first["passages"][0]["roots"][0]["source_kind"] == "paper"
    assert save(engine, body) == first
    assert save(engine, body, "recovered-after-disconnect") == first
    assert provider.calls == 1
    with Session(engine) as session, session.begin():
        assert rows(session) == before
        assert session.get(QueryModelRun, answer.model_run_id).raw_output == raw
        found = retrieve(
            session, "project", "synthesis", [], source_kinds=["wiki"], purpose="local"
        )
        assert any(h["object_id"] == first["passage_ids"][0] for h in found["hits"])
        assert get_saved(session, "project", first["saved_id"])["content_state"] == "valid"
        assert first["saved_id"] in {n["id"] for n in derived_graph(session, "project")["nodes"]}


def _database_rows(db, tables):
    return {
        table: (
            db.execute(f'PRAGMA table_info("{table}")').fetchall(),
            db.execute(f'SELECT * FROM "{table}"').fetchall(),
        )
        for table in tables
    }


def test_0012_to_0013_is_additive_and_backup_keeps_query_and_raw_history(tmp_path):
    engine = make_engine(tmp_path)
    config = Config()
    config.set_main_option(
        "script_location", str(Path("services/engine/researchgraph/migrations").resolve())
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0012")
        connection.exec_driver_sql("INSERT INTO projects VALUES ('p','Synthetic','','now')")
        connection.exec_driver_sql(
            """INSERT INTO query_runs VALUES
            ('q','p','{"question":"old"}','{"immutable":true}',:hash,'answered',NULL,'now','now')""",
            {"hash": "a" * 64},
        )
        connection.exec_driver_sql(
            """INSERT INTO query_model_runs VALUES
            ('m','q','p','synthetic','synthetic','P07',:hash,'old',:hash,'{}','{}','succeeded',
             '{"old_raw":"preserved"}',NULL,'now','now')""",
            {"hash": "b" * 64},
        )
        connection.exec_driver_sql(
            """INSERT INTO query_answer_versions VALUES
            ('a','p','q','m',1,'validated','{"original":true}',:hash,'now')""",
            {"hash": "a" * 64},
        )
        connection.exec_driver_sql("INSERT INTO query_fts VALUES ('e','p','preserved','alias')")
    database = tmp_path / "researchgraph.sqlite3"
    with sqlite3.connect(database) as db:
        tables = [
            r[0]
            for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name!='alembic_version'"
            )
        ]
        before = _database_rows(db, tables)
    migrate(engine, tmp_path)
    with sqlite3.connect(database) as db:
        assert _database_rows(db, tables) == before
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (SCHEMA_HEAD,)
        assert SCHEMA_HEAD == "0014"
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT count(*) FROM query_saved_knowledge").fetchone() == (0,)
    backups = list((tmp_path / "backups").glob("*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0012",)
        assert _database_rows(db, tables) == before
    migrate(engine, tmp_path)
    assert list((tmp_path / "backups").glob("*.sqlite3")) == backups
    engine.dispose()
