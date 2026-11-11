"""External renderers use short-lived capabilities, never real provider keys."""

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from researchgraph.credentials import SecretStore
from researchgraph.lite_models import LiteTokenUsage
from researchgraph.models import AttachmentRevision, Base, Job, Paper, Project, now
from researchgraph.translation_proxy import TranslationProxy
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

CLIENT = httpx.AsyncClient


def fixture(tmp_path: Path, **budgets: int) -> TranslationProxy:
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    project_id, paper_id, revision_id, job_id = (str(uuid4()) for _ in range(4))
    with Session(engine) as session, session.begin():
        session.add(
            Project(
                id=project_id,
                name="Translation test",
                description="",
                experience_mode="lite",
                created_at=now(),
            )
        )
        session.add(Paper(id=paper_id, project_id=project_id, title="Synthetic", created_at=now()))
        session.add(
            AttachmentRevision(
                id=revision_id,
                paper_id=paper_id,
                sha256="a" * 64,
                parser_version="test",
                page_count=1,
                warnings=[],
                created_at=now(),
            )
        )
        session.add(
            Job(
                id=job_id,
                project_id=project_id,
                kind="pdf_translation",
                status="running",
                payload={},
                created_at=now(),
                updated_at=now(),
            )
        )
    return TranslationProxy(
        engine,
        job_id,
        tmp_path,
        {
            "provider": "compatible",
            "model": "fixture-model",
            "base_url": "https://model.test/v1",
            "credential_ref": str(uuid4()),
            "parameters": {"temperature": 0.2, "reasoning_effort": "low", "json_mode": True},
        },
        {"project_id": project_id, "paper_id": paper_id, "document_version_id": revision_id},
        max_calls=budgets.get("max_calls", 5),
        max_input_tokens=budgets.get("max_input_tokens", 10000),
    )


def ledger(proxy: TranslationProxy) -> list[LiteTokenUsage]:
    with Session(proxy.engine) as session:
        return list(session.scalars(select(LiteTokenUsage).order_by(LiteTokenUsage.created_at)))


def payload(text: str = "Translate this anonymous test sentence.") -> dict[str, Any]:
    return {"model": "fixture-model", "messages": [{"role": "user", "content": text}]}


def response(*, usage: bool = True) -> dict[str, Any]:
    result: dict[str, Any] = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "这是一条匿名测试文本。"},
            }
        ]
    }
    if usage:
        result["usage"] = {"prompt_tokens": 21, "completion_tokens": 12, "total_tokens": 33}
    return result


