import asyncio
import json

import httpx
import pytest
from researchgraph.model_adapters import new_task_parameters
from researchgraph.providers import ConfiguredProvider, ProviderError


def event(delta=None, finish=None, usage=None):
    value = {"choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}]}
    if usage is not None:
        value["usage"] = usage
    return ("data: " + json.dumps(value, ensure_ascii=False) + "\n\n").encode()


class Bytes(httpx.AsyncByteStream):
    def __init__(self, parts):
        self.parts, self.closed = parts, False

    async def __aiter__(self):
        for part in self.parts:
            if isinstance(part, Exception):
                raise part
            yield part

    async def aclose(self):
        self.closed = True


def provider_with_stream(monkeypatch, parts, *, key=""):
    stream = Bytes(parts)
    requests = []

    async def response(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(**kw, transport=httpx.MockTransport(response))
    )
    provider = ConfiguredProvider(base_url="https://model.example/v1", model="test", key=key)
    provider.capabilities_checked = True
    return provider, stream, requests


def test_sse_utf8_chunks_reasoning_and_last_content_usage(monkeypatch):
    usage = {
        "prompt_tokens": 12,
        "completion_tokens": 23,
        "total_tokens": 35,
        "completion_tokens_details": {"reasoning_tokens": 13},
    }
    wire = (
        b": heartbeat\n\n"
        + event({"reasoning_content": "private reasoning"})
        + event({"content": '{"结果":'})
        + event({"content": '"有效"}'})
        + event(finish="stop", usage=usage)
        + b"data: [DONE]\n\n"
    )
    provider, stream, requests = provider_with_stream(monkeypatch, [bytes([b]) for b in wire])
    raw = asyncio.run(provider.complete("JSON", {}, {}))
    assert json.loads(raw) == {"结果": "有效"}
    assert provider.usage == {
        "prompt_tokens": 12,
        "completion_tokens": 23,
        "total_tokens": 35,
        "reasoning_tokens": 13,
    }
    assert provider.request_metadata["reasoning_characters"] == len("private reasoning")
    assert provider.request_metadata["finish_reason"] == "stop"
    assert "private reasoning" not in str(provider.request_metadata)
    assert requests[0]["stream"] is True and requests[0]["stream_options"]["include_usage"]
    assert stream.closed


@pytest.mark.parametrize(
    "ending,category",
    [
        ([], "incomplete_stream"),
        ([httpx.ReadTimeout("private diagnostic")], "timeout"),
        ([httpx.ReadError("private diagnostic")], "incomplete_stream"),
        ([event(finish="length"), b"data: [DONE]\n\n"], "output_limit"),
    ],
)
def test_incomplete_stream_never_returns_json_and_preserves_safe_partial(
    monkeypatch, ending, category
):
    provider, stream, requests = provider_with_stream(
        monkeypatch, [event({"content": '{"partial":'}), *ending]
    )
    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.complete("JSON", {}, {}))
    assert caught.value.category == category
    if category == "output_limit":
        assert provider.request_metadata["finish_reason"] == "length"
    assert "private diagnostic" not in str(caught.value)
    assert provider.partial_output == '{"partial":'
    assert len(requests) == 1 and stream.closed


def test_secret_split_between_deltas_is_never_preserved(monkeypatch):
    provider, _, _ = provider_with_stream(
        monkeypatch,
        [event({"content": "synthetic-"}), event({"content": "secret"})],
        key="synthetic-secret",
    )
    with pytest.raises(ProviderError):
        asyncio.run(provider.complete("JSON", {}, {}))
    assert provider.partial_output is None


def test_stream_envelope_overhead_does_not_reduce_text_budget(monkeypatch):
    parts = [event({"content": "x"})] * 24000
    provider, stream, _ = provider_with_stream(
        monkeypatch, [*parts, event(finish="stop"), b"data: [DONE]\n\n"]
    )
    assert asyncio.run(provider.complete("JSON", {}, {})) == "x" * 24000
    assert provider.request_metadata["response_bytes"] > 2_000_000 and stream.closed


def test_stream_text_still_has_a_separate_size_limit(monkeypatch):
    provider, stream, _ = provider_with_stream(
        monkeypatch, [event({"content": "x" * 1_000_001})] * 2
    )
    with pytest.raises(ProviderError, match="文本超过"):
        asyncio.run(provider.complete("JSON", {}, {}))
    assert stream.closed and len(provider.partial_output) == 1_000_001


