"""Durable library snapshots and preferences outlive disposable parser outputs."""

import asyncio
import json
import sqlite3
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from researchgraph import storage
from researchgraph.import_plan_models import ImportSession
from researchgraph.knowledge_library import ensure_library_paper, publish_version
from researchgraph.knowledge_library_api import register_knowledge_library_api
from researchgraph.knowledge_library_models import (
    KnowledgeLibrary,
    LibraryPaper,
    LibraryPaperSourceLink,
    PaperKnowledgeVersion,
)
from researchgraph.model_document_models import LlmDocumentOutput, LlmDocumentParse
from researchgraph.model_document_overview import validate_model_overview
from researchgraph.models import AttachmentRevision, Base, Idempotency, Job, Paper, Project, now
from researchgraph.paper_overview_models import PaperOverviewResult
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

EXAMPLE = Path(
    "docs/ResearchGraph_Lite_LightGraph_Addendum/examples/paper_overview_graph.example.json"
)


def _fixture(tmp_path):
    engine = storage.make_engine(tmp_path)
    Base.metadata.create_all(engine)
    project_id, paper_id, revision_id, result_id = (str(uuid4()) for _ in range(4))
    payload = validate_model_overview(EXAMPLE.read_text(encoding="utf-8"), paper_id)
    with Session(engine) as db, db.begin():
        db.add(Project(id=project_id, name="anonymous", description="", created_at=now()))
        db.flush()
        db.add(Paper(id=paper_id, project_id=project_id, title="Synthetic paper", created_at=now()))
        db.flush()
        db.add(
            AttachmentRevision(
                id=revision_id,
                paper_id=paper_id,
                sha256="a" * 64,
                parser_version="synthetic",
                page_count=1,
                warnings=[],
                created_at=now(),
            )
        )
        db.flush()
        db.add(
            PaperOverviewResult(
                id=result_id,
                project_id=project_id,
                paper_id=paper_id,
                document_version_id=revision_id,
                pdf_hash="a" * 64,
                input_hash="b" * 64,
                cache_key="c" * 64,
                schema_version=payload["schema_version"],
                prompt_version="synthetic",
                provider_id="synthetic",
                model_id="fixture",
                paper_card_json=payload["paper_card"],
                graph_json=payload["graph"],
                status="COMPLETED",
            )
        )
    app = FastAPI()
    register_knowledge_library_api(app, lambda: engine, tmp_path)
    return engine, TestClient(app), paper_id, revision_id, result_id


def _headers(key="synthetic-request"):
    return {"Idempotency-Key": key}


def _collect(client, paper_id, revision_id, **changes):
    return client.post(
        "/api/v1/knowledge/papers/collect",
        headers=_headers(),
        json={
            "paper_id": paper_id,
            "source_kind": "local_revision",
            "source_id": revision_id,
            **changes,
        },
    )


def test_read_defaults_do_not_create_rows_or_jobs_and_collect_is_zero_request_replay(tmp_path):
    engine, client, paper_id, revision_id, _ = _fixture(tmp_path)
    assert client.get("/api/v1/knowledge/library").json()["settings"]["auto_connect"] is False
    assert client.get("/api/v1/knowledge/papers").json() == {"items": [], "total": 0}
    with Session(engine) as db:
        assert db.query(KnowledgeLibrary).count() == db.query(Job).count() == 0
    response = _collect(client, paper_id, revision_id)
    assert response.status_code == 200, response.text
    result = response.json()
    version = result["current_version"]
    assert version["evidence_status"] == "legacy"
    assert version["content"]["coverage"]["status"] == "legacy_unanchored"
    assert version["content"]["graph"]["nodes"][0]["type"] == "PAPER"
    assert version["content"]["graph"]["nodes"][0]["label_zh"] == "Synthetic paper"
    assert any(edge["type"] == "HAS_KNOWLEDGE" for edge in version["content"]["graph"]["edges"])
    assert _collect(client, paper_id, revision_id).json() == result
    with Session(engine) as db:
        assert db.query(PaperKnowledgeVersion).count() == 1
        assert db.query(Job).count() == 0
        assert db.get(PaperOverviewResult, version["source_id"]).raw_output is None


