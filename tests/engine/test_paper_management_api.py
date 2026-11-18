"""Paper management mutations are isolated, backed up, and source-safe."""

import sqlite3
from pathlib import Path
from uuid import uuid4

from researchgraph.import_plan_models import ImportPlanItem, ImportSession
from researchgraph.lite_models import LiteCacheEntry, LiteTokenUsage
from researchgraph.model_document_models import (
    LlmDocumentOutput,
    LlmDocumentParse,
    LlmDocumentSegment,
)
from researchgraph.models import (
    AttachmentRevision,
    Chunk,
    EvidenceSpan,
    Job,
    Paper,
    PaperSource,
    Section,
    ZoteroLink,
    now,
)
from researchgraph.paper_overview_models import (
    PaperOverviewResult,
)
from researchgraph.paper_reading_models import PaperReadingResult
from researchgraph.qa_models import LiteQARecord
from researchgraph.reading_document_models import ReadingDocumentProjection
from researchgraph.reading_state_models import ConceptUnderstanding, ReadingState
from researchgraph.section_guide_models import SectionGuideResult
from researchgraph.structure_models import DocumentParse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_engine import client, post


def add_paper(api, data_dir: Path, *, managed_copy: bool = True):
    project_response = post(api, "/projects", {"name": f"paper-management-{uuid4()}"})
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["id"]
    paper_id, revision_id, section_id, chunk_id = (str(uuid4()) for _ in range(4))
    imported_path = data_dir / "zotero-original.pdf"
    imported_path.write_bytes(b"original zotero pdf")
    managed_root = data_dir / "attachments"
    managed_root.mkdir(exist_ok=True)
    managed_path = managed_root / f"{uuid4().hex}.pdf"
    managed_path.write_bytes(b"managed copy")
    outside_root = data_dir.parent / f"outside-managed-{uuid4().hex}.pdf"
    outside_root.write_bytes(b"outside file")
    overview_id, session_id, parse_id = (str(uuid4()) for _ in range(3))
    parse_job_id = str(uuid4())

    with Session(api.app.state.engine) as db, db.begin():
        db.add(Paper(id=paper_id, project_id=project_id, title="Original title", created_at=now()))
        db.flush()
        db.add(
            AttachmentRevision(
                id=revision_id,
                paper_id=paper_id,
                sha256="a" * 64,
                parser_version="fixture-v1",
                page_count=1,
                warnings=[],
                created_at=now(),
            )
        )
        db.flush()
        db.add(
            Section(
                id=section_id,
                document_version_id=revision_id,
                title="Introduction",
                ordinal=0,
                role="method",
                parser="fixture-v1",
                parent_id=None,
                level=0,
                start_page=0,
                end_page=0,
                excluded=False,
            )
        )
        db.flush()
        db.add_all(
            [
                PaperSource(
                    id=str(uuid4()),
                    paper_id=paper_id,
                    revision_id=revision_id,
                    path=str(imported_path),
                    mode="reference",
                    managed_path=None,
                ),
                PaperSource(
                    id=str(uuid4()),
                    paper_id=paper_id,
                    revision_id=revision_id,
                    path=str(data_dir / "selected.pdf"),
                    mode="managed",
                    managed_path=str(managed_path) if managed_copy else None,
                ),
                PaperSource(
                    id=str(uuid4()),
                    paper_id=paper_id,
                    revision_id=revision_id,
                    path=str(data_dir / "unsafe.pdf"),
                    mode="managed",
                    managed_path=str(outside_root),
                ),
                ZoteroLink(
                    id=str(uuid4()),
                    paper_id=paper_id,
                    document_version_id=revision_id,
                    library_id="users/0",
                    item_key="ABC12345",
                    attachment_key="DEF67890",
                    metadata_snapshot={"title": "Zotero fixture"},
                ),
                Chunk(
                    id=chunk_id,
                    revision_id=revision_id,
                    page_index=0,
                    page_label="1",
                    block_index=0,
                    text="legacy extracted paragraph",
                    bbox=[0, 0, 20, 20],
                ),
                EvidenceSpan(
                    id=str(uuid4()),
                    document_version_id=revision_id,
                    section_id=section_id,
                    paragraph_id=chunk_id,
                    page_index=0,
                    start_offset=0,
                    end_offset=7,
                    quote="legacy ",
                    text_sha256="b" * 64,
                    normalization="identity",
                    bbox_list=[[0, 0, 20, 20]],
                ),
                DocumentParse(
                    id=str(uuid4()),
                    document_version_id=revision_id,
                    parser_version="fixture-structure-v1",
                    source_sha256="a" * 64,
                    data={"text": "legacy structure text"},
                    created_at=now(),
                ),
                ReadingDocumentProjection(
                    id=str(uuid4()),
                    document_version_id=revision_id,
                    projection_version="reading-document-2",
                    source_hash="a" * 64,
                    projection_hash="c" * 64,
                    data={"paragraphs": [{"text": "legacy cached paragraph"}]},
                    created_at=now(),
                    updated_at=now(),
                ),
                LiteCacheEntry(
                    cache_key="d" * 64,
                    project_id=project_id,
                    task_kind="paper_overview",
                    paper_id=paper_id,
                    document_version_id=revision_id,
                    section_id=section_id,
                    input_fingerprint="e" * 64,
                    prompt_version="fixture-prompt",
                    schema_version="fixture-schema",
                    provider="fixture",
                    model="fixture-model",
                    config_fingerprint="f" * 64,
                    source_hash="a" * 64,
                    state="fresh",
                    response={"text": "cached response"},
                    created_at=now(),
                    updated_at=now(),
                ),
                LiteTokenUsage(
                    id=str(uuid4()),
                    project_id=project_id,
                    paper_id=paper_id,
                    document_version_id=revision_id,
                    section_id=section_id,
                    task_run_id=str(uuid4()),
                    task_kind="paper_overview",
                    provider="fixture",
                    model="fixture-model",
                    prompt_version="fixture-prompt",
                    input_tokens=12,
                    output_tokens=8,
                    total_tokens=20,
                    retry_count=0,
                    cache_hit=False,
                    usage_source="provider",
                    cost_estimate=None,
                    status="succeeded",
                    reason_code=None,
                    extra={"fixture": True},
                    created_at=now(),
                ),
                PaperOverviewResult(
                    id=overview_id,
                    project_id=project_id,
                    paper_id=paper_id,
                    document_version_id=revision_id,
                    pdf_hash="a" * 64,
                    input_hash="b" * 64,
                    cache_key="c" * 64,
                    schema_version="overview-v1",
                    prompt_version="overview-prompt-v1",
                    provider_id="fixture",
                    model_id="fixture-model",
                    paper_card_json={"summary": "saved overview note"},
                    graph_json={"nodes": []},
                    usage_json={"total_tokens": 20},
                    status="SUCCEEDED",
                    graph_status="READY",
                    job_id=None,
                    error_code=None,
                    error=None,
                    raw_output="overview raw output",
                    request_metadata={"fixture": True},
                    cache_hit=False,
                    created_at=now(),
                    updated_at=now(),
                ),
                PaperReadingResult(
                    id=str(uuid4()),
                    project_id=project_id,
                    paper_id=paper_id,
                    document_version_id=revision_id,
                    projection_version="reading-document-2",
                    projection_hash="c" * 64,
                    source_hash="a" * 64,
                    input_hash="b" * 64,
                    cache_key="f" * 64,
                    schema_version="reading-v1",
                    prompt_version="reading-prompt-v1",
                    provider_id="fixture",
                    model_id="fixture-model",
                    status="SUCCEEDED",
                    analysis_json={"summary": "saved reading note"},
                    warnings_json=[],
                    request_metadata={},
                    cache_hit=False,
                    created_at=now(),
                    updated_at=now(),
                ),
                ReadingState(
                    id=str(uuid4()),
                    paper_id=paper_id,
                    document_version_id=revision_id,
                    section_id=section_id,
                    source_hash="a" * 64,
                    progress="IN_PROGRESS",
                    self_assessment="UNDERSTOOD",
                    unresolved_concept_ids=[],
                    graph_reference_json={},
                    questions=[{"question": "my note"}],
                    updated_at=now(),
                ),
                ConceptUnderstanding(
                    id=str(uuid4()),
                    paper_id=paper_id,
                    document_version_id=revision_id,
                    overview_result_id=overview_id,
                    graph_node_id="n1",
                    node_fingerprint="a" * 64,
                    node_snapshot={"label": "concept"},
                    self_level="UNDERSTOOD",
                    last_check_result="SUPPORTED",
                    note_zh="personal concept note",
                    last_check_note_zh="generated check note",
                    updated_at=now(),
                ),
                LiteQARecord(
                    id=str(uuid4()),
                    project_id=project_id,
                    paper_id=paper_id,
                    document_version_id=revision_id,
                    section_id=section_id,
                    scope="paper",
                    question="saved question",
                    source_hash="a" * 64,
                    input_hash="b" * 64,
                    retrieval_spans_json=[],
                    cache_key="1" * 64,
                    schema_version="qa-v1",
                    prompt_version="qa-prompt-v1",
                    provider_id="fixture",
                    model_id="fixture-model",
                    answer_json={"answer": "saved answer"},
                    usage_json={"total_tokens": 10},
                    status="SUCCEEDED",
                    request_metadata={},
                    cache_hit=False,
                    created_at=now(),
                    updated_at=now(),
                ),
                SectionGuideResult(
                    id=str(uuid4()),
                    project_id=project_id,
                    paper_id=paper_id,
                    document_version_id=revision_id,
                    section_id=section_id,
                    depth="standard",
                    source_hash="a" * 64,
                    input_hash="b" * 64,
                    cache_key="2" * 64,
                    schema_version="guide-v1",
                    prompt_version="guide-prompt-v1",
                    provider_id="fixture",
                    model_id="fixture-model",
                    guide_json={"summary": "saved guide"},
                    status="SUCCEEDED",
                    request_metadata={},
                    cache_hit=False,
                    created_at=now(),
                    updated_at=now(),
                ),
                Job(
                    id=parse_job_id,
                    project_id=project_id,
                    kind="llm_document_parse",
                    payload={"paper_id": paper_id, "import_session_id": session_id},
                    status="succeeded",
                    stage="complete",
                    attempt=1,
                    error=None,
                    result={"paper_id": paper_id},
                    created_at=now(),
                    updated_at=now(),
                ),
                ImportSession(
                    id=session_id,
                    project_id=project_id,
                    source_kind="pdf",
                    selection_id=str(uuid4()),
                    source_snapshot={"paper_id": paper_id, "file_name": "model.pdf"},
                    plan={"overview": True, "reading": True},
                    status="succeeded",
                    error=None,
                    created_at=now(),
                    updated_at=now(),
                ),
            ]
        )
        db.flush()
        db.add(
            ImportPlanItem(
                id=str(uuid4()),
                session_id=session_id,
                item_kind="document_parse",
                status="succeeded",
                config={"parse": True},
                job_id=parse_job_id,
                attempt=1,
                error=None,
                result={"parse_id": parse_id},
                created_at=now(),
                updated_at=now(),
            )
        )
        db.add(
            LlmDocumentParse(
                id=parse_id,
                import_session_id=session_id,
                parse_version="reading-semantic-1",
                provider_id="fixture",
                model_id="fixture-model",
                modality="pdf",
                status="succeeded",
                raw_response={"segments": 1},
                warnings=[],
                error_code=None,
                error=None,
                started_at=now(),
                finished_at=now(),
                created_at=now(),
                updated_at=now(),
            )
        )
        db.flush()
        db.add(
            LlmDocumentSegment(
                id=str(uuid4()),
                parse_id=parse_id,
                chapter_ref="1",
                chapter_title="Model chapter",
                chapter_level=1,
                chapter_order=0,
                kind="paragraph",
                ordinal=0,
                text="model-first document content",
                latex=None,
                mathml=None,
                raw_table_text=None,
                table_data=None,
                locator=None,
                confidence=1.0,
                status="ok",
                warnings=[],
                created_at=now(),
            )
        )
        db.flush()
        db.add(
            LlmDocumentOutput(
                id=str(uuid4()),
                import_session_id=session_id,
                parse_id=parse_id,
                item_kind="paper_reading",
                status="succeeded",
                provider_id="fixture",
                model_id="fixture-model",
                output_json={"summary": "model-first output"},
                raw_response='{"summary":"model-first output"}',
                usage={"total_tokens": 5},
                error_code=None,
                error=None,
                created_at=now(),
                updated_at=now(),
            )
        )
        db.flush()
        db.connection().exec_driver_sql(
            "INSERT INTO chunk_fts(chunk_id,paper_id,document_version_id,section_id,text) "
            "VALUES(?,?,?,?,?)",
            (chunk_id, paper_id, revision_id, section_id, "legacy extracted paragraph"),
        )
    return {
        "project_id": project_id,
        "paper_id": paper_id,
        "revision_id": revision_id,
        "section_id": section_id,
        "chunk_id": chunk_id,
        "session_id": session_id,
        "parse_id": parse_id,
        "managed_path": managed_path,
        "outside_root": outside_root,
        "imported_path": imported_path,
    }


