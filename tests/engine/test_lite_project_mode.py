"""Lite project mode migration and API defaults."""

import hashlib
import json
from pathlib import Path

from alembic import command
from alembic.config import Config
from researchgraph.models import Idempotency, Project
from researchgraph.storage import SCHEMA_HEAD, make_engine, migrate
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_engine import client


def _upgrade_to(data: Path, revision: str) -> None:
    engine = make_engine(data)
    config = Config()
    config.set_main_option(
        "script_location",
        str(Path(__file__).parents[2] / "services/engine/researchgraph/migrations"),
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)
    engine.dispose()


def test_existing_project_is_backfilled_as_legacy(tmp_path):
    _upgrade_to(tmp_path, "0020")
    engine = make_engine(tmp_path)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO projects (id,name,description,created_at) "
                "VALUES ('old','Old project','keep','2026-11-09T00:00:00Z')"
            )
        )
    migrate(engine, tmp_path)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == SCHEMA_HEAD
        assert (
            connection.scalar(text("SELECT experience_mode FROM projects WHERE id='old'"))
            == "legacy"
        )
    engine.dispose()


def test_new_project_defaults_lite_and_explicit_legacy_is_idempotent(tmp_path):
    with client(tmp_path) as api:
        default = api.post(
            "/api/v1/projects", json={"name": "Lite"}, headers={"Idempotency-Key": "lite-default"}
        )
        assert default.status_code == 201, default.text
        assert default.json()["experience_mode"] == "lite"

        legacy_body = {"name": "Legacy", "experience_mode": "legacy"}
        first = api.post(
            "/api/v1/projects", json=legacy_body, headers={"Idempotency-Key": "legacy-explicit"}
        )
        replay = api.post(
            "/api/v1/projects", json=legacy_body, headers={"Idempotency-Key": "legacy-explicit"}
        )
        assert first.status_code == replay.status_code == 201
        assert replay.json() == first.json()
        assert first.json()["experience_mode"] == "legacy"


def test_same_idempotency_key_cannot_change_project_mode(tmp_path):
    with client(tmp_path) as api:
        headers = {"Idempotency-Key": "mode-conflict"}
        first = api.post("/api/v1/projects", json={"name": "Mode"}, headers=headers)
        conflict = api.post(
            "/api/v1/projects", json={"name": "Mode", "experience_mode": "legacy"}, headers=headers
        )
        assert first.status_code == 201
        assert first.json()["experience_mode"] == "lite"
        assert conflict.status_code == 409


def test_pre_lite_idempotency_replay_defaults_to_legacy(tmp_path):
    with client(tmp_path) as api:
        headers = {"Idempotency-Key": "legacy-replay"}
        created = api.post("/api/v1/projects", json={"name": "Replay"}, headers=headers)
        assert created.status_code == 201
        with Session(api.app.state.engine) as session, session.begin():
            project = session.get(Project, created.json()["id"])
            project.experience_mode = "legacy"
            item = session.get(Idempotency, "project:legacy-replay")
            item.request_hash = hashlib.sha256(
                json.dumps({"name": "Replay", "description": ""}, sort_keys=True).encode()
            ).hexdigest()
            item.response = {
                key: value for key, value in item.response.items() if key != "experience_mode"
            }
        replay = api.post("/api/v1/projects", json={"name": "Replay"}, headers=headers)
        assert replay.status_code == 201
        assert replay.json()["experience_mode"] == "legacy"
