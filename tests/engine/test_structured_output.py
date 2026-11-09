import asyncio
import json

import httpx
import pytest
from researchgraph.model_adapters import new_task_parameters
from researchgraph.model_settings import from_snapshot, snapshot_for
from researchgraph.providers import ConfiguredProvider, ProviderError
from researchgraph.structured_output import (
    OPENAI_ENDPOINT,
    OPENAI_SOURCE,
    OPENAI_STRICT_MODELS,
    StructuredOutputError,
    freeze_output_policy,
    strict_schema,
)
from sqlalchemy.orm import Session
from test_engine import client, post


def model_schema():
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string", "minLength": 1, "maxLength": 80},
            "optional": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None},
        },
        "required": ["answer"],
    }


def configured(endpoint=OPENAI_ENDPOINT, model="gpt-4o-mini", name="openai", **changes):
    parameters = {"json_mode": True, **changes}
    parameters["output_policy"] = freeze_output_policy(name, endpoint, model, parameters)
    provider = ConfiguredProvider(
        base_url=endpoint, model=model, provider_name=name, parameters=parameters
    )
    provider.capabilities_checked = True
    return provider


@pytest.mark.parametrize("model", sorted(OPENAI_STRICT_MODELS))
def test_only_exact_documented_official_models_use_native_strict(model):
    provider = configured(model=model)
    body = provider._build_body("Return JSON", {}, model_schema())
    wire = body["response_format"]
    assert wire["type"] == "json_schema" and wire["json_schema"]["strict"] is True
    assert wire["json_schema"]["schema"]["required"] == ["answer", "optional"]
    assert wire["json_schema"]["schema"]["properties"]["answer"]["minLength"] == 1
    assert wire["json_schema"]["schema"]["properties"]["answer"]["maxLength"] == 80
    sent = json.loads(body["messages"][1]["content"])
    assert sent["output_schema"] == wire["json_schema"]["schema"]
    audit = provider.request_metadata["structured_output"]
    assert audit["source"] == OPENAI_SOURCE and audit["support"] == "documented"
    assert audit["automatic_fallback"] is False
    assert len(audit["source_schema_sha256"]) == len(audit["request_schema_sha256"]) == 64


@pytest.mark.parametrize(
    "name,endpoint,model",
    [
        ("compatible", "https://gateway.example/v1", "gpt-4o-mini"),
        ("compatible", OPENAI_ENDPOINT, "gpt-4o-mini"),
        ("openai", OPENAI_ENDPOINT, "gpt-4o-mini-future"),
        ("openai", OPENAI_ENDPOINT, "ft:gpt-4o-mini:personal"),
        ("openai", "https://api.openai.com.proxy.example/v1", "gpt-4o-mini"),
        ("local", "http://127.0.0.1:1234/v1", "gpt-4o-mini"),
    ],
)
def test_compatible_or_unknown_modes_request_json_without_claiming_strict(name, endpoint, model):
    provider = configured(endpoint, model, name)
    body = provider._build_body("Return JSON", {}, model_schema())
    assert body["response_format"] == {"type": "json_object"}
    audit = provider.request_metadata["structured_output"]
    assert audit["mode"] == "json_object" and audit["support"] == "requested"
    assert "request_schema_sha256" not in audit


def test_json_disabled_and_thinking_adapter_freeze_prompt_mode_without_mutation():
    endpoint, model = "https://tokenhub.tencentmaas.com/plan/v3", "deepseek-v4.1-flash"
    original = {"json_mode": True}
    parameters = new_task_parameters(endpoint, model, original, "reasoning")
    policy = freeze_output_policy("compatible", endpoint, model, parameters)
    assert policy["mode"] == "prompt" and "thinking" in policy["reason"]
    provider = configured(endpoint, model, "compatible", **parameters)
    body = provider._build_body("Return JSON", {}, model_schema())
    assert "response_format" not in body and body["thinking"]["type"] == "enabled"
    assert provider.request_metadata["structured_output"]["support"] == "disabled"
    assert original == {"json_mode": True}
    assert (
        freeze_output_policy("local", "http://localhost/v1", "fixture", {"json_mode": False})[
            "mode"
        ]
        == "prompt"
    )


@pytest.mark.parametrize(
    "field,value", [("endpoint", "https://elsewhere.example/v1"), ("model", "x")]
)
def test_frozen_policy_endpoint_and_model_mismatch_stop_before_request(field, value):
    provider = configured()
    provider.parameters["output_policy"][field] = value
    with pytest.raises(ProviderError) as caught:
        provider._build_body("JSON", {}, model_schema())
    assert caught.value.category == "structured_output_unsupported"


def test_strict_policy_cannot_be_forged_for_unknown_gateway():
    provider = configured("https://gateway.example/v1", "gpt-4o-mini", "compatible")
    provider.parameters["output_policy"].update(
        mode="native_json_schema", support="documented", source=OPENAI_SOURCE
    )
    with pytest.raises(ProviderError) as caught:
        provider._build_body("JSON", {}, model_schema())
    assert caught.value.category == "structured_output_unsupported"