def test_update_paper_title_is_validated(tmp_path):
    with client(tmp_path) as api:
        values = add_paper(api, tmp_path)
        response = api.patch(
            f"/api/v1/papers/{values['paper_id']}", json={"title": "  Revised title  "}
        )
        assert response.status_code == 200, response.text
        with Session(api.app.state.engine) as db:
            assert db.get(Paper, values["paper_id"]).title == "Revised title"
        assert (
            api.patch(f"/api/v1/papers/{values['paper_id']}", json={"title": "  "}).status_code
            == 422
        )
        assert api.patch(f"/api/v1/papers/{uuid4()}", json={"title": "Missing"}).status_code == 404


def test_legacy_cleanup_preserves_notes_model_results_sources_and_backup(tmp_path):
    with client(tmp_path) as api:
        values = add_paper(api, tmp_path)
        response = api.delete(f"/api/v1/papers/{values['paper_id']}/legacy-content")
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["backup_file"].startswith("backups/before-paper-legacy-content-")
        backup_path = tmp_path / result["backup_file"]
        assert backup_path.is_file()
        with sqlite3.connect(backup_path) as backup:
            assert backup.execute("SELECT count(*) FROM chunks").fetchone()[0] == 1
            assert backup.execute("SELECT count(*) FROM chunk_fts").fetchone()[0] == 1

        with Session(api.app.state.engine) as db:
            assert db.get(Paper, values["paper_id"]) is not None
            revision = db.get(AttachmentRevision, values["revision_id"])
            assert revision is not None
            assert "旧本地解析内容已由用户清理，普通读取不会自动重建。" in revision.warnings
            assert db.get(Chunk, values["chunk_id"]) is None
            assert db.scalar(select(func.count()).select_from(EvidenceSpan)) == 0
            assert db.scalar(select(func.count()).select_from(DocumentParse)) == 0
            assert db.scalar(select(func.count()).select_from(ReadingDocumentProjection)) == 0
            assert db.scalar(select(func.count()).select_from(LiteCacheEntry)) == 0
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(Section)
                    .where(Section.id == values["section_id"])
                )
                == 1
            )
            assert db.scalar(select(func.count()).select_from(ReadingState)) == 1
            assert db.scalar(select(func.count()).select_from(ConceptUnderstanding)) == 1
            overview = db.scalar(select(PaperOverviewResult))
            assert overview.paper_card_json == {"summary": "saved overview note"}
            assert db.scalar(select(func.count()).select_from(PaperReadingResult)) == 1
            assert db.scalar(select(func.count()).select_from(LiteQARecord)) == 1
            assert db.scalar(select(func.count()).select_from(SectionGuideResult)) == 1
            assert db.scalar(select(func.count()).select_from(LiteTokenUsage)) == 1
            assert db.get(ImportSession, values["session_id"]) is not None
            assert db.get(LlmDocumentParse, values["parse_id"]) is not None
            assert db.scalar(select(LlmDocumentOutput)) is not None
        with sqlite3.connect(api.app.state.engine.url.database) as db:
            assert db.execute("SELECT count(*) FROM chunk_fts").fetchone()[0] == 0
        response = api.get(
            f"/api/v1/papers/{values['paper_id']}/reading-document"
            f"?document_version_id={values['revision_id']}"
        )
        assert response.status_code == 409
        with Session(api.app.state.engine) as db:
            assert db.scalar(select(func.count()).select_from(DocumentParse)) == 0
            assert db.scalar(select(func.count()).select_from(ReadingDocumentProjection)) == 0
            assert db.scalar(select(func.count()).select_from(Chunk)) == 0
        assert values["managed_path"].is_file()
        assert values["imported_path"].is_file()


