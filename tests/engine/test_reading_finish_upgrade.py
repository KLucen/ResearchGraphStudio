"""Legacy ranking failures move to the new protocol without another P12 call."""

import asyncio
import copy

import pytest
import test_knowledge
from researchgraph import reading_finish_semantic, reading_selection
from researchgraph.graph_models import SourceAssertion
from researchgraph.knowledge_models import EvidenceSpan, ModelRun
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, digest
from researchgraph.models import Job, now
from researchgraph.providers import ProviderError
from researchgraph.reading_finish_upgrade import (
    adopt_integration,
    available,
    integration_input,
    upgrade_job,
)
from researchgraph.reading_finish_wire import INTEGRATION_PROMPT, RANKING_PROMPT
from researchgraph.reading_pipeline import finish_reading
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_engine import post
from test_reading_extraction import save
from test_reading_semantic_flow import SemanticFixture, setup_job, source_snapshot

seeded = test_knowledge.seeded


def legacy_failure(engine, eid, monkeypatch, *, association=True):
    save(engine, eid)
    setup_job(engine)
    with monkeypatch.context() as patch:
        patch.setattr(reading_finish_semantic, "DEFAULT_RANKING_PROMPT", RANKING_PROMPT)
        with pytest.raises(ProviderError):
            asyncio.run(
                finish_reading(
                    engine, "job", SemanticFixture("p13_timeout", add_association=association)
                )
            )
    with Session(engine) as session, session.begin():
        job = session.get(Job, "job")
        job.status, job.attempt = "failed", 3
        return copy.deepcopy(job.payload)


def history(session):
    return {
        run.id: (
            run.status,
            run.error,
            run.finished_at,
            run.raw_output,
            copy.deepcopy(run.parameters),
        )
        for run in session.scalars(select(ModelRun))
    }


def test_retry_upgrades_at_attempt_limit_and_preserves_original_history(seeded, monkeypatch):
    api, engine, eid = seeded
    original_payload = legacy_failure(engine, eid, monkeypatch)
    before = source_snapshot(engine)
    with Session(engine) as session:
        old_runs = history(session)
        old_result = copy.deepcopy(session.get(Job, "job").result)
    response = post(api, "/jobs/job/retry", key="ranking-upgrade")
    assert response.status_code == 200, response.text
    successor_id = response.json()["id"]
    assert successor_id != "job"
    assert post(api, "/jobs/job/retry", key="ranking-upgrade-again").json()["id"] == successor_id
    assert source_snapshot(engine) == before
    with Session(engine) as session:
        old, new = session.get(Job, "job"), session.get(Job, successor_id)
        assert (
            old.payload == original_payload and old.result == old_result and old.status == "failed"
        )
        assert history(session) == old_runs
        assert new.status == "queued" and new.attempt == 0
        assert new.payload["reading_only"] and new.payload["resumed_from"] == "job"
        assert "reading_finish_plan" not in new.payload
        assert new.payload["provider"] == original_payload["provider"]
        assert new.result["model_calls"] == 0 and new.result["ranking_protocol_upgraded"]


@pytest.mark.parametrize("fault", ["snapshot", "support", "evidence", "raw", "manifest"])
def test_unsafe_legacy_inputs_block_upgrade_before_calls_or_successor(seeded, monkeypatch, fault):
    _, engine, eid = seeded
    legacy_failure(engine, eid, monkeypatch)
    with Session(engine) as session, session.begin():
        old = session.get(Job, "job")
        if fault == "snapshot":
            payload = copy.deepcopy(old.payload)
            payload["reading_finish_plan"]["snapshot"] = "f" * 64
            old.payload = payload
        elif fault == "support":
            edge = session.scalar(select(SourceAssertion))
            session.delete(edge)
        elif fault == "evidence":
            session.get(EvidenceSpan, eid).end_offset -= 1
        else:
            run = session.scalar(select(ModelRun).where(ModelRun.prompt_name == INTEGRATION_PROMPT))
            if fault == "raw":
                run.raw_output = '{"associations":'
            else:
                run.parameters = {**run.parameters, "input_manifest": {}}
    with Session(engine) as session:
        old_runs = history(session)
    with Session(engine) as session, session.begin():
        with pytest.raises(KnowledgeError):
            upgrade_job(session, session.get(Job, "job"))
    with Session(engine) as session:
        assert history(session) == old_runs
        assert session.scalar(select(func.count()).select_from(Job)) == 1


