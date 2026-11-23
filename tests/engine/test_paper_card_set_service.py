"""Local card generation uses production FK/transactions and anonymous parsed text."""

import asyncio
import json
from uuid import uuid4

import pymupdf
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from researchgraph.core import KnowledgeError
from researchgraph.document_structure import apply_structure
from researchgraph.knowledge_connection_models import KnowledgeConnectionRun
from researchgraph.knowledge_extraction_models import KnowledgeExtractionRun
from researchgraph.knowledge_library_models import KnowledgeLibrary
from researchgraph.lite_models import LiteTokenUsage
from researchgraph.lite_usage import aggregate_usage
from researchgraph.model_capabilities import ModelCapabilities
from researchgraph.models import AttachmentRevision, Base, Chunk, Job, Paper, Project, now
from researchgraph.paper_card_set_contracts import (
    SCHEMA_VERSION,
    SYSTEM_PROMPT,
    paper_card_set_schema,
)
from researchgraph.paper_card_set_service import card_overview_view
from researchgraph.paper_overview_api import (
    execute_overview,
    recover_overviews,
    register_paper_overview_api,
)
from researchgraph.paper_overview_models import PaperOverviewResult
from researchgraph.pdf_structure import parse_structure
from researchgraph.providers import ConfiguredProvider, ProviderError
from researchgraph.storage import make_engine
from sqlalchemy import select
from sqlalchemy.orm import Session


def fixture(tmp_path, monkeypatch):
    from researchgraph import model_settings

    snapshot = {"provider": "synthetic", "model": "synthetic", "parameters": {}}
    monkeypatch.setattr(model_settings, "snapshot_for", lambda *args: dict(snapshot))
    engine = make_engine(tmp_path)
    Base.metadata.create_all(engine)
    project_id, paper_id, revision_id = (str(uuid4()) for _ in range(3))
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((40, 90), "1 Methods", fontsize=15, fontname="hebo")
        page.insert_text((40, 130), "The authors propose a synthetic method for reading.")
        structure = parse_structure(pdf)
    with Session(engine) as db, db.begin():
        db.add(Project(id=project_id, name="Synthetic", description="", created_at=now()))
        db.flush()
        db.add(Paper(id=paper_id, project_id=project_id, title="Synthetic paper", created_at=now()))
        db.flush()
        db.add(
            AttachmentRevision(
                id=revision_id,
                paper_id=paper_id,
                sha256="c" * 64,
                parser_version="synthetic",
                page_count=1,
                warnings=[],
                created_at=now(),
            )
        )
        db.flush()
        for block in structure["blocks"]:
            db.add(
                Chunk(
                    id=str(uuid4()),
                    revision_id=revision_id,
                    page_index=block["page_index"],
                    page_label="1",
                    block_index=block["block_index"],
                    text=block["text"],
                    bbox=block["bbox"],
                )
            )
        db.flush()
        apply_structure(db, revision_id, "c" * 64, structure)
    app = FastAPI()

    @app.exception_handler(KnowledgeError)
    async def error_handler(request, error):
        return JSONResponse(status_code=409, content={"code": error.code})

    register_paper_overview_api(app, lambda: engine, tmp_path)
    return engine, TestClient(app), paper_id, revision_id, snapshot


def response(context):
    source = context["sources"][0]
    return {
        "schema_version": SCHEMA_VERSION,
        "article_overview_zh": "论文提出一种合成方法。",
        "overview_card_ids": ["c1"],
        "card_set_intro_zh": "先阅读方法卡片。",
        "coverage_notes": ["未发现作者自述局限。"],
        "cards": [
            {
                "id": "c1",
                "kind": "key_concept",
                "attribution": "AUTHOR",
                "title_zh": "合成方法",
                "title_en": None,
                "body_zh": "作者提出一种合成方法。",
                "reading_guide_zh": "核对原文中的适用条件。",
                "evidence": [
                    {
                        "source_id": source["source_id"],
                        "quote_en": source["text"],
                        "occurrence_index": 0,
                        "translation_zh": "作者提出一种合成方法。",
                    }
                ],
            }
        ],
    }


