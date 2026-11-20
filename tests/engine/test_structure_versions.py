"""New local section trees reuse immutable original spans without duplicating data."""

from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from researchgraph.close_reading_api import _local_paragraphs
from researchgraph.core import KnowledgeError
from researchgraph.document_structure import (
    _contents_section_ids,
    active_section_rows,
    apply_structure,
    current_structure,
    section_model_spans,
    section_spans,
    span_is_readable,
)
from researchgraph.local_index import (
    index_document,
    register_local_index_api,
    search,
    section_views,
)
from researchgraph.models import (
    AttachmentRevision,
    Base,
    Chunk,
    EvidenceSpan,
    Paper,
    Project,
    Section,
)
from researchgraph.paper_overview_api import build_overview_input
from researchgraph.qa_api import _is_stale, _retrieved_spans, _view, build_qa_input
from researchgraph.qa_models import LiteQARecord
from researchgraph.reading_document_api import register_reading_document_api
from researchgraph.reading_state_api import _scope as state_scope
from researchgraph.section_guide_api import _section_scope, build_guide_input
from researchgraph.structure_models import DocumentParse
from researchgraph.structure_upgrade import ensure_structure_v2
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def section(ref, title, ordinal, *, role="other", parent="s0", level=1):
    return {
        "id": ref,
        "title": title,
        "ordinal": ordinal,
        "role": role,
        "parent_id": parent,
        "level": level,
        "start_page": 0,
        "end_page": 0,
        "excluded": False,
    }


@pytest.fixture
def versioned():
    # The route regression below runs through FastAPI's worker thread.  Share
    # the in-memory database across that thread while keeping the fixture
    # isolated from the application database.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE VIRTUAL TABLE chunk_fts USING fts5("
                "chunk_id UNINDEXED,paper_id UNINDEXED,document_version_id UNINDEXED,"
                "section_id UNINDEXED,text,tokenize='unicode61')"
            )
        )
    structure = {
        "schema_version": "pdf-structure-1",
        "parser_version": "synthetic-structure-1",
        "sections": [section("s0", "Document", 0, role="document", parent=None, level=0)],
        "blocks": [],
    }
    with Session(engine) as session, session.begin():
        session.add(Project(id="project", name="Synthetic", description="", created_at="now"))
        session.flush()
        session.add(Paper(id="paper", project_id="project", title="Synthetic", created_at="now"))
        session.flush()
        session.add(
            AttachmentRevision(
                id="revision",
                paper_id="paper",
                sha256="a" * 64,
                parser_version="synthetic",
                page_count=1,
                warnings=[],
                created_at="now",
            )
        )
        session.flush()
        for index, value in enumerate(
            (
                "The method uses shared memory to coordinate decisions.",
                "The reported outcome is limited to the synthetic setting.",
            )
        ):
            bbox = [40, 100 + index * 100, 500, 150 + index * 100]
            session.add(
                Chunk(
                    id=f"chunk-{index}",
                    revision_id="revision",
                    page_index=0,
                    page_label="1",
                    block_index=index,
                    text=value,
                    bbox=bbox,
                )
            )
            structure["blocks"].append(
                {
                    "ref": f"p0:b{index}",
                    "page_index": 0,
                    "block_index": index,
                    "text": value,
                    "bbox": bbox,
                    "section_ref": "s0",
                    "excluded": False,
                }
            )
        session.flush()
        apply_structure(session, "revision", "a" * 64, structure)
    yield engine, structure
    engine.dispose()


def snapshot(session, model):
    return {
        row.id: {
            column.name: deepcopy(getattr(row, column.name)) for column in model.__table__.columns
        }
        for row in session.scalars(select(model))
    }


def add_current(session, structure):
    updated = deepcopy(structure)
    updated["parser_version"] = "synthetic-structure-2"
    updated["sections"] += [
        section("s1", "2 Methods", 1, role="method"),
        section("s2", "3 Results", 2, role="result"),
    ]
    updated["blocks"][0]["section_ref"] = "s1"
    updated["blocks"][1]["section_ref"] = "s2"
    apply_structure(session, "revision", "a" * 64, updated)
    index_document(session, "revision")
    return updated