@pytest.mark.parametrize("corruption", ["hash", "node", "project"])
def test_collection_revalidates_persisted_overview_ownership_and_source(tmp_path, corruption):
    engine, client, paper_id, revision_id, result_id = _fixture(tmp_path)
    with Session(engine) as db, db.begin():
        result = db.get(PaperOverviewResult, result_id)
        if corruption == "hash":
            result.pdf_hash = "d" * 64
        elif corruption == "project":
            other = Project(id=str(uuid4()), name="other", description="", created_at=now())
            db.add(other)
            db.flush()
            result.project_id = other.id
        else:
            graph = deepcopy(result.graph_json)
            graph["nodes"][0]["id"] = str(uuid4())
            result.graph_json = graph
    response = _collect(client, paper_id, revision_id)
    assert response.status_code == 409, response.text
    with Session(engine) as db:
        assert db.query(PaperKnowledgeVersion).count() == db.query(LibraryPaper).count() == 0


def test_reliable_identity_merges_project_links_but_never_title_alone(tmp_path):
    engine, _client, paper_id, _revision_id, _ = _fixture(tmp_path)
    with Session(engine) as db, db.begin():
        first = ensure_library_paper(db, db.get(Paper, paper_id))
        project = Project(id=str(uuid4()), name="second", description="", created_at=now())
        db.add(project)
        db.flush()
        second = Paper(id=str(uuid4()), project_id=project.id, title=first.title, created_at=now())
        third = Paper(id=str(uuid4()), project_id=project.id, title=first.title, created_at=now())
        db.add_all([second, third])
        db.flush()
        db.add(
            AttachmentRevision(
                id=str(uuid4()),
                paper_id=second.id,
                sha256="a" * 64,
                parser_version="test",
                page_count=1,
                warnings=[],
                created_at=now(),
            )
        )
        db.flush()
        assert ensure_library_paper(db, second).id == first.id
        assert ensure_library_paper(db, third).id != first.id
        assert db.query(LibraryPaper).count() == 2
        assert db.query(LibraryPaperSourceLink).count() == 3


def test_model_overview_collection_keeps_real_parse_identity_and_rejects_changed_source(tmp_path):
    engine, client, paper_id, _revision_id, _ = _fixture(tmp_path)
    session_id, parse_id, output_id = (str(uuid4()) for _ in range(3))
    with Session(engine) as db, db.begin():
        paper = db.get(Paper, paper_id)
        db.add(
            ImportSession(
                id=session_id,
                project_id=paper.project_id,
                source_kind="pdf",
                selection_id="synthetic",
                source_snapshot={"paper_id": paper_id},
                plan={},
                status="succeeded",
                created_at=now(),
                updated_at=now(),
            )
        )
        db.flush()
        parse = LlmDocumentParse(
            id=parse_id,
            import_session_id=session_id,
            parse_version="llm-document-1",
            modality="text",
            status="succeeded",
            warnings=[],
            created_at=now(),
            updated_at=now(),
        )
        db.add(parse)
        db.flush()
        db.add(
            LlmDocumentOutput(
                id=output_id,
                import_session_id=session_id,
                parse_id=parse_id,
                item_kind="paper_overview",
                status="succeeded",
                output_json=validate_model_overview(EXAMPLE.read_text(encoding="utf-8"), paper_id),
                usage={"source_updated_at": parse.updated_at},
                created_at=now(),
                updated_at=now(),
            )
        )
    body = {"paper_id": paper_id, "source_kind": "model_parse", "source_id": parse_id}
    result = client.post("/api/v1/knowledge/papers/collect", json=body, headers=_headers())
    assert result.status_code == 200, result.text
    assert result.json()["current_version"]["source_id"] == output_id
    with Session(engine) as db, db.begin():
        assert db.query(Job).count() == 0
        db.get(LlmDocumentParse, parse_id).updated_at = "changed-source"
    result = client.post(
        "/api/v1/knowledge/papers/collect", json=body, headers=_headers("changed-source")
    )
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == "KNOWLEDGE_SOURCE_CHANGED"


