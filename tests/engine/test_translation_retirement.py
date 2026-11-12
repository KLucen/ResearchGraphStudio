"""Removing translation never resumes old work or rewrites reading data."""

import subprocess
import sys
from uuid import uuid4

import httpx
import pytest
from researchgraph.__main__ import main
from researchgraph.app import claim_queued_job, remember
from researchgraph.lite_models import LiteCacheEntry, LiteTokenUsage
from researchgraph.models import AttachmentRevision, Chunk, Job, Paper, Project, Section, now
from researchgraph.retired_tasks import TRANSLATION_REMOVED, TRANSLATION_REMOVED_MESSAGE
from researchgraph.translation_models import PDFTranslation, PDFTranslationSettings
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from test_engine import client, post


def _snapshot(engine, *, exclude=()):
    with engine.connect().execution_options(sqlite_readonly=True) as connection:
        return {
            table: sorted(
                [tuple(row) for row in connection.execute(text(f'SELECT * FROM "{table}"'))],
                key=repr,
            )
            for table in inspect(engine).get_table_names()
            if table not in exclude
        }


def _seed(api, statuses=("queued", "running", "succeeded", "failed", "cancelled", "interrupted")):
    project = str(uuid4())
    paper_id, revision_id = str(uuid4()), str(uuid4())
    timestamp = now()
    jobs = []
    with Session(api.app.state.engine) as session, session.begin():
        session.add(
            Project(id=project, name="Keep reading data", description="", created_at=timestamp)
        )
        session.flush()
        session.add(
            Paper(id=paper_id, project_id=project, title="Keep paper", created_at=timestamp)
        )
        session.flush()
        session.add(
            AttachmentRevision(
                id=revision_id,
                paper_id=paper_id,
                sha256="a" * 64,
                parser_version="synthetic",
                page_count=2,
                warnings=[],
                created_at=timestamp,
            )
        )
        session.add(
            PDFTranslationSettings(
                id="global",
                enabled=True,
                service_url="http://127.0.0.1:8999",
                launch_mode="bundled",
                python_path=None,
                server_path=None,
            )
        )
        session.flush()
        section_id = str(uuid4())
        session.add(
            Section(
                id=section_id,
                document_version_id=revision_id,
                title="Keep section",
                ordinal=0,
                role="body",
                parser="synthetic",
                start_page=0,
                end_page=1,
                excluded=False,
            )
        )
        session.add(
            Chunk(
                id=str(uuid4()),
                revision_id=revision_id,
                page_index=0,
                page_label="1",
                block_index=0,
                text="Synthetic indexed source",
                bbox=[1, 1, 2, 2],
            )
        )
        session.flush()
        session.add(
            LiteCacheEntry(
                cache_key="c" * 64,
                project_id=project,
                paper_id=paper_id,
                document_version_id=revision_id,
                section_id=section_id,
                task_kind="section_guide",
                input_fingerprint="d" * 64,
                prompt_version="historic-prompt",
                schema_version="historic-schema",
                provider="synthetic",
                model="synthetic-model",
                config_fingerprint="e" * 64,
                source_hash="a" * 64,
                state="fresh",
                response={"keep": "reading response"},
                hit_count=3,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        for status in statuses:
            job_id = str(uuid4())
            job = Job(
                id=job_id,
                project_id=project,
                kind="pdf_translation",
                status=status,
                stage="starting_service"
                if status == "interrupted"
                else ("stopping_service" if status == "cancelled" else "generating"),
                attempt=2,
                error=f"historic {status}",
                payload={"translation_id": job_id},
                result={"keep": status},
                created_at=timestamp,
                updated_at=timestamp,
            )
            session.add(job)
            session.flush()
            jobs.append((job_id, status))
            session.add(
                PDFTranslation(
                    id=job_id,
                    project_id=project,
                    paper_id=paper_id,
                    document_version_id=revision_id,
                    source_hash="a" * 64,
                    profile_id=str(uuid4()),
                    model_id="synthetic-model",
                    model_snapshot={"model": "synthetic-model", "credential_ref": None},
                    output_mode="dual",
                    runtime_snapshot={"launch_mode": "bundled"},
                    cache_key="b" * 64,
                    service_url="http://127.0.0.1:8999",
                    engine_version="synthetic",
                    status={
                        "queued": "PENDING",
                        "running": "RUNNING",
                        "succeeded": "COMPLETED",
                        "failed": "FAILED",
                        "cancelled": "CANCELLED",
                        "interrupted": "FAILED",
                    }[status],
                    page_start=1,
                    page_end=2,
                    page_count=2,
                    progress=50,
                    stage="historic-stage",
                    job_id=job_id,
                    external_task_id="old-external-id",
                    external_state="historic",
                    error_code="HISTORIC",
                    error=f"historic {status}",
                    warnings=["keep warning"],
                    artifacts=[{"path": "translations/history.pdf"}],
                    max_calls=100,
                    max_input_tokens=200000,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
            session.add(
                LiteTokenUsage(
                    id=str(uuid4()),
                    project_id=project,
                    paper_id=paper_id,
                    document_version_id=revision_id,
                    task_run_id=job_id,
                    task_kind="pdf_translation",
                    provider="synthetic",
                    model="synthetic-model",
                    input_tokens=12 if status == "succeeded" else None,
                    output_tokens=8 if status == "succeeded" else None,
                    total_tokens=20 if status == "succeeded" else None,
                    cost_estimate=0.01 if status == "succeeded" else None,
                    retry_count=1,
                    cache_hit=False,
                    usage_source="provider",
                    status=status,
                    reason_code="HISTORIC",
                    extra={"keep": status},
                    created_at=timestamp,
                )
            )
        # A previous successful retry response must not bypass the removal guard.
        first_id = jobs[0][0]
        remember(
            session,
            "job-action:historic-retry",
            {"job_id": first_id, "action": "retry"},
            {
                "id": first_id,
                "kind": "pdf_translation",
                "status": "queued",
                "attempt": 2,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        )
    return jobs


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/settings/translation"),
        ("PUT", "/settings/translation"),
        ("POST", "/settings/translation/check"),
        ("POST", "/papers/paper/translations/prepare"),
        ("POST", "/papers/paper/translations"),
        ("GET", "/papers/paper/translations"),
        ("GET", "/papers/paper/translations/translation"),
        ("POST", "/papers/paper/translations/translation/cancel"),
        ("GET", "/papers/paper/translations/translation/artifacts/mono"),
        ("GET", "/translations/translation/artifacts/dual"),
    ],
)
def test_translation_routes_and_contracts_are_removed(tmp_path, method, path):
    with client(tmp_path) as api:
        assert api.request(method, "/api/v1" + path).status_code == 404
        schema = api.get("/openapi.json").json()
        assert not any("translation" in path for path in schema["paths"])
        assert not any("Translation" in name for name in schema["components"]["schemas"])
        assert api.get("/api/v1/settings/models").status_code == 200
        assert post(api, "/jobs", {"kind": "pdf_translation"}).status_code == 422


@pytest.mark.parametrize(
    "arguments",
    [
        ["--translation-server"],
        ["--translation-port", "8999"],
        ["--translation-root", "C:/synthetic"],
    ],
)
def test_cli_rejects_removed_server_flags(monkeypatch, arguments):
    monkeypatch.setattr(sys, "argv", ["researchgraph", *arguments])
    with pytest.raises(SystemExit) as stopped:
        main()
    assert stopped.value.code == 2


def test_startup_retires_unfinished_work_and_preserves_history_usage_and_files(
    tmp_path, monkeypatch
):
    with client(tmp_path) as api:
        pass
    # Simulate a process that crashed with work still running. Seeding after
    # shutdown avoids the normal graceful-shutdown recovery of running jobs.
    jobs = _seed(api)
    engine = api.app.state.engine
    unchanged = _snapshot(engine, exclude=("jobs", "pdf_translations"))
    with engine.connect().execution_options(sqlite_readonly=True) as connection:
        histories = {
            job_id: {
                table: tuple(
                    connection.execute(
                        text(f'SELECT * FROM "{table}" WHERE id=:id'), {"id": job_id}
                    ).one()
                )
                for table in ("jobs", "pdf_translations")
            }
            for job_id, status in jobs
            if status not in {"queued", "running"}
        }
    artifact = tmp_path / "translations" / "history.pdf"
    artifact.parent.mkdir()
    artifact.write_bytes(b"synthetic historic artifact, do not rewrite")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("removed translation must not launch a process or model request")

    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    with client(tmp_path, worker=True) as api:
        assert api.get("/api/v1/health").json()["schema_version"] == "lite0008"
        assert _snapshot(api.app.state.engine, exclude=("jobs", "pdf_translations")) == unchanged
        with Session(api.app.state.engine) as session:
            for job_id, status in jobs:
                job, record = session.get(Job, job_id), session.get(PDFTranslation, job_id)
                assert job.attempt == 2 and job.result == {"keep": status}
                if status in {"queued", "running"}:
                    assert job.status == "cancelled" and job.stage == "interrupted"
                    assert job.error == TRANSLATION_REMOVED_MESSAGE
                    assert record.status == "CANCELLED" and record.stage == "disabled"
                    assert record.error_code == TRANSLATION_REMOVED
                else:
                    connection = session.connection()
                    for table, old in histories[job_id].items():
                        assert (
                            tuple(
                                connection.execute(
                                    text(f'SELECT * FROM "{table}" WHERE id=:id'), {"id": job_id}
                                ).one()
                            )
                            == old
                        )
        for index, (job_id, _status) in enumerate(jobs):
            detail = api.get(f"/api/v1/jobs/{job_id}")
            assert detail.status_code == 200
            if _status in {"cancelled", "interrupted"}:
                assert detail.json()["stage"] == "interrupted"
            response = post(api, f"/jobs/{job_id}/retry", key=f"removed-retry-{index}")
            assert response.status_code == 409
            assert response.json()["error"]["code"] == TRANSLATION_REMOVED
        replay = post(api, f"/jobs/{jobs[0][0]}/retry", key="historic-retry")
        assert replay.status_code == 409 and replay.json()["error"]["code"] == TRANSLATION_REMOVED
        assert _snapshot(api.app.state.engine, exclude=("jobs", "pdf_translations")) == unchanged
        assert artifact.read_bytes() == b"synthetic historic artifact, do not rewrite"
        with Session(api.app.state.engine) as session:
            project_id = session.get(Job, jobs[0][0]).project_id
        listed = api.get(f"/api/v1/projects/{project_id}/jobs")
        assert listed.status_code == 200 and len(listed.json()["items"]) == len(jobs)
        assert not (tmp_path / "backups").exists()  # Same schema; no downgrade or reinitialization.
    with client(tmp_path) as api:
        assert _snapshot(api.app.state.engine, exclude=("jobs", "pdf_translations")) == unchanged


@pytest.mark.parametrize("action", ["claim", "cancel"])
def test_old_work_inserted_after_startup_is_stopped_without_attempt_or_usage(tmp_path, action):
    with client(tmp_path) as api:
        jobs = _seed(api, statuses=("queued",))
        job_id = jobs[0][0]
        before = _snapshot(
            api.app.state.engine, exclude=("jobs", "pdf_translations", "idempotency_keys")
        )
        if action == "claim":
            assert claim_queued_job(api.app.state.engine) is None
            diagnostic = post(api, "/jobs", {"kind": "diagnostics"}, key="diagnostic-key").json()
            assert claim_queued_job(api.app.state.engine) == (diagnostic["id"], "diagnostics")
            with Session(api.app.state.engine) as session, session.begin():
                session.delete(session.get(Job, diagnostic["id"]))
        else:
            response = post(api, f"/jobs/{job_id}/cancel", key="removed-cancel")
            assert response.status_code == 200 and response.json()["status"] == "cancelled"
        with Session(api.app.state.engine) as session:
            job = session.get(Job, job_id)
            record = session.get(PDFTranslation, job_id)
            assert job.status == "cancelled" and job.attempt == 2
            assert record.status == "CANCELLED" and record.error_code == TRANSLATION_REMOVED
        assert (
            _snapshot(
                api.app.state.engine, exclude=("jobs", "pdf_translations", "idempotency_keys")
            )
            == before
        )
