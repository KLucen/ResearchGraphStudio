import json
import os
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from researchgraph.credentials import SecretStore
from researchgraph.model_settings import ModelProfile, ModelRole, from_snapshot, snapshot_for
from researchgraph.models import Project, now
from researchgraph.providers import ConfiguredProvider
from researchgraph.storage import make_engine
from sqlalchemy.orm import Session
from test_engine import client, post


@pytest.fixture
def vault(monkeypatch):
    values = {}
    monkeypatch.setattr(SecretStore, "put", lambda self, key, value: values.__setitem__(key, value))
    monkeypatch.setattr(SecretStore, "get", lambda self, key: values[key])
    monkeypatch.setattr(SecretStore, "delete", lambda self, key: values.pop(key, None))
    return values


def profile_body(**changes):
    return {
        "name": "Test gateway",
        "provider": "compatible",
        "base_url": "https://models.example/v1",
        "model": "test-model",
        **changes,
    }


def test_profile_secrets_roles_snapshots_and_delete(tmp_path, vault):
    secret = "unit-credential:" + str(uuid4())
    with client(tmp_path) as api:
        project = post(api, "/projects", {"name": "Models"}).json()["id"]
        route = f"/projects/{project}"
        saved = post(api, route + "/models", profile_body(api_key=secret))
        assert saved.status_code == 200, saved.text
        p = saved.json()
        assert p["has_api_key"] and secret not in saved.text and "credential_ref" not in p
        roles = post(api, route + "/model-roles", {"extraction": p["id"], "reasoning": p["id"]})
        assert roles.status_code == 200 and secret not in roles.text
        with Session(api.app.state.engine) as session:
            snapshot = snapshot_for(session, project, "extraction")
            assert from_snapshot(snapshot, tmp_path, True).key == secret
            with pytest.raises(ValueError, match="同意"):
                from_snapshot(snapshot, tmp_path, False)
        other_endpoint = post(
            api,
            route + f"/models/{p['id']}/update",
            profile_body(base_url="https://other.example/v1"),
        )
        assert other_endpoint.status_code == 200 and not other_endpoint.json()["has_api_key"]
        assert from_snapshot(snapshot, tmp_path, True).key == secret
        assert secret.encode() not in (tmp_path / "researchgraph.sqlite3").read_bytes()
        assert post(api, route + f"/models/{p['id']}/delete").status_code == 200
        assert not vault
        assert api.get("/api/v1" + route + "/models").json()["roles"]["extraction"] is None
    with client(tmp_path) as reopened:
        assert reopened.get("/api/v1" + route + "/models").json()["profiles"] == []


def test_profile_validation_and_global_sharing(tmp_path, vault):
    with client(tmp_path) as api:
        a = post(api, "/projects", {"name": "A"}, "project-a").json()["id"]
        b = post(api, "/projects", {"name": "B"}, "project-b").json()["id"]
        for url in [
            "http://remote.example/v1",
            "https://user:secret@example.com",
            "https://x/v1?key=x",
        ]:
            assert post(api, f"/projects/{a}/models", profile_body(base_url=url)).status_code == 422
        secret = "unit-credential:" + str(uuid4())
        invalid = post(
            api,
            f"/projects/{a}/models",
            profile_body(api_key=secret, parameters={"api_key": secret}),
        )
        assert invalid.status_code == 422 and secret not in invalid.text
        p = post(api, f"/projects/{a}/models", profile_body()).json()["id"]
        assert post(api, f"/projects/{b}/model-roles", {"extraction": p}).status_code == 200
        shared = api.get("/api/v1/settings/models").json()
        assert shared["profiles"][0]["id"] == p and shared["roles"]["extraction"] == p
        with Session(api.app.state.engine) as session:
            assert snapshot_for(session, a, "extraction")["id"] == p
            assert snapshot_for(session, b, "extraction")["id"] == p
        assert post(api, f"/projects/{uuid4()}/models/{p}/test").status_code == 404


def test_global_configuration_without_project_and_delete_clears_roles(tmp_path, vault):
    with client(tmp_path) as api:
        p = post(api, "/settings/models", profile_body(provider="mock", base_url="")).json()
        assert p["project_id"] is None
        selected = post(api, "/settings/model-roles", {"extraction": p["id"], "reasoning": p["id"]})
        assert selected.status_code == 200
        assert post(api, f"/settings/models/{p['id']}/test").json()["mock"]
        assert post(api, f"/settings/models/{p['id']}/delete").status_code == 200
        assert api.get("/api/v1/settings/models").json()["roles"] == {
            "extraction": None,
            "reasoning": None,
        }


