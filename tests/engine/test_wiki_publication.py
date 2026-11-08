"""Temporary Vault fault matrix: no user files, PDFs, model calls, or live credentials."""

import hashlib
import os
import subprocess

import pytest
from researchgraph.knowledge_models import AuthorizedRoot
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore
from researchgraph.query_documents import read_passages
from researchgraph.wiki_models import WikiFileBinding, WikiPublication, WikiVersion, WikiWriteRoot
from researchgraph.wiki_publish import (
    WikiPublisher,
    _folder,
    authorize_root,
    file_diagnostics,
    file_status,
    inspect_file,
    revoke_root,
)
from researchgraph.wiki_store import page_filename, read_page
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_query_documents import engine as engine
from test_wiki_documents import draft, passage, patch, save


def output(engine, tmp_path, view):
    folder = tmp_path / "vault"
    folder.mkdir(exist_ok=True)
    with Session(engine) as session, session.begin():
        root = authorize_root(KnowledgeStore(session), "p", str(folder))
    command = {
        "root_id": root["root_id"],
        "version_id": view["version_id"],
        "expected_content_hash": view["content_hash"],
        "expected_target_hash": None,
    }
    target = folder / _folder("p") / page_filename(view["page_id"])
    return command, target


def test_first_publish_identical_content_new_key_and_restart_are_idempotent(engine, tmp_path):
    view = save(engine, draft(engine))
    command, target = output(engine, tmp_path, view)
    result = WikiPublisher(engine).publish("p", view["page_id"], command, "publish-key-1")
    assert result["state"] == "succeeded"
    before = target.stat()
    assert target.read_text(encoding="utf-8") == view["markdown"]
    again = WikiPublisher(engine).publish("p", view["page_id"], command, "publish-key-1")
    assert again["operation_id"] == result["operation_id"]
    command["expected_target_hash"] = hashlib.sha256(target.read_bytes()).hexdigest()
    third = WikiPublisher(engine).publish("p", view["page_id"], command, "publish-key-2")
    assert third["state"] == "succeeded"
    assert target.stat().st_mtime_ns == before.st_mtime_ns
    with Session(engine) as session:
        status = file_status(session, "p", view["page_id"])
        assert status["state"] == "in_sync"
        assert file_diagnostics(session, "p", view["page_id"]) == []
        assert len(read_passages(session, "p")) == 2
    assert not list(target.parent.glob(".stage-*.tmp"))


@pytest.mark.parametrize(
    "checkpoint", ["prepared", "staged", "replacing", "replaced", "before_confirm"]
)
def test_crash_each_durable_phase_recovers_without_overwriting_private_files(
    engine, tmp_path, checkpoint
):
    class Crash(BaseException):
        pass

    view = save(engine, draft(engine))
    command, target = output(engine, tmp_path, view)
    private = tmp_path / "vault" / "personal.md"
    private.write_bytes(b"Private unchanged.\n")
    private_sha = hashlib.sha256(private.read_bytes()).hexdigest()

    def fault(stage):
        if stage == checkpoint:
            raise Crash()

    with pytest.raises(Crash):
        WikiPublisher(engine, fault).publish("p", view["page_id"], command, "crash-publish-1")
    with Session(engine) as session:
        operation = session.scalar(select(WikiPublication))
        operation_id = operation.id
        assert operation.state in {"prepared", "staged", "replacing"}
    restored = WikiPublisher(engine).recover("p", operation_id)
    assert restored["state"] == "succeeded"
    assert target.read_text(encoding="utf-8") == view["markdown"]
    assert hashlib.sha256(private.read_bytes()).hexdigest() == private_sha
    assert WikiPublisher(engine).recover("p", operation_id)["state"] == "succeeded"


@pytest.mark.parametrize(
    "private_data", [b"", b"Private document", b"---\nresearchgraph: wiki-1\n---"]
)
def test_same_name_private_file_even_zero_bytes_never_adopted(engine, tmp_path, private_data):
    view = save(engine, draft(engine))
    command, target = output(engine, tmp_path, view)
    target.parent.mkdir()
    target.write_bytes(private_data)
    result = WikiPublisher(engine).publish("p", view["page_id"], command, "private-collision")
    assert result["state"] == "conflict" and result["error"] == "WIKI_PRIVATE_FILE"
    assert target.read_bytes() == private_data
    with Session(engine) as session:
        assert session.get(WikiFileBinding, view["page_id"]) is None


