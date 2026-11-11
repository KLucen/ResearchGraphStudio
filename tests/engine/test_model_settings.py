import json
import os
from uuid import uuid4

import pytest
from researchgraph.credentials import SecretStore
from researchgraph.model_settings import from_snapshot, snapshot_for
from researchgraph.providers import ConfiguredProvider
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
        assert secret.encode() not in (tmp_path / "researchgraph-lite.sqlite3").read_bytes()
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


def test_global_connection_test_uses_a_profile_model_without_paper_data(
    tmp_path, vault, monkeypatch
):
    requests = []

    async def complete(self, prompt, data, schema):
        requests.append(data)
        return '{"ok":true}'

    monkeypatch.setattr(ConfiguredProvider, "complete", complete)
    with client(tmp_path) as api:
        connection = post(
            api,
            "/settings/connections",
            {
                "name": "Shared gateway",
                "provider": "compatible",
                "base_url": "https://models.example/v1",
            },
            "connection-test-create",
        ).json()
        profile = post(
            api,
            "/settings/models",
            {"name": "Overview", "connection_id": connection["id"], "model": "overview"},
            "connection-test-profile",
        ).json()
        result = post(
            api,
            f"/settings/connections/{connection['id']}/test",
            key="connection-test-run",
        )
        assert result.status_code == 200, result.text
        assert result.json()["model"] == profile["model"]
        assert requests == [{"purpose": "connection_test_no_paper_data"}]


def test_connection_is_reused_by_multiple_model_profiles(tmp_path, vault):
    secret = "unit-credential:" + str(uuid4())
    with client(tmp_path) as api:
        connection = post(
            api,
            "/settings/connections",
            {
                "name": "Shared gateway",
                "provider": "compatible",
                "base_url": "https://models.example/v1",
                "api_key": secret,
            },
        )
        assert connection.status_code == 200, connection.text
        connection_view = connection.json()
        assert connection_view["has_api_key"]
        project = post(api, "/projects", {"name": "Profiles"}).json()["id"]
        profile_payload = {
            "name": "Overview model",
            "connection_id": connection_view["id"],
            "model": "overview-v1",
        }
        first = post(api, "/settings/models", profile_payload)
        second = post(
            api,
            "/settings/models",
            {**profile_payload, "name": "Reading model", "model": "reading-v1"},
        )
        assert first.status_code == 200 and second.status_code == 200
        assert first.json()["connection_id"] == second.json()["connection_id"]
        settings = api.get("/api/v1/settings/models").json()
        assert len(settings["connections"]) == 1
        assert settings["connections"][0]["has_api_key"]
        assert all("api_key" not in value for value in settings.values() if isinstance(value, str))
        # A role snapshot resolves the credential from the shared connection.
        post(api, "/settings/model-roles", {"extraction": first.json()["id"]})
        with Session(api.app.state.engine) as session:
            snapshot = snapshot_for(session, project, "extraction")
            assert snapshot["base_url"] == "https://models.example/v1"
            assert from_snapshot(snapshot, tmp_path, True).key == secret


def test_global_connection_is_reused_by_profiles_and_snapshots_are_immutable(tmp_path, vault):
    old_secret = "unit-old-credential:" + str(uuid4())
    new_secret = "unit-new-credential:" + str(uuid4())
    with client(tmp_path) as api:
        project = post(api, "/projects", {"name": "Shared connection"}).json()["id"]
        connection = post(
            api,
            "/settings/connections",
            {
                "name": "Shared gateway",
                "provider": "compatible",
                "base_url": "https://models.example/v1",
                "api_key": old_secret,
            },
        )
        assert connection.status_code == 200, connection.text
        connection_view = connection.json()
        assert connection_view["has_api_key"]
        assert old_secret not in connection.text and "credential_ref" not in connection_view

        first = post(
            api,
            f"/projects/{project}/models",
            {"name": "Fast model", "connection_id": connection_view["id"], "model": "fast"},
        )
        second = post(
            api,
            f"/projects/{project}/models",
            {"name": "Reasoning model", "connection_id": connection_view["id"], "model": "deep"},
            "second-profile",
        )
        assert first.status_code == second.status_code == 200
        assert (
            first.json()["connection_id"] == second.json()["connection_id"] == connection_view["id"]
        )
        assert first.json()["has_api_key"] and second.json()["has_api_key"]

        roles = post(
            api,
            "/settings/model-roles",
            {"extraction": first.json()["id"]},
            "shared-role",
        )
        assert roles.status_code == 200, roles.text
        with Session(api.app.state.engine) as session:
            old_snapshot = snapshot_for(session, project, "extraction")
            assert from_snapshot(old_snapshot, tmp_path, True).key == old_secret

        updated = post(
            api,
            f"/settings/connections/{connection_view['id']}/update",
            {
                "name": "Shared gateway",
                "provider": "compatible",
                "base_url": "https://models.example/v1",
                "api_key": new_secret,
            },
            "connection-update",
        )
        assert updated.status_code == 200, updated.text
        assert new_secret not in updated.text
        with Session(api.app.state.engine) as session:
            current_snapshot = snapshot_for(session, project, "extraction")
            assert from_snapshot(old_snapshot, tmp_path, True).key == old_secret
            assert from_snapshot(current_snapshot, tmp_path, True).key == new_secret

        settings = api.get("/api/v1/settings/models").json()
        assert len(settings["connections"]) == 1
        assert old_secret not in json.dumps(settings, ensure_ascii=False)
        assert new_secret not in json.dumps(settings, ensure_ascii=False)
        assert (
            post(api, f"/projects/{project}/models/{first.json()['id']}/delete").status_code == 200
        )
        assert vault
        assert new_secret in vault.values()
        assert (
            post(api, f"/projects/{project}/models/{second.json()['id']}/delete").status_code == 200
        )
        assert not vault


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
