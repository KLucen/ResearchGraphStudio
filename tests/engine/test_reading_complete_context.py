"""Explicit offline coverage for complete paper integration and frozen-plan recovery."""

import asyncio
import copy
import json

import pytest
import test_knowledge
from researchgraph.extraction import PROMPT_DIR
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeNode, ModelRun, NodeEvidence
from researchgraph.knowledge_store import KnowledgeStore, digest, text_hash
from researchgraph.models import Chunk, Job, now
from researchgraph.providers import MockProvider, ProviderError
from researchgraph.reading_contracts import CoreSelectionProposal, PaperIntegrationProposal
from researchgraph.reading_pipeline import finish_reading
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_reading_extraction import candidate_batch, save

seeded = test_knowledge.seeded


def set_job(engine, job_id="job"):
    with Session(engine) as session, session.begin():
        job = session.get(Job, job_id)
        if job is None:
            job = Job(
                id=job_id,
                kind="knowledge_extract",
                project_id="project",
                status="running",
                attempt=1,
                created_at=now(),
                updated_at=now(),
            )
            session.add(job)
        job.status = "running"
        job.payload = {"document_version_id": "version", "density": "standard"}


def immutable_source_snapshot(engine):
    with Session(engine) as session:
        return (
            {
                n.id: (n.text, copy.deepcopy(n.payload))
                for n in session.scalars(select(KnowledgeNode))
            },
            {c.id: (c.text, copy.deepcopy(c.bbox)) for c in session.scalars(select(Chunk))},
            {
                e.id: (e.quote, e.text_sha256, e.start_offset, e.end_offset)
                for e in session.scalars(select(EvidenceSpan))
            },
            session.get(ModelRun, "run").raw_output,
        )


@pytest.mark.parametrize("failure", ["timeout", "context_limit"])
def test_complete_context_keeps_all_candidates_evidence_support_and_old_graph_on_failure(
    seeded, failure
):
    _, engine, eid = seeded
    # The evidence is deliberately larger than the former 24K gate. It remains
    # an exact complete paragraph and is not a real/private paper.
    text = "Synthetic source protocol describes independently numbered measurements. " * 500
    with Session(engine) as session, session.begin():
        span = session.get(EvidenceSpan, eid)
        session.get(Chunk, span.paragraph_id).text = text
        span.quote, span.end_offset, span.text_sha256 = text, len(text), text_hash(text)
    save(engine, eid)
    set_job(engine)
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    with Session(engine) as session:
        old_selection = KnowledgeStore(session).reading().current("paper").id

    batch = candidate_batch(eid)
    root = batch["items"][0]
    methods, links = [], []
    for index in range(65):
        method = copy.deepcopy(batch["items"][1])
        method["local_ref"] = f"long-method-{index}"
        method["label"]["original"] = f"Synthetic method {index}"
        method["summary"]["original"] = (
            f"Protocol {index}: " + "A complete supporting detail. " * 35
        )
        methods.append(method)
        links.append(
            dict(
                source_local_ref=root["local_ref"],
                target_local_ref=method["local_ref"],
                relation="ASSOCIATED_METHOD",
                evidence_ids=[eid],
            )
        )
    batch["items"], batch["links"] = [root, *methods], links
    save(engine, eid, batch, key="more-support")
    before = immutable_source_snapshot(engine)
    set_job(engine, "complete-build")

    class FailingSelection(MockProvider):
        def __init__(self):
            self.calls = []
            self.fail = True

        async def complete(self, prompt, data, schema):
            self.calls.append((schema["title"], copy.deepcopy(data)))
            if schema["title"] == "CoreSelectionProposal" and self.fail:
                raise ProviderError(
                    failure, "Synthetic full-context failure", timeout_phase="total"
                )
            return await super().complete(prompt, data, schema)

    provider = FailingSelection()
    with pytest.raises(ProviderError):
        asyncio.run(finish_reading(engine, "complete-build", provider))
    with Session(engine) as session:
        assert KnowledgeStore(session).reading().current("paper").id == old_selection
        job = session.get(Job, "complete-build")
        assert job.payload["reading_finish_plan"]["context_policy"] == "complete-context-v1"
        assert len(job.payload["reading_windows"]["windows"]) == 1
    assert immutable_source_snapshot(engine) == before
    integration, selection = [data for _, data in provider.calls]
    assert len(integration["candidates"]) == 69
    assert len(json.dumps(integration["candidates"], ensure_ascii=False)) > 26000
    assert sum(len(e["text"]) for e in integration["allowed_evidence"]) > 24000
    assert {e["id"] for e in integration["allowed_evidence"]} == {eid}
    assert len(json.dumps(selection, ensure_ascii=False)) > 48000
    assert len(selection["units"]) == 1 and len(selection["units"][0]["members"]) == 68
    provider.fail = False
    asyncio.run(finish_reading(engine, "complete-build", provider))
    assert [title for title, _ in provider.calls] == [
        "PaperIntegrationProposal",
        "CoreSelectionProposal",
        "CoreSelectionProposal",
    ]
    assert provider.calls[-1][1] == selection
    assert immutable_source_snapshot(engine) == before
    with Session(engine) as session:
        current = KnowledgeStore(session).reading().current("paper")
        assert current.id != old_selection and len(current.data["units"][0]["memberships"]) == 68
        assert current.data["coverage_gaps"] == []
        assert session.get(Job, "complete-build").status == "succeeded"


