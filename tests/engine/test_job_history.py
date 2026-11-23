import subprocess
import time
from uuid import UUID, uuid4

from researchgraph import ingest
from researchgraph.models import Job, Paper
from sqlalchemy.orm import Session
from test_engine import client, post
from test_ingest import FIXTURES, queue


def test_workspace_lists_reach_records_before_the_legacy_window(tmp_path):
    with client(tmp_path) as api:
        project = post(api, "/projects", {"name": "Workspace History"}).json()
        project_id = project["id"]
        assert api.get(f"/api/v1/projects/{project_id}").json() == project
        ids = [str(UUID(int=i)) for i in range(1, 52)]
        with Session(api.app.state.engine) as session, session.begin():
            for index, item_id in enumerate(ids):
                timestamp = f"2026-10-30T00:00:{index:02d}Z"
                session.add(
                    Paper(id=item_id, project_id=project_id, title=item_id, created_at=timestamp)
                )
                session.add(
                    Job(
                        id=item_id,
                        project_id=project_id,
                        kind="diagnostics",
                        status="running" if index == 0 else "succeeded",
                        attempt=1,
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
        assert len(api.get("/api/v1/jobs").json()) == 50
        first = api.get("/api/v1/jobs/page?limit=50").json()
        assert [job["id"] for job in first["items"]] == ids[:0:-1]
        last = api.get("/api/v1/jobs/page", params={"cursor": first["next_cursor"]}).json()
        assert last["next_cursor"] is None
        assert [(job["id"], job["status"]) for job in last["items"]] == [(ids[0], "running")]
        path = f"/api/v1/projects/{project_id}/papers"
        first_papers = api.get(path).json()
        assert first_papers["total"] == 51 and first_papers["next_cursor"] == 50
        last_papers = api.get(path, params={"cursor": first_papers["next_cursor"]}).json()
        assert last_papers["total"] == 51 and last_papers["next_cursor"] is None
        assert [paper["id"] for paper in last_papers["items"]] == ids[:1]


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


def test_observed_progress_survives_cancel_and_retry_keeps_batch_result(tmp_path, monkeypatch):
    original = subprocess.Popen

    def slow_child(command, **kwargs):
        work = command[command.index("--output-dir") + 1]
        script = "\n".join(
            [
                "import sys, time",
                "from pathlib import Path",
                "from researchgraph.workspaces import report_stage, worker_workspace",
                "work = Path(sys.argv[1])",
                "with worker_workspace(work):",
                "    report_stage(work, 'parsing')",
                "    time.sleep(60)",
            ]
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
        with Session(api.app.state.engine) as session, session.begin():
            persisted = session.get(Job, job["id"])
            persisted.result = {
                "document_version_id": "version",
                "completed_batches": "1",
                "total_batches": "7",
                "batches": [{"index": 0, "status": "succeeded"}],
            }
        retry = post(api, f"/jobs/{job['id']}/retry", key="progress-retry").json()
        assert retry["status"] == "queued" and retry["stage"] is None
        assert retry["result"]["completed_batches"] == "1"
        assert retry["result"]["batches"][0]["status"] == "succeeded"
