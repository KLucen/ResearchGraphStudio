"""K2 uses two anonymous papers and synthetic providers; no network or user data."""

import asyncio
import copy
import json
from uuid import uuid4

import pymupdf
import pytest
from researchgraph.core import KnowledgeError
from researchgraph.import_plan_models import ImportSession
from researchgraph.knowledge_connection_models import (
    KnowledgeAnalysisEvent,
    KnowledgeConnectionRequest,
    KnowledgeConnectionRun,
)
from researchgraph.knowledge_extraction_models import KnowledgeExtractionRun
from researchgraph.knowledge_library import ensure_library
from researchgraph.knowledge_library_models import LibraryPaper, PaperKnowledgeVersion
from researchgraph.knowledge_sources import build_knowledge_sources, revalidate_knowledge_sources
from researchgraph.knowledge_tasks import (
    queue_knowledge_extract,
    recover_knowledge_extractions,
    run_knowledge_extract,
)
from researchgraph.model_capabilities import ModelCapabilities
from researchgraph.model_document_models import LlmDocumentParse, LlmDocumentSegment
from researchgraph.models import Base, Chunk, Job, Paper, Project, now
from researchgraph.paper_knowledge import (
    knowledge_model_input,
    knowledge_schema,
    validate_knowledge_response,
)
from researchgraph.paper_overview_contracts import SCHEMA_VERSION as LEGACY_SCHEMA
from researchgraph.paper_overview_contracts import PaperOverviewDraft
from researchgraph.storage import make_engine
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_reading_projection import store, textbox

SNAPSHOT = {
    "provider": "synthetic",
    "model": "fixture",
    "base_url": "https://invalid.test",
    "parameters": {},
}


def model_fixture(tmp_path):
    engine = make_engine(tmp_path / "knowledge")
    Base.metadata.create_all(engine)
    project, paper, session, parse = (str(uuid4()) for _ in range(4))
    with Session(engine) as db, db.begin():
        db.add(Project(id=project, name="Anonymous", description="", created_at=now()))
        db.flush()
        db.add(Paper(id=paper, project_id=project, title="Anonymous model paper", created_at=now()))
        db.flush()
        db.add(
            ImportSession(
                id=session,
                project_id=project,
                source_kind="pdf",
                selection_id="synthetic",
                source_snapshot={"paper_id": paper},
                plan={},
                status="succeeded",
                created_at=now(),
                updated_at=now(),
            )
        )
        db.flush()
        db.add(
            LlmDocumentParse(
                id=parse,
                import_session_id=session,
                parse_version="llm-document-1",
                status="succeeded",
                modality="text",
                warnings=[],
                created_at=now(),
                updated_at=now(),
            )
        )
        db.flush()
        for index, (chapter, kind, text) in enumerate(
            [
                (
                    "1 Introduction",
                    "paragraph",
                    "We ask whether a synthetic method improves retrieval. "
                    "A synthetic method improves retrieval.",
                ),
                ("2 Method", "formula", "x + y = z"),
                ("3 Results", "table", "Method | Score\nSynthetic | 3"),
                ("4 References", "paragraph", "Excluded reference marker."),
            ]
        ):
            db.add(
                LlmDocumentSegment(
                    id=str(uuid4()),
                    parse_id=parse,
                    chapter_ref=f"c{index}",
                    chapter_title=chapter,
                    chapter_level=1,
                    chapter_order=index,
                    kind=kind,
                    ordinal=0,
                    text=text if kind == "paragraph" else None,
                    latex=text if kind == "formula" else None,
                    raw_table_text=text if kind == "table" else None,
                    locator={"page": index + 1},
                    status="ok",
                    warnings=[],
                    created_at=now(),
                )
            )
    return engine, paper, parse


