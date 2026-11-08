"""Synthetic Wiki versions, exact immutable copies, provenance and authorization boundaries."""

import copy

import pytest
from pydantic import ValidationError
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, text_hash
from researchgraph.query_documents import read_passages, validate_dependencies
from researchgraph.query_models import (
    QueryDocument,
    QueryDocumentVersion,
    QueryOperation,
    QueryPassage,
)
from researchgraph.wiki_contracts import WikiDraftInput, WikiPatchInput
from researchgraph.wiki_models import WikiPage, WikiSection, WikiVersion
from researchgraph.wiki_store import WikiMutations, read_page, wiki_version_state
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_query_documents import add_note, dependency
from test_query_documents import engine as engine


def passage(text="A method at 20 K.", **extra):
    return {
        "heading": "Methods",
        "text": text,
        "attribution": "paper_author",
        "dependencies": [dependency()],
        "caveats": [],
        "conditions": [{"dimension": "temperature", "state": "known", "value": "20", "unit": "K"}],
        "links": [],
        **extra,
    }


def draft(engine, passages=None):
    with Session(engine) as session, session.begin():
        result = WikiMutations(KnowledgeStore(session)).create_draft(
            "p",
            {"title": "Synthetic Wiki", "passages": passages or [passage(), passage("A limit.")]},
            "create-draft-1",
        )
        return read_page(session, "p", result["page_id"])


def save(engine, view):
    with Session(engine) as session, session.begin():
        result = WikiMutations(KnowledgeStore(session)).save_draft(
            "p",
            view["page_id"],
            {
                "version_id": view["version_id"],
                "expected_head_version_id": view["head_version_id"],
                "expected_content_hash": view["content_hash"],
            },
            "save-" + view["version_id"],
        )
        return read_page(session, "p", result["page_id"])


def patch(engine, view, operations, key="patch-1"):
    with Session(engine) as session, session.begin():
        result = WikiMutations(KnowledgeStore(session)).apply_patch(
            "p",
            view["page_id"],
            {
                "base_version_id": view["version_id"],
                "base_content_hash": view["content_hash"],
                "operations": operations,
            },
            key,
        )
        return read_page(session, "p", result["page_id"])


def test_draft_saved_versions_share_registry_without_republishing_or_graph_mutation(
    engine, tmp_path
):
    from researchgraph.knowledge_models import GraphRevision

    view = draft(engine)
    assert view["state"] == "draft" and view["saved_version_id"] is None
    assert view["file_state"] == "not_exported"
    with Session(engine) as session:
        assert read_passages(session, "p") == []
        assert list(session.scalars(select(GraphRevision))) == []
    saved = save(engine, view)
    assert saved["state"] == "saved"
    assert saved["version_id"] != view["version_id"]
    assert saved["markdown"] == view["markdown"]
    assert saved["content_hash"] == view["content_hash"]
    assert [s["section_id"] for s in saved["sections"]] == [
        s["section_id"] for s in view["sections"]
    ]
    with Session(engine) as session:
        assert len(read_passages(session, "p")) == 2
        assert list(session.scalars(select(GraphRevision))) == []
        assert session.get(QueryDocument, view["page_id"]).current_version_id == saved["version_id"]
        assert session.get(QueryDocumentVersion, view["version_id"]).state == "draft"
    assert not list(tmp_path.rglob("*.md"))


def test_render_is_deterministic_and_escapes_model_html_urls_and_preserves_math(engine):
    view = draft(
        engine,
        [passage("<script>alert(1)</script> [bad](javascript:evil) ![img](file:///x) α² + β = 3")],
    )
    markdown = view["markdown"]
    assert "<script>" not in markdown
    assert "&lt;script&gt;" in markdown
    assert "[bad](javascript:evil)" not in markdown
    assert "![img](file:///x)" not in markdown
    assert "α² + β = 3" in markdown
    assert "| temperature | known | 20 | K |" in markdown
    with Session(engine) as session:
        again = read_page(session, "p", view["page_id"])
        assert again["markdown"] == markdown
        assert again["content_hash"] == view["content_hash"]


