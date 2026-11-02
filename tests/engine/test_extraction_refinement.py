"""Output capability discovery, bounded split recovery and old job compatibility."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pymupdf
import pytest
from researchgraph.model_capabilities import parse_capabilities
from researchgraph.models import Job
from researchgraph.providers import ConfiguredProvider, MockProvider, ProviderError
from researchgraph.unified_extraction import plan_sections
from sqlalchemy.orm import Session
from test_engine import client, post
from test_ingest import queue, wait_job


def test_product_contract_defaults_require_a_real_configured_model():
    from researchgraph.knowledge_contracts import ExtractionRequest
    from researchgraph.reasoning_contracts import InferenceRequest
    from researchgraph.translation import TranslationRequest

    request = ExtractionRequest(document_version_id="version")
    assert request.provider == "project" and request.pipeline == "unified-v3"
    assert not request.allow_network
    assert TranslationRequest(node_ids=["node"]).provider == "project"
    assert InferenceRequest(source_id="a", target_id="b").provider == "project"


def test_adjacent_page_fallbacks_pack_without_dropping_evidence():
    spans = [
        SimpleNamespace(id=str(i), quote="Text " * 80, section_id=f"page{i}") for i in range(48)
    ]
    groups = plan_sections(spans)
    assert len(groups) == 2
    assert [e["id"] for g in groups for e in g] == [s.id for s in spans]
    assert len(plan_sections(spans, legacy=True)) == 48


@pytest.mark.parametrize("metadata", [True, False])
def test_capability_discovery_and_truncated_usage(monkeypatch, metadata):
    requests = []

    def response(request):
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "chosen",
                            **(
                                {"max_output_tokens": 131072, "context_window": 262144}
                                if metadata
                                else {}
                            ),
                        }
                    ]
                },
            )
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "length", "message": {"content": '{"items":['}}],
                "usage": {
                    "completion_tokens": 4000,
                    "prompt_tokens": 500,
                    "total_tokens": 4500,
                    "completion_tokens_details": {"reasoning_tokens": 3000},
                },
            },
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real_client(**kw, transport=httpx.MockTransport(response)),
    )
    provider = ConfiguredProvider(
        base_url="https://model.example/v1", model="chosen", parameters={"max_output_tokens": 65536}
    )
    with pytest.raises(ProviderError, match="截断"):
        asyncio.run(provider.complete("Return JSON", {}, {}))
    assert provider.usage["total_tokens"] == 4500
    assert provider.usage["reasoning_tokens"] == 3000
    assert provider.partial_output == '{"items":['
    if metadata:
        assert requests[0]["max_tokens"] == 131072
    else:
        assert "max_tokens" not in requests[0]
    assert parse_capabilities({"max_output_tokens": True}).max_output_tokens is None


def document(path, pages):
    with pymupdf.open() as pdf:
        for i in range(pages):
            page = pdf.new_page()
            page.insert_text((40, 60), f"Our method improves accuracy in experiment {i}.")
        pdf.save(path)


def test_truncation_splits_only_uncommitted_batches_and_repeated_job_reuses_children(
    tmp_path, monkeypatch
):
    document(tmp_path / "paper.pdf", 8)
    calls = []

    class Truncated(MockProvider):
        fail = True

        async def complete(self, prompt, data, schema):
            calls.append(data["chunk_id"])
            self.usage = {"total_tokens": 100}
            if len(data["allowed_evidence"]) == 8:
                self.partial_output = '{"items":['
                raise ProviderError("output_limit", "Truncated")
            self.partial_output = None
            if self.fail and len(calls) == 3:
                raise ProviderError("client", "Failure after successful child")
            return await super().complete(prompt, data, schema)

    provider = Truncated()
    monkeypatch.setattr("researchgraph.unified_extraction.provider_for", lambda *_: provider)
    with client(tmp_path / "data", worker=True) as api:
        project = post(api, "/projects", {"name": "Split test"}).json()["id"]
        imported = wait_job(api, queue(api, project, tmp_path / "paper.pdf", "import-refinement"))
        body = {"document_version_id": imported["result"]["revision_id"], "pipeline": "unified-v3"}
        failed = wait_job(api, post(api, "/knowledge/extract", body, "extract-refinement").json())
        assert failed["status"] == "failed", failed
        assert failed["result"]["completed_batches"] == "1"
        assert failed["result"]["total_batches"] == "2"
        assert failed["result"]["usage"]["total_tokens"] == 300
        provider.fail = False
        resumed = wait_job(
            api, post(api, f"/jobs/{failed['id']}/retry", key="resume-refinement").json()
        )
        assert resumed["status"] == "succeeded", resumed
        assert len(calls) == 4 and calls.count(calls[1]) == 1
        repeat = wait_job(api, post(api, "/knowledge/extract", body, "repeat-refinement").json())
        assert repeat["status"] == "succeeded", repeat
        assert len(calls) == 4
        # Verify failed usage/raw result directly; no dependency on UI endpoint naming.
        from researchgraph.knowledge_models import ModelRun
        from sqlalchemy import select

        with Session(api.app.state.engine) as session:
            run = session.scalar(
                select(ModelRun)
                .where(ModelRun.job_id == failed["id"], ModelRun.status == "failed")
                .order_by(ModelRun.created_at)
            )
            assert run.raw_output == '{"items":['
            assert run.parameters["usage"]["total_tokens"] == 100


def test_old_48_batch_job_retains_first_commit_after_upgrade(tmp_path, monkeypatch):
    document(tmp_path / "paper.pdf", 48)
    calls = []

    class Failing(MockProvider):
        fail = True

        async def complete(self, prompt, data, schema):
            calls.append(data["chunk_id"])
            if self.fail and len(calls) == 2:
                raise ProviderError("output_limit", "Old truncation")
            return await super().complete(prompt, data, schema)

    provider = Failing()
    monkeypatch.setattr("researchgraph.unified_extraction.provider_for", lambda *_: provider)
    with client(tmp_path / "data", worker=True) as api:
        project = post(api, "/projects", {"name": "Old 48 batches"}).json()["id"]
        imported = wait_job(api, queue(api, project, tmp_path / "paper.pdf", "old-import"))
        version = imported["result"]["revision_id"]
        # Queue via API while pausing dispatch, then seed only the legacy progress shape.
        from researchgraph import app as app_module

        original = app_module.run_extraction

        async def legacy_job(engine, job_id):
            with Session(engine) as session, session.begin():
                job = session.get(Job, job_id)
                job.result = {
                    "pipeline": "unified-v3",
                    "batches": [{"status": "pending"} for _ in range(48)],
                }
            await original(engine, job_id)

        monkeypatch.setattr(app_module, "run_extraction", legacy_job)
        failed = wait_job(
            api,
            post(
                api,
                "/knowledge/extract",
                {"document_version_id": version, "pipeline": "unified-v3"},
                "old-job-refinement",
            ).json(),
        )
        assert failed["result"]["completed_batches"] == "1", failed
        with Session(api.app.state.engine) as session, session.begin():
            job = session.get(Job, failed["id"])
            job.payload = {k: v for k, v in job.payload.items() if k != "unified_plan"}
        monkeypatch.setattr(app_module, "run_extraction", original)
        provider.fail = False
        # 47 independent durable commits can exceed the short-job budget on CI.
        # This is a bounded test-runner wait, not the provider's request timeout.
        resumed = wait_job(
            api,
            post(api, f"/jobs/{failed['id']}/retry", key="upgrade-resume").json(),
            timeout=90,
        )
        assert resumed["status"] == "succeeded", resumed
        assert resumed["result"]["completed_batches"] == "48"
        assert calls.count(calls[0]) == 1 and len(calls) == 49
