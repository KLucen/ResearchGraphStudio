"""Saved-reading personal metadata and retirement preserve immutable query/source history."""

import copy
import json
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from researchgraph.knowledge_store import KnowledgeStore
from researchgraph.models import Event
from researchgraph.query_documents import read_passages, validate_dependencies
from researchgraph.query_models import QueryAnswerVersion, QueryPassage
from researchgraph.query_saved_models import QuerySavedKnowledge
from researchgraph.storage import make_engine, migrate
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_engine import client, post
from test_query_answers import OfflineProvider, run
from test_query_api import PREFIX, error, generate, prepare, save, seed
from test_query_api import command as save_command


def completed(api, engine, key, *, source_kinds=None, output=None, question=None, **updates):
    prepared = prepare(
        api,
        key=f"prepare-{key}",
        question=question or ("实验条件" if source_kinds else "accuracy"),
        **({"source_kinds": source_kinds} if source_kinds else {}),
        **updates,
    )
    jid = generate(api, prepared["query_id"], key=f"generate-{key}").json()["id"]
    provider = OfflineProvider(engine, output=output)
    run(engine, jid, provider)
    result = api.get(PREFIX + f"/runs/{prepared['query_id']}/answer")
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "succeeded", result.text
    return prepared, result.json(), provider


def metadata(api, sid, action, revision, *, annotation=None, key=None, include_personal=False):
    body = {"expected_revision": revision}
    if annotation is not None:
        body["annotation"] = annotation
    method = api.put if action == "annotation" else api.post
    return method(
        PREFIX + f"/saved/{sid}/{action}?include_personal={str(include_personal).lower()}",
        json=body,
        headers={
            "Idempotency-Key": f"saved-metadata-{key}" if key else f"{sid}-{action}-{revision}"
        },
    )


def immutable_rows(session):
    tables = [
        "papers",
        "attachment_revisions",
        "chunks",
        "evidence_spans",
        "knowledge_nodes",
        "query_runs",
        "query_answer_versions",
        "query_model_runs",
        "query_documents",
        "query_document_versions",
        "query_passages",
        "query_saved_knowledge",
        "graph_revisions",
    ]
    return {table: list(session.execute(text(f'SELECT * FROM "{table}"'))) for table in tables}


def test_annotation_restart_conflicts_and_personal_only_context(tmp_path):
    data = tmp_path / "data"
    with client(data) as api:
        engine = seed(api)
        prepared, answer, provider = completed(api, engine, "original")
        body = save_command(prepared, answer["answer"])
        response = save(api, body)
        assert response.status_code == 200, response.text
        saved = response.json()
        sid = saved["saved_id"]
        assert saved["annotation"] == "" and saved["metadata_revision"] == 0
        with Session(engine) as session:
            before = immutable_rows(session)
        personal = "personal_annotation_unique_zxcv 我对这段知识的个人看法"
        changed = metadata(api, sid, "annotation", 0, annotation=personal)
        assert changed.status_code == 200, changed.text
        assert changed.json()["annotation"] == personal
        assert changed.json()["metadata_revision"] == 1
        assert metadata(api, sid, "annotation", 0, annotation=personal).json() == changed.json()
        error(
            metadata(api, sid, "annotation", 0, annotation="stale", key="stale"),
            "QUERY_SAVED_METADATA_CONFLICT",
        )
        error(
            metadata(api, sid, "annotation", 0, annotation="changed"),
            "IDEMPOTENCY_CONFLICT",
            409,
        )
        for bad in (-1, True, "0"):
            error(
                metadata(api, sid, "annotation", bad, annotation="bad", key=str(bad)),
                "INVALID_INPUT",
            )
        error(metadata(api, sid, "annotation", 1, annotation="x" * 12001), "INVALID_INPUT")
        with Session(engine) as session:
            assert immutable_rows(session) == before
            event = session.scalar(
                select(Event).where(Event.event_type == "query.saved_annotation_changed")
            )
            assert event.actor == "user" and event.payload["attribution"] == "user_view"
            assert event.before_revision == event.after_revision
        searched = api.post(
            PREFIX + "/search",
            json={
                "project_id": "project",
                "question": "personal_annotation_unique_zxcv",
                "source_kinds": ["synthesis"],
                "include_personal": True,
            },
        )
        assert searched.status_code == 200 and searched.json()["hits"] == []
        # The annotation is local user metadata, never a source, even with personal sources enabled.
        fresh = prepare(
            api,
            key="annotation-source-check",
            question="实验条件",
            source_kinds=["synthesis"],
            include_personal=True,
        )
        assert personal not in json.dumps(fresh["snapshot"], ensure_ascii=False)
        assert provider.calls == 1
    with client(data) as reopened:
        view = reopened.get(PREFIX + f"/saved/{sid}").json()
        assert view["annotation"] == personal and view["metadata_revision"] == 1
        cleared = metadata(reopened, sid, "annotation", 1, annotation="", key="clear")
        assert cleared.status_code == 200 and cleared.json()["annotation"] == ""
        assert cleared.json()["metadata_revision"] == 2
        assert reopened.get(PREFIX + f"/runs/{prepared['query_id']}/answer").json() == answer


