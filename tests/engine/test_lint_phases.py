"""Resumable Lint phases and telemetry on synthetic, isolated databases only."""

import copy

import pytest
from researchgraph import lint_service
from researchgraph.knowledge_models import GraphRevision, ModelRun
from researchgraph.knowledge_store import KnowledgeStore
from researchgraph.lint_contracts import LintRequest
from researchgraph.lint_models import DependencyCursor, LintOperation, LintRun
from researchgraph.lint_service import get_run, list_issues
from researchgraph.models import Chunk, Event
from researchgraph.p5_contracts import WorkflowPrepare
from researchgraph.p5_models import P5ModelRun, P5Workflow
from researchgraph.p5_workflows import prepare, validate_workflow
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from test_knowledge import seeded as seeded
from test_p5_workflows import prepared
from test_p5_workflows import ready as ready


def start(engine):
    with Session(engine) as session, session.begin():
        return (
            KnowledgeStore(session).lint().start("project", LintRequest(), "phase-start-isolated")
        )


def advance(engine, run, key):
    with Session(engine) as session, session.begin():
        return KnowledgeStore(session).lint().advance("project", run["id"], 100, key)


def rebuilding(engine):
    run = start(engine)
    for index in range(10):
        if run["phase"] != "scanning" or run["status"] not in {"queued", "running"}:
            break
        run = advance(engine, run, f"phase-check-batch-{index}")
    assert run["status"] == "running" and run["phase"] == "rebuilding_dependencies", run
    assert run["processed"] == run["total"]
    assert run["finished_at"] is None
    return run


def bookkeeping(engine):
    with Session(engine) as session:
        return {
            "runs": [
                dict(row)
                for row in session.execute(
                    select(LintRun.__table__).order_by(LintRun.id)
                ).mappings()
            ],
            "operations": [
                dict(row)
                for row in session.execute(
                    select(LintOperation.__table__).order_by(LintOperation.key)
                ).mappings()
            ],
            "events": [
                dict(row)
                for row in session.execute(
                    select(Event.__table__).order_by(Event.sequence)
                ).mappings()
            ],
            "cursors": [
                dict(row) for row in session.execute(select(DependencyCursor.__table__)).mappings()
            ],
        }


def graph_revisions(engine):
    with Session(engine) as session:
        return [dict(row) for row in session.execute(select(GraphRevision.__table__)).mappings()]


def assert_no_scientific_write(engine, before):
    assert graph_revisions(engine) == before
    with Session(engine) as session:
        assert session.get(Chunk, "paragraph").text.startswith("Our method achieves accuracy 81%")
        assert session.get(ModelRun, "run").raw_output == '{"original":true}'
        assert list(session.scalars(select(P5ModelRun))) == []


