"""Observable token activity can outlive the old total limit; heartbeats cannot."""

import asyncio
import json

import httpx
import pytest
from researchgraph.knowledge_diagnostics import knowledge_diagnostic
from researchgraph.providers import ConfiguredProvider, ProviderError
from test_chat_stream import event


def configured(monkeypatch, stream, *, content_type="text/event-stream", responder=None):
    requests = []

    async def response(request):
        requests.append(request)
        if responder:
            return await responder(request)
        return httpx.Response(200, headers={"content-type": content_type}, stream=stream)

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(**kw, transport=httpx.MockTransport(response))
    )
    provider = ConfiguredProvider(
        base_url="https://model.example/v1",
        model="synthetic",
        parameters={"timeout_seconds": 0.08, "text_timeout_policy": "activity"},
    )
    provider.capabilities_checked = True
    return provider, requests


class DelayedStream(httpx.AsyncByteStream):
    def __init__(self, parts):
        self.parts, self.closed = parts, False

    async def __aiter__(self):
        for delay, part in self.parts:
            await asyncio.sleep(delay)
            yield part

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("kind", ["content", "reasoning_content", "reasoning"])
def test_real_generation_outlives_legacy_total_deadline_without_retry(monkeypatch, kind):
    delta = {kind: "private thought" if kind != "content" else " "}
    stream = DelayedStream(
        [
            *[(0.015, event(delta)) for _ in range(12)],
            (0, event({"content": '{"ok":true}'})),
            (0, event(finish="stop")),
            (0, b"data: [DONE]\n\n"),
        ]
    )
    provider, requests = configured(monkeypatch, stream)
    monkeypatch.setattr(ConfiguredProvider, "total_timeout", property(lambda _: 0.04))
    result = asyncio.run(asyncio.wait_for(provider.complete("Return JSON", {}, {}), timeout=2))
    assert json.loads(result) == {"ok": True}
    assert provider.request_metadata["elapsed_seconds"] > provider.total_timeout
    assert provider.request_metadata["total_timeout_seconds"] is None
    assert provider.request_metadata["text_timeout_policy"] == "activity"
    assert provider.request_metadata["last_generation_kind"] == "content"
    assert "private thought" not in str(provider.request_metadata)
    assert stream.closed and len(requests) == 1


@pytest.mark.parametrize(
    "part",
    [b": heartbeat\n\n", event({}), event({"role": "assistant"}), event(usage={"total_tokens": 1})],
)
def test_heartbeat_empty_role_and_usage_cannot_hide_absent_first_generation(monkeypatch, part):
    stream = DelayedStream([(0.01, part)] * 100)
    provider, requests = configured(monkeypatch, stream)
    with pytest.raises(ProviderError) as caught:
        asyncio.run(asyncio.wait_for(provider.complete("Return JSON", {}, {}), timeout=2))
    assert caught.value.category == "timeout"
    assert caught.value.timeout_phase == "first_generation"
    assert "first_generation_seconds" not in provider.request_metadata
    assert provider.request_metadata["response_bytes"] > 0
    assert stream.closed and len(requests) == 1


def test_stall_after_visible_reasoning_and_content_preserves_partial_and_closes(monkeypatch):
    prefix = '{"ok":'
    stream = DelayedStream(
        [
            (0, event({"reasoning_content": "private thought"})),
            (0, event({"content": prefix})),
            *[(0.01, b": heartbeat\n\n") for _ in range(100)],
        ]
    )
    provider, requests = configured(monkeypatch, stream)
    with pytest.raises(ProviderError) as caught:
        asyncio.run(asyncio.wait_for(provider.complete("Return JSON", {}, {}), timeout=2))
    assert caught.value.timeout_phase == "generation_idle"
    assert provider.partial_output == prefix
    assert provider.request_metadata["reasoning_characters"] == len("private thought")
    assert provider.request_metadata["content_characters"] == len(prefix)
    diagnostic = knowledge_diagnostic(
        caught.value,
        request_sent=True,
        raw_available=False,
        provider_metadata=provider.request_metadata,
    )
    assert "停滞" in diagnostic["summary"] and "0.08 秒" in diagnostic["summary"]
    assert "private thought" not in json.dumps(diagnostic)
    assert stream.closed and len(requests) == 1


def test_first_generation_wait_starts_after_sending_even_if_headers_do_not_arrive(monkeypatch):
    async def response(request):
        await request.extensions["trace"]("http11.send_request_body.complete", {})
        await asyncio.sleep(1)
        return httpx.Response(200, json={})

    provider, requests = configured(monkeypatch, None, responder=response)
    with pytest.raises(ProviderError) as caught:
        asyncio.run(asyncio.wait_for(provider.complete("Return JSON", {}, {}), timeout=2))
    assert caught.value.timeout_phase == "first_generation"
    assert "http_status" not in provider.request_metadata
    assert provider.request_metadata["request_sent_seconds"] >= 0
    assert len(requests) == 1


