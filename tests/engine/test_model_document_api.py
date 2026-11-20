import asyncio
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from researchgraph.import_plan_models import ImportPlanItem, ImportSession
from researchgraph.model_capabilities import ModelCapabilities
from researchgraph.model_document_api import (
    execute_document_parse,
    execute_document_postprocess,
    materialize_document_parse,
    recover_document_imports,
    synchronize_import_job,
)
from researchgraph.model_document_contracts import ModelDocumentParseInput
from researchgraph.model_document_models import (
    LlmDocumentOutput,
    LlmDocumentParse,
    LlmDocumentSegment,
)
from researchgraph.models import Base, Job, Project, now
from researchgraph.providers import ConfiguredProvider, ProviderError, require_document_capability
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


@pytest.mark.parametrize("payload_consent", [True, False])
def test_frozen_provider_values_survive_session_close_and_phases_are_visible(
    tmp_path, monkeypatch, payload_consent
):
    from researchgraph import model_document_api

    engine = _database(tmp_path)
    session_id, job_id = _queued_document_job(engine, tmp_path)
    with Session(engine) as db, db.begin():
        db.get(ImportSession, session_id).plan = {"modality": "pdf", "allow_network": True}
        job = db.get(Job, job_id)
        job.payload = {**job.payload, "provider_snapshot": {"profile_id": "synthetic"}}
        if payload_consent:
            job.payload = {**job.payload, "allow_network": True}
    phases = []

    def observe(expected):
        with Session(engine) as db:
            job = db.get(Job, job_id)
            assert job.status == "running" and job.stage == expected
        phases.append(expected)

    class ObservedProvider(SyntheticPdfProvider):
        async def complete_document(self, payload):
            observe("model_parsing")
            return await super().complete_document(payload)

    provider = ObservedProvider()

    def from_snapshot(snapshot, data_dir, allow_network):
        observe("preparing_provider")
        assert snapshot == {"profile_id": "synthetic"}
        assert data_dir == tmp_path and allow_network is True
        return provider

    decode = model_document_api._decode_provider_result
    publish = model_document_api.materialize_document_parse

    def decode_result(raw):
        observe("validating_document")
        return decode(raw)

    def publish_result(*args, **kwargs):
        observe("saving_document")
        return publish(*args, **kwargs)

    monkeypatch.setattr("researchgraph.model_settings.from_snapshot", from_snapshot)
    monkeypatch.setattr(model_document_api, "_decode_provider_result", decode_result)
    monkeypatch.setattr(model_document_api, "materialize_document_parse", publish_result)

    asyncio.run(execute_document_parse(engine, job_id, tmp_path))

    assert phases == [
        "preparing_provider",
        "model_parsing",
        "validating_document",
        "saving_document",
    ]
    with Session(engine) as db:
        assert db.get(Job, job_id).status == "succeeded"
        assert db.get(ImportSession, session_id).status == "succeeded"
        assert db.query(LlmDocumentParse).count() == 1


@pytest.mark.parametrize("failure_step", ["attachment", "provider", "publication"])
def test_unexpected_parse_errors_end_job_session_and_plan_item(tmp_path, monkeypatch, failure_step):
    engine = _database(tmp_path)
    session_id, job_id = _queued_document_job(engine, tmp_path)
    provider = SyntheticPdfProvider()

    def fail(*_args, **_kwargs):
        raise OSError("synthetic I/O failure")

    if failure_step == "attachment":
        with Session(engine) as db, db.begin():
            job = db.get(Job, job_id)
            job.kind = "zotero_import"
            job.payload = {
                "import_session_id": session_id,
                "library": "users/0",
                "attachment_key": "ATTACH12",
                "modality": "pdf",
            }
        monkeypatch.setattr("researchgraph.integrations.ZoteroAdapter.attachment_path", fail)
    elif failure_step == "provider":

        async def provider_failure(_payload):
            fail()

        monkeypatch.setattr(provider, "complete_document", provider_failure)
    else:
        monkeypatch.setattr("researchgraph.model_document_api.materialize_document_parse", fail)

    with pytest.raises(OSError, match="synthetic I/O failure"):
        asyncio.run(execute_document_parse(engine, job_id, tmp_path, provider=provider))

    # A terminal Job must neither repeat the request nor create another parse.
    asyncio.run(execute_document_parse(engine, job_id, tmp_path, provider=provider))
    with Session(engine) as db:
        job = db.get(Job, job_id)
        session = db.get(ImportSession, session_id)
        item = db.query(ImportPlanItem).filter_by(session_id=session_id).one()
        parse = db.query(LlmDocumentParse).one()
        assert job.status == session.status == item.status == parse.status == "failed"
        assert job.stage == "failed"
        assert job.error == session.error == item.error == parse.error
        assert item.result == {"parse_id": parse.id, "error_code": parse.error_code}
        assert parse.error_code == "MODEL_DOCUMENT_EXECUTION_FAILED"


