"""Offline semantic flow: program-owned units, conservative previews and exact recovery."""

import asyncio
import copy
import json

import pytest
import test_knowledge
from researchgraph import reading_transport, unified_extraction
from researchgraph.extraction import PROMPT_DIR, run_extraction
from researchgraph.graph_models import SourceAssertion
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeNode, ModelRun
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest, text_hash
from researchgraph.models import Chunk, Job, now
from researchgraph.providers import MockProvider, ProviderError
from researchgraph.reading_finish_wire import (
    INTEGRATION_PROMPT,
    LEGACY_RANKING_PROMPT,
    POLICY,
    RANKING_PROMPT,
    assert_prompt_contract,
    schema_for,
)
from researchgraph.reading_models import ReadingCheckpoint, ReadingSelection
from researchgraph.reading_pipeline import finish_reading
from researchgraph.reading_stage_validation import StageValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_engine import post
from test_reading_extraction import candidate_batch, save

seeded = test_knowledge.seeded


@pytest.fixture(autouse=True)
def historical_v2_default(monkeypatch):
    """These regressions deliberately retain the frozen v1/v2 transport."""
    from researchgraph import reading_finish_semantic

    monkeypatch.setattr(reading_finish_semantic, "DEFAULT_RANKING_PROMPT", RANKING_PROMPT)


def setup_job(engine, jid="job", *, semantic=True):
    with Session(engine) as session, session.begin():
        job = session.get(Job, jid)
        if job is None:
            job = Job(
                id=jid,
                kind="knowledge_extract",
                project_id="project",
                status="running",
                attempt=1,
                created_at=now(),
                updated_at=now(),
            )
            session.add(job)
        job.payload = {
            "document_version_id": "version",
            "pipeline": "paper-reading-v1",
            "provider": "mock",
            "allow_network": False,
            **({"reading_flow_policy": POLICY} if semantic else {}),
        }
        job.status = "running"


def source_snapshot(engine):
    with Session(engine) as session:
        return {
            "nodes": {
                n.id: (
                    n.text,
                    copy.deepcopy(n.payload),
                    n.model_run_id,
                    n.source_status,
                    n.review_status,
                )
                for n in session.scalars(select(KnowledgeNode))
            },
            "chunks": {
                c.id: (c.text, copy.deepcopy(c.bbox)) for c in session.scalars(select(Chunk))
            },
            "evidence": {
                e.id: (
                    e.quote,
                    e.text_sha256,
                    e.start_offset,
                    e.end_offset,
                    copy.deepcopy(e.bbox_list),
                )
                for e in session.scalars(select(EvidenceSpan))
            },
            "original_run": session.get(ModelRun, "run").raw_output,
        }


class SemanticFixture(MockProvider):
    def __init__(self, failure=None, *, add_association=False):
        self.calls = []
        self.responses = []
        self.failure = failure
        self.add_association = add_association

    async def complete(self, prompt, data, schema):
        title = schema["title"]
        self.calls.append((title, copy.deepcopy(data)))
        if title == "ReadingSemanticBatch":
            result = reading_transport.fixture(candidate_batch(data["allowed_evidence"][0]["id"]))
        elif title == "SemanticIntegration":
            if self.failure == "p12_json":
                raw = '{"associations":['
                self.responses.append((title, raw))
                return raw
            result = {"associations": [], "duplicates": [], "warnings": []}
            if self.add_association:
                candidates = {i["content"]["kind"]: i["candidate_ref"] for i in data["candidates"]}
                result["associations"] = [
                    {
                        "source_ref": candidates["Method"],
                        "target_ref": candidates["Condition"],
                        "relation": "HAS_CONDITION",
                        "evidence_refs": [data["allowed_evidence"][0]["evidence_ref"]],
                        "rationale": "Synthetic additional source-supported method condition",
                    }
                ]
            if self.failure == "version":
                result["document_version_id"] = "invented-version"
            if self.failure == "evidence":
                candidates = {i["content"]["kind"]: i["candidate_ref"] for i in data["candidates"]}
                result["associations"] = [
                    {
                        "source_ref": candidates["Claim"],
                        "target_ref": candidates["Method"],
                        "relation": "ASSOCIATED_METHOD",
                        "evidence_refs": ["invented-evidence"],
                        "rationale": "This fixture tests rejection, not a scientific relationship.",
                    }
                ]
        elif title == "KeyedContributionRanking":
            if self.failure == "p13_timeout":
                raise ProviderError("timeout", "Synthetic ranking timeout", timeout_phase="total")
            result = {
                "assessments": {
                    ref: {
                        "recommendation": "suggest_core",
                        "reasons": ["main_contribution"],
                        "rationale": "Synthetic contribution ranking",
                        "priority": 50,
                    }
                    for ref in data["assessment_refs"]
                },
                "warnings": [],
            }
        elif title == "ContributionRanking":
            if self.failure == "p13_timeout":
                raise ProviderError("timeout", "Synthetic ranking timeout", timeout_phase="total")
            result = {
                "ranked_claims": [
                    {
                        "claim_ref": u["claim_ref"],
                        "recommendation": "suggest_core",
                        "reasons": ["main_contribution"],
                        "rationale": "Synthetic contribution ranking",
                    }
                    for u in data["units"]
                ],
                "warnings": [],
            }
            if self.failure == "root":
                result["ranked_claims"][0]["claim_ref"] = "invented-root"
        else:
            raise AssertionError("Unexpected legacy or extra model call: " + title)
        raw = json.dumps(result, ensure_ascii=False)
        self.responses.append((title, raw))
        return raw


