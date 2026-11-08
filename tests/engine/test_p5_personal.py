"""Explicit personal sources, purpose revocation and immutable references; synthetic data only."""

import hashlib
import json

import pytest
import test_knowledge
from pydantic import ValidationError
from researchgraph.knowledge_models import Annotation, NoteSnapshot, ZoteroLink
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, text_hash
from researchgraph.models import now
from researchgraph.p5_contracts import PersonalSources, WorkflowPrepare
from researchgraph.p5_models import P5ModelRun, P5Workflow
from researchgraph.p5_personal import annotation_source, personal_catalog, set_annotation_grant
from researchgraph.p5_personal_models import AnnotationHead
from researchgraph.p5_transport import validate_output
from researchgraph.p5_workflows import materialize, prepare, view
from researchgraph.query_context import validate_context
from researchgraph.query_documents import read_passages, validate_dependencies
from researchgraph.wiki_publish import WikiPublisher, _folder, authorize_root
from researchgraph.wiki_store import page_filename, read_page
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_lint import scan
from test_p5_workflows import Provider, dispatch, run
from test_query_answers import configure
from test_query_graph import production, second_paper
from test_query_retrieval import document, notes, request, science_rows

seeded = test_knowledge.seeded


@pytest.fixture
def personal(seeded, tmp_path):
    api, engine, eid = seeded
    production(engine, eid)
    configure(engine)
    root = notes(engine, tmp_path)
    private = "UNSELECTED-PRIVATE-CONTENT"
    (root / "second.md").write_text(private, encoding="utf-8")
    with Session(engine) as session, session.begin():
        session.add(
            NoteSnapshot(
                id="second-note",
                root_id="root",
                relative_path="second.md",
                sha256=text_hash(private),
                text=private,
                created_at=now(),
            )
        )
        KnowledgeStore(session).query().set_note_grant("project", "root", True, True)
        session.add(
            ZoteroLink(
                id="link",
                paper_id="paper",
                document_version_id="version",
                library_id="users/0",
                item_key="PAPER001",
                attachment_key="PDF00001",
                metadata_snapshot={},
            )
        )
        session.flush()
        session.add(
            Annotation(
                id="annotation",
                link_id="link",
                document_version_id="version",
                annotation_key="NOTE0001",
                annotation_type="note",
                text="Unresolved highlighted text",
                comment="My private question",
                source_position={},
                source_hash="d" * 64,
                anchor_status="unresolved",
                evidence_id=None,
                created_at=now(),
            )
        )
        session.flush()
        session.add(
            AnnotationHead(
                link_id="link",
                annotation_key="NOTE0001",
                annotation_id="annotation",
                removed=False,
                revision=1,
            )
        )
    return api, engine, root


def prepared_personal(engine, selection, *, key="personal-prepare", **changes):
    body = WorkflowPrepare(
        kind="wiki_synthesis",
        query=request(
            "Explicit sources", purpose="model", include_personal=True, source_kinds=["note"]
        ),
        personal_sources=selection,
        **changes,
    )
    with Session(engine) as session, session.begin():
        row = prepare(session, "project", body, key)
        return row.id


def grant(engine, *, allow_model=True, revision=0, allow_local=None):
    with Session(engine) as session, session.begin():
        return set_annotation_grant(
            KnowledgeStore(session),
            "project",
            "annotation",
            allow_model,
            revision,
            f"grant-{revision}",
            allow_local=allow_local,
        )


def test_explicit_selection_excludes_other_notes_and_nested_documents(personal):
    _, engine, _ = personal
    document(engine, "Private derived paragraph", personal=True)
    wid = prepared_personal(engine, {"note_ids": ["second-note"]})
    with Session(engine) as session:
        row = session.get(P5Workflow, wid)
        context = row.snapshot["context"]
        assert {r["id"] for r in context["references"]} == {"second-note"}
        assert "Private synthetic note" not in json.dumps(row.snapshot)
        assert "Private derived paragraph" not in json.dumps(row.snapshot)
        validate_context(
            session, context, row.snapshot["retrieval"], model_snapshot=row.snapshot["model"]
        )
    empty = prepared_personal(engine, {}, key="empty-personal")
    with Session(engine) as session:
        row = session.get(P5Workflow, empty)
        assert row.snapshot["context"]["references"] == []
        assert row.status == "insufficient"