def test_external_edit_snapshot_diff_and_no_silent_overwrite(engine, tmp_path):
    view = save(engine, draft(engine))
    command, target = output(engine, tmp_path, view)
    assert (
        WikiPublisher(engine).publish("p", view["page_id"], command, "first")["state"]
        == "succeeded"
    )
    old_sha = hashlib.sha256(target.read_bytes()).hexdigest()
    private = target.read_bytes() + b"\nA personal external addition.\n"
    target.write_bytes(private)
    with Session(engine) as session, session.begin():
        assert file_status(session, "p", view["page_id"])["state"] == "modified"
        snapshot = inspect_file(KnowledgeStore(session), "p", view["page_id"])
        assert snapshot["attribution"] == "external_user" and not snapshot["source_verified"]
        assert "A personal external addition." in snapshot["diff"]
        assert "WIKI_FILE_MODIFIED" in {
            i["code"] for i in file_diagnostics(session, "p", view["page_id"])
        }
        # Internal valid saved version remains usable; external bytes never inherit its manifest.
        assert all(p["content_state"] == "valid" for p in read_passages(session, "p"))
    updated = patch(
        engine,
        view,
        [
            {
                "op": "replace",
                "section_id": view["sections"][0]["section_id"],
                "passage": passage("Updated summary."),
            }
        ],
    )
    updated = save(engine, updated)
    command.update(
        version_id=updated["version_id"],
        expected_content_hash=updated["content_hash"],
        expected_target_hash=old_sha,
    )
    rejected = WikiPublisher(engine).publish("p", view["page_id"], command, "external-conflict")
    assert rejected["state"] == "conflict"
    assert target.read_bytes() == private


def test_update_saved_version_uses_old_file_hash_and_preserves_history(engine, tmp_path):
    view = save(engine, draft(engine))
    command, target = output(engine, tmp_path, view)
    first = WikiPublisher(engine).publish("p", view["page_id"], command, "first")
    old_hash = first["target_hash"]
    updated = save(
        engine,
        patch(
            engine,
            view,
            [
                {
                    "op": "replace",
                    "section_id": view["sections"][0]["section_id"],
                    "passage": passage("Updated result."),
                }
            ],
        ),
    )
    command.update(
        version_id=updated["version_id"],
        expected_content_hash=updated["content_hash"],
        expected_target_hash=old_hash,
    )
    result = WikiPublisher(engine).publish("p", view["page_id"], command, "update")
    assert result["state"] == "succeeded"
    assert "Updated result." in target.read_text(encoding="utf-8")
    with Session(engine) as session:
        assert (
            read_page(session, "p", view["page_id"], view["version_id"])["markdown"]
            == view["markdown"]
        )


def test_read_authorization_never_grants_writes_and_revoked_output_fails(engine, tmp_path):
    view = save(engine, draft(engine))
    folder = tmp_path / "vault"
    folder.mkdir()
    with Session(engine) as session, session.begin():
        session.add(
            AuthorizedRoot(
                id="read-only", project_id="p", path=str(folder), active=True, created_at="now"
            )
        )
    with pytest.raises(KnowledgeError):
        WikiPublisher(engine).publish(
            "p",
            view["page_id"],
            {
                "root_id": "read-only",
                "version_id": view["version_id"],
                "expected_content_hash": view["content_hash"],
            },
            "unauthorized",
        )
    command, target = output(engine, tmp_path, view)
    with Session(engine) as session, session.begin():
        revoke_root(KnowledgeStore(session), "p", command["root_id"])
    with pytest.raises(KnowledgeError):
        WikiPublisher(engine).publish("p", view["page_id"], command, "revoked")
    assert not target.exists()


@pytest.mark.parametrize("race", ["external", "revoke", "source"])
def test_last_phase_rechecks_external_bytes_authorization_and_source(engine, tmp_path, race):
    from researchgraph.models import Chunk

    view = save(engine, draft(engine))
    command, target = output(engine, tmp_path, view)

    def fault(stage):
        if stage != "replacing":
            return
        if race == "external":
            target.write_bytes(b"Concurrent private file")
        else:
            with Session(engine) as session, session.begin():
                if race == "revoke":
                    revoke_root(KnowledgeStore(session), "p", command["root_id"])
                else:
                    session.get(Chunk, "c").text = "Changed source."

    result = WikiPublisher(engine, fault).publish("p", view["page_id"], command, "race")
    assert result["state"] == "conflict"
    if race == "external":
        assert target.read_bytes() == b"Concurrent private file"
    else:
        assert not target.exists()