def test_adopted_p12_has_real_provenance_and_zero_additional_model_runs(seeded, monkeypatch):
    _, engine, eid = seeded
    legacy_failure(engine, eid, monkeypatch)
    before = source_snapshot(engine)
    with Session(engine) as session, session.begin():
        successor = upgrade_job(session, session.get(Job, "job"))
        jid = successor.id
        old_runs = history(session)
        original_support = KnowledgeStore(session).reading().snapshot("version")
    with Session(engine) as session, session.begin():
        job = session.get(Job, jid)
        frozen = integration_input(session, job)
        assert frozen == session.get(Job, "job").payload["reading_finish_plan"]["integration_input"]
        integrated = adopt_integration(
            session,
            job,
            frozen["wire"],
            frozen["canonical"],
            frozen["context"],
            original_support,
            "new-protocol:integration",
        )
        assert integrated is not None
        provenance = job.result["integration_adopted"]
        assert provenance["source_job_id"] == "job" and provenance["new_requests"] == 0
        assert provenance["terminal_revalidated"]
        assert provenance["input_hash"] == digest(frozen["wire"])
        assert session.get(ModelRun, provenance["source_model_run_id"]).job_id == "job"
    assert source_snapshot(engine) == before
    with Session(engine) as session:
        # Integration may append deterministic audit fields, but never change
        # original status/error/time/raw or create a synthetic model invocation.
        after_runs = history(session)
        assert after_runs.keys() == old_runs.keys()
        assert {key: value[:4] for key, value in after_runs.items()} == {
            key: value[:4] for key, value in old_runs.items()
        }
        assert (
            KnowledgeStore(session)
            .reading()
            .checkpoint("new-protocol:integration", digest(frozen["wire"]))
            == integrated
        )


@pytest.mark.parametrize("fault", ["marker", "new_relation", "candidate_input"])
def test_successor_rechecks_immutable_input_and_paths_before_adoption(seeded, monkeypatch, fault):
    _, engine, eid = seeded
    legacy_failure(engine, eid, monkeypatch)
    with Session(engine) as session, session.begin():
        successor = upgrade_job(session, session.get(Job, "job"))
        jid = successor.id
        frozen = integration_input(session, successor)
        snapshot = successor.payload["semantic_finish_upgrade"]["snapshot"]
    with Session(engine) as session, session.begin():
        job = session.get(Job, jid)
        if fault == "marker":
            payload = copy.deepcopy(job.payload)
            payload["semantic_finish_upgrade"]["source_signature"] = "changed"
            job.payload = payload
        elif fault == "new_relation":
            session.delete(session.scalar(select(SourceAssertion)))
        else:
            frozen["canonical"]["candidates"][0]["content"]["label"]["original"] = "changed"
    with Session(engine) as session, session.begin():
        with pytest.raises(KnowledgeError):
            adopt_integration(
                session,
                session.get(Job, jid),
                frozen["wire"],
                frozen["canonical"],
                frozen["context"],
                snapshot,
                "new-protocol:integration",
            )
        assert (
            KnowledgeStore(session)
            .reading()
            .checkpoint("new-protocol:integration", digest(frozen["wire"]))
            is None
        )


@pytest.mark.parametrize("stage", ["integrating", "extracting", "publishing"])
def test_only_old_p13_failures_are_eligible(seeded, monkeypatch, stage):
    _, engine, eid = seeded
    legacy_failure(engine, eid, monkeypatch)
    with Session(engine) as session:
        job = session.get(Job, "job")
        assert available(job)
        job.result = {**job.result, "stage_failure": {"stage": stage}}
        assert not available(job)


def test_active_same_paper_blocks_new_successor(seeded, monkeypatch):
    _, engine, eid = seeded
    legacy_failure(engine, eid, monkeypatch)
    setup_job(engine, "active")
    with Session(engine) as session, session.begin():
        with pytest.raises(KnowledgeError, match="仍有任务运行"):
            upgrade_job(session, session.get(Job, "job"))


def adopted_failure(session, jid, source_id="job", *, result_provenance=False):
    source = session.get(Job, source_id)
    payload = copy.deepcopy(source.payload)
    original = session.scalar(
        select(ModelRun).where(
            ModelRun.job_id == "job",
            ModelRun.prompt_name == INTEGRATION_PROMPT,
            ModelRun.status == "succeeded",
        )
    )
    adoption = {
        "source_job_id": source_id,
        "source_model_run_id": original.id,
        "input_hash": digest(payload["reading_finish_plan"]["integration_input"]["wire"]),
        "new_requests": 0,
        "terminal_revalidated": True,
    }
    result = copy.deepcopy(source.result)
    if result_provenance:
        result["integration_adopted"] = adoption
    else:
        payload["adopted_stage"] = {"stage": "P12", **adoption}
    job = Job(
        id=jid,
        kind=source.kind,
        project_id=source.project_id,
        payload=payload,
        result=result,
        status="failed",
        stage="selecting",
        attempt=3,
        created_at=now(),
        updated_at=now(),
    )
    session.add(job)
    session.flush()
    return job