def old_signature(provider, prompts):
    return digest(
        {
            "prompts": {
                p: text_hash((PROMPT_DIR / (p + ".md")).read_text(encoding="utf-8"))
                for p in prompts
            },
            "schemas": [
                PaperIntegrationProposal.model_json_schema(),
                CoreSelectionProposal.model_json_schema(),
            ],
            "provider": provider.name,
            "model": provider.model,
            "parameters": getattr(provider, "parameters", {}),
            "endpoint": getattr(provider, "base_url", "offline"),
        }
    )


def test_legacy_frozen_windows_and_successful_selection_checkpoint_are_not_recalled(seeded):
    _, engine, eid = seeded
    batch = candidate_batch(eid)
    root = batch["items"][0]
    batch["items"], batch["links"] = [], []
    for index in range(9):
        claim = copy.deepcopy(root)
        claim["local_ref"] = f"claim-{index}"
        claim["statement"]["original"] = f"Distinct synthetic conclusion {index}"
        batch["items"].append(claim)
    save(engine, eid, batch)
    set_job(engine)

    class LegacyFailure(MockProvider):
        def __init__(self):
            self.calls = []
            self.fail = True

        async def complete(self, prompt, data, schema):
            self.calls.append((schema["title"], copy.deepcopy(data)))
            if schema["title"] == "CoreSelectionProposal":
                if len(data["units"]) == 1 and self.fail:
                    raise ProviderError(
                        "timeout", "Synthetic old selection failure", timeout_phase="total"
                    )
            result = json.loads(await super().complete(prompt, data, schema))
            if schema["title"] == "PaperIntegrationProposal":
                # Legacy second-stage input must exceed the removed 48K gate.
                for unit in result["units"]:
                    unit["rationale"] = "Complete source-grounded context. " * 190
            return json.dumps(result)

    provider = LegacyFailure()
    prompts = ["P12_reading_integration_v2", "P13_reading_selection_v3"]
    with Session(engine) as session, session.begin():
        reading = KnowledgeStore(session).reading()
        reading.adapt("version")
        snapshot = reading.snapshot("version")
        nodes = reading.nodes("version")
        candidates = [
            dict(
                id=n.id,
                kind=n.kind,
                content=n.payload,
                text=n.text,
                authorship=n.authorship,
                evidence_ids=list(
                    session.scalars(
                        select(NodeEvidence.evidence_id).where(NodeEvidence.node_id == n.id)
                    )
                ),
            )
            for n in nodes
        ]
        roots = [n.id for n in nodes]
        windows = [
            dict(
                document_version_id="version",
                input_revision=int(snapshot[:12], 16),
                paper_type="unknown",
                root_claim_ids=roots[start : start + 8],
                candidates=candidates,
                existing_associations=[],
                allowed_evidence=[{"id": eid, "text": session.get(EvidenceSpan, eid).quote}],
                coverage_gaps=[],
                integration_rules={"required_roots": "Preserve this exact legacy window."},
            )
            for start in (0, 8)
        ]
        frozen = {"windows": windows, "gaps": []}
        job = session.get(Job, "job")
        job.payload = {
            **job.payload,
            "reading_finish_plan": dict(
                prompts=prompts,
                snapshot=snapshot,
                signature=old_signature(provider, prompts),
                expected_revision=0,
            ),
            "reading_windows": copy.deepcopy(frozen),
        }
    before = immutable_source_snapshot(engine)
    with pytest.raises(ProviderError):
        asyncio.run(finish_reading(engine, "job", provider))
    assert [title for title, _ in provider.calls] == [
        "PaperIntegrationProposal",
        "PaperIntegrationProposal",
        "CoreSelectionProposal",
        "CoreSelectionProposal",
    ]
    assert [
        data for title, data in provider.calls if title == "PaperIntegrationProposal"
    ] == windows
    selection_inputs = [data for title, data in provider.calls if title == "CoreSelectionProposal"]
    assert [len(data["units"]) for data in selection_inputs] == [8, 1]
    assert len(json.dumps(selection_inputs[0], ensure_ascii=False)) > 48000
    with Session(engine) as session:
        assert session.get(Job, "job").payload["reading_windows"] == frozen
        assert "context_policy" not in session.get(Job, "job").payload["reading_finish_plan"]
    provider.fail = False
    asyncio.run(finish_reading(engine, "job", provider))
    assert len(provider.calls) == 5
    assert provider.calls[-1] == ("CoreSelectionProposal", selection_inputs[1])
    assert immutable_source_snapshot(engine) == before
    with Session(engine) as session:
        assert session.get(Job, "job").status == "succeeded"
        assert len(KnowledgeStore(session).reading().current("paper").data["units"]) == 9


