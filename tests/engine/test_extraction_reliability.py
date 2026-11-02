"""Null-marker compatibility and bounded response-timeout adaptation."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError
from researchgraph import unified_extraction as pipeline
from researchgraph.extraction_normalization import normalize_empty_placeholders
from researchgraph.knowledge_models import KnowledgeNode, ModelRun
from researchgraph.providers import ConfiguredProvider, MockProvider, ProviderError
from researchgraph.unified_contracts import KnowledgeExtractionBatch
from researchgraph.unified_mock import complete
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_engine import client, post
from test_extraction_refinement import document
from test_ingest import queue, wait_job


@pytest.mark.parametrize("value", [None, [], {}, "", "reported value", 0])
def test_only_null_at_exact_known_path_is_normalized(value):
    data = {
        "document_version_id": "v",
        "chunk_id": "c",
        "allowed_evidence": [{"id": "ev0001", "text": "Our method improves accuracy."}],
    }
    output = complete(data)
    claim = next(x for x in output["items"] if x["kind"] == "Claim")
    claim["claim_detail"]["findings_placeholder"] = value
    raw = json.dumps(output)
    normalized, paths = normalize_empty_placeholders(raw)
    assert json.loads(raw) == output
    if value is None:
        assert len(paths) == 1
        validated = KnowledgeExtractionBatch.model_validate_json(normalized)
        assert (
            validated.items[-1].claim_detail.statement_en == claim["claim_detail"]["statement_en"]
        )
    else:
        assert normalized == raw and paths == []
        with pytest.raises(ValidationError):
            KnowledgeExtractionBatch.model_validate_json(normalized)
    claim["claim_detail"]["unknown_science"] = None
    normalized, _ = normalize_empty_placeholders(json.dumps(output))
    with pytest.raises(ValidationError):
        KnowledgeExtractionBatch.model_validate_json(normalized)


def test_previous_placeholder_failure_resumes_without_a_model_call(tmp_path, monkeypatch):
    document(tmp_path / "paper.pdf", 1)
    calls = []

    class PlaceholderProvider(MockProvider):
        async def complete(self, prompt, data, schema):
            calls.append(data)
            value = json.loads(await super().complete(prompt, data, schema))
            for item in value["items"]:
                if item["kind"] == "Claim":
                    item["claim_detail"]["findings_placeholder"] = None
            return json.dumps(value)

    monkeypatch.setattr(pipeline, "provider_for", lambda *_: PlaceholderProvider())
    real_validate = pipeline.validate_or_repair

    async def old_validate(engine, job_id, provider, run_id, raw, data, manifest):
        return run_id, KnowledgeExtractionBatch.model_validate_json(raw)

    monkeypatch.setattr(pipeline, "validate_or_repair", old_validate)
    with client(tmp_path / "data", worker=True) as api:
        project = post(api, "/projects", {"name": "Null marker"}).json()["id"]
        imported = wait_job(api, queue(api, project, tmp_path / "paper.pdf", "null-import"))
        body = {"document_version_id": imported["result"]["revision_id"], "pipeline": "unified-v3"}
        failed = wait_job(api, post(api, "/knowledge/extract", body, "null-extract").json())
        assert failed["status"] == "failed"
        monkeypatch.setattr(pipeline, "validate_or_repair", real_validate)
        resumed = wait_job(api, post(api, f"/jobs/{failed['id']}/retry", key="null-retry").json())
        assert resumed["status"] == "succeeded", resumed
        assert len(calls) == 1
        with Session(api.app.state.engine) as session:
            run = session.scalar(select(ModelRun).where(ModelRun.job_id == failed["id"]))
            assert run.status == "succeeded" and run.error is None
            assert "findings_placeholder" in run.raw_output
            assert run.parameters["normalization"]["removed_paths"]
            assert list(session.scalars(select(KnowledgeNode)))


@pytest.mark.parametrize("child_fails", [False, True])
def test_response_timeout_splits_once_and_keeps_completed_children(
    tmp_path, monkeypatch, child_fails
):
    document(tmp_path / "paper.pdf", 8)
    calls = []

    class Slow(MockProvider):
        failing = True

        async def complete(self, prompt, data, schema):
            calls.append(data["chunk_id"])
            if len(data["allowed_evidence"]) == 8 or (
                child_fails and self.failing and len(calls) == 3
            ):
                raise ProviderError("timeout", "Response wait", timeout_phase="response_headers")
            return await super().complete(prompt, data, schema)

    provider = Slow()
    monkeypatch.setattr(pipeline, "provider_for", lambda *_: provider)
    with client(tmp_path / "data", worker=True) as api:
        project = post(api, "/projects", {"name": "Adaptive timeout"}).json()["id"]
        imported = wait_job(api, queue(api, project, tmp_path / "paper.pdf", "timeout-import"))
        body = {"document_version_id": imported["result"]["revision_id"], "pipeline": "unified-v3"}
        job = wait_job(api, post(api, "/knowledge/extract", body, "timeout-extract").json())
        assert len(calls) == 3
        assert job["result"]["total_batches"] == "2"
        assert all(x["split_reason"] == "timeout" for x in job["result"]["batches"])
        if child_fails:
            assert job["status"] == "failed" and job["result"]["completed_batches"] == "1"
            assert "停止自动重发" in job["error"]
            provider.failing = False
            job = wait_job(api, post(api, f"/jobs/{job['id']}/retry", key="timeout-retry").json())
        assert job["status"] == "succeeded", job
        assert calls.count(calls[1]) == 1
        repeat = wait_job(api, post(api, "/knowledge/extract", body, "timeout-repeat").json())
        assert repeat["status"] == "succeeded" and len(calls) == (4 if child_fails else 3)


def test_new_plans_limit_evidence_count_and_split_by_text_size():
    spans = [SimpleNamespace(id=str(i), quote="x" * 100, section_id="s") for i in range(150)]
    groups = pipeline.plan_sections(spans, budget=8000, max_evidence=64)
    assert [len(g) for g in groups] == [64, 64, 22]
    uneven = [
        {"id": str(i), "text": "x" * n, "section": "s"}
        for i, n in enumerate([20, 20, 20, 20, 500, 500])
    ]
    parts = pipeline.split_group(uneven)
    assert [len(g) for g in parts] == [5, 1]
    assert parts[0] + parts[1] == uneven


@pytest.mark.parametrize(
    "failure,phase",
    [
        (httpx.ConnectTimeout, "connection"),
        (httpx.ReadTimeout, "response_headers"),
        (httpx.WriteTimeout, "request_write"),
        (httpx.PoolTimeout, "connection_pool"),
    ],
)
def test_provider_reports_timeout_stage_without_secrets(monkeypatch, failure, phase):
    async def response(request):
        raise failure("private upstream error", request=request)

    real = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real(**kw, transport=httpx.MockTransport(response))
    )
    provider = ConfiguredProvider(
        base_url="https://model.example/v1", model="chosen", key="synthetic-private-value"
    )
    provider.capabilities_checked = True
    with pytest.raises(ProviderError) as caught:
        asyncio.run(
            provider.complete("JSON", {"allowed_evidence": [{"id": "e", "text": "text"}]}, {})
        )
    assert caught.value.timeout_phase == phase
    assert provider.request_metadata["timeout_phase"] == phase
    assert provider.request_metadata["source_characters"] == 4
    assert "private" not in str(caught.value)
    assert provider.usage == {}