def draft(manifest):
    source = manifest["sources"][0]
    return {
        "schema_version": "paper-knowledge-1",
        "paper_card": {
            "research_question": "合成研究问题",
            "motivation": "",
            "method_summary": "合成方法",
            "contributions": [],
            "main_findings": [],
            "limitations": [],
        },
        "graph": {
            "nodes": [
                {
                    "id": "n1",
                    "type": "METHOD",
                    "label_zh": "合成方法",
                    "label_en": "Synthetic method",
                    "description_zh": "作者描述的合成方法。",
                    "basis": "EXPLICIT",
                    "source_refs": [
                        {"source_id": source["ref"], "quote": source["text"], "occurrence_index": 0}
                    ],
                }
            ],
            "edges": [],
        },
    }


class FixtureProvider:
    name = "synthetic"
    model = "fixture"
    capabilities = ModelCapabilities(max_output_tokens=16000, context_window=1000000)
    request_metadata = {"test": True}
    usage = {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300}

    def __init__(self, response=None, action=None):
        self.calls = 0
        self.prepares = 0
        self.response = response
        self.action = action

    async def prepare(self):
        self.prepares += 1

    async def complete(self, prompt, data, schema):
        self.calls += 1
        assert schema == knowledge_schema()
        assert "untrusted data" in prompt
        if self.action:
            self.action()
        if isinstance(self.response, Exception):
            raise self.response
        return (
            self.response
            if self.response is not None
            else json.dumps(draft(data), ensure_ascii=False)
        )


def queued(values, **kwargs):
    engine, paper, source = values
    with Session(engine) as db, db.begin():
        return queue_knowledge_extract(
            db,
            paper_id=paper,
            source_kind="model_parse",
            source_version_id=source,
            model_snapshot=SNAPSHOT,
            allow_network=True,
            **kwargs,
        ).id


def run_record(engine, job_id):
    with Session(engine) as db:
        job = db.get(Job, job_id)
        run = db.scalar(
            select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job_id)
        )
        return job, run


def test_both_source_adapters_keep_real_origin_and_exclude_references(tmp_path):
    values = model_fixture(tmp_path)
    with Session(values[0]) as db:
        manifest = build_knowledge_sources(db, values[1], "model_parse", values[2])
    assert len(manifest["sources"]) == 3
    assert [s["kind"] for s in manifest["sources"]] == ["paragraph", "formula", "table"]
    assert manifest["sources"][0]["origin"]["segment_id"]
    assert manifest["sources"][0]["page_start"] is None
    assert all("Excluded" not in s["text"] for s in manifest["sources"])
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        page.insert_text((40, 90), "1 Methods", fontsize=15, fontname="hebo")
        textbox(
            page,
            40,
            150,
            "We introduce a reproducible synthetic method. It processes anonymous data.",
        )
        engine, paper, revision = store(document)
    with Session(engine) as db:
        local = build_knowledge_sources(db, paper, "local_revision", revision)
    assert local["sources"][0]["origin"]["sources"][0]["chunk_id"]
    assert local["sources"][0]["page_start"] == 1
    assert local["paper_id"] != manifest["paper_id"]
    assert local["source_fingerprint"] != manifest["source_fingerprint"]
    content = validate_knowledge_response(json.dumps(draft(local)), local)
    assert content["graph"]["nodes"][0]["label_zh"] == "Synthetic"
    assert len(content["sources"]) == 1


@pytest.mark.parametrize(
    "mutation", ["extra", "quote", "source", "duplicate", "endpoint", "type", "occurrence"]
)
def test_strict_contract_rejects_invalid_content(tmp_path, mutation):
    engine, paper, parse = model_fixture(tmp_path)
    with Session(engine) as db:
        manifest = build_knowledge_sources(db, paper, "model_parse", parse)
    payload = draft(manifest)
    node = payload["graph"]["nodes"][0]
    if mutation == "extra":
        node["secret_instruction"] = "ignored?"
    elif mutation == "quote":
        node["source_refs"][0]["quote"] = "not in the original"
    elif mutation == "source":
        node["source_refs"][0]["source_id"] = "s99"
    elif mutation == "duplicate":
        payload["graph"]["nodes"].append(copy.deepcopy(node))
    elif mutation == "endpoint":
        payload["graph"]["edges"].append(
            {
                "id": "e1",
                "source": "n1",
                "target": "n9",
                "type": "YIELDS",
                "basis": "EXPLICIT",
                "source_refs": node["source_refs"],
            }
        )
    elif mutation == "type":
        node["type"] = "PAPER"
    else:
        node["source_refs"][0]["occurrence_index"] = 1
    with pytest.raises(ValueError):
        validate_knowledge_response(json.dumps(payload), manifest)


