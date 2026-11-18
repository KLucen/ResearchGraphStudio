"""Whole-paper requests never silently become per-paragraph or automatic retries."""

import asyncio
import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from researchgraph.core import KnowledgeError, text_hash
from researchgraph.lite_models import LiteCacheEntry, LiteTokenUsage
from researchgraph.models import AttachmentRevision, Chunk, Job, Paper, Section, now
from researchgraph.paper_reading_api import (
    _configuration,
    _hash,
    _identity,
    build_paper_reading_input,
    execute_paper_reading,
    paper_reading_budget,
    recover_paper_readings,
    register_paper_reading_api,
)
from researchgraph.paper_reading_contracts import SCHEMA_VERSION, TASK_KIND, validate_paper_analysis
from researchgraph.paper_reading_models import PaperReadingResult
from researchgraph.providers import ProviderError
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_close_reading_api import CountingProvider, fixture, paragraph_result


def snapshot(provider):
    return {
        "provider": provider.name,
        "model": provider.model,
        "base_url": provider.base_url,
        "parameters": provider.parameters,
    }


def paper_context(session, paper_id, revision_id):
    """Synthetic source projection; production projection has independent PDF tests."""
    paper, revision = session.get(Paper, paper_id), session.get(AttachmentRevision, revision_id)
    section = session.scalar(select(Section).where(Section.document_version_id == revision_id))
    chunks = session.scalars(
        select(Chunk).where(Chunk.revision_id == revision_id).order_by(Chunk.block_index)
    ).all()
    paragraphs = [
        {
            "paragraph_id": chunk.id,
            "text_en": chunk.text,
            "section_id": section.id,
            "source_hash": text_hash(chunk.text),
            "sources": [{"chunk_id": chunk.id, "text_hash": text_hash(chunk.text)}],
        }
        for chunk in chunks
    ]
    return (
        paper,
        revision,
        {
            "paper_title": paper.title,
            "document_version_id": revision.id,
            "source_hash": revision.sha256,
            "projection_version": "test-projection-1",
            "projection_hash": _hash(paragraphs),
            "sections": [
                {"section_id": section.id, "title": section.title, "level": 0, "role": "method"}
            ],
            "paragraphs": paragraphs,
            "material_count": 2,
            "source_warnings": ["Figures retained locally; no image analysis"],
            "overview_result_id": None,
            "allowed_graph_nodes": [],
        },
    )


def setup(monkeypatch, provider=None):
    values = fixture()
    monkeypatch.setattr("researchgraph.paper_reading_api.build_paper_reading_input", paper_context)
    if provider is not None:
        monkeypatch.setattr(
            "researchgraph.model_settings.snapshot_for", lambda *_: snapshot(provider)
        )
    app = FastAPI()
    register_paper_reading_api(app, lambda: values[0], Path("unused"))
    return values, TestClient(app)


def response(ids, **changes):
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "paragraphs": [paragraph_result(item) for item in ids],
            "paper_argument": {
                "logic_chain_zh": ["提出问题与方法", "报告有限结果"],
                "core_claim_zh": "全文正文描述合成方法。",
                "strong_point_zh": None,
                "question_to_verify_zh": "图表尚需回看。",
            },
            **changes,
        },
        ensure_ascii=False,
    )


def queue(values, provider, *, allow=True, force=False):
    engine, project, paper, revision, _section, _ids = values
    with Session(engine) as session, session.begin():
        p, rev, context = paper_context(session, paper, revision)
        key, _ = _identity(p, rev, context, snapshot(provider))
        job = Job(
            id=str(uuid4()),
            project_id=project,
            kind=TASK_KIND,
            payload={
                "paper_id": paper,
                "document_version_id": revision,
                "input_hash": _hash(context),
                "cache_key": key,
                "allow_network": allow,
                "force_regenerate": force,
                "model_snapshot": snapshot(provider),
            },
            status="queued",
            stage="queued",
            attempt=0,
            created_at=now(),
            updated_at=now(),
        )
        session.add(job)
        return job.id