def mock_upstream(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    monkeypatch.setattr(SecretStore, "get", lambda _self, _ref: "synthetic-secret-do-not-persist")

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        return CLIENT(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


async def send(
    proxy: TranslationProxy, body: dict[str, Any] | None = None, token: str | None = None
) -> httpx.Response:
    async with CLIENT(
        transport=httpx.ASGITransport(app=proxy.app), base_url="http://test"
    ) as client:
        return await client.post(
            "/v1/chat/completions",
            json=body or payload(),
            headers={"Authorization": f"Bearer {token or proxy.token}"},
        )


def test_proxy_freezes_parameters_records_usage_and_deduplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = fixture(tmp_path)
    requests = []

    def upstream(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == "Bearer synthetic-secret-do-not-persist"
        body = json.loads(request.content)
        assert body["temperature"] == 0.2 and body["reasoning_effort"] == "low"
        assert body["max_tokens"] == 8192
        assert "response_format" not in body and "tools" not in body
        assert ledger(proxy)[0].status == "running"
        return httpx.Response(200, json=response())

    mock_upstream(monkeypatch, upstream)

    async def run() -> None:
        assert (await send(proxy)).status_code == 200
        assert (await send(proxy)).status_code == 200

    asyncio.run(run())
    rows = ledger(proxy)
    assert len(requests) == 1 and proxy.calls == 1
    assert len(rows) == 2 and sum(row.cache_hit for row in rows) == 1
    actual = next(row for row in rows if not row.cache_hit)
    assert (actual.input_tokens, actual.output_tokens, actual.total_tokens) == (21, 12, 33)
    assert actual.cost_estimate is None and actual.usage_source == "provider"
    assert actual.extra["request_fields"] == [
        "max_tokens",
        "messages",
        "model",
        "reasoning_effort",
        "temperature",
    ]
    assert all(row.retry_count == 0 for row in rows)
    assert "synthetic-secret" not in str([row.__dict__ for row in rows])
    assert list(tmp_path.iterdir()) == []


def test_proxy_accepts_babeldoc_control_fields_but_rebuilds_frozen_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = fixture(tmp_path)
    requests = []

    def upstream(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=response())

    mock_upstream(monkeypatch, upstream)
    incoming = payload()
    incoming.update(
        {
            "max_tokens": 2048,
            "temperature": 0,
            "extra_body": {},
            "stream": False,
        }
    )
    result = asyncio.run(send(proxy, incoming))
    assert result.status_code == 200
    assert len(requests) == 1
    # The upstream SDK's compatibility fields do not override the frozen
    # proxy budget or model parameters.
    assert requests[0]["max_tokens"] == 8192
    assert requests[0]["temperature"] == 0.2
    assert requests[0]["reasoning_effort"] == "low"


def test_proxy_can_disable_reading_parameters_for_bundled_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = fixture(tmp_path)
    proxy.forward_parameters = False
    requests = []

    def upstream(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=response())

    mock_upstream(monkeypatch, upstream)
    assert asyncio.run(send(proxy)).status_code == 200
    assert requests[0] == {
        "model": "fixture-model",
        "messages": [{"role": "user", "content": "Translate this anonymous test sentence."}],
        "max_tokens": 8192,
    }


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, "TRANSLATION_PROVIDER_REQUEST_REJECTED"),
        (401, "TRANSLATION_PROVIDER_AUTH_FAILED"),
        (429, "TRANSLATION_PROVIDER_RATE_LIMITED"),
        (503, "TRANSLATION_PROVIDER_FAILED"),
    ],
)
def test_proxy_classifies_provider_http_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int, code: str
) -> None:
    proxy = fixture(tmp_path)
    mock_upstream(monkeypatch, lambda _request: httpx.Response(status))
    assert asyncio.run(send(proxy)).status_code == 409
    assert proxy.error_code == code
    assert ledger(proxy)[0].reason_code == code


@pytest.mark.parametrize(
    "kind", ["missing_usage", "http_error", "timeout", "invalid_json", "redirect"]
)
def test_proxy_unknown_usage_and_failures_do_not_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    proxy = fixture(tmp_path)
    calls = []

    def upstream(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if kind == "timeout":
            raise httpx.ReadTimeout("synthetic-secret and private content", request=request)
        if kind == "http_error":
            return httpx.Response(429, text="synthetic-secret and private content")
        if kind == "redirect":
            return httpx.Response(307, headers={"location": "https://other.test"})
        if kind == "invalid_json":
            return httpx.Response(200, text="synthetic-secret and private content")
        return httpx.Response(200, json=response(usage=False))

    mock_upstream(monkeypatch, upstream)

    async def run() -> None:
        first = await send(proxy)
        assert first.status_code == (200 if kind == "missing_usage" else 409)
        second = await send(proxy)
        assert second.status_code == (200 if kind == "missing_usage" else 403)
        assert "synthetic-secret" not in first.text and "private content" not in first.text

    asyncio.run(run())
    actual = [row for row in ledger(proxy) if not row.cache_hit]
    assert len(calls) == len(actual) == 1
    assert actual[0].input_tokens is None and actual[0].usage_source == "unknown"
    assert actual[0].cost_estimate is None
    assert actual[0].status == ("succeeded" if kind == "missing_usage" else "failed")


@pytest.mark.parametrize(
    "change", ["token", "model", "tool", "image", "stream", "json", "scope", "job"]
)
def test_proxy_rejects_unauthorized_and_nontext_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    proxy = fixture(tmp_path)
    mock_upstream(monkeypatch, lambda _req: pytest.fail("must not contact provider"))
    body = payload()
    if change == "model":
        body["model"] = "different"
    elif change == "tool":
        body["tools"] = []
    elif change == "image":
        body["messages"][0]["content"] = [{"type": "image_url", "image_url": {"url": "x"}}]
    elif change == "stream":
        body["stream"] = True
    elif change == "json":
        body["response_format"] = {"type": "json_object"}
    elif change == "scope":
        proxy.scope["document_version_id"] = str(uuid4())
    elif change == "job":
        with Session(proxy.engine) as session, session.begin():
            job = session.get(Job, proxy.job_id)
            assert job is not None
            job.status = "cancelled"
    result = asyncio.run(send(proxy, body, token="wrong" if change == "token" else None))
    assert result.status_code in {400, 403}
    assert ledger(proxy) == []


@pytest.mark.parametrize("budget", ["calls", "bytes"])
def test_proxy_enforces_budgets_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, budget: str
) -> None:
    proxy = fixture(tmp_path, max_calls=1, max_input_tokens=10000 if budget == "calls" else 1)
    mock_upstream(monkeypatch, lambda _req: httpx.Response(200, json=response()))

    async def run() -> None:
        if budget == "calls":
            assert (await send(proxy)).status_code == 200
        result = await send(proxy, payload("Different text"))
        assert result.status_code == 403
        assert proxy.error_code == "TRANSLATION_BUDGET_EXCEEDED"
        assert (await send(proxy)).status_code == 403

    asyncio.run(run())
    assert proxy.calls == (1 if budget == "calls" else 0)


