"""Offline document transport checks: every model response is synthetic."""

import asyncio
import base64
import json

import httpx
import pymupdf
import pytest
from researchgraph import document_transport, providers
from researchgraph.providers import ConfiguredProvider, DocumentRequestCancelled, ProviderError


def _pdf(*, pages=2, width=500, height=600):
    with pymupdf.open() as document:
        for index in range(pages):
            page = document.new_page(width=width, height=height)
            page.insert_text((40, 45), f"Synthetic page {index + 1}", fontsize=16)
            page.insert_text((40, 80), "Formula: E = mc^2", fontsize=12)
            page.insert_text((40, 110), "Table: A | B     1 | 2", fontsize=12)
        return document.tobytes()


def _provider(*, transport="chat_file", new_parameters=True):
    parameters = {
        "timeout_seconds": 90,
        "capabilities": {
            "document_input": "image" if transport == "chat_images" else "pdf",
            "multimodal": transport == "chat_images",
            "document_transport": transport,
        },
    }
    if new_parameters:
        parameters.update(document_timeout_seconds=600, document_total_timeout_seconds=1800)
    return ConfiguredProvider(
        base_url="https://synthetic.example/v1", model="synthetic-vision", parameters=parameters
    )


def _payload(raw=None):
    return {
        "modality": "pdf",
        "document_base64": base64.b64encode(raw or _pdf()).decode(),
        "file_name": "private-local-file.pdf",
        "source_snapshot": {
            "title": "Synthetic paper",
            "path": "C:/private/file.pdf",
            "file_name": "private-local-file.pdf",
        },
    }


def _response(*, finish_reason="stop"):
    return httpx.Response(
        200,
        json={
            "choices": [
                {"message": {"content": '{"synthetic": true}'}, "finish_reason": finish_reason}
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        },
    )


def _mock_client(monkeypatch, response):
    original = httpx.AsyncClient
    settings = []

    def client(**kwargs):
        settings.append(kwargs)
        return original(**kwargs, transport=httpx.MockTransport(response))

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return settings


@pytest.mark.parametrize(
    "finish,content,category",
    [("error", '{"synthetic":true}', "response"), ("stop", "  ", "empty_response")],
)
def test_document_envelope_cannot_publish_failed_or_empty_completion(
    monkeypatch, finish, content, category
):
    requests = []

    def receive(request):
        requests.append(request)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": content}, "finish_reason": finish}]}
        )

    _mock_client(monkeypatch, receive)
    provider = _provider()
    with pytest.raises(ProviderError) as error:
        asyncio.run(provider.complete_document(_payload()))
    assert error.value.category == category
    assert len(requests) == 1 and provider.partial_output is None


def test_images_send_all_pages_in_order_without_local_text_extraction(monkeypatch):
    requests, progress = [], []

    def no_local_text(*_args, **_kwargs):
        raise AssertionError("The model input must not use local text extraction")

    monkeypatch.setattr(pymupdf.Page, "get_text", no_local_text)

    def receive(request):
        requests.append(request)
        return _response()

    settings = _mock_client(monkeypatch, receive)
    provider = _provider(transport="chat_images")
    result = asyncio.run(
        provider.complete_document(
            _payload(), on_progress=lambda stage, info: progress.append((stage, info))
        )
    )
    assert result == '{"synthetic": true}' and len(requests) == 1
    body = json.loads(requests[0].content)
    parts = body["messages"][1]["content"]
    assert body["stream"] is False
    assert [part["type"] for part in parts] == ["text", "text", "image_url", "text", "image_url"]
    assert "第 1 页 / 共 2 页" in parts[1]["text"]
    assert "第 2 页 / 共 2 页" in parts[3]["text"]
    for part in (parts[2], parts[4]):
        encoded = part["image_url"]["url"].split(",", 1)[1]
        assert base64.b64decode(encoded).startswith(b"\xff\xd8")
    serialized = json.dumps(body, ensure_ascii=False)
    assert "private-local-file.pdf" not in serialized and "C:/private" not in serialized
    assert settings[0]["timeout"].read == 600 and settings[0]["timeout"].connect == 15
    assert settings[0]["trust_env"] is False
    assert provider.document_total_timeout == 1800
    assert provider.request_metadata["request_bytes"] == len(requests[0].content)
    assert provider.request_metadata["response_bytes"] > 0
    assert provider.request_metadata["page_count"] == 2
    assert provider.request_metadata["phase"] == "completed"
    assert provider.usage["total_tokens"] == 3
    assert any(
        stage == "document_rendering" and info.get("rendered_pages") == 2
        for stage, info in progress
    )


@pytest.mark.parametrize("old", [True, False])
def test_file_transport_preserves_old_timeout_snapshot(monkeypatch, old):
    requests = []
    settings = _mock_client(monkeypatch, lambda req: requests.append(req) or _response())
    provider = _provider(new_parameters=not old)
    asyncio.run(provider.complete_document(_payload()))
    assert settings[0]["timeout"].read == (90 if old else 600)
    assert provider.document_total_timeout == (180 if old else 1800)
    assert json.loads(requests[0].content)["messages"][1]["content"][1]["type"] == "file"


