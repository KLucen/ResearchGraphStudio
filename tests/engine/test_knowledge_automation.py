"""A committed parsing receipt recovers K2 without replaying parsing or sent slots."""

import asyncio
from uuid import uuid4

import pytest
from researchgraph.core import KnowledgeError
from researchgraph.knowledge_automation import note_parsed
from researchgraph.knowledge_connection_models import (
    KnowledgeAnalysisEvent,
    KnowledgeCollectionEvent,
    KnowledgeConnectionRun,
)
from researchgraph.knowledge_extraction_models import KnowledgeExtractionRun
from researchgraph.knowledge_library import ensure_library
from researchgraph.knowledge_library_contracts import LibrarySettings
from researchgraph.knowledge_tasks import queue_knowledge_extract, run_knowledge_extract
from researchgraph.model_document_models import LlmDocumentParse, LlmDocumentSegment
from researchgraph.models import Job, now
from researchgraph.storage import make_engine
from researchgraph.task_worker import after_knowledge_job, dispatch_pending_knowledge
from sqlalchemy.orm import Session
from test_knowledge_extraction import SNAPSHOT, FixtureProvider, model_fixture


def _policy(db, **changes):
    settings = LibrarySettings(auto_collect=True, allow_network=True, **changes)
    ensure_library(db).settings_json = settings.model_dump()


def _parsed(db, parse_id):
    job = Job(
        id=str(uuid4()),
        kind="llm_document_parse",
        project_id=None,
        payload={},
        status="succeeded",
        stage="completed",
        result={"parse_id": parse_id},
        created_at=now(),
        updated_at=now(),
    )
    db.add(job)
    db.flush()
    return job


def test_atomic_receipt_recovers_after_parse_commit_without_reparsing_or_duplicate_k2(
    tmp_path, monkeypatch
):
    engine, paper_id, parse_id = model_fixture(tmp_path)
    monkeypatch.setattr("researchgraph.knowledge_automation.snapshot_for", lambda *_: SNAPSHOT)
    with Session(engine) as db, db.begin():
        _policy(db, max_output_tokens=1000, total_request_limit=4)
        job = _parsed(db, parse_id)
        note_parsed(db, job)
        identity = job.id
        assert db.get(KnowledgeCollectionEvent, identity).source_fingerprint
        assert db.query(KnowledgeExtractionRun).count() == 0
    # The process can stop here, before app.after_knowledge_job gets control.
    engine.dispose()
    restarted = make_engine(tmp_path / "knowledge")
    with Session(restarted) as db, db.begin():
        _policy(db, max_output_tokens=500, total_request_limit=3)
    dispatch_pending_knowledge(restarted)
    dispatch_pending_knowledge(restarted)
    with Session(restarted) as db:
        assert db.query(LlmDocumentParse).count() == 1
        assert db.query(Job).filter(Job.kind == "llm_document_parse").count() == 1
        assert db.query(Job).filter(Job.kind == "knowledge_extract").count() == 1
        run = db.query(KnowledgeExtractionRun).one()
        assert run.paper_id == paper_id and not run.request_sent
        assert run.policy_json["max_output_tokens"] == 500
        assert run.policy_json["total_request_limit"] == 3
        event = db.get(KnowledgeCollectionEvent, identity)
        assert event.state == "queued" and event.extraction_job_id == run.job_id


def test_old_unmarked_parse_is_never_scanned_when_automatic_policy_is_enabled(tmp_path):
    engine, _paper_id, parse_id = model_fixture(tmp_path)
    with Session(engine) as db, db.begin():
        old = _parsed(db, parse_id)
        note_parsed(db, old)  # disabled at source publication
        assert db.query(KnowledgeCollectionEvent).count() == 0
        _policy(db)
    dispatch_pending_knowledge(engine)
    with Session(engine) as db:
        assert db.query(KnowledgeExtractionRun).count() == 0


def test_receipt_rolls_back_with_source_publication_and_rejects_changed_source(
    tmp_path, monkeypatch
):
    engine, _paper_id, parse_id = model_fixture(tmp_path)
    monkeypatch.setattr("researchgraph.knowledge_automation.snapshot_for", lambda *_: SNAPSHOT)
    with pytest.raises(RuntimeError), Session(engine) as db, db.begin():
        _policy(db)
        note_parsed(db, _parsed(db, parse_id))
        raise RuntimeError("synthetic publication failure")
    with Session(engine) as db, db.begin():
        assert db.query(KnowledgeCollectionEvent).count() == 0
        _policy(db)
        job = _parsed(db, parse_id)
        note_parsed(db, job)
        identity = job.id
        segment = (
            db.query(LlmDocumentSegment)
            .filter(
                LlmDocumentSegment.parse_id == parse_id,
                LlmDocumentSegment.kind == "paragraph",
            )
            .first()
        )
        segment.text = "Changed source after publication"
    dispatch_pending_knowledge(engine)
    with Session(engine) as db:
        assert db.query(KnowledgeExtractionRun).count() == 0
        event = db.get(KnowledgeCollectionEvent, identity)
        assert event.state == "failed" and event.reason == "KNOWLEDGE_SOURCE_CHANGED"