def test_provider_configuration_failure_retains_specific_error_once(tmp_path, monkeypatch):
    engine = _database(tmp_path)
    session_id, job_id = _queued_document_job(engine, tmp_path)
    with Session(engine) as db, db.begin():
        job = db.get(Job, job_id)
        job.payload = {
            **job.payload,
            "provider_snapshot": {"profile_id": "synthetic"},
            "allow_network": True,
        }

    def invalid_snapshot(*_args):
        raise ValueError("synthetic unavailable profile")

    monkeypatch.setattr("researchgraph.model_settings.from_snapshot", invalid_snapshot)
    with pytest.raises(ProviderError, match="synthetic unavailable profile"):
        asyncio.run(execute_document_parse(engine, job_id, tmp_path))
    with Session(engine) as db:
        parse = db.query(LlmDocumentParse).one()
        assert parse.error_code == "MODEL_DOCUMENT_PROVIDER_CONFIG_ERROR"
        assert db.get(Job, job_id).status == db.get(ImportSession, session_id).status == "failed"


@pytest.mark.parametrize("attachment_exists", [True, False])
def test_cancelled_while_resolving_attachment_never_prepares_or_calls_model(
    tmp_path, monkeypatch, attachment_exists
):
    engine = _database(tmp_path)
    session_id, job_id = _queued_document_job(engine, tmp_path)
    with Session(engine) as db, db.begin():
        job = db.get(Job, job_id)
        job.kind = "zotero_import"
        job.payload = {
            "import_session_id": session_id,
            "library": "users/0",
            "attachment_key": "ATTACH12",
            "modality": "pdf",
            "provider_snapshot": {"profile_id": "synthetic"},
            "allow_network": True,
        }
    provider = SyntheticPdfProvider()
    provider_preparations = []

    def resolve_after_cancellation(*_args):
        # This runs in the awaited attachment thread, matching cancellation
        # while Zotero is resolving/downloading the selected source.
        with Session(engine) as db, db.begin():
            job = db.get(Job, job_id)
            assert job.stage == "document_source"
            job.status, job.stage, job.error = "cancelled", "interrupted", "user cancelled"
            synchronize_import_job(db, job)
        return tmp_path / ("synthetic.pdf" if attachment_exists else "missing.pdf")

    def prepare_provider(*_args):
        provider_preparations.append(True)
        return provider

    monkeypatch.setattr(
        "researchgraph.integrations.ZoteroAdapter.attachment_path", resolve_after_cancellation
    )
    monkeypatch.setattr("researchgraph.model_settings.from_snapshot", prepare_provider)
    asyncio.run(execute_document_parse(engine, job_id, tmp_path))

    assert provider_preparations == provider.calls == []
    with Session(engine) as db:
        job = db.get(Job, job_id)
        item = db.query(ImportPlanItem).filter_by(session_id=session_id).one()
        assert job.status == "cancelled" and job.stage == "interrupted"
        assert job.error == "user cancelled"
        assert item.status == db.get(ImportSession, session_id).status == "interrupted"
        assert "path" not in job.payload and "paper_id" not in job.payload
        assert db.query(LlmDocumentParse).count() == db.query(LlmDocumentSegment).count() == 0
        assert db.query(LlmDocumentOutput).count() == 0


