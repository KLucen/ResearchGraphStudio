"""A failed response can be repaired once by explicit action without PDF retransmission."""

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from researchgraph import document_batch_transport, storage
from researchgraph.document_batch_contracts import BatchValidationError, validate_batch
from researchgraph.document_batch_models import LlmDocumentBatch, LlmDocumentBatchFailure
from researchgraph.document_batches import _repair_preserves_material
from researchgraph.document_format_repair import (
    authorize_format_repair,
    clear_format_repair_intent,
    execute_authorized_format_repair,
    format_repair_view,
    ordinary_document_attempts,
    register_document_format_repair_api,
)
from researchgraph.lite_usage import aggregate_usage
from researchgraph.model_document_api import execute_document_parse
from researchgraph.model_document_models import LlmDocumentOutputLocalRecovery
from researchgraph.model_document_overview_models import (
    ModelOverviewGraphLayout,
    ModelOverviewGraphViewport,
)
from researchgraph.models import Job, Project, now
from researchgraph.providers import ProviderError
from sqlalchemy import Table, delete, select
from sqlalchemy.orm import Session
from test_document_batches import FakeProvider, setup_job
from test_engine import client, post


def failed_response(tmp_path, *, provider=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    engine, session_id, job_id, path = setup_job(tmp_path, repair=False, pages=5)
    provider = provider or FakeProvider(invalid=True)
    with pytest.raises((BatchValidationError, ProviderError)):
        asyncio.run(execute_document_parse(engine, job_id, tmp_path, provider=provider))
    return engine, session_id, job_id, path, provider


def authorize_and_claim(engine, job_id):
    with Session(engine) as db, db.begin():
        job = db.get(Job, job_id)
        batch_id = authorize_format_repair(db, job, allow_network=True)
        job.status = "running"
        job.attempt += 1
    return batch_id


def test_retained_raw_is_private_and_one_explicit_repair_never_reads_or_retransmits_pdf(
    tmp_path, monkeypatch
):
    engine, _, job_id, _, provider = failed_response(tmp_path)
    with Session(engine) as db:
        job = db.get(Job, job_id)
        view = format_repair_view(db, job)
        assert view.available and view.page_start == 1 and view.page_end == 3
        failure = db.get(LlmDocumentBatchFailure, view.batch_id)
        original = failure.raw_response
        assert "extra_private_source_text" in original
        assert "extra_private_source_text" not in json.dumps(job.result)
        assert original not in json.dumps(view.model_dump())
    batch_id = authorize_and_claim(engine, job_id)

    def forbidden(*args, **kwargs):
        raise AssertionError("Explicit format repair cannot read PDF bytes")

    monkeypatch.setattr(document_batch_transport, "read_pdf_bytes", forbidden)
    assert asyncio.run(execute_authorized_format_repair(engine, job_id, provider))
    assert len(provider.calls) == 1 and len(provider.repairs) == 1
    assert provider.repairs[0]["raw"] == original
    with Session(engine) as db:
        row, failure = db.get(LlmDocumentBatch, batch_id), db.get(LlmDocumentBatchFailure, batch_id)
        assert row.status == "validated" and row.repair_attempts == 1 and row.request_count == 2
        assert failure.raw_response == original and failure.state == "succeeded"
        assert failure.repair_response is not None
        job = db.get(Job, job_id)
        assert job.status == "failed" and job.stage == "paused"
        assert job.result["document_format_repair_only"] is False
        assert job.result["document_format_repair_completed"] is True
        assert not format_repair_view(db, job).available
        assert len(list(db.scalars(select(LlmDocumentBatch)))) == 2
        usage = aggregate_usage(db, None)
        assert usage.calls == 2 and usage.retry_count == 1
        assert usage.cost_estimate is None
    with Session(engine) as db, db.begin():
        with pytest.raises(HTTPException) as error:
            authorize_format_repair(db, db.get(Job, job_id), allow_network=True)
        assert error.value.status_code == 409


def test_explicit_repair_rejects_semantic_rewrite_and_never_grants_second_slot(tmp_path):
    provider = FakeProvider(invalid=True, bad_repair=True)
    engine, _, job_id, _, provider = failed_response(tmp_path, provider=provider)
    batch_id = authorize_and_claim(engine, job_id)
    with pytest.raises(BatchValidationError):
        asyncio.run(execute_authorized_format_repair(engine, job_id, provider))
    assert len(provider.calls) == len(provider.repairs) == 1
    with Session(engine) as db:
        row, failure = db.get(LlmDocumentBatch, batch_id), db.get(LlmDocumentBatchFailure, batch_id)
        assert row.status == "schema_failed" and row.result_json is None
        assert row.repair_attempts == 1 and row.request_count == 2
        assert failure.state == "failed" and "invented replacement" in failure.repair_response
        assert not format_repair_view(db, db.get(Job, job_id)).available


def test_format_repair_cannot_drop_source_uncertainty_warnings(tmp_path):
    engine, _, _, _, _ = failed_response(tmp_path)
    with Session(engine) as db:
        original = json.loads(db.scalar(select(LlmDocumentBatchFailure)).raw_response)
    original.pop("extra_private_source_text")
    original["warnings"] = ["Cross-page transcription remains uncertain"]
    original["segments"][0]["warnings"] = ["Equation could not be confirmed"]
    repaired = json.loads(json.dumps(original))
    repaired["warnings"] = []
    fixed = validate_batch(repaired, 1, 3)
    assert not _repair_preserves_material(json.dumps(original), fixed)
    repaired["warnings"] = original["warnings"]
    repaired["segments"][0]["warnings"] = []
    assert not _repair_preserves_material(json.dumps(original), validate_batch(repaired, 1, 3))


def test_explicit_repair_requires_network_consent_and_unchanged_source(tmp_path):
    engine, _, job_id, path, provider = failed_response(tmp_path)
    with Session(engine) as db, db.begin():
        with pytest.raises(HTTPException) as error:
            authorize_format_repair(db, db.get(Job, job_id), allow_network=False)
        assert error.value.status_code == 422
    authorize_and_claim(engine, job_id)
    path.write_bytes(path.read_bytes() + b"\nchanged")
    with pytest.raises(ValueError, match="版本已变化"):
        asyncio.run(execute_authorized_format_repair(engine, job_id, provider))
    assert len(provider.repairs) == 0


def test_raw_without_decodable_json_or_without_saved_response_has_no_model_repair(tmp_path):
    engine, _, job_id, _, _ = failed_response(tmp_path)
    with Session(engine) as db, db.begin():
        failure = db.scalar(select(LlmDocumentBatchFailure))
        failure.raw_response = '{"segments": [truncated'
    with Session(engine) as db:
        view = format_repair_view(db, db.get(Job, job_id))
        assert not view.available and view.reason_code == "RAW_JSON_NOT_DECODABLE"
    with Session(engine) as db, db.begin():
        db.execute(delete(LlmDocumentBatchFailure))
    with Session(engine) as db:
        assert not format_repair_view(db, db.get(Job, job_id)).available


def test_network_failure_has_no_response_repair_and_checkpoint_tampering_stops_dispatch(tmp_path):
    engine, _, job_id, _, provider = failed_response(tmp_path, provider=FakeProvider(fail=1))
    with Session(engine) as db:
        assert db.scalar(select(LlmDocumentBatchFailure)) is None
        assert not format_repair_view(db, db.get(Job, job_id)).available
    other = tmp_path / "other"
    engine, _, job_id, _, provider = failed_response(other)
    batch_id = authorize_and_claim(engine, job_id)
    with Session(engine) as db, db.begin():
        row = db.get(LlmDocumentBatch, batch_id)
        row.request_count += 1
    with pytest.raises(ProviderError, match="授权已变化"):
        asyncio.run(execute_authorized_format_repair(engine, job_id, provider))
    assert not provider.repairs


def test_interrupted_sent_repair_cannot_be_replayed_on_restart(tmp_path):
    engine, _, job_id, _, provider = failed_response(tmp_path)
    batch_id = authorize_and_claim(engine, job_id)
    with Session(engine) as db, db.begin():
        row, failure = db.get(LlmDocumentBatch, batch_id), db.get(LlmDocumentBatchFailure, batch_id)
        row.status, row.repair_attempts, row.request_count = "uncertain", 1, 2
        failure.state = "sent"
        db.get(Job, job_id).attempt += 1
    with pytest.raises(ProviderError, match="请求已使用"):
        asyncio.run(execute_authorized_format_repair(engine, job_id, provider))
    assert not provider.repairs


def test_cancelled_unclaimed_repair_does_not_discount_a_later_pdf_worker_attempt(tmp_path):
    engine, _, job_id, _, _ = failed_response(tmp_path)
    with Session(engine) as db, db.begin():
        job = db.get(Job, job_id)
        authorize_format_repair(db, job, allow_network=True)
        # The repair was cancelled while queued, before any worker claimed it.
        job.status = "cancelled"
        clear_format_repair_intent(job)
        job.status = "running"
        job.attempt += 1
        assert ordinary_document_attempts(job) == 2
        assert not job.result.get("document_format_repair_worker_attempts")


def test_repair_api_read_is_private_and_authorization_is_idempotent(tmp_path):
    engine, session_id, job_id, _, _ = failed_response(tmp_path)
    app = FastAPI()
    register_document_format_repair_api(app, lambda: engine)
    with TestClient(app) as api:
        route = f"/import-sessions/{session_id}/document-parse/format-repair"
        view = api.get("/api/v1" + route)
        assert view.status_code == 200 and view.json()["available"]
        assert "raw_response" not in view.text and "extra_private_source_text" not in view.text
        assert post(api, route, {"allow_network": False}, "no-repair-consent").status_code == 422
        first = post(api, route, {"allow_network": True}, "explicit-format-repair")
        assert first.status_code == 202 and first.json()["id"] == job_id
        second = post(api, route, {"allow_network": True}, "explicit-format-repair")
        assert second.json() == first.json()
        assert post(api, route, {"allow_network": True}, "second-repair-intent").status_code == 409


def test_lite0013_upgrade_preserves_all_existing_rows_and_creates_backup(tmp_path):
    engine = storage.make_engine(tmp_path)
    config = Config()
    config.set_main_option("script_location", str(Path(storage.__file__).parent / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "lite0013")
        for model in (
            LlmDocumentBatchFailure,
            LlmDocumentOutputLocalRecovery,
            ModelOverviewGraphLayout,
            ModelOverviewGraphViewport,
        ):
            model.__table__.drop(connection, checkfirst=True)
    with Session(engine) as db, db.begin():
        db.add(
            Project(id="preserved-project", name="Keep old data", description="", created_at=now())
        )
    database = tmp_path / storage.DATABASE_NAME

    def snapshot(path):
        with sqlite3.connect(path) as db:
            names = [
                row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            ]
            return {
                name: db.execute('SELECT * FROM "' + name.replace('"', '""') + '"').fetchall()
                for name in names
                if name != "alembic_version"
            }

    before = snapshot(database)
    storage.migrate(engine, tmp_path)
    after = snapshot(database)
    assert set(after) - set(before) == {
        "llm_document_batch_failures",
        "llm_document_output_local_recoveries",
        "model_overview_graph_layouts",
        "model_overview_graph_viewports",
    }
    for name, rows in before.items():
        assert after[name] == rows
    backups = list((tmp_path / "backups").glob("before-migration-*.sqlite3"))
    assert len(backups) == 1 and snapshot(backups[0]) == before
    assert storage.diagnostics(engine)["integrity"] == "ok"
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("lite0020",)


def test_lite0014_upgrade_failure_rolls_back_new_tables_and_schema_version(tmp_path, monkeypatch):
    engine = storage.make_engine(tmp_path)
    config = Config()
    config.set_main_option("script_location", str(Path(storage.__file__).parent / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "lite0013")
        for model in (
            LlmDocumentBatchFailure,
            LlmDocumentOutputLocalRecovery,
            ModelOverviewGraphLayout,
            ModelOverviewGraphViewport,
        ):
            model.__table__.drop(connection, checkfirst=True)
    original = Table.create

    def fail_second_table(table, *args, **kwargs):
        if table.name == "model_overview_graph_layouts":
            raise RuntimeError("synthetic migration interruption")
        return original(table, *args, **kwargs)

    monkeypatch.setattr(Table, "create", fail_second_table)
    with pytest.raises(RuntimeError, match="synthetic migration interruption"):
        storage.migrate(engine, tmp_path)
    with sqlite3.connect(tmp_path / storage.DATABASE_NAME) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("lite0013",)
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "llm_document_batch_failures" not in names
        assert "model_overview_graph_layouts" not in names
        assert "model_overview_graph_viewports" not in names
    assert len(list((tmp_path / "backups").glob("before-migration-*.sqlite3"))) == 1


def test_integrated_worker_repairs_once_then_explicit_continue_uses_only_remaining_pdf_batch(
    tmp_path,
):
    # Initialize a real migrated application database before seeding the
    # anonymous failure, so the restart exercises production recovery code.
    with client(tmp_path):
        pass
    engine, session_id, job_id, _, provider = failed_response(tmp_path)
    engine.dispose()
    with client(tmp_path) as api:
        route = f"/import-sessions/{session_id}/document-parse/format-repair"
        queued = post(api, route, {"allow_network": True}, "repair-integrated-once")
        assert queued.status_code == 202, queued.text
        from researchgraph.app import claim_queued_job

        assert claim_queued_job(api.app.state.engine) == (job_id, "llm_document_parse")
        asyncio.run(
            execute_document_parse(api.app.state.engine, job_id, tmp_path, provider=provider)
        )
        repaired = api.get(f"/api/v1/jobs/{job_id}")
        assert repaired.status_code == 200 and repaired.json()["stage"] == "paused"
        assert len(provider.calls) == 1 and len(provider.repairs) == 1
        assert post(api, f"/jobs/{job_id}/retry", key="continue-after-repair").status_code == 200
        assert claim_queued_job(api.app.state.engine) == (job_id, "llm_document_parse")
        provider.invalid = False
        asyncio.run(
            execute_document_parse(api.app.state.engine, job_id, tmp_path, provider=provider)
        )
        completed = api.get(f"/api/v1/jobs/{job_id}").json()
        assert completed["status"] == "succeeded", completed
        assert len(provider.calls) == 2 and len(provider.repairs) == 1
        assert provider.calls[1]["page_start"] == 4
        with Session(api.app.state.engine) as db:
            usage = aggregate_usage(db, None)
            assert usage.calls == 3 and usage.retry_count == 1