def add_mixed(session, structure, *, excluded=False):
    updated = deepcopy(structure)
    updated["parser_version"] = "synthetic-structure-2"
    updated["sections"] += [
        section("s1", "2 Methods", 1, role="method"),
        section(
            "s2",
            "shared memory",
            2,
            role="references" if excluded else "method",
            parent="s1",
            level=2,
        ),
    ]
    updated["sections"][2]["excluded"] = excluded
    for block in updated["blocks"]:
        block["section_ref"] = "s1"
    block = updated["blocks"][0]
    start = block["text"].index("shared memory")
    block["heading_candidates"] = [
        {
            "start_offset": start,
            "end_offset": start + len("shared memory"),
            "text": "shared memory",
            "section_ref": "s2",
            "level": 2,
            "role": "references" if excluded else "method",
        }
    ]
    apply_structure(session, "revision", "a" * 64, updated)
    index_document(session, "revision")
    return updated


def test_new_tree_reuses_source_spans_and_preserves_historical_rows(versioned):
    engine, structure = versioned
    with Session(engine) as session, session.begin():
        originals = {
            model: snapshot(session, model)
            for model in (Chunk, Section, EvidenceSpan, DocumentParse)
        }
        old_section = active_section_rows(session, "revision")[0]
        old_spans = section_spans(session, old_section)
        add_current(session, structure)
        current = active_section_rows(session, "revision")
        assert [row.title for row in current] == ["Document", "2 Methods", "3 Results"]
        assert old_section.id not in {row.id for row in current}
        for model, saved in originals.items():
            assert {key: snapshot(session, model)[key] for key in saved} == saved
        assert len(snapshot(session, EvidenceSpan)) == 2
        assert [span.id for span in section_spans(session, current[1])] == [old_spans[0].id]
        assert section_spans(session, current[1])[0].section_id == old_section.id
        assert [span.id for span in section_spans(session, old_section)] == [
            span.id for span in old_spans
        ]
        assert search(session, "project", "shared memory", "paper", "revision", old_section.id)
        views = section_views(session, "revision")
        assert len(views) == 3 and views[1].chunk_ids == ["chunk-0"]
        assert "shared memory" in views[1].text


def test_current_tree_guide_search_qa_state_and_overview_read_existing_text(versioned):
    engine, structure = versioned
    with Session(engine) as session, session.begin():
        add_current(session, structure)
        method = active_section_rows(session, "revision")[1]
        paper, revision, selected, parent, spans = _section_scope(
            session, "paper", "revision", method.id
        )
        context = build_guide_input(session, paper, revision, selected, parent, spans, "quick")
        assert context["section_heading"] == "2 Methods"
        assert "shared memory" in context["allowed_spans"][0]["text_en"]
        assert context["allowed_spans"][0]["section_id"] != method.id
        hits = search(session, "project", "shared memory", "paper", "revision", method.id)
        assert len(hits) == 1 and hits[0].section_id == method.id
        for scope in ("section", "selection"):
            retrieved = _retrieved_spans(
                session,
                project_id="project",
                paper_id="paper",
                revision_id="revision",
                section_id=method.id,
                question="shared memory",
                selection_span_ids=[spans[0].id],
                scope=scope,
            )
            assert [span.id for span in retrieved] == [spans[0].id]
            assert retrieved[0].section_id != method.id
        assert state_scope(session, "paper", "revision", method.id)[3] == {"chunk-0"}
        assert (
            _local_paragraphs(session, "paper", "revision", method.id)[3][0]["paragraph_id"]
            == "chunk-0"
        )
        overview = build_overview_input(session, paper, revision)
        assert "shared memory" in overview["method_overview_excerpt"]
        assert "reported outcome" in overview["result_overview_excerpt"]
        assert overview["section_headings"].count("2 Methods") == 1


@pytest.mark.parametrize("target", ["span_hash", "chunk_bbox", "artifact_text"])
@pytest.mark.parametrize("equal_timestamp", [False, True])
def test_current_mapping_rejects_changed_source_or_anchor(versioned, target, equal_timestamp):
    engine, structure = versioned
    with Session(engine) as session, session.begin():
        add_current(session, structure)
        if equal_timestamp:
            for saved in session.scalars(select(DocumentParse)):
                saved.created_at = "2026-01-01T00:00:00+00:00"
            session.flush()
        method = active_section_rows(session, "revision")[1]
        if target == "span_hash":
            section_spans(session, method)[0].text_sha256 = "b" * 64
        elif target == "chunk_bbox":
            session.get(Chunk, "chunk-0").bbox = [0, 0, 1, 1]
        else:
            # Windows clocks can assign both versions the same timestamp.
            # Mutate the artifact actually backing this section; a timestamp-
            # only query may select an untouched historical version instead.
            artifact = current_structure(session, "revision")
            assert method.id in {item["section_id"] for item in artifact.data["sections"]}
            artifact.data = {
                **artifact.data,
                "blocks": [
                    {**artifact.data["blocks"][0], "text": "changed"},
                    artifact.data["blocks"][1],
                ],
            }
        with pytest.raises(KnowledgeError) as error:
            section_spans(session, method)
        assert error.value.code == "PARSE_ANCHOR_MISMATCH"


