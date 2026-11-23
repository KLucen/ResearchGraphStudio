import asyncio
import json
import os
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from researchgraph.credentials import CredentialError, SecretStore
from researchgraph.model_capabilities import ModelCapabilities, parse_capabilities
from researchgraph.model_settings import ModelParameters, ModelProfile, from_snapshot, snapshot_for
from researchgraph.models import Job, now
from researchgraph.providers import ConfiguredProvider, ProviderError, require_document_capability
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


@pytest.mark.parametrize("stored_policy", [None, "legacy", "activity"])
def test_new_task_timeout_policy_is_frozen_without_rewriting_old_profile(
    tmp_path, vault, stored_policy
):
    with client(tmp_path) as api:
        project = post(api, "/projects", {"name": "Activity timeout"}).json()["id"]
        saved = post(api, "/settings/models", profile_body())
        assert saved.status_code == 200, saved.text
        profile_id = saved.json()["id"]
        assert (
            post(
                api,
                "/settings/model-roles",
                {
                    "extraction": profile_id,
                    "knowledge_extract": profile_id,
                    "knowledge_connect": profile_id,
                    "document_parse": profile_id,
                },
            ).status_code
            == 200
        )
        with Session(api.app.state.engine) as session, session.begin():
            profile = session.get(ModelProfile, profile_id)
            original = {
                key: value
                for key, value in profile.parameters.items()
                if key != "text_timeout_policy"
            }
            if stored_policy is not None:
                original["text_timeout_policy"] = stored_policy
            profile.parameters = original
        with Session(api.app.state.engine) as session:
            for role in ("extraction", "knowledge_extract", "knowledge_connect", "document_parse"):
                frozen = snapshot_for(session, project, role)
                assert frozen["parameters"]["text_timeout_policy"] == (stored_policy or "activity")
                if role == "document_parse":
                    active = from_snapshot(frozen, tmp_path, True)
                    assert active.document_timeout == 600 and active.document_total_timeout == 1800
            assert session.get(ModelProfile, profile_id).parameters == original
        # A historical snapshot is consumed as saved, independently of new defaults.
        frozen["parameters"] = {**original}
        frozen["parameters"].pop("text_timeout_policy", None)
        historical = from_snapshot(frozen, tmp_path, True)
        assert "text_timeout_policy" not in historical.parameters
        assert historical.total_timeout == 180


def test_timeout_policy_rejects_unknown_values():
    with pytest.raises(ValidationError):
        ModelParameters(text_timeout_policy="unknown")


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
        assert secret in vault.values()
        archived = api.get("/api/v1/archive?kind=model_connection").json()["items"][0]
        profile = api.get("/api/v1/archive?kind=model_profile").json()["items"][0]
        assert api.delete(f"/api/v1/archive/{profile['id']}").status_code == 200
        assert secret in vault.values()
        assert api.delete(f"/api/v1/archive/{archived['id']}").status_code == 200
        assert not vault
        assert api.get("/api/v1" + route + "/models").json()["roles"]["extraction"] is None
    with client(tmp_path) as reopened:
        assert reopened.get("/api/v1" + route + "/models").json()["profiles"] == []


def test_provider_purge_checks_active_snapshots_and_can_retry_vault_failure(
    tmp_path, vault, monkeypatch
):
    with client(tmp_path) as api:
        saved = post(api, "/settings/models", profile_body(api_key="synthetic-vault-value"))
        assert saved.status_code == 200, saved.text
        profile = saved.json()
        post(api, "/settings/model-roles", {"extraction": profile["id"]})
        job_id = str(uuid4())
        with Session(api.app.state.engine) as db, db.begin():
            db.add(
                Job(
                    id=job_id,
                    kind="llm_document_postprocess",
                    status="queued",
                    payload={"provider_snapshot": snapshot_for(db, None, "extraction")},
                    created_at=now(),
                    updated_at=now(),
                )
            )
        staged = post(
            api, "/archive", {"kind": "model_connection", "target_id": profile["connection_id"]}
        )
        assert staged.status_code == 200 and "synthetic-vault-value" not in staged.text
        item_id = staged.json()["id"]
        path = f"/api/v1/archive/{item_id}"
        failed = api.delete(path)
        assert (
            failed.status_code == 409
            and failed.json()["error"]["code"] == "ARCHIVE_MODEL_TASK_ACTIVE"
        )
        assert post(api, f"/archive/{item_id}/restore").status_code == 200
        assert api.get("/api/v1/settings/models").json()["roles"]["extraction"] == profile["id"]

        with Session(api.app.state.engine) as db, db.begin():
            db.get(Job, job_id).status = "succeeded"
        staged = post(
            api,
            "/archive",
            {"kind": "model_connection", "target_id": profile["connection_id"]},
            "restage-model",
        )
        item_id = staged.json()["id"]
        path = f"/api/v1/archive/{item_id}"
        with monkeypatch.context() as patch:

            def fail_vault_delete(_store, _reference):
                raise CredentialError("synthetic vault failure")

            patch.setattr(SecretStore, "delete", fail_vault_delete)
            failed = api.delete(path)
        assert failed.status_code == 409
        assert failed.json()["error"]["code"] == "ARCHIVE_CREDENTIAL_PURGE_FAILED"
        assert api.get("/api/v1/archive").json()["items"][0]["status"] == "purging"
        assert (
            post(api, f"/archive/{item_id}/restore", key="after-vault-failure").status_code == 409
        )
        assert vault
        assert api.delete(path).json()["status"] == "purged" and not vault
        assert api.get(f"/api/v1/jobs/{job_id}").json()["status"] == "succeeded"


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


