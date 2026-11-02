import asyncio

import pytest
import test_knowledge
from researchgraph import unified_extraction
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeNode, ModelRun
from researchgraph.knowledge_store import KnowledgeStore, text_hash
from researchgraph.models import Chunk, Job
from researchgraph.providers import MockProvider, ProviderError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

seeded = test_knowledge.seeded


def test_seven_batches_resume_after_second_timeout_without_recalling_first(seeded, monkeypatch):
    _, engine, eid = seeded
    with Session(engine) as session, session.begin():
        first = session.get(EvidenceSpan, eid)
        for index in range(1, 7):
            text = f"Synthetic method {index} reports a conditional result."
            cid = f"chunk-{index}"
            session.add(
                Chunk(
                    id=cid,
                    revision_id="version",
                    page_index=0,
                    page_label="1",
                    block_index=index,
                    text=text,
                    bbox=[0.0, 0.0, 100.0, 100.0],
                )
            )
            session.flush()
            session.add(
                EvidenceSpan(
                    id=f"ev-{index}",
                    document_version_id="version",
                    paragraph_id=cid,
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
            "provider": "mock",
            "allow_network": False,
        }

    class Fault(MockProvider):
        calls = []
        failing = True

        async def complete(self, prompt, data, schema):
            if data.get("contract_version") == "reading-extraction-1.0":
                self.calls.append(data["chunk_id"])
                if self.failing and len(self.calls) == 2:
                    raise ProviderError(
                        "timeout", "Synthetic response timeout", timeout_phase="total"
                    )
            return await super().complete(prompt, data, schema)

    provider = Fault()
    monkeypatch.setattr(unified_extraction, "provider_for", lambda *args: provider)
    monkeypatch.setattr(
        unified_extraction,
        "plan_sections",
        lambda spans, **kwargs: [
            [{"id": s.id, "text": s.quote, "section": s.section_id}] for s in spans
        ],
    )
    with pytest.raises(ValueError, match="超时"):
        asyncio.run(unified_extraction.run_unified_extraction(engine, "job", reading=True))
    with Session(engine) as session:
        job = session.get(Job, "job")
        assert job.result["completed_batches"] == "1"
        assert job.result["total_batches"] == "7"
        first_ids = set(session.scalars(select(KnowledgeNode.id)))
        first_call = provider.calls[0]
    provider.failing = False
    asyncio.run(unified_extraction.run_unified_extraction(engine, "job", reading=True))
    assert provider.calls.count(first_call) == 1
    assert len(provider.calls) == 8  # Seven successes, one timed-out request.
    with Session(engine) as session:
        job = session.get(Job, "job")
        assert job.status == "succeeded"
        assert job.result["completed_batches"] == "7"
        assert first_ids <= set(session.scalars(select(KnowledgeNode.id)))
        assert len(KnowledgeStore(session).reading().current("paper").data["units"]) == 7
        assert session.scalar(select(func.count()).select_from(ModelRun)) == 11
