import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from researchgraph.import_plan_models import ImportPlanItem, ImportSession
from researchgraph.model_capabilities import ModelCapabilities
from researchgraph.model_document_api import (
    execute_document_parse,
    execute_document_postprocess,
    materialize_document_parse,
)
from researchgraph.model_document_contracts import ModelDocumentParseInput
from researchgraph.model_document_models import LlmDocumentOutput, LlmDocumentSegment
from researchgraph.models import Base, Job, Project, now
from researchgraph.providers import ProviderError, require_document_capability
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class TextProvider:
    capabilities = ModelCapabilities(document_input="text")


class ImageProvider:
    capabilities = ModelCapabilities(
        document_input="image", multimodal=True, document_transport="chat_file"
    )


class SyntheticPdfProvider:
    capabilities = ModelCapabilities(document_input="pdf", document_transport="chat_file")

    def __init__(self, *, require_multimodal: bool = False) -> None:
        self.require_multimodal = require_multimodal
        self.calls: list[dict[str, object]] = []

    async def complete_document(self, payload: dict[str, object]) -> str:
        self.calls.append(payload)
        return (
            '{"parse_version":"llm-document-1","modality":"pdf",'
            '"segments":['
            '{"chapter_ref":"ch-1","chapter_title":"Introduction",'
            '"kind":"paragraph","text":"Synthetic paragraph."},'
            '{"chapter_ref":"ch-1","chapter_title":"Introduction",'
            '"kind":"formula","ordinal":1,"text":"E = mc^2",'
            '"latex":"E = mc^2","status":"needs_review"},'
            '{"chapter_ref":"ch-1","chapter_title":"Introduction",'
            '"kind":"table","ordinal":2,"raw_table_text":"A | B\\n1 | 2",'
            '"status":"degraded"}'
            "]} "
        ).strip()

    async def complete(
        self, prompt: str, data: dict[str, object], schema: dict[str, object]
    ) -> str:
        item_kind = str(data["item_kind"])
        translations = (
            '[{"chapter_ref":"ch-1","source_text":"Synthetic paragraph.",'
            '"translation_zh":"合成段落。"}]'
            if item_kind == "translation"
            else "[]"
        )
        return (
            '{"item_kind":"' + item_kind + '","summary":"Synthetic summary",'
            '"sections":[],"contributions":[],"findings":[],'
            '"limitations":[],"translations":' + translations + "}"
        )


def _database(tmp_path: Path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'test.sqlite3').as_posix()}")
    Base.metadata.create_all(engine)
    return engine


def test_document_capability_rejects_pdf_without_native_support():
    with pytest.raises(ProviderError, match="未声明 PDF"):
        require_document_capability(TextProvider(), "pdf")
    require_document_capability(ImageProvider(), "image", require_multimodal=True)


