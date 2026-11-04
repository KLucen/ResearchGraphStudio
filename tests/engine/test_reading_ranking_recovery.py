"""Real orchestration with synthetic providers, never real credentials or API calls."""

import asyncio
import copy
import json

import pytest
import test_knowledge
from researchgraph.knowledge_models import KnowledgeNode, ModelRun
from researchgraph.knowledge_store import KnowledgeStore
from researchgraph.models import Job
from researchgraph.providers import ProviderError
from researchgraph.reading_pipeline import finish_reading
from researchgraph.reading_ranking_wire import PROMPT
from researchgraph.reading_stage_validation import StageValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_reading_extraction import candidate_batch, save
from test_reading_semantic_flow import SemanticFixture, setup_job, source_snapshot

seeded = test_knowledge.seeded


class KeyedFixture(SemanticFixture):
    def __init__(self, fault=None, *, always=False, engine=None):
        super().__init__()
        self.fault, self.always, self.engine = fault, always, engine
        self.keyed_calls = 0

    async def complete(self, prompt, data, schema):
        if schema["title"] != "KeyedContributionRanking":
            return await super().complete(prompt, data, schema)
        self.calls.append((schema["title"], copy.deepcopy(data)))
        self.keyed_calls += 1
        value = {
            "assessments": {
                ref: {
                    "recommendation": "suggest_core",
                    "reasons": ["main_contribution"],
                    "rationale": "Synthetic evidence-aware contribution",
                    "priority": 50,
                }
                for ref in data["assessment_refs"]
            },
            "warnings": [],
        }
        if self.keyed_calls == 1 or self.always:
            ref = data["assessment_refs"][-1]
            if self.fault == "missing":
                value["assessments"].pop(ref)
            elif self.fault == "extra_slot":
                value["assessments"][ref]["note_unused"] = "Untrusted extra content"
            elif self.fault == "extra_root":
                value["warnings_note"] = "Untrusted extra content"
            elif self.fault == "legacy_conflict":
                value = {
                    "ranked_claims": [
                        {"claim_ref": ref, "recommendation": "suggest_core"},
                        {"claim_ref": ref, "recommendation": "keep_retrievable"},
                    ],
                    "warnings": [],
                }
            elif self.fault == "unknown_alias":
                value["assessments"]["c9999"] = value["assessments"][ref]
            elif self.fault == "timeout":
                raise ProviderError("timeout", "Synthetic timeout", timeout_phase="total")
            elif self.fault == "source_change":
                with Session(self.engine) as session, session.begin():
                    node = session.scalar(
                        select(KnowledgeNode).where(KnowledgeNode.kind == "method")
                    )
                    node.issues = ["Changed source interpretation"]
        raw = json.dumps(value)
        if (self.keyed_calls == 1 or self.always) and self.fault == "duplicate_key":
            raw = '{"assessments":{},"assessments":{},"warnings":[]}'
        if (self.keyed_calls == 1 or self.always) and self.fault == "invalid_json":
            raw = raw[:-2]
        self.responses.append((schema["title"], raw))
        return raw


def prepare(engine, eid):
    batch = candidate_batch(eid)
    second = copy.deepcopy(batch["items"][0])
    second["local_ref"] = "second"
    second["statement"]["original"] = "A second synthetic independent conclusion"
    second["label"]["original"] = "A second synthetic conclusion"
    batch["items"].append(second)
    save(engine, eid, batch)
    setup_job(engine)


def test_keyed_finish_uses_new_frozen_contract_and_program_order(seeded):
    _, engine, eid = seeded
    prepare(engine, eid)
    before = source_snapshot(engine)
    provider = KeyedFixture()
    asyncio.run(finish_reading(engine, "job", provider))
    assert source_snapshot(engine) == before
    assert [title for title, _ in provider.calls] == [
        "SemanticIntegration",
        "KeyedContributionRanking",
    ]
    with Session(engine) as session:
        job = session.get(Job, "job")
        assert job.payload["reading_finish_plan"]["ranking_prompt"] == PROMPT
        assert job.status == "succeeded" and job.result["ranking_completed_claims"] == 2
        assert job.result["ranking_total_claims"] == 2
        current = KnowledgeStore(session).reading().current("paper")
        assert job.result["ranking_status"] == "complete"
        assert current.data.get("selection_mode") != "provisional"
        run = session.scalar(select(ModelRun).where(ModelRun.prompt_name == PROMPT))
        assert run.parameters["ranking_recovery"]["terminal_validated"] is True
        assert len(run.parameters["ranking_recovery"]["slot_provenance"]) == 2