def test_partial_patch_preserves_other_sections_bytes_and_cas(engine):
    view = save(engine, draft(engine))
    original = copy.deepcopy(view["sections"][1])
    changed = patch(
        engine,
        view,
        [
            {
                "op": "replace",
                "section_id": view["sections"][0]["section_id"],
                "passage": passage("A changed interpretation."),
            }
        ],
    )
    assert changed["state"] == "draft"
    assert changed["saved_version_id"] == view["version_id"]
    for field in (
        "section_id",
        "text",
        "dependencies",
        "attribution",
        "caveats",
        "heading",
        "conditions",
        "links",
    ):
        assert changed["sections"][1][field] == original[field]
    assert "A changed interpretation." in changed["diff"]
    with pytest.raises(KnowledgeError, match="基线"):
        patch(
            engine,
            view,
            [{"op": "mark_stale", "section_id": original["section_id"], "reason": "Changed"}],
            key="stale-baseline",
        )
    with Session(engine) as session:
        old = read_page(session, "p", view["page_id"], view["version_id"])
        assert old["markdown"] == view["markdown"]


def test_mark_stale_is_only_metadata_and_cannot_reenter_query_via_passage(engine):
    view = save(engine, draft(engine))
    changed = patch(
        engine,
        view,
        [
            {
                "op": "mark_stale",
                "section_id": view["sections"][0]["section_id"],
                "reason": "Source needs updating",
            }
        ],
    )
    assert changed["sections"][0]["text"] == view["sections"][0]["text"]
    assert changed["sections"][0]["dependencies"] == view["sections"][0]["dependencies"]
    assert changed["sections"][0]["content_state"] == "stale"
    with pytest.raises(KnowledgeError, match="过期"):
        save(engine, changed)
    # A corrupt/legacy caller cannot launder a stale marked saved paragraph through another doc.
    with Session(engine) as session, session.begin():
        version = session.get(QueryDocumentVersion, changed["version_id"])
        version.state = "saved"
        session.get(QueryDocument, view["page_id"]).current_version_id = version.id
        pid = changed["sections"][0]["passage_id"]
        checked = validate_dependencies(
            session,
            "p",
            [{"type": "passage", "id": pid, "sha256": text_hash(changed["sections"][0]["text"])}],
        )
        assert checked["content_state"] == "stale"
        assert "WIKI_SECTION_MARKED_STALE" in checked["issues"]
        found = read_passages(session, "p")
        assert found[0]["text"] == "" and found[0]["content_state"] == "stale"


def test_preserve_invalid_old_source_only_unchanged_draft_not_new_scientific_content(engine):
    from researchgraph.models import Chunk

    view = save(engine, draft(engine))
    with Session(engine) as session, session.begin():
        session.get(Chunk, "c").text = "Changed source."
    # Explicit marking preserves the exact previous paragraph, never refreshes its old hash.
    changed = patch(
        engine,
        view,
        [
            {
                "op": "mark_stale",
                "section_id": view["sections"][0]["section_id"],
                "reason": "Source changed",
            }
        ],
    )
    assert changed["content_state"] == "invalid"
    assert changed["sections"][0]["text"] == ""
    with Session(engine) as session:
        raw = session.get(QueryPassage, changed["sections"][0]["passage_id"])
        assert raw.text == view["sections"][0]["text"]
    with pytest.raises(KnowledgeError) as caught:
        patch(
            engine,
            changed,
            [
                {
                    "op": "replace",
                    "section_id": changed["sections"][1]["section_id"],
                    "passage": passage("New unsupported text."),
                }
            ],
            key="invalid-new",
        )
    assert caught.value.code == "DOCUMENT_DEPENDENCY_INVALID"


def test_revoke_note_cannot_leak_body_heading_conditions_markdown_or_old_diff(engine, tmp_path):
    with Session(engine) as session, session.begin():
        root, note, _ = add_note(session, tmp_path)
        root_id, note_id, sha = root.id, note.id, note.sha256
    note_passage = passage(
        "Private phrase",
        heading="Private heading",
        attribution="user_view",
        dependencies=[{"type": "note", "id": note_id, "sha256": sha}],
        caveats=["Private caveat"],
        conditions=[
            {"dimension": "Private condition", "state": "known", "value": "secret", "unit": None}
        ],
    )
    view = draft(engine, [note_passage])
    assert "Private phrase" not in view["markdown"]  # defaults do not opt in personal materials
    with Session(engine) as session:
        allowed = read_page(session, "p", view["page_id"], include_personal=True)
        assert allowed["sections"][0]["text"] == "Private phrase"
    with Session(engine) as session, session.begin():
        from researchgraph.knowledge_models import AuthorizedRoot

        session.get(AuthorizedRoot, root_id).active = False
    with Session(engine) as session:
        blocked = read_page(session, "p", view["page_id"], include_personal=True)
        assert "Private" not in blocked["markdown"]
        assert blocked["diff"] == ""
        assert blocked["sections"][0]["text"] == ""
        assert blocked["sections"][0]["heading"] == ""
        assert blocked["sections"][0]["caveats"] == []
        assert blocked["sections"][0]["conditions"] == []