def test_generation_idle_clock_does_not_count_active_request_upload(monkeypatch):
    stream = DelayedStream(
        [
            (0, event({"content": '{"ok":true}'})),
            (0, event(finish="stop")),
            (0, b"data: [DONE]\n\n"),
        ]
    )

    async def response(request):
        await request.extensions["trace"]("http11.send_request_body.started", {})
        await asyncio.sleep(0.12)
        await request.extensions["trace"]("http11.send_request_body.complete", {})
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)

    provider, requests = configured(monkeypatch, stream, responder=response)
    assert asyncio.run(provider.complete("Return JSON", {}, {})) == '{"ok":true}'
    assert provider.request_metadata["request_sent_seconds"] > 0.08
    assert stream.closed and len(requests) == 1


def test_cannot_connect_is_distinct_from_waiting_for_generation(monkeypatch):
    async def response(request):
        raise httpx.ConnectTimeout("synthetic connection failure")

    provider, requests = configured(monkeypatch, None, responder=response)
    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.complete("Return JSON", {}, {}))
    assert caught.value.timeout_phase == "connection"
    assert "first_generation_seconds" not in provider.request_metadata
    assert len(requests) == 1


def test_done_ends_response_without_waiting_for_keepalive_eof(monkeypatch):
    stream = DelayedStream(
        [
            (0, event({"content": '{"ok":true}'})),
            (0, event(finish="stop")),
            (0, b"data: [DONE]\n\n"),
            (1, b": keepalive\n\n"),
        ]
    )
    provider, requests = configured(monkeypatch, stream)
    assert asyncio.run(provider.complete("Return JSON", {}, {})) == '{"ok":true}'
    assert provider.request_metadata["finish_reason"] == "stop"
    assert stream.closed and len(requests) == 1


def test_receiving_non_sse_json_bytes_is_not_mislabeled_token_activity(monkeypatch):
    envelope = json.dumps(
        {"choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}]}
    ).encode()
    stream = DelayedStream([(0.015, envelope[n : n + 10]) for n in range(0, len(envelope), 10)])
    provider, requests = configured(monkeypatch, stream, content_type="application/json")
    monkeypatch.setattr(ConfiguredProvider, "total_timeout", property(lambda _: 0.04))
    assert asyncio.run(provider.complete("Return JSON", {}, {})) == '{"ok":true}'
    assert provider.request_metadata["last_activity_kind"] == "response_bytes"
    assert "first_generation_seconds" not in provider.request_metadata
    assert "reasoning_characters" not in provider.request_metadata
    assert stream.closed and len(requests) == 1


def test_json_whitespace_keepalive_is_not_generation_activity(monkeypatch):
    stream = DelayedStream([(0.01, b" \n\t")] * 100)
    provider, requests = configured(monkeypatch, stream, content_type="application/json")
    with pytest.raises(ProviderError) as caught:
        asyncio.run(asyncio.wait_for(provider.complete("Return JSON", {}, {}), timeout=2))
    assert caught.value.timeout_phase == "first_response_data"
    assert "last_activity_seconds" not in provider.request_metadata
    assert "first_generation_seconds" not in provider.request_metadata
    assert stream.closed and len(requests) == 1


@pytest.mark.parametrize("policy,connect", [("activity", 15), ("legacy", 5)])
def test_activity_connection_deadline_is_independent_of_idle_setting(monkeypatch, policy, connect):
    stream = DelayedStream(
        [
            (0, event({"content": '{"ok":true}'})),
            (0, event(finish="stop")),
            (0, b"data: [DONE]\n\n"),
        ]
    )
    provider, requests = configured(monkeypatch, stream)
    provider.parameters.update(timeout_seconds=5, text_timeout_policy=policy)
    asyncio.run(provider.complete("Return JSON", {}, {}))
    assert requests[0].extensions["timeout"]["connect"] == connect
    assert provider.request_metadata["connect_timeout_seconds"] == connect


def test_cancellation_closes_active_socket_and_preserves_private_partial(monkeypatch):
    stream = DelayedStream([(0, event({"content": '{"ok":'})), (1, event({"content": "true}"}))])
    provider, requests = configured(monkeypatch, stream)

    async def cancelled():
        task = asyncio.create_task(provider.complete("Return JSON", {}, {}))
        while "content_characters" not in provider.request_metadata:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(asyncio.wait_for(cancelled(), timeout=2))
    assert provider.partial_output == '{"ok":' and stream.closed
    assert len(requests) == 1


@pytest.mark.parametrize("policy", [None, "legacy"])
def test_existing_frozen_policy_keeps_historical_total_deadline(monkeypatch, policy):
    stream = DelayedStream([(0.015, event({"reasoning_content": "thinking"}))] * 100)
    provider, requests = configured(monkeypatch, stream)
    provider.parameters["text_timeout_policy"] = policy
    monkeypatch.setattr(ConfiguredProvider, "total_timeout", property(lambda _: 0.04))
    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.complete("Return JSON", {}, {}))
    assert caught.value.timeout_phase == "total"
    assert provider.request_metadata["text_timeout_policy"] == "legacy"
    assert stream.closed and len(requests) == 1