def test_materialize_model_document_generates_ids_and_keeps_legacy_tables_separate(tmp_path):
    engine = _database(tmp_path)
    project_id, session_id = str(uuid4()), str(uuid4())
    with Session(engine) as db, db.begin():
        db.add(Project(id=project_id, name="fixture", description="", created_at=now()))
        db.add(
            ImportSession(
                id=session_id,
                project_id=project_id,
                source_kind="pdf",
                selection_id="selection-1",
                source_snapshot={"file_name": "fixture.pdf"},
                plan={"modality": "text"},
                status="planned",
                created_at=now(),
                updated_at=now(),
            )
        )
        db.add(
            ImportPlanItem(
                id=str(uuid4()),
                session_id=session_id,
                item_kind="document_parse",
                status="planned",
                config={"modality": "text"},
                attempt=0,
                created_at=now(),
                updated_at=now(),
            )
        )
        body = ModelDocumentParseInput.model_validate(
            {
                "parse_version": "llm-document-1",
                "modality": "text",
                "segments": [
                    {
                        "chapter_ref": "intro",
                        "chapter_title": "Introduction",
                        "chapter_order": 0,
                        "ordinal": 0,
                        "kind": "paragraph",
                        "text": "A paragraph.",
                    },
                    {
                        "chapter_ref": "intro",
                        "chapter_title": "Introduction",
                        "chapter_order": 0,
                        "ordinal": 1,
                        "kind": "formula",
                        "text": "E = mc^2",
                        "status": "needs_review",
                    },
                    {
                        "chapter_ref": "intro",
                        "chapter_title": "Introduction",
                        "chapter_order": 0,
                        "ordinal": 2,
                        "kind": "table",
                        "raw_table_text": "A | B\\n1 | 2",
                        "status": "degraded",
                    },
                ],
            }
        )
        parse = materialize_document_parse(
            db,
            session_id,
            body,
            provider_id="fixture",
            model_id="fixture-model",
            raw_response=body.model_dump(),
        )
        db.flush()
        segments = db.query(LlmDocumentSegment).filter_by(parse_id=parse.id).all()
        item = db.query(ImportPlanItem).filter_by(session_id=session_id).one()
        saved_session = db.get(ImportSession, session_id)
        assert len(segments) == 3
        assert len({segment.id for segment in segments}) == 3
        assert parse.status == "succeeded"
        assert item.status == "succeeded"
        assert item.result == {
            "parse_id": parse.id,
            "parse_version": "llm-document-1",
            "segment_count": 3,
            "warnings": [],
        }
        assert saved_session is not None and saved_session.status == "succeeded"
        assert db.query(Job).count() == 0


def _queued_document_job(
    engine,
    tmp_path: Path,
    *,
    modality: str = "pdf",
    require_multimodal: bool = False,
) -> tuple[str, str]:
    project_id, session_id, job_id = (str(uuid4()) for _ in range(3))
    path = tmp_path / "synthetic.pdf"
    path.write_bytes(b"%PDF-synthetic")
    with Session(engine) as db, db.begin():
        db.add(Project(id=project_id, name="fixture", description="", created_at=now()))
        db.add(
            ImportSession(
                id=session_id,
                project_id=project_id,
                source_kind="pdf",
                selection_id="selection-synthetic",
                source_snapshot={"file_name": path.name},
                plan={"modality": modality, "require_multimodal": require_multimodal},
                status="queued",
                created_at=now(),
                updated_at=now(),
            )
        )
        db.add(
            ImportPlanItem(
                id=str(uuid4()),
                session_id=session_id,
                item_kind="document_parse",
                status="queued",
                config={"modality": modality},
                job_id=job_id,
                attempt=0,
                created_at=now(),
                updated_at=now(),
            )
        )
        db.add(
            Job(
                id=job_id,
                kind="llm_document_parse",
                project_id=project_id,
                payload={
                    "import_session_id": session_id,
                    "path": str(path),
                    "modality": modality,
                    "require_multimodal": require_multimodal,
                },
                status="running",
                attempt=0,
                created_at=now(),
                updated_at=now(),
            )
        )
    return session_id, job_id


def test_synthetic_pdf_provider_exports_paragraph_formula_and_table(tmp_path):
    engine = _database(tmp_path)
    session_id, job_id = _queued_document_job(engine, tmp_path)
    provider = SyntheticPdfProvider()

    asyncio.run(execute_document_parse(engine, job_id, tmp_path, provider=provider))

    with Session(engine) as db:
        segments = list(
            db.query(LlmDocumentSegment)
            .order_by(LlmDocumentSegment.chapter_order, LlmDocumentSegment.ordinal)
            .all()
        )
        saved_job = db.get(Job, job_id)
        saved_session = db.get(ImportSession, session_id)
        assert saved_job is not None and saved_job.status == "succeeded"
        assert saved_session is not None and saved_session.status == "succeeded"
        assert [segment.kind for segment in segments] == ["paragraph", "formula", "table"]
        assert segments[1].latex == "E = mc^2"
        assert segments[2].raw_table_text is not None
    assert len(provider.calls) == 1