def test_legacy_cleanup_rejects_queued_local_job(tmp_path):
    with client(tmp_path) as api:
        values = add_paper(api, tmp_path)
        with Session(api.app.state.engine) as db, db.begin():
            db.add(
                Job(
                    id=str(uuid4()),
                    project_id=values["project_id"],
                    kind="paper_reading",
                    payload={"paper_id": values["paper_id"]},
                    status="queued",
                    stage="queued",
                    attempt=0,
                    error=None,
                    result={},
                    created_at=now(),
                    updated_at=now(),
                )
            )

        response = api.delete(f"/api/v1/papers/{values['paper_id']}/legacy-content")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "PAPER_TASK_RUNNING"
        with Session(api.app.state.engine) as db:
            assert db.get(Chunk, values["chunk_id"]) is not None


def test_managed_file_candidate_rejects_attachments_root_alias(tmp_path, monkeypatch):
    from researchgraph.paper_management_api import _managed_file_candidate

    data_dir = tmp_path / "data"
    attachment_root = data_dir / "attachments"
    attachment_root.mkdir(parents=True)
    managed_file = attachment_root / "paper.pdf"
    managed_file.write_bytes(b"managed")
    external_root = tmp_path / "external"
    external_root.mkdir()
    original_resolve = Path.resolve

    def resolve_with_external_attachments(path, *args, **kwargs):
        if path == attachment_root:
            return external_root
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve_with_external_attachments)
    assert _managed_file_candidate(str(managed_file), data_dir) is None


