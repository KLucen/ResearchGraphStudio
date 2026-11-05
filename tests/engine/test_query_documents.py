"""Q01 deterministic document state and transitive authorization checks."""

import copy
import hashlib

import pytest
from pydantic import ValidationError
from researchgraph.knowledge_models import (
    AuthorizedRoot,
    EvidenceSpan,
    GraphRevision,
    KnowledgeNode,
    ModelRun,
    NodeEvidence,
    NoteSnapshot,
    Section,
)
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, text_hash
from researchgraph.models import AttachmentRevision, Chunk, Event, Job, Paper, Project
from researchgraph.query_contracts import (
    DocumentSaveRequest,
    GroundedQueryPassage,
    QueryAnswer,
    QueryDependency,
    QueryRequest,
    QuerySaveCommand,
)
from researchgraph.query_documents import (
    read_authorized_file,
    read_notes,
    read_passages,
    validate_dependencies,
)
from researchgraph.query_models import QueryDocumentVersion, QueryFileBinding, QueryPassage
from researchgraph.reading_models import CandidateMetadata
from researchgraph.storage import make_engine, migrate
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_engine import client, post
from test_reading_extraction import candidate_batch


@pytest.fixture
def engine(tmp_path):
    engine = make_engine(tmp_path / "data")
    migrate(engine, tmp_path / "data")
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                Project(id="p", name="One", description="", created_at="now"),
                Project(id="other", name="Other", description="", created_at="now"),
            ]
        )
        session.flush()
        session.add(Paper(id="paper", project_id="p", title="Synthetic", created_at="now"))
        session.flush()
        session.add(
            AttachmentRevision(
                id="v",
                paper_id="paper",
                sha256="a" * 64,
                parser_version="synthetic",
                page_count=1,
                warnings=[],
                created_at="2026-01-01",
            )
        )
        session.flush()
        session.add(
            Chunk(
                id="c",
                revision_id="v",
                page_index=0,
                page_label="1",
                block_index=0,
                text="A method at 20 K.",
                bbox=[0, 0, 100, 50],
            )
        )
        session.add(
            Section(
                id="s",
                document_version_id="v",
                title="Methods",
                ordinal=0,
                role="methods",
                parser="synthetic",
            )
        )
        session.flush()
        session.add(
            EvidenceSpan(
                id="e",
                document_version_id="v",
                section_id="s",
                paragraph_id="c",
                page_index=0,
                start_offset=0,
                end_offset=17,
                quote="A method at 20 K.",
                text_sha256=text_hash("A method at 20 K."),
                normalization="identity-v1",
                bbox_list=[[0, 0, 100, 50]],
            )
        )
    yield engine
    engine.dispose()


def dependency():
    return {
        "type": "chunk",
        "id": "c",
        "sha256": text_hash("A method at 20 K."),
        "start": 0,
        "end": 17,
        "quote": "A method at 20 K.",
    }


def request(**updates):
    body = {
        "project_id": "p",
        "title": "Methods",
        "kind": "wiki",
        "passages": [
            {
                "local_ref": "one",
                "text": "The experiment uses 20 K.",
                "attribution": "paper_author",
                "dependencies": [dependency()],
            }
        ],
    }
    return {**body, **updates}


