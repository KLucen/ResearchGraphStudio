"""Query display reads must not queue behind a writer or observe its pending data."""

import asyncio
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
import test_query_api
from researchgraph.models import Job, Project, now
from researchgraph.storage import read_session
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_engine import client, post
from test_query_api import PREFIX, prepare

api_setup = test_query_api.api_setup


def test_history_and_sibling_reads_remain_available_while_a_writer_is_open(api_setup):
    api, engine = api_setup
    prepared = prepare(api)
    database = engine.url.database
    routes = ["/runs", "/documents", "/saved", "/derived-graph"]
    with sqlite3.connect(database) as writer:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("UPDATE query_runs SET status='failed'")
        try:
            with ThreadPoolExecutor(max_workers=4) as executor:
                responses = list(executor.map(lambda path: api.get(PREFIX + path), routes))
            for response in responses:
                assert response.status_code == 200, response.text
            history = responses[0].json()["items"]
            assert len(history) == 1 and history[0]["query_id"] == prepared["query_id"]
            assert history[0]["status"] == "prepared", "Uncommitted status must stay private"
        finally:
            writer.rollback()


def test_real_writer_contention_returns_a_safe_retryable_json_error(api_setup):
    api, engine = api_setup
    prepare(api)

    def short_wait(connection, _record):
        connection.execute("PRAGMA busy_timeout=30")

    event.listen(engine, "connect", short_wait)
    engine.dispose()
    with sqlite3.connect(engine.url.database) as writer:
        writer.execute("BEGIN IMMEDIATE")
        try:
            response = api.post(
                PREFIX + "/prepare",
                json={"project_id": "project", "question": "accuracy"},
                headers={"Idempotency-Key": "contended-query-request"},
            )
            assert response.status_code == 503, response.text
            error = response.json()["error"]
            assert error["code"] == "DATABASE_BUSY" and error["retryable"] is True
            assert error["request_id"]
            assert "SELECT" not in response.text and "query_runs" not in response.text
        finally:
            writer.rollback()
    # A failed BEGIN never created an operation or a paid task; explicit retry works.
    retried = api.post(
        PREFIX + "/prepare",
        json={"project_id": "project", "question": "accuracy"},
        headers={"Idempotency-Key": "contended-query-request"},
    )
    assert retried.status_code == 200, retried.text


def test_read_snapshot_does_not_block_writer_commit_or_see_uncommitted_changes(api_setup):
    _, engine = api_setup
    with read_session(engine) as reader:
        original = reader.get(Project, "project")
        assert original.description == ""
        with Session(engine) as writer, writer.begin():
            writer.get(Project, "project").description = "Committed synthetic update"
        reader.expire_all()
        assert reader.get(Project, "project").description == ""
    with read_session(engine) as reader:
        assert reader.get(Project, "project").description == "Committed synthetic update"


def test_read_session_cannot_write_and_pool_reuse_restores_write_access(api_setup):
    _, engine = api_setup
    with read_session(engine) as reader:
        with pytest.raises(OperationalError, match="readonly"):
            reader.connection().exec_driver_sql("UPDATE projects SET description='forbidden'")
    with Session(engine) as writer, writer.begin():
        writer.get(Project, "project").description = "Allowed writer"
    with read_session(engine) as reader:
        assert reader.get(Project, "project").description == "Allowed writer"


def test_database_errors_return_json_without_sql_or_driver_details(api_setup):
    api, _ = api_setup

    @api.app.get("/api/v1/test-database-failure")
    def failed():
        raise OperationalError(
            "SELECT synthetic_private_source", {}, sqlite3.OperationalError("synthetic detail")
        )

    response = api.get("/api/v1/test-database-failure")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "DATABASE_ERROR"
    assert "synthetic" not in response.text


def test_worker_claim_wait_never_blocks_history_or_claims_a_job_twice(tmp_path, monkeypatch):
    import researchgraph.app as app_module

    gate = threading.Event()
    claiming = threading.Event()
    original = app_module.claim_queued_job

    def gated(engine):
        assert gate.wait(5)
        return original(engine)

    monkeypatch.setattr(app_module, "claim_queued_job", gated)
    with client(tmp_path / "worker-data", worker=True) as api:
        engine = test_query_api.seed(api)
        prepared = prepare(api)
        job_response = post(api, "/jobs", {"kind": "diagnostics"})
        assert job_response.status_code == 202, job_response.text
        job = job_response.json()

        def before_sql(_connection, _cursor, statement, _params, _context, _many):
            if statement == "BEGIN IMMEDIATE":
                claiming.set()

        event.listen(engine, "before_cursor_execute", before_sql)
        with sqlite3.connect(engine.url.database) as writer:
            writer.execute("BEGIN IMMEDIATE")
            try:
                gate.set()
                assert claiming.wait(3), "Worker never reached the contended claim"
                with ThreadPoolExecutor(max_workers=1) as executor:
                    response = executor.submit(api.get, PREFIX + "/runs").result(timeout=2)
                assert response.status_code == 200, response.text
                assert response.json()["items"][0]["query_id"] == prepared["query_id"]
            finally:
                writer.rollback()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            current = api.get("/api/v1/jobs/" + job["id"]).json()
            if current["status"] == "succeeded":
                break
            time.sleep(0.05)
        assert current["status"] == "succeeded" and current["attempt"] == 1


def test_model_wait_cancellation_poll_is_read_only_during_an_open_writer(api_setup):
    from researchgraph.query_answers import _call

    _, engine = api_setup
    with Session(engine) as session, session.begin():
        session.add(
            Job(
                id="poll-job",
                kind="query_answer",
                project_id="project",
                status="running",
                attempt=1,
                payload={},
                created_at=now(),
                updated_at=now(),
            )
        )

    class OfflineDelay:
        total_timeout = 2
        calls = 0

        async def complete(self, *_args):
            self.calls += 1
            await asyncio.sleep(0.25)
            return "synthetic response"

    provider = OfflineDelay()
    with sqlite3.connect(engine.url.database) as writer:
        writer.execute("BEGIN IMMEDIATE")
        try:
            answer = asyncio.run(
                _call(
                    engine,
                    "poll-job",
                    provider,
                    SimpleNamespace(prompt="", wire={}, schema={}),
                    None,
                )
            )
        finally:
            writer.rollback()
    assert answer == "synthetic response" and provider.calls == 1