def test_whole_paper_single_request_and_revalidated_cache(monkeypatch, tmp_path):
    provider = CountingProvider("")
    values, api = setup(monkeypatch, provider)
    provider.response = response(values[5])
    route = f"/api/v1/papers/{values[2]}/reading-notes"
    assert api.get(route).json() is None
    refused = api.post(route + "/generate", json={"allow_network": False})
    assert refused.status_code == 409 and provider.calls == 0
    with Session(values[0]) as session:
        assert session.query(Job).count() == session.query(LiteTokenUsage).count() == 0
    first = api.post(route + "/generate", json={"allow_network": True}).json()
    pending = api.post(
        route + "/generate", json={"allow_network": True, "force_regenerate": True}
    ).json()
    assert first["id"] == pending["id"] and first["status"] == "PENDING"
    asyncio.run(execute_paper_reading(values[0], first["job_id"], tmp_path, provider=provider))
    asyncio.run(execute_paper_reading(values[0], first["job_id"], tmp_path, provider=provider))
    result = api.get(route).json()
    assert result["status"] == "COMPLETED", result
    assert result["paragraph_count"] == len(values[5])
    assert result["usage"]["total_tokens"] == 357 and result["usage"]["cost"] is None
    assert result["missing_paragraph_ids"] == []
    assert result["analysis"]["paper_argument"]
    cached = api.post(route + "/generate", json={"allow_network": True}).json()
    assert cached["cache_hit"] and cached["id"] == first["id"]
    assert provider.calls == 1
    prompt, data, schema = provider.received[0]
    assert "整篇论文" in prompt and "不重复输出英文全文" in prompt
    assert [item["paragraph_id"] for item in data["paragraphs"]] == values[5]
    assert data["excluded_material_count"] == 2 and "sources" not in data["paragraphs"][0]
    assert schema["title"] == "PaperReadingAnalysis"
    assert "text_en" not in result["analysis"]["paragraphs"][0]
    with Session(values[0]) as session:
        assert session.query(LiteCacheEntry).count() == 1
        ledger = session.scalars(select(LiteTokenUsage)).all()
        assert len(ledger) == 2 and sum(not item.cache_hit for item in ledger) == 1
        frozen = session.get(PaperReadingResult, first["id"]).request_metadata["source_context"]
        assert frozen["paragraphs"][0]["sources"][0]["text_hash"]


def test_worker_cache_and_unknown_usage_are_not_fabricated(monkeypatch, tmp_path):
    provider = CountingProvider("", usage=False)
    values, _api = setup(monkeypatch)
    provider.response = response(values[5])
    first, second = queue(values, provider), queue(values, provider)
    asyncio.run(execute_paper_reading(values[0], first, tmp_path, provider=provider))
    asyncio.run(execute_paper_reading(values[0], second, tmp_path, provider=provider))
    with Session(values[0]) as session:
        rows = session.scalars(
            select(PaperReadingResult).order_by(PaperReadingResult.created_at)
        ).all()
        assert [row.status for row in rows] == ["COMPLETED", "COMPLETED"]
        assert rows[1].cache_hit and rows[0].usage_json["input_tokens"] is None
        assert rows[0].usage_json["usage_source"] == "unknown"
    assert provider.calls == 1