@pytest.mark.parametrize("terminal_status", ["cancelled", "failed", "interrupted"])
@pytest.mark.parametrize("checkpoint", ["provider_setup", "capability_check"])
def test_terminal_job_before_document_request_never_calls_model_or_publishes(
    tmp_path, monkeypatch, terminal_status, checkpoint
):
    engine = _database(tmp_path)
    session_id, job_id = _queued_document_job(engine, tmp_path)
    with Session(engine) as db, db.begin():
        job = db.get(Job, job_id)
        job.payload = {
            **job.payload,
            "provider_snapshot": {"profile_id": "synthetic"},
            "allow_network": True,
        }
    provider = SyntheticPdfProvider()

    def terminate_job():
        with Session(engine) as db, db.begin():
            job = db.get(Job, job_id)
            job.status, job.stage, job.error = terminal_status, "interrupted", "terminal outcome"
            synchronize_import_job(db, job)

    def prepare_provider(*_args):
        if checkpoint == "provider_setup":
            terminate_job()
        return provider

    def check_capability(*_args, **_kwargs):
        if checkpoint == "capability_check":
            terminate_job()

    monkeypatch.setattr("researchgraph.model_settings.from_snapshot", prepare_provider)
    monkeypatch.setattr(
        "researchgraph.model_document_api.require_document_capability", check_capability
    )
    asyncio.run(execute_document_parse(engine, job_id, tmp_path))

    assert provider.calls == []
    with Session(engine) as db:
        job = db.get(Job, job_id)
        assert job.status == terminal_status and job.stage == "interrupted"
        assert job.error == "terminal outcome"
        expected = "interrupted" if terminal_status == "cancelled" else terminal_status
        assert db.get(ImportSession, session_id).status == expected
        assert db.query(ImportPlanItem).filter_by(session_id=session_id).one().status == expected
        assert db.query(LlmDocumentParse).count() == db.query(LlmDocumentSegment).count() == 0
        assert db.query(LlmDocumentOutput).count() == 0


@pytest.mark.parametrize("terminal_status", ["cancelled", "failed", "interrupted"])
@pytest.mark.parametrize("checkpoint", ["read_bytes", "client_enter"])
def test_configured_document_cancel_during_local_setup_never_posts(
    tmp_path, monkeypatch, terminal_status, checkpoint
):
    engine = _database(tmp_path)
    session_id, job_id = _queued_document_job(engine, tmp_path)
    provider = ConfiguredProvider(
        base_url="https://synthetic.example/v1",
        model="synthetic-pdf",
        key="",
        parameters={"capabilities": {"document_input": "pdf", "document_transport": "chat_file"}},
    )
    posts = []
    checkpoints = []
    from researchgraph import document_transport

    original_read = document_transport.read_pdf_bytes
    original_client = httpx.AsyncClient

    def terminate_job():
        with Session(engine) as db, db.begin():
            job = db.get(Job, job_id)
            assert job.status == "running" and job.stage in {
                "model_parsing",
                "document_rendering",
                "document_connecting",
            }
            job.status, job.stage, job.error = terminal_status, "interrupted", "stopped locally"
            synchronize_import_job(db, job)
        checkpoints.append(checkpoint)

    def read_and_cancel(path):
        content = original_read(path)
        if checkpoint == "read_bytes" and path == tmp_path / "synthetic.pdf":
            terminate_job()
        return content

    def no_network(request):
        posts.append(request)
        raise AssertionError("A terminal document Job must not send an HTTP request")

    class LocalClient(original_client):
        async def __aenter__(self):
            result = await super().__aenter__()
            if checkpoint == "client_enter":
                terminate_job()
            return result

    monkeypatch.setattr(document_transport, "read_pdf_bytes", read_and_cancel)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: LocalClient(**kw, transport=httpx.MockTransport(no_network)),
    )
    asyncio.run(execute_document_parse(engine, job_id, tmp_path, provider=provider))

    assert checkpoints == [checkpoint] and posts == []
    assert provider.usage == {}
    with Session(engine) as db:
        job = db.get(Job, job_id)
        assert job.status == terminal_status and job.stage == "interrupted"
        assert job.error == "stopped locally"
        expected = "interrupted" if terminal_status == "cancelled" else terminal_status
        assert db.get(ImportSession, session_id).status == expected
        assert db.query(ImportPlanItem).filter_by(session_id=session_id).one().status == expected
        assert db.query(LlmDocumentParse).count() == db.query(LlmDocumentSegment).count() == 0
        assert db.query(LlmDocumentOutput).count() == 0
        assert "before_send" not in json.dumps(job.payload)


