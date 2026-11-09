"""External snapshots preserve bytes, attribution, permissions and prior document history."""

import copy
import hashlib
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from researchgraph.external_document_api import register_external_document_api
from researchgraph.external_document_contracts import ExternalDocumentRegister
from researchgraph.external_document_models import ExternalDocumentVersion
from researchgraph.external_documents import (
    ExternalDocumentMutations,
    lint_document_metadata,
    list_external_documents,
    personal_external_sources,
    preview_external_document,
    read_external_document,
    validate_external_version,
)
from researchgraph.knowledge_models import AuthorizedRoot, GraphRevision
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore
from researchgraph.models import Project
from researchgraph.query_documents import read_passages, validate_dependencies
from researchgraph.query_models import (
    QueryDocument,
    QueryDocumentVersion,
    QueryOperation,
    QueryPassage,
)
from researchgraph.query_retrieval import collect_entries
from researchgraph.storage import make_engine
from researchgraph.wiki_models import WikiPage, WikiWriteRoot
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_query_documents import add_note
from test_query_documents import engine as engine


@pytest.fixture
def source(engine, tmp_path):
    with Session(engine) as session, session.begin():
        root, _, path = add_note(session, tmp_path)
        return {"root_id": root.id, "relative_path": "note.md", "path": path}


def request(source, **extra):
    return {
        "root_id": source["root_id"],
        "relative_path": source["relative_path"],
        "expected_sha256": hashlib.sha256(source["path"].read_bytes()).hexdigest(),
        "title": "Independent external Markdown",
        "attribution": "external_source",
        **extra,
    }


def register(engine, body, key="external-key-1"):
    with Session(engine) as session, session.begin():
        return ExternalDocumentMutations(KnowledgeStore(session)).register(
            "p", body, key, include_personal=True
        )


def persistence(engine):
    with Session(engine) as session:
        return {
            "versions": sorted(session.scalars(select(QueryDocumentVersion.id))),
            "passages": sorted(session.scalars(select(QueryPassage.id))),
            "operations": sorted(session.scalars(select(QueryOperation.key))),
            "heads": list(
                session.execute(
                    select(QueryDocument.id, QueryDocument.current_version_id).order_by(
                        QueryDocument.id
                    )
                )
            ),
        }


def test_registration_preserves_exact_utf8_bytes_and_never_inherits_wiki_authority(engine, source):
    original = b"\xef\xbb\xbf# External\r\n<script>untrusted()</script>\r\n"
    source["path"].write_bytes(original)
    with Session(engine) as session:
        preview = preview_external_document(session, "p", "root", "note.md", include_personal=True)
    view = register(engine, request(source))
    assert view["text"].encode("utf-8") == original
    assert view["sha256"] == preview["sha256"]
    assert view["content_state"] == "unverified" and view["snapshot_valid"]
    assert view["attribution"] == "external_source" and view["source_verified"] is False
    assert view["file_state"] == "in_sync"
    assert source["path"].read_bytes() == original
    with Session(engine) as session:
        assert list(session.scalars(select(WikiPage))) == []
        assert list(session.scalars(select(WikiWriteRoot))) == []
        assert list(session.scalars(select(GraphRevision))) == []
        paragraph = session.scalar(select(QueryPassage))
        assert paragraph.dependencies == [] and paragraph.caveats == []
        assert read_passages(session, "p") == []
        assert read_passages(session, "p", include_personal=True) == []
        assert not any(e["source_kind"] == "external" for e in collect_entries(session, "p"))
        assert lint_document_metadata(session, "p") == []
        assert list_external_documents(session, "p") == {"items": [], "total": 0}


def test_current_file_hash_idempotency_and_explicit_version_cas(engine, source):
    body = request(source, attribution="user_view")
    first = register(engine, body)
    before = persistence(engine)
    assert register(engine, body)["version_id"] == first["version_id"]
    assert persistence(engine) == before
    with pytest.raises(KnowledgeError) as conflict:
        register(engine, {**body, "title": "Different"})
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
    source["path"].write_text("A separately edited source.\n", encoding="utf-8")
    with pytest.raises(KnowledgeError) as changed:
        register(engine, body)
    assert changed.value.code == "EXTERNAL_FILE_CHANGED"
    assert persistence(engine) == before
    next_body = request(
        source,
        document_id=first["document_id"],
        base_version_id=first["version_id"],
        title="New independent source version",
    )
    second = register(engine, next_body, "external-key-2")
    assert second["revision"] == 2 and second["version_id"] != first["version_id"]
    assert len(second["versions"]) == 2
    with Session(engine) as session:
        historical = read_external_document(
            session, "p", first["document_id"], first["version_id"], include_personal=True
        )
        assert historical["text"] == first["text"]
        assert historical["title"] == first["title"]
        assert historical["file_state"] == "modified"
        assert {i["id"] for i in personal_external_sources(session, "p")} == {
            first["version_id"],
            second["version_id"],
        }
    with pytest.raises(KnowledgeError) as stale:
        register(engine, next_body, "external-key-3")
    assert stale.value.code == "EXTERNAL_VERSION_CONFLICT"