def test_normal_semantic_finish_binds_short_references_without_rewriting_candidates(seeded):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)
    before = source_snapshot(engine)
    provider = SemanticFixture()
    asyncio.run(finish_reading(engine, "job", provider))
    assert [t for t, _ in provider.calls] == ["SemanticIntegration", "ContributionRanking"]
    assert source_snapshot(engine) == before
    for title, data in provider.calls:
        encoded = json.dumps(data)
        for key in ("document_version_id", "input_revision", "root_claim_id", "local_ref"):
            assert '"' + key + '"' not in encoded
        if title == "SemanticIntegration":
            assert all(c["candidate_ref"].startswith("n") for c in data["candidates"])
            assert all(e["evidence_ref"].startswith("e") for e in data["allowed_evidence"])
        else:
            assert all(u["claim_ref"].startswith("c") for u in data["units"])
    with Session(engine) as session:
        job = session.get(Job, "job")
        selection = KnowledgeStore(session).reading().current("paper")
        assert job.status == "succeeded" and job.result["ranking_status"] == "complete"
        assert job.payload["reading_finish_plan"]["flow_policy"] == POLICY
        assert selection.data.get("selection_mode") != "provisional"
        assert (
            len(selection.data["units"]) == 1
            and len(selection.data["units"][0]["memberships"]) == 3
        )
        runs = list(session.scalars(select(ModelRun).where(ModelRun.id != "run")))
        assert {r.prompt_name for r in runs} == {INTEGRATION_PROMPT, RANKING_PROMPT}
        assert {r.raw_output for r in runs} == {r for _, r in provider.responses}
        assert all(r.status == "succeeded" for r in runs)


def test_bad_integration_keeps_candidates_and_only_unambiguous_contributions_in_preview(seeded):
    _, engine, eid = seeded
    batch = candidate_batch(eid)
    for name, changes in [
        ("unknown", {"modality": "unknown"}),
        ("speculative", {"modality": "speculative"}),
        ("background", {"contribution_type": "background"}),
        ("uncertain", {"uncertainties": ["Unresolved source interpretation"]}),
        ("cited", {"origin": "citation_report"}),
    ]:
        claim = copy.deepcopy(batch["items"][0])
        claim.update(local_ref=name, **changes)
        claim["statement"]["original"] = "Synthetic " + name + " conclusion"
        batch["items"].append(claim)
    save(engine, eid, batch)
    setup_job(engine)
    before = source_snapshot(engine)
    provider = SemanticFixture("p12_json")
    with pytest.raises(StageValidationError):
        asyncio.run(finish_reading(engine, "job", provider))
    assert [title for title, _ in provider.calls] == ["SemanticIntegration"]
    assert source_snapshot(engine) == before
    with Session(engine) as session:
        job = session.get(Job, "job")
        selection = KnowledgeStore(session).reading().current("paper")
        assert selection.data["selection_mode"] == "provisional"
        assert (
            selection.data["ranking_status"] == "pending"
            and selection.data["build_state"] == "partial"
        )
        assert len(selection.data["units"]) == 1
        root = session.get(KnowledgeNode, selection.data["units"][0]["root_claim_id"])
        assert root.payload["modality"] == "conditional" and not root.issues
        assert len(selection.data["entries"]) == 9  # All candidates remain retrievable.
        assert job.result["stage_failure"]["stage"] == "integrating"
        failed = session.scalar(select(ModelRun).where(ModelRun.prompt_name == INTEGRATION_PROMPT))
        assert (
            failed.status == "validation_failed" and failed.raw_output == provider.responses[0][1]
        )
    provider.failure = None
    asyncio.run(finish_reading(engine, "job", provider))
    assert source_snapshot(engine) == before
    with Session(engine) as session:
        assert session.get(Job, "job").status == "succeeded"
        assert KnowledgeStore(session).reading().current("paper").revision == 2


def test_failed_ranking_retries_only_ranking_then_replaces_preview_atomically(seeded):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)
    before = source_snapshot(engine)
    provider = SemanticFixture("p13_timeout")
    with pytest.raises(ProviderError):
        asyncio.run(finish_reading(engine, "job", provider))
    with Session(engine) as session:
        preview = KnowledgeStore(session).reading().current("paper")
        assert preview.data["selection_mode"] == "provisional" and preview.revision == 1
        preview_id = preview.id
        assert len(preview.data["units"][0]["memberships"]) == 3
        assert session.get(Job, "job").result["ranking_status"] == "pending"
    assert source_snapshot(engine) == before
    provider.failure = None
    asyncio.run(finish_reading(engine, "job", provider))
    assert [title for title, _ in provider.calls] == [
        "SemanticIntegration",
        "ContributionRanking",
        "ContributionRanking",
    ]
    assert provider.calls[1][1] == provider.calls[2][1]
    assert source_snapshot(engine) == before
    with Session(engine) as session:
        current = KnowledgeStore(session).reading().current("paper")
        assert current.id != preview_id and current.revision == 2
        assert session.get(ReadingSelection, preview_id) is not None  # Historical preview retained.
        assert current.data.get("selection_mode") != "provisional"
        assert current.data["coverage_gaps"] == []
        assert session.get(Job, "job").result["stage_failure"] is None


def test_ranking_retry_reuses_p12_even_when_it_added_valid_associations(seeded):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)
    before = source_snapshot(engine)
    provider = SemanticFixture("p13_timeout", add_association=True)
    with pytest.raises(ProviderError):
        asyncio.run(finish_reading(engine, "job", provider))
    provider.failure = None
    asyncio.run(finish_reading(engine, "job", provider))
    assert [title for title, _ in provider.calls] == [
        "SemanticIntegration",
        "ContributionRanking",
        "ContributionRanking",
    ]
    assert source_snapshot(engine) == before