@pytest.mark.parametrize("fault", ["missing", "extra_slot"])
def test_repair_only_invalid_slot_preserves_valid_decision_and_full_context(seeded, fault):
    _, engine, eid = seeded
    prepare(engine, eid)
    before = source_snapshot(engine)
    provider = KeyedFixture(fault)
    asyncio.run(finish_reading(engine, "job", provider))
    assert source_snapshot(engine) == before
    first, repair = [data for title, data in provider.calls if title == "KeyedContributionRanking"]
    assert len(first["assessment_refs"]) == 2 and len(repair["assessment_refs"]) == 1
    assert first["units"] == repair["units"]
    assert first["allowed_evidence"] == repair["allowed_evidence"]
    assert first["evidence_layout_context"] == repair["evidence_layout_context"]
    assert len(repair["completed_assessments"]) == 1
    assert not set(repair["completed_assessments"]) & set(repair["assessment_refs"])
    assert "Untrusted extra content" not in json.dumps(repair)
    with Session(engine) as session:
        runs = list(
            session.scalars(
                select(ModelRun).where(ModelRun.prompt_name == PROMPT).order_by(ModelRun.created_at)
            )
        )
        assert [run.status for run in runs] == ["validation_failed", "succeeded"]
        assert [run.raw_output for run in runs] == [
            raw for title, raw in provider.responses if title == "KeyedContributionRanking"
        ]
        provenance = runs[-1].parameters["ranking_recovery"]["slot_provenance"]
        assert {entry["run_id"] for entry in provenance.values()} == {run.id for run in runs}
        assert session.get(Job, "job").result["model_calls"] == 3


@pytest.mark.parametrize(
    "fault", ["extra_root", "legacy_conflict", "unknown_alias", "duplicate_key", "invalid_json"]
)
def test_bad_envelope_is_not_silently_dropped_or_merged_but_corrected_once(seeded, fault):
    _, engine, eid = seeded
    prepare(engine, eid)
    provider = KeyedFixture(fault)
    asyncio.run(finish_reading(engine, "job", provider))
    first, repair = [data for title, data in provider.calls if title == "KeyedContributionRanking"]
    assert repair["assessment_refs"] == first["assessment_refs"]
    assert "protocol_correction" in repair
    with Session(engine) as session:
        job = session.get(Job, "job")
        assert job.status == "succeeded" and job.result["ranking_status"] == "complete"


def test_exhaustion_is_persisted_and_continue_never_recharges_same_bad_response(seeded):
    _, engine, eid = seeded
    prepare(engine, eid)
    before = source_snapshot(engine)
    provider = KeyedFixture("extra_slot", always=True)
    for _ in range(3):
        with pytest.raises(StageValidationError) as caught:
            asyncio.run(finish_reading(engine, "job", provider))
        assert caught.value.code == "RANKING_PROTOCOL_EXHAUSTED"
    assert provider.keyed_calls == 2
    assert source_snapshot(engine) == before
    with Session(engine) as session:
        assert session.get(Job, "job").result["ranking_status"] == "pending"
        assert session.get(Job, "job").result["model_calls"] == 3
        selection = KnowledgeStore(session).reading().current("paper")
        assert selection.data["selection_mode"] == "provisional"
        assert len(session.get(Job, "job").payload["reading_ranking_state"]["requests"]) == 2


def test_timeout_is_not_automatically_resent_but_explicit_resume_uses_last_slot(seeded):
    _, engine, eid = seeded
    prepare(engine, eid)
    provider = KeyedFixture("timeout")
    with pytest.raises(ProviderError):
        asyncio.run(finish_reading(engine, "job", provider))
    assert provider.keyed_calls == 1
    provider.fault = None
    asyncio.run(finish_reading(engine, "job", provider))
    assert provider.keyed_calls == 2
    with Session(engine) as session:
        assert session.get(Job, "job").status == "succeeded"


def test_source_change_blocks_repair_without_rewriting_received_history(seeded):
    _, engine, eid = seeded
    prepare(engine, eid)
    provider = KeyedFixture("source_change", engine=engine)
    with pytest.raises(StageValidationError) as caught:
        asyncio.run(finish_reading(engine, "job", provider))
    assert caught.value.response_invalid is False
    with Session(engine) as session:
        run = session.scalar(select(ModelRun).where(ModelRun.prompt_name == PROMPT))
        original = (run.status, run.error, run.finished_at, run.raw_output)
        assert run.status == "received"
    with pytest.raises(StageValidationError):
        asyncio.run(finish_reading(engine, "job", provider))
    assert provider.keyed_calls == 1
    with Session(engine) as session:
        run = session.get(ModelRun, run.id)
        assert (run.status, run.error, run.finished_at, run.raw_output) == original