def test_versions_are_immutable_and_survive_application_paper_removal(tmp_path):
    engine, client, paper_id, revision_id, _ = _fixture(tmp_path)
    result = _collect(client, paper_id, revision_id).json()
    original = result["current_version"]
    with Session(engine) as db, db.begin():
        new = publish_version(
            db,
            paper_id=paper_id,
            source_kind="local_revision",
            source_id=revision_id,
            source_fingerprint="f" * 64,
            content_json={"new": "data"},
            source_snapshot_json={"frozen": "source"},
        )
        replay = publish_version(
            db,
            paper_id=paper_id,
            source_kind="local_revision",
            source_id=revision_id,
            source_fingerprint="f" * 64,
            content_json={"new": "data"},
            source_snapshot_json={"frozen": "source"},
            job_id="another-job",
        )
        assert new.id == replay.id
    endpoint = "/api/v1/knowledge/papers/" + result["id"]
    updated = client.patch(
        endpoint,
        headers=_headers("preference-change"),
        json={
            "note": "Personal view",
            "current_version_id": original["id"],
            "archived": True,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["current_version"] == original
    assert client.get("/api/v1/knowledge/papers").json()["total"] == 0
    assert client.get("/api/v1/knowledge/papers?include_archived=true").json()["total"] == 1
    with Session(engine) as db, db.begin():
        db.execute(delete(PaperOverviewResult).where(PaperOverviewResult.paper_id == paper_id))
        db.execute(delete(AttachmentRevision).where(AttachmentRevision.paper_id == paper_id))
        db.execute(delete(Paper).where(Paper.id == paper_id))
    restored = client.get(endpoint).json()
    assert restored["current_version"] == original
    assert len(restored["versions"]) == 2
    assert restored["source_links"][0]["paper_id"] is None
    assert restored["source_links"][0]["source_available"] is False


def test_collections_settings_layout_and_export_survive_fresh_engine(tmp_path):
    engine, client, paper_id, revision_id, _ = _fixture(tmp_path)
    paper = _collect(client, paper_id, revision_id).json()
    collection = client.post(
        "/api/v1/knowledge/collections", headers=_headers(), json={"name": "Methods"}
    ).json()
    path = f"/api/v1/knowledge/collections/{collection['id']}"
    assert client.put(path + "/papers/" + paper["id"], headers=_headers()).status_code == 200
    assert (
        client.get("/api/v1/knowledge/papers?collection_id=" + collection["id"]).json()["total"]
        == 1
    )
    for setting in ({"auto_collect": True}, {"auto_connect": True}):
        assert (
            client.patch("/api/v1/knowledge/library", headers=_headers(), json=setting).status_code
            == 422
        )
    settings = {
        "allow_network": True,
        "auto_connect": True,
        "scope": "collection",
        "collection_id": collection["id"],
    }
    assert (
        client.patch("/api/v1/knowledge/library", headers=_headers(), json=settings).status_code
        == 200
    )
    layout = {
        "view_key": "all",
        "layout": {
            "positions": [{"node_id": paper["id"], "x": 8, "y": 2, "pinned": True}],
            "viewport": {"x": 1, "y": 2, "zoom": 1.5},
        },
    }
    assert (
        client.put("/api/v1/knowledge/layout", headers=_headers(), json=layout).status_code == 200
    )
    invalid = deepcopy(layout)
    invalid["layout"]["positions"] *= 2
    assert (
        client.put(
            "/api/v1/knowledge/layout", headers=_headers("duplicate-layout"), json=invalid
        ).status_code
        == 422
    )
    engine.dispose()
    restarted = storage.make_engine(tmp_path)
    app = FastAPI()
    register_knowledge_library_api(app, lambda: restarted, tmp_path)
    fresh = TestClient(app)
    assert fresh.get("/api/v1/knowledge/layout").json() == layout
    exported = fresh.get("/api/v1/knowledge/export").json()
    assert exported["papers"][0]["current_version"] == paper["current_version"]
    assert len(exported["collections"]) == 1
    assert exported["layouts"] == [layout]
    assert exported["reports"] == []
    assert fresh.delete(path, headers=_headers()).status_code == 200
    settings = fresh.get("/api/v1/knowledge/library").json()["settings"]
    assert settings["auto_connect"] is False and settings["scope"] == "project"


def test_explicit_purge_backs_up_and_removes_mutation_copies(tmp_path, monkeypatch):
    engine, client, paper_id, revision_id, _ = _fixture(tmp_path)
    paper = _collect(client, paper_id, revision_id).json()
    cleaned = []
    monkeypatch.setitem(
        sys.modules,
        "researchgraph.knowledge_connections",
        SimpleNamespace(
            cleanup_library_paper=lambda db, identity: cleaned.append(identity),
        ),
    )
    endpoint = "/api/v1/knowledge/papers/" + paper["id"]
    assert client.delete(endpoint, headers=_headers()).status_code == 200
    assert client.delete(endpoint, headers=_headers()).status_code == 200
    assert cleaned == [paper["id"]]
    assert client.get(endpoint).status_code == 404
    assert len(list((tmp_path / "backups").glob("before-knowledge-purge-*.sqlite3"))) == 1
    with Session(engine) as db:
        assert db.query(PaperKnowledgeVersion).count() == db.query(LibraryPaper).count() == 0
        assert db.get(Paper, paper_id) is not None
        encoded = json.dumps([row.response for row in db.scalars(select(Idempotency))])
        assert paper["current_version"]["id"] not in encoded


def test_additive_lite0015_upgrade_preserves_old_rows_and_creates_backup(tmp_path):
    engine = storage.make_engine(tmp_path)
    config = Config()
    config.set_main_option("script_location", str(Path(storage.__file__).parent / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "lite0015")
        # lite0001 imports the live Base; remove future empty tables to model
        # an actual on-disk deployment that predates the library migrations.
        for table in reversed(Base.metadata.sorted_tables):
            if table.name.startswith("knowledge_") or table.name == "paper_knowledge_versions":
                table.drop(connection, checkfirst=True)
        connection.execute(
            text(
                "INSERT INTO projects (id,name,description,created_at,experience_mode) "
                "VALUES ('keep','untouched','','now','lite')"
            )
        )
    with sqlite3.connect(tmp_path / storage.DATABASE_NAME) as db:
        names = [
            row[0]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if row[0] != "alembic_version"
        ]
        old = {name: db.execute('SELECT * FROM "' + name + '"').fetchall() for name in names}
        assert "knowledge_library_papers" not in names
    storage.migrate(engine, tmp_path)
    with sqlite3.connect(tmp_path / storage.DATABASE_NAME) as db:
        assert {name: db.execute('SELECT * FROM "' + name + '"').fetchall() for name in old} == old
        assert db.execute("SELECT COUNT(*) FROM knowledge_library_papers").fetchone() == (0,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert len(list((tmp_path / "backups").glob("before-migration-*.sqlite3"))) == 1


def test_export_revalidates_reports_preserves_personal_metadata_and_excludes_private_runs(tmp_path):
    from researchgraph.knowledge_connection_models import (
        KnowledgeConnectionReport,
        KnowledgeConnectionRequest,
    )
    from researchgraph.knowledge_connections import run_knowledge_connect
    from test_knowledge_connections import (
        ConnectionProvider,
        built_papers,
        connection_record,
        queue_connection,
    )

    engine, versions, _ = built_papers(tmp_path)
    identity = queue_connection(engine, versions[1])
    provider = ConnectionProvider()
    asyncio.run(run_knowledge_connect(engine, identity, tmp_path, provider=provider))
    _job, _run, _requests, report = connection_record(engine, identity)
    with Session(engine) as db, db.begin():
        saved = db.get(KnowledgeConnectionReport, report.id)
        saved.read, saved.pinned, saved.note = True, True, "个人观点与模型分析分开保存"
    app = FastAPI()
    register_knowledge_library_api(app, lambda: engine, tmp_path)
    client = TestClient(app)
    response = client.get("/api/v1/knowledge/export")
    assert response.status_code == 200, response.text
    exported = response.json()
    saved = exported["reports"][0]
    assert saved["id"] == report.id and saved["read"] and saved["pinned"]
    assert saved["note"] == "个人观点与模型分析分开保存"
    assert saved["relations"] == report.report_json["relations"]
    encoded = json.dumps(exported)
    for private in (
        "raw_response",
        "raw_output",
        "credential_ref",
        "model_snapshot",
        "policy_json",
    ):
        assert private not in encoded
    assert provider.calls == 1
    with Session(engine) as db, db.begin():
        receipt = (
            db.query(KnowledgeConnectionRequest)
            .filter(KnowledgeConnectionRequest.run_id == report.run_id)
            .one()
        )
        receipt.raw_response = '{"schema_version":"tampered"}'
    response = client.get("/api/v1/knowledge/export")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "KNOWLEDGE_CHECKPOINT_INVALID"
    assert provider.calls == 1
