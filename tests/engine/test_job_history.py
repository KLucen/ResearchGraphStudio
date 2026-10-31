import json
import subprocess
import time
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from researchgraph import ingest
from researchgraph.models import Job
from researchgraph.storage import make_engine, migrate
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_engine import client, post
from test_ingest import FIXTURES, queue


def test_keyset_history_keeps_order_across_new_jobs_and_retry(tmp_path):
    with client(tmp_path) as api:
        project = post(api, "/projects", {"name": "History"}).json()["id"]
        other = post(api, "/projects", {"name": "Other"}, "other-project").json()["id"]
        ids = [str(UUID(int=i)) for i in range(1, 106)]
        with Session(api.app.state.engine) as session, session.begin():
            for job_id in ids:
                session.add(
                    Job(
                        id=job_id,
                        project_id=project,
                        kind="pdf_import",
                        status="cancelled",
                        attempt=1,
                        created_at="2026-10-30T00:00:00Z",
                        updated_at="2026-10-30T00:00:00Z",
                    )
                )
        url = f"/api/v1/projects/{project}/jobs?limit=13"
        first = api.get(url).json()
        assert [j["id"] for j in first["items"]] == ids[::-1][:13]
        cursor = first["next_cursor"]
        first_cursor = cursor
        second = api.get(url + "&cursor=" + first_cursor).json()
        # A later row with a tied timestamp and an older UUID cannot enter this snapshot.
        tied_id = str(UUID(int=0))
        with Session(api.app.state.engine) as session, session.begin():
            session.add(
                Job(
                    id=tied_id,
                    project_id=project,
                    kind="diagnostics",
                    status="succeeded",
                    attempt=1,
                    created_at="2026-10-30T00:00:00Z",
                    updated_at="2026-10-30T00:00:00Z",
                )
            )
        # New entries and status updates cannot move an existing cursor boundary.
        new = queue(api, project, FIXTURES / "two-pages.pdf", "new-history-job")
        retried = post(api, f"/jobs/{ids[1]}/retry", key="history-retry").json()
        assert retried["stage"] is None and retried["status"] == "queued"
        assert api.get(url + "&cursor=" + cursor).json() == second
        seen = [j["id"] for j in first["items"]]
        while cursor:
            page = api.get(url + "&cursor=" + cursor).json()
            seen.extend(j["id"] for j in page["items"])
            cursor = page["next_cursor"]
        assert seen == ids[::-1] and len(set(seen)) == 105
        assert tied_id not in seen
        assert api.get(url).json()["items"][0]["id"] == new["id"]
        assert api.get(f"/api/v1/projects/{other}/jobs?cursor={first_cursor}").status_code == 422
        for query in ("cursor=bad", f"cursor={uuid4()}", "limit=0", "limit=101"):
            assert api.get(f"/api/v1/projects/{project}/jobs?{query}").status_code == 422


def test_observed_progress_survives_cancel_and_resets_on_retry(tmp_path, monkeypatch):
    original = subprocess.Popen

    def slow_child(command, **kwargs):
        work = command[command.index("--output-dir") + 1]
        script = (
            "import sys,time; from pathlib import Path; "
            "from researchgraph.workspaces import worker_workspace,report_stage; "
            "work=Path(sys.argv[1]); "
            "\nwith worker_workspace(work):\n report_stage(work,'parsing'); time.sleep(60)\n"
        )
        return original([command[0], "-c", script, work], **kwargs)

    monkeypatch.setattr(ingest.subprocess, "Popen", slow_child)
    with client(tmp_path, worker=True) as api:
        project = post(api, "/projects", {"name": "Progress"}).json()["id"]
        job = queue(api, project, FIXTURES / "two-pages.pdf", "progress-job")
        assert job["stage"] is None
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            current = api.get(f"/api/v1/jobs/{job['id']}").json()
            if current["stage"] == "parsing":
                break
            time.sleep(0.05)
        assert current["stage"] == "parsing" and current["status"] == "running"
        assert (
            post(api, f"/jobs/{job['id']}/cancel", key="progress-cancel").json()["status"]
            == "cancelled"
        )
    with client(tmp_path) as api:
        assert api.get(f"/api/v1/jobs/{job['id']}").json()["stage"] == "parsing"
        retry = post(api, f"/jobs/{job['id']}/retry", key="progress-retry").json()
        assert retry["status"] == "queued" and retry["stage"] is None


def test_upgrade_0003_keeps_jobs_and_old_idempotent_responses(tmp_path):
    engine = make_engine(tmp_path)
    config = Config()
    config.set_main_option(
        "script_location",
        str(Path(__file__).parents[2] / "services/engine/researchgraph/migrations"),
    )
    old = dict(
        id=str(uuid4()),
        kind="diagnostics",
        status="succeeded",
        attempt=1,
        error=None,
        result=None,
        project_id=None,
        created_at="now",
        updated_at="now",
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0003")
        connection.exec_driver_sql(
            "INSERT INTO jobs (id,kind,status,attempt,created_at,updated_at) "
            "VALUES (?,?,'succeeded',1,'now','now')",
            (old["id"], old["kind"]),
        )
    migrate(engine, tmp_path)
    with Session(engine) as session:
        job = session.get(Job, old["id"])
        assert job.stage is None and job.status == "succeeded" and job.attempt == 1
    from researchgraph.schemas import JobView

    assert JobView.model_validate(json.loads(json.dumps(old))).stage is None
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0004"
        assert connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE name='ix_jobs_project_history'"
        ).fetchone()
    assert len(list((tmp_path / "backups").glob("*.sqlite3"))) == 1
    engine.dispose()