def test_removal_hides_retrieval_graph_and_replay_but_keeps_original_history(tmp_path):
    with client(tmp_path / "data") as api:
        engine = seed(api)
        prepared, answer, provider = completed(api, engine, "original")
        body = save_command(prepared, answer["answer"])
        saved = save(api, body).json()
        sid = saved["saved_id"]
        independently_saved = save(api, {**body, "kind": "insight"}, "independent-kind-save")
        assert independently_saved.status_code == 200, independently_saved.text
        independent = independently_saved.json()
        assert independent["document_id"] != saved["document_id"]
        # Build the index before removal; the next retrieval must purge orphaned FTS rows too.
        search = {"project_id": "project", "question": "实验条件", "source_kinds": ["synthesis"]}
        assert api.post(PREFIX + "/search", json=search).json()["hits"]
        with Session(engine) as session:
            before = immutable_rows(session)
        error(metadata(api, sid, "remove", 1), "QUERY_SAVED_METADATA_CONFLICT")
        removed = metadata(api, sid, "remove", 0)
        assert removed.status_code == 200, removed.text
        assert removed.json()["removed_at"] and removed.json()["metadata_revision"] == 1
        assert metadata(api, sid, "remove", 0).json() == removed.json()
        assert metadata(api, sid, "remove", 0, key="remove-again").json() == removed.json()
        assert {item["saved_id"] for item in api.get(PREFIX + "/saved").json()["items"]} == {
            independent["saved_id"]
        }
        error(api.get(PREFIX + f"/saved/{sid}"), "QUERY_SAVED_REMOVED")
        error(metadata(api, sid, "annotation", 1, annotation="retired"), "QUERY_SAVED_REMOVED")
        assert sid not in {n["id"] for n in api.get(PREFIX + "/derived-graph").json()["nodes"]}
        assert (
            api.get(PREFIX + f"/saved/{independent['saved_id']}").json()["content_state"] == "valid"
        )
        assert {
            hit["object_id"] for hit in api.post(PREFIX + "/search", json=search).json()["hits"]
        } == set(independent["passage_ids"])
        for key in ("query-save-api", "same-fingerprint-new-key"):
            error(save(api, body, key), "QUERY_SAVED_REMOVED")
        other = api.post(
            f"/api/v1/projects/other/query/saved/{sid}/remove",
            json={"expected_revision": 0},
            headers={"Idempotency-Key": "foreign-remove"},
        )
        error(other, "QUERY_SAVED_NOT_FOUND", 404)
        assert api.get(PREFIX + f"/runs/{prepared['query_id']}/answer").json() == answer
        with Session(engine) as session:
            assert immutable_rows(session) == before
            assert [p["id"] for p in read_passages(session, "project")] == independent[
                "passage_ids"
            ]
            assert (
                session.execute(
                    text("SELECT count(*) FROM query_index_entries WHERE source_kind='synthesis'")
                ).scalar()
                == 1
            )
            assert (
                session.execute(
                    text(
                        "SELECT count(*) FROM query_fts f LEFT JOIN query_index_entries i "
                        "ON i.id=f.entry_id WHERE i.id IS NULL"
                    )
                ).scalar()
                == 0
            )
        assert provider.calls == 1