@pytest.mark.parametrize("failure", ["p12_json", "p13_timeout", "version", "root", "evidence"])
def test_invalid_stage_response_never_replaces_existing_graph_or_mutates_source(seeded, failure):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine, semantic=False)
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    with Session(engine) as session:
        old_selection = KnowledgeStore(session).reading().current("paper").id
    setup_job(engine, "new-semantic-build")
    before = source_snapshot(engine)
    provider = SemanticFixture(failure)
    with pytest.raises((StageValidationError, ProviderError)):
        asyncio.run(finish_reading(engine, "new-semantic-build", provider))
    assert source_snapshot(engine) == before
    with Session(engine) as session:
        assert KnowledgeStore(session).reading().current("paper").id == old_selection
        job = session.get(Job, "new-semantic-build")
        assert job.result["previous_graph_retained"] is True
        assert job.result["ranking_status"] == "pending"
        assert session.scalar(select(func.count()).select_from(ReadingSelection)) == 1


def test_complete_p02_to_semantic_publication_offline_preserves_raw_and_source(seeded, monkeypatch):
    _, engine, _ = seeded
    setup_job(engine)
    before = source_snapshot(engine)
    provider = SemanticFixture()
    monkeypatch.setattr(unified_extraction, "provider_for", lambda *_: provider)
    asyncio.run(run_extraction(engine, "job"))
    assert [title for title, _ in provider.calls] == [
        "ReadingSemanticBatch",
        "SemanticIntegration",
        "ContributionRanking",
    ]
    p02_data = provider.calls[0][1]
    assert not set(p02_data) & reading_transport.BOUND_FIELDS - {"source_language"}
    raw = provider.responses[0][1]
    assert set(json.loads(raw)) == {"items", "links"}
    with Session(engine) as session:
        job = session.get(Job, "job")
        assert job.status == "succeeded" and job.result["completed_batches"] == "1"
        assert job.payload["unified_plan"]["prompt_name"] == reading_transport.PROMPT
        run = session.scalar(
            select(ModelRun).where(ModelRun.prompt_name == reading_transport.PROMPT)
        )
        assert run.status == "succeeded" and run.raw_output == raw
        assert (
            run.parameters["input_manifest"]["transport_context"]["document_version_id"]
            == "version"
        )
        assert len(KnowledgeStore(session).reading().current("paper").data["units"]) == 1
    after = source_snapshot(engine)
    assert after["chunks"] == before["chunks"] and after["evidence"] == before["evidence"]
    assert after["original_run"] == before["original_run"]


@pytest.mark.parametrize("failure", ["p12_json", "p13_timeout"])
def test_full_extraction_failure_keeps_p02_and_continues_only_unfinished_stages(
    seeded, monkeypatch, failure
):
    _, engine, _ = seeded
    setup_job(engine)
    provider = SemanticFixture(failure)
    monkeypatch.setattr(unified_extraction, "provider_for", lambda *_: provider)
    with pytest.raises((StageValidationError, ProviderError)):
        asyncio.run(run_extraction(engine, "job"))
    before_retry = source_snapshot(engine)
    with Session(engine) as session:
        assert len(before_retry["nodes"]) == 4
        job = session.get(Job, "job")
        assert job.result["completed_batches"] == "1"
        p02 = session.scalar(
            select(ModelRun).where(ModelRun.prompt_name == reading_transport.PROMPT)
        )
        assert p02.status == "succeeded"
        saved_p02 = p02.id, p02.raw_output
    provider.failure = None
    asyncio.run(run_extraction(engine, "job"))
    assert [title for title, _ in provider.calls].count("ReadingSemanticBatch") == 1
    assert [title for title, _ in provider.calls].count("SemanticIntegration") == (
        2 if failure == "p12_json" else 1
    )
    assert source_snapshot(engine) == before_retry
    with Session(engine) as session:
        assert session.get(Job, "job").status == "succeeded"
        assert session.get(ModelRun, saved_p02[0]).raw_output == saved_p02[1]
        current = KnowledgeStore(session).reading().current("paper")
        assert current.revision == 2 and current.data.get("selection_mode") != "provisional"


def test_no_claim_roots_skips_semantic_models_and_publishes_explicit_empty_graph(seeded):
    _, engine, eid = seeded
    batch = candidate_batch(eid)
    batch["items"] = [batch["items"][1]]
    batch["links"] = []
    save(engine, eid, batch)
    setup_job(engine)
    provider = SemanticFixture()
    before = source_snapshot(engine)
    asyncio.run(finish_reading(engine, "job", provider))
    assert provider.calls == []
    assert source_snapshot(engine) == before
    with Session(engine) as session:
        job = session.get(Job, "job")
        assert job.status == "succeeded"
        selection = KnowledgeStore(session).reading().current("paper")
        assert selection.data["units"] == []
        assert selection.data["coverage_gaps"]
        assert len(selection.data["entries"]) == 1


class AccountedFixture(SemanticFixture):
    async def complete(self, prompt, data, schema):
        total = {
            "ReadingSemanticBatch": 10,
            "SemanticIntegration": 20,
            "ContributionRanking": 30,
        }[schema["title"]]
        self.usage = {"prompt_tokens": total - 2, "completion_tokens": 2, "total_tokens": total}
        return await super().complete(prompt, data, schema)


