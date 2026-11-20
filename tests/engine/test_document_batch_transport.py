"""All provider responses are local synthetic HTTP fixtures, never real models."""

import asyncio
import base64
import json

import httpx
import pymupdf
import pytest
from researchgraph import document_transport
from researchgraph.document_batch_contracts import BatchResult, BoundaryResult
from researchgraph.document_batch_transport import (
    assert_source_version,
    prepare_document,
    slice_pdf,
)
from researchgraph.document_transport import (
    DocumentRenderCancelled,
    DocumentRenderDeadline,
    DocumentRenderError,
)
from researchgraph.providers import ConfiguredProvider, DocumentRequestCancelled, ProviderError


def _pdf(pages=12, width=300, height=400):
    with pymupdf.open() as document:
        for i in range(pages):
            page = document.new_page(width=width, height=height)
            page.insert_text((30, 40), f"Anonymous page {i + 1}")
        return document.tobytes()


def _provider(transport="chat_images", **capabilities):
    return ConfiguredProvider(
        base_url="https://synthetic.example/v1",
        model="fixture-vision",
        parameters={
            "document_timeout_seconds": 600,
            "document_total_timeout_seconds": 1800,
            "capabilities": {
                "document_input": "image" if transport == "chat_images" else "pdf",
                "document_transport": transport,
                "multimodal": transport == "chat_images",
                **capabilities,
            },
        },
    )


def _mock(monkeypatch, receive):
    original = httpx.AsyncClient
    settings = []

    def create(**kwargs):
        settings.append(kwargs)
        return original(**kwargs, transport=httpx.MockTransport(receive))

    monkeypatch.setattr(httpx, "AsyncClient", create)
    return settings


def _response(content="{}", finish="stop"):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}, "finish_reason": finish}],
            "usage": {"total_tokens": 3},
        },
    )


def test_planner_uses_complete_core_pages_one_shared_page_and_no_hash(tmp_path, monkeypatch):
    path = tmp_path / "private-file.pdf"
    path.write_bytes(_pdf())
    monkeypatch.setattr(
        pymupdf.Page, "get_text", lambda *_a, **_k: pytest.fail("no text extraction")
    )
    raw, version, ranges = prepare_document(path, 5, _provider())
    assert ranges == [
        {"index": 0, "page_start": 1, "page_end": 5, "send_start": 1, "send_end": 5},
        {"index": 1, "page_start": 6, "page_end": 9, "send_start": 5, "send_end": 9},
        {"index": 2, "page_start": 10, "page_end": 12, "send_start": 9, "send_end": 12},
    ]
    assert version["page_count"] == 12 and version["size"] == len(raw)
    assert not any("hash" in k or "sha" in k or "path" in k for k in version)
    assert_source_version(path, version)
    path.write_bytes(raw + b"\n")
    with pytest.raises(DocumentRenderError, match="版本已变化"):
        assert_source_version(path, version)


def test_planner_shrinks_for_known_output_and_pixel_capacity(tmp_path, monkeypatch):
    path = tmp_path / "source.pdf"
    path.write_bytes(_pdf(8))
    _, _, ranges = prepare_document(path, 5, _provider(max_output_tokens=4096))
    assert all(x["send_end"] - x["send_start"] < 2 for x in ranges)
    monkeypatch.setattr(document_transport, "MAX_TOTAL_PIXELS", 2 * 300 * 400 * 4)
    _, _, ranges = prepare_document(path, 5, _provider())
    assert all(x["send_end"] - x["send_start"] < 2 for x in ranges)
    assert [p for x in ranges for p in range(x["page_start"], x["page_end"] + 1)] == list(
        range(1, 9)
    )


def test_planner_refuses_impossible_single_page_without_discarding_pages(tmp_path, monkeypatch):
    path = tmp_path / "source.pdf"
    path.write_bytes(_pdf(3))
    monkeypatch.setattr(document_transport, "MAX_PAGE_PIXELS", 1)
    with pytest.raises(DocumentRenderError, match="未发送或截页"):
        prepare_document(path, 5, _provider())