@pytest.mark.parametrize(
    "operation",
    [
        {"op": "replace", "section_id": "outside", "passage": passage()},
        {"op": "append", "after_section_id": "outside", "passage": passage()},
        {"op": "mark_stale", "section_id": "outside", "reason": "bad"},
    ],
)
def test_patch_cannot_reference_other_page_sections(engine, operation):
    view = draft(engine)
    with pytest.raises(KnowledgeError, match="段落"):
        patch(engine, view, [operation])


def test_contract_does_not_accept_paths_or_silent_unknown_fields():
    with pytest.raises(ValidationError):
        WikiDraftInput.model_validate(
            {"title": "Page", "passages": [passage()], "path": "private.md"}
        )
    with pytest.raises(ValidationError):
        WikiPatchInput.model_validate(
            {
                "base_version_id": "v",
                "base_content_hash": "a" * 64,
                "operations": [{"op": "delete", "section_id": "s"}],
            }
        )


def test_draft_and_save_idempotency_and_cross_project_scope(engine):
    view = draft(engine)
    with Session(engine) as session, session.begin():
        repeat = WikiMutations(KnowledgeStore(session)).create_draft(
            "p",
            {"title": "Synthetic Wiki", "passages": [passage(), passage("A limit.")]},
            "create-draft-1",
        )
        assert repeat["version_id"] == view["version_id"]
        assert len(list(session.scalars(select(WikiPage)))) == 1
        with pytest.raises(KnowledgeError):
            read_page(session, "other", view["page_id"])
    saved = save(engine, view)
    with Session(engine) as session:
        assert len(list(session.scalars(select(WikiSection)))) == 4
    with Session(engine) as session, session.begin():
        repeat = WikiMutations(KnowledgeStore(session)).save_draft(
            "p",
            view["page_id"],
            {
                "version_id": view["version_id"],
                "expected_head_version_id": view["head_version_id"],
                "expected_content_hash": view["content_hash"],
            },
            "save-" + view["version_id"],
        )
        assert repeat["version_id"] == saved["version_id"]


def _damage_snapshot(engine, view, damage):
    with Session(engine) as session, session.begin():
        paragraph = session.get(QueryPassage, view["sections"][-1]["passage_id"])
        if damage == "body":
            paragraph.text = "Corrupt unsupported replacement."
        elif damage == "caveat":
            paragraph.caveats = ["Corrupt unsupported limitation."]
        else:
            session.delete(session.get(WikiSection, paragraph.id))


def _page_persistence(engine, page_id):
    with Session(engine) as session:
        return {
            "saved": session.get(QueryDocument, page_id).current_version_id,
            "head": session.get(WikiPage, page_id).head_version_id,
            "versions": sorted(session.scalars(select(QueryDocumentVersion.id))),
            "passages": sorted(session.scalars(select(QueryPassage.id))),
            "sections": sorted(session.scalars(select(WikiSection.passage_id))),
            "operations": sorted(session.scalars(select(QueryOperation.key))),
        }


@pytest.mark.parametrize("operation", ["save", "patch"])
@pytest.mark.parametrize("damage", ["body", "caveat", "missing_section"])
def test_corrupt_snapshot_cannot_be_rehashed_by_save_or_unrelated_patch(engine, operation, damage):
    view = draft(engine)
    _damage_snapshot(engine, view, damage)
    before = _page_persistence(engine, view["page_id"])
    with pytest.raises(KnowledgeError) as caught:
        if operation == "save":
            save(engine, view)
        else:
            patch(
                engine,
                view,
                [
                    {
                        "op": "replace",
                        "section_id": view["sections"][0]["section_id"],
                        "passage": passage("A valid edit to a different paragraph."),
                    }
                ],
            )
    assert caught.value.code == "WIKI_SNAPSHOT_INVALID"
    assert _page_persistence(engine, view["page_id"]) == before
    with Session(engine) as session:
        assert read_page(session, "p", view["page_id"])["content_state"] == "invalid"


@pytest.mark.parametrize("operation", ["save", "patch"])
@pytest.mark.parametrize("damaged_version", ["input", "result"])
def test_idempotent_wiki_replay_revalidates_input_and_result_snapshots(
    engine, operation, damaged_version
):
    original = draft(engine)
    edits = [
        {
            "op": "replace",
            "section_id": original["sections"][0]["section_id"],
            "passage": passage("A supported new interpretation."),
        }
    ]
    result = save(engine, original) if operation == "save" else patch(engine, original, edits)
    _damage_snapshot(engine, original if damaged_version == "input" else result, "body")
    before = _page_persistence(engine, original["page_id"])
    with pytest.raises(KnowledgeError) as caught:
        if operation == "save":
            save(engine, original)
        else:
            patch(engine, original, edits)
    assert caught.value.code == "WIKI_SNAPSHOT_INVALID"
    assert _page_persistence(engine, original["page_id"]) == before