@pytest.mark.parametrize("chain", [False, True])
def test_explicit_p12_adoption_lineage_reuses_original_real_run(seeded, monkeypatch, chain):
    _, engine, eid = seeded
    legacy_failure(engine, eid, monkeypatch)
    before = source_snapshot(engine)
    with Session(engine) as session, session.begin():
        source = adopted_failure(session, "continued")
        if chain:
            source = adopted_failure(
                session, "continued-again", "continued", result_provenance=True
            )
        old_runs = history(session)
        successor = upgrade_job(session, source)
        original_run_id = successor.payload["semantic_finish_upgrade"]["source_model_run_id"]
        assert session.get(ModelRun, original_run_id).job_id == "job"
        frozen = integration_input(session, successor)
        integrated = adopt_integration(
            session,
            successor,
            frozen["wire"],
            frozen["canonical"],
            frozen["context"],
            source.payload["reading_finish_plan"]["snapshot"],
            "lineage:integration",
        )
        assert integrated is not None
        assert successor.result["integration_adopted"]["source_job_id"] == source.id
        assert successor.result["integration_adopted"]["source_model_run_id"] == original_run_id
        assert successor.result["integration_adopted"]["new_requests"] == 0
        after_runs = history(session)
        assert {k: v[:4] for k, v in after_runs.items()} == {k: v[:4] for k, v in old_runs.items()}
    assert source_snapshot(engine) == before


@pytest.mark.parametrize(
    "fault",
    ["run", "input_hash", "stage", "requests", "terminal", "cycle", "project", "input", "support"],
)
def test_p12_adoption_lineage_requires_exact_trusted_provenance(seeded, monkeypatch, fault):
    _, engine, eid = seeded
    legacy_failure(engine, eid, monkeypatch)
    with Session(engine) as session, session.begin():
        top = adopted_failure(session, "continued")
        payload = copy.deepcopy(top.payload)
        adoption = payload["adopted_stage"]
        if fault == "run":
            adoption["source_model_run_id"] = "run"
        elif fault == "input_hash":
            adoption["input_hash"] = "wrong"
        elif fault == "stage":
            adoption["stage"] = "P13"
        elif fault == "requests":
            adoption["new_requests"] = 1
        elif fault == "terminal":
            adoption["terminal_revalidated"] = False
        elif fault == "cycle":
            adoption["source_job_id"] = top.id
        elif fault == "project":
            top.project_id = None
        elif fault == "input":
            payload["reading_finish_plan"]["integration_input"]["canonical"]["candidates"][0][
                "content"
            ]["label"]["original"] = "different immutable input"
        else:
            payload["reading_finish_plan"]["support_context"] = {"changed": True}
        top.payload = payload
    with Session(engine) as session:
        old_runs = history(session)
    with Session(engine) as session, session.begin():
        with pytest.raises(KnowledgeError):
            upgrade_job(session, session.get(Job, "continued"))
    with Session(engine) as session:
        assert history(session) == old_runs
        assert session.scalar(select(func.count()).select_from(Job)) == 2


@pytest.mark.parametrize("fault", ["pipeline", "schema_hash", "semantic_context", "extra"])
def test_p12_manifest_must_match_entire_frozen_contract(seeded, monkeypatch, fault):
    _, engine, eid = seeded
    legacy_failure(engine, eid, monkeypatch)
    with Session(engine) as session, session.begin():
        run = session.scalar(
            select(ModelRun).where(
                ModelRun.prompt_name == INTEGRATION_PROMPT, ModelRun.status == "succeeded"
            )
        )
        params = copy.deepcopy(run.parameters)
        params["input_manifest"][fault] = "unexpected"
        run.parameters = params
    with Session(engine) as session, session.begin():
        with pytest.raises(KnowledgeError):
            upgrade_job(session, session.get(Job, "job"))


def test_store_adoption_diagnostics_preserve_all_historical_run_parameters(seeded, monkeypatch):
    _, engine, eid = seeded
    legacy_failure(engine, eid, monkeypatch)
    original_integrate = reading_selection.integrate

    def integration_with_diagnostic(store, **request):
        result = original_integrate(store, **request)
        run = store.session.get(ModelRun, request["run_id"])
        run.parameters = {**run.parameters, "new_adoption_diagnostic": {"count": 1}}
        return result

    monkeypatch.setattr(reading_selection, "integrate", integration_with_diagnostic)
    with Session(engine) as session, session.begin():
        successor = upgrade_job(session, session.get(Job, "job"))
        frozen = integration_input(session, successor)
        original_history = history(session)
        adopt_integration(
            session,
            successor,
            frozen["wire"],
            frozen["canonical"],
            frozen["context"],
            successor.payload["semantic_finish_upgrade"]["snapshot"],
            "diagnostic:integration",
        )
        assert history(session) == original_history
        assert successor.result["integration_adopted"]["store_diagnostics"] == {
            "new_adoption_diagnostic": {"count": 1}
        }
