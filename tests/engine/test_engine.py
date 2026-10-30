import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from filelock import Timeout
from researchgraph.app import create_app
from researchgraph.models import Event, Job
from researchgraph.storage import make_engine, migrate
from sqlalchemy import select, text
from sqlalchemy.orm import Session

TOKEN = "test-only-token-" * 4
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def client(path: Path, worker: bool = False) -> TestClient:
    return TestClient(create_app(path, TOKEN, start_worker=worker), headers=AUTH)


def post(api: TestClient, path: str, body: dict | None = None, key: str = "test-key-123"):
    return api.post("/api/v1" + path, json=body, headers={"Idempotency-Key": key})


def test_auth_origin_and_health(tmp_path):
    with client(tmp_path) as api:
        assert api.get("/api/v1/health").json()["fts5"] is True
        assert api.get("/api/v1/health", headers={"Authorization": ""}).status_code == 401
        assert api.get("/openapi.json", headers={"Authorization": "bad"}).status_code == 401
        assert (
            api.get("/api/v1/projects", headers={"Origin": "https://evil.test"}).status_code == 403
        )
        assert api.get("/api/v1/health", headers={"Host": "evil.test"}).status_code == 400


def test_project_persistence_idempotency_and_atomic_event(tmp_path):
    body = {"name": "  中文路径研究  ", "description": "What changes?"}
    with client(tmp_path) as api:
        first = post(api, "/projects", body)
        assert first.status_code == 201
        assert first.json()["name"] == "中文路径研究"
        assert post(api, "/projects", body).json() == first.json()
        assert post(api, "/projects", {"name": "different"}).status_code == 409
        with Session(api.app.state.engine) as session:
            assert len(session.scalars(select(Event)).all()) == 1
    with client(tmp_path) as reopened:
        assert reopened.get("/api/v1/projects").json()["items"] == [first.json()]


def test_simultaneous_retry_does_not_duplicate_project(tmp_path):
    with client(tmp_path) as api, ThreadPoolExecutor(max_workers=3) as executor:
        responses = list(executor.map(lambda _: post(api, "/projects", {"name": "One"}), range(3)))
        assert {r.status_code for r in responses} == {201}
        assert len({r.json()["id"] for r in responses}) == 1


@pytest.mark.parametrize(
    "payload", [{"name": "  "}, {"name": "x" * 121}, {"name": "ok", "sql": "DROP TABLE projects"}]
)
def test_invalid_project_cannot_write(tmp_path, payload):
    with client(tmp_path) as api:
        assert post(api, "/projects", payload).status_code == 422
        assert api.get("/api/v1/projects").json()["items"] == []


def test_pagination(tmp_path):
    with client(tmp_path) as api:
        for i in range(3):
            post(api, "/projects", {"name": str(i)}, f"pagination-{i}")
        page = api.get("/api/v1/projects?limit=2").json()
        assert len(page["items"]) == 2 and page["next_cursor"] == 2
        assert len(api.get("/api/v1/projects?cursor=2&limit=2").json()["items"]) == 1


def test_job_cancel_retry_and_restart_recovery(tmp_path):
    with client(tmp_path) as api:
        job = post(api, "/jobs", {"kind": "diagnostics"}).json()
        assert post(api, "/jobs", {"kind": "diagnostics"}).json()["id"] == job["id"]
        path = f"/jobs/{job['id']}"
        assert post(api, path + "/cancel", key="cancel-key").json()["status"] == "cancelled"
        assert post(api, path + "/retry", key="retry-key").json()["status"] == "queued"
        assert post(api, path + "/retry", key="retry-key").status_code == 200
        assert post(api, path + "/retry", key="another-key").status_code == 409
    engine = make_engine(tmp_path)
    with Session(engine) as session, session.begin():
        saved = session.get(Job, job["id"])
        saved.status, saved.attempt = "running", 1
    engine.dispose()
    with client(tmp_path) as api:
        assert api.get("/api/v1" + path).json()["status"] == "interrupted"
        with Session(api.app.state.engine) as session, session.begin():
            session.get(Job, job["id"]).attempt = 3
        exhausted = post(api, path + "/retry", key="retry-exhausted-key")
        assert exhausted.status_code == 409
        assert api.get("/api/v1" + path).json()["status"] == "interrupted"


def test_real_diagnostic_worker(tmp_path):
    with client(tmp_path, worker=True) as api:
        job = post(api, "/jobs", {"kind": "diagnostics"}).json()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = api.get(f"/api/v1/jobs/{job['id']}").json()
            if result["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.05)
        assert result["status"] == "succeeded"
        assert result["result"] == {"integrity": "ok", "foreign_keys": True, "fts5": True}


def test_single_writer_lock(tmp_path):
    with client(tmp_path), pytest.raises(Timeout), client(tmp_path):
        pass


def test_migration_failure_rolls_back_and_preserves_backup(tmp_path):
    data = tmp_path / "data"
    with client(data) as api:
        post(api, "/projects", {"name": "Keep me"})
    source = Path(__file__).parents[2] / "services/engine/researchgraph/migrations"
    migrations = tmp_path / "migrations"
    shutil.copytree(source, migrations)
    (migrations / "versions/0004_failure.py").write_text(
        "from alembic import op\nimport sqlalchemy as sa\n"
        "revision='0004'\ndown_revision='0003'\n"
        "def upgrade():\n    op.create_table('half_written',sa.Column('id',sa.Integer()))\n"
        "    raise RuntimeError('injected migration failure')\n",
        encoding="utf-8",
    )
    engine = make_engine(data)
    with pytest.raises(RuntimeError, match="injected"):
        migrate(engine, data, migrations)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT name FROM projects")) == "Keep me"
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0003"
        assert not connection.scalar(
            text("SELECT name FROM sqlite_master WHERE name='half_written'")
        )
    assert len(list((data / "backups").glob("*.sqlite3"))) == 1
    engine.dispose()