def test_partial_endpoint_metadata_retains_documented_other_limit(monkeypatch):
    endpoint = "https://tokenhub.tencentmaas.com/plan/v3"
    provider = ConfiguredProvider(base_url=endpoint, model="deepseek-v4.1-flash")
    original = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"data": [{"id": provider.model, "max_output_tokens": 8192}]}
        )
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: original(**kw, transport=transport))
    asyncio.run(provider.prepare())
    assert provider.capabilities.max_output_tokens == 8192
    assert provider.capabilities.context_window == 1_000_000
    assert "endpoint_metadata" in provider.capabilities.source


def test_continuous_heartbeats_cannot_extend_total_deadline(monkeypatch):
    class Heartbeat(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            while True:
                yield b": heartbeat\n\n"
                await asyncio.sleep(0.01)

        async def aclose(self):
            self.closed = True

    stream = Heartbeat()

    async def response(request):
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(**kw, transport=httpx.MockTransport(response))
    )
    monkeypatch.setattr(ConfiguredProvider, "total_timeout", property(lambda _: 0.05))
    provider = ConfiguredProvider(base_url="https://model.example/v1", model="test")
    provider.capabilities_checked = True
    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.complete("JSON", {}, {}))
    assert caught.value.timeout_phase == "total" and stream.closed


def test_tencent_documented_limits_and_new_task_modes_preserve_frozen_settings():
    endpoint, model = "https://tokenhub.tencentmaas.com/plan/v3", "deepseek-v4.1-flash"
    original = {"reasoning_effort": None, "json_mode": True, "timeout_seconds": 90}
    for role, thinking, budget in [
        ("extraction", "disabled", 393216),
        ("reasoning", "enabled", 393216),
    ]:
        params = new_task_parameters(endpoint, model, original, role)
        provider = ConfiguredProvider(base_url=endpoint, model=model, parameters=params)
        body = provider._build_body("JSON", {}, {})
        assert provider.capabilities.context_window == 1_000_000
        assert provider.capabilities.max_output_tokens == 393216
        assert body["thinking"]["type"] == thinking and body["max_tokens"] == budget
        assert ("response_format" in body) == (role == "extraction")
        assert "reasoning_effort" not in body
        assert provider.total_timeout == 180
    assert original == {"reasoning_effort": None, "json_mode": True, "timeout_seconds": 90}
    old = ConfiguredProvider(base_url=endpoint, model=model, parameters=original)._build_body(
        "JSON", {}, {}
    )
    assert "thinking" not in old and "reasoning_effort" not in old


@pytest.mark.parametrize(
    "host",
    ["https://unrelated.example/v1", "https://tokenhub.tencentmaas.com.evil.example/plan/v3"],
)
def test_model_alias_does_not_activate_vendor_adapter_on_other_endpoints(host):
    params = new_task_parameters(
        host, "deepseek-v4.1-flash", {"reasoning_effort": None}, "extraction"
    )
    provider = ConfiguredProvider(base_url=host, model="deepseek-v4.1-flash", parameters=params)
    assert provider.capabilities.max_output_tokens is None
    assert "thinking" not in provider._build_body("JSON", {}, {})


@pytest.mark.parametrize(
    "effort,expected", [("low", "high"), ("medium", "high"), ("xhigh", "max"), ("max", "max")]
)
def test_tencent_effort_mapping_is_explicit_and_lower_endpoint_limit_wins(effort, expected):
    endpoint, model = "https://tokenhub.tencentmaas.com/plan/v3", "deepseek-v4.1-flash"
    params = new_task_parameters(
        endpoint,
        model,
        {
            "reasoning_effort": effort,
            "json_mode": True,
            "capabilities": {
                "max_output_tokens": 8192,
                "context_window": 131072,
                "source": "endpoint_metadata",
            },
        },
        "extraction",
    )
    body = ConfiguredProvider(base_url=endpoint, model=model, parameters=params)._build_body(
        "JSON", {}, {}
    )
    assert body["thinking"]["reasoning_effort"] == expected
    assert body["max_tokens"] == 8192 and "response_format" not in body