def test_permission_failure_keeps_previous_export_and_is_recoverable(engine, tmp_path, monkeypatch):
    import researchgraph.wiki_publish as module

    view = save(engine, draft(engine))
    command, target = output(engine, tmp_path, view)
    assert (
        WikiPublisher(engine).publish("p", view["page_id"], command, "first")["state"]
        == "succeeded"
    )
    previous = target.read_bytes()
    updated = save(
        engine,
        patch(
            engine,
            view,
            [
                {
                    "op": "replace",
                    "section_id": view["sections"][0]["section_id"],
                    "passage": passage("Changed summary."),
                }
            ],
        ),
    )
    command.update(
        version_id=updated["version_id"],
        expected_content_hash=updated["content_hash"],
        expected_target_hash=hashlib.sha256(previous).hexdigest(),
    )
    original = module.os.replace

    def denied(*args, **kwargs):
        raise PermissionError("Synthetic permission failure")

    monkeypatch.setattr(module.os, "replace", denied)
    failed = WikiPublisher(engine).publish("p", view["page_id"], command, "permission-fail")
    assert failed["error"] == "WIKI_PERMISSION_DENIED"
    assert target.read_bytes() == previous
    monkeypatch.setattr(module.os, "replace", original)
    assert WikiPublisher(engine).recover("p", failed["operation_id"])["state"] == "succeeded"


@pytest.mark.parametrize("link_kind", ["symlink", "junction"])
def test_generated_directory_link_escape_rejected_without_outside_writes(
    engine, tmp_path, link_kind
):
    view = save(engine, draft(engine))
    command, target = output(engine, tmp_path, view)
    outside = tmp_path / "outside"
    outside.mkdir()
    if link_kind == "junction":
        if os.name != "nt":
            pytest.skip("Windows junction only")
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target.parent), str(outside)], capture_output=True
        )
        assert completed.returncode == 0
    else:
        try:
            target.parent.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("Current account lacks symbolic-link privilege")
    try:
        result = WikiPublisher(engine).publish("p", view["page_id"], command, "unsafe")
        assert result["state"] == "failed" and result["error"] == "WIKI_UNSAFE_PATH"
        assert list(outside.iterdir()) == []
    finally:
        if link_kind == "junction":
            target.parent.rmdir()
        else:
            target.parent.unlink()


def test_root_replacement_and_forged_relative_path_rejected(engine, tmp_path):
    view = save(engine, draft(engine))
    command, target = output(engine, tmp_path, view)

    class Crash(BaseException):
        pass

    def fault(stage):
        if stage == "prepared":
            raise Crash()

    with pytest.raises(Crash):
        WikiPublisher(engine, fault).publish("p", view["page_id"], command, "path")
    with Session(engine) as session, session.begin():
        operation = session.scalar(select(WikiPublication))
        operation.relative_path = "../outside.md"
        op_id = operation.id
    assert WikiPublisher(engine).recover("p", op_id)["error"] == "WIKI_UNSAFE_PATH"
    assert not (tmp_path / "outside.md").exists()
    assert not target.exists()


def test_missing_file_and_section_link_diagnostics_do_not_touch_files(engine, tmp_path):
    view = save(engine, draft(engine))
    command, target = output(engine, tmp_path, view)
    WikiPublisher(engine).publish("p", view["page_id"], command, "first")
    target.write_text("Edited without any anchors. [broken](#ref-missing)\n", encoding="utf-8")
    before = target.read_bytes()
    with Session(engine) as session:
        codes = {issue["code"] for issue in file_diagnostics(session, "p", view["page_id"])}
        assert {
            "WIKI_FILE_MODIFIED",
            "WIKI_SECTION_MAPPING_INVALID",
            "WIKI_REFERENCE_LINK_BROKEN",
        } <= codes
    assert target.read_bytes() == before
    target.unlink()
    with Session(engine) as session:
        assert file_status(session, "p", view["page_id"])["state"] == "missing"
        assert all(p["content_state"] == "valid" for p in read_passages(session, "p"))