@pytest.mark.parametrize("failure", ["p12_json", "p13_timeout"])
def test_semantic_failure_and_retry_account_all_recorded_calls_without_recharging_cache(
    seeded, monkeypatch, failure
):
    _, engine, _ = seeded
    setup_job(engine)
    provider = AccountedFixture(failure)
    monkeypatch.setattr(unified_extraction, "provider_for", lambda *_: provider)
    with pytest.raises((StageValidationError, ProviderError)):
        asyncio.run(run_extraction(engine, "job"))
    with Session(engine) as session:
        result = session.get(Job, "job").result
        assert result["model_calls"] == (2 if failure == "p12_json" else 3)
        assert result["usage"]["total_tokens"] == (30 if failure == "p12_json" else 60)
        assert result["model_calls_unrecorded_runs"] == 1
        assert result["model_calls_status"] == "known_attempts_only"
        assert result["cost"] is None and result["cost_status"] == "provider_not_reported"
        original = copy.deepcopy(session.get(ModelRun, "run").parameters)
        assert "attempts" not in original  # No fabricated attempt for a historical cached record.
    provider.failure = None
    asyncio.run(run_extraction(engine, "job"))
    with Session(engine) as session:
        job = session.get(Job, "job")
        assert job.status == "succeeded" and job.result["model_calls"] == 4
        assert job.result["usage"]["total_tokens"] == (80 if failure == "p12_json" else 90)
        assert job.result["cost"] is None
        assert session.get(ModelRun, "run").parameters == original
        assert [t for t, _ in provider.calls].count("ReadingSemanticBatch") == 1


def test_empty_publication_keeps_recorded_history_but_does_not_charge_reused_responses(seeded):
    _, engine, eid = seeded
    batch = candidate_batch(eid)
    batch["items"], batch["links"] = [batch["items"][1]], []
    save(engine, eid, batch)
    setup_job(engine)
    with Session(engine) as session, session.begin():
        old = session.get(ModelRun, "run")
        old.parameters = {
            "attempts": [{"status": "timeout"}, {"status": "received"}],
            "usage": {"total_tokens": 45},
        }
        session.add(
            ModelRun(
                id="reused",
                job_id="job",
                document_version_id="version",
                provider=old.provider,
                model=old.model,
                prompt_name=old.prompt_name,
                prompt_hash=old.prompt_hash,
                schema_version=old.schema_version,
                input_hash=old.input_hash,
                raw_output=old.raw_output,
                status="succeeded",
                created_at=now(),
                parameters={"response_reused_from": "run", "attempts": [], "usage": {}},
            )
        )
    provider = SemanticFixture()
    asyncio.run(finish_reading(engine, "job", provider))
    with Session(engine) as session:
        result = session.get(Job, "job").result
        assert result["model_calls"] == 2 and result["usage"] == {"total_tokens": 45}
        assert result["model_calls_unrecorded_runs"] == 0
        assert result["model_calls_status"] == "recorded" and provider.calls == []
        assert session.get(ModelRun, "reused").parameters["attempts"] == []


def test_ranked_claim_order_is_persisted_and_survives_density_and_display_preference(seeded):
    api, engine, eid = seeded
    batch = candidate_batch(eid)
    second = copy.deepcopy(batch["items"][0])
    second["local_ref"] = "second-conclusion"
    second["statement"]["original"] = "Synthetic second contribution for ordering"
    batch["items"].append(second)
    save(engine, eid, batch)
    setup_job(engine)

    class ReversedRanking(SemanticFixture):
        async def complete(self, prompt, data, schema):
            raw = await super().complete(prompt, data, schema)
            if schema["title"] == "ContributionRanking":
                value = json.loads(raw)
                value["ranked_claims"].reverse()
                raw = json.dumps(value)
                self.responses[-1] = (schema["title"], raw)
            return raw

    provider = ReversedRanking()
    asyncio.run(finish_reading(engine, "job", provider))
    with Session(engine) as session, session.begin():
        reading = KnowledgeStore(session).reading()
        selection = reading.current("paper")
        data = selection.data
        order = [r["root_claim_id"] for r in data["selection_proposal"]["recommendations"]]
        assert len(order) == 2 and data["contribution_order"] == order
        assert [u["root_claim_id"] for u in data["units"]] == order
        assert [u["contribution_rank"] for u in data["units"]] == [1, 2]
        roots = sorted(n.id for n in reading.nodes("version") if n.kind == "claim")
        assert order == list(reversed(roots))  # The provider deliberately inverted input order.
        reading.set_preference(order[0], "exclude_core", "Synthetic visibility preference")
        changed = reading.publish(
            version_id="version",
            snapshot=selection.snapshot_hash,
            unit_ids=data["integration_unit_ids"],
            proposal=data["selection_proposal"],
            density="concise",
            expected_revision=selection.revision,
            key="rank-preference",
            contribution_order=data["contribution_order"],
        )
        assert changed["contribution_order"] == order
        assert [u["root_claim_id"] for u in changed["units"]] == [order[1]]
        assert changed["units"][0]["contribution_rank"] == 2  # Hiding is not a model reranking.
        hidden = next(e for e in changed["entries"] if e["candidate_id"] == order[0])
        assert hidden["contribution_rank"] == 1 and hidden["graph_role"] == "retrieval_only"
        reading.set_preference(order[0], "include_core", "Synthetic restored visibility")
        restored = reading.publish(
            version_id="version",
            snapshot=selection.snapshot_hash,
            unit_ids=data["integration_unit_ids"],
            proposal=data["selection_proposal"],
            density="detailed",
            expected_revision=changed["selection_revision"],
            key="rank-restore",
            contribution_order=data["contribution_order"],
        )
        assert [u["root_claim_id"] for u in restored["units"]] == order
        assert [u["contribution_rank"] for u in restored["units"]] == [1, 2]
    response = post(
        api,
        "/papers/paper/graph-selection/rebuild",
        {
            "document_version_id": "version",
            "density": "concise",
            "expected_revision": restored["selection_revision"],
            "allow_network": False,
        },
        "rank-http-density",
    )
    assert response.status_code == 202 and response.json()["status"] == "succeeded", response.text
    with Session(engine) as session:
        current = KnowledgeStore(session).reading().current("paper")
        assert current.data["contribution_order"] == order
        assert [u["contribution_rank"] for u in current.data["units"]] == [1, 2]
        revision = current.revision
    for action, expected in (("exclude_core", [2]), ("include_core", [1, 2])):
        response = post(
            api,
            "/papers/paper/graph-selection/preferences",
            {
                "candidate_id": order[0],
                "action": action,
                "reason": "Synthetic HTTP visibility preference",
                "expected_revision": revision,
            },
            "rank-http-" + action,
        )
        assert response.status_code == 200, response.text
        changed = response.json()
        assert changed["contribution_order"] == order
        assert [u["contribution_rank"] for u in changed["units"]] == expected
        revision = changed["selection_revision"]
    assert len(provider.calls) == 2