def test_document_declaration_survives_save_snapshot_and_restart(tmp_path, vault):
    with client(tmp_path) as api:
        project = post(api, "/projects", {"name": "Document settings"}).json()["id"]
        text_profile = post(api, "/settings/models", profile_body(), "text-profile").json()
        document = post(
            api,
            "/settings/models",
            profile_body(
                model="document-model",
                parameters={
                    "temperature": 0.2,
                    "capabilities": {
                        "document_input": "pdf",
                        "document_transport": "chat_file",
                        "multimodal": False,
                        "context_window": 500_000,
                        "max_output_tokens": 200_000,
                        "source": "pretend_endpoint_metadata",
                    },
                },
            ),
            "document-profile",
        )
        assert document.status_code == 200, document.text
        profile = document.json()
        capabilities = profile["parameters"]["capabilities"]
        assert capabilities == {
            "document_input": "pdf",
            "document_transport": "chat_file",
            "multimodal": False,
            "context_window": None,
            "max_output_tokens": None,
            "source": "user_declared",
        }
        assert (
            post(
                api,
                "/settings/model-roles",
                {
                    "document_parse": profile["id"],
                    "reasoning": text_profile["id"],
                },
                "document-role",
            ).status_code
            == 200
        )
        with Session(api.app.state.engine) as session:
            frozen = snapshot_for(session, project, "document_parse")
            text_snapshot = snapshot_for(session, project, "reasoning")
        require_document_capability(from_snapshot(frozen, tmp_path, True), "pdf")
        with pytest.raises(ProviderError, match="未声明"):
            require_document_capability(from_snapshot(text_snapshot, tmp_path, True), "pdf")
        updated = post(
            api,
            f"/settings/models/{profile['id']}/update",
            profile_body(
                model="document-model",
                parameters={
                    "capabilities": {
                        "document_input": "text",
                        "multimodal": False,
                        "document_transport": "none",
                    }
                },
            ),
            "correct-to-text",
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["parameters"]["capabilities"]["document_input"] == "text"
        # Editing current settings does not mutate a queued task's frozen declaration.
        assert frozen["parameters"]["capabilities"]["document_input"] == "pdf"
        with Session(api.app.state.engine) as session:
            current = snapshot_for(session, project, "document_parse")
        with pytest.raises(ProviderError, match="未声明"):
            require_document_capability(from_snapshot(current, tmp_path, True), "pdf")
    with client(tmp_path) as reopened:
        saved = reopened.get("/api/v1/settings/models").json()
        assert saved["roles"]["document_parse"] == profile["id"]
        assert (
            next(item for item in saved["profiles"] if item["id"] == profile["id"])["parameters"][
                "capabilities"
            ]["document_input"]
            == "text"
        )


def test_visual_document_timeouts_survive_save_restart_and_freeze(tmp_path, vault):
    parameters = {
        "temperature": 0.3,
        "top_p": 0.8,
        "timeout_seconds": 90,
        "document_timeout_seconds": 720,
        "document_total_timeout_seconds": 2100,
        "reasoning_effort": "low",
        "capabilities": {
            "document_input": "image",
            "multimodal": True,
            "document_transport": "chat_images",
        },
    }
    with client(tmp_path) as api:
        project = post(api, "/projects", {"name": "Visual settings"}).json()["id"]
        saved = post(
            api,
            "/settings/models",
            profile_body(model="visual-model", parameters=parameters),
            "visual-profile",
        )
        assert saved.status_code == 200, saved.text
        profile_id = saved.json()["id"]
        assert (
            post(
                api,
                "/settings/model-roles",
                {"document_parse": profile_id},
                "visual-role",
            ).status_code
            == 200
        )
        with Session(api.app.state.engine) as session:
            frozen = snapshot_for(session, project, "document_parse")
        assert frozen["parameters"]["document_timeout_seconds"] == 720
        assert frozen["parameters"]["document_total_timeout_seconds"] == 2100
        assert frozen["parameters"]["timeout_seconds"] == 90
        assert frozen["parameters"]["capabilities"]["document_transport"] == "chat_images"
        updated = post(
            api,
            f"/settings/models/{profile_id}/update",
            profile_body(
                model="visual-model",
                parameters={**parameters, "document_timeout_seconds": 800},
            ),
            "visual-update",
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["parameters"]["document_timeout_seconds"] == 800
        assert frozen["parameters"]["document_timeout_seconds"] == 720
    with client(tmp_path) as reopened:
        profiles = reopened.get("/api/v1/settings/models").json()["profiles"]
        current = next(item["parameters"] for item in profiles if item["id"] == profile_id)
        assert current["document_timeout_seconds"] == 800
        assert current["document_total_timeout_seconds"] == 2100
        assert current["temperature"] == 0.3 and current["top_p"] == 0.8
        assert current["reasoning_effort"] == "low"
        assert current["capabilities"]["document_transport"] == "chat_images"
        assert current["capabilities"]["source"] == "user_declared"


def test_new_document_snapshot_defaults_do_not_change_legacy_profiles_or_snapshots(tmp_path, vault):
    with client(tmp_path) as api:
        project = post(api, "/projects", {"name": "Legacy document settings"}).json()["id"]
        saved = post(api, "/settings/models", profile_body(), "legacy-profile").json()
        profile_id = saved["id"]
        assert (
            post(
                api,
                "/settings/model-roles",
                {"document_parse": profile_id, "reasoning": profile_id},
                "legacy-roles",
            ).status_code
            == 200
        )
        legacy_parameters = {"timeout_seconds": 90, "json_mode": True}
        with Session(api.app.state.engine) as session, session.begin():
            stored = session.get(ModelProfile, profile_id)
            assert stored is not None
            stored.parameters = dict(legacy_parameters)
        legacy_snapshot = {
            "provider": "compatible",
            "base_url": "https://models.example/v1",
            "model": "test-model",
            "parameters": dict(legacy_parameters),
        }
        with Session(api.app.state.engine) as session:
            document = snapshot_for(session, project, "document_parse")
            text = snapshot_for(session, project, "reasoning")
            stored = session.get(ModelProfile, profile_id)
            assert stored is not None and stored.parameters == legacy_parameters
        assert document["parameters"]["document_timeout_seconds"] == 600
        assert document["parameters"]["document_total_timeout_seconds"] == 1800
        assert "document_timeout_seconds" not in text["parameters"]
        old_provider = from_snapshot(legacy_snapshot, tmp_path, True)
        assert old_provider.parameters == legacy_parameters
        assert old_provider.total_timeout == 180
        assert legacy_snapshot["parameters"] == legacy_parameters


@pytest.mark.parametrize(
    "parameters",
    [
        {"document_timeout_seconds": 29},
        {"document_timeout_seconds": 1801},
        {"document_total_timeout_seconds": 59},
        {"document_total_timeout_seconds": 3601},
        {"document_timeout_seconds": 700, "document_total_timeout_seconds": 600},
    ],
)
def test_document_timeout_validation_rejects_invalid_limits(parameters):
    with pytest.raises(ValidationError):
        ModelParameters.model_validate(parameters)


def test_visual_transport_requires_explicit_visual_capabilities():
    for document_input, multimodal in [("text", False), ("pdf", True), ("image", False)]:
        with pytest.raises(ValidationError, match="图片输入和多模态"):
            ModelCapabilities(
                document_input=document_input,
                multimodal=multimodal,
                document_transport="chat_images",
            )
    metadata = parse_capabilities(
        {"input_modalities": ["text", "image"], "document_transport": "chat_images"}
    )
    assert metadata.document_input == "image" and metadata.multimodal
    assert metadata.document_transport == "none"


@pytest.mark.parametrize("declared", ["text", "pdf"])
def test_explicit_document_declaration_wins_over_metadata(monkeypatch, declared):
    requests = []

    def response(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "document-model",
                        "context_window": 128000,
                        "max_output_tokens": 8192,
                        "document_input": "image",
                        "multimodal": True,
                        "file_input": True,
                    }
                ]
            },
        )

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            **kwargs,
            transport=httpx.MockTransport(response),
        ),
    )
    provider = ConfiguredProvider(
        base_url="https://models.example/v1",
        model="document-model",
        key="",
        parameters={
            "capabilities": {
                "document_input": declared,
                "document_transport": "none" if declared == "text" else "chat_file",
                "multimodal": False,
                "source": "user_declared",
            }
        },
    )
    asyncio.run(provider.prepare())
    assert [request.method for request in requests] == ["GET"]
    assert provider.capabilities.document_input == declared
    assert not provider.capabilities.multimodal
    assert provider.capabilities.document_transport == (
        "none" if declared == "text" else "chat_file"
    )
    assert provider.capabilities.context_window == 128000
    assert provider.capabilities.max_output_tokens == 8192
    assert provider.capabilities.source.startswith("user_declared")
    if declared == "text":
        with pytest.raises(ProviderError, match="未声明"):
            require_document_capability(provider, "pdf")
    else:
        require_document_capability(provider, "pdf")


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
        for archived in api.get("/api/v1/archive?kind=model_profile").json()["items"]:
            assert api.delete(f"/api/v1/archive/{archived['id']}").status_code == 200
        assert set(vault.values()) == {old_secret, new_secret}
        staged = post(api, f"/settings/connections/{connection_view['id']}/delete")
        assert staged.status_code == 200, staged.text
        archived = api.get("/api/v1/archive?kind=model_connection").json()["items"][0]
        assert api.delete(f"/api/v1/archive/{archived['id']}").status_code == 200
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