@pytest.mark.parametrize("fault", ["raw", "version", "schema", "parameters"])
def test_cached_lineage_change_stops_without_recharge_or_history_rewrite(seeded, fault):
    _, engine, eid = seeded
    prepare(engine, eid)
    provider = KeyedFixture("extra_slot", always=True)
    with pytest.raises(StageValidationError):
        asyncio.run(finish_reading(engine, "job", provider))
    with Session(engine) as session, session.begin():
        run = session.scalar(
            select(ModelRun).where(ModelRun.prompt_name == PROMPT).order_by(ModelRun.created_at)
        )
        if fault == "raw":
            value = json.loads(run.raw_output)
            value["assessments"]["c0001"]["rationale"] = "A substituted legal private decision"
            run.raw_output = json.dumps(value)
        elif fault == "version":
            from researchgraph.models import AttachmentRevision

            original_version = session.get(AttachmentRevision, "version")
            session.add(
                AttachmentRevision(
                    id="other-version",
                    paper_id="paper",
                    sha256="b" * 64,
                    parser_version=original_version.parser_version,
                    page_count=1,
                    warnings=[],
                    created_at=original_version.created_at,
                )
            )
            session.flush()
            run.document_version_id = "other-version"
        elif fault == "schema":
            run.schema_version = "other-contract"
        else:
            run.parameters = {**run.parameters, "temperature": 1}
        original = (run.id, run.status, run.error, run.finished_at, run.raw_output)
    with pytest.raises(StageValidationError) as caught:
        asyncio.run(finish_reading(engine, "job", provider))
    assert caught.value.response_invalid is False and provider.keyed_calls == 2
    with Session(engine) as session:
        run = session.get(ModelRun, original[0])
        assert (run.id, run.status, run.error, run.finished_at, run.raw_output) == original


def test_received_response_crash_reuses_raw_without_another_call(seeded, monkeypatch):
    from researchgraph import reading_ranking

    _, engine, eid = seeded
    prepare(engine, eid)
    provider = KeyedFixture()
    split = reading_ranking.split_validate
    with monkeypatch.context() as patch:

        def crash(*_):
            raise RuntimeError("Synthetic process interruption after receipt")

        patch.setattr(reading_ranking, "split_validate", crash)
        with pytest.raises(RuntimeError):
            asyncio.run(finish_reading(engine, "job", provider))
    assert reading_ranking.split_validate == split
    asyncio.run(finish_reading(engine, "job", provider))
    assert provider.keyed_calls == 1
    with Session(engine) as session:
        assert session.get(Job, "job").status == "succeeded"


def test_old_failed_sort_continues_with_one_new_p13_and_no_p02_or_p12(seeded, monkeypatch):
    from researchgraph import reading_finish_semantic
    from researchgraph.reading_finish_upgrade import upgrade_job
    from researchgraph.reading_finish_wire import RANKING_PROMPT

    _, engine, eid = seeded
    prepare(engine, eid)
    with monkeypatch.context() as patch:
        patch.setattr(reading_finish_semantic, "DEFAULT_RANKING_PROMPT", RANKING_PROMPT)
        with pytest.raises(ProviderError):
            asyncio.run(
                finish_reading(engine, "job", SemanticFixture("p13_timeout", add_association=True))
            )
    before = source_snapshot(engine)
    with Session(engine) as session, session.begin():
        old = session.get(Job, "job")
        old.status, old.attempt = "failed", 3
        frozen_payload = copy.deepcopy(old.payload)
        successor = upgrade_job(session, old)
        successor.status, successor.attempt = "running", 1
        jid = successor.id
        old_runs = {
            run.id: (run.raw_output, run.status, run.error, run.finished_at)
            for run in session.scalars(select(ModelRun))
        }
    provider = KeyedFixture()
    asyncio.run(finish_reading(engine, jid, provider))
    assert [title for title, _ in provider.calls] == ["KeyedContributionRanking"]
    assert source_snapshot(engine) == before
    with Session(engine) as session:
        assert session.get(Job, "job").payload == frozen_payload
        assert session.get(Job, jid).status == "succeeded"
        assert session.get(Job, jid).result["integration_adopted"]["new_requests"] == 0
        for rid, historical in old_runs.items():
            run = session.get(ModelRun, rid)
            assert (run.raw_output, run.status, run.error, run.finished_at) == historical