def test_strict_json_and_occurrence_grounding_preserve_legacy(tmp_path):
    engine, paper, parse = model_fixture(tmp_path)
    with Session(engine) as db:
        manifest = build_knowledge_sources(db, paper, "model_parse", parse)
    for raw in ['{"schema_version":"x","schema_version":"y"}', '{"a":NaN}', '{"a":Infinity}']:
        with pytest.raises(ValueError):
            validate_knowledge_response(raw, manifest)
    payload = draft(manifest)
    payload["graph"]["nodes"][0]["source_refs"][0].update(
        quote="improves retrieval.", occurrence_index=1
    )
    content = validate_knowledge_response(json.dumps(payload), manifest)
    assert content == validate_knowledge_response(json.dumps(payload), manifest)
    assert content["graph"]["nodes"][0]["type"] == "PAPER"
    assert content["graph"]["edges"][0]["type"] == "HAS_KNOWLEDGE"
    assert len(content["sources"]) == 1
    assert LEGACY_SCHEMA == "paper_overview_graph.v1"
    assert "source_refs" not in json.dumps(PaperOverviewDraft.model_json_schema())


def test_success_single_dispatch_cache_restart_and_usage(tmp_path):
    values = model_fixture(tmp_path)
    job_id = queued(values, auto_connect=True)
    provider = FixtureProvider()
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    job, run = run_record(values[0], job_id)
    assert job.status == run.status == "succeeded", job.error
    assert provider.calls == 1
    assert run.request_sent and run.raw_response
    assert run.usage_json["total_tokens"] == 300
    assert job.result["knowledge_version_id"] == run.version_id
    assert job.result["library_paper_id"] == run.library_paper_id
    assert queued(values) == job_id
    with Session(values[0]) as db:
        assert db.query(PaperKnowledgeVersion).count() == 1
        version = db.get(PaperKnowledgeVersion, run.version_id)
        assert version.source_snapshot_json == run.source_manifest
        assert version.content_json["coverage"]["semantic_accuracy"] == "unverified"


def test_received_response_recovers_without_network_or_resend(tmp_path):
    values = model_fixture(tmp_path)
    job_id = queued(values)
    with Session(values[0]) as db, db.begin():
        run = db.scalar(
            select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job_id)
        )
        run.request_sent, run.status = True, "received"
        run.raw_response = json.dumps(draft(run.source_manifest))
        job = db.get(Job, job_id)
        job.status = "failed"
        job.payload = {**job.payload, "allow_network": False}
    provider = FixtureProvider(RuntimeError("must not call"))
    assert queued(values) == job_id
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    assert provider.calls == provider.prepares == 0
    assert run_record(values[0], job_id)[0].status == "succeeded"


def test_sent_interruption_never_resends_and_explicit_retry_is_bounded(tmp_path):
    values = model_fixture(tmp_path)
    first = queued(values)
    with Session(values[0]) as db, db.begin():
        run = db.scalar(
            select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == first)
        )
        run.request_sent, run.status = True, "request_sent"
    provider = FixtureProvider("invalid JSON")
    asyncio.run(run_knowledge_extract(values[0], first, tmp_path, provider=provider))
    assert provider.calls == 0
    assert run_record(values[0], first)[1].error_code == "KNOWLEDGE_REQUEST_INTERRUPTED"
    assert queued(values) == first
    second = queued(values, retry_failed=True)
    assert second != first
    asyncio.run(run_knowledge_extract(values[0], second, tmp_path, provider=provider))
    assert provider.calls == 1
    _, run = run_record(values[0], second)
    assert run.previous_run_id and run.attempt == 2
    assert run.raw_response == "invalid JSON"
    assert run.usage_json["retry_count"] == 1
    with pytest.raises(KnowledgeError, match="请求上限"):
        queued(values, retry_failed=True)
    with Session(values[0]) as db:
        assert db.query(PaperKnowledgeVersion).count() == 0