def test_slices_have_requested_pages_only_without_get_text(monkeypatch):
    raw = _pdf(7)
    monkeypatch.setattr(
        pymupdf.Page, "get_text", lambda *_a, **_k: pytest.fail("no text extraction")
    )
    split = slice_pdf(raw, 4, 6)
    with pymupdf.open(stream=split, filetype="pdf") as document:
        assert len(document) == 3
    with pytest.raises(DocumentRenderError):
        slice_pdf(raw, 1, 8)


@pytest.mark.parametrize("transport", ["chat_file", "chat_images"])
def test_batch_transmits_only_slice_with_original_page_context(monkeypatch, transport):
    requests = []
    _mock(monkeypatch, lambda req: requests.append(req) or _response())
    context = {
        "version": "document-batch-1",
        "task": "extract",
        "page_start": 6,
        "page_end": 9,
        "send_start": 5,
        "send_end": 9,
        "document_pages": 12,
        "private-unknown": "private-path",
    }
    asyncio.run(
        _provider(transport).complete_document(
            {
                "modality": "pdf",
                "document_base64": base64.b64encode(slice_pdf(_pdf(), 5, 9)).decode(),
                "file_name": "private-source.pdf",
                "path": "C:/private/source.pdf",
                "document_batch_context": context,
            },
            schema=BatchResult.model_json_schema(),
        )
    )
    assert len(requests) == 1
    body = json.loads(requests[0].content)
    serialized = json.dumps(body, ensure_ascii=False)
    assert "private" not in serialized
    parts = body["messages"][1]["content"]
    batch_meta = json.loads(parts[1]["text"])["document_batch_context"]
    assert batch_meta["page_start"] == 6 and batch_meta["send_start"] == 5
    if transport == "chat_images":
        labels = [x["text"] for x in parts if x["type"] == "text" and x["text"].startswith("PDF")]
        assert "第 5 页 / 共 12 页" in labels[0] and "第 9 页 / 共 12 页" in labels[-1]
    else:
        assert parts[2]["file"]["filename"] == "paper-batch.pdf"
        raw = base64.b64decode(parts[2]["file"]["file_data"].split(",", 1)[1])
        with pymupdf.open(stream=raw, filetype="pdf") as subset:
            assert len(subset) == 5


def test_boundary_prompt_only_requests_decision_with_given_segments(monkeypatch):
    requests = []
    _mock(monkeypatch, lambda req: requests.append(req) or _response())
    segment = {
        "chapter_ref": "intro",
        "chapter_title": "Intro",
        "kind": "paragraph",
        "text": "Anonymous continuation",
        "page_start": 4,
        "page_end": 4,
    }
    asyncio.run(
        _provider().complete_document(
            {
                "modality": "pdf",
                "document_base64": base64.b64encode(_pdf(2)).decode(),
                "document_batch_context": {
                    "version": "document-batch-1",
                    "task": "boundary",
                    "page_start": 4,
                    "page_end": 5,
                    "send_start": 4,
                    "send_end": 5,
                    "document_pages": 8,
                },
                "document_boundary_context": {
                    "left": segment,
                    "right": dict(segment, page_start=5, page_end=5),
                },
            },
            schema=BoundaryResult.model_json_schema(),
        )
    )
    body = json.loads(requests[0].content)
    assert "不得返回、改写" in body["messages"][0]["content"]
    context = json.loads(body["messages"][1]["content"][1]["text"])
    assert context["document_boundary_context"]["left"]["text"] == segment["text"]