def test_proxy_cancel_interrupts_network_and_updates_same_usage_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = fixture(tmp_path)

    async def run() -> None:
        started = asyncio.Event()

        async def upstream(_request: httpx.Request) -> httpx.Response:
            started.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        mock_upstream(monkeypatch, upstream)
        request = asyncio.create_task(send(proxy))
        await asyncio.wait_for(started.wait(), timeout=2)
        await proxy.cancel()
        result = await request
        assert result.status_code == 403
        assert (await send(proxy)).status_code == 403

    asyncio.run(run())
    rows = ledger(proxy)
    assert len(rows) == 1 and rows[0].status == "cancelled"
    assert rows[0].input_tokens is None and rows[0].cost_estimate is None


def test_proxy_loopback_lifecycle_and_no_automatic_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = fixture(tmp_path)
    mock_upstream(monkeypatch, lambda _req: httpx.Response(200, json=response()))

    async def run() -> None:
        async with proxy:
            assert proxy.base_url.startswith("http://127.0.0.1:")
            async with CLIENT(trust_env=False) as client:
                result = await client.post(
                    proxy.base_url + "/chat/completions",
                    json=payload(),
                    headers={"Authorization": f"Bearer {proxy.token}"},
                )
                assert result.status_code == 200
        assert proxy.cancelled
        assert proxy._server_task is not None and proxy._server_task.done()
        restarted = TranslationProxy(
            proxy.engine, proxy.job_id, tmp_path, proxy.snapshot, proxy.scope, 5, 10000
        )
        with pytest.raises(ValueError, match="new explicit job"):
            await restarted.__aenter__()

    asyncio.run(run())


def test_proxy_revalidates_source_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = fixture(tmp_path)

    def upstream(_request: httpx.Request) -> httpx.Response:
        with Session(proxy.engine) as session, session.begin():
            revision = session.get(AttachmentRevision, proxy.scope["document_version_id"])
            assert revision is not None
            revision.sha256 = "b" * 64
        return httpx.Response(200, json=response())

    mock_upstream(monkeypatch, upstream)
    assert asyncio.run(send(proxy)).status_code == 409
    assert ledger(proxy)[0].status == "failed"
    assert ledger(proxy)[0].total_tokens == 33


def test_proxy_rejects_browser_origin_even_with_valid_capability(tmp_path: Path) -> None:
    proxy = fixture(tmp_path)

    async def run() -> None:
        async with CLIENT(
            transport=httpx.ASGITransport(app=proxy.app), base_url="http://test"
        ) as client:
            result = await client.post(
                "/v1/chat/completions",
                json=payload(),
                headers={
                    "Origin": "https://foreign.test",
                    "Authorization": f"Bearer {proxy.token}",
                },
            )
            assert result.status_code == 403

    asyncio.run(run())
    assert ledger(proxy) == []