@pytest.mark.parametrize(
    ("error_type", "phase", "label", "seconds"),
    [
        (httpx.ConnectTimeout, "connection", "建立连接", 15),
        (httpx.ReadTimeout, "response_headers", "等待模型响应", 600),
        (httpx.WriteTimeout, "request_write", "上传文档", 600),
        (httpx.PoolTimeout, "connection_pool", "等待连接", 600),
    ],
)
def test_timeout_diagnostics_distinguish_failures_without_sensitive_data(
    monkeypatch, error_type, phase, label, seconds
):
    def fail(request):
        raise error_type("secret-upstream-error /private/path", request=request)

    _mock_client(monkeypatch, fail)
    provider = _provider()
    with pytest.raises(ProviderError, match=label) as error:
        asyncio.run(provider.complete_document(_payload()))
    assert error.value.timeout_phase == phase
    assert f"{seconds} 秒" in str(error.value)
    assert provider.request_metadata["timeout_phase"] == phase
    assert provider.request_metadata["timeout_type"] == error_type.__name__
    assert provider.request_metadata["elapsed_seconds"] >= 0
    assert "secret-upstream-error" not in str(error.value)
    assert "private" not in json.dumps(provider.request_metadata)


def test_total_deadline_is_separate_and_stops_without_retry(monkeypatch):
    calls = []

    async def slow(request):
        calls.append(request)
        await asyncio.sleep(0.2)
        return _response()

    _mock_client(monkeypatch, slow)
    provider = _provider()
    monkeypatch.setattr(ConfiguredProvider, "document_total_timeout", property(lambda _: 0.1))
    with pytest.raises(ProviderError, match="总时限") as error:
        asyncio.run(provider.complete_document(_payload()))
    assert len(calls) == 1 and error.value.timeout_phase == "total"
    assert provider.request_metadata["timeout_type"] == "TotalTimeout"


def test_document_rate_limit_keeps_only_safe_delay_without_a_second_attempt(monkeypatch):
    calls = []
    private = "upstream-private-error-contents"

    def limited(request):
        calls.append(request.method)
        return httpx.Response(429, headers={"Retry-After": "64"}, text=private)

    _mock_client(monkeypatch, limited)
    provider = _provider()
    with pytest.raises(ProviderError) as error:
        asyncio.run(provider.complete_document(_payload()))
    assert calls == ["POST"] and error.value.category == "rate_limit"
    assert error.value.retry_after == provider.request_metadata["retry_after_seconds"] == 64
    assert provider.request_metadata["http_status"] == 429
    assert private not in str(error.value) + json.dumps(provider.request_metadata)


def test_rendering_time_counts_toward_total_deadline_before_network(monkeypatch):
    calls = []
    _mock_client(monkeypatch, lambda req: calls.append(req) or _response())
    original = document_transport.render_pdf_images

    def delayed_render(*args, **kwargs):
        import time

        time.sleep(0.03)
        return original(*args, **kwargs)

    monkeypatch.setattr(document_transport, "render_pdf_images", delayed_render)
    monkeypatch.setattr(ConfiguredProvider, "document_total_timeout", property(lambda _: 0.02))
    provider = _provider(transport="chat_images")
    with pytest.raises(ProviderError, match="总时限"):
        asyncio.run(provider.complete_document(_payload()))
    assert calls == [] and provider.request_metadata["timeout_phase"] == "total"
    assert provider.request_metadata["elapsed_seconds"] >= 0.02