def test_delete_paper_removes_all_associated_rows_and_only_managed_root_file(tmp_path):
    with client(tmp_path) as api:
        values = add_paper(api, tmp_path)
        response = api.delete(f"/api/v1/papers/{values['paper_id']}")
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["backup_file"].startswith("backups/before-paper-delete-")
        with sqlite3.connect(tmp_path / result["backup_file"]) as backup:
            assert backup.execute("SELECT count(*) FROM papers").fetchone()[0] == 1
            assert backup.execute("SELECT count(*) FROM llm_document_segments").fetchone()[0] == 1

        with Session(api.app.state.engine) as db:
            assert db.get(Paper, values["paper_id"]) is None
            assert db.get(AttachmentRevision, values["revision_id"]) is None
            assert db.get(ImportSession, values["session_id"]) is None
            assert db.get(LlmDocumentParse, values["parse_id"]) is None
            assert db.scalar(select(func.count()).select_from(LlmDocumentOutput)) == 0
            assert db.scalar(select(func.count()).select_from(PaperReadingResult)) == 0
            assert db.scalar(select(func.count()).select_from(PaperOverviewResult)) == 0
            assert db.scalar(select(func.count()).select_from(LiteQARecord)) == 0
            assert db.scalar(select(func.count()).select_from(SectionGuideResult)) == 0
            assert db.scalar(select(func.count()).select_from(LiteTokenUsage)) == 0
            assert db.scalar(select(func.count()).select_from(PaperSource)) == 0
            assert db.scalar(select(func.count()).select_from(ZoteroLink)) == 0
        assert not values["managed_path"].exists()
        assert values["outside_root"].is_file()
        assert values["imported_path"].is_file()
        assert api.delete(f"/api/v1/papers/{values['paper_id']}").status_code == 404
        paths = api.get("/openapi.json").json()["paths"]
        assert "/api/v1/papers/{paper_id}" in paths
        assert "patch" in paths["/api/v1/papers/{paper_id}"]
        assert "delete" in paths["/api/v1/papers/{paper_id}"]
        assert "delete" in paths["/api/v1/papers/{paper_id}/legacy-content"]