def test_current_reference_classification_blocks_qa_without_rewriting_span(versioned):
    engine, structure = versioned
    with Session(engine) as session, session.begin():
        original_span = session.scalar(
            select(EvidenceSpan).where(EvidenceSpan.paragraph_id == "chunk-0")
        )
        original_section = original_span.section_id
        updated = deepcopy(structure)
        updated["parser_version"] = "synthetic-structure-2"
        updated["sections"][0]["role"] = "references"
        updated["sections"][0]["excluded"] = True
        apply_structure(session, "revision", "a" * 64, updated)
        assert not span_is_readable(session, original_span)
        assert original_span.section_id == original_section
        with pytest.raises(KnowledgeError) as error:
            _retrieved_spans(
                session,
                project_id="project",
                paper_id="paper",
                revision_id="revision",
                section_id=None,
                question="shared memory",
                selection_span_ids=[original_span.id],
                scope="selection",
            )
        assert error.value.code == "SELECTION_SCOPE_INVALID"


def test_middle_of_block_child_has_context_and_scoped_search_without_duplicate_index(versioned):
    engine, structure = versioned
    with Session(engine) as session, session.begin():
        original = snapshot(session, EvidenceSpan)
        index_document(session, "revision")
        old_section = active_section_rows(session, "revision")[0]
        old_paper, old_revision, old_selected, old_parent, old_spans = _section_scope(
            session, "paper", "revision", old_section.id
        )
        old_guide = build_guide_input(
            session, old_paper, old_revision, old_selected, old_parent, old_spans, "quick"
        )
        old_qa = build_qa_input(
            session,
            old_paper,
            old_revision,
            question="shared memory",
            scope="section",
            section_id=old_section.id,
            selection_span_ids=[],
            optional_short_card=None,
        )[0]
        add_mixed(session, structure)
        parent, child = active_section_rows(session, "revision")[1:]
        assert child.parent_id == parent.id
        assert [span.paragraph_id for span in section_spans(session, child)] == ["chunk-0"]
        assert section_views(session, "revision")[2].text == structure["blocks"][0]["text"]
        assert session.scalar(text("SELECT COUNT(*) FROM chunk_fts")) == 2
        hits = search(session, "project", "shared memory", "paper", "revision", child.id)
        assert len(hits) == 1 and hits[0].chunk_id == "chunk-0"
        # The one FTS row keeps its original whole-block owner, not the new child title.
        assert hits[0].section_id == parent.id
        paper, revision, selected, ancestor, spans = _section_scope(
            session, "paper", "revision", child.id
        )
        guide = build_guide_input(session, paper, revision, selected, ancestor, spans, "quick")
        assert guide["source_boundary"]["policy"] == "whole_original_blocks"
        assert guide["source_boundary"]["requested_section_id"] == child.id
        qa, retrieved = build_qa_input(
            session,
            paper,
            revision,
            question="shared memory",
            scope="section",
            section_id=child.id,
            selection_span_ids=[],
            optional_short_card=None,
        )
        assert qa["source_boundary"]["requested_heading"] == child.title
        assert len(retrieved) == 1 and retrieved[0].paragraph_id == "chunk-0"
        assert snapshot(session, EvidenceSpan) == original
        assert (
            build_guide_input(
                session,
                old_paper,
                old_revision,
                old_selected,
                old_parent,
                section_spans(session, old_section),
                "quick",
            )
            == old_guide
        )
        assert (
            build_qa_input(
                session,
                old_paper,
                old_revision,
                question="shared memory",
                scope="section",
                section_id=old_section.id,
                selection_span_ids=[],
                optional_short_card=None,
            )[0]
            == old_qa
        )
        overview = build_overview_input(session, paper, revision)
        assert overview["unclassified_excerpt"].count("shared memory") == 1
        assert "shared memory" not in overview["method_overview_excerpt"]