def test_model_first_pdf_without_provider_fails_without_local_parser_fallback(tmp_path):
    engine = _database(tmp_path)
    session_id, job_id = _queued_document_job(engine, tmp_path)

    with pytest.raises(ProviderError, match="未回退本地解析"):
        asyncio.run(execute_document_parse(engine, job_id, tmp_path))

    with Session(engine) as db:
        saved_job = db.get(Job, job_id)
        saved_session = db.get(ImportSession, session_id)
        assert saved_job is not None and saved_job.status == "failed"
        assert saved_session is not None and saved_session.status == "failed"
        assert db.query(LlmDocumentSegment).count() == 0


def test_required_multimodal_pauses_before_synthetic_provider_call(tmp_path):
    engine = _database(tmp_path)
    session_id, job_id = _queued_document_job(engine, tmp_path, require_multimodal=True)
    provider = SyntheticPdfProvider()

    with pytest.raises(ProviderError, match="多模态"):
        asyncio.run(execute_document_parse(engine, job_id, tmp_path, provider=provider))

    with Session(engine) as db:
        saved_job = db.get(Job, job_id)
        saved_session = db.get(ImportSession, session_id)
        assert saved_job is not None and saved_job.status == "paused"
        assert saved_session is not None and saved_session.status == "paused"
        assert db.query(LlmDocumentSegment).count() == 0
    assert provider.calls == []


def test_successful_parse_queues_independent_model_outputs(tmp_path):
    engine = _database(tmp_path)
    project_id, session_id, parse_job_id = (str(uuid4()) for _ in range(3))
    with Session(engine) as db, db.begin():
        db.add(Project(id=project_id, name="fixture", description="", created_at=now()))
        db.add(
            ImportSession(
                id=session_id,
                project_id=project_id,
                source_kind="pdf",
                selection_id="selection",
                source_snapshot={"file_name": "fixture.pdf", "paper_id": str(uuid4())},
                plan={
                    "modality": "text",
                    "overview": True,
                    "reading": True,
                    "translation_mode": "full",
                    "allow_network": True,
                },
                status="running",
                created_at=now(),
                updated_at=now(),
            )
        )
        db.add(
            ImportPlanItem(
                id=str(uuid4()),
                session_id=session_id,
                item_kind="document_parse",
                status="running",
                config={},
                job_id=parse_job_id,
                attempt=0,
                created_at=now(),
                updated_at=now(),
            )
        )
        for item_kind in ("paper_overview", "paper_reading", "translation"):
            db.add(
                ImportPlanItem(
                    id=str(uuid4()),
                    session_id=session_id,
                    item_kind=item_kind,
                    status="planned",
                    config={},
                    attempt=0,
                    created_at=now(),
                    updated_at=now(),
                )
            )
        db.add(
            Job(
                id=parse_job_id,
                kind="llm_document_parse",
                project_id=project_id,
                payload={"import_session_id": session_id, "modality": "text", "source_text": "{}"},
                status="running",
                created_at=now(),
                updated_at=now(),
            )
        )
        body = ModelDocumentParseInput.model_validate(
            {
                "parse_version": "llm-document-1",
                "modality": "text",
                "segments": [
                    {
                        "chapter_ref": "intro",
                        "chapter_title": "Intro",
                        "kind": "paragraph",
                        "text": "Text",
                    }
                ],
            }
        )
        materialize_document_parse(db, session_id, body)
        db.flush()
        jobs = db.query(Job).filter(Job.kind == "llm_document_postprocess").all()
        assert len(jobs) == 3
        assert {job.payload["item_kind"] for job in jobs} == {
            "paper_overview",
            "paper_reading",
            "translation",
        }
        assert db.query(LlmDocumentOutput).count() == 0
        first = jobs[0]
        first_job_id = first.id
        first_item_kind = first.payload["item_kind"]
        first.status = "running"
    provider = SyntheticPdfProvider()
    asyncio.run(execute_document_postprocess(engine, first_job_id, tmp_path, provider=provider))
    with Session(engine) as db:
        output = db.query(LlmDocumentOutput).one()
        assert output.item_kind == first_item_kind
        assert output.status == "succeeded"
        assert db.get(Job, first_job_id).status == "succeeded"