def test_proxy_truncation_keeps_measured_usage_and_revokes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = fixture(tmp_path)
    result = response()
    result["choices"][0]["finish_reason"] = "length"
    mock_upstream(monkeypatch, lambda _req: httpx.Response(200, json=result))
    assert asyncio.run(send(proxy)).status_code == 409
    row = ledger(proxy)[0]
    assert row.status == "failed" and row.total_tokens == 33 and row.cost_estimate is None
    assert proxy.error_code == "TRANSLATION_PROVIDER_TRUNCATED"


@pytest.mark.parametrize("finish_reason", [None, "", "content_filter", "tool_calls"])
def test_proxy_does_not_infer_stop_from_unknown_or_incomplete_responses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, finish_reason: str | None
) -> None:
    proxy = fixture(tmp_path)
    result = response()
    result["choices"][0]["finish_reason"] = finish_reason
    mock_upstream(monkeypatch, lambda _req: httpx.Response(200, json=result))
    assert asyncio.run(send(proxy)).status_code == 409
    assert proxy.error_code == "TRANSLATION_PROVIDER_RESPONSE_INVALID"
    assert ledger(proxy)[0].total_tokens == 33
    assert proxy._cache == {}


@pytest.mark.parametrize(
    "fields",
    [
        {"stream": 0},
        {"stream": "false"},
        {"max_tokens": True},
        {"extra_body": {"tools": []}},
        {"temperature": 3},
        {"top_p": 2},
        {"reasoning_effort": "unsupported"},
    ],
)
def test_proxy_rejects_invalid_compatibility_values_before_any_provider_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fields: dict[str, Any]
) -> None:
    proxy = fixture(tmp_path)
    mock_upstream(monkeypatch, lambda _request: pytest.fail("must not contact provider"))
    assert asyncio.run(send(proxy, {**payload(), **fields})).status_code == 400
    assert proxy.error_code == "TRANSLATION_TEXT_ONLY"
    assert ledger(proxy) == []


def test_proxy_concurrent_duplicates_make_one_provider_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = fixture(tmp_path)
    mock_upstream(monkeypatch, lambda _req: httpx.Response(200, json=response()))

    async def run() -> None:
        results = await asyncio.gather(send(proxy), send(proxy), send(proxy))
        assert all(result.status_code == 200 for result in results)

    asyncio.run(run())
    assert proxy.calls == 1
    assert sum(row.cache_hit for row in ledger(proxy)) == 2


def test_proxy_watcher_cancels_http_after_job_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = fixture(tmp_path)

    async def run() -> None:
        started = asyncio.Event()

        async def upstream(_request: httpx.Request) -> httpx.Response:
            started.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        mock_upstream(monkeypatch, upstream)
        async with proxy:
            task = asyncio.create_task(send(proxy))
            await asyncio.wait_for(started.wait(), timeout=2)
            with Session(proxy.engine) as session, session.begin():
                job = session.get(Job, proxy.job_id)
                assert job is not None
                job.status = "cancelled"
            result = await asyncio.wait_for(task, timeout=3)
            assert result.status_code == 403
            assert proxy.cancelled
        assert ledger(proxy)[0].status == "cancelled"

    asyncio.run(run())


def test_proxy_rejects_echoed_credential_without_losing_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = fixture(tmp_path)
    result = response()
    result["choices"][0]["message"]["content"] = "echo synthetic-secret-do-not-persist"
    mock_upstream(monkeypatch, lambda _req: httpx.Response(200, json=result))

    async def run() -> None:
        first = await send(proxy)
        assert first.status_code == 409
        assert "synthetic-secret" not in first.text
        assert (await send(proxy)).status_code == 403

    asyncio.run(run())
    rows = ledger(proxy)
    assert len(rows) == 1 and rows[0].status == "failed"
    assert rows[0].total_tokens == 33 and rows[0].usage_source == "provider"
    assert "synthetic-secret" not in str(rows[0].__dict__)
    assert proxy._cache == {}