def passage_output(data):
    passage = next(
        ref for ref in data["evidence_context"]["references"] if ref["type"] == "passage"
    )
    return json.dumps(
        {
            "passages": [
                {
                    "text": "Derived accuracy interpretation of 实验条件 with its reading source.",
                    "attribution": "model_synthesis",
                    "source_refs": [passage["ref"]],
                    "limitations": [],
                }
            ],
            "limitations": [],
        }
    )


@pytest.mark.parametrize("legacy", [False, True])
def test_removed_lineage_invalidates_flattened_derivative_and_cached_dispatch(tmp_path, legacy):
    with client(tmp_path / "data") as api:
        engine = seed(api)
        p1, a1, first_provider = completed(api, engine, "first")
        first = save(api, save_command(p1, a1["answer"]), "save-first").json()
        p2, a2, second_provider = completed(
            api, engine, "second", source_kinds=["synthesis"], output=passage_output
        )
        second_body = save_command(p2, a2["answer"])
        second = save(api, second_body, "save-second").json()
        assert second["content_state"] == "valid"
        assert second["passages"][0]["lineage_dependencies"][0]["type"] == "passage"
        assert all(d["type"] != "passage" for d in second["passages"][0]["dependencies"])
        if legacy:
            with Session(engine) as session, session.begin():
                for item in (first, second):
                    saved = session.get(QuerySavedKnowledge, item["saved_id"])
                    manifest = copy.deepcopy(saved.manifest)
                    for passage in manifest["passages"]:
                        passage.pop("lineage_dependencies")
                    saved.manifest = manifest
            # A valid 0013 save recovers its wrapper refs without adding fields to its manifest.
            recovered = api.get(PREFIX + f"/saved/{second['saved_id']}").json()
            assert recovered["content_state"] == "valid"
            assert recovered["passages"][0]["lineage_dependencies"][0]["type"] == "passage"
        prepared = prepare(
            api, key="cached-before-removal", question="实验条件", source_kinds=["synthesis"]
        )
        with Session(engine) as session:
            immutable = immutable_rows(session)
        assert metadata(api, first["saved_id"], "remove", 0).status_code == 200
        invalid = api.get(PREFIX + f"/saved/{second['saved_id']}").json()
        assert invalid["content_state"] == "invalid" and invalid["passages"][0]["text"] == ""
        assert "QUERY_SAVED_REMOVED" in invalid["passages"][0]["issues"]
        assert api.get(PREFIX + f"/runs/{p2['query_id']}/answer").status_code == 422
        assert generate(api, prepared["query_id"], key="blocked-dispatch").status_code == 422
        assert save(api, second_body, "save-second-new-key").status_code == 422
        assert api.get(PREFIX + "/derived-graph").json() == {"nodes": [], "edges": []}
        assert (
            api.post(
                PREFIX + "/search",
                json={
                    "project_id": "project",
                    "question": "accuracy",
                    "source_kinds": ["synthesis"],
                },
            ).json()["hits"]
            == []
        )
        with Session(engine) as session:
            assert all(p["text"] == "" for p in read_passages(session, "project"))
            assert immutable_rows(session) == immutable
        assert first_provider.calls == second_provider.calls == 1


