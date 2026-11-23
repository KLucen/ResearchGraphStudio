"""Batch checkpoints upgrade additively and preserve content lifecycle boundaries."""

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from researchgraph import storage
from researchgraph.document_batch_models import (
    LlmDocumentBatch,
    LlmDocumentBatchFailure,
    LlmDocumentBatchRun,
)
from researchgraph.import_plan_api import normalize_post_import_plan
from researchgraph.import_plan_models import ImportSession
from researchgraph.model_document_models import (
    LlmDocumentOutputLocalRecovery,
    LlmDocumentParse,
    LlmDocumentSegment,
)
from researchgraph.model_document_overview_models import (
    ModelOverviewGraphLayout,
    ModelOverviewGraphViewport,
)
from researchgraph.models import Job, Project, now
from researchgraph.schemas import ImportPlan, JobView, PdfPostImportPlan
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_engine import client
from test_paper_management_api import add_paper, purge_archived_paper_data


def _old_rows(path: Path) -> dict[str, list[tuple]]:
    with sqlite3.connect(path) as db:
        names = [
            row[0]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if row[0] != "alembic_version"
        ]
        return {
            name: db.execute('SELECT * FROM "' + name.replace('"', '""') + '"').fetchall()
            for name in names
        }


def _session(db: Session) -> tuple[str, str]:
    project_id, session_id, job_id = (str(uuid4()) for _ in range(3))
    timestamp = now()
    db.add(Project(id=project_id, name="Anonymous", description="", created_at=timestamp))
    db.flush()
    db.add(
        Job(
            id=job_id,
            kind="llm_document_parse",
            project_id=project_id,
            status="failed",
            stage="failed",
            attempt=1,
            payload={"import_session_id": session_id},
            result={"old_diagnostic": 17},
            error="Original failure",
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    db.add(
        ImportSession(
            id=session_id,
            project_id=project_id,
            source_kind="pdf",
            selection_id=str(uuid4()),
            source_snapshot={"page_count": 2},
            plan={"allow_network": False},
            status="failed",
            error="Keep old failure",
            created_at=timestamp,
            updated_at=timestamp,
        )
    )
    db.flush()
    return session_id, job_id


def _run(session_id: str, job_id: str) -> LlmDocumentBatchRun:
    return LlmDocumentBatchRun(
        id=str(uuid4()),
        import_session_id=session_id,
        job_id=job_id,
        source_version={"source_generation": 1, "file_bytes": 21},
        settings={"contract_version": "document-batch-1", "pages_per_batch": 5},
        page_count=8,
        status="pending",
        created_at=now(),
        updated_at=now(),
    )


def _batch(run_id: str, *, kind: str = "extract", ordinal: int = 0) -> LlmDocumentBatch:
    return LlmDocumentBatch(
        id=str(uuid4()),
        run_id=run_id,
        ordinal=ordinal,
        kind=kind,
        page_start=1,
        page_end=5,
        send_start=1,
        send_end=6,
        status="pending",
        created_at=now(),
        updated_at=now(),
    )


def test_lite0012_upgrade_preserves_old_content_and_creates_exact_backup(tmp_path):
    engine = storage.make_engine(tmp_path)
    config = Config()
    config.set_main_option("script_location", str(Path(storage.__file__).parent / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "lite0012")
        # Models may already be registered on Base during test collection.
        # Remove only the empty future tables to model an actual old installation.
        for model in (
            LlmDocumentBatchFailure,
            LlmDocumentOutputLocalRecovery,
            ModelOverviewGraphLayout,
            ModelOverviewGraphViewport,
        ):
            model.__table__.drop(connection, checkfirst=True)
        LlmDocumentBatch.__table__.drop(connection, checkfirst=True)
        LlmDocumentBatchRun.__table__.drop(connection, checkfirst=True)
    with Session(engine) as db, db.begin():
        session_id, _job_id = _session(db)
        parse_id = str(uuid4())
        db.add(
            LlmDocumentParse(
                id=parse_id,
                import_session_id=session_id,
                parse_version="old-document-1",
                modality="pdf",
                status="succeeded",
                raw_response={"original": "保留正文 58.0 与公式 x²"},
                warnings=["Keep old warning"],
                created_at=now(),
                updated_at=now(),
            )
        )
        db.flush()
        db.add(
            LlmDocumentSegment(
                id=str(uuid4()),
                parse_id=parse_id,
                chapter_ref="intro",
                chapter_title="Introduction",
                kind="paragraph",
                text="Unmodified transcription\n58.0",
                created_at=now(),
            )
        )
    database = tmp_path / storage.DATABASE_NAME
    original = _old_rows(database)
    storage.migrate(engine, tmp_path)
    after = _old_rows(database)
    assert set(after) - set(original) == {
        "llm_document_batch_runs",
        "llm_document_batches",
        "llm_document_batch_failures",
        "llm_document_output_local_recoveries",
        "model_overview_graph_layouts",
        "model_overview_graph_viewports",
    }
    for name, rows in original.items():
        assert after[name] == rows, name
    backups = list((tmp_path / "backups").glob("before-migration-*.sqlite3"))
    assert len(backups) == 1 and _old_rows(backups[0]) == original
    with sqlite3.connect(backups[0]) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("lite0012",)
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("lite0020",)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert storage.diagnostics(engine)["integrity"] == "ok"
    engine.dispose()


def test_batch_checkpoints_unique_per_session_kind_and_ordinal(tmp_path):
    with client(tmp_path) as api:
        engine = api.app.state.engine
        with Session(engine) as db, db.begin():
            session_id, job_id = _session(db)
            run = _run(session_id, job_id)
            db.add(run)
            db.flush()
            run_id = run.id
            db.add_all([_batch(run_id), _batch(run_id, kind="boundary")])
        with pytest.raises(IntegrityError), Session(engine) as db, db.begin():
            db.add(_run(session_id, job_id))
            db.flush()
        with pytest.raises(IntegrityError), Session(engine) as db, db.begin():
            db.add(_batch(run_id))
            db.flush()
        with Session(engine) as db:
            batch = db.scalar(select(LlmDocumentBatch).where(LlmDocumentBatch.kind == "extract"))
            assert batch is not None
            assert (batch.attempts, batch.repair_attempts, batch.request_count) == (0, 0, 0)
            assert batch.result_json is None
            assert batch.validation_errors == []
            assert batch.usage == batch.request_metadata == {}
        assert "raw_response" not in LlmDocumentBatch.__table__.columns


@pytest.mark.parametrize(
    "column,value", [("result_json", {"text": "reject"}), ("repair_attempts", 2)]
)
def test_invalid_checkpoint_content_or_unbounded_repair_is_rejected(tmp_path, column, value):
    with client(tmp_path) as api:
        engine = api.app.state.engine
        with Session(engine) as db, db.begin():
            session_id, job_id = _session(db)
            run = _run(session_id, job_id)
            db.add(run)
            db.flush()
            run_id = run.id
        with pytest.raises(IntegrityError), Session(engine) as db, db.begin():
            batch = _batch(run_id)
            setattr(batch, column, value)
            db.add(batch)
            db.flush()


def test_import_session_delete_cascades_batch_run_and_checkpoints(tmp_path):
    with client(tmp_path) as api:
        engine = api.app.state.engine
        with Session(engine) as db, db.begin():
            session_id, job_id = _session(db)
            run = _run(session_id, job_id)
            db.add(run)
            db.flush()
            db.add(_batch(run.id))
        with Session(engine) as db, db.begin():
            db.execute(delete(ImportSession).where(ImportSession.id == session_id))
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(LlmDocumentBatchRun)) == 0
            assert db.scalar(select(func.count()).select_from(LlmDocumentBatch)) == 0
            assert db.get(Job, job_id) is not None


def test_legacy_cleanup_keeps_batches_but_paper_delete_removes_them(tmp_path):
    with client(tmp_path) as api:
        values = add_paper(api, tmp_path)
        engine = api.app.state.engine
        with Session(engine) as db, db.begin():
            job_id = db.scalar(select(Job.id).where(Job.kind == "llm_document_parse"))
            assert job_id is not None
            run = _run(values["session_id"], job_id)
            db.add(run)
            db.flush()
            batch = _batch(run.id)
            batch.status = "validated"
            batch.result_json = {"segments": [{"text": "Anonymous preserved result"}]}
            batch.request_count, batch.repair_attempts = 2, 1
            db.add(batch)
            db.flush()
            run_id, batch_id = run.id, batch.id
            db.add(
                LlmDocumentBatchFailure(
                    batch_id=batch_id,
                    raw_response='{"private": "Anonymous original failure"}',
                    source_request_count=1,
                    state="succeeded",
                    authorized_attempt=2,
                    created_at=now(),
                    updated_at=now(),
                )
            )
        cleared = api.delete(f"/api/v1/papers/{values['paper_id']}/legacy-content")
        purge_archived_paper_data(api, cleared)
        with Session(engine) as db:
            assert db.get(LlmDocumentBatchRun, run_id) is not None
            stored = db.get(LlmDocumentBatch, batch_id)
            assert stored is not None
            assert stored.result_json == {"segments": [{"text": "Anonymous preserved result"}]}
            assert db.get(LlmDocumentBatchFailure, batch_id) is not None
        deleted = api.delete(f"/api/v1/papers/{values['paper_id']}")
        deleted = purge_archived_paper_data(api, deleted)
        assert deleted.json()["removed"]["llm_document_batches"] == 1
        assert deleted.json()["removed"]["llm_document_batch_runs"] == 1
        with Session(engine) as db:
            assert db.get(LlmDocumentBatchRun, run_id) is None
            assert db.get(LlmDocumentBatch, batch_id) is None
            assert db.get(LlmDocumentBatchFailure, batch_id) is None
        assert values["imported_path"].is_file()


def test_batch_plan_defaults_preserve_direct_api_and_enable_desktop_batches():
    assert ImportPlan().document_batching is False
    desktop = PdfPostImportPlan(
        pages_per_batch=6, allow_format_repair=True, allow_boundary_review=False
    )
    plan = normalize_post_import_plan(desktop)
    assert plan is not None and plan.document_batching is True
    assert plan.pages_per_batch == 6
    assert plan.allow_format_repair is True
    assert plan.allow_boundary_review is False
    assert normalize_post_import_plan(PdfPostImportPlan(parse=False)) is None


@pytest.mark.parametrize("pages", [1, 9])
def test_batch_plan_page_limits_are_enforced(pages):
    with pytest.raises(ValidationError):
        PdfPostImportPlan(pages_per_batch=pages)
    with pytest.raises(ValidationError):
        ImportPlan(pages_per_batch=pages)


@pytest.mark.parametrize("stage", ["document_batching", "document_repairing", "document_boundary"])
def test_public_jobs_accept_batch_pipeline_stages(stage):
    job = JobView(
        id=str(uuid4()),
        kind="llm_document_parse",
        project_id=None,
        status="running",
        stage=stage,
        attempt=1,
        error=None,
        result=None,
        created_at=now(),
        updated_at=now(),
    )
    assert job.stage == stage