def test_mixed_excluded_block_stays_local_and_frozen_history_remains_readable(versioned):
    engine, structure = versioned
    with Session(engine) as session, session.begin():
        index_document(session, "revision")
        old = active_section_rows(session, "revision")[0]
        span = section_spans(session, old)[0]
        row = LiteQARecord(
            id="old-qa",
            project_id="project",
            paper_id="paper",
            document_version_id="revision",
            section_id=old.id,
            scope="section",
            question="shared memory",
            source_hash="a" * 64,
            input_hash="frozen-input",
            cache_key="frozen-cache",
            schema_version="grounded_qa.v1",
            prompt_version="d01_grounded_qa_v1",
            provider_id="test",
            model_id="test",
            status="COMPLETED",
            answer_json={"answer_zh": "保留的历史答案", "insufficient_evidence": True},
            retrieval_spans_json=[
                {
                    "span_id": span.id,
                    "page_start": 1,
                    "page_end": 1,
                    "quote": span.quote,
                    "section_id": old.id,
                }
            ],
            raw_output="frozen-output",
        )
        session.add(row)
        session.flush()
        saved = snapshot(session, LiteQARecord)
        add_mixed(session, structure, excluded=True)
        parent = active_section_rows(session, "revision")[1]
        assert len(section_spans(session, parent)) == 2
        assert [item.paragraph_id for item in section_model_spans(session, parent)] == ["chunk-1"]
        assert not search(session, "project", "shared memory", "paper", "revision", parent.id)
        assert not span_is_readable(session, span)
        assert "shared memory" not in str(
            build_overview_input(
                session, session.get(Paper, "paper"), session.get(AttachmentRevision, "revision")
            )
        )
        view = _view(row, stale=_is_stale(session, row))
        assert view.status == "COMPLETED" and view.retrieval_spans[0].section_id == old.id
        assert view.retrieval_spans[0].quote == span.quote
        assert snapshot(session, LiteQARecord) == saved


@pytest.mark.parametrize(
    "target", ["bool_offset", "unknown_ref", "wrong_ref", "level", "role", "text"]
)
def test_mixed_candidate_corruption_cannot_expand_a_section_scope(versioned, target):
    engine, structure = versioned
    with Session(engine) as session, session.begin():
        add_mixed(session, structure)
        child = active_section_rows(session, "revision")[2]
        artifact = current_structure(session, "revision")
        data = deepcopy(artifact.data)
        candidate = data["blocks"][0]["heading_candidates"][0]
        if target == "bool_offset":
            candidate["start_offset"] = True
        elif target == "unknown_ref":
            candidate["section_ref"] = "absent"
        elif target == "wrong_ref":
            candidate["section_ref"] = "s1"
        else:
            candidate[target] = {"level": 1, "role": "result", "text": "changed"}[target]
        artifact.data = data
        with pytest.raises(KnowledgeError) as error:
            section_spans(session, child)
        assert error.value.code in {"PARSE_ANCHOR_MISMATCH", "INVALID_SECTION"}


def test_current_structure_prefers_v2_when_imported_timestamps_tie(versioned):
    engine, structure = versioned
    with Session(engine) as session, session.begin():
        old = current_structure(session, "revision")
        updated = deepcopy(structure)
        updated["parser_version"] = "pymupdf/synthetic;structure-v2"
        new = apply_structure(session, "revision", "a" * 64, updated)
        new.created_at = old.created_at
        session.flush()
        assert current_structure(session, "revision").id == new.id


