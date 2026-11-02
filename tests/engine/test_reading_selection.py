import asyncio

import pytest
import test_knowledge
from researchgraph.knowledge_models import KnowledgeNode, ModelRun, ReviewDecision
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore
from researchgraph.models import Job
from researchgraph.providers import MockProvider, ProviderError
from researchgraph.reading_models import ReadingSelection
from researchgraph.reading_pipeline import finish_reading
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_reading_extraction import save


def setup_job(engine):
    with Session(engine) as session, session.begin():
        session.get(Job, "job").payload = {"document_version_id": "version", "density": "standard"}


def test_unit_selection_and_density_do_not_rewrite_knowledge(seeded):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    with Session(engine) as session, session.begin():
        reading = KnowledgeStore(session).reading()
        current = reading.current("paper")
        assert len(current.data["units"]) == 1
        assert len(current.data["units"][0]["memberships"]) == 3
        assert [e["graph_role"] for e in current.data["entries"]].count("core") == 1
        assert session.scalar(select(func.count()).select_from(ReviewDecision)) == 0
        count = session.scalar(select(func.count()).select_from(KnowledgeNode))
        reading.publish(
            version_id="version",
            snapshot=current.snapshot_hash,
            unit_ids=current.data["integration_unit_ids"],
            proposal=current.data["selection_proposal"],
            density="concise",
            expected_revision=1,
            key="density-test",
        )
        assert session.scalar(select(func.count()).select_from(KnowledgeNode)) == count
        with pytest.raises(KnowledgeError, match="选择已更新"):
            reading.publish(
                version_id="version",
                snapshot=current.snapshot_hash,
                unit_ids=current.data["integration_unit_ids"],
                proposal=current.data["selection_proposal"],
                density="detailed",
                expected_revision=1,
                key="stale-density",
            )


def test_failed_selection_reuses_integration_response(seeded):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)

    class Failing(MockProvider):
        calls = []
        fail = True

        async def complete(self, prompt, data, schema):
            self.calls.append(schema["title"])
            if schema["title"] == "CoreSelectionProposal" and self.fail:
                raise ProviderError("timeout", "synthetic timeout", timeout_phase="total")
            return await super().complete(prompt, data, schema)

    provider = Failing()
    with pytest.raises(ProviderError):
        asyncio.run(finish_reading(engine, "job", provider))
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ReadingSelection)) == 0
        assert session.scalar(select(func.count()).select_from(KnowledgeNode)) == 4
    provider.fail = False
    asyncio.run(finish_reading(engine, "job", provider))
    assert provider.calls.count("PaperIntegrationProposal") == 1
    assert provider.calls.count("CoreSelectionProposal") == 2
    with Session(engine) as session:
        assert session.get(Job, "job").status == "succeeded"
        assert session.scalar(select(func.count()).select_from(ModelRun)) == 4


def test_unreachable_member_rejected_and_old_graph_kept(seeded):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    with Session(engine) as session, session.begin():
        reading = KnowledgeStore(session).reading()
        current = reading.current("paper")
        nodes = reading.nodes("version")
        root = next(n.id for n in nodes if n.kind == "claim")
        proposal = {
            "contract_version": "reading-integration-1.0",
            "document_version_id": "version",
            "input_revision": int(current.snapshot_hash[:12], 16),
            "units": [
                {
                    "local_ref": "u",
                    "root_claim_id": root,
                    "member_ids": ["nonexistent"],
                    "rationale": "bad",
                }
            ],
        }
        with pytest.raises(KnowledgeError, match="不存在"):
            reading.integrate(
                proposal=proposal,
                version_id="version",
                snapshot=current.snapshot_hash,
                run_id="run",
                key="bad-unit",
            )
        assert reading.current("paper").id == current.id


def test_new_pipeline_offline_end_to_end(seeded):
    _, engine, _ = seeded
    from researchgraph.extraction import run_extraction

    with Session(engine) as session, session.begin():
        session.get(Job, "job").payload = {
            "document_version_id": "version",
            "pipeline": "paper-reading-v1",
            "provider": "mock",
            "allow_network": False,
        }
    asyncio.run(run_extraction(engine, "job"))
    with Session(engine) as session:
        assert session.get(Job, "job").status == "succeeded"
        assert KnowledgeStore(session).reading().current("paper").data["units"]


def test_identical_new_job_reuses_semantic_stages(seeded):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)

    class Counting(MockProvider):
        calls = 0

        async def complete(self, prompt, data, schema):
            self.calls += 1
            return await super().complete(prompt, data, schema)

    provider = Counting()
    asyncio.run(finish_reading(engine, "job", provider))
    assert provider.calls == 2
    from researchgraph.models import now

    with Session(engine) as session, session.begin():
        session.add(
            Job(
                id="second-job",
                kind="knowledge_extract",
                project_id="project",
                status="running",
                attempt=1,
                created_at=now(),
                updated_at=now(),
                payload={"document_version_id": "version", "density": "standard"},
            )
        )
    asyncio.run(finish_reading(engine, "second-job", provider))
    assert provider.calls == 2


# Explicit alias keeps the shared fixture registered when lint removes unused imports.
seeded = test_knowledge.seeded