def add_note(session, tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir(exist_ok=True)
    path = vault / "note.md"
    path.write_text("A personal interpretation.", encoding="utf-8")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    root = AuthorizedRoot(id="root", project_id="p", path=str(vault), active=True, created_at="now")
    session.add(root)
    session.flush()
    note = NoteSnapshot(
        id="note",
        root_id=root.id,
        relative_path="note.md",
        sha256=sha,
        text=path.read_text(),
        created_at="now",
    )
    session.add(note)
    session.flush()
    return root, note, path


def test_query_contracts_are_strict_and_do_not_accept_fake_source_identity():
    assert QueryRequest(project_id="p", question="Question").purpose == "local"
    for extra in (
        {"provider": "mock"},
        {"limit": 0},
        {"paper_ids": ["a", "a"]},
        {"question": " "},
        {"source_kinds": ["private"]},
        {"knowledge_kinds": ["unregistered"]},
        {"source_kinds": ["wiki", "wiki"]},
    ):
        with pytest.raises(ValidationError):
            QueryRequest.model_validate({"project_id": "p", "question": "Question", **extra})
    for dep in (
        {"type": "node", "id": "node"},
        {"type": "note", "id": "note"},
        {**dependency(), "page_index": 12},
        {**dependency(), "end": 0},
    ):
        with pytest.raises(ValidationError):
            QueryDependency.model_validate(dep)
    duplicate = request()
    duplicate["passages"] *= 2
    with pytest.raises(ValidationError):
        DocumentSaveRequest.model_validate(duplicate)


def test_save_versions_are_immutable_idempotent_and_do_not_advance_scientific_graph(engine):
    with Session(engine) as session, session.begin():
        store = KnowledgeStore(session)
        first = store.query().save_document(request(), "doc-one")
        assert store.query().save_document(request(), "doc-one") == first
        with pytest.raises(KnowledgeError, match="相同操作键"):
            store.query().save_document(request(title="Different"), "doc-one")
        old = copy.deepcopy(session.get(QueryPassage, first["passage_ids"][0]).text)
        second = store.query().save_document(
            request(document_id=first["document_id"], base_version_id=first["version_id"]),
            "doc-two",
        )
        assert second["revision"] == 2
        assert session.get(QueryPassage, first["passage_ids"][0]).text == old
        assert session.get(QueryDocumentVersion, first["version_id"]).state == "saved"
        assert read_passages(session, "p")[0]["version_id"] == second["version_id"]
        assert store.graph_revision("p") == 0
        assert session.get(GraphRevision, "p") is None
        with pytest.raises(KnowledgeError, match="文档基线"):
            store.query().save_document(
                request(document_id=first["document_id"], base_version_id=first["version_id"]),
                "stale-write",
            )
    with Session(engine) as session:
        assert len(read_passages(session, "p")) == 1
        events = list(session.scalars(select(Event)))
        assert len(events) == 2 and all(e.before_revision == e.after_revision == 0 for e in events)


def test_answer_and_explicit_save_contracts_are_reserved_strict_and_consistent():
    passage = GroundedQueryPassage(
        local_ref="p1",
        text="A grounded explanation.",
        attribution="paper_author",
        source_refs=["S1"],
    )
    body = dict(
        answer_version_id="answer",
        query_run_id="run",
        revision=1,
        input_hash="a" * 64,
        status="validated",
        knowledge_status="source_grounded",
        passages=[passage.model_dump()],
    )
    assert QueryAnswer.model_validate(body).passages[0].source_refs == ["S1"]
    for changes in (
        {"passages": []},
        {"status": "incomplete"},
        {"knowledge_status": "mixed_sources"},
        {"passages": [passage.model_dump(), passage.model_dump()]},
        {"passages": [{**passage.model_dump(), "attribution": "user_view"}]},
        {"knowledge_status": "insufficient"},
        {"input_hash": "forged"},
    ):
        with pytest.raises(ValidationError):
            QueryAnswer.model_validate({**body, **changes})
    answer = QueryAnswer.model_validate(
        {
            **body,
            "passages": [],
            "knowledge_status": "insufficient",
            "limitations": ["No source found."],
        }
    )
    assert answer.passages == []
    command = dict(
        source_query_id="run",
        answer_version_id="answer",
        selected_passage_refs=["p1"],
        expected_input_hash="a" * 64,
    )
    assert QuerySaveCommand.model_validate(command).kind == "synthesis"
    for changes in (
        {"selected_passage_refs": ["p1", "p1"]},
        {"target_document_id": "wiki"},
        {"base_version_id": "version"},
        {"execute_shell": "forbidden"},
    ):
        with pytest.raises(ValidationError):
            QuerySaveCommand.model_validate({**command, **changes})


def test_default_paper_read_does_not_open_excluded_personal_document_file(
    engine, tmp_path, monkeypatch
):
    with Session(engine) as session, session.begin():
        root, note, path = add_note(session, tmp_path)
        body = request()
        body["passages"][0].update(
            attribution="model_synthesis",
            dependencies=[{"type": "note", "id": note.id, "sha256": note.sha256}],
        )
        mutation = KnowledgeStore(session).query()
        saved = mutation.save_document(body, "private-document")
        mutation.register_file(
            saved["document_id"],
            root.id,
            "note.md",
            saved["version_id"],
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )

        def forbidden(*args, **kwargs):
            pytest.fail("Default literature mode must not open a personal file")

        monkeypatch.setattr("researchgraph.query_documents.read_authorized_file", forbidden)
        assert read_passages(session, "p") == []
        assert read_notes(session, "p") == []


def test_new_draft_does_not_replace_saved_version_or_enter_retrieval(engine):
    with Session(engine) as session, session.begin():
        mutation = KnowledgeStore(session).query()
        first = mutation.save_document(request(), "saved")
        draft = mutation.save_document(
            request(
                document_id=first["document_id"], base_version_id=first["version_id"], state="draft"
            ),
            "draft",
        )
        assert read_passages(session, "p")[0]["version_id"] == first["version_id"]
        assert draft["revision"] == 2
        next_saved = mutation.save_document(
            request(document_id=first["document_id"], base_version_id=first["version_id"]),
            "saved-next",
        )
        assert next_saved["revision"] == 3
        mutation.save_document(request(title="Only draft", state="draft"), "only-draft")
        assert len(read_passages(session, "p")) == 1


@pytest.mark.parametrize(
    "change",
    [{"id": "missing"}, {"sha256": "0" * 64}, {"quote": "Changed"}, {"end": 180}, {"start": 1}],
)
def test_bad_chunk_identity_is_rejected_before_document_write(engine, change):
    with Session(engine) as session, session.begin():
        dep = {**dependency(), **change}
        checked = validate_dependencies(session, "p", [dep])
        assert checked["content_state"] == "invalid"
        body = request()
        body["passages"][0]["dependencies"] = [dep]
        with pytest.raises(KnowledgeError):
            KnowledgeStore(session).query().save_document(body, "bad")


def test_cross_project_sources_and_document_target_are_rejected(engine):
    with Session(engine) as session, session.begin():
        assert validate_dependencies(session, "other", [dependency()])["content_state"] == "invalid"
        mutation = KnowledgeStore(session).query()
        first = mutation.save_document(request(), "first")
        with pytest.raises(KnowledgeError):
            mutation.save_document(
                request(
                    project_id="other",
                    document_id=first["document_id"],
                    base_version_id=first["version_id"],
                ),
                "other",
            )
        passage = session.get(QueryPassage, first["passage_ids"][0])
        checked = validate_dependencies(
            session, "other", [{"type": "passage", "id": passage.id, "sha256": passage.sha256}]
        )
        assert checked["content_state"] == "invalid" and not checked["roots"]


def test_only_changed_passage_becomes_stale(engine):
    with Session(engine) as session, session.begin():
        body = request()
        body["passages"].append(
            {
                "local_ref": "two",
                "text": "A second valid statement.",
                "attribution": "model_synthesis",
                "dependencies": [dependency()],
            }
        )
        done = KnowledgeStore(session).query().save_document(body, "two-passages")
        first = session.get(QueryPassage, done["passage_ids"][0])
        first.dependencies = [{**dependency(), "sha256": "0" * 64}]
        values = read_passages(session, "p")
        assert [v["content_state"] for v in values] == ["invalid", "valid"]
        session.add(
            AttachmentRevision(
                id="v2",
                paper_id="paper",
                sha256="b" * 64,
                parser_version="synthetic",
                page_count=1,
                warnings=[],
                created_at="2026-02-01",
            )
        )
        session.flush()
        assert read_passages(session, "p")[1]["content_state"] == "stale"


def test_evidence_and_node_roots_retain_project_version_and_anchor(engine):
    with Session(engine) as session, session.begin():
        session.add(
            Job(
                id="j",
                project_id="p",
                kind="knowledge_extract",
                status="succeeded",
                attempt=1,
                created_at="now",
                updated_at="now",
            )
        )
        session.flush()
        session.add(
            ModelRun(
                id="m",
                job_id="j",
                document_version_id="v",
                provider="synthetic-production-no-network",
                model="synthetic",
                prompt_name="P02_reading_extract",
                prompt_hash="0" * 64,
                schema_version="reading-1.0",
                input_hash="0" * 64,
                parameters={},
                status="succeeded",
                created_at="now",
            )
        )
        session.flush()
        session.add(
            KnowledgeNode(
                id="n",
                paper_id="paper",
                document_version_id="v",
                kind="claim",
                text="Claim",
                payload=candidate_batch("e", "v", "c")["items"][0],
                origin="author",
                authorship="paper_author",
                source_status="source_verified",
                review_status="unreviewed",
                issues=[],
                dimension=None,
                known_state=None,
                value=None,
                unit=None,
                fingerprint="n" * 64,
                model_run_id="m",
                revision=2,
                created_at="now",
                updated_at="now",
            )
        )
        session.flush()
        session.add(
            CandidateMetadata(
                node_id="n",
                quality={},
                validation_status="valid",
                canonical_id=None,
                policy_version="synthetic",
            )
        )
        session.add(NodeEvidence(node_id="n", evidence_id="e", role="supports"))
        session.flush()
        dep = {"type": "node", "id": "n", "revision": 2}
        checked = validate_dependencies(session, "p", [dep])
        assert checked["content_state"] == "valid"
        assert checked["roots"][0]["paper_id"] == "paper"
        assert checked["roots"][0]["document_version_id"] == "v"
        assert checked["roots"][0]["quote"] == "A method at 20 K."
        assert (
            validate_dependencies(session, "p", [{**dep, "revision": 1}])["content_state"]
            == "stale"
        )
        session.get(ModelRun, "m").provider = "mock"
        assert validate_dependencies(session, "p", [dep])["content_state"] == "invalid"
        session.get(ModelRun, "m").provider = "synthetic-production-no-network"
        session.get(CandidateMetadata, "n").validation_status = "quarantined"
        assert validate_dependencies(session, "p", [dep])["content_state"] == "invalid"
        session.get(CandidateMetadata, "n").validation_status = "valid"
        session.get(EvidenceSpan, "e").quote = "Wrong"
        assert validate_dependencies(session, "p", [dep])["content_state"] == "invalid"


def test_dependency_cycle_and_unsaved_passage_are_never_scientific_support(engine):
    with Session(engine) as session, session.begin():
        mutation = KnowledgeStore(session).query()
        first = mutation.save_document(request(), "first")
        passage = session.get(QueryPassage, first["passage_ids"][0])
        dep = {"type": "passage", "id": passage.id, "sha256": passage.sha256}
        passage.dependencies = [dep]
        checked = validate_dependencies(session, "p", [dep])
        assert checked["content_state"] == "invalid"
        assert "QUERY_DEPENDENCY_CYCLE" in checked["issues"]
        passage.dependencies = [dependency()]
        session.get(QueryDocumentVersion, first["version_id"]).state = "draft"
        assert validate_dependencies(session, "p", [dep])["content_state"] == "invalid"


def test_note_grants_revoke_through_document_and_transitive_document(engine, tmp_path):
    with Session(engine) as session, session.begin():
        root, note, path = add_note(session, tmp_path)
        assert read_notes(session, "p") == []
        assert len(read_notes(session, "p", True)) == 1
        assert read_notes(session, "p", True, "model") == []
        mutation = KnowledgeStore(session).query()
        body = request()
        body["passages"][0].update(
            attribution="user_view",
            dependencies=[{"type": "note", "id": note.id, "sha256": note.sha256}],
        )
        done = mutation.save_document(body, "note-doc")
        passage = session.get(QueryPassage, done["passage_ids"][0])
        second = request(title="Derived")
        second["passages"][0].update(
            attribution="user_view",
            dependencies=[{"type": "passage", "id": passage.id, "sha256": passage.sha256}],
        )
        mutation.save_document(second, "transitive")
        assert read_passages(session, "p") == []
        assert len(read_passages(session, "p", True)) == 2
        assert read_passages(session, "p", True, "model") == []
        mutation.set_note_grant("p", root.id, True, True)
        assert len(read_passages(session, "p", True, "model")) == 2
        original = path.read_bytes()
        mutation.set_note_grant("p", root.id, True, False)
        assert read_passages(session, "p", True, "model") == []
        assert len(read_passages(session, "p", True)) == 2
        root.active = False
        assert read_notes(session, "p", True) == []
        assert read_passages(session, "p", True) == []
        assert path.read_bytes() == original


def test_note_snapshot_bom_exact_bytes_restore_and_tampering(engine, tmp_path):
    with Session(engine) as session, session.begin():
        _, note, path = add_note(session, tmp_path)
        original = path.read_bytes()
        path.write_bytes(b"\xef\xbb\xbf" + original)
        note.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        dep = {"type": "note", "id": note.id, "sha256": note.sha256}
        assert validate_dependencies(session, "p", [dep], True)["content_state"] == "valid"
        assert read_notes(session, "p", True)[0]["id"] == note.id
        second = NoteSnapshot(
            id="new-note",
            root_id=note.root_id,
            relative_path=note.relative_path,
            sha256=hashlib.sha256(b"New note").hexdigest(),
            text="New note",
            created_at="zzz",
        )
        session.add(second)
        session.flush()
        assert read_notes(session, "p", True)[0]["id"] == note.id
        note.text = "In-place corrupted snapshot"
        assert read_notes(session, "p", True) == []
        assert validate_dependencies(session, "p", [dep], True)["content_state"] == "invalid"


def test_unaudited_personal_view_cannot_be_attributed_to_paper(engine, tmp_path):
    with Session(engine) as session, session.begin():
        _, note, _ = add_note(session, tmp_path)
        body = request()
        body["passages"][0]["dependencies"].append(
            {"type": "note", "id": note.id, "sha256": note.sha256}
        )
        with pytest.raises(KnowledgeError, match="归属"):
            KnowledgeStore(session).query().save_document(body, "bad-attribution")


def test_file_sync_and_content_are_independent_and_no_file_is_written(engine, tmp_path):
    with Session(engine) as session, session.begin():
        root, _, path = add_note(session, tmp_path)
        mutation = KnowledgeStore(session).query()
        done = mutation.save_document(request(), "file-doc")
        assert read_passages(session, "p")[0]["file_state"] == "not_exported"
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        mutation.register_file(done["document_id"], root.id, "note.md", done["version_id"], sha)
        assert read_passages(session, "p")[0]["file_state"] == "in_sync"
        path.write_text("User edits retain private original ownership.", encoding="utf-8")
        assert read_notes(session, "p", True) == []
        value = read_passages(session, "p")[0]
        assert value["file_state"] == "modified" and value["content_state"] == "valid"
        assert value["text"] == "The experiment uses 20 K."
        session.get(QueryFileBinding, done["document_id"]).conflict = True
        assert read_passages(session, "p")[0]["file_state"] == "conflict"
        session.get(QueryFileBinding, done["document_id"]).conflict = False
        path.unlink()
        value = read_passages(session, "p")[0]
        assert value["file_state"] == "missing" and value["content_state"] == "valid"
        assert not path.exists()
        for unsafe in ("../outside.md", "/outside.md", "..\\outside.md", "C:\\outside.md"):
            assert read_authorized_file(root, unsafe)[0] is None


def test_notes_authorize_scan_revoke_and_permissions_are_audit_only(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "personal.md").write_text("Private", encoding="utf-8")
    with client(tmp_path / "data") as api:
        project = post(api, "/projects", {"name": "Notes"}).json()["id"]
        root = post(
            api,
            "/integrations/obsidian/roots",
            {"project_id": project, "path": str(vault)},
            "authorize-root",
        ).json()["id"]
        post(api, f"/integrations/obsidian/{root}/scan", key="scan-notes")
        grant = api.put(
            f"/api/v1/integrations/obsidian/{root}/query-permissions",
            json={"allow_model": True},
            headers={"Idempotency-Key": "grant-model"},
        )
        assert grant.status_code == 200, grant.text
        assert grant.json()["allow_model"] is True
        post(api, f"/integrations/obsidian/{root}/revoke", key="revoke-notes")
        with Session(api.app.state.engine) as session:
            assert KnowledgeStore(session).graph_revision(project) == 0
            assert session.get(GraphRevision, project) is None
            notes = list(session.scalars(select(Event).where(Event.event_type.like("NOTE%"))))
            assert len(notes) == 4
            assert all(n.before_revision == n.after_revision == 0 for n in notes)
        post(
            api,
            "/integrations/obsidian/roots",
            {"project_id": project, "path": str(vault)},
            "reauthorize-read-only",
        )
        with Session(api.app.state.engine) as session:
            assert len(read_notes(session, project, True, "local")) == 1
            assert read_notes(session, project, True, "model") == []
            assert KnowledgeStore(session).graph_revision(project) == 0