def test_old_structure_contents_rows_are_detected_without_mutating_artifact():
    artifact = DocumentParse(
        id="old",
        document_version_id="revision",
        parser_version="pymupdf/old;structure-v1",
        source_sha256="a" * 64,
        data={
            "sections": [
                {
                    "id": "s0",
                    "section_id": "section-document",
                    "title": "Document",
                    "block_refs": [],
                },
                {
                    "id": "s1",
                    "section_id": "section-contents",
                    "title": "Contents",
                    "parent_id": "s0",
                    "block_refs": ["p1:b0"],
                },
                {
                    "id": "s2",
                    "section_id": "section-contents-conclusion",
                    "title": "5 Conclusion",
                    "parent_id": "s1",
                    "block_refs": ["p1:b1"],
                },
                {
                    "id": "s3",
                    "section_id": "section-introduction",
                    "title": "1 Introduction",
                    "parent_id": "s0",
                    "block_refs": ["p0:b0"],
                },
            ],
            "blocks": [
                {
                    "ref": "p0:b0",
                    "page_index": 0,
                    "text": "1 Introduction",
                    "section_ref": "s3",
                    "excluded": False,
                    "kind": "heading",
                    "bbox": [45, 90, 150, 105],
                    "lines": [
                        {
                            "text": "1 Introduction",
                            "bbox": [45, 90, 150, 105],
                        }
                    ],
                },
                {
                    "ref": "p1:b0",
                    "page_index": 1,
                    "text": "Contents",
                    "section_ref": "s1",
                    "excluded": False,
                    "kind": "paragraph",
                    "bbox": [45, 90, 130, 105],
                    "lines": [{"text": "Contents", "bbox": [45, 90, 130, 105]}],
                },
                {
                    "ref": "p1:b1",
                    "page_index": 1,
                    "text": "5 Conclusion\n10",
                    "section_ref": "s2",
                    "excluded": False,
                    "kind": "paragraph",
                    "bbox": [45, 130, 535, 145],
                    "lines": [
                        {"text": "5 Conclusion", "bbox": [45, 130, 160, 145]},
                        {"text": "10", "bbox": [510, 130, 535, 145]},
                    ],
                },
            ],
        },
        created_at="now",
    )
    hidden = _contents_section_ids(artifact)
    assert hidden == {"s1", "s2"}
    assert not artifact.data["blocks"][1].get("contents_entry")


def test_legacy_tree_upgrade_publishes_v2_before_outline_reads(versioned, monkeypatch):
    engine, original = versioned
    fresh = deepcopy(original)
    fresh["parser_version"] = "pymupdf/test;structure-v2"
    monkeypatch.setattr(
        "researchgraph.reading_projection._scan_pdf",
        lambda *_args, **_kwargs: (deepcopy(fresh), []),
    )
    assert ensure_structure_v2(engine, "paper", "revision", None)
    with Session(engine) as session:
        assert section_views(session, "revision")[0].title == "Document"
    with Session(engine) as session:
        artifacts = list(session.scalars(select(DocumentParse).order_by(DocumentParse.created_at)))
        assert len(artifacts) == 2
        assert artifacts[-1].parser_version.endswith(";structure-v2")
        assert current_structure(session, "revision").id == artifacts[-1].id


def test_sections_route_upgrades_legacy_tree_before_returning_outline(versioned, monkeypatch):
    engine, original = versioned
    fresh = deepcopy(original)
    fresh["parser_version"] = "pymupdf/test;structure-v2"
    calls = []

    def scan(*_args, **_kwargs):
        calls.append(True)
        return deepcopy(fresh), []

    monkeypatch.setattr("researchgraph.reading_projection._scan_pdf", scan)
    app = FastAPI()
    register_local_index_api(app, lambda: engine)
    client = TestClient(app)

    first = client.get("/api/v1/revisions/revision/sections")
    assert first.status_code == 200, first.text
    assert first.json()["document_version_id"] == "revision"
    assert len(calls) == 1

    second = client.get("/api/v1/revisions/revision/sections")
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    assert len(calls) == 1


def test_qa_directory_reads_only_committed_headings_without_source_scan(versioned, monkeypatch):
    engine, _original = versioned
    with Session(engine) as session:
        before = {
            model: snapshot(session, model)
            for model in (Chunk, Section, EvidenceSpan, DocumentParse)
        }

    def unexpected(*_args, **_kwargs):
        pytest.fail("QA directory must not scan a PDF or materialize any section text")

    monkeypatch.setattr("researchgraph.local_index.ensure_structure_v2", unexpected)
    monkeypatch.setattr("researchgraph.local_index.section_spans", unexpected)
    app = FastAPI()
    register_local_index_api(app, lambda: engine)
    with TestClient(app) as client:
        response = client.get("/api/v1/revisions/revision/sections?include_text=false")
    assert response.status_code == 200, response.text
    rows = response.json()["sections"]
    assert len(rows) == 1 and rows[0]["title"] == "Document"
    assert rows[0]["text"] == "" and rows[0]["chunk_ids"] == []
    with Session(engine) as session:
        for model, saved in before.items():
            assert snapshot(session, model) == saved