@pytest.mark.parametrize(
    "corruption",
    ["context_hash", "missing_hash", "answer_hash", "model_hash", "answer_scope", "refs"],
)
def test_legacy_lineage_unrecoverable_is_isolated_and_never_treated_as_no_dependency(
    tmp_path, corruption
):
    with client(tmp_path / "data") as api:
        engine = seed(api)
        prepared, answer, provider = completed(api, engine, "legacy")
        body = save_command(prepared, answer["answer"])
        first = save(api, body).json()
        independent = save(api, {**body, "kind": "insight"}, "independent-kind-save").json()
        with Session(engine) as session, session.begin():
            saved = session.get(QuerySavedKnowledge, first["saved_id"])
            manifest = copy.deepcopy(saved.manifest)
            for passage in manifest["passages"]:
                passage.pop("lineage_dependencies")
            if corruption == "context_hash":
                manifest["source_context_hash"] = "0" * 64
            elif corruption == "missing_hash":
                manifest.pop("source_context_hash")
            elif corruption == "answer_hash":
                manifest["answer_hash"] = "0" * 64
            elif corruption == "model_hash":
                manifest["model_lineage_hash"] = "0" * 64
            elif corruption == "answer_scope":
                foreign = session.get(QueryAnswerVersion, saved.answer_version_id)
                foreign.project_id = "other"
            else:
                manifest["passages"][0]["source_refs"] = ["UNKNOWN"]
            saved.manifest = manifest
        with Session(engine) as session:
            immutable = immutable_rows(session)
        view = api.get(PREFIX + f"/saved/{first['saved_id']}")
        assert view.status_code == 200, view.text
        assert view.json()["content_state"] == "invalid"
        passage = view.json()["passages"][0]
        assert passage["text"] == "" and "QUERY_SAVED_LINEAGE_INVALID" in passage["issues"]
        # A different save/document of the same answer is not retired by this failed projection.
        assert (
            api.get(PREFIX + f"/saved/{independent['saved_id']}").json()["content_state"] == "valid"
        )
        assert len(api.get(PREFIX + "/saved").json()["items"]) == 2
        with Session(engine) as session:
            passages = read_passages(session, "project")
            assert {p["id"] for p in passages if p["content_state"] == "valid"} == set(
                independent["passage_ids"]
            )
            assert immutable_rows(session) == immutable
        assert provider.calls == 1


def test_root_only_dependency_validation_does_not_scan_saved_lineage(tmp_path, monkeypatch):
    with client(tmp_path / "data") as api:
        engine = seed(api)
        prepared, answer, _ = completed(api, engine, "roots")
        saved = save(api, save_command(prepared, answer["answer"])).json()

        def unexpected(*_args):
            raise AssertionError("root-only validation must not scan saved wrapper lineage")

        monkeypatch.setattr("researchgraph.query_documents.saved_passage_states", unexpected)
        with Session(engine) as session:
            assert (
                validate_dependencies(session, "project", saved["passages"][0]["dependencies"])[
                    "content_state"
                ]
                == "valid"
            )


def test_removed_copy_does_not_reappear_on_append_but_unrelated_passage_remains(tmp_path):
    with client(tmp_path / "data") as api:
        engine = seed(api)
        p1, a1, _ = completed(api, engine, "first")
        first = save(api, save_command(p1, a1["answer"]), "save-first").json()
        p2, a2, _ = completed(api, engine, "second")
        second = save(
            api,
            save_command(
                p2,
                a2["answer"],
                target_document_id=first["document_id"],
                base_version_id=first["version_id"],
            ),
            "save-second",
        ).json()
        assert second["revision"] == 2
        with Session(engine) as session:
            copies = list(
                session.scalars(
                    select(QueryPassage).where(QueryPassage.version_id == second["version_id"])
                )
            )
            assert len(copies) == 2
            copied_ref = copies[0].local_ref
            immutable = copy.deepcopy([(p.id, p.text, p.local_ref, p.sha256) for p in copies])
        assert metadata(api, first["saved_id"], "remove", 0).status_code == 200
        with Session(engine) as session:
            current = read_passages(session, "project")
            assert len(current) == 1 and current[0]["id"] == second["passage_ids"][0]
            assert (
                session.scalar(
                    select(QueryPassage.local_ref).where(QueryPassage.id == current[0]["id"])
                )
                != copied_ref
            )
            assert [
                (
                    session.get(QueryPassage, row[0]).id,
                    session.get(QueryPassage, row[0]).text,
                    session.get(QueryPassage, row[0]).local_ref,
                    session.get(QueryPassage, row[0]).sha256,
                )
                for row in immutable
            ] == immutable
        assert api.get(PREFIX + f"/saved/{second['saved_id']}").json()["content_state"] == "valid"