def test_legacy_publication_fingerprint_is_unchanged_without_explicit_contribution_order(seeded):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine, semantic=False)
    asyncio.run(finish_reading(engine, "job", MockProvider()))
    with Session(engine) as session:
        current = KnowledgeStore(session).reading().current("paper")
        data = current.data
        assert "contribution_order" not in data
        assert all("contribution_rank" not in u for u in data["units"])
        assert session.get(ReadingCheckpoint, "reading:job:publish").input_hash == digest(
            [
                "version",
                current.snapshot_hash,
                data["integration_unit_ids"],
                data["selection_proposal"],
                "standard",
                0,
            ]
        )


@pytest.mark.parametrize("order", [[], ["invented"], ["same", "same"]])
def test_invalid_contribution_order_cannot_publish_or_change_an_existing_selection(seeded, order):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)
    asyncio.run(finish_reading(engine, "job", SemanticFixture()))
    with Session(engine) as session, session.begin():
        reading = KnowledgeStore(session).reading()
        current = reading.current("paper")
        data, original_id = current.data, current.id
        with pytest.raises(KnowledgeError, match="贡献排序"):
            reading.publish(
                version_id="version",
                snapshot=current.snapshot_hash,
                unit_ids=data["integration_unit_ids"],
                proposal=data["selection_proposal"],
                density="standard",
                expected_revision=current.revision,
                key="invalid-order",
                contribution_order=order,
            )
        assert reading.current("paper").id == original_id


def test_p02_trusted_anchor_change_preserves_received_run_and_prevents_a_new_request(
    seeded, monkeypatch
):
    _, engine, eid = seeded
    setup_job(engine)

    class ChangedAnchor(SemanticFixture):
        async def complete(self, prompt, data, schema):
            raw = await super().complete(prompt, data, schema)
            assert schema["title"] == "ReadingSemanticBatch"
            with Session(engine) as session, session.begin():
                session.get(EvidenceSpan, eid).end_offset -= 1
            return raw

    provider = ChangedAnchor()
    monkeypatch.setattr(unified_extraction, "provider_for", lambda *_: provider)
    with pytest.raises(ValueError, match="原文证据定位"):
        asyncio.run(run_extraction(engine, "job"))
    with Session(engine) as session:
        run = session.scalar(
            select(ModelRun).where(ModelRun.prompt_name == reading_transport.PROMPT)
        )
        assert run.status == "received" and run.error is None
        assert run.raw_output == provider.responses[0][1]
        assert run.parameters["stage_validation"]["response_invalid"] is False
        recorded = (
            run.id,
            run.raw_output,
            run.finished_at,
            copy.deepcopy(run.parameters["attempts"]),
        )
        assert session.scalar(select(func.count()).select_from(KnowledgeNode)) == 0
    with pytest.raises(ValueError, match="原文证据定位"):
        asyncio.run(run_extraction(engine, "job"))
    assert len(provider.calls) == 1
    with Session(engine) as session:
        run = session.get(ModelRun, recorded[0])
        assert (run.id, run.raw_output, run.finished_at, run.parameters["attempts"]) == recorded
        assert run.status == "received" and run.error is None
        assert run.parameters["stage_validation"]["response_invalid"] is False
        assert session.scalar(select(func.count()).select_from(KnowledgeNode)) == 0


def test_changed_support_after_timeout_stops_before_another_paid_ranking(seeded):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)
    provider = SemanticFixture("p13_timeout")
    with pytest.raises(ProviderError):
        asyncio.run(finish_reading(engine, "job", provider))
    with Session(engine) as session, session.begin():
        reading = KnowledgeStore(session).reading()
        preview_id, snapshot = reading.current("paper").id, reading.snapshot("version")
        session.delete(session.scalar(select(SourceAssertion)))
    provider.failure = None
    for _ in range(2):
        with pytest.raises(StageValidationError) as caught:
            asyncio.run(finish_reading(engine, "job", provider))
        assert caught.value.code == "SUPPORT_CONTEXT_CHANGED"
        assert not caught.value.response_invalid
    assert len(provider.calls) == 2
    with Session(engine) as session:
        reading = KnowledgeStore(session).reading()
        assert reading.snapshot("version") == snapshot  # Candidate-only snapshot is unchanged.
        assert reading.current("paper").id == preview_id
        assert session.get(Job, "job").result["stage_failure"]["category"] == "context"