def test_capacity_rejection_is_before_job_or_network_and_legacy_limit_ignored(monkeypatch):
    provider = CountingProvider("")
    provider.parameters = {"capabilities": {"max_output_tokens": 128, "context_window": 32768}}
    values, api = setup(monkeypatch, provider)
    blocked = api.post(
        f"/api/v1/papers/{values[2]}/reading-notes/generate", json={"allow_network": True}
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "PAPER_READING_MODEL_CAPACITY_INSUFFICIENT"
    assert "128" in blocked.json()["detail"]["message"]
    with Session(values[0]) as session:
        assert session.query(Job).count() == session.query(LiteTokenUsage).count() == 0
        _paper, _revision, context = paper_context(session, values[2], values[3])
    unknown = paper_reading_budget(context)
    assert "容量未完全声明" in unknown.warning
    legacy = paper_reading_budget(
        context, {**snapshot(provider), "parameters": {"max_output_tokens": 128}}
    )
    assert legacy.estimated_output_tokens > 128
    with pytest.raises(KnowledgeError, match="当前上下文|容量不足"):
        paper_reading_budget(context, {"parameters": {"capabilities": {"context_window": 1024}}})
    assert provider.calls == 0


def test_no_arbitrary_section_2000_limit_and_actual_provider_context_reserve(monkeypatch):
    values, _api = setup(monkeypatch)
    with Session(values[0]) as session:
        _p, _r, context = paper_context(session, values[2], values[3])
    context["paragraphs"][0]["text_en"] = "Long but valid source sentence. " * 500
    estimate = paper_reading_budget(context)
    assert estimate.estimated_source_tokens > 2000
    with pytest.raises(KnowledgeError) as caught:
        paper_reading_budget(
            context,
            {
                "provider": "compatible",
                "model": "fixture",
                "base_url": "https://provider.test/v1",
                "parameters": {
                    "capabilities": {"context_window": 12000, "max_output_tokens": 100000}
                },
            },
        )
    assert caught.value.code == "PAPER_READING_MODEL_CAPACITY_INSUFFICIENT"


@pytest.mark.parametrize("mode", ["missing", "wrong_id", "truncated", "provider_length"])
def test_incomplete_never_completed_or_automatically_retried(monkeypatch, tmp_path, mode):
    provider = CountingProvider("")
    values, api = setup(monkeypatch, provider)
    provider.response = response(values[5][:1] if mode == "missing" else values[5])
    if mode == "wrong_id":
        payload = json.loads(provider.response)
        payload["paragraphs"].append(paragraph_result("outside-source"))
        provider.response = json.dumps(payload)
    if mode == "truncated":
        provider.response = (
            '{"schema_version":"paper_reading_analysis.v1","paragraphs":['
            + json.dumps(paragraph_result(values[5][0]))
            + ',{"paragraph_id":'
        )
    if mode == "provider_length":
        provider.partial_output = provider.response

        async def length(*_args):
            provider.calls += 1
            raise ProviderError("output_limit", "synthetic")

        provider.complete = length
    job_id = queue(values, provider)
    asyncio.run(execute_paper_reading(values[0], job_id, tmp_path, provider=provider))
    asyncio.run(execute_paper_reading(values[0], job_id, tmp_path, provider=provider))
    result = api.get(f"/api/v1/papers/{values[2]}/reading-notes").json()
    assert result["status"] == "INCOMPLETE", result
    assert result["analysis"]["paragraphs"]
    assert provider.calls == 1
    with Session(values[0]) as session:
        assert session.query(LiteCacheEntry).count() == 0
        row = session.scalar(select(PaperReadingResult))
        assert row.raw_output == provider.response
    if mode == "provider_length":
        assert "PROVIDER_FINISH_LENGTH" in result["warnings"]
        assert result["error_code"] == "PAPER_READING_PROVIDER_TRUNCATED"


def test_source_changed_during_response_blocks_publication_and_retains_usage(monkeypatch, tmp_path):
    values, _api = setup(monkeypatch)

    def modify():
        with Session(values[0]) as session, session.begin():
            session.get(Chunk, values[5][0]).text += " Changed."

    provider = CountingProvider(response(values[5]), before_return=modify)
    job_id = queue(values, provider)
    asyncio.run(execute_paper_reading(values[0], job_id, tmp_path, provider=provider))
    with Session(values[0]) as session:
        row = session.scalar(select(PaperReadingResult))
        assert row.status == "FAILED" and row.error_code == "PAPER_READING_INPUT_CHANGED"
        assert row.raw_output == provider.response and row.analysis_json is None
        assert row.usage_json["total_tokens"] == 357
        assert session.query(LiteCacheEntry).count() == 0


def test_restart_or_cancel_does_not_resend_or_publish(monkeypatch, tmp_path):
    provider = CountingProvider("")
    values, _api = setup(monkeypatch)
    provider.response = response(values[5])
    first = queue(values, provider)
    assert recover_paper_readings(values[0]) == 1
    asyncio.run(execute_paper_reading(values[0], first, tmp_path, provider=provider))
    assert provider.calls == 0
    second = queue(values, provider)

    def cancel():
        with Session(values[0]) as session, session.begin():
            session.get(Job, second).status = "cancelled"

    provider.before_return = cancel
    asyncio.run(execute_paper_reading(values[0], second, tmp_path, provider=provider))
    with Session(values[0]) as session:
        row = session.scalar(select(PaperReadingResult).where(PaperReadingResult.job_id == second))
        assert row.analysis_json is None
        assert session.scalar(select(LiteTokenUsage)).status == "cancelled"
    asyncio.run(execute_paper_reading(values[0], second, tmp_path, provider=provider))
    assert provider.calls == 1


def test_cache_source_map_tampering_does_not_publish(monkeypatch, tmp_path):
    provider = CountingProvider("")
    values, api = setup(monkeypatch, provider)
    provider.response = response(values[5])
    job_id = queue(values, provider)
    asyncio.run(execute_paper_reading(values[0], job_id, tmp_path, provider=provider))
    route = f"/api/v1/papers/{values[2]}/reading-notes"
    assert api.get(route).json()["status"] == "COMPLETED"
    with Session(values[0]) as session, session.begin():
        row = session.scalar(select(PaperReadingResult))
        metadata = copy.deepcopy(row.request_metadata)
        metadata["source_context"]["paragraphs"][0]["sources"][0]["text_hash"] = "bad"
        row.request_metadata = metadata
    result = api.get(route).json()
    assert result["status"] == "FAILED" and result["analysis"] is None
    assert provider.calls == 1


def test_paper_schema_strict_highlights_and_changed_prompt_hash(monkeypatch):
    values, _api = setup(monkeypatch)
    with Session(values[0]) as session:
        _paper, _revision, context = paper_context(session, values[2], values[3])
    payload = json.loads(response(values[5]))
    payload["paragraphs"][0]["highlights"] = [
        {"type": "METHOD", "quote_en": "not in source", "occurrence_index": 0}
    ]
    result, missing, warnings, complete = validate_paper_analysis(
        json.dumps(payload), paragraphs=context["paragraphs"], allowed_graph_node_ids=set()
    )
    assert complete and not missing and not result.paragraphs[0].highlights and warnings
    payload["extra"] = "unexpected"
    with pytest.raises(ValueError):
        validate_paper_analysis(
            json.dumps(payload), paragraphs=context["paragraphs"], allowed_graph_node_ids=set()
        )
    before = _configuration({})
    monkeypatch.setattr("researchgraph.paper_reading_api.SYSTEM_PROMPT", "new versioned prompt")
    assert _configuration({}) != before


def test_real_projection_source_adapter_on_parsed_fixture(tmp_path, monkeypatch):
    """A real local PDF/projection crosses the service boundary with zero models."""
    import pymupdf
    import researchgraph.reading_document_models  # noqa: F401
    from researchgraph.document_structure import apply_structure
    from researchgraph.pdf_structure import parse_structure
    from test_ingest import FIXTURES

    values = fixture()
    with pymupdf.open(FIXTURES / "two-pages.pdf") as document:
        structure = parse_structure(document)
        blocks = [
            {
                "page_index": page.number,
                "page_label": str(page.number + 1),
                "block_index": i,
                "text": raw[4],
                "bbox": list(raw[:4]),
            }
            for page in document
            for i, raw in enumerate(
                block
                for block in page.get_text("blocks", sort=True)
                if block[6] == 0 and block[4].strip()
            )
        ]
    with Session(values[0]) as session, session.begin():
        # Publish into a separate paper rather than changing fixture sources.
        paper_id = str(uuid4())
        session.add(
            Paper(
                id=paper_id, project_id=values[1], title="Local projection test", created_at=now()
            )
        )
        session.flush()
        revision = AttachmentRevision(
            id=str(uuid4()),
            paper_id=paper_id,
            sha256="b" * 64,
            parser_version="fixture",
            page_count=2,
            warnings=[],
            created_at=now(),
        )
        session.add(revision)
        session.flush()
        session.add_all(
            [Chunk(id=str(uuid4()), revision_id=revision.id, **block) for block in blocks]
        )
        session.flush()
        apply_structure(session, revision.id, revision.sha256, structure)
        _paper, _revision, context = build_paper_reading_input(session, paper_id, revision.id)
        assert context["paragraphs"] and context["projection_version"] == "reading-document-2"
        assert all(item["sources"] for item in context["paragraphs"])
        assert session.query(LiteTokenUsage).count() == 0
        from researchgraph.reading_projection import build_reading_document

        def transient_warning(*args, **kwargs):
            view = build_reading_document(*args, **kwargs)
            view.warnings.append("Temporary local PDF unavailable; retry refresh later")
            return view

        monkeypatch.setattr(
            "researchgraph.reading_projection.build_reading_document", transient_warning
        )
        _, _, unchanged = build_paper_reading_input(session, paper_id, revision.id)
        assert _hash(context) == _hash(unchanged)