def test_missing_model_keeps_explicit_receipt_and_current_policy_can_pause_dispatch(
    tmp_path, monkeypatch
):
    engine, _paper_id, parse_id = model_fixture(tmp_path)

    def missing(*_):
        raise KnowledgeError("MODEL_NOT_CONFIGURED", "synthetic no selected model")

    monkeypatch.setattr("researchgraph.knowledge_automation.snapshot_for", missing)
    with Session(engine) as db, db.begin():
        _policy(db)
        job = _parsed(db, parse_id)
        note_parsed(db, job)
        identity = job.id
    with Session(engine) as db, db.begin():
        event = db.get(KnowledgeCollectionEvent, identity)
        assert event.state == "pending" and event.reason == "MODEL_NOT_CONFIGURED"
        assert event.source_fingerprint is not None
        ensure_library(db).settings_json = LibrarySettings().model_dump()
    monkeypatch.setattr("researchgraph.knowledge_automation.snapshot_for", lambda *_: SNAPSHOT)
    dispatch_pending_knowledge(engine)
    with Session(engine) as db, db.begin():
        assert db.query(KnowledgeExtractionRun).count() == 0
        _policy(db)
    dispatch_pending_knowledge(engine)
    with Session(engine) as db:
        assert db.query(KnowledgeExtractionRun).count() == 1
        assert db.get(KnowledgeCollectionEvent, identity).state == "queued"


def test_receipt_never_retries_a_cancelled_or_failed_extraction(tmp_path, monkeypatch):
    engine, _paper_id, parse_id = model_fixture(tmp_path)
    monkeypatch.setattr("researchgraph.knowledge_automation.snapshot_for", lambda *_: SNAPSHOT)
    with Session(engine) as db, db.begin():
        _policy(db)
        note_parsed(db, _parsed(db, parse_id))
    dispatch_pending_knowledge(engine)
    with Session(engine) as db, db.begin():
        run = db.query(KnowledgeExtractionRun).one()
        run.status, run.request_sent, run.raw_response = "failed", True, "bad raw kept"
        db.get(Job, run.job_id).status = "cancelled"
        db.query(KnowledgeCollectionEvent).one().state = "pending"
    dispatch_pending_knowledge(engine)
    with Session(engine) as db:
        run = db.query(KnowledgeExtractionRun).one()
        assert run.status == "failed" and run.raw_response == "bad raw kept"
        assert db.get(Job, run.job_id).status == "cancelled"
        assert db.query(Job).filter(Job.kind == "knowledge_extract").count() == 1


@pytest.mark.parametrize("authorized", [False, True])
def test_only_frozen_connect_authorization_creates_an_event_and_revocation_pauses_it(
    tmp_path, authorized
):
    engine, paper_id, parse_id = model_fixture(tmp_path)
    with Session(engine) as db, db.begin():
        job = queue_knowledge_extract(
            db,
            paper_id=paper_id,
            source_kind="model_parse",
            source_version_id=parse_id,
            model_snapshot=SNAPSHOT,
            allow_network=True,
            auto_connect=authorized,
        )
        identity = job.id
        # The current automatic strategy is off before this K2 finishes.
        ensure_library(db).settings_json = LibrarySettings().model_dump()
    provider = FixtureProvider()
    asyncio.run(run_knowledge_extract(engine, identity, tmp_path, provider=provider))
    after_knowledge_job(engine, identity)
    with Session(engine) as db, db.begin():
        result = db.get(Job, identity)
        assert result.status == "succeeded" and provider.calls == 1
        version_id = result.result["knowledge_version_id"]
        event = db.get(KnowledgeAnalysisEvent, version_id)
        if authorized:
            assert event is not None and event.state == "pending"
            assert event.reason == "POLICY_DISABLED"
        else:
            assert event is None
            # Opting into automatic work later cannot backfill this old K2.
            ensure_library(db).settings_json = LibrarySettings(
                auto_connect=True,
                allow_network=True,
            ).model_dump()
        assert db.query(KnowledgeConnectionRun).count() == 0
    dispatch_pending_knowledge(engine)
    with Session(engine) as db:
        assert db.query(KnowledgeConnectionRun).count() == 0