@pytest.mark.parametrize("conflicting", [False, True])
def test_upgrade_preserves_profiles_credentials_and_old_roles(tmp_path, vault, conflicting):
    engine = make_engine(tmp_path)
    config = Config()
    config.set_main_option(
        "script_location",
        str(Path(__file__).parents[2] / "services/engine/researchgraph/migrations"),
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0006")
    project_ids, profile_ids = [str(uuid4()) for _ in range(2)], [str(uuid4()) for _ in range(2)]
    reference = str(uuid4())
    vault[reference] = "unit-migrated-credential"
    with Session(engine) as session, session.begin():
        for pid in project_ids:
            session.add(Project(id=pid, name="Existing project", description="", created_at=now()))
        session.flush()
        for profile_id in profile_ids:
            session.add(
                ModelProfile(
                    id=profile_id,
                    project_id=project_ids[0],
                    name="Existing model",
                    provider="compatible",
                    base_url="https://model.example/v1",
                    model="fixture",
                    parameters={},
                    credential_ref=reference,
                    secret_refs=[reference],
                    active=True,
                    updated_at=now(),
                )
            )
        session.flush()
        for index, pid in enumerate(project_ids):
            session.add(
                ModelRole(
                    project_id=pid,
                    role="extraction",
                    profile_id=profile_ids[index if conflicting else 0],
                )
            )
    engine.dispose()
    with client(tmp_path) as api:
        settings = api.get("/api/v1/settings/models").json()
        assert len(settings["profiles"]) == 2
        assert all(p["has_api_key"] for p in settings["profiles"])
        assert settings["roles"]["extraction"] == (None if conflicting else profile_ids[0])
        with Session(api.app.state.engine) as session:
            assert session.get(ModelProfile, profile_ids[0]).credential_ref == reference
            assert session.get(ModelRole, (project_ids[1], "extraction"))
            if not conflicting:
                assert (
                    from_snapshot(
                        snapshot_for(session, project_ids[1], "extraction"), tmp_path, True
                    ).key
                    == vault[reference]
                )
        assert len(api.get("/api/v1/projects").json()["items"]) == 2
    backups = list((tmp_path / "backups").glob("*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("select version_num from alembic_version").fetchone()[0] == "0006"
        assert backup.execute("select count(*) from project_model_roles").fetchone()[0] == 2


def test_connection_uses_fixed_text_not_documents(tmp_path, vault, monkeypatch):
    requests = []

    async def complete(self, prompt, data, schema):
        requests.append(data)
        return '{"ok":true}'

    monkeypatch.setattr(ConfiguredProvider, "complete", complete)
    with client(tmp_path) as api:
        project = post(api, "/projects", {"name": "Test"}).json()["id"]
        p = post(api, f"/projects/{project}/models", profile_body()).json()["id"]
        response = post(api, f"/projects/{project}/models/{p}/test")
        assert response.json()["connected"] and response.json()["valid_json"]
        assert requests == [{"purpose": "connection_test_no_paper_data"}]


@pytest.mark.skipif(os.name != "nt", reason="Windows Credential Manager")
def test_windows_credential_roundtrip_without_plaintext_file(tmp_path):
    store, ref, secret = SecretStore(tmp_path), str(uuid4()), "unit-credential:" + str(uuid4())
    try:
        store.put(ref, secret)
        assert store.get(ref) == secret
        assert not list(tmp_path.iterdir())
    finally:
        store.delete(ref)


def test_openai_request_parameter_mapping_and_secret_echo_rejection(monkeypatch):
    seen = []
    secret = "unit-credential:" + str(uuid4())

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self, *_):
            return json.dumps({"choices": [{"message": {"content": secret}}]}).encode()

    class Transport:
        def open(self, request, timeout):
            seen.append(json.loads(request.data))
            return Response()

    monkeypatch.setattr("urllib.request.build_opener", lambda *_: Transport())
    provider = ConfiguredProvider(
        base_url="https://api.openai.com/v1",
        model="test",
        key=secret,
        parameters={
            "max_output_tokens": 1024,
            "temperature": None,
            "reasoning_effort": "low",
            "capabilities": {"max_output_tokens": 32768, "source": "endpoint_metadata"},
        },
        provider_name="openai",
    )
    with pytest.raises(ValueError, match="凭据"):
        provider._request("Return JSON", {}, {})
    assert seen[0]["max_completion_tokens"] == 32768 and "temperature" not in seen[0]
    assert secret not in json.dumps(seen)