@pytest.mark.parametrize("when", ["before", "after"])
def test_source_mutation_stops_send_or_publication_but_keeps_raw(tmp_path, when):
    values = model_fixture(tmp_path)
    job_id = queued(values)

    def change():
        with Session(values[0]) as db, db.begin():
            db.execute(text("PRAGMA reverse_unordered_selects=ON"))
            segment = db.scalar(
                select(LlmDocumentSegment).where(
                    LlmDocumentSegment.parse_id == values[2],
                    LlmDocumentSegment.chapter_ref == "c0",
                )
            )
            segment.text = (segment.text or "") + " Changed source."

    provider = FixtureProvider(action=change if when == "after" else None)
    if when == "before":
        change()
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    job, run = run_record(values[0], job_id)
    assert job.status == "failed"
    assert run.error_code == "KNOWLEDGE_SOURCE_CHANGED"
    assert provider.calls == (1 if when == "after" else 0)
    assert bool(run.raw_response) == (when == "after")
    with Session(values[0]) as db:
        assert db.query(PaperKnowledgeVersion).count() == 0


def test_capacity_and_network_fail_before_occupying_slot(tmp_path):
    values = model_fixture(tmp_path)
    first = queued(values)
    provider = FixtureProvider()
    provider.capabilities = ModelCapabilities(max_output_tokens=512, context_window=1024)
    asyncio.run(run_knowledge_extract(values[0], first, tmp_path, provider=provider))
    job, run = run_record(values[0], first)
    assert job.status == "failed" and run.error_code == "KNOWLEDGE_CAPACITY_INSUFFICIENT"
    assert not run.request_sent and provider.calls == 0
    second = queued(values, retry_failed=True)
    with Session(values[0]) as db, db.begin():
        job = db.get(Job, second)
        job.payload = {**job.payload, "allow_network": False}
    asyncio.run(run_knowledge_extract(values[0], second, tmp_path, provider=provider))
    _, run = run_record(values[0], second)
    assert run.error_code == "NETWORK_CONSENT_REQUIRED"
    assert not run.request_sent


def test_local_source_mutation_is_detected_without_pdf_read(tmp_path):
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        textbox(page, 40, 150, "A complete synthetic paragraph describes a locally parsed paper.")
        engine, paper, revision = store(document)
    with Session(engine) as db:
        manifest = build_knowledge_sources(db, paper, "local_revision", revision)
    with Session(engine) as db, db.begin():
        chunk = db.scalar(select(Chunk))
        chunk.text += " Changed archive."
    with Session(engine) as db, pytest.raises(KnowledgeError):
        revalidate_knowledge_sources(db, manifest)


@pytest.mark.parametrize("action", ["archive", "cancel"])
def test_inflight_archive_and_cancellation_keep_receipt_without_publication(tmp_path, action):
    values = model_fixture(tmp_path)
    job_id = queued(values)

    def change():
        with Session(values[0]) as db, db.begin():
            if action == "cancel":
                db.get(Job, job_id).status = "cancelled"
            else:
                run = db.scalar(
                    select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job_id)
                )
                db.get(LibraryPaper, run.library_paper_id).archived = True

    provider = FixtureProvider(action=change)
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    job, run = run_record(values[0], job_id)
    assert provider.calls == 1 and run.raw_response
    assert job.status == ("cancelled" if action == "cancel" else "failed")
    with Session(values[0]) as db:
        assert db.query(PaperKnowledgeVersion).count() == 0