def test_annotation_needs_separate_model_grant_and_never_invents_page(personal):
    api, engine, _ = personal
    with pytest.raises(KnowledgeError, match="用途授权"):
        prepared_personal(engine, {"annotation_ids": ["annotation"]})
    before = api.get("/api/v1/projects/project/p5/personal-sources").json()
    annotation = next(i for i in before["items"] if i["type"] == "annotation")
    assert not annotation["allow_model"] and "page_index" not in annotation
    assert annotation["text"] == "My private question" and annotation["highlight"]
    response = api.post(
        "/api/v1/projects/project/p5/annotations/annotation/grant",
        json={"allow_model": True, "expected_revision": 0},
        headers={"Idempotency-Key": "annotation-api-grant"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 1
    wid = prepared_personal(engine, {"annotation_ids": ["annotation"]})
    with Session(engine) as session:
        row = session.get(P5Workflow, wid)
        refs = row.snapshot["context"]["references"]
        assert len(refs) == 1 and refs[0]["type"] == "annotation"
        assert refs[0]["field"] == "comment" and "page_index" not in refs[0]
        assert "Unresolved highlighted text" not in json.dumps(row.snapshot)
        before_rows = science_rows(session)
    grant(engine, allow_model=False, revision=1)
    with Session(engine) as session:
        assert view(session, session.get(P5Workflow, wid))["status"] == "failed"
        assert science_rows(session) == before_rows


@pytest.mark.parametrize("mutation", ["comment", "head", "removed", "version", "permission"])
def test_selected_source_currentness_rechecked_without_rewriting_snapshots(personal, mutation):
    _, engine, _ = personal
    grant(engine)
    wid = prepared_personal(engine, {"annotation_ids": ["annotation"]})
    if mutation == "version":
        second_paper(engine)
    with Session(engine) as session, session.begin():
        if mutation == "comment":
            session.get(Annotation, "annotation").comment += " changed"
        elif mutation == "head":
            session.get(AnnotationHead, ("link", "NOTE0001")).revision += 1
        elif mutation == "removed":
            session.get(AnnotationHead, ("link", "NOTE0001")).removed = True
        elif mutation == "version":
            session.get(ZoteroLink, "link").document_version_id = "version2"
        else:
            from researchgraph.p5_personal_models import AnnotationUseGrant

            session.get(AnnotationUseGrant, "annotation").allow_model = False
    with Session(engine) as session:
        assert view(session, session.get(P5Workflow, wid))["status"] == "failed"


class CommentProvider(Provider):
    async def complete(self, prompt, data, schema):
        self.calls += 1
        source = next(
            r for r in data["evidence_context"]["references"] if r["type"] == "annotation"
        )
        return json.dumps(
            {
                "title": "User question",
                "passages": [
                    {
                        "heading": "Comment",
                        "text": "My question needs further investigation.",
                        "attribution": "user_view",
                        "source_refs": [source["ref"]],
                        "limitations": [],
                        "conditions": [],
                    }
                ],
                "coverage_gaps": [],
            }
        )


def test_comment_only_generate_save_publish_then_local_revoke_blocks_all_read_paths(
    personal, tmp_path
):
    api, engine, _ = personal
    grant(engine)
    wid = prepared_personal(engine, {"annotation_ids": ["annotation"]})
    provider = CommentProvider(engine)
    run(engine, dispatch(engine, wid), provider)
    with Session(engine) as session, session.begin():
        row = session.get(P5Workflow, wid)
        assert view(session, row)["status"] == "succeeded"
        raw = session.scalar(select(P5ModelRun)).raw_output
        draft = materialize(KnowledgeStore(session), "project", wid, "personal-materialize")
    saved = api.post(
        f"/api/v1/projects/project/wiki/pages/{draft['page_id']}/save",
        json={
            "version_id": draft["version_id"],
            "expected_head_version_id": draft["version_id"],
            "expected_content_hash": draft["content_hash"],
        },
        headers={"Idempotency-Key": "save-comment"},
    )
    assert saved.status_code == 200, saved.text
    saved = saved.json()
    folder = tmp_path / "output"
    folder.mkdir()
    with Session(engine) as session, session.begin():
        output_root = authorize_root(KnowledgeStore(session), "project", str(folder))
        page = read_page(session, "project", draft["page_id"])
        before = science_rows(session)
    command = {
        "root_id": output_root["root_id"],
        "version_id": saved["version_id"],
        "expected_content_hash": page["content_hash"],
        "expected_target_hash": None,
    }
    target = folder / _folder("project") / page_filename(draft["page_id"])
    published = WikiPublisher(engine).publish(
        "project", draft["page_id"], command, "publish-comment"
    )
    assert published["state"] == "succeeded", published
    assert target.exists()
    grant(engine, revision=1, allow_local=False)
    original_annotations = api.get("/api/v1/revisions/version/annotations")
    assert original_annotations.status_code == 200
    assert "My private question" not in original_annotations.text
    assert "Unresolved highlighted text" not in original_annotations.text
    with Session(engine) as session:
        assert read_passages(session, "project", True) == []
        page = read_page(session, "project", draft["page_id"])
        assert "My question" not in page["markdown"] and all(
            not s["text"] for s in page["sections"]
        )
        workflow = view(session, session.get(P5Workflow, wid))
        assert workflow["result"] is None and workflow["status"] == "failed"
        assert session.scalar(select(P5ModelRun)).raw_output == raw
        assert science_rows(session) == before
        catalog = personal_catalog(session, "project")
        redacted = next(i for i in catalog["items"] if i["id"] == "annotation")
        assert redacted["redacted"] and not redacted.get("text") and not redacted.get("highlight")
    command["expected_target_hash"] = hashlib.sha256(target.read_bytes()).hexdigest()
    with pytest.raises(KnowledgeError):
        WikiPublisher(engine).publish("project", draft["page_id"], command, "after-revoke")
    assert (
        WikiPublisher(engine).recover("project", published["operation_id"])["state"] != "succeeded"
    )
    assert provider.calls == 1
    grant(engine, revision=2, allow_local=True)
    assert "My private question" in api.get("/api/v1/revisions/version/annotations").text
    with Session(engine) as session:
        assert read_passages(session, "project", True)


def test_comment_cannot_be_saved_as_paper_claim_or_ai_scientific_synthesis(personal):
    _, engine, _ = personal
    with Session(engine) as session:
        source = annotation_source(session, "project", "annotation")
    for attribution in ("paper_author", "citation_report", "model_synthesis"):
        with Session(engine) as session, session.begin(), pytest.raises(KnowledgeError):
            KnowledgeStore(session).query().save_document(
                {
                    "project_id": "project",
                    "kind": "wiki",
                    "title": "Invalid attribution",
                    "passages": [
                        {
                            "local_ref": "x",
                            "text": "Claim",
                            "attribution": attribution,
                            "dependencies": [
                                {
                                    "type": "annotation",
                                    "id": "annotation",
                                    "sha256": source["sha256"],
                                }
                            ],
                        }
                    ],
                },
                "invalid-" + attribution,
            )
    with Session(engine) as session:
        checked = validate_dependencies(
            session,
            "project",
            [{"type": "annotation", "id": "annotation", "sha256": source["sha256"]}],
            True,
        )
        assert (
            checked["content_state"] == "valid"
            and checked["roots"][0]["source_kind"] == "annotation"
        )


def test_semantic_lint_only_transmits_explicitly_selected_personal_issues(personal):
    _, engine, _ = personal
    report = scan(engine, project_id="project", include_personal=True)
    assert report["status"] == "completed"
    with Session(engine) as session, session.begin():
        row = prepare(
            session,
            "project",
            WorkflowPrepare(
                kind="lint_semantic",
                query=request("Check", purpose="model", include_personal=True),
                lint_run_id=report["id"],
                personal_sources=PersonalSources(note_ids=["note"]),
            ),
            "semantic-selected-note",
        )
        wire = row.snapshot["lint"]
        assert any(i["object_type"] == "note" for i in wire["issues"])
        assert "second-note" not in json.dumps(wire)
        assert "second.md" not in json.dumps(wire) and "annotation" not in json.dumps(wire)


def test_new_selection_is_optional_for_history_and_does_not_change_p4_request_shape():
    body = WorkflowPrepare(kind="wiki_synthesis", query=request(purpose="model"))
    assert "personal_sources" not in body.model_dump(mode="json")
    assert "personal_sources" not in body.query.model_dump(mode="json")
    with pytest.raises(ValidationError):
        WorkflowPrepare(
            kind="wiki_synthesis",
            query=request(purpose="model"),
            personal_sources={"annotation_ids": ["a"]},
        )
    with pytest.raises(ValidationError):
        PersonalSources(note_ids=["a", "a"])


def test_new_personal_prepare_cannot_omit_explicit_selection(personal):
    _, engine, _ = personal
    with (
        Session(engine) as session,
        session.begin(),
        pytest.raises(KnowledgeError, match="逐份选择"),
    ):
        prepare(
            session,
            "project",
            WorkflowPrepare(
                kind="wiki_synthesis", query=request(purpose="model", include_personal=True)
            ),
            "must-explicitly-select",
        )


@pytest.mark.parametrize(
    "origin,allowed", [("user_view", "user_view"), ("external_source", "model_synthesis")]
)
def test_external_source_origin_is_preserved_and_never_promoted_to_paper(personal, origin, allowed):
    from researchgraph.external_documents import ExternalDocumentMutations

    _, engine, root = personal
    content = "A separately registered outside document."
    (root / "external.md").write_text(content, encoding="utf-8")
    with Session(engine) as session, session.begin():
        external = ExternalDocumentMutations(KnowledgeStore(session)).register(
            "project",
            {
                "root_id": "root",
                "relative_path": "external.md",
                "expected_sha256": text_hash(content),
                "title": "External original",
                "attribution": origin,
            },
            "external-personal-register",
            include_personal=True,
        )
    wid = prepared_personal(engine, {"external_version_ids": [external["version_id"]]})
    with Session(engine) as session, session.begin():
        workflow = session.get(P5Workflow, wid)
        reference = next(
            r for r in workflow.snapshot["context"]["references"] if r["type"] == "external"
        )
        assert reference["attribution"] == reference["source_attribution"] == origin
        assert not reference["source_verified"] and reference["content_state"] == "unverified"
        for attribution in ("paper_author", "citation_report", "user_view", "model_synthesis"):
            raw = json.dumps(
                {
                    "title": "External synthesis",
                    "passages": [
                        {
                            "heading": "Reading",
                            "text": "This source requires separate scientific verification.",
                            "attribution": attribution,
                            "source_refs": [reference["ref"]],
                            "limitations": [],
                            "conditions": [],
                        }
                    ],
                    "coverage_gaps": [],
                }
            )
            if attribution != allowed:
                with pytest.raises(KnowledgeError):
                    validate_output(session, workflow, "synthetic-run", raw)
                continue
            result = validate_output(session, workflow, "synthetic-run", raw)
            passage = result["draft"]["passages"][0]
            assert passage["attribution"] == allowed and passage["caveats"]
            assert passage["dependencies"] == [
                {"type": "external", "id": external["version_id"], "sha256": text_hash(content)}
            ]
            KnowledgeStore(session).query().save_document(
                {
                    "project_id": "project",
                    "title": "Copy",
                    "passages": [
                        {
                            "local_ref": "one",
                            "text": passage["text"],
                            "attribution": allowed,
                            "dependencies": passage["dependencies"],
                        }
                    ],
                },
                "copy-external",
            )


def test_annotation_grant_cas_idempotency_and_local_regrant_has_no_hidden_text(personal):
    api, engine, _ = personal
    first = grant(engine, allow_model=True, allow_local=False)
    assert first["allow_model"] and not first["allow_local"]
    with Session(engine) as session:
        with pytest.raises(KnowledgeError):
            annotation_source(session, "project", "annotation", purpose="local")
        assert annotation_source(session, "project", "annotation", purpose="model")["text"]
        assert not next(
            i for i in personal_catalog(session, "project")["items"] if i["type"] == "annotation"
        ).get("text")
    response = api.post(
        "/api/v1/projects/project/p5/annotations/annotation/grant",
        json={"allow_model": True, "allow_local": True, "expected_revision": 0},
        headers={"Idempotency-Key": "stale-grant-revision"},
    )
    assert response.status_code == 409
    second = grant(engine, allow_model=False, revision=1)
    assert not second["allow_local"]  # Model toggle must not silently restore local access.
    restored = grant(engine, allow_model=False, allow_local=True, revision=2)
    assert restored["allow_local"] and not restored["allow_model"]


def _private_delta_baseline(engine, secret):
    with Session(engine) as session, session.begin():
        note = session.get(NoteSnapshot, "note")
        result = (
            KnowledgeStore(session)
            .wiki()
            .create_draft(
                "project",
                {
                    "title": "Private baseline",
                    "passages": [
                        {
                            "heading": "Personal context",
                            "text": secret,
                            "attribution": "user_view",
                            "dependencies": [
                                {"type": "note", "id": note.id, "sha256": note.sha256}
                            ],
                            "conditions": [],
                            "caveats": [],
                            "links": [],
                        }
                    ],
                },
                "private-delta-baseline",
            )
        )
        return read_page(session, "project", result["page_id"], include_personal=True)


def _legacy_delta_snapshot(engine, baseline):
    """Freeze a genuine historical no-selection envelope without invoking the new prepare gate."""
    import math

    from researchgraph.knowledge_store import digest
    from researchgraph.model_settings import snapshot_for
    from researchgraph.p5_sources import collect_scope, selection_map
    from researchgraph.p5_transport import load_prompt, make_wire, output_schema
    from researchgraph.p5_workflows import _base
    from researchgraph.query_context import build_context

    body = WorkflowPrepare(
        kind="wiki_delta",
        query=request(
            "Legacy update", purpose="model", include_personal=True, source_kinds=["chunk"]
        ),
        page_id=baseline["page_id"],
        base_version_id=baseline["version_id"],
        affected_section_ids=[baseline["sections"][0]["section_id"]],
    )
    with Session(engine) as session, session.begin():
        model = snapshot_for(session, "project", "reasoning")
        found = collect_scope(session, "project", body.query, exclude_document_id=body.page_id)
        context = build_context(
            session,
            body.query.model_dump(mode="json"),
            found,
            model_snapshot=model,
            include_layout=True,
            include_scientific_guidance=True,
        )
        base, targets = _base(session, "project", body)
        wire = make_wire(body.kind, context, base, targets, None)
        prompt = load_prompt(body.kind)
        snapshot = {
            "request": body.model_dump(mode="json"),
            "retrieval": found,
            "context": context,
            "model": model,
            "base": base,
            "targets": targets,
            "lint": None,
            "source_revisions": selection_map(session, context),
            "schema_hash": digest(output_schema(body.kind, context, list(targets))),
            "wire_hash": digest(wire),
            "prompt_hash": text_hash(prompt),
            "estimated_input_tokens": math.ceil(
                (len(str(wire).encode()) + len(prompt.encode())) / 3
            ),
            "complete_context_sufficient": True,
        }
        assert "personal_sources" not in snapshot["request"]
        assert "p5_personal_sources" not in context and "personal_source_snapshots" not in context
        row = P5Workflow(
            id="legacy-private-delta",
            project_id="project",
            kind=body.kind,
            request=body.model_dump(mode="json"),
            snapshot=snapshot,
            input_hash=digest(snapshot),
            status="prepared",
            created_at=now(),
            updated_at=now(),
        )
        session.add(row)
        return row.id


def test_legacy_delta_get_revalidates_local_permission_of_baseline_outside_context(personal):
    api, engine, _ = personal
    secret = "PRIVATE-LEGACY-BASE-ONLY"
    baseline = _private_delta_baseline(engine, secret)
    wid = _legacy_delta_snapshot(engine, baseline)

    def output(data, _passage):
        return json.dumps(
            {
                "edits": [
                    {
                        "op": "mark_stale",
                        "section_ref": "T00001",
                        "reason": data["affected_sections"][0]["text"],
                    }
                ],
                "coverage_gaps": [],
            }
        )

    provider = Provider(engine, output=output)
    run(engine, dispatch(engine, wid), provider)
    with Session(engine) as session:
        row = session.get(P5Workflow, wid)
        assert view(session, row)["status"] == "succeeded"
        assert secret not in json.dumps(row.snapshot["context"]["references"])
        old_snapshot, old_hash = json.dumps(row.snapshot, sort_keys=True), row.input_hash
        raw = session.scalar(select(P5ModelRun).where(P5ModelRun.workflow_id == wid)).raw_output
    with Session(engine) as session, session.begin():
        KnowledgeStore(session).query().set_note_grant("project", "root", False, True)
    response = api.get(f"/api/v1/projects/project/workflows/{wid}")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "failed" and response.json()["result"] is None
    assert secret not in response.text
    with Session(engine) as session:
        row = session.get(P5Workflow, wid)
        assert (
            row.input_hash == old_hash and json.dumps(row.snapshot, sort_keys=True) == old_snapshot
        )
        assert (
            session.scalar(select(P5ModelRun).where(P5ModelRun.workflow_id == wid)).raw_output
            == raw
        )
    assert provider.calls == 1


def test_unselected_invalid_personal_delta_baseline_never_enters_model_wire(personal):
    _, engine, _ = personal
    baseline = _private_delta_baseline(engine, "UNSELECTED-INVALID-PRIVATE-BASE")
    with Session(engine) as session, session.begin():
        session.get(NoteSnapshot, "note").text += " changed immutable snapshot"
    with Session(engine) as session, session.begin(), pytest.raises(KnowledgeError):
        prepare(
            session,
            "project",
            WorkflowPrepare(
                kind="wiki_delta",
                query=request(
                    "Update", purpose="model", include_personal=True, source_kinds=["chunk"]
                ),
                personal_sources={},
                page_id=baseline["page_id"],
                base_version_id=baseline["version_id"],
                affected_section_ids=[baseline["sections"][0]["section_id"]],
            ),
            "empty-selected-invalid-baseline",
        )


def _saved_personal_wiki(engine, source_kind, root):
    from researchgraph.external_documents import ExternalDocumentMutations

    with Session(engine) as session, session.begin():
        if source_kind == "annotation":
            source = annotation_source(session, "project", "annotation")
            attribution = "user_view"
        else:
            content = "EXTERNAL-ROOT-COMPAT-SECRET"
            (root / "compat.md").write_text(content, encoding="utf-8")
            source = ExternalDocumentMutations(KnowledgeStore(session)).register(
                "project",
                {
                    "root_id": "root",
                    "relative_path": "compat.md",
                    "expected_sha256": text_hash(content),
                    "title": "Independent compatibility source",
                    "attribution": source_kind,
                },
                "external-compat-register",
                include_personal=True,
            )
            source = {**source, "type": "external", "id": source["version_id"]}
            attribution = "user_view" if source_kind == "user_view" else "model_synthesis"
        dependency = {"type": source["type"], "id": source["id"], "sha256": source["sha256"]}
        draft = (
            KnowledgeStore(session)
            .wiki()
            .create_draft(
                "project",
                {
                    "title": "Compatibility Wiki",
                    "passages": [
                        {
                            "heading": "Explicit source",
                            "text": "compatibility summary PRIVATE-COMPAT-WIKI",
                            "attribution": attribution,
                            "dependencies": [dependency],
                            "conditions": [],
                            "caveats": [],
                            "links": [],
                        }
                    ],
                },
                "personal-compat-wiki",
            )
        )
        saved = (
            KnowledgeStore(session)
            .wiki()
            .save_draft(
                "project",
                draft["page_id"],
                {
                    "version_id": draft["version_id"],
                    "expected_head_version_id": draft["version_id"],
                    "expected_content_hash": draft["content_hash"],
                },
                "save-personal-compat-wiki",
            )
        )
        return source, saved


@pytest.mark.parametrize("source_kind", ["annotation", "user_view", "external_source"])
def test_ordinary_query_reads_saved_personal_wiki_with_typed_roots_and_separate_grants(
    personal, source_kind
):
    from researchgraph.query_answer_wire import bind_answer

    api, engine, root = personal
    if source_kind == "annotation":
        grant(engine)
    source, saved = _saved_personal_wiki(engine, source_kind, root)
    endpoint = "/api/v1/projects/project/query/prepare"
    body = request("compatibility", purpose="model", include_personal=True, source_kinds=["wiki"])
    assert "personal_sources" not in body
    prepared_response = api.post(
        endpoint, json=body, headers={"Idempotency-Key": "query-compat-first"}
    )
    assert prepared_response.status_code == 200, prepared_response.text
    prepared = prepared_response.json()
    assert prepared["status"] == "prepared"
    context = prepared["snapshot"]["context"]
    source_type = "annotation" if source_kind == "annotation" else "external"
    assert any(r["type"] == source_type and r["id"] == source["id"] for r in context["references"])
    assert "p5_personal_sources" not in context
    passage = next(r for r in context["references"] if r["type"] == "passage")
    expected_attribution = "model_synthesis" if source_kind == "external_source" else "user_view"
    raw = json.dumps(
        {
            "passages": [
                {
                    "text": "Compatibility answer.",
                    "attribution": expected_attribution,
                    "source_refs": [passage["ref"]],
                    "limitations": [],
                }
            ],
            "limitations": [],
        }
    )
    assert bind_answer(raw, context, query_id="q", answer_id="a", revision=1).passages
    for wrong_attribution in ("paper_author", "citation_report"):
        with pytest.raises(KnowledgeError):
            bind_answer(
                raw.replace(expected_attribution, wrong_attribution),
                context,
                query_id="q",
                answer_id="a",
                revision=1,
            )
    default = api.get("/api/v1/projects/project/query/documents")
    assert "PRIVATE-COMPAT-WIKI" not in default.text
    no_personal = api.post(
        endpoint,
        json={**body, "include_personal": False},
        headers={"Idempotency-Key": "query-compat-default"},
    )
    assert no_personal.status_code == 200
    assert no_personal.json()["status"] == "insufficient"
    assert "PRIVATE-COMPAT-WIKI" not in no_personal.text
    with Session(engine) as session, session.begin():
        if source_kind == "annotation":
            set_annotation_grant(
                KnowledgeStore(session), "project", "annotation", False, 1, "model-revoke-compat"
            )
        else:
            KnowledgeStore(session).query().set_note_grant("project", "root", True, False)
    blocked = api.get(f"/api/v1/projects/project/query/runs/{prepared['query_id']}")
    assert blocked.status_code != 200
    assert "PRIVATE-COMPAT-WIKI" not in blocked.text
    local_docs = api.get("/api/v1/projects/project/query/documents?include_personal=true")
    assert "PRIVATE-COMPAT-WIKI" in local_docs.text
    assert saved["page_id"] in local_docs.text


@pytest.mark.parametrize("source_kind", ["annotation", "external_source"])
def test_query_model_permission_never_returns_local_revoked_wiki_snapshot(personal, source_kind):
    api, engine, root = personal
    if source_kind == "annotation":
        grant(engine)
    _saved_personal_wiki(engine, source_kind, root)
    with Session(engine) as session, session.begin():
        if source_kind == "annotation":
            set_annotation_grant(
                KnowledgeStore(session),
                "project",
                "annotation",
                True,
                1,
                "local-revoke-compat",
                allow_local=False,
            )
        else:
            KnowledgeStore(session).query().set_note_grant("project", "root", False, True)
    # A user-facing prepare/GET response is a local read even when preparing model input.
    response = api.post(
        "/api/v1/projects/project/query/prepare",
        json=request(
            "compatibility", purpose="model", include_personal=True, source_kinds=["wiki"]
        ),
        headers={"Idempotency-Key": "local-revoked-query-prepare"},
    )
    assert "PRIVATE-COMPAT-WIKI" not in response.text
    if response.status_code == 200:
        queried = api.get(f"/api/v1/projects/project/query/runs/{response.json()['query_id']}")
        assert "PRIVATE-COMPAT-WIKI" not in queried.text


def test_explicit_annotation_import_updates_heads_and_tombstones_without_changing_old_comments(
    personal, tmp_path
):
    from researchgraph.integrations import AnnotationImporter
    from researchgraph.models import AttachmentRevision, PaperSource

    _, engine, _ = personal
    source = tmp_path / "authorized-synthetic.pdf"
    source.write_bytes(b"synthetic source bytes; no parser or model")
    with Session(engine) as session, session.begin():
        session.get(AttachmentRevision, "version").sha256 = hashlib.sha256(
            source.read_bytes()
        ).hexdigest()
        session.add(
            PaperSource(
                id="source",
                paper_id="paper",
                revision_id="version",
                path=str(source),
                mode="reference",
                generation=0,
            )
        )
    payload = [
        {
            "key": "NOTE0001",
            "data": {
                "parentItem": "PDF00001",
                "annotationText": "unresolved",
                "annotationComment": "Changed comment",
                "annotationPosition": "{}",
                "annotationType": "note",
            },
        }
    ]
    with Session(engine) as session, session.begin():
        store = KnowledgeStore(session)
        importer = AnnotationImporter(store)
        assert (
            importer.apply("version", "users/0", "PAPER001", "PDF00001", {}, payload, source)[
                "added"
            ]
            == 1
        )
        session.flush()
        head = session.get(AnnotationHead, ("link", "NOTE0001"))
        current_id, revision = head.annotation_id, head.revision
        assert (
            current_id != "annotation"
            and session.get(Annotation, "annotation").comment == "My private question"
        )
        assert (
            importer.apply("version", "users/0", "PAPER001", "PDF00001", {}, payload, source)[
                "added"
            ]
            == 0
        )
        assert head.revision == revision
        with pytest.raises(KnowledgeError):
            annotation_source(session, "project", current_id, purpose="model")
        importer.apply("version", "users/0", "PAPER001", "PDF00001", {}, [], source)
        assert head.removed and head.revision == revision + 1
        assert session.get(Annotation, current_id).comment == "Changed comment"
        with pytest.raises(KnowledgeError):
            annotation_source(session, "project", current_id)


def test_annotation_reverse_dependencies_track_permission_and_source_changes(personal):
    from researchgraph.lint_service import dependencies, rebuild_dependencies

    _, engine, _ = personal
    with Session(engine) as session, session.begin():
        source = annotation_source(session, "project", "annotation")
        saved = (
            KnowledgeStore(session)
            .query()
            .save_document(
                {
                    "project_id": "project",
                    "title": "Personal comment copy",
                    "passages": [
                        {
                            "local_ref": "one",
                            "text": "Interpretation",
                            "attribution": "user_view",
                            "dependencies": [
                                {
                                    "type": "annotation",
                                    "id": "annotation",
                                    "sha256": source["sha256"],
                                }
                            ],
                        }
                    ],
                },
                "annotation-dependent",
            )
        )
        rebuild_dependencies(KnowledgeStore(session), "project", include_personal=True)
        affected = dependencies(
            session, "project", object_type="annotation", object_id="annotation"
        )
        assert any(r["dependent_type"] == "passage" for r in affected["items"])
        assert any(r["dependent_id"] == saved["document_id"] for r in affected["items"])
    grant(engine, allow_model=False, allow_local=False)
    with Session(engine) as session:
        assert (
            dependencies(session, "project", object_type="annotation", object_id="annotation")[
                "items"
            ]
            == []
        )