@pytest.mark.parametrize("transport", ["chat_file", "chat_images"])
def test_boundary_json_mode_meets_endpoint_json_instruction_requirement(monkeypatch, transport):
    requests = []
    decision = {
        "version": "document-boundary-1",
        "action": "merge",
        "separator": "space",
        "reason": "continuation",
    }

    def receive(request):
        requests.append(request)
        body = json.loads(request.content)
        if body.get("response_format", {}).get("type") == "json_object" and (
            "json" not in json.dumps(body["messages"]).lower()
        ):
            return httpx.Response(
                400,
                json={"error": {"message": "synthetic endpoint requires JSON instruction"}},
            )
        return _response(json.dumps(decision))

    _mock(monkeypatch, receive)
    part = {
        "chapter_ref": "main",
        "chapter_title": "Main",
        "kind": "paragraph",
        "text": "Anonymous fragment",
        "page_start": 3,
        "page_end": 3,
    }
    provider = _provider(transport)
    result = asyncio.run(
        provider.complete_document(
            {
                "modality": "pdf",
                "document_base64": base64.b64encode(_pdf(2)).decode(),
                "document_batch_context": {
                    "version": "document-batch-1",
                    "task": "boundary",
                    "page_start": 3,
                    "page_end": 4,
                    "send_start": 3,
                    "send_end": 4,
                    "document_pages": 7,
                },
                "document_boundary_context": {
                    "left": part,
                    "right": dict(part, page_start=4, page_end=4),
                },
            },
            BoundaryResult.model_json_schema(),
        )
    )
    assert json.loads(result) == decision and len(requests) == 1
    body = json.loads(requests[0].content)
    assert body["response_format"] == {"type": "json_object"}
    assert "JSON" in body["messages"][0]["content"]
    assert body["stream"] is False
    assert provider.request_metadata["boundary_prompt_version"] == 2


def test_repair_is_one_text_request_with_document_timeouts_and_no_pdf(monkeypatch):
    requests, progress = [], []
    settings = _mock(monkeypatch, lambda req: requests.append(req) or _response("{}"))
    provider = _provider()
    result = asyncio.run(
        provider.repair_document_format(
            '{"version":"wrong"}',
            BatchResult.model_json_schema(),
            [{"path": "segments[3].kind", "code": "literal_error"}],
            on_progress=lambda stage, info: progress.append((stage, info)),
        )
    )
    assert result == "{}" and len(requests) == 1
    body = json.loads(requests[0].content)
    assert isinstance(body["messages"][1]["content"], str)
    text = json.dumps(body, ensure_ascii=False)
    assert "data:application/pdf" not in text and "image_url" not in text
    assert body["stream"] is False and settings[0]["timeout"].read == 600
    assert provider.request_metadata["transport"] == "chat-document-repair-v1"
    assert provider.request_metadata["total_timeout_seconds"] == 1800
    assert provider.usage["total_tokens"] == 3 and progress


def test_repair_cancel_and_timeout_never_retries(monkeypatch):
    requests = []

    def fail(req):
        requests.append(req)
        raise httpx.ReadTimeout("private", request=req)

    _mock(monkeypatch, fail)
    provider = _provider()
    with pytest.raises(DocumentRequestCancelled):
        asyncio.run(provider.repair_document_format("{}", {}, [], before_send=lambda: False))
    assert requests == []
    with pytest.raises(ProviderError, match="等待模型响应超时"):
        asyncio.run(provider.repair_document_format("{}", {}, []))
    assert len(requests) == 1


def test_repair_rejects_unsupported_strict_policy_before_network(monkeypatch):
    requests = []
    _mock(monkeypatch, lambda req: requests.append(req) or _response())
    provider = _provider()
    provider.parameters["output_policy"] = {"mode": "strict", "source": "requested"}
    with pytest.raises(ProviderError):
        asyncio.run(provider.repair_document_format("{}", BatchResult.model_json_schema(), []))
    assert requests == []


@pytest.mark.parametrize("repair", [False, True])
def test_presend_slot_callback_can_stop_network_and_is_not_swallowed(monkeypatch, repair):
    requests = []
    _mock(monkeypatch, lambda req: requests.append(req) or _response())

    class SlotError(RuntimeError):
        pass

    def reserve(stage, _info):
        if stage == "document_connecting":
            raise SlotError("slot unavailable")

    provider = _provider("chat_file")
    with pytest.raises(SlotError):
        if repair:
            asyncio.run(provider.repair_document_format("{}", {}, [], on_progress=reserve))
        else:
            asyncio.run(
                provider.complete_document(
                    {
                        "modality": "pdf",
                        "document_base64": base64.b64encode(_pdf(1)).decode(),
                    },
                    on_progress=reserve,
                )
            )
    assert requests == []


