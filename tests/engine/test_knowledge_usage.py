"""Knowledge request ledgers aggregate once across both parse source families."""

import asyncio

import pytest
from researchgraph.knowledge_connections import cleanup_library_paper, run_knowledge_connect
from researchgraph.knowledge_library_models import PaperKnowledgeVersion
from researchgraph.knowledge_tasks import run_knowledge_extract
from researchgraph.lite_usage import aggregate_knowledge_usage, aggregate_usage
from researchgraph.model_capabilities import ModelCapabilities
from researchgraph.providers import ConfiguredProvider
from sqlalchemy.orm import Session
from test_knowledge_connections import ConnectionProvider, built_papers, queue_connection
from test_knowledge_extraction import FixtureProvider, model_fixture, queued


def test_usage_counts_k2_input_output_and_k3_prompt_completion_by_real_origin(tmp_path):
    engine, versions, originals = built_papers(tmp_path)
    job_id = queue_connection(engine, versions[1])
    asyncio.run(run_knowledge_connect(engine, job_id, tmp_path, provider=ConnectionProvider()))
    with Session(engine) as db:
        global_usage = aggregate_usage(db, None)
        library_usage = aggregate_knowledge_usage(db)
        assert global_usage.calls == library_usage.calls == 3
        assert global_usage.input_tokens == library_usage.input_tokens == 600
        assert global_usage.output_tokens == library_usage.output_tokens == 300
        assert global_usage.total_tokens == library_usage.total_tokens == 900
        assert library_usage.unknown_usage_calls == 0
        assert library_usage.cost_known is False and library_usage.cost_estimate is None
        by_kind = {item.task_kind: item for item in library_usage.by_kind}
        assert (
            by_kind["knowledge_extract"].calls == 2
            and by_kind["knowledge_extract"].total_tokens == 600
        )
        assert (
            by_kind["knowledge_connect"].calls == 1
            and by_kind["knowledge_connect"].total_tokens == 300
        )
        for index, (_engine, paper, _source) in enumerate(originals):
            version = db.get(PaperKnowledgeVersion, versions[index])
            expected = 1 if index == 0 else 2
            assert aggregate_usage(db, version.project_id).calls == expected
            assert aggregate_usage(db, version.project_id, paper).calls == expected
        assert aggregate_usage(db, None, "unrelated-paper").calls == 0


def test_purge_preserves_global_and_library_usage_but_removes_project_attribution(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    job_id = queue_connection(engine, versions[1])
    asyncio.run(run_knowledge_connect(engine, job_id, tmp_path, provider=ConnectionProvider()))
    with Session(engine) as db, db.begin():
        version = db.get(PaperKnowledgeVersion, versions[1])
        project, paper, library_paper = (
            version.project_id,
            version.source_paper_id,
            version.library_paper_id,
        )
        before = aggregate_knowledge_usage(db)
        assert aggregate_usage(db, project, paper).calls == 2
        cleanup_library_paper(db, library_paper)
    with Session(engine) as db:
        after = aggregate_knowledge_usage(db)
        assert (after.calls, after.input_tokens, after.output_tokens, after.total_tokens) == (
            before.calls,
            before.input_tokens,
            before.output_tokens,
            before.total_tokens,
        )
        assert aggregate_usage(db, None).total_tokens == 900
        assert aggregate_usage(db, project, paper).calls == 0
        assert aggregate_usage(db, project).calls == 0


def test_unknown_usage_receipt_stays_unknown_after_purge(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    job_id = queue_connection(engine, versions[1])
    provider = ConnectionProvider()
    provider.usage = {}
    asyncio.run(run_knowledge_connect(engine, job_id, tmp_path, provider=provider))
    with Session(engine) as db, db.begin():
        usage = aggregate_knowledge_usage(db)
        assert usage.calls == 3 and usage.unknown_usage_calls == 1
        assert usage.total_tokens == 600
        version = db.get(PaperKnowledgeVersion, versions[1])
        cleanup_library_paper(db, version.library_paper_id)
    with Session(engine) as db:
        usage = aggregate_knowledge_usage(db)
        assert usage.calls == 3 and usage.unknown_usage_calls == 1
        assert usage.total_tokens == 600 and usage.cost_estimate is None


def test_unsent_metadata_failure_does_not_count_model_call(tmp_path):
    values = model_fixture(tmp_path)
    job_id = queued(values)

    class MetadataFailure(FixtureProvider):
        async def prepare(self):
            raise RuntimeError("synthetic metadata failure")

    asyncio.run(run_knowledge_extract(values[0], job_id, tmp_path, provider=MetadataFailure()))
    with Session(values[0]) as db:
        usage = aggregate_knowledge_usage(db)
        assert usage.calls == usage.total_tokens == usage.unknown_usage_calls == 0


def test_sent_failure_counts_once_and_explicit_successor_counts_as_retry(tmp_path):
    engine, versions, _ = built_papers(tmp_path)
    first = queue_connection(engine, versions[1])
    provider = ConnectionProvider(TimeoutError("synthetic timeout"))
    provider.usage = {}
    asyncio.run(run_knowledge_connect(engine, first, tmp_path, provider=provider))
    asyncio.run(run_knowledge_connect(engine, first, tmp_path, provider=provider))
    second = queue_connection(engine, versions[1], retry_failed=True)
    asyncio.run(run_knowledge_connect(engine, second, tmp_path, provider=ConnectionProvider()))
    with Session(engine) as db, db.begin():
        usage = aggregate_knowledge_usage(db)
        assert usage.calls == 4 and usage.retry_count == 1 and usage.unknown_usage_calls == 1
        assert usage.total_tokens == 900
        version = db.get(PaperKnowledgeVersion, versions[1])
        cleanup_library_paper(db, version.library_paper_id)
    with Session(engine) as db:
        after = aggregate_knowledge_usage(db)
        assert after.calls == 4 and after.retry_count == 1 and after.unknown_usage_calls == 1


@pytest.mark.parametrize("endpoint_output, expected", [(8000, 2048), (1024, 1024), (None, 2048)])
def test_task_output_budget_survives_endpoint_metadata_without_changing_profile_knob(
    endpoint_output, expected
):
    class MetadataProvider(ConfiguredProvider):
        async def prepare(self):
            self.capabilities = ModelCapabilities(
                max_output_tokens=endpoint_output, context_window=1000000
            )

    provider = MetadataProvider(
        base_url="https://invalid.test",
        model="synthetic",
        key="",
        parameters={"max_output_tokens": 100000, "json_mode": True},
    )
    provider.task_output_budget = 2048
    asyncio.run(provider.prepare())
    body = provider._build_body("synthetic prompt", {"sources": []}, {"type": "object"})
    assert body["max_tokens"] == expected
    assert provider.request_metadata["output_limit"] == expected
    assert provider.parameters["max_output_tokens"] == 100000


def test_legacy_provider_without_task_budget_keeps_existing_output_behavior():
    provider = ConfiguredProvider(
        base_url="https://invalid.test",
        model="synthetic",
        key="",
        parameters={"max_output_tokens": 128},
    )
    provider.capabilities = ModelCapabilities(max_output_tokens=8000, context_window=1000000)
    body = provider._build_body("synthetic prompt", {}, {"type": "object"})
    assert body["max_tokens"] == 8000