def test_thinking_conflict_does_not_silently_remove_native_format():
    provider = configured(reasoning_effort="high")
    with pytest.raises(ProviderError) as caught:
        provider._build_body("JSON", {}, model_schema())
    assert caught.value.category == "structured_output_unsupported"
    provider = configured(reasoning_effort="none")
    assert "reasoning_effort" not in provider._build_body("JSON", {}, model_schema())


@pytest.mark.parametrize("keyword", ["allOf", "not", "if", "patternProperties", "unknownKeyword"])
def test_unknown_or_unsupported_schema_constraints_are_rejected_instead_of_dropped(keyword):
    schema = model_schema()
    schema["properties"]["answer"][keyword] = {}
    with pytest.raises(StructuredOutputError):
        strict_schema(schema)


def test_nonexclusive_oneof_and_open_object_are_not_silently_relaxed():
    schema = model_schema()
    schema["properties"]["answer"] = {"oneOf": [{"type": "string"}, {"type": "string"}]}
    with pytest.raises(StructuredOutputError, match="互斥"):
        strict_schema(schema)
    schema = model_schema()
    schema["additionalProperties"] = True
    with pytest.raises(StructuredOutputError, match="额外字段"):
        strict_schema(schema)


def test_legacy_tasks_keep_original_request_mode_and_schema():
    schema = model_schema()
    provider = ConfiguredProvider(
        base_url=OPENAI_ENDPOINT, model="gpt-4o-mini", provider_name="openai", parameters={}
    )
    body = provider._build_body("JSON", {}, schema)
    assert body["response_format"] == {"type": "json_object"}
    assert json.loads(body["messages"][1]["content"])["output_schema"] == schema
    assert "structured_output" not in provider.request_metadata


def test_new_snapshot_freezes_mode_and_profile_cannot_inject_strict(tmp_path):
    with client(tmp_path) as api:
        project = post(api, "/projects", {"name": "Output policy"}).json()["id"]
        forged = freeze_output_policy("openai", OPENAI_ENDPOINT, "gpt-4o-mini", {})
        profile = post(
            api,
            "/settings/models",
            {
                "name": "Gateway",
                "provider": "compatible",
                "base_url": "https://gateway.example/v1",
                "model": "gpt-4o-mini",
                "parameters": {"output_policy": forged},
            },
        ).json()
        assert profile["parameters"]["output_policy"] is None
        assert post(api, "/settings/model-roles", {"extraction": profile["id"]}).status_code == 200
        with Session(api.app.state.engine) as session:
            snapshot = snapshot_for(session, project, "extraction")
        assert snapshot["parameters"]["output_policy"]["mode"] == "json_object"
        provider = from_snapshot(snapshot, tmp_path, True)
        assert provider.parameters["output_policy"] == snapshot["parameters"]["output_policy"]


def test_rejected_native_schema_is_not_resent_as_json_mode(monkeypatch):
    requests = []

    async def response(request):
        requests.append(json.loads(request.content))
        return httpx.Response(400, json={"error": {"message": "unsupported schema"}})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(**kw, transport=httpx.MockTransport(response))
    )
    provider = configured()
    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.complete("JSON", {}, model_schema()))
    assert caught.value.category == "client" and len(requests) == 1
    assert requests[0]["response_format"]["json_schema"]["strict"] is True


def test_unsupported_schema_stops_before_model_transport(monkeypatch):
    def forbidden_transport(**kwargs):
        raise AssertionError("No provider request should be created")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden_transport)
    schema = model_schema()
    schema["properties"]["answer"]["allOf"] = []
    with pytest.raises(ProviderError) as caught:
        asyncio.run(configured().complete("JSON", {}, schema))
    assert caught.value.category == "structured_output_unsupported"


@pytest.mark.parametrize("streaming,include_content", [(False, False), (False, True), (True, True)])
def test_native_refusal_is_distinct_and_never_saved_as_scientific_content(
    monkeypatch, streaming, include_content
):
    requests = []

    async def response(request):
        requests.append(request)
        if streaming:
            data = {
                "choices": [{"delta": {"refusal": "private refusal text"}, "finish_reason": "stop"}]
            }
            wire = "data: " + json.dumps(data) + "\n\ndata: [DONE]\n\n"
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=wire)
        message = {"refusal": "private refusal text"}
        if include_content:
            message["content"] = None
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": message,
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(**kw, transport=httpx.MockTransport(response))
    )
    provider = configured()
    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.complete("JSON", {}, model_schema()))
    assert caught.value.category == "structured_output_refused" and len(requests) == 1
    assert "private refusal text" not in str(caught.value)
    assert "private refusal text" not in str(provider.request_metadata)


@pytest.mark.parametrize("has_policy", [False, True])
def test_content_filter_uses_new_distinct_failure_without_changing_legacy_stream(
    monkeypatch, has_policy
):
    async def response(request):
        data = {"choices": [{"delta": {}, "finish_reason": "content_filter"}]}
        wire = "data: " + json.dumps(data) + "\n\ndata: [DONE]\n\n"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=wire)

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(**kw, transport=httpx.MockTransport(response))
    )
    provider = configured()
    if not has_policy:
        del provider.parameters["output_policy"]
    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.complete("JSON", {}, model_schema()))
    assert caught.value.category == (
        "structured_output_refused" if has_policy else "incomplete_stream"
    )