def test_library_budget_counts_connections_and_current_reservation(tmp_path):
    values = model_fixture(tmp_path)
    job_id = queued(values)
    with Session(values[0]) as db, db.begin():
        library = ensure_library(db)
        library.settings_json = {**library.settings_json, "total_request_limit": 1}
        connection = KnowledgeConnectionRun(
            id=str(uuid4()),
            job_id=str(uuid4()),
            library_paper_id="synthetic",
            version_id="synthetic",
            input_hash="0" * 64,
            input_json={},
            model_snapshot={},
            policy_json={},
            status="queued",
        )
        db.add(connection)
        db.flush()
        db.add(
            KnowledgeConnectionRequest(
                id=str(uuid4()), run_id=connection.id, ordinal=0, input_json={}, status="planned"
            )
        )
    provider = FixtureProvider()
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    _, run = run_record(values[0], job_id)
    assert provider.calls == 0 and not run.request_sent
    assert run.error_code == "KNOWLEDGE_TOTAL_BUDGET_EXHAUSTED"
    with pytest.raises(KnowledgeError, match="预算"):
        queued(values, retry_failed=True)


def test_provider_prepare_failure_is_not_a_paid_request(tmp_path):
    values = model_fixture(tmp_path)
    job_id = queued(values)

    class FailingMetadataProvider(FixtureProvider):
        async def prepare(self):
            raise RuntimeError("Metadata unavailable")

    provider = FailingMetadataProvider()
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    _, run = run_record(values[0], job_id)
    assert provider.calls == 0 and not run.request_sent
    assert run.usage_json["calls"] == 0


def test_local_closed_loop_and_model_input_avoid_duplicate_raw_anchors(tmp_path, monkeypatch):
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        page.insert_text((40, 90), "1 Methods", fontsize=15, fontname="hebo")
        textbox(page, 40, 150, "The reproducible synthetic method processes anonymous samples.")
        engine, paper, revision = store(document)
    monkeypatch.setattr(
        "researchgraph.reading_projection._scan_pdf", lambda *_: pytest.fail("No PDF reread")
    )
    with Session(engine) as db, db.begin():
        manifest = build_knowledge_sources(db, paper, "local_revision", revision)
        request = knowledge_model_input(manifest)
        assert "origin" not in request["sources"][0]
        assert request["sources"][0]["text"] == manifest["sources"][0]["text"]
        job_id = queue_knowledge_extract(
            db,
            paper_id=paper,
            source_kind="local_revision",
            source_version_id=revision,
            model_snapshot=SNAPSHOT,
            allow_network=True,
        ).id
    provider = FixtureProvider()
    asyncio.run(run_knowledge_extract(engine, job_id, tmp_path, provider=provider))
    job, run = run_record(engine, job_id)
    assert job.status == "succeeded", job.error
    assert run.output_json["sources"][0]["origin"]["sources"][0]["chunk_id"]
    assert provider.calls == 1


def test_provider_timeout_retains_single_slot_and_private_partial(tmp_path):
    values = model_fixture(tmp_path)
    job_id = queued(values)
    provider = FixtureProvider(TimeoutError("Synthetic timeout"))
    provider.partial_output = '{"schema_version":"paper-knowledge-1"'
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    _, run = run_record(values[0], job_id)
    assert provider.calls == 1 and run.request_sent
    assert run.raw_response is None
    assert run.request_metadata["partial_output"] == provider.partial_output


def test_cache_corruption_is_rejected_without_network(tmp_path):
    values = model_fixture(tmp_path)
    job_id = queued(values)
    provider = FixtureProvider()
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    with Session(values[0]) as db, db.begin():
        run = db.scalar(
            select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job_id)
        )
        version = db.get(PaperKnowledgeVersion, run.version_id)
        version.content_json = {**version.content_json, "injected": "not allowed"}
    with pytest.raises(KnowledgeError, match="冻结来源"):
        queued(values)
    assert provider.calls == 1