def test_inflight_support_change_keeps_received_response_and_stops_repeated_requests(seeded):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)

    class ChangedSupport(SemanticFixture):
        async def complete(self, prompt, data, schema):
            raw = await super().complete(prompt, data, schema)
            if schema["title"] == "ContributionRanking":
                with Session(engine) as session, session.begin():
                    session.delete(session.scalar(select(SourceAssertion)))
            return raw

    provider = ChangedSupport()
    with pytest.raises(StageValidationError) as caught:
        asyncio.run(finish_reading(engine, "job", provider))
    assert not caught.value.response_invalid and caught.value.code == "SUPPORT_CONTEXT_CHANGED"
    with Session(engine) as session:
        run = session.scalar(select(ModelRun).where(ModelRun.prompt_name == RANKING_PROMPT))
        original = (run.id, run.status, run.error, run.finished_at, run.raw_output)
        assert run.status == "received" and run.error is None
        assert run.raw_output == provider.responses[-1][1]
        assert run.parameters["stage_validation"]["response_invalid"] is False
        assert KnowledgeStore(session).reading().current("paper") is None
    with pytest.raises(StageValidationError):
        asyncio.run(finish_reading(engine, "job", provider))
    assert len(provider.calls) == 2
    with Session(engine) as session:
        run = session.get(ModelRun, original[0])
        assert (run.id, run.status, run.error, run.finished_at, run.raw_output) == original


def test_legacy_semantic_unit_checkpoint_without_manifest_reuses_unchanged_paths(seeded):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)
    provider = SemanticFixture("p13_timeout", add_association=True)
    with pytest.raises(ProviderError):
        asyncio.run(finish_reading(engine, "job", provider))
    with Session(engine) as session, session.begin():
        job = session.get(Job, "job")
        plan = {
            k: v for k, v in job.payload["reading_finish_plan"].items() if k != "support_context"
        }
        job.payload = {**job.payload, "reading_finish_plan": plan}
        before = {}
        for checkpoint in session.scalars(select(ReadingCheckpoint)):
            before[checkpoint.key] = checkpoint.input_hash
            checkpoint.response = {
                k: v for k, v in checkpoint.response.items() if k != "support_context"
            }
    provider.failure = None
    asyncio.run(finish_reading(engine, "job", provider))
    assert len(provider.calls) == 3  # P12 is not called again.
    with Session(engine) as session:
        assert session.get(Job, "job").status == "succeeded"
        assert all(
            session.get(ReadingCheckpoint, key).input_hash == value for key, value in before.items()
        )


@pytest.mark.parametrize(
    "fault,category,code",
    [
        ("evidence", "evidence", "EVIDENCE_NOT_ALLOWED"),
        ("root", "context", "RESPONSE_ROOTS_MISMATCH"),
    ],
)
def test_semantic_alias_errors_have_stable_evidence_or_context_diagnostics(
    seeded, fault, category, code
):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)
    with pytest.raises(StageValidationError) as caught:
        asyncio.run(finish_reading(engine, "job", SemanticFixture(fault)))
    assert (caught.value.category, caught.value.code, caught.value.response_invalid) == (
        category,
        code,
        True,
    )


def test_v2_ranking_receives_all_cited_original_evidence_and_stored_issues(seeded):
    from researchgraph.unified_store import evidence_ids

    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)
    with Session(engine) as session, session.begin():
        method = session.scalar(select(KnowledgeNode).where(KnowledgeNode.kind == "method"))
        method.issues = ["Synthetic source qualification remains unresolved"]
    provider = SemanticFixture()
    asyncio.run(finish_reading(engine, "job", provider))
    ranking = provider.calls[1][1]
    assert ranking["paper_context"] == {
        "title": "Synthetic",
        "pdf_sha256": "a" * 64,
        "parser_version": "test",
    }
    supplied = {entry["evidence_ref"]: entry["text"] for entry in ranking["allowed_evidence"]}
    assert set(supplied) == evidence_ids(ranking["units"])
    with Session(engine) as session:
        assert set(supplied.values()) == {session.get(EvidenceSpan, eid).quote}
        job = session.get(Job, "job")
        assert job.payload["reading_finish_plan"]["ranking_prompt"] == RANKING_PROMPT
        assert job.payload["reading_finish_plan"]["ranking_input"]["wire"] == ranking
        run = session.scalar(select(ModelRun).where(ModelRun.prompt_name == RANKING_PROMPT))
        assert run.parameters["input_manifest"]["semantic_context"]["prompt_name"] == RANKING_PROMPT
    assert ranking["units"][0]["support_issues"]
    assert any(
        issue["issues"] == ["Synthetic source qualification remains unresolved"]
        for issue in ranking["units"][0]["support_issues"]
    )
    prompt = (PROMPT_DIR / (RANKING_PROMPT + ".md")).read_text(encoding="utf-8")
    assert_prompt_contract("P13", prompt)
    assert "insufficient_support" in prompt and "same scope, conditions and attribution" in prompt


def _legacy_finish_plan(engine, provider):
    with Session(engine) as session, session.begin():
        snapshot = KnowledgeStore(session).reading().snapshot("version")
        signature = digest(
            {
                "policy": POLICY,
                "prompts": {
                    p: text_hash((PROMPT_DIR / (p + ".md")).read_text(encoding="utf-8"))
                    for p in (INTEGRATION_PROMPT, LEGACY_RANKING_PROMPT)
                },
                "schemas": [schema_for("P12"), schema_for("P13")],
                "provider": provider.name,
                "model": provider.model,
                "parameters": getattr(provider, "parameters", {}),
                "endpoint": getattr(provider, "base_url", "offline"),
            }
        )
        job = session.get(Job, "job")
        job.payload = {
            **job.payload,
            "reading_finish_plan": {
                "flow_policy": POLICY,
                "context_policy": "complete-context-v1",
                "signature": signature,
                "snapshot": snapshot,
                "expected_revision": 0,
                "extraction_coverage_gaps": [],
            },
        }
    return signature