def test_cross_project_root_scope_and_arbitrary_page_path_rejected(engine, tmp_path):
    view = save(engine, draft(engine))
    with Session(engine) as session, session.begin():
        folder = tmp_path / "other-vault"
        folder.mkdir()
        other = authorize_root(KnowledgeStore(session), "other", str(folder))
    with pytest.raises(KnowledgeError):
        WikiPublisher(engine).publish(
            "p",
            view["page_id"],
            {
                "root_id": other["root_id"],
                "version_id": view["version_id"],
                "expected_content_hash": view["content_hash"],
            },
            "cross-project",
        )
    for malicious in ("../private", "C:/private", "page.md", "a\\b", ""):
        with pytest.raises(KnowledgeError):
            page_filename(malicious)
    with Session(engine) as session:
        assert len(list(session.scalars(select(WikiWriteRoot)))) == 1


def test_forged_reference_and_matching_cached_render_cannot_be_published(engine, tmp_path):
    from researchgraph.wiki_store import _derive_references, _sections, render_markdown

    view = save(engine, draft(engine))
    command, target = output(engine, tmp_path, view)
    with Session(engine) as session, session.begin():
        wiki = session.get(WikiVersion, view["version_id"])
        sections = _sections(session, view["version_id"])
        _, section_refs = _derive_references(session, "p", sections)
        wiki.references = [{**wiki.references[0], "quote": "An invented scientific result."}]
        wiki.markdown = render_markdown(
            view["page_id"],
            wiki.title,
            sections,
            wiki.references,
            section_refs,
            wiki.content_hash,
        )
    with pytest.raises(KnowledgeError) as caught:
        WikiPublisher(engine).publish("p", view["page_id"], command, "forged-render")
    assert caught.value.code == "WIKI_CONTENT_CHANGED"
    assert not target.exists()


@pytest.mark.parametrize("checkpoint", ["staged", "replacing", "replaced", "before_confirm"])
def test_update_crash_recovers_exact_new_file_and_confirms_its_identity(
    engine, tmp_path, checkpoint
):
    class Crash(BaseException):
        pass

    view = save(engine, draft(engine))
    command, target = output(engine, tmp_path, view)
    first = WikiPublisher(engine).publish("p", view["page_id"], command, "first-export")
    updated = save(
        engine,
        patch(
            engine,
            view,
            [
                {
                    "op": "replace",
                    "section_id": view["sections"][0]["section_id"],
                    "passage": passage("An updated interpretation."),
                }
            ],
        ),
    )
    command.update(
        version_id=updated["version_id"],
        expected_content_hash=updated["content_hash"],
        expected_target_hash=first["target_hash"],
    )

    def crash(stage):
        if stage == checkpoint:
            raise Crash()

    with pytest.raises(Crash):
        WikiPublisher(engine, crash).publish("p", view["page_id"], command, "crashed-update")
    with Session(engine) as session:
        operation = session.scalar(
            select(WikiPublication).where(
                WikiPublication.key == "wiki-publish:p:crashed-update",
            )
        )
        operation_id = operation.id
    result = WikiPublisher(engine).recover("p", operation_id)
    assert result["state"] == "succeeded"
    assert target.read_text(encoding="utf-8") == updated["markdown"]
    with Session(engine) as session:
        assert file_status(session, "p", view["page_id"])["state"] == "in_sync"
    assert not list(target.parent.glob(".stage-*.tmp"))


def test_equal_bytes_from_replaced_external_file_do_not_inherit_managed_identity(engine, tmp_path):
    view = save(engine, draft(engine))
    command, target = output(engine, tmp_path, view)
    first = WikiPublisher(engine).publish("p", view["page_id"], command, "first-export")
    external = target.parent / "private-replacement.md"
    external.write_bytes(target.read_bytes())
    os.replace(external, target)
    identity = target.stat().st_ino
    command["expected_target_hash"] = first["target_hash"]
    result = WikiPublisher(engine).publish("p", view["page_id"], command, "external-identity")
    assert result["state"] == "conflict" and result["error"] == "WIKI_FILE_CONFLICT"
    assert target.stat().st_ino == identity
