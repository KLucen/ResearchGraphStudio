import asyncio
from copy import deepcopy

import pytest
import test_knowledge
from researchgraph import ingest, model_settings, reading_wire, unified_extraction
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeNode, ModelRun
from researchgraph.knowledge_store import text_hash
from researchgraph.model_adapters import TENCENT_DEEPSEEK
from researchgraph.models import Chunk, Job
from researchgraph.providers import ConfiguredProvider, MockProvider, ProviderError
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_engine import post

seeded = test_knowledge.seeded


@pytest.mark.parametrize("legacy_prompt", [False, True])
def test_explicit_adapter_resume_keeps_plan_and_never_recalls_committed_batch(
    seeded, monkeypatch, legacy_prompt
):
    api, engine, eid = seeded
    current_prompt = reading_wire.PROMPT
    if legacy_prompt:
        monkeypatch.setattr(reading_wire, "PROMPT", reading_wire.LEGACY_PROMPT)
    with Session(engine) as session, session.begin():
        first = session.get(EvidenceSpan, eid)
        text = "Synthetic method reports a second conditional result."
        session.add(
            Chunk(
                id="second",
                revision_id="version",
                page_index=0,
                page_label="1",
                block_index=1,
                text=text,
                bbox=[0.0, 0.0, 100.0, 100.0],
            )
        )
        session.flush()
        session.add(
            EvidenceSpan(
                id="second-evidence",
                document_version_id="version",
                paragraph_id="second",
                section_id=first.section_id,
                page_index=0,
                start_offset=0,
                end_offset=len(text),
                quote=text,
                text_sha256=text_hash(text),
                normalization="identity-v1",
                bbox_list=[[0.0, 0.0, 100.0, 100.0]],
            )
        )
        session.get(Job, "job").payload = {
            "document_version_id": "version",
            "pipeline": "paper-reading-v1",
            "provider": "project",
            "allow_network": True,
            "model_snapshot": {
                "base_url": "https://tokenhub.tencentmaas.com/plan/v3",
                "model": "deepseek-v4.1-flash",
                "provider": "compatible",
                "parameters": {"reasoning_effort": None, "timeout_seconds": 90, "json_mode": True},
            },
        }
    calls = []

    class Synthetic(ConfiguredProvider):
        async def complete(self, prompt, data, schema):
            if data.get("contract_version") == "reading-extraction-1.0":
                calls.append((data["chunk_id"], dict(self.parameters)))
                if len(calls) == 2:
                    raise ProviderError("timeout", "synthetic timeout", timeout_phase="total")
            return await MockProvider().complete(prompt, data, schema)

    def configured(snapshot, *args):
        provider = Synthetic(
            base_url=snapshot["base_url"],
            model=snapshot["model"],
            parameters=dict(snapshot["parameters"]),
            provider_name=snapshot["provider"],
        )
        provider.capabilities_checked = True
        return provider

    monkeypatch.setattr(model_settings, "from_snapshot", configured)

    async def no_source(*args):
        # This fixture tests retry policy with an offline provider, not PDF parsing.
        return None

    monkeypatch.setattr(ingest, "ensure_structured_source", no_source)
    monkeypatch.setattr(
        unified_extraction,
        "plan_sections",
        lambda spans, **kw: [
            [{"id": s.id, "text": s.quote, "section": s.section_id}] for s in spans
        ],
    )
    with pytest.raises(ValueError, match="超时"):
        asyncio.run(unified_extraction.run_unified_extraction(engine, "job", reading=True))
    monkeypatch.setattr(reading_wire, "PROMPT", current_prompt)
    with Session(engine) as session, session.begin():
        job = session.get(Job, "job")
        job.status, job.attempt = "failed", 3
        before = deepcopy(job.payload)
        first_ids = set(session.scalars(select(KnowledgeNode.id)))
    assert api.get("/api/v1/jobs/job").json()["resume_adapter_available"]
    response = post(api, "/jobs/job/retry", key="resume-one")
    assert response.status_code == 200, response.text
    jid = response.json()["id"]
    assert jid != "job"
    assert post(api, "/jobs/job/retry", key="resume-two").json()["id"] == jid
    with Session(engine) as session, session.begin():
        session.get(Job, jid).status = "running"
    asyncio.run(unified_extraction.run_unified_extraction(engine, jid, reading=True))
    assert len(calls) == 3 and calls[0][0] != calls[2][0]
    assert calls[2][1]["adapter_policy"] == TENCENT_DEEPSEEK
    assert calls[2][1]["reasoning_effort"] == "none"
    with Session(engine) as session:
        assert session.get(Job, "job").payload == before
        assert session.get(Job, "job").status == "failed"
        successor = session.get(Job, jid)
        assert successor.status == "succeeded"
        assert successor.result["completed_batches"] == "2"
        if legacy_prompt:
            assert (
                successor.payload["unified_plan"]["signature"]
                != before["unified_plan"]["signature"]
            )
            assert successor.payload["unified_plan"]["leaves"][0]["committed_operation_key"]
        else:
            assert (
                successor.payload["unified_plan"]["signature"]
                == before["unified_plan"]["signature"]
            )
            assert successor.payload["unified_plan"]["config"] == before["unified_plan"]["config"]
        assert first_ids <= set(session.scalars(select(KnowledgeNode.id)))
        runs = list(session.scalars(select(ModelRun).where(ModelRun.job_id == jid)))
        assert all(r.parameters["adapter_policy"] == TENCENT_DEEPSEEK for r in runs)


@pytest.mark.parametrize("change", ["active", "explicit_effort", "unknown_endpoint", "integrating"])
def test_resume_does_not_override_active_work_or_explicit_settings(seeded, change):
    api, engine, _ = seeded
    with Session(engine) as session, session.begin():
        job = session.get(Job, "job")
        job.status = "running" if change == "active" else "failed"
        job.payload = {
            "pipeline": "paper-reading-v1",
            "allow_network": True,
            "unified_plan": {"signature": "frozen"},
            "model_snapshot": {
                "base_url": "https://other.example/v1"
                if change == "unknown_endpoint"
                else "https://tokenhub.tencentmaas.com/plan/v3",
                "model": "deepseek-v4.1-flash",
                "parameters": {"reasoning_effort": "high" if change == "explicit_effort" else None},
            },
            **({"reading_finish_plan": {"signature": "frozen"}} if change == "integrating" else {}),
        }
    assert not api.get("/api/v1/jobs/job").json()["resume_adapter_available"]
    assert post(api, "/jobs/job/resume-adapted", key="ineligible").status_code >= 400
