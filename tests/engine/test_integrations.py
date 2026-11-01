import copy
import hashlib
import json
import os
from pathlib import Path

import pytest
from researchgraph.integrations import AnnotationImporter, ZoteroAdapter
from researchgraph.knowledge_models import Annotation
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_engine import client, post
from test_ingest import FIXTURES, queue, wait_job


def test_authorized_notes_readonly_hash_dedup_versions_and_revoke(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "private.md"
    note.write_text("# My private interpretation\nNot a paper claim.", encoding="utf-8")
    original = note.read_bytes()
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    with client(tmp_path / "data") as api:
        project = post(api, "/projects", {"name": "Notes"}).json()["id"]
        created = post(
            api,
            "/integrations/obsidian/roots",
            {"project_id": project, "path": str(vault)},
            "notes-root",
        )
        assert created.status_code == 200, created.text
        root = created.json()["id"]
        scanned = post(api, f"/integrations/obsidian/{root}/scan", key="notes-scan").json()
        assert scanned["added"] == 1
        assert (
            post(api, f"/integrations/obsidian/{root}/scan", key="notes-again").json()["added"] == 0
        )
        notes = api.get(f"/api/v1/integrations/obsidian/{root}/notes").json()
        assert notes[0]["sha256"] == hashlib.sha256(original).hexdigest()
        assert notes[0]["authorship"] == "user" and note.read_bytes() == original
        note.write_text("Edited by user", encoding="utf-8")
        assert (
            post(api, f"/integrations/obsidian/{root}/scan", key="notes-new-version").json()[
                "added"
            ]
            == 1
        )
        assert len(api.get(f"/api/v1/integrations/obsidian/{root}/notes").json()) == 2
        assert (
            post(api, "/integrations/obsidian/not-authorized/scan", key="denied-root").status_code
            == 422
        )
        assert (
            post(api, f"/integrations/obsidian/{root}/revoke", key="revoke-root").status_code == 200
        )
        assert api.get(f"/api/v1/integrations/obsidian/{root}/notes").status_code == 422
        assert (
            post(api, f"/integrations/obsidian/{root}/scan", key="scan-revoked").status_code == 422
        )
    assert outside.read_text() == "outside"


def test_note_symlink_never_reads_outside(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    secret = tmp_path / "secret.md"
    secret.write_text("not authorized", encoding="utf-8")
    try:
        os.symlink(secret, vault / "leak.md")
    except OSError:
        pytest.skip("OS does not allow creating file symlinks")
    with client(tmp_path / "data") as api:
        project = post(api, "/projects", {"name": "Bounded notes"}).json()["id"]
        root = post(
            api,
            "/integrations/obsidian/roots",
            {"project_id": project, "path": str(vault)},
            "root-boundary",
        ).json()["id"]
        result = post(api, f"/integrations/obsidian/{root}/scan", key="scan-boundary").json()
        assert result["added"] == 0 and result["skipped"] == 1
        assert api.get(f"/api/v1/integrations/obsidian/{root}/notes").json() == []


def test_annotation_unresolved_dedup_and_original_text_are_preserved(tmp_path):
    source = FIXTURES / "two-pages.pdf"
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    with client(tmp_path, worker=True) as api:
        project = post(api, "/projects", {"name": "Annotations"}).json()["id"]
        imported = wait_job(api, queue(api, project, source, "annotation-source"))
        version = imported["result"]["revision_id"]
        raw = [
            {
                "key": "NOTE0001",
                "data": {
                    "itemType": "annotation",
                    "parentItem": "PDF00001",
                    "annotationType": "highlight",
                    "annotationText": "Baseline accuracy: 72%.",
                    "annotationComment": "My question",
                    "annotationPosition": json.dumps({"pageIndex": 0, "rects": [[1, 2, 3, 4]]}),
                },
            },
            {
                "key": "NOTE0002",
                "data": {
                    "itemType": "annotation",
                    "parentItem": "PDF00001",
                    "annotationType": "note",
                    "annotationText": "not present",
                    "annotationComment": "Unknown location",
                    "annotationPosition": "{}",
                },
            },
        ]
        before = copy.deepcopy(raw)
        with Session(api.app.state.engine) as session, session.begin():
            importer = AnnotationImporter(KnowledgeStore(session))
            result = importer.apply(version, "users/0", "PAPER001", "PDF00001", {}, raw, source)
            assert result == {"added": 2, "unresolved": 1}
        assert raw == before
        with Session(api.app.state.engine) as session, session.begin():
            assert (
                AnnotationImporter(KnowledgeStore(session)).apply(
                    version, "users/0", "PAPER001", "PDF00001", {}, raw, source
                )["added"]
                == 0
            )
            records = session.scalars(select(Annotation)).all()
            unresolved = next(a for a in records if a.annotation_key == "NOTE0002")
            assert unresolved.evidence_id is None and unresolved.source_position == {}
        with (
            Session(api.app.state.engine) as session,
            session.begin(),
            pytest.raises(KnowledgeError, match="选择器"),
        ):
            AnnotationImporter(KnowledgeStore(session)).apply(
                version, "users/0", "PAPER001", "PDF00001", {}, raw, tmp_path / "unauthorized.pdf"
            )
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash


@pytest.mark.parametrize(
    "library", ["../private", "users/0/../../etc", "https://evil.test", "users/0?token=x"]
)
def test_zotero_library_path_boundary(library):
    with pytest.raises(KnowledgeError):
        ZoteroAdapter.library(library)


def test_zotero_readonly_fixture_calls_and_missing_service(monkeypatch):
    routes = []
    adapter = ZoteroAdapter()

    def get(route):
        routes.append(route)
        if route.endswith("PAPER001"):
            return {"key": "PAPER001", "data": {"title": "Synthetic"}}
        if route.endswith("PDF00001"):
            return {"data": {"parentItem": "PAPER001"}}
        return [{"key": "NOTE0001", "data": {"itemType": "annotation"}}]

    monkeypatch.setattr(adapter, "get", get)
    monkeypatch.setattr(adapter, "attachment_path", lambda *_: Path("synthetic.pdf"))
    _, annotations, _ = adapter.read_annotations("users/0", "PAPER001", "PDF00001")
    assert len(annotations) == 1 and all(route.startswith("/users/0/items/") for route in routes)