class Provider:
    name = model = "synthetic"
    usage = {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
    request_metadata = {"status": 200}

    def __init__(self, mutate=None, during=None):
        self.calls = 0
        self.mutate, self.during = mutate, during
        self.raw = None

    async def complete(self, prompt, context, schema):
        self.calls += 1
        assert prompt == SYSTEM_PROMPT and schema == paper_card_set_schema()
        value = response(context)
        if self.mutate:
            self.mutate(value)
        if self.during:
            self.during()
        self.raw = json.dumps(value, ensure_ascii=False)
        return self.raw


def queue(values, **extra):
    _engine, client, paper_id, revision_id, _snapshot = values
    result = client.post(
        f"/api/v1/papers/{paper_id}/overview/generate",
        json={"document_version_id": revision_id, "allow_network": True, **extra},
    )
    assert result.status_code == 200, result.text
    return result.json()


def test_local_complete_cache_force_config_and_read_only_get(tmp_path, monkeypatch):
    values = fixture(tmp_path, monkeypatch)
    engine, client, paper_id, revision_id, snapshot = values
    endpoint = f"/api/v1/papers/{paper_id}/overview"
    assert client.get(endpoint).json() is None
    assert (
        client.post(endpoint + "/generate", json={"document_version_id": revision_id}).status_code
        == 409
    )
    pending = queue(values)
    assert queue(values)["id"] == pending["id"]
    provider = Provider()
    asyncio.run(execute_overview(engine, pending["job_id"], tmp_path, provider=provider))
    result = client.get(endpoint).json()
    assert result["status"] == "COMPLETED" and result["graph"] is None
    assert result["card_set"]["cards"][0]["evidence"][0]["position"]["chapter_title"] == "1 Methods"
    assert result["card_set"]["semantic_accuracy"] == "unverified"
    cached = queue(values)
    assert cached["id"] == pending["id"] and cached["cache_hit"] and cached["usage"]["calls"] == 0
    assert provider.calls == 1
    with Session(engine) as db:
        usage = list(db.scalars(select(LiteTokenUsage)))
        assert len(usage) == 2 and sum(row.cache_hit for row in usage) == 1
        assert db.get(Job, pending["job_id"]).status == "succeeded"
        assert db.get(PaperOverviewResult, pending["id"]).raw_output == provider.raw
    assert queue(values, force_regenerate=True)["id"] != pending["id"]
    snapshot["parameters"] = {"temperature": 0.5}
    assert queue(values)["id"] != pending["id"]


@pytest.mark.parametrize("mutation", ["extra", "quote"])
def test_bad_local_response_retains_raw_and_usage_no_retry(tmp_path, monkeypatch, mutation):
    values = fixture(tmp_path, monkeypatch)
    engine, _client, _paper, _revision, _snapshot = values
    pending = queue(values)

    def mutate(value):
        if mutation == "extra":
            value["graph"] = {}
        else:
            value["cards"][0]["evidence"][0]["quote_en"] = "Not from this paper."

    provider = Provider(mutate)
    asyncio.run(execute_overview(engine, pending["job_id"], tmp_path, provider=provider))
    asyncio.run(execute_overview(engine, pending["job_id"], tmp_path, provider=provider))
    assert queue(values)["id"] == pending["id"]
    with Session(engine) as db:
        result = db.get(PaperOverviewResult, pending["id"])
        usage = db.scalar(select(LiteTokenUsage))
        assert result.status == "FAILED" and result.raw_output == provider.raw
        assert result.usage_json["total_tokens"] == usage.total_tokens == 30
        assert result.paper_card_json is None and result.graph_json is None
    assert provider.calls == 1
    assert queue(values, retry_failed=True)["id"] != pending["id"]


@pytest.mark.parametrize("when", ["before", "during"])
def test_source_changes_never_publish_or_resend(tmp_path, monkeypatch, when):
    values = fixture(tmp_path, monkeypatch)
    engine, _client, paper_id, _revision, _snapshot = values
    pending = queue(values)

    def drift():
        with Session(engine) as db, db.begin():
            db.get(Paper, paper_id).title = "Changed anonymous title"

    if when == "before":
        drift()
    provider = Provider(during=drift if when == "during" else None)
    asyncio.run(execute_overview(engine, pending["job_id"], tmp_path, provider=provider))
    with Session(engine) as db:
        row = db.get(PaperOverviewResult, pending["id"])
        assert row.status == "FAILED" and row.error_code == "CARD_SOURCE_CHANGED"
        assert row.paper_card_json is None
        assert row.raw_output == provider.raw
        assert db.query(LiteTokenUsage).count() == (0 if when == "before" else 1)
    assert provider.calls == (0 if when == "before" else 1)


def test_restart_retires_sent_task_and_never_resends(tmp_path, monkeypatch):
    values = fixture(tmp_path, monkeypatch)
    engine, _client, _paper, _revision, _snapshot = values
    pending = queue(values)
    with Session(engine) as db, db.begin():
        db.get(Job, pending["job_id"]).status = "running"
        row = db.get(PaperOverviewResult, pending["id"])
        row.request_metadata = {**row.request_metadata, "request_started": True}
    provider = Provider()
    asyncio.run(execute_overview(engine, pending["job_id"], tmp_path, provider=provider))
    assert recover_overviews(engine) == 1
    asyncio.run(execute_overview(engine, pending["job_id"], tmp_path, provider=provider))
    assert provider.calls == 0
    with Session(engine) as db:
        assert db.get(PaperOverviewResult, pending["id"]).error_code == "INTERRUPTED"


def test_cancelled_during_generation_retains_receipt_without_publication(tmp_path, monkeypatch):
    values = fixture(tmp_path, monkeypatch)
    engine, _client, _paper, _revision, _snapshot = values
    pending = queue(values)

    def cancel():
        with Session(engine) as db, db.begin():
            db.get(Job, pending["job_id"]).status = "cancelled"
            result = db.get(PaperOverviewResult, pending["id"])
            result.status, result.error_code = "FAILED", "CANCELLED"

    provider = Provider(during=cancel)
    asyncio.run(execute_overview(engine, pending["job_id"], tmp_path, provider=provider))
    with Session(engine) as db:
        row = db.get(PaperOverviewResult, pending["id"])
        assert row.status == "FAILED" and row.error_code == "CANCELLED"
        assert row.raw_output == provider.raw and row.usage_json["total_tokens"] == 30
        assert row.paper_card_json is None
        assert db.scalar(select(LiteTokenUsage)).status == "cancelled"
    assert provider.calls == 1


def test_tampered_saved_card_is_rejected_on_read_and_cache(tmp_path, monkeypatch):
    values = fixture(tmp_path, monkeypatch)
    engine, client, paper_id, _revision, _snapshot = values
    pending = queue(values)
    asyncio.run(execute_overview(engine, pending["job_id"], tmp_path, provider=Provider()))
    with Session(engine) as db, db.begin():
        row = db.get(PaperOverviewResult, pending["id"])
        row.paper_card_json = {**row.paper_card_json, "article_overview_zh": "Tampered"}
    result = client.get(f"/api/v1/papers/{paper_id}/overview")
    assert result.status_code == 409 and result.json()["code"] == "CARD_SOURCE_OR_CONTENT_CHANGED"
    with Session(engine) as db:
        with pytest.raises(KnowledgeError):
            card_overview_view(db, db.get(PaperOverviewResult, pending["id"]))
    replacement = queue(values)
    assert replacement["status"] == "PENDING" and replacement["id"] != pending["id"]
    with Session(engine) as db:
        assert db.query(LiteTokenUsage).count() == 1  # No cache hit or extra dispatch yet.


def test_real_provider_preflight_fails_before_creating_a_send_slot(tmp_path, monkeypatch):
    values = fixture(tmp_path, monkeypatch)
    engine, _client, _paper, _revision, _snapshot = values
    pending = queue(values)
    provider = ConfiguredProvider(base_url="https://model.example/v1", model="synthetic", key="")
    provider.capabilities = ModelCapabilities(context_window=1024, max_output_tokens=128)

    async def forbidden_complete(*args):
        pytest.fail("A known local preflight rejection must not enter complete or prepare")

    monkeypatch.setattr(provider, "complete", forbidden_complete)
    asyncio.run(execute_overview(engine, pending["job_id"], tmp_path, provider=provider))
    with Session(engine) as db:
        row = db.get(PaperOverviewResult, pending["id"])
        assert row.status == "FAILED" and row.error_code == "CARD_PROVIDER_FAILED"
        assert row.request_metadata["request_started"] is False
        assert row.request_metadata["generation_request_sent"] is False
        assert row.usage_json["calls"] == 0 and row.raw_output is None
        assert db.query(LiteTokenUsage).count() == aggregate_usage(db, None).calls == 0
        assert db.query(KnowledgeLibrary).count() == 0
        assert (
            db.query(KnowledgeExtractionRun).count()
            == db.query(KnowledgeConnectionRun).count()
            == 0
        )


@pytest.mark.parametrize("already_cancelled", [False, True])
def test_actual_task_cancellation_retains_partial_usage_and_preserves_user_cancel(
    tmp_path, monkeypatch, already_cancelled
):
    values = fixture(tmp_path, monkeypatch)
    engine, _client, _paper, _revision, _snapshot = values
    pending = queue(values)

    class StreamingProvider:
        name = model = "synthetic"
        usage = {}
        partial_output = None
        request_metadata = {}
        calls = 0

        def __init__(self):
            self.entered = asyncio.Event()

        async def complete(self, prompt, context, schema):
            self.calls += 1
            self.entered.set()
            try:
                await asyncio.Future()
            finally:
                # The real streaming provider writes these in its own finally.
                self.partial_output = '{"schema_version":"paper-card-set-2"'
                self.usage = {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}
                self.request_metadata = {"response_bytes": 42, "content_characters": 38}

    provider = StreamingProvider()

    async def cancel_running_task():
        task = asyncio.create_task(
            execute_overview(engine, pending["job_id"], tmp_path, provider=provider)
        )
        await asyncio.wait_for(provider.entered.wait(), timeout=2)
        if already_cancelled:
            with Session(engine) as db, db.begin():
                db.get(Job, pending["job_id"]).status = "cancelled"
                row = db.get(PaperOverviewResult, pending["id"])
                row.status, row.error_code, row.error = "FAILED", "CANCELLED", "User cancelled"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_running_task())
    expected_status = "cancelled" if already_cancelled else "interrupted"
    expected_code = "CANCELLED" if already_cancelled else "INTERRUPTED"
    with Session(engine) as db:
        row = db.get(PaperOverviewResult, pending["id"])
        usage = db.query(LiteTokenUsage).one()
        assert row.status == "FAILED" and row.error_code == expected_code
        assert db.get(Job, pending["job_id"]).status == expected_status
        assert row.raw_output == provider.partial_output
        assert row.request_metadata["provider"] == provider.request_metadata
        assert row.usage_json["total_tokens"] == usage.total_tokens == 12
        assert row.usage_json["calls"] == aggregate_usage(db, None).calls == 1
        assert usage.status == expected_status and usage.reason_code == expected_code
        assert row.paper_card_json is None and row.graph_json is None
        if already_cancelled:
            assert row.error == "User cancelled"
    asyncio.run(execute_overview(engine, pending["job_id"], tmp_path, provider=provider))
    assert recover_overviews(engine) == 0
    assert provider.calls == 1