def test_final_object_count_persists_across_restart_and_report_get_does_not_advance(seeded):
    api, engine, _ = seeded
    science_before = graph_revisions(engine)
    initial = start(engine)
    assert initial["phase"] == "scanning" and initial["processed"] == 0
    assert initial["timings"]["prepare_seconds"] >= 0
    pending = advance(engine, initial, "phase-check-batch-final")
    assert (pending["status"], pending["phase"]) == ("running", "rebuilding_dependencies")
    assert pending["processed"] == pending["total"] and pending["finished_at"] is None
    with Session(engine) as session:
        assert session.get(DependencyCursor, "project") is None
        assert not session.scalar(select(Event).where(Event.event_type == "LINT_FINISHED"))

    engine.dispose()
    before = bookkeeping(engine)
    writes = []

    def observe(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().split(None, 1)[0].upper() in {
            "INSERT",
            "UPDATE",
            "DELETE",
            "REPLACE",
            "ALTER",
            "CREATE",
            "DROP",
        }:
            writes.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        for _ in range(2):
            response = api.get(f"/api/v1/projects/project/lint/runs/{pending['id']}")
            assert response.status_code == 200, response.text
            assert response.json() == pending
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert writes == []
    assert bookkeeping(engine) == before

    completed = advance(engine, pending, "phase-dependencies-after-restart")
    assert (completed["status"], completed["phase"]) == ("completed", "finished")
    assert completed["processed"] == pending["processed"]
    assert completed["finished_at"] is not None
    for key in (
        "prepare_seconds",
        "validate_seconds",
        "check_seconds",
        "dependency_rebuild_seconds",
        "finalize_seconds",
        "elapsed_seconds",
        "last_advance_seconds",
    ):
        assert completed["timings"][key] >= 0, key
    assert completed["timings"]["advance_calls"] == 2
    assert completed["timings"]["elapsed_seconds"] >= completed["timings"]["prepare_seconds"]
    assert_no_scientific_write(engine, science_before)


def test_replayed_batch_key_cannot_rebuild_and_distinct_phase_key_rebuilds_once(
    seeded, monkeypatch
):
    _, engine, _ = seeded
    science_before = graph_revisions(engine)
    pending = rebuilding(engine)
    calls = []
    actual_rebuild = lint_service.rebuild_dependencies

    def counted(*args, **kwargs):
        calls.append(True)
        return actual_rebuild(*args, **kwargs)

    monkeypatch.setattr(lint_service, "rebuild_dependencies", counted)
    unchanged = advance(engine, pending, "phase-check-batch-0")
    assert unchanged == pending and calls == []
    completed = advance(engine, pending, "phase-dependency-step")
    assert completed["status"] == "completed" and calls == [True]
    assert advance(engine, completed, "phase-dependency-step") == completed
    assert advance(engine, completed, "phase-terminal-new-key") == completed
    assert calls == [True]
    with Session(engine) as session:
        assert session.get(DependencyCursor, "project") is not None
        assert (
            len(list(session.scalars(select(Event).where(Event.event_type == "LINT_FINISHED"))))
            == 1
        )
    assert_no_scientific_write(engine, science_before)


@pytest.mark.parametrize("stage", ["scanning", "rebuilding_dependencies"])
def test_cancellation_at_either_phase_prevents_late_advances_and_rebuild(
    seeded, monkeypatch, stage
):
    _, engine, _ = seeded
    science_before = graph_revisions(engine)
    pending = start(engine) if stage == "scanning" else rebuilding(engine)

    def forbidden(*_args, **_kwargs):
        pytest.fail("A cancelled run must never rebuild dependencies")

    monkeypatch.setattr(lint_service, "rebuild_dependencies", forbidden)
    with Session(engine) as session, session.begin():
        cancelled = (
            KnowledgeStore(session).lint().cancel("project", pending["id"], "phase-cancel-once")
        )
    assert (cancelled["status"], cancelled["phase"]) == ("cancelled", "finished")
    assert cancelled["processed"] == pending["processed"]
    assert advance(engine, cancelled, "phase-late-advance") == cancelled
    with Session(engine) as session, session.begin():
        assert (
            KnowledgeStore(session).lint().cancel("project", pending["id"], "phase-cancel-once")
            == cancelled
        )
        assert session.get(DependencyCursor, "project") is None
        assert (
            len(list(session.scalars(select(Event).where(Event.event_type == "LINT_CANCELLED"))))
            == 1
        )
        assert not session.scalar(select(Event).where(Event.event_type == "LINT_FINISHED"))
    assert_no_scientific_write(engine, science_before)


def test_source_change_before_dependency_phase_stops_instead_of_rebuilding(seeded, monkeypatch):
    _, engine, _ = seeded
    science_before = graph_revisions(engine)
    pending = rebuilding(engine)
    with Session(engine) as session, session.begin():
        session.get(Chunk, "paragraph").text += " Changed before dependency rebuilding."

    def forbidden(*_args, **_kwargs):
        pytest.fail("Source validation must run before dependency rebuilding")

    monkeypatch.setattr(lint_service, "rebuild_dependencies", forbidden)
    stale = advance(engine, pending, "phase-revalidate-input")
    assert (stale["status"], stale["phase"]) == ("input_stale", "finished")
    assert (stale["processed"], stale["input_hash"], stale["counts"]) == (
        pending["processed"],
        pending["input_hash"],
        pending["counts"],
    )
    with Session(engine) as session:
        assert session.get(DependencyCursor, "project") is None
        assert all(
            issue["lifecycle"] == "input_stale"
            for issue in list_issues(session, "project", pending["id"])["items"]
        )
    assert_no_scientific_write(engine, science_before)


def test_rebuild_failure_rolls_back_then_same_request_key_resumes_the_persisted_phase(
    seeded, monkeypatch
):
    _, engine, _ = seeded
    science_before = graph_revisions(engine)
    pending = rebuilding(engine)
    before = bookkeeping(engine)
    actual_rebuild = lint_service.rebuild_dependencies

    def interrupted(*_args, **_kwargs):
        raise RuntimeError("isolated dependency rebuild interruption")

    monkeypatch.setattr(lint_service, "rebuild_dependencies", interrupted)
    with pytest.raises(RuntimeError, match="isolated dependency"):
        advance(engine, pending, "phase-interrupted-rebuild")
    assert bookkeeping(engine) == before
    engine.dispose()
    monkeypatch.setattr(lint_service, "rebuild_dependencies", actual_rebuild)
    completed = advance(engine, pending, "phase-interrupted-rebuild")
    assert (completed["status"], completed["phase"]) == ("completed", "finished")
    assert advance(engine, completed, "phase-interrupted-rebuild") == completed
    assert_no_scientific_write(engine, science_before)


def test_phase_telemetry_does_not_change_p09_frozen_snapshot_or_wire_hash(ready):
    _, engine, _ = ready
    pending = rebuilding(engine)
    completed = advance(engine, pending, "phase-finish-for-p09")
    wid = prepared(engine, kind="lint_semantic", lint_run_id=completed["id"])
    with Session(engine) as session:
        row = session.get(P5Workflow, wid)
        frozen = copy.deepcopy(row.snapshot)
        hashes = (row.input_hash, row.snapshot["wire_hash"], row.snapshot["prompt_hash"])
        request = WorkflowPrepare.model_validate(row.request)
        assert "phase" not in row.snapshot["lint"]
        assert "timings" not in row.snapshot["lint"]
        assert all("repair_plan" not in issue for issue in row.snapshot["lint"]["issues"])
    with Session(engine) as session, session.begin():
        report = session.get(LintRun, completed["id"])
        report.timings = {**report.timings, "elapsed_seconds": 123.0, "advance_calls": 99}
    engine.dispose()
    with Session(engine) as session, session.begin():
        row = session.get(P5Workflow, wid)
        validate_workflow(session, row)
        cached = prepare(session, "project", request, "phase-telemetry-cached-prepare")
        assert cached.id == wid
        assert row.snapshot == frozen
        assert (row.input_hash, row.snapshot["wire_hash"], row.snapshot["prompt_hash"]) == hashes
        assert get_run(session, "project", completed["id"])["timings"]["advance_calls"] == 99
        assert list(session.scalars(select(P5ModelRun))) == []