@pytest.mark.parametrize("change", ["local", "model", "root"])
def test_current_permission_revalidated_for_get_selection_registration_and_replay(
    engine, source, change
):
    body = request(source)
    view = register(engine, body)
    with Session(engine) as session, session.begin():
        KnowledgeStore(session).query().set_note_grant("p", "root", True, True)
    with Session(engine) as session:
        assert (
            validate_external_version(
                session, "p", view["version_id"], include_personal=True, purpose="model"
            )["authorization_revision"]
            == 1
        )
    with Session(engine) as session, session.begin():
        if change == "root":
            session.get(AuthorizedRoot, "root").active = False
        else:
            KnowledgeStore(session).query().set_note_grant(
                "p", "root", change != "local", change != "model"
            )
    before = persistence(engine)
    with Session(engine) as session:
        purpose = "model" if change == "model" else "local"
        with pytest.raises(KnowledgeError) as denied:
            validate_external_version(
                session, "p", view["version_id"], include_personal=True, purpose=purpose
            )
        assert denied.value.code == "EXTERNAL_SOURCE_NOT_AUTHORIZED"
        dependency = [{"type": "external", "id": view["version_id"], "sha256": view["sha256"]}]
        checked = validate_dependencies(session, "p", dependency, True, purpose)
        assert checked["content_state"] == "invalid"
        if change != "model":
            assert list_external_documents(session, "p", include_personal=True)["items"] == []
            assert personal_external_sources(session, "p") == []
            assert lint_document_metadata(session, "p", True) == []
        else:
            assert personal_external_sources(session, "p")[0]["allow_model"] is False
    if change != "model":
        with pytest.raises(KnowledgeError):
            register(engine, body)
    assert persistence(engine) == before


@pytest.mark.parametrize("damage", ["text", "attribution", "metadata", "missing", "dependencies"])
def test_snapshot_damage_blocks_get_idempotent_replay_and_new_version(engine, source, damage):
    body = request(source)
    view = register(engine, body)
    with Session(engine) as session, session.begin():
        paragraph = session.scalar(
            select(QueryPassage).where(QueryPassage.version_id == view["version_id"])
        )
        origin = session.get(ExternalDocumentVersion, view["version_id"])
        if damage == "text":
            paragraph.text = "Tampered unsupported statement."
        elif damage == "attribution":
            paragraph.attribution = "paper_author"
        elif damage == "metadata":
            origin.title = "Forged source title"
        elif damage == "missing":
            session.delete(paragraph)
        else:
            paragraph.dependencies = [{"type": "evidence", "id": "e", "sha256": "a" * 64}]
    before = persistence(engine)
    with Session(engine) as session:
        with pytest.raises(KnowledgeError) as corrupt:
            read_external_document(session, "p", view["document_id"], include_personal=True)
        assert corrupt.value.code == "EXTERNAL_SNAPSHOT_INVALID"
        metadata = lint_document_metadata(session, "p", True)
        assert metadata[0]["status"] == "invalid"
        assert "Forged" not in metadata[0]["title"]
    for command_body, key in (
        (body, "external-key-1"),
        (
            {**body, "document_id": view["document_id"], "base_version_id": view["version_id"]},
            "new-key",
        ),
    ):
        with pytest.raises(KnowledgeError) as refused:
            register(engine, command_body, key)
        assert refused.value.code == "EXTERNAL_SNAPSHOT_INVALID"
    assert persistence(engine) == before


@pytest.mark.parametrize(
    "relative",
    [
        "../outside.md",
        "sub/../../outside.md",
        "C:/private.md",
        "note.md:stream",
        "sub\\note.md",
        "/outside.md",
    ],
)
def test_preview_and_register_never_read_paths_outside_authorized_root(engine, source, relative):
    with Session(engine) as session:
        with pytest.raises(KnowledgeError) as denied:
            preview_external_document(session, "p", "root", relative, include_personal=True)
        assert denied.value.code == "EXTERNAL_FILE_UNAVAILABLE"
    original = source["path"].read_bytes()
    with pytest.raises(KnowledgeError):
        register(engine, request(source, relative_path=relative))
    assert source["path"].read_bytes() == original
    assert persistence(engine)["versions"] == []