def test_startup_marks_interrupted_without_auto_queue_or_raw_loss(tmp_path):
    values = model_fixture(tmp_path)
    job_id = queued(values)
    with Session(values[0]) as db, db.begin():
        run = db.scalar(
            select(KnowledgeExtractionRun).where(KnowledgeExtractionRun.job_id == job_id)
        )
        run.request_sent, run.status = True, "received"
        run.raw_response = json.dumps(draft(run.source_manifest))
        db.get(Job, job_id).status = "interrupted"  # App generic restart recovery may run first.
    assert recover_knowledge_extractions(values[0]) == 1
    assert recover_knowledge_extractions(values[0]) == 0
    job, run = run_record(values[0], job_id)
    assert job.status == run.status == "interrupted" and run.raw_response
    assert queued(values) == job_id  # Explicit reuse queues only local validation.
    provider = FixtureProvider(RuntimeError("No network"))
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    assert provider.calls == 0 and run_record(values[0], job_id)[0].status == "succeeded"


def test_automatic_queue_freezes_scope_and_smaller_budgets_then_honors_revocation(tmp_path):
    from researchgraph.knowledge_library_contracts import LibrarySettings

    values = model_fixture(tmp_path)
    frozen = LibrarySettings(
        auto_collect=True,
        auto_connect=True,
        allow_network=True,
        scope="all",
        max_input_tokens=12000,
        max_output_tokens=8000,
        total_request_limit=10,
    ).model_dump()
    with Session(values[0]) as db, db.begin():
        library = ensure_library(db)
        library.settings_json = {
            **library.settings_json,
            "allow_network": True,
            "max_output_tokens": 5000,
            "total_request_limit": 8,
        }
    job_id = queued(values, policy_snapshot=frozen)
    _, run = run_record(values[0], job_id)
    assert run.policy_json["scope"] == "all"
    assert run.policy_json["max_input_tokens"] == 12000
    assert run.policy_json["max_output_tokens"] == 5000
    assert run.policy_json["total_request_limit"] == 8
    with Session(values[0]) as db, db.begin():
        library = ensure_library(db)
        library.settings_json = {**library.settings_json, "allow_network": False}
    provider = FixtureProvider()
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    _, run = run_record(values[0], job_id)
    assert run.error_code == "KNOWLEDGE_POLICY_REVOKED"
    assert provider.calls == 0 and not run.request_sent


def test_budget_tightening_during_metadata_preparation_stops_before_send(tmp_path):
    values = model_fixture(tmp_path)
    job_id = queued(values)

    class TighteningProvider(FixtureProvider):
        task_output_budget = None

        async def prepare(self):
            with Session(values[0]) as db, db.begin():
                library = ensure_library(db)
                library.settings_json = {**library.settings_json, "max_output_tokens": 256}

    provider = TighteningProvider()
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    _, run = run_record(values[0], job_id)
    assert provider.calls == 0 and not run.request_sent
    assert run.error_code == "KNOWLEDGE_CAPACITY_INSUFFICIENT"


@pytest.mark.parametrize("frozen_auto_connect", [False, True])
def test_publish_creates_analysis_event_only_with_queue_time_authorization(
    tmp_path, frozen_auto_connect
):
    values = model_fixture(tmp_path)
    job_id = queued(values, auto_connect=frozen_auto_connect)

    def enable_policy():
        with Session(values[0]) as db, db.begin():
            library = ensure_library(db)
            library.settings_json = {
                **library.settings_json,
                "auto_connect": True,
                "allow_network": True,
            }

    provider = FixtureProvider(action=enable_policy)
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    job, run = run_record(values[0], job_id)
    assert job.status == "succeeded"
    with Session(values[0]) as db:
        event = db.get(KnowledgeAnalysisEvent, run.version_id)
        assert (event is not None) == frozen_auto_connect
