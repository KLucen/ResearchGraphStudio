"""Optional software caps preserve real capacity, receipts, and explicit retry boundaries."""

import asyncio
import json

import pytest
from pydantic import ValidationError
from researchgraph.core import KnowledgeError
from researchgraph.knowledge_budgets import estimate_knowledge_input_tokens
from researchgraph.knowledge_connections import (
    GROUND_NUMBER_PROMPT,
    _context,
    report_view,
    run_knowledge_connect,
)
from researchgraph.knowledge_connections_contracts import GroundedNumberConnectionsDraft
from researchgraph.knowledge_library import ensure_library
from researchgraph.knowledge_library_contracts import LibrarySettings
from researchgraph.knowledge_library_models import PaperKnowledgeVersion
from researchgraph.knowledge_tasks import _effective_policy, run_knowledge_extract
from researchgraph.model_capabilities import ModelCapabilities
from researchgraph.model_document_models import LlmDocumentSegment
from researchgraph.providers import ConfiguredProvider
from researchgraph.token_estimates import estimate_tokens
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_knowledge_connections import (
    ConnectionProvider,
    built_papers,
    connection_record,
    queue_connection,
)
from test_knowledge_extraction import FixtureProvider, model_fixture, queued, run_record, wire_draft


def settings(engine, **changes):
    with Session(engine) as db, db.begin():
        library = ensure_library(db)
        library.settings_json = {**library.settings_json, **changes}


def test_nullable_caps_roundtrip_and_finite_validation():
    unlimited = LibrarySettings(
        max_input_tokens=None, max_output_tokens=None, max_requests_per_run=None
    )
    assert LibrarySettings.model_validate_json(unlimited.model_dump_json()) == unlimited
    assert unlimited.total_request_limit == 20 and unlimited.max_candidates == 8
    for field in ("max_input_tokens", "max_output_tokens", "max_requests_per_run"):
        with pytest.raises(ValidationError):
            LibrarySettings.model_validate({field: 0})


@pytest.mark.parametrize(
    ("current", "frozen", "expected"),
    [(None, None, None), (None, 12000, 12000), (12000, None, 12000), (12000, 24000, 12000)],
)
def test_current_and_frozen_caps_intersect_with_null_as_unbounded(current, frozen, expected):
    result = _effective_policy(
        LibrarySettings(max_input_tokens=current, max_output_tokens=current),
        LibrarySettings(max_input_tokens=frozen, max_output_tokens=frozen),
    )
    assert result.max_input_tokens == result.max_output_tokens == expected


def test_capacity_estimate_counts_tokens_separately_from_transfer_bytes():
    assert estimate_tokens("a" * 3000) == 1000
    assert estimate_tokens("研" * 1000) == 2000


def test_unsent_input_budget_failure_recovers_explicitly_with_unlimited_current_policy(tmp_path):
    values = model_fixture(tmp_path)
    with Session(values[0]) as db, db.begin():
        segment = db.scalar(
            select(LlmDocumentSegment).where(
                LlmDocumentSegment.parse_id == values[2],
                LlmDocumentSegment.chapter_ref == "c1",
            )
        )
        segment.latex = "x + y = z " * 20000
    first = queued(values)
    provider = FixtureProvider()
    asyncio.run(run_knowledge_extract(values[0], first, tmp_path, provider=provider))
    old_job, old_run = run_record(values[0], first)
    assert old_job.status == "failed"
    assert old_run.error_code == "KNOWLEDGE_INPUT_BUDGET_EXCEEDED"
    assert not old_run.request_sent and old_run.raw_response is None and provider.calls == 0
    settings(values[0], max_input_tokens=None, max_output_tokens=None, max_requests_per_run=None)
    assert queued(values) == first  # Raising a budget never silently re-sends an old failure.
    second = queued(values, retry_failed=True)
    assert second != first
    asyncio.run(run_knowledge_extract(values[0], second, tmp_path, provider=provider))
    job, run = run_record(values[0], second)
    assert job.status == "succeeded" and provider.calls == 1
    assert run.policy_json["max_input_tokens"] is None
    assert run.policy_json["max_output_tokens"] is None and run.attempt == 1
    assert run.request_metadata["capacity"]["input_token_estimate"] > 48000
    assert run_record(values[0], first)[1].error_code == "KNOWLEDGE_INPUT_BUDGET_EXCEEDED"
    assert not run_record(values[0], first)[1].request_sent