def test_valid_save_and_patch_replays_keep_historical_result_after_newer_head(engine):
    original = draft(engine)
    saved = save(engine, original)
    edits = [
        {
            "op": "replace",
            "section_id": saved["sections"][0]["section_id"],
            "passage": passage("An edited interpretation."),
        }
    ]
    changed = patch(engine, saved, edits)
    latest = save(engine, changed)
    before = _page_persistence(engine, original["page_id"])
    with Session(engine) as session, session.begin():
        mutations = WikiMutations(KnowledgeStore(session))
        replayed_save = mutations.save_draft(
            "p",
            original["page_id"],
            {
                "version_id": original["version_id"],
                "expected_head_version_id": original["head_version_id"],
                "expected_content_hash": original["content_hash"],
            },
            "save-" + original["version_id"],
        )
        replayed_patch = mutations.apply_patch(
            "p",
            saved["page_id"],
            {
                "base_version_id": saved["version_id"],
                "base_content_hash": saved["content_hash"],
                "operations": edits,
            },
            "patch-1",
        )
        assert replayed_save["version_id"] == saved["version_id"]
        assert replayed_patch["version_id"] == changed["version_id"]
        assert session.get(WikiPage, original["page_id"]).head_version_id == latest["version_id"]
    assert _page_persistence(engine, original["page_id"]) == before


@pytest.mark.parametrize("replay", [False, True])
def test_save_revalidates_current_personal_source_permission_even_on_replay(
    engine, tmp_path, replay
):
    from researchgraph.knowledge_models import AuthorizedRoot

    with Session(engine) as session, session.begin():
        root, note, _ = add_note(session, tmp_path)
        root_id, note_id, sha = root.id, note.id, note.sha256
    original = draft(
        engine,
        [
            passage(
                "An explicitly personal interpretation.",
                attribution="user_view",
                dependencies=[{"type": "note", "id": note_id, "sha256": sha}],
            )
        ],
    )
    if replay:
        save(engine, original)
    with Session(engine) as session, session.begin():
        session.get(AuthorizedRoot, root_id).active = False
    before = _page_persistence(engine, original["page_id"])
    with pytest.raises(KnowledgeError) as caught:
        save(engine, original)
    assert caught.value.code == "WIKI_CONTENT_STALE"
    assert _page_persistence(engine, original["page_id"]) == before


@pytest.mark.parametrize("damage", ["body", "caveat", "missing_section", "wrong_version"])
def test_corrupt_immutable_wiki_snapshot_is_not_displayed_as_valid(engine, damage):
    view = save(engine, draft(engine))
    with Session(engine) as session, session.begin():
        paragraph = session.get(QueryPassage, view["sections"][0]["passage_id"])
        sidecar = session.get(WikiSection, paragraph.id)
        if damage == "body":
            paragraph.text = "Corrupt unsupported result."
        elif damage == "caveat":
            paragraph.caveats = ["Corrupt unsupported limitation."]
        elif damage == "missing_section":
            session.delete(sidecar)
        else:
            # Keep this corruption legal under the independent (version, section) unique key.
            sidecar.section_id = "unrelated-section"
            sidecar.version_id = view["versions"][-1]["version_id"]
    with Session(engine) as session:
        assert wiki_version_state(session, view["version_id"])["content_state"] == "invalid"
        blocked = read_page(session, "p", view["page_id"])
        assert blocked["content_state"] == "invalid"
        assert "A method at 20 K." not in blocked["markdown"]
        assert "Corrupt unsupported" not in blocked["markdown"]
        assert blocked["diff"] == ""
        assert all(not section["text"] for section in blocked["sections"])


def test_cached_markdown_and_reference_quotes_cannot_replace_verified_root_render(engine):
    view = save(engine, draft(engine))
    with Session(engine) as session, session.begin():
        wiki = session.get(WikiVersion, view["version_id"])
        wiki.markdown = "Injected cached material."
        wiki.references = [{**wiki.references[0], "quote": "Injected private quote."}]
    with Session(engine) as session:
        current = read_page(session, "p", view["page_id"])
        assert current["markdown"] == view["markdown"]
        assert "Injected" not in current["diff"]


