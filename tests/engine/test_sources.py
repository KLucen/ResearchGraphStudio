import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
from researchgraph import source_files
from researchgraph.models import Event, PaperSource
from researchgraph.storage import make_engine, migrate
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_engine import client, post
from test_ingest import FIXTURES, queue, wait_job


def setup_source(api, path, mode="reference"):
    project = post(api, "/projects", {"name": "Source tests"}).json()["id"]
    job = wait_job(api, queue(api, project, path, "initial-import", mode))
    assert job["status"] == "succeeded", job
    detail = api.get(f"/api/v1/papers/{job['result']['paper_id']}").json()
    return project, detail["paper"]["id"], detail["sources"][0]


def act(api, source, kind="check", key="source-check", **extra):
    return post(
        api,
        f"/sources/{source['id']}/{kind}",
        {
            "expected_generation": source["generation"],
            **extra,
        },
        key,
    )


def test_original_and_managed_checks_are_independent_and_persist(tmp_path):
    original = tmp_path / "论文 source.pdf"
    shutil.copyfile(FIXTURES / "two-pages.pdf", original)
    data = tmp_path / "data"
    with client(data, worker=True) as api:
        project, paper, source = setup_source(api, original, "managed")
        revision = source["revision_id"]
        blocks = api.get(f"/api/v1/revisions/{revision}/chunks").json()
        assert source["last_check"] is None
        job = wait_job(api, act(api, source).json())
        assert job["result"]["original_state"] == job["result"]["managed_state"] == "available"
        original.unlink()
        job = wait_job(api, act(api, source, key="check-missing").json())
        assert job["result"]["original_state"] == "missing"
        assert job["result"]["managed_state"] == "available"
        with Session(api.app.state.engine) as session:
            managed = Path(session.get(PaperSource, source["id"]).managed_path)
        managed.write_bytes(b"Changed cache")
        job = wait_job(api, act(api, source, key="check-changed-cache").json())
        assert job["result"]["managed_state"] == "changed"
        assert api.get(f"/api/v1/revisions/{revision}/chunks").json() == blocks
        assert len(api.get(f"/api/v1/projects/{project}/jobs").json()["items"]) == 4
        other = post(api, "/projects", {"name": "other"}, "other-project").json()["id"]
        assert api.get(f"/api/v1/projects/{other}/jobs").json() == {
            "items": [],
            "next_cursor": None,
        }
    with client(data) as api:
        checked = api.get(f"/api/v1/papers/{paper}").json()["sources"][0]["last_check"]
        assert checked["original"]["state"] == "missing"
        assert checked["managed"]["state"] == "changed"
        assert checked["checked_at"]


def test_relocation_preserves_identity_history_and_idempotency(tmp_path):
    original, moved = tmp_path / "原路径.pdf", tmp_path / "移动后的 paper.pdf"
    shutil.copyfile(FIXTURES / "two-pages.pdf", original)
    data = tmp_path / "data"
    with client(data, worker=True) as api:
        project, paper, source = setup_source(api, original)
        blocks = api.get(f"/api/v1/revisions/{source['revision_id']}/chunks").json()
        original.rename(moved)
        queued = act(api, source, "relocate", "relocate-identical", path=str(moved))
        assert queued.status_code == 202
        job = wait_job(api, queued.json())
        assert job["status"] == "succeeded", job
        assert (
            act(api, source, "relocate", "relocate-identical", path=str(moved)).json()["id"]
            == job["id"]
        )
        detail = api.get(f"/api/v1/papers/{paper}").json()
        updated = detail["sources"][0]
        assert updated["id"] == source["id"] and updated["revision_id"] == source["revision_id"]
        assert (
            updated["path"] == str(moved.resolve()) and updated["generation"] > source["generation"]
        )
        assert len(detail["revisions"]) == 1
        assert api.get(f"/api/v1/revisions/{source['revision_id']}/chunks").json() == blocks
        assert act(api, source, key="stale-source-generation").status_code == 409
        with Session(api.app.state.engine) as session:
            events = session.scalars(
                select(Event).where(Event.event_type == "SOURCE_RELOCATED")
            ).all()
            assert len(events) == 1
            assert events[0].payload["old_path"] == str(original.resolve())
            assert events[0].payload["new_path"] == str(moved.resolve())
    with client(data) as api:
        assert api.get(f"/api/v1/papers/{paper}").json()["sources"][0] == updated