def test_unlimited_software_caps_still_reject_real_endpoint_capacity_before_send(tmp_path):
    values = model_fixture(tmp_path)
    settings(values[0], max_input_tokens=None, max_output_tokens=None, max_requests_per_run=None)
    job_id = queued(values)
    provider = FixtureProvider()
    provider.capabilities = ModelCapabilities(context_window=1024, max_output_tokens=512)
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    _, run = run_record(values[0], job_id)
    assert run.error_code == "KNOWLEDGE_CAPACITY_INSUFFICIENT"
    assert not run.request_sent and provider.calls == 0


def test_configured_provider_accepts_token_capacity_when_transfer_bytes_are_larger(tmp_path):
    values = model_fixture(tmp_path)
    with Session(values[0]) as db, db.begin():
        segment = db.scalar(
            select(LlmDocumentSegment).where(
                LlmDocumentSegment.parse_id == values[2],
                LlmDocumentSegment.chapter_ref == "c1",
            )
        )
        segment.latex = "x + y = z " * 20000
    settings(values[0], max_input_tokens=None, max_output_tokens=None)
    job_id = queued(values)

    class CapacityProvider(ConfiguredProvider):
        def __init__(self):
            super().__init__(base_url="https://invalid.test", model="synthetic", key="")
            self.capabilities = ModelCapabilities(context_window=100000, max_output_tokens=16000)
            self.calls = 0

        async def prepare(self):
            pass

        async def complete(self, prompt, data, schema):
            self.calls += 1
            return json.dumps(wire_draft(data), ensure_ascii=False)

    provider = CapacityProvider()
    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=provider))
    job, run = run_record(values[0], job_id)
    assert job.status == "succeeded" and provider.calls == 1
    assert run.request_metadata["provider"]["input_bytes"] > 100000
    assert run.request_metadata["capacity"]["input_token_estimate"] + 16000 + 512 < 100000
    assert run.request_metadata["provider"]["output_limit"] == 16000


def test_unlimited_connections_build_and_preserve_capacity_audit(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    settings(engine, max_input_tokens=None, max_output_tokens=None, max_requests_per_run=None)
    job_id = queue_connection(engine, versions[1])
    provider = ConnectionProvider()
    asyncio.run(run_knowledge_connect(engine, job_id, tmp_path, provider=provider))
    job, run, requests, report = connection_record(engine, job_id)
    assert job.status == "succeeded" and provider.calls == 1 and report
    assert run.policy_json["max_requests_per_run"] is None
    assert requests[0].usage_json["capacity"]["input_token_estimate"] > 0
    assert requests[0].usage_json["total_tokens"] == 300


def test_unlimited_request_count_can_compare_ten_batches_but_keeps_total_cap(tmp_path):
    engine, versions, _ = built_papers(tmp_path, 11)
    with Session(engine) as db:
        source = _context(db, db.get(PaperKnowledgeVersion, versions[-1]))
        candidate = {**_context(db, db.get(PaperKnowledgeVersion, versions[0])), "ref": "p1"}
    one = estimate_knowledge_input_tokens(
        GROUND_NUMBER_PROMPT,
        {"source": source, "candidates": [candidate]},
        GroundedNumberConnectionsDraft.model_json_schema(),
    )
    settings(
        engine,
        max_candidates=20,
        max_input_tokens=one + 100,
        max_output_tokens=None,
        max_requests_per_run=None,
    )
    with pytest.raises(KnowledgeError, match="预算"):
        queue_connection(engine, versions[-1])  # 11 extracts plus 10 batches exceeds total20.
    settings(engine, total_request_limit=30)
    job_id = queue_connection(engine, versions[-1])
    provider = ConnectionProvider()
    asyncio.run(run_knowledge_connect(engine, job_id, tmp_path, provider=provider))
    job, _, requests, report = connection_record(engine, job_id)
    assert job.status == "succeeded" and provider.calls == len(requests) == 10
    assert report.report_json["coverage"]["compared"] == 10
    with Session(engine) as db:
        view = report_view(db, report)
        assert len(view["relations"]) == 10
        assert all(relation["detail"]["comparison_zh"] for relation in view["relations"])


def test_connection_budget_tightening_before_send_also_applies_with_unlimited_snapshot(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    settings(engine, max_input_tokens=None, max_output_tokens=None, max_requests_per_run=None)
    job_id = queue_connection(engine, versions[1])

    class TighteningProvider(ConnectionProvider):
        async def prepare(self):
            settings(engine, max_input_tokens=1024)

    provider = TighteningProvider()
    asyncio.run(run_knowledge_connect(engine, job_id, tmp_path, provider=provider))
    job, run, requests, _ = connection_record(engine, job_id)
    assert job.status == "failed" and run.error_code == "KNOWLEDGE_INPUT_BUDGET_EXCEEDED"
    assert provider.calls == 0 and requests[0].sent_at is None