def test_cross_project_and_default_personal_flags_block_source_body(engine, source):
    view = register(engine, request(source))
    with Session(engine) as session:
        for project_id, personal in (("p", False), ("other", True)):
            with pytest.raises(KnowledgeError):
                validate_external_version(
                    session, project_id, view["version_id"], include_personal=personal
                )
        assert lint_document_metadata(session, "other", True) == []
        assert list_external_documents(session, "other", include_personal=True)["items"] == []
    before = persistence(engine)
    with Session(engine) as session, session.begin():
        with pytest.raises(KnowledgeError):
            ExternalDocumentMutations(KnowledgeStore(session)).register(
                "other", request(source), "other-key", include_personal=True
            )
    assert persistence(engine) == before


def test_missing_disk_file_keeps_authorized_immutable_history_and_lint_target(engine, source):
    view = register(engine, request(source))
    source["path"].unlink()
    with Session(engine) as session:
        current = read_external_document(session, "p", view["document_id"], include_personal=True)
        assert current["file_state"] == "missing" and current["text"] == view["text"]
        assert current["content_state"] == "unverified" and current["source_verified"] is False
        assert lint_document_metadata(session, "p", True)[0]["id"] == view["document_id"]


def test_file_change_during_final_registration_check_rolls_back_all_metadata(
    engine, source, monkeypatch
):
    from researchgraph import external_documents

    original = external_documents.read_external_document

    def replace_before_final_read(*args, **kwargs):
        source["path"].write_text("Concurrent external editor content.", encoding="utf-8")
        return original(*args, **kwargs)

    monkeypatch.setattr(external_documents, "read_external_document", replace_before_final_read)
    before = persistence(engine)
    with pytest.raises(KnowledgeError) as changed:
        register(engine, request(source))
    assert changed.value.code == "EXTERNAL_FILE_CHANGED"
    assert persistence(engine) == before
    assert source["path"].read_text(encoding="utf-8") == "Concurrent external editor content."


def test_existing_wiki_frontmatter_and_output_root_never_grant_scientific_or_read_authority(
    engine, source
):
    from test_wiki_documents import draft, save

    wiki = save(engine, draft(engine))
    source["path"].write_text(wiki["markdown"], encoding="utf-8")
    before = persistence(engine)
    with pytest.raises(KnowledgeError) as target:
        register(
            engine,
            request(
                source,
                document_id=wiki["page_id"],
                base_version_id=wiki["version_id"],
            ),
        )
    assert target.value.code == "EXTERNAL_DOCUMENT_NOT_FOUND"
    assert persistence(engine) == before
    external = register(engine, request(source))
    assert external["document_id"] != wiki["page_id"]
    with Session(engine) as session, session.begin():
        assert session.get(QueryDocument, wiki["page_id"]).current_version_id == wiki["version_id"]
        assert (
            session.scalar(
                select(QueryPassage).where(QueryPassage.version_id == external["version_id"])
            ).dependencies
            == []
        )
        session.add(
            WikiWriteRoot(
                id="write-only",
                project_id="p",
                path=str(source["path"].parent),
                device="unused",
                inode="unused",
                active=True,
                revision=1,
                created_at="now",
            )
        )
    with Session(engine) as session:
        with pytest.raises(KnowledgeError) as no_read:
            preview_external_document(session, "p", "write-only", "note.md", include_personal=True)
        assert no_read.value.code == "EXTERNAL_SOURCE_NOT_AUTHORIZED"


def test_lint_source_selection_and_pending_scan_revalidate_current_read_permission(engine, source):
    from test_lint import codes, scan, start, step

    external = register(engine, request(source))
    scope = {"document_ids": [external["document_id"]], "include_personal": True}
    clean = scan(engine, key="external-lint-clean", **scope)
    assert "DEPENDENCY_UNVERIFIED" in codes(engine, clean)
    pending = start(engine, key="external-lint-before-revocation", **scope)
    with Session(engine) as session, session.begin():
        KnowledgeStore(session).query().set_note_grant("p", "root", False, False)
    assert step(engine, pending)["status"] == "input_stale"
    after = scan(engine, key="external-lint-after-revocation", **scope)
    assert after["total"] == 0
    assert not any("Independent external" in str(item) for item in codes(engine, after))


def test_corrupt_authorized_external_snapshot_remains_a_lint_diagnostic_target(engine, source):
    from test_lint import issues, scan

    view = register(engine, request(source))
    with Session(engine) as session, session.begin():
        paragraph = session.scalar(
            select(QueryPassage).where(QueryPassage.version_id == view["version_id"])
        )
        paragraph.text = "Corrupted body"
    report = scan(
        engine,
        key="external-corruption-lint",
        document_ids=[view["document_id"]],
        include_personal=True,
    )
    assert report["total"] > 0
    invalid = [issue for issue in issues(engine, report) if issue["code"] == "DEPENDENCY_INVALID"]
    assert any(
        "EXTERNAL_SNAPSHOT_INVALID" in issue["location"].get("issue_codes", []) for issue in invalid
    )