@pytest.mark.parametrize("interruption", ["received", "succeeded"])
def test_frozen_legacy_v1_plan_keeps_exact_wire_signature_and_cached_response(
    seeded, monkeypatch, interruption
):
    from researchgraph.reading_store import ReadingMutations

    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)
    provider = SemanticFixture()
    signature = _legacy_finish_plan(engine, provider)
    original_save, original_publish = ReadingMutations.save_checkpoint, ReadingMutations.publish

    def save_checkpoint(self, key, version_id, stage, fingerprint, response):
        if stage == "selecting":
            raise RuntimeError("Synthetic interruption after receiving complete P13")
        return original_save(self, key, version_id, stage, fingerprint, response)

    def publish(self, **request):
        raise RuntimeError("Synthetic interruption after P13 success checkpoint")

    with monkeypatch.context() as patch:
        patch.setattr(
            ReadingMutations,
            "save_checkpoint" if interruption == "received" else "publish",
            save_checkpoint if interruption == "received" else publish,
        )
        with pytest.raises(RuntimeError, match="Synthetic interruption"):
            asyncio.run(finish_reading(engine, "job", provider))
    assert original_publish is ReadingMutations.publish
    with Session(engine) as session:
        run = session.scalar(select(ModelRun).where(ModelRun.prompt_name == LEGACY_RANKING_PROMPT))
        historical = (run.id, run.raw_output, run.input_hash, run.prompt_hash)
        assert run.status == interruption
        context = run.parameters["input_manifest"]["semantic_context"]
        assert set(context) == {
            "document_version_id",
            "input_revision",
            "claim_aliases",
            "coverage_gaps",
        }
    old_wire = copy.deepcopy(provider.calls[1][1])
    assert set(old_wire) == {"contract_rules", "density", "units", "coverage_gaps"}
    assert all(set(unit) == {"claim_ref", "claim", "support"} for unit in old_wire["units"])
    asyncio.run(finish_reading(engine, "job", provider))
    assert len(provider.calls) == 2
    with Session(engine) as session:
        job = session.get(Job, "job")
        plan = job.payload["reading_finish_plan"]
        assert "ranking_prompt" not in plan and "ranking_input" not in plan
        assert plan["signature"] == signature and job.status == "succeeded"
        run = session.get(ModelRun, historical[0])
        assert (run.id, run.raw_output, run.input_hash, run.prompt_hash) == historical
        assert run.input_hash == digest(old_wire)
        key = "reading:semantic-ranking:" + digest([plan["snapshot"], signature, old_wire])
        assert session.get(ReadingCheckpoint, key).input_hash == digest(old_wire)
    assert_prompt_contract(
        "P13", (PROMPT_DIR / (LEGACY_RANKING_PROMPT + ".md")).read_text(encoding="utf-8")
    )


@pytest.mark.parametrize("fault", ["title", "source_hash", "issues"])
def test_v2_ranking_blocks_inflight_source_context_change_without_recharging(seeded, fault):
    from researchgraph.models import AttachmentRevision, Paper

    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)

    class ChangedContext(SemanticFixture):
        async def complete(self, prompt, data, schema):
            raw = await super().complete(prompt, data, schema)
            if schema["title"] == "ContributionRanking":
                with Session(engine) as session, session.begin():
                    if fault == "title":
                        session.get(Paper, "paper").title = "Changed source metadata"
                    elif fault == "source_hash":
                        session.get(AttachmentRevision, "version").sha256 = "d" * 64
                    else:
                        method = session.scalar(
                            select(KnowledgeNode).where(KnowledgeNode.kind == "method")
                        )
                        method.issues = ["New source qualification during ranking"]
            return raw

    provider = ChangedContext()
    with pytest.raises(StageValidationError) as caught:
        asyncio.run(finish_reading(engine, "job", provider))
    assert caught.value.code == (
        "RANKING_INPUT_CHANGED" if fault == "issues" else "PAPER_CONTEXT_CHANGED"
    )
    assert not caught.value.response_invalid
    with Session(engine) as session:
        run = session.scalar(select(ModelRun).where(ModelRun.prompt_name == RANKING_PROMPT))
        recorded = (run.id, run.status, run.raw_output, run.error, run.finished_at)
        assert (
            run.status == "received"
            and run.parameters["stage_validation"]["response_invalid"] is False
        )
        assert KnowledgeStore(session).reading().current("paper") is None
    with pytest.raises((StageValidationError, KnowledgeError)):
        asyncio.run(finish_reading(engine, "job", provider))
    assert len(provider.calls) == 2
    with Session(engine) as session:
        run = session.get(ModelRun, recorded[0])
        assert (run.id, run.status, run.raw_output, run.error, run.finished_at) == recorded


def test_v2_frozen_prompt_change_requires_new_build_without_new_request(
    seeded, monkeypatch, tmp_path
):
    from researchgraph import reading_finish_semantic

    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)
    for name in (INTEGRATION_PROMPT, LEGACY_RANKING_PROMPT, RANKING_PROMPT):
        (tmp_path / (name + ".md")).write_text(
            (PROMPT_DIR / (name + ".md")).read_text(encoding="utf-8"), encoding="utf-8"
        )
    monkeypatch.setattr(reading_finish_semantic, "PROMPT_DIR", tmp_path)
    provider = SemanticFixture("p13_timeout")
    with pytest.raises(ProviderError):
        asyncio.run(finish_reading(engine, "job", provider))
    prompt = tmp_path / (RANKING_PROMPT + ".md")
    prompt.write_text(
        prompt.read_text(encoding="utf-8") + "\nChanged future prompt text.\n", encoding="utf-8"
    )
    provider.failure = None
    with pytest.raises(KnowledgeError) as caught:
        asyncio.run(finish_reading(engine, "job", provider))
    assert caught.value.code == "READING_INPUT_CHANGED" and len(provider.calls) == 2