@pytest.mark.parametrize("cancel_after_dispatch", [False, True])
def test_configured_document_guard_is_local_and_does_not_recall_dispatched_request(
    tmp_path, monkeypatch, cancel_after_dispatch
):
    engine = _database(tmp_path)
    session_id, job_id = _queued_document_job(engine, tmp_path)
    provider = ConfiguredProvider(
        base_url="https://synthetic.example/v1",
        model="synthetic-pdf",
        key="",
        parameters={"capabilities": {"document_input": "pdf", "document_transport": "chat_file"}},
    )
    requests = []
    original_client = httpx.AsyncClient

    def response(request):
        requests.append(json.loads(request.content))
        if cancel_after_dispatch:
            with Session(engine) as db, db.begin():
                job = db.get(Job, job_id)
                job.status = "cancelled"
                synchronize_import_job(db, job)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "parse_version": "llm-document-1",
                                    "modality": "pdf",
                                    "segments": [
                                        {
                                            "chapter_ref": "intro",
                                            "chapter_title": "Introduction",
                                            "kind": "paragraph",
                                            "text": "Synthetic paragraph.",
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ],
            },
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original_client(**kw, transport=httpx.MockTransport(response)),
    )
    asyncio.run(execute_document_parse(engine, job_id, tmp_path, provider=provider))

    assert len(requests) == 1
    assert "before_send" not in json.dumps(requests)
    with Session(engine) as db:
        job = db.get(Job, job_id)
        assert "before_send" not in json.dumps(job.payload)
        if cancel_after_dispatch:
            assert job.status == "cancelled"
            assert db.get(ImportSession, session_id).status == "interrupted"
            assert db.query(LlmDocumentParse).count() == db.query(LlmDocumentSegment).count() == 0
        else:
            assert job.status == db.get(ImportSession, session_id).status == "succeeded"
            assert db.query(LlmDocumentParse).count() == db.query(LlmDocumentSegment).count() == 1


@pytest.mark.parametrize("terminal_status", ["failed", "interrupted", "cancelled"])
def test_recovery_aligns_stale_active_import_plans_without_requeue(tmp_path, terminal_status):
    engine = _database(tmp_path)
    session_id, job_id = _queued_document_job(engine, tmp_path)
    with Session(engine) as db, db.begin():
        db.get(ImportSession, session_id).status = "running"
        item = db.query(ImportPlanItem).filter_by(session_id=session_id).one()
        item.status = "running"
        job = db.get(Job, job_id)
        job.status, job.error = terminal_status, "synthetic old failure"

    recover_document_imports(engine)
    recover_document_imports(engine)

    with Session(engine) as db:
        expected = "interrupted" if terminal_status == "cancelled" else terminal_status
        item = db.query(ImportPlanItem).filter_by(session_id=session_id).one()
        assert item.status == db.get(ImportSession, session_id).status == expected
        assert item.error == "synthetic old failure"
        assert db.get(Job, job_id).status == terminal_status
        assert db.query(LlmDocumentParse).count() == db.query(LlmDocumentSegment).count() == 0


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
        assert saved_job is not None and saved_job.status == "failed"
        assert saved_job.stage == "paused"
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


@pytest.mark.parametrize("provider_fails", [False, True])
def test_cancelled_postprocessing_keeps_terminal_state_after_provider_returns(
    tmp_path, provider_fails
):
    engine = _database(tmp_path)
    session_id, parse_job_id = _queued_document_job(engine, tmp_path)
    with Session(engine) as db, db.begin():
        session = db.get(ImportSession, session_id)
        session.plan = {"modality": "pdf", "reading": True}
        session.source_snapshot = {"paper_id": str(uuid4())}
        db.add(
            ImportPlanItem(
                id=str(uuid4()),
                session_id=session_id,
                item_kind="paper_reading",
                status="planned",
                config={},
                attempt=0,
                created_at=now(),
                updated_at=now(),
            )
        )
    asyncio.run(
        execute_document_parse(engine, parse_job_id, tmp_path, provider=SyntheticPdfProvider())
    )
    with Session(engine) as db, db.begin():
        job = db.query(Job).filter_by(kind="llm_document_postprocess").one()
        job.status, job_id = "running", job.id

    class CancelledProvider(SyntheticPdfProvider):
        async def complete(self, prompt, data, schema):
            with Session(engine) as db, db.begin():
                job = db.get(Job, job_id)
                job.status = "cancelled"
                synchronize_import_job(db, job)
            if provider_fails:
                raise OSError("synthetic error after cancellation")
            return await super().complete(prompt, data, schema)

    asyncio.run(
        execute_document_postprocess(engine, job_id, tmp_path, provider=CancelledProvider())
    )

    with Session(engine) as db:
        job = db.get(Job, job_id)
        session = db.get(ImportSession, session_id)
        item = (
            db.query(ImportPlanItem)
            .filter_by(session_id=session_id, item_kind="paper_reading")
            .one()
        )
        output = db.query(LlmDocumentOutput).one()
        assert job.status == "cancelled"
        assert session.status == item.status == "interrupted"
        assert output.status == "failed"
        assert output.error_code == "MODEL_DOCUMENT_JOB_INTERRUPTED"
        assert output.output_json is None