def test_wrong_content_and_registered_destination_do_not_relocate(tmp_path):
    original, other = tmp_path / "original.pdf", tmp_path / "other.pdf"
    shutil.copyfile(FIXTURES / "two-pages.pdf", original)
    shutil.copyfile(FIXTURES / "image-only.pdf", other)
    with client(tmp_path / "data", worker=True) as api:
        project, paper, source = setup_source(api, original)
        job = wait_job(api, act(api, source, "relocate", "wrong-content", path=str(other)).json())
        assert job["status"] == "failed" and "内容不同" in job["error"]
        assert api.get(f"/api/v1/papers/{paper}").json()["sources"][0] == source
        second = wait_job(api, queue(api, project, other, "other-paper"))
        assert second["result"]["paper_id"] != paper
        shutil.copyfile(original, other)
        job = wait_job(
            api, act(api, source, "relocate", "conflict-destination", path=str(other)).json()
        )
        assert job["status"] == "failed" and "冲突" in job["error"]
        assert api.get(f"/api/v1/papers/{paper}").json()["sources"][0] == source


def test_queued_stale_checks_and_relocations_cannot_overwrite_new_revision(tmp_path):
    original, moved = tmp_path / "original.pdf", tmp_path / "moved.pdf"
    shutil.copyfile(FIXTURES / "two-pages.pdf", original)
    shutil.copyfile(original, moved)
    data = tmp_path / "data"
    with client(data, worker=True) as api:
        project, paper, source = setup_source(api, original)
    with client(data) as api:
        shutil.copyfile(FIXTURES / "image-only.pdf", original)
        imported = queue(api, project, original, "new-revision")
        checked = act(api, source).json()
        relocated = act(api, source, "relocate", "queued-relocation", path=str(moved)).json()
    with client(data, worker=True) as api:
        assert wait_job(api, imported)["status"] == "succeeded"
        for job in (checked, relocated):
            failed = wait_job(api, job)
            assert failed["status"] == "failed" and "来源已更新" in failed["error"]
        updated = api.get(f"/api/v1/papers/{paper}").json()["sources"][0]
        assert updated["last_check"] is None and updated["path"] == source["path"]
        assert updated["revision_id"] != source["revision_id"]


def test_cancelled_source_check_can_retry_after_restart(tmp_path):
    with client(tmp_path, worker=True) as api:
        _, paper, source = setup_source(api, FIXTURES / "two-pages.pdf")
    with client(tmp_path) as api:
        job = act(api, source).json()
        assert (
            post(api, f"/jobs/{job['id']}/cancel", key="cancel-check").json()["status"]
            == "cancelled"
        )
    with client(tmp_path, worker=True) as api:
        assert (
            wait_job(api, post(api, f"/jobs/{job['id']}/retry", key="retry-check").json())["status"]
            == "succeeded"
        )
        assert (
            api.get(f"/api/v1/papers/{paper}").json()["sources"][0]["last_check"]["original"][
                "state"
            ]
            == "available"
        )


def test_upgrade_0002_preserves_source_and_starts_unchecked(tmp_path):
    engine = make_engine(tmp_path)
    config = Config()
    config.set_main_option(
        "script_location",
        str(Path(__file__).parents[2] / "services/engine/researchgraph/migrations"),
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0002")
        connection.exec_driver_sql("INSERT INTO projects VALUES ('p','Project','','now')")
        connection.exec_driver_sql("INSERT INTO papers VALUES ('paper','p','Title','now')")
        connection.exec_driver_sql(
            "INSERT INTO attachment_revisions VALUES ('r','paper','hash','parser',2,'[]','now')"
        )
        connection.exec_driver_sql(
            "INSERT INTO paper_sources VALUES ('s','paper','r','C:/source.pdf','reference',NULL)"
        )
    migrate(engine, tmp_path)
    with Session(engine) as session:
        source = session.get(PaperSource, "s")
        assert source.generation == 0 and source.last_check is None
        assert source.revision_id == "r" and source.path == "C:/source.pdf"
    (backup,) = (tmp_path / "backups").glob("*.sqlite3")
    with sqlite3.connect(backup) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0002"
    engine.dispose()


def test_read_limits_and_permission_errors_have_explicit_states(tmp_path, monkeypatch):
    path = tmp_path / "sample.pdf"
    path.write_bytes(b"12345")
    monkeypatch.setattr(source_files, "MAX_BYTES", 4)
    assert source_files.inspect_file(str(path), "hash").state == "too_large"

    def denied(*_args, **_kwargs):
        raise PermissionError("private detail")

    monkeypatch.setattr(Path, "open", denied)
    assert source_files.inspect_file(str(path), "hash").model_dump() == {
        "state": "unreadable",
        "observed_sha256": None,
    }


def test_file_replaced_during_read_does_not_claim_a_hash_match(tmp_path, monkeypatch):
    path = tmp_path / "sample.pdf"
    path.write_bytes(b"unchanged bytes")
    before = path.stat()
    monkeypatch.setattr(
        Path,
        "stat",
        lambda *_args, **_kwargs: SimpleNamespace(
            st_dev=before.st_dev,
            st_ino=before.st_ino + 1,
            st_size=before.st_size,
            st_mtime_ns=before.st_mtime_ns,
        ),
    )
    assert source_files.inspect_file(str(path), "hash").model_dump() == {
        "state": "unstable",
        "observed_sha256": None,
    }