def test_v2_insufficient_semantic_support_stays_retrievable_without_rewriting_claim(seeded):
    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)
    before = source_snapshot(engine)

    class EvidenceGap(SemanticFixture):
        async def complete(self, prompt, data, schema):
            raw = await super().complete(prompt, data, schema)
            if schema["title"] == "ContributionRanking":
                assert data["allowed_evidence"]
                value = json.loads(raw)
                for hint in value["ranked_claims"]:
                    hint.update(
                        recommendation="needs_context",
                        reasons=["insufficient_support"],
                        rationale="Synthetic semantic mismatch remains unresolved",
                    )
                raw = json.dumps(value)
            return raw

    asyncio.run(finish_reading(engine, "job", EvidenceGap()))
    assert source_snapshot(engine) == before
    with Session(engine) as session:
        selection = KnowledgeStore(session).reading().current("paper")
        assert not selection.data["units"]
        assert all(entry["graph_role"] == "retrieval_only" for entry in selection.data["entries"])


def _synthetic_layout(version_id, ids):
    return {
        "policy_version": "reading-layout-context-1",
        "document_version_id": version_id,
        "parse_artifact_id": "synthetic-official-parse-id",
        "status": "checked",
        "checked_evidence_count": len(ids),
        "risk_blocks": [
            {
                "paragraph_id": "synthetic-official-paragraph-id",
                "block_ref": "block-1",
                "evidence_ids": sorted(ids),
                "risk": "numeric_script_layout",
                "lines": [
                    {
                        "text": "212",
                        "bbox": [0, 0, 20, 10],
                        "spans": [
                            {"text": "2", "size": 10, "bbox": [0, 0, 10, 10]},
                            {"text": "12", "size": 6, "bbox": [10, -3, 20, 3]},
                        ],
                        "risk_pairs": [
                            {
                                "left_span": 0,
                                "right_span": 1,
                                "size_change": True,
                                "vertical_shift": True,
                            }
                        ],
                    }
                ],
            }
        ],
        "unresolved_evidence": [],
    }


def test_v2_layout_context_preserves_geometry_and_binds_only_short_evidence_aliases(
    seeded, monkeypatch
):
    from researchgraph import reading_evidence_quality

    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)
    contexts = []

    def layout(_session, version_id, ids):
        assert version_id == "version" and set(ids) == {eid}
        result = _synthetic_layout(version_id, ids)
        contexts.append(copy.deepcopy(result))
        return result

    monkeypatch.setattr(reading_evidence_quality, "layout_context", layout)
    provider = SemanticFixture()
    asyncio.run(finish_reading(engine, "job", provider))
    wire = provider.calls[1][1]["evidence_layout_context"]
    assert wire["status"] == "checked" and wire["checked_evidence_count"] == 1
    assert wire["risk_blocks"][0]["evidence_refs"] == ["e0001"]
    assert wire["risk_blocks"][0]["lines"] == contexts[0]["risk_blocks"][0]["lines"]
    encoded = json.dumps(wire)
    assert eid not in encoded and "synthetic-official" not in encoded
    assert (
        "document_version_id" not in encoded
        and "paragraph_id" not in encoded
        and "parse_artifact_id" not in encoded
    )
    assert len(contexts) >= 4  # Freeze, pre-request, terminal validation and publication.
    with Session(engine) as session:
        frozen = session.get(Job, "job").payload["reading_finish_plan"]["ranking_input"]
        assert frozen["canonical"]["evidence_layout_context"] == contexts[0]
        assert frozen["canonical"]["layout_evidence_ids"] == [eid]


def test_v2_layout_change_during_response_preserves_received_run_and_blocks_paid_retry(
    seeded, monkeypatch
):
    from researchgraph import reading_evidence_quality

    _, engine, eid = seeded
    save(engine, eid)
    setup_job(engine)
    changed = False

    def layout(_session, version_id, ids):
        result = _synthetic_layout(version_id, ids)
        if changed:
            result["parse_artifact_id"] = "new-synthetic-parse-id"
        return result

    class ChangedLayout(SemanticFixture):
        async def complete(self, prompt, data, schema):
            nonlocal changed
            raw = await super().complete(prompt, data, schema)
            if schema["title"] == "ContributionRanking":
                changed = True
            return raw

    monkeypatch.setattr(reading_evidence_quality, "layout_context", layout)
    provider = ChangedLayout()
    with pytest.raises(StageValidationError) as caught:
        asyncio.run(finish_reading(engine, "job", provider))
    assert (
        caught.value.code == "EVIDENCE_LAYOUT_CONTEXT_CHANGED" and not caught.value.response_invalid
    )
    with Session(engine) as session:
        run = session.scalar(select(ModelRun).where(ModelRun.prompt_name == RANKING_PROMPT))
        original = (run.id, run.status, run.error, run.finished_at, run.raw_output)
        assert run.status == "received" and run.error is None
        assert run.parameters["stage_validation"]["response_invalid"] is False
        assert KnowledgeStore(session).reading().current("paper") is None
    with pytest.raises(StageValidationError) as retry:
        asyncio.run(finish_reading(engine, "job", provider))
    assert retry.value.code == "RANKING_INPUT_CHANGED" and not retry.value.response_invalid
    assert len(provider.calls) == 2
    with Session(engine) as session:
        run = session.get(ModelRun, original[0])
        assert (run.id, run.status, run.error, run.finished_at, run.raw_output) == original