def test_render_deadline_stops_before_rendering_later_pages(monkeypatch):
    from types import SimpleNamespace

    clock, rendered, calls = [100.0], [], []
    _mock_client(monkeypatch, lambda req: calls.append(req) or _response())
    monkeypatch.setattr(providers, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(ConfiguredProvider, "document_total_timeout", property(lambda _: 0.5))
    original = pymupdf.Page.get_pixmap

    def render_and_advance(page, **kwargs):
        result = original(page, **kwargs)
        rendered.append(page.number)
        clock[0] += 1
        return result

    monkeypatch.setattr(pymupdf.Page, "get_pixmap", render_and_advance)
    provider = _provider(transport="chat_images")
    with pytest.raises(ProviderError, match="页面转换达到总时限") as error:
        asyncio.run(provider.complete_document(_payload(_pdf(pages=3))))
    assert rendered == [0] and calls == []
    assert error.value.timeout_phase == "total"
    assert provider.request_metadata["elapsed_seconds"] == 1
    assert provider.request_metadata["rendered_pages"] == 1


def test_response_body_timeout_retains_received_bytes_and_trace_timing(monkeypatch):
    class BrokenResponse(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"choices":['
            raise httpx.ReadTimeout("private upstream details")

    async def response(request):
        await request.extensions["trace"]("http11.send_request_body.complete", {})
        return httpx.Response(200, stream=BrokenResponse())

    _mock_client(monkeypatch, response)
    provider = _provider()
    with pytest.raises(ProviderError, match="读取模型结果") as error:
        asyncio.run(provider.complete_document(_payload()))
    assert error.value.timeout_phase == "response_body"
    assert provider.request_metadata["response_bytes"] == len(b'{"choices":[')
    assert provider.request_metadata["response_started_seconds"] >= 0
    assert provider.request_metadata["request_sent_seconds"] >= 0


def test_response_capacity_is_bounded_before_json_decode(monkeypatch):
    _mock_client(monkeypatch, lambda _: _response())
    monkeypatch.setattr(providers, "MAX_DOCUMENT_RESPONSE_BYTES", 16)
    provider = _provider()
    with pytest.raises(ProviderError, match="安全限制"):
        asyncio.run(provider.complete_document(_payload()))
    assert provider.request_metadata["response_bytes"] > 16


@pytest.mark.parametrize("phase", ["before_render", "after_render", "client_enter"])
def test_cancelled_image_request_never_sends(monkeypatch, phase):
    active, calls = True, []
    original = httpx.AsyncClient

    def progress(_stage, info):
        nonlocal active
        if phase == "after_render" and info.get("rendered_pages") == 2:
            active = False

    class LocalClient(original):
        async def __aenter__(self):
            nonlocal active
            result = await super().__aenter__()
            if phase == "client_enter":
                active = False
            return result

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: LocalClient(
            **kw, transport=httpx.MockTransport(lambda req: calls.append(req) or _response())
        ),
    )
    if phase == "before_render":
        active = False
    with pytest.raises(DocumentRequestCancelled):
        asyncio.run(
            _provider(transport="chat_images").complete_document(
                _payload(), before_send=lambda: active, on_progress=progress
            )
        )
    assert calls == []


def test_worker_cancellation_from_render_progress_propagates_without_network(monkeypatch):
    calls = []
    _mock_client(monkeypatch, lambda req: calls.append(req) or _response())

    def stop(_stage, info):
        if info.get("rendered_pages") == 1:
            raise DocumentRequestCancelled

    with pytest.raises(DocumentRequestCancelled):
        asyncio.run(
            _provider(transport="chat_images").complete_document(_payload(), on_progress=stop)
        )
    assert calls == []


@pytest.mark.parametrize("kind", ["page_count", "page_pixels", "total_pixels", "image_bytes"])
def test_images_over_capacity_fail_before_any_network(monkeypatch, kind):
    calls = []
    _mock_client(monkeypatch, lambda req: calls.append(req) or _response())
    name = {
        "page_count": "MAX_DOCUMENT_PAGES",
        "page_pixels": "MAX_PAGE_PIXELS",
        "total_pixels": "MAX_TOTAL_PIXELS",
        "image_bytes": "MAX_IMAGE_BYTES",
    }[kind]
    monkeypatch.setattr(document_transport, name, 1)
    with pytest.raises(ProviderError, match="未发送"):
        asyncio.run(_provider(transport="chat_images").complete_document(_payload()))
    assert calls == []


def test_pdf_source_size_is_checked_before_read(monkeypatch, tmp_path):
    path = tmp_path / "oversize.pdf"
    with path.open("wb") as file:
        file.truncate(50 * 1024 * 1024 + 1)
    calls = []
    _mock_client(monkeypatch, lambda req: calls.append(req) or _response())
    with pytest.raises(ProviderError, match="50 MiB"):
        asyncio.run(_provider().complete_document({"modality": "pdf", "path": str(path)}))
    assert calls == []


def test_truncated_document_never_returns_success(monkeypatch):
    _mock_client(monkeypatch, lambda _: _response(finish_reason="length"))
    provider = _provider()
    with pytest.raises(ProviderError, match="截断"):
        asyncio.run(provider.complete_document(_payload()))
    assert provider.partial_output == '{"synthetic": true}'
    assert provider.request_metadata["finish_reason"] == "length"
    assert provider.usage["total_tokens"] == 3


def test_encrypted_or_invalid_pdf_never_sends(monkeypatch):
    calls = []
    _mock_client(monkeypatch, lambda req: calls.append(req) or _response())
    with pytest.raises(ProviderError, match="无法转换"):
        asyncio.run(_provider(transport="chat_images").complete_document(_payload(b"not-pdf")))
    assert calls == []


def test_password_protected_pdf_is_rejected_before_network(monkeypatch):
    calls = []
    _mock_client(monkeypatch, lambda req: calls.append(req) or _response())
    with pymupdf.open() as document:
        document.new_page()
        raw = document.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="synthetic", owner_pw="owner"
        )
    with pytest.raises(ProviderError, match="加密"):
        asyncio.run(_provider(transport="chat_images").complete_document(_payload(raw)))
    assert calls == []


def test_http_rejection_does_not_read_or_echo_upstream_body(monkeypatch):
    class UnreadableErrorBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise AssertionError("Do not read a rejected upstream error body")
            yield b""  # pragma: no cover

    _mock_client(monkeypatch, lambda _: httpx.Response(400, stream=UnreadableErrorBody()))
    with pytest.raises(ProviderError, match="HTTP 400") as error:
        asyncio.run(_provider().complete_document(_payload()))
    assert error.value.category == "client"
