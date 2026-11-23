import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from researchgraph import storage
from researchgraph.archive_models import ArchivedItem
from researchgraph.knowledge_library import ensure_library
from researchgraph.knowledge_library_models import LibraryPaper
from researchgraph.models import Job, now
from sqlalchemy.orm import Session
from test_engine import client, post


def test_terminal_tasks_archive_restore_and_purge_keep_provenance(tmp_path):
    with client(tmp_path) as api:
        project_id = post(api, "/projects", {"name": "Synthetic archive"}).json()["id"]
        with Session(api.app.state.engine) as db, db.begin():
            job_ids = {}
            for kind, payload, status in (
                (
                    "card",
                    {"item_kind": "paper_overview", "postprocess_contract_version": 6},
                    "failed",
                ),
                ("reading", {"item_kind": "paper_reading"}, "succeeded"),
                ("translation", {"item_kind": "translation"}, "succeeded"),
                ("active", {"item_kind": "paper_reading"}, "queued"),
            ):
                job = Job(
                    id=str(uuid4()),
                    project_id=project_id,
                    kind="llm_document_postprocess",
                    payload=payload,
                    status=status,
                    created_at=now(),
                    updated_at=now(),
                    result={"title": "Synthetic paper"} if kind == "card" else None,
                )
                db.add(job)
                job_ids[kind] = job.id
        attempt = post(api, "/archive", {"kind": "job", "target_id": job_ids["active"]})
        assert attempt.status_code == 409
        assert attempt.json()["error"]["code"] == "ARCHIVE_TASK_ACTIVE"

        archived = {}
        for kind, title in (
            ("card", "论文卡片集生成 · Synthetic paper"),
            ("reading", "全文精读笔记生成"),
            ("translation", "逐段中文翻译"),
        ):
            target = {"kind": "job", "target_id": job_ids[kind]}
            response = post(api, "/archive", target, f"archive-{kind}")
            assert response.status_code == 200, response.text
            archived[kind] = response.json()["id"]
            assert response.json()["title"] == title
            assert post(api, "/archive", target, f"repeat-{kind}").json() == response.json()
            assert api.get(f"/api/v1/jobs/{job_ids[kind]}").status_code == 404

        page = api.get("/api/v1/archive?kind=job&offset=1&limit=1").json()
        assert page["total"] == 3 and len(page["items"]) == 1
        assert [item["id"] for item in api.get("/api/v1/jobs").json()] == [job_ids["active"]]
        history = api.get(f"/api/v1/projects/{project_id}/jobs?limit=1").json()
        assert [item["id"] for item in history["items"]] == [job_ids["active"]]
        assert history["next_cursor"] is None
        retry = post(api, f"/jobs/{job_ids['card']}/retry")
        assert retry.status_code == 409 and retry.json()["error"]["code"] == "JOB_ARCHIVED"

        restore = f"/archive/{archived['card']}/restore"
        assert post(api, restore).status_code == post(api, restore).status_code == 200
        assert api.get(f"/api/v1/jobs/{job_ids['card']}").json()["status"] == "failed"
        path = f"/api/v1/archive/{archived['translation']}"
        assert api.delete(path).status_code == api.delete(path).status_code == 200
        assert (
            post(api, f"/archive/{archived['translation']}/restore", key="purged-job").status_code
            == 404
        )
        assert api.get("/api/v1/archive?kind=job").json()["total"] == 1
        with Session(api.app.state.engine) as db:
            receipt = db.get(Job, job_ids["translation"])
            assert receipt.payload == {"item_kind": "translation"}
            assert db.get(ArchivedItem, archived["translation"]).title == ""

    with client(tmp_path) as reopened:
        assert reopened.get(f"/api/v1/jobs/{job_ids['translation']}").status_code == 404
        assert reopened.get(f"/api/v1/jobs/{job_ids['card']}").status_code == 200


def test_archive_migration_backfills_previous_library_archive_and_backup(tmp_path):
    engine = storage.make_engine(tmp_path)
    config = Config()
    config.set_main_option("script_location", str(Path(storage.__file__).parent / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "lite0018")
        ArchivedItem.__table__.drop(connection, checkfirst=True)
    paper_id = str(uuid4())
    with Session(engine) as db, db.begin():
        library = ensure_library(db)
        db.add(
            LibraryPaper(
                id=paper_id,
                library_id=library.id,
                identity_keys=["synthetic-test"],
                title="Saved archive",
                note="Existing private note",
                archived=True,
                created_at=now(),
                updated_at=now(),
            )
        )
    storage.migrate(engine, tmp_path)
    backup_path = next((tmp_path / "backups").glob("before-migration-*.sqlite3"))
    with closing(sqlite3.connect(backup_path)) as backup:
        assert backup.execute("SELECT version_num FROM alembic_version").fetchone() == ("lite0018",)
        assert backup.execute("SELECT archived FROM knowledge_library_papers").fetchone() == (1,)
    with client(tmp_path) as api:
        listed = api.get("/api/v1/archive?kind=knowledge_paper").json()
        assert listed["total"] == 1
        item = listed["items"][0]
        assert item["target_id"] == paper_id and item["title"] == "Saved archive"
        assert post(api, f"/archive/{item['id']}/restore").status_code == 200
        papers = api.get("/api/v1/knowledge/papers").json()
        assert papers["total"] == 1 and papers["items"][0]["note"] == "Existing private note"