def test_late_real_provider_preflight_keeps_unsent_slot_and_excludes_generation_calls(
    tmp_path, monkeypatch
):
    values = fixture(tmp_path, monkeypatch)
    engine, _client, _paper, _revision, _snapshot = values
    pending = queue(values)
    provider = ConfiguredProvider(base_url="https://model.example/v1", model="synthetic", key="")
    provider.capabilities = ModelCapabilities(context_window=1_000_000, max_output_tokens=2048)
    prepares, clients = [], []

    async def discover_lower_capacity():
        prepares.append(True)
        provider.capabilities = ModelCapabilities(context_window=1024, max_output_tokens=128)

    def forbidden_post_client(*args, **kwargs):
        clients.append(True)
        pytest.fail("A deterministic request-body failure must happen before a POST client")

    monkeypatch.setattr(provider, "prepare", discover_lower_capacity)
    monkeypatch.setattr("researchgraph.providers.httpx.AsyncClient", forbidden_post_client)
    asyncio.run(execute_overview(engine, pending["job_id"], tmp_path, provider=provider))
    assert len(prepares) == 1 and clients == []
    with Session(engine) as db:
        row = db.get(PaperOverviewResult, pending["id"])
        slot = db.query(LiteTokenUsage).one()
        assert row.status == "FAILED" and db.get(Job, pending["job_id"]).status == "failed"
        assert row.usage_json["calls"] == aggregate_usage(db, None).calls == 0
        assert row.request_metadata["request_started"] is True
        assert row.request_metadata["generation_request_sent"] is False
        assert row.usage_json["retry_count"] == slot.retry_count == 0
        assert row.paper_card_json is None and row.raw_output is None
        assert slot.status == "not_sent" and slot.extra["generation_request_sent"] is False


@pytest.mark.parametrize("category", ["network", "response"])
def test_unknown_or_network_provider_errors_keep_the_reserved_call(tmp_path, monkeypatch, category):
    values = fixture(tmp_path, monkeypatch)
    engine, _client, _paper, _revision, _snapshot = values
    pending = queue(values)
    provider = ConfiguredProvider(base_url="https://model.example/v1", model="synthetic", key="")

    async def uncertain_failure(*args):
        raise ProviderError(category, "Synthetic uncertain generation request")

    monkeypatch.setattr(provider, "complete", uncertain_failure)
    asyncio.run(execute_overview(engine, pending["job_id"], tmp_path, provider=provider))
    with Session(engine) as db:
        row = db.get(PaperOverviewResult, pending["id"])
        slot = db.query(LiteTokenUsage).one()
        assert row.usage_json["calls"] == aggregate_usage(db, None).calls == 1
        assert slot.status == "failed" and "generation_request_sent" not in slot.extra