@pytest.mark.parametrize(
    "condition",
    [
        {"dimension": "temperature", "state": "known", "value": "  "},
        {"dimension": "temperature", "state": "unknown", "unit": "K"},
        {"dimension": "temperature", "state": "not_applicable", "value": "20"},
        {"dimension": " ", "state": "unknown"},
    ],
)
def test_wiki_condition_states_do_not_invent_values_or_units(condition):
    with pytest.raises(ValidationError):
        WikiDraftInput.model_validate(
            {
                "title": "Conditions",
                "passages": [passage(conditions=[condition])],
            }
        )


@pytest.mark.parametrize("anchored", [False, True])
def test_annotation_comment_render_retains_user_attribution_and_only_valid_anchor_page(
    engine, anchored
):
    from researchgraph.knowledge_models import Annotation, ZoteroLink
    from researchgraph.p5_personal import annotation_source
    from researchgraph.p5_personal_models import AnnotationHead

    comment = "<script>personal()</script> [unsafe](javascript:evil) 用户评论"
    with Session(engine) as session, session.begin():
        session.add(
            ZoteroLink(
                id="comment-link",
                paper_id="paper",
                document_version_id="v",
                library_id="users/123",
                item_key="PAPER123",
                attachment_key="ATTACH12",
                metadata_snapshot={},
            )
        )
        session.flush()
        session.add(
            Annotation(
                id="personal-comment",
                link_id="comment-link",
                document_version_id="v",
                annotation_key="COMMENT1",
                annotation_type="highlight",
                text="A method at 20 K.",
                comment=comment,
                source_position={"pageIndex": 0 if anchored else 99},
                source_hash="d" * 64,
                anchor_status="block_matched" if anchored else "unresolved",
                evidence_id="e" if anchored else None,
                created_at="now",
            )
        )
        session.flush()
        session.add(
            AnnotationHead(
                link_id="comment-link",
                annotation_key="COMMENT1",
                annotation_id="personal-comment",
                revision=1,
            )
        )
        session.flush()
        source = annotation_source(session, "p", "personal-comment")
    view = draft(
        engine,
        [
            passage(
                "An interpretation of my comment.",
                attribution="user_view",
                dependencies=[
                    {"type": "annotation", "id": source["id"], "sha256": source["sha256"]}
                ],
            )
        ],
    )
    with Session(engine) as session:
        allowed = read_page(session, "p", view["page_id"], include_personal=True)
        markdown = allowed["markdown"]
        assert "批注评论（用户）" in markdown
        assert "归属：用户观点；不作为论文科学证据" in markdown
        assert "&lt;script&gt;" in markdown and "<script>" not in markdown
        assert "[unsafe](javascript:evil)" not in markdown
        assert "zotero://open-pdf/library/items/ATTACH12" in markdown
        if anchored:
            assert "PDF 页：1" in markdown and "?page=1" in markdown
        else:
            assert "PDF 页：" not in markdown and "?page=" not in markdown
        assert "用户评论" not in read_page(session, "p", view["page_id"])["markdown"]


@pytest.mark.parametrize("attribution", ["user_view", "external_source"])
def test_external_reference_render_preserves_registered_origin_and_escapes_title_path(
    engine, tmp_path, attribution
):
    from researchgraph.external_documents import ExternalDocumentMutations
    from test_external_documents import request as external_request

    with Session(engine) as session, session.begin():
        root, _, path = add_note(session, tmp_path)
        source = {"root_id": root.id, "relative_path": "note.md", "path": path}
        external = ExternalDocumentMutations(KnowledgeStore(session)).register(
            "p",
            external_request(
                source, attribution=attribution, title="<b>External</b> [unsafe](javascript:evil)"
            ),
            "external-render",
            include_personal=True,
        )
    view = draft(
        engine,
        [
            passage(
                "An interpretation of the imported source.",
                attribution="user_view" if attribution == "user_view" else "model_synthesis",
                dependencies=[
                    {"type": "external", "id": external["version_id"], "sha256": external["sha256"]}
                ],
            )
        ],
    )
    with Session(engine) as session:
        markdown = read_page(session, "p", view["page_id"], include_personal=True)["markdown"]
        expected = (
            "个人资料（用户观点）" if attribution == "user_view" else "外部资料（作者归属未验证）"
        )
        assert expected in markdown
        assert "&lt;b&gt;External&lt;/b&gt;" in markdown
        assert "[unsafe](javascript:evil)" not in markdown
        assert "独立文档版本：" + external["version_id"] in markdown
        assert "相对路径：note.md" in markdown
        assert "来源状态：未由论文证据核验" in markdown
        assert "PDF 页：" not in markdown
