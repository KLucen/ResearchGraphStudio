import asyncio
import base64
import json

import httpx
import pytest
from researchgraph.core import KnowledgeError
from researchgraph.translation_bridge import TranslationBridge, output_names


def test_bridge_exact_protocol_without_upstream_credentials(monkeypatch):
    requests = []
    real_client = httpx.AsyncClient

    def handler(request):
        requests.append(request)
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "version": "4.1.8"})
        if request.url.path == "/api/tasks":
            return httpx.Response(200, json={"status": "success", "tasks": []})
        if request.url.path == "/translate":
            return httpx.Response(200, json={"status": "accepted", "taskId": "task"})
        return httpx.Response(404)

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)
    )

    async def run():
        bridge = TranslationBridge("http://127.0.0.1:8890")
        health = await bridge.check()
        assert health.available and health.version == "4.1.8"
        response = await bridge.submit(
            b"%PDF-test",
            "rg-synthetic",
            "http://127.0.0.1:12345/v1",
            "ephemeral-token",
            "selected-model",
        )
        assert response["taskId"] == "task"

    asyncio.run(run())
    body = json.loads(requests[-1].content)
    assert base64.b64decode(body["fileContent"]) == b"%PDF-test"
    assert body["engine"] == "pdf2zh_next" and body["next_service"] == "openai"
    assert body["ignoreCache"] is True and body["disableGlossary"] is True
    assert body["noWatermark"] is True and body["dualMode"] == "LR"
    assert body["llm_api"]["apiKey"] == "ephemeral-token"
    assert body["llm_api"]["apiUrl"] == "http://127.0.0.1:12345/v1"


@pytest.mark.parametrize("version", ["4.1.7", "4.2.0", None])
def test_bridge_rejects_unverified_versions(monkeypatch, version):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real_client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json={"status": "ok", "version": version})
            ),
            **kw,
        ),
    )
    health = asyncio.run(TranslationBridge("http://127.0.0.1:8890").check())
    assert health.available is False


def test_bridge_refuses_redirects_and_traversal(monkeypatch):
    real_client = httpx.AsyncClient
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://example.invalid"})

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)
    )
    bridge = TranslationBridge("http://127.0.0.1:8890")
    assert asyncio.run(bridge.check()).available is False
    assert len(requests) == 1
    with pytest.raises(KnowledgeError):
        asyncio.run(bridge.download("../private.pdf"))
    assert len(requests) == 1


def test_output_names_require_audited_task_stem_and_modes():
    stem = "rg-test"
    valid = [stem + ".no_watermark.zh-CN.mono.pdf", stem + ".no_watermark.zh-CN.LR_dual.pdf"]
    assert set(output_names({"result": {"fileList": valid}}, stem)) == {"mono", "dual"}
    with pytest.raises(KnowledgeError):
        output_names({"fileList": ["../../file.pdf", valid[0]]}, stem)
    with pytest.raises(KnowledgeError):
        output_names({"fileList": valid}, "rg-another")


@pytest.mark.parametrize("operation", ["health", "submit", "poll", "download"])
def test_guard_rejection_prevents_each_operation_from_sending_http(monkeypatch, operation):
    requests = []
    real_client = httpx.AsyncClient

    def forbidden(request):
        requests.append(request)
        pytest.fail("lost ownership must prevent HTTP requests")

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(forbidden), **kw),
    )
    rejected = KnowledgeError("TRANSLATION_RUNTIME_OWNERSHIP_LOST", "synthetic owner lost")

    async def guard():
        raise rejected

    async def run():
        bridge = TranslationBridge("http://127.0.0.1:8890", before_request=guard)
        with pytest.raises(KnowledgeError) as caught:
            if operation == "health":
                await bridge.check()
            elif operation == "submit":
                await bridge.submit(b"%PDF-synthetic", "rg-task", "http://127.0.0.1:1/v1", "t", "m")
            elif operation == "poll":
                await bridge.poll("synthetic-task")
            else:
                await bridge.download("rg-task.no_watermark.zh-CN.mono.pdf")
        assert caught.value is rejected
        assert requests == []

    asyncio.run(run())