def test_external_api_is_explicit_and_does_not_enable_model_use(engine, source):
    app = FastAPI()

    @app.exception_handler(KnowledgeError)
    async def knowledge_error(_request, error):
        return JSONResponse(status_code=409, content={"code": error.code})

    register_external_document_api(app, lambda: engine)
    base = "/api/v1/projects/p/external-documents"
    with TestClient(app) as api:
        preview = api.post(
            base + "/preview?include_personal=true",
            json={"root_id": "root", "relative_path": "note.md"},
        )
        assert preview.status_code == 200
        assert (
            api.post(
                base + "/preview", json={"root_id": "root", "relative_path": "note.md"}
            ).json()["code"]
            == "EXTERNAL_SOURCE_NOT_AUTHORIZED"
        )
        body = request(source)
        headers = {"Idempotency-Key": "explicit-register"}
        denied = api.post(base, json=body, headers=headers)
        assert denied.json()["code"] == "EXTERNAL_SOURCE_NOT_AUTHORIZED"
        response = api.post(base + "?include_personal=true", json=body, headers=headers)
        assert response.status_code == 200
        view = response.json()
        assert api.get(base).json() == {"items": [], "total": 0}
        assert (
            api.get(base + "?include_personal=true").json()["items"][0]["document_id"]
            == view["document_id"]
        )
        detail = f"{base}/{view['document_id']}?include_personal=true"
        assert api.get(detail + "&purpose=model").json()["code"] == "EXTERNAL_SOURCE_NOT_AUTHORIZED"
        assert api.get(detail).json()["source_verified"] is False
        assert (
            api.post(
                base + "?include_personal=true", json={**body, "dependencies": []}, headers=headers
            ).status_code
            == 422
        )


def test_registered_source_reopens_through_actual_application_api_without_file_writes(tmp_path):
    from test_engine import client

    data = tmp_path / "app"
    base = "/api/v1/projects/p/external-documents"
    with client(data) as api:
        with Session(api.app.state.engine) as session, session.begin():
            session.add(Project(id="p", name="Project", description="", created_at="now"))
            session.flush()
            root, _, path = add_note(session, tmp_path)
            root_id = root.id
        original = path.read_bytes()
        response = api.post(
            base + "?include_personal=true",
            json=request({"root_id": root_id, "relative_path": "note.md", "path": path}),
            headers={"Idempotency-Key": "actual-app-external"},
        )
        assert response.status_code == 200, response.text
        saved = response.json()
    with client(data) as reopened:
        result = reopened.get(base + f"/{saved['document_id']}?include_personal=true")
        assert result.status_code == 200, result.text
        assert result.json()["version_id"] == saved["version_id"]
        assert result.json()["text"] == original.decode("utf-8")
        assert reopened.get(base).json()["items"] == []
    assert path.read_bytes() == original


def test_contract_forbids_fake_evidence_paths_and_incomplete_version_baseline(source):
    from pydantic import ValidationError

    for extra in (
        {"path": str(source["path"])},
        {"attribution": "paper_author"},
        {"dependencies": [{"type": "evidence", "id": "e"}]},
        {"document_id": "doc"},
        {"base_version_id": "version"},
        {"title": "  "},
    ):
        with pytest.raises(ValidationError):
            ExternalDocumentRegister.model_validate(request(source, **extra))


def test_0017_to_0018_preserves_old_rows_and_external_file_bytes(tmp_path):
    from test_p5_migration import snapshot

    data = tmp_path / "migration"
    engine = make_engine(data)
    config = Config()
    config.set_main_option(
        "script_location", str(Path("services/engine/researchgraph/migrations").resolve())
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0017")
    with Session(engine) as session, session.begin():
        session.execute(
            text(
                "INSERT INTO projects (id, name, description, created_at) "
                "VALUES (:id, :name, :description, :created_at)"
            ),
            {"id": "p", "name": "Old project", "description": "Keep", "created_at": "old"},
        )
        _, _, path = add_note(session, tmp_path)
    old_bytes = path.read_bytes()
    database = data / "researchgraph.sqlite3"
    before = copy.deepcopy(snapshot(database))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0018")
    assert snapshot(database, list(before)) == before
    assert path.read_bytes() == old_bytes
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0018",)
        assert db.execute("SELECT * FROM external_document_versions").fetchall() == []
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    engine.dispose()