def test_personal_source_permissions_recheck_annotation_replay_and_removal(tmp_path):
    with client(tmp_path / "data") as api:
        engine = seed(api)
        vault = tmp_path / "vault"
        vault.mkdir()
        note = vault / "reading.md"
        original = "Private synthetic accuracy interpretation."
        note.write_text(original, encoding="utf-8")
        root = post(
            api,
            "/integrations/obsidian/roots",
            {"project_id": "project", "path": str(vault)},
            key="authorize-note-root",
        )
        assert root.status_code == 200, root.text
        root_id = root.json()["id"]
        root_route = f"/api/v1/integrations/obsidian/{root_id}"
        assert (
            api.put(
                root_route + "/query-permissions",
                json={"allow_local": True, "allow_model": True},
                headers={"Idempotency-Key": "enable-note-purpose"},
            ).status_code
            == 200
        )
        assert (
            post(api, f"/integrations/obsidian/{root_id}/scan", key="scan-note-root").status_code
            == 200
        )
        p, a, provider = completed(
            api,
            engine,
            "personal-note",
            source_kinds=["note"],
            question="accuracy",
            include_personal=True,
        )
        response = save(api, save_command(p, a["answer"]))
        assert response.status_code == 200, response.text
        sid = response.json()["saved_id"]
        error(
            metadata(api, sid, "annotation", 0, annotation="personal"), "QUERY_SAVED_NOT_ACCESSIBLE"
        )
        added = metadata(api, sid, "annotation", 0, annotation="personal", include_personal=True)
        assert added.status_code == 200, added.text
        with Session(engine) as session:
            revision = KnowledgeStore(session).graph_revision("project")
        assert (
            post(
                api, f"/integrations/obsidian/{root_id}/revoke", key="revoke-note-root"
            ).status_code
            == 200
        )
        for expected, key in ((0, None), (1, "new-after-revocation")):
            error(
                metadata(
                    api,
                    sid,
                    "annotation",
                    expected,
                    annotation="personal",
                    key=key,
                    include_personal=True,
                ),
                "QUERY_SAVED_NOT_ACCESSIBLE",
            )
        error(metadata(api, sid, "remove", 1, include_personal=True), "QUERY_SAVED_NOT_ACCESSIBLE")
        with Session(engine) as session:
            assert KnowledgeStore(session).graph_revision("project") == revision
        assert provider.calls == 1 and note.read_text(encoding="utf-8") == original


def test_0013_to_current_backup_preserves_saved_rows_and_raw_exactly(tmp_path):
    engine = make_engine(tmp_path)
    config = Config()
    config.set_main_option(
        "script_location", str(Path("services/engine/researchgraph/migrations").resolve())
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0013")
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
        connection.exec_driver_sql(
            "INSERT INTO query_documents VALUES ('d','p','synthesis','Old','v','now')"
        )
        connection.exec_driver_sql(
            "INSERT INTO query_document_versions VALUES ('v','d',1,'saved',:hash,'now')",
            {"hash": "c" * 64},
        )
        connection.exec_driver_sql(
            """INSERT INTO query_passages VALUES
            ('passage','v',0,'old-local','Unchanged old answer',:hash,
             'model_synthesis','[]','[]')""",
            {"hash": "d" * 64},
        )
        connection.exec_driver_sql(
            """INSERT INTO query_saved_knowledge VALUES
            ('s','p','synthesis','Old','q','a','d','v',:hash,:hash,'["A00001"]','["passage"]',
            '{"immutable_manifest":true}',1,'now')""",
            {"hash": "e" * 64},
        )
    database = tmp_path / "researchgraph.sqlite3"
    with sqlite3.connect(database) as db:
        tables = [
            r[0]
            for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name!='alembic_version'"
            )
        ]
        before = {
            table: (
                db.execute(f'PRAGMA table_info("{table}")').fetchall(),
                db.execute(f'SELECT * FROM "{table}"').fetchall(),
            )
            for table in tables
        }
    migrate(engine, tmp_path)
    with sqlite3.connect(database) as db:
        assert {
            table: (
                db.execute(f'PRAGMA table_info("{table}")').fetchall(),
                db.execute(f'SELECT * FROM "{table}"').fetchall(),
            )
            for table in tables
        } == before
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0020",)
        assert db.execute("SELECT count(*) FROM query_saved_preferences").fetchone() == (0,)
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    backups = list((tmp_path / "backups").glob("*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0013",)
        assert {
            table: (
                db.execute(f'PRAGMA table_info("{table}")').fetchall(),
                db.execute(f'SELECT * FROM "{table}"').fetchall(),
            )
            for table in tables
        } == before
    migrate(engine, tmp_path)
    assert list((tmp_path / "backups").glob("*.sqlite3")) == backups
    engine.dispose()