def test_slice_page_mismatch_is_rejected_before_network(monkeypatch):
    requests = []
    _mock(monkeypatch, lambda req: requests.append(req) or _response())
    with pytest.raises(ProviderError, match="页码不匹配"):
        asyncio.run(
            _provider("chat_file").complete_document(
                {
                    "modality": "pdf",
                    "document_base64": base64.b64encode(_pdf(1)).decode(),
                    "document_batch_context": {
                        "version": "document-batch-1",
                        "task": "extract",
                        "page_start": 4,
                        "page_end": 5,
                        "send_start": 4,
                        "send_end": 5,
                        "document_pages": 8,
                    },
                },
                schema=BatchResult.model_json_schema(),
            )
        )
    assert requests == []


def test_cancelled_after_client_setup_does_not_emit_paid_dispatch_stage(monkeypatch):
    active, requests, progress = [True], [], []
    original = httpx.AsyncClient

    class CancellingClient(original):
        async def __aenter__(self):
            result = await super().__aenter__()
            active[0] = False
            return result

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: CancellingClient(
            **kwargs, transport=httpx.MockTransport(lambda req: requests.append(req) or _response())
        ),
    )
    with pytest.raises(DocumentRequestCancelled):
        asyncio.run(
            _provider().repair_document_format(
                "{}",
                {},
                [],
                before_send=lambda: active[0],
                on_progress=lambda stage, _details: progress.append(stage),
            )
        )
    assert requests == [] and "document_connecting" not in progress


def test_connection_failure_emits_exactly_one_dispatch_slot_callback(monkeypatch):
    stages, requests = [], []

    def fail(request):
        requests.append(request)
        raise httpx.ConnectTimeout("fixture failure", request=request)

    _mock(monkeypatch, fail)
    with pytest.raises(ProviderError):
        asyncio.run(
            _provider().repair_document_format(
                "{}",
                {},
                [],
                on_progress=lambda stage, _info: stages.append(stage),
            )
        )
    assert len(requests) == 1 and stages.count("document_connecting") == 1


def test_planner_cancels_before_reading_and_between_rendered_pages(tmp_path, monkeypatch):
    path = tmp_path / "fixture.pdf"
    path.write_bytes(_pdf(6))
    with pytest.raises(DocumentRenderCancelled):
        prepare_document(path, 5, _provider(), should_continue=lambda: False)
    rendered = []
    original = pymupdf.Page.get_pixmap

    def render(page, **kwargs):
        rendered.append(page.number)
        return original(page, **kwargs)

    monkeypatch.setattr(pymupdf.Page, "get_pixmap", render)
    with pytest.raises(DocumentRenderCancelled):
        prepare_document(path, 5, _provider(), should_continue=lambda: not rendered)
    assert rendered == [0]


def test_planner_propagates_caller_total_deadline_without_wrapping(tmp_path):
    path = tmp_path / "fixture.pdf"
    path.write_bytes(_pdf(2))

    def deadline():
        raise DocumentRenderDeadline

    with pytest.raises(DocumentRenderDeadline):
        prepare_document(path, 5, _provider(), should_continue=deadline)


def test_planner_checks_cancellation_around_file_capacity_slicing(tmp_path, monkeypatch):
    from researchgraph import document_batch_transport

    path = tmp_path / "fixture.pdf"
    path.write_bytes(_pdf(5))
    slices = []
    original = document_batch_transport.slice_pdf

    def sliced(*args):
        result = original(*args)
        slices.append(True)
        return result

    monkeypatch.setattr(document_batch_transport, "slice_pdf", sliced)
    with pytest.raises(DocumentRenderCancelled):
        prepare_document(path, 5, _provider("chat_file"), should_continue=lambda: not slices)
    assert len(slices) == 1