def test_qa_preview_materializes_only_selected_current_section(versioned, monkeypatch):
    engine, structure = versioned
    with Session(engine) as session, session.begin():
        old_section_id = active_section_rows(session, "revision")[0].id
        add_current(session, structure)
        method = active_section_rows(session, "revision")[1]
        method_id = method.id
    calls = []

    def unexpected(*_args, **_kwargs):
        pytest.fail("QA preview must not reopen or upgrade a PDF")

    original_spans = section_spans

    def selected_spans(session, selected):
        calls.append(selected.id)
        return original_spans(session, selected)

    monkeypatch.setattr("researchgraph.local_index.ensure_structure_v2", unexpected)
    monkeypatch.setattr("researchgraph.local_index.section_spans", selected_spans)
    app = FastAPI()
    register_local_index_api(app, lambda: engine)
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/revisions/revision/sections", params={"section_id": method_id}
        )
        assert response.status_code == 200, response.text
        rows = response.json()["sections"]
        assert len(rows) == 1 and rows[0]["id"] == method_id
        assert rows[0]["chunk_ids"] == ["chunk-0"]
        assert "shared memory" in rows[0]["text"]
        assert calls == [method_id]
        for unavailable in (old_section_id, "foreign-or-missing"):
            with pytest.raises(KnowledgeError) as caught:
                client.get(
                    "/api/v1/revisions/revision/sections", params={"section_id": unavailable}
                )
            assert caught.value.code == "SECTION_NOT_FOUND"
        # A preview still validates the immutable source before exposing text.
        with Session(engine) as session, session.begin():
            span = session.scalar(
                select(EvidenceSpan).where(EvidenceSpan.paragraph_id == "chunk-0")
            )
            span.text_sha256 = "b" * 64
        with pytest.raises(KnowledgeError) as caught:
            client.get("/api/v1/revisions/revision/sections", params={"section_id": method_id})
        assert caught.value.code == "PARSE_ANCHOR_MISMATCH"


def test_reading_document_route_upgrades_legacy_tree_before_projection(versioned, monkeypatch):
    engine, original = versioned
    fresh = deepcopy(original)
    fresh["parser_version"] = "pymupdf/test;structure-v2"
    calls = []

    def scan(*_args, **_kwargs):
        calls.append(True)
        return deepcopy(fresh), []

    monkeypatch.setattr("researchgraph.reading_projection._scan_pdf", scan)
    app = FastAPI()
    register_reading_document_api(app, lambda: engine, None)
    client = TestClient(app)

    first = client.get("/api/v1/papers/paper/reading-document")
    assert first.status_code == 200, first.text
    assert [item["title"] for item in first.json()["sections"]] == ["Document"]
    assert len(calls) == 1

    second = client.get("/api/v1/papers/paper/reading-document")
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    assert len(calls) == 1


def test_legacy_upgrade_keeps_old_tree_when_registered_pdf_is_unavailable(versioned, monkeypatch):
    engine, _original = versioned
    monkeypatch.setattr(
        "researchgraph.reading_projection._scan_pdf",
        lambda *_args, **_kwargs: (None, ["source unavailable"]),
    )
    with Session(engine) as session:
        before = current_structure(session, "revision")
        assert before is not None
        old_id = before.id
    assert not ensure_structure_v2(engine, "paper", "revision", None)
    with Session(engine) as session:
        after = current_structure(session, "revision")
        assert after is not None and after.id == old_id


def test_reading_document_explains_legacy_tree_when_upgrade_source_is_unavailable(
    versioned, monkeypatch
):
    engine, _original = versioned
    monkeypatch.setattr(
        "researchgraph.reading_projection._scan_pdf",
        lambda *_args, **_kwargs: (None, ["source unavailable"]),
    )
    app = FastAPI()
    register_reading_document_api(app, lambda: engine, None)
    response = TestClient(app).get("/api/v1/papers/paper/reading-document")
    assert response.status_code == 200, response.text
    assert any("旧章节解析" in warning for warning in response.json()["warnings"])


def test_historical_section_still_revalidates_original_span_hash_after_refresh(versioned):
    engine, structure = versioned
    with Session(engine) as session, session.begin():
        old = active_section_rows(session, "revision")[0]
        original = section_spans(session, old)[0]
        add_current(session, structure)
        original.text_sha256 = "changed"
        with pytest.raises(KnowledgeError) as error:
            section_spans(session, old)
        assert error.value.code == "PARSE_ANCHOR_MISMATCH"