@pytest.mark.parametrize("operation", ["health", "poll"])
def test_guard_runs_again_before_tasks_or_history_fallback_http(monkeypatch, operation):
    requests = []
    calls = []
    real_client = httpx.AsyncClient
    rejected = KnowledgeError("TRANSLATION_RUNTIME_OWNERSHIP_LOST", "synthetic replacement")

    def handler(request):
        requests.append(request.url.path)
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "version": "4.1.8"})
        assert request.url.path == "/api/tasks"
        return httpx.Response(200, json={"status": "success", "tasks": []})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )

    async def guard():
        calls.append(True)
        if len(calls) == 2:
            raise rejected

    async def run():
        bridge = TranslationBridge("http://127.0.0.1:8890", before_request=guard)
        with pytest.raises(KnowledgeError) as caught:
            if operation == "health":
                await bridge.check()
            else:
                await bridge.poll("synthetic-task")
        assert caught.value is rejected
        assert requests == (["/health"] if operation == "health" else ["/api/tasks"])
        assert len(calls) == 2

    asyncio.run(run())


@pytest.mark.parametrize("mode", ["dual", "mono", "both"])
def test_bridge_sends_generation_flags_and_requires_only_selected_files(monkeypatch, mode):
    requests = []
    real_client = httpx.AsyncClient

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"status": "accepted", "taskId": "synthetic"})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    bridge = TranslationBridge("http://127.0.0.1:8890")
    asyncio.run(
        bridge.submit(b"synthetic", "rg-mode", "http://127.0.0.1:1/v1", "t", "m", output_mode=mode)
    )
    body = json.loads(requests[0].content)
    expected = {"mono", "dual"} if mode == "both" else {mode}
    assert body["mono"] == ("mono" in expected)
    assert body["dual"] == ("dual" in expected)
    assert body["noMono"] == ("mono" not in expected)
    assert body["noDual"] == ("dual" not in expected)
    names = {
        "mono": "rg-mode.no_watermark.zh-CN.mono.pdf",
        "dual": "rg-mode.no_watermark.zh-CN.LR_dual.pdf",
    }
    assert (
        set(
            output_names(
                {"fileList": [names[kind] for kind in expected]}, "rg-mode", output_mode=mode
            )
        )
        == expected
    )
    # An engine may return an additional unrequested file. It is neither used
    # nor downloaded, and cannot substitute for a missing requested output.
    assert (
        set(output_names({"fileList": list(names.values())}, "rg-mode", output_mode=mode))
        == expected
    )
    with pytest.raises(KnowledgeError):
        output_names({"fileList": []}, "rg-mode", output_mode=mode)


def test_private_service_token_is_sent_for_every_request_and_version_is_bound(monkeypatch):
    requests = []
    real_client = httpx.AsyncClient

    def handler(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer synthetic-private-ticket"
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "version": "synthetic-bundled-1"})
        if request.url.path == "/api/tasks":
            return httpx.Response(200, json={"status": "success", "tasks": []})
        if request.url.path == "/api/history":
            return httpx.Response(200, json={"status": "success", "history": []})
        if request.url.path == "/translate":
            return httpx.Response(200, json={"status": "accepted", "taskId": "synthetic"})
        return httpx.Response(200, content=b"%PDF-synthetic")

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )

    async def run():
        bridge = TranslationBridge(
            "http://127.0.0.1:8890",
            service_token="synthetic-private-ticket",
            expected_version="synthetic-bundled-1",
        )
        assert (await bridge.check()).available
        await bridge.submit(b"synthetic", "rg-mode", "http://127.0.0.1:1/v1", "t", "m")
        assert await bridge.poll("synthetic") is None
        assert await bridge.download("synthetic.pdf") == b"%PDF-synthetic"

    asyncio.run(run())
    assert len(requests) == 6