def test_more_than_twenty_legacy_windows_of_roots_reach_one_complete_request(seeded):
    _, engine, eid = seeded
    template = candidate_batch(eid)["items"][0]
    for start, stop in ((0, 90), (90, 161)):
        batch = candidate_batch(eid)
        batch["items"], batch["links"] = [], []
        for index in range(start, stop):
            claim = copy.deepcopy(template)
            claim["local_ref"] = f"claim-{index}"
            claim["statement"]["original"] = f"Distinct source-grounded conclusion {index}"
            batch["items"].append(claim)
        save(engine, eid, batch, key=f"many-roots-{start}")
    set_job(engine)
    before = immutable_source_snapshot(engine)

    class StopAtInput(MockProvider):
        def __init__(self):
            self.inputs = []

        async def complete(self, prompt, data, schema):
            self.inputs.append(copy.deepcopy(data))
            raise ProviderError("context_limit", "Synthetic endpoint refuses this whole request")

    provider = StopAtInput()
    with pytest.raises(ProviderError, match="Synthetic endpoint"):
        asyncio.run(finish_reading(engine, "job", provider))
    assert len(provider.inputs) == 1
    assert len(provider.inputs[0]["root_claim_ids"]) == 161
    assert len(provider.inputs[0]["candidates"]) == 161
    assert immutable_source_snapshot(engine) == before
    with Session(engine) as session:
        assert len(session.get(Job, "job").payload["reading_windows"]["windows"]) == 1
        assert KnowledgeStore(session).reading().current("paper") is None
