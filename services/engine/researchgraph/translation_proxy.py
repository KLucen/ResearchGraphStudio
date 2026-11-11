"""Job-scoped loopback bridge: the external renderer never receives provider credentials.

Only text chat is supported. The byte budget is deliberately conservative and is
not represented as measured token usage. Failed requests revoke the capability;
external SDK retries therefore cannot produce additional provider charges.
"""

import asyncio
import hashlib
import json
import secrets
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from researchgraph.credentials import SecretStore
from researchgraph.lite_models import LiteTokenUsage
from researchgraph.lite_usage import record_usage
from researchgraph.model_adapters import adapt_request
from researchgraph.model_settings import ModelParameters, _validated_base_url
from researchgraph.models import AttachmentRevision, Job, Paper
from researchgraph.storage import read_session


class _ProxyFailure(Exception):
    """A provider failure with a safe, user-facing classification."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


_REQUEST_FIELDS = {
    "model",
    "messages",
    # OpenAI SDK/BabelDOC compatibility fields.  Values are validated and
    # ignored when the proxy rebuilds the frozen request below.
    "max_tokens",
    "max_completion_tokens",
    "temperature",
    "top_p",
    "reasoning_effort",
    "extra_body",
    "stream",
    # Structured output and tool calls are deliberately rejected below.
    "response_format",
    "tools",
    "tool_choice",
}


class _LocalServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self) -> Iterator[None]:
        # The desktop sidecar owns process signals, not this per-job listener.
        yield


class TranslationProxy:
    def __init__(
        self,
        engine: Engine,
        job_id: str,
        data_dir: Path,
        snapshot: dict[str, Any],
        scope: dict[str, str],
        max_calls: int,
        max_input_tokens: int,
        *,
        forward_parameters: bool = True,
    ) -> None:
        if type(max_calls) is not int or not 1 <= max_calls <= 5000:
            raise ValueError("Invalid translation call budget")
        if type(max_input_tokens) is not int or not 1 <= max_input_tokens <= 50_000_000:
            raise ValueError("Invalid translation input budget")
        self.engine, self.job_id, self.data_dir = engine, job_id, data_dir
        self.scope = {k: scope[k] for k in ("project_id", "paper_id", "document_version_id")}
        self.snapshot = json.loads(json.dumps(snapshot))
        self.model = str(self.snapshot["model"])
        self.provider = str(self.snapshot["provider"])
        if not self.model or self.provider not in {"openai", "compatible", "local"}:
            raise ValueError("Unsupported translation model")
        self.upstream_url = _validated_base_url(self.provider, str(snapshot["base_url"]))
        self.parameters = ModelParameters.model_validate(snapshot.get("parameters", {}))
        self.max_calls, self.max_input_tokens = max_calls, max_input_tokens
        self.forward_parameters = forward_parameters
        self.calls = 0
        self.estimated_input_tokens = 0
        self.cancelled = False
        self.error_code: str | None = None
        self.token = secrets.token_urlsafe(32)
        self.base_url = ""
        self._revoked = False
        self._entered = False
        self._source_hash: str | None = None
        self._lock = asyncio.Lock()
        self._cache: dict[str, dict[str, Any]] = {}
        self._server: _LocalServer | None = None
        self._server_task: asyncio.Task[None] | None = None
        self._watcher_task: asyncio.Task[None] | None = None
        self._socket: socket.socket | None = None
        self._request_task: asyncio.Task[dict[str, Any]] | None = None
        self.last_request_fields: tuple[str, ...] = ()
        self.app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        self.app.add_api_route("/v1/chat/completions", self._handle, methods=["POST"])

    def _check_scope(self, session: Session) -> None:
        job = session.get(Job, self.job_id)
        paper = session.get(Paper, self.scope["paper_id"])
        revision = session.get(AttachmentRevision, self.scope["document_version_id"])
        if (
            job is None
            or job.status not in {"queued", "running"}
            or job.project_id != self.scope["project_id"]
            or paper is None
            or paper.project_id != self.scope["project_id"]
            or revision is None
            or revision.paper_id != paper.id
            or (self._source_hash is not None and revision.sha256 != self._source_hash)
        ):
            raise ValueError("Translation scope is no longer active")
        self._source_hash = revision.sha256

    async def __aenter__(self) -> "TranslationProxy":
        if self._entered:
            raise ValueError("A translation capability cannot be restarted")
        self._entered = True
        with read_session(self.engine) as session:
            self._check_scope(session)
            prior = session.scalar(
                select(LiteTokenUsage.id)
                .where(
                    LiteTokenUsage.task_run_id == self.job_id,
                    LiteTokenUsage.task_kind == "pdf_translation",
                    LiteTokenUsage.cache_hit.is_(False),
                )
                .limit(1)
            )
            if prior is not None:
                raise ValueError("Translation requires a new explicit job after interruption")
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.bind(("127.0.0.1", 0))
        self._socket.setblocking(False)
        self.base_url = f"http://127.0.0.1:{self._socket.getsockname()[1]}/v1"
        self._server = _LocalServer(
            uvicorn.Config(
                self.app,
                host="127.0.0.1",
                log_config=None,
                log_level="critical",
                access_log=False,
                lifespan="off",
                timeout_graceful_shutdown=2,
            )
        )
        self._server_task = asyncio.create_task(self._server.serve(sockets=[self._socket]))
        try:
            async with asyncio.timeout(5):
                while not self._server.started:
                    if self._server_task.done():
                        await self._server_task
                        raise RuntimeError("Translation proxy did not start")
                    await asyncio.sleep(0.01)
        except BaseException:
            await self.cancel()
            raise
        self._watcher_task = asyncio.create_task(self._watch_scope())
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.cancel()

    async def cancel(self) -> None:
        """Revoke new calls, cancel in-flight HTTP and close only our listener."""
        self.cancelled = True
        self._revoked = True
        if self._watcher_task is not None and self._watcher_task is not asyncio.current_task():
            self._watcher_task.cancel()
            await asyncio.gather(self._watcher_task, return_exceptions=True)
        task = self._request_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        if self._server is not None:
            self._server.should_exit = True
        if self._server_task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._server_task), timeout=4)
            except (TimeoutError, asyncio.CancelledError):
                self._server_task.cancel()
                await asyncio.gather(self._server_task, return_exceptions=True)
        if self._socket is not None:
            self._socket.close()
        self._cache.clear()

    async def _watch_scope(self) -> None:
        while not self._revoked:
            await asyncio.sleep(0.2)
            try:
                with read_session(self.engine) as session:
                    self._check_scope(session)
            except Exception:
                self._revoke("TRANSLATION_SCOPE_CHANGED")
                await self.cancel()
                return

    @staticmethod
    def _error(code: str, status: int = 403) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "type": "translation_error",
                    "code": code,
                    "message": "Translation request stopped",
                }
            },
            status_code=status,
        )

    async def _handle(self, request: Request) -> JSONResponse:
        if "origin" in request.headers:
            return self._error("TRANSLATION_BROWSER_ORIGIN_FORBIDDEN")
        supplied = request.headers.get("authorization", "")
        if not secrets.compare_digest(supplied.encode("utf-8"), f"Bearer {self.token}".encode()):
            return self._error("TRANSLATION_CAPABILITY_INVALID")
        if self._revoked:
            return self._error(self.error_code or "TRANSLATION_CANCELLED")
        try:
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > 2_000_000:
                    return self._error("TRANSLATION_INPUT_TOO_LARGE", 400)
            incoming = json.loads(raw)
            body = self._body(incoming)
        except (ValueError, TypeError, KeyError):
            # A malformed or unsupported request must revoke the capability so
            # an SDK retry loop cannot keep sending the same invalid shape.
            self._revoke("TRANSLATION_TEXT_ONLY")
            return self._error("TRANSLATION_TEXT_ONLY", 400)
        fingerprint = hashlib.sha256(
            json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        size = len(json.dumps(body, ensure_ascii=False).encode("utf-8"))
        async with self._lock:
            if self._revoked:
                return self._error(self.error_code or "TRANSLATION_CANCELLED")
            try:
                with read_session(self.engine) as session:
                    self._check_scope(session)
            except ValueError:
                self._revoke("TRANSLATION_SCOPE_CHANGED")
                return self._error(self.error_code or "TRANSLATION_SCOPE_CHANGED")
            if fingerprint in self._cache:
                self._record(fingerprint, size, cache_hit=True, request_fields=tuple(sorted(body)))
                return JSONResponse(self._cache[fingerprint])
            if (
                self.calls >= self.max_calls
                or self.estimated_input_tokens + size > self.max_input_tokens
            ):
                self._revoke("TRANSLATION_BUDGET_EXCEEDED")
                return self._error("TRANSLATION_BUDGET_EXCEEDED")
            self._request_task = asyncio.create_task(self._send(body, fingerprint, size))
            try:
                result = await self._request_task
            except asyncio.CancelledError:
                return self._error("TRANSLATION_CANCELLED")
            except Exception:
                self._revoke(self.error_code or "TRANSLATION_PROVIDER_FAILED")
                return self._error(self.error_code or "TRANSLATION_PROVIDER_FAILED", 409)
            finally:
                self._request_task = None
            self._cache[fingerprint] = result
            return JSONResponse(result)

    def _revoke(self, code: str) -> None:
        self.error_code, self._revoked = code, True

    def _body(self, incoming: Any) -> dict[str, Any]:
        if not isinstance(incoming, dict):
            raise ValueError("Object required")
        self.last_request_fields = tuple(sorted(str(key) for key in incoming))
        if set(incoming) - _REQUEST_FIELDS:
            raise ValueError("Only text model/messages are accepted")
        if incoming.get("model") != self.model:
            raise ValueError("Model differs from frozen snapshot")
        messages = incoming.get("messages")
        if not isinstance(messages, list) or not 1 <= len(messages) <= 32:
            raise ValueError("Invalid messages")
        for item in messages:
            if (
                not isinstance(item, dict)
                or set(item) != {"role", "content"}
                or item["role"] not in {"system", "user", "assistant"}
                or not isinstance(item["content"], str)
                or not item["content"].strip()
            ):
                raise ValueError("Only text messages are accepted")
        if "stream" in incoming and incoming["stream"] is not False:
            raise ValueError("Streaming is not supported")
        if "response_format" in incoming or "tools" in incoming or "tool_choice" in incoming:
            raise ValueError("Structured output and tools are not supported")
        if "extra_body" in incoming and incoming["extra_body"] not in ({}, None):
            raise ValueError("Provider-specific request fields are not supported")
        for name in ("max_tokens", "max_completion_tokens"):
            if name in incoming and (
                type(incoming[name]) is not int or not 1 <= incoming[name] <= 2_000_000
            ):
                raise ValueError("Invalid output limit")
        for name, upper in (("temperature", 2.0), ("top_p", 1.0)):
            if name in incoming and (
                type(incoming[name]) not in {int, float} or not 0 <= float(incoming[name]) <= upper
            ):
                raise ValueError("Invalid sampling parameter")
        if "reasoning_effort" in incoming and incoming["reasoning_effort"] not in {
            "none",
            "minimal",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        }:
            raise ValueError("Invalid reasoning effort")
        body: dict[str, Any] = {"model": self.model, "messages": messages}
        parameters = self.parameters.model_dump()
        if self.forward_parameters:
            for name in ("temperature", "top_p", "reasoning_effort"):
                if parameters[name] is not None:
                    body[name] = parameters[name]
        limit = min(8192, self.parameters.capabilities.max_output_tokens or 8192)
        body["max_completion_tokens" if self.provider == "openai" else "max_tokens"] = limit
        if self.forward_parameters:
            adapt_request(self.upstream_url, self.model, parameters, body)
        return body

    def _record(
        self,
        fingerprint: str,
        size: int,
        *,
        cache_hit: bool = False,
        request_fields: tuple[str, ...] = (),
    ) -> str:
        with Session(self.engine) as session, session.begin():
            self._check_scope(session)
            row = record_usage(
                session,
                project_id=self.scope["project_id"],
                paper_id=self.scope["paper_id"],
                document_version_id=self.scope["document_version_id"],
                task_kind="pdf_translation",
                task_run_id=self.job_id,
                provider=self.provider,
                model=self.model,
                prompt_version="external-pdf2zh-1",
                status="succeeded" if cache_hit else "running",
                cache_hit=cache_hit,
                extra={
                    "request_sha256": fingerprint,
                    "input_estimate_bytes": size,
                    "estimate_policy": "utf8-bytes-v1",
                    # Field names only; never persist request text, headers,
                    # credentials, or provider response bodies.
                    "request_fields": list(request_fields),
                },
            )
            session.flush()
            return row.id

    def _finish(
        self, row_id: str, status: str, code: str | None, usage: dict[str, Any] | None = None
    ) -> None:
        with Session(self.engine) as session, session.begin():
            row = session.get(LiteTokenUsage, row_id)
            if row is None:
                raise RuntimeError("Translation usage record missing")
            row.status, row.reason_code = status, code
            values = usage or {}
            input_tokens, output_tokens = (
                values.get("prompt_tokens"),
                values.get("completion_tokens"),
            )
            if (
                type(input_tokens) is int
                and input_tokens >= 0
                and type(output_tokens) is int
                and output_tokens >= 0
            ):
                row.input_tokens, row.output_tokens = input_tokens, output_tokens
                total = values.get("total_tokens")
                row.total_tokens = (
                    total if type(total) is int and total >= 0 else input_tokens + output_tokens
                )
                row.usage_source = "provider"

    async def _send(self, body: dict[str, Any], fingerprint: str, size: int) -> dict[str, Any]:
        reference = self.snapshot.get("credential_ref")
        key = SecretStore(self.data_dir).get(reference) if reference else ""
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        row_id = self._record(fingerprint, size, request_fields=tuple(sorted(body)))
        self.calls += 1
        self.estimated_input_tokens += size
        measured_usage: dict[str, Any] | None = None
        try:
            async with httpx.AsyncClient(
                trust_env=False, follow_redirects=False, timeout=self.parameters.timeout_seconds
            ) as client:
                async with client.stream(
                    "POST", self.upstream_url + "/chat/completions", json=body, headers=headers
                ) as response:
                    if response.status_code != 200:
                        if response.status_code == 429:
                            raise _ProxyFailure("TRANSLATION_PROVIDER_RATE_LIMITED")
                        if response.status_code in {401, 403}:
                            raise _ProxyFailure("TRANSLATION_PROVIDER_AUTH_FAILED")
                        if 400 <= response.status_code < 500:
                            raise _ProxyFailure("TRANSLATION_PROVIDER_REQUEST_REJECTED")
                        raise _ProxyFailure("TRANSLATION_PROVIDER_FAILED")
                    raw = bytearray()
                    async for part in response.aiter_bytes():
                        raw.extend(part)
                        if len(raw) > 4_000_000:
                            raise ValueError("Translation response too large")
            try:
                data = json.loads(raw)
            except (ValueError, RecursionError):
                raise _ProxyFailure("TRANSLATION_PROVIDER_RESPONSE_INVALID") from None
            usage = data.get("usage") if isinstance(data, dict) else None
            measured_usage = usage if isinstance(usage, dict) else None
            if not isinstance(data, dict):
                raise _ProxyFailure("TRANSLATION_PROVIDER_RESPONSE_INVALID")
            choices = data.get("choices")
            if not isinstance(choices, list) or len(choices) != 1:
                raise _ProxyFailure("TRANSLATION_PROVIDER_RESPONSE_INVALID")
            if not isinstance(choices[0], dict):
                raise _ProxyFailure("TRANSLATION_PROVIDER_RESPONSE_INVALID")
            if choices[0].get("finish_reason") == "length":
                raise _ProxyFailure("TRANSLATION_PROVIDER_TRUNCATED")
            if choices[0].get("finish_reason") != "stop":
                raise _ProxyFailure("TRANSLATION_PROVIDER_RESPONSE_INVALID")
            message = choices[0].get("message", {})
            if not isinstance(message, dict):
                raise _ProxyFailure("TRANSLATION_PROVIDER_RESPONSE_INVALID")
            content = message.get("content")
            if not isinstance(content, str) or not content.strip() or message.get("tool_calls"):
                raise _ProxyFailure("TRANSLATION_PROVIDER_RESPONSE_INVALID")
            if key and key in content:
                raise ValueError("Provider credential appeared in translation text")
            if self._revoked:
                raise asyncio.CancelledError
            with read_session(self.engine) as session:
                self._check_scope(session)
            self._finish(row_id, "succeeded", None, usage if isinstance(usage, dict) else None)
            # Do not forward provider diagnostics, URLs, tool payloads or hidden reasoning.
            result: dict[str, Any] = {
                "id": f"translation-{row_id}",
                "object": "chat.completion",
                "created": 0,
                "model": self.model,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": content},
                    }
                ],
            }
            if isinstance(usage, dict):
                result["usage"] = {
                    k: v
                    for k, v in usage.items()
                    if k in {"prompt_tokens", "completion_tokens", "total_tokens"}
                    and type(v) is int
                    and v >= 0
                }
            return result
        except asyncio.CancelledError:
            self._revoke("TRANSLATION_CANCELLED")
            self._finish(row_id, "cancelled", "TRANSLATION_CANCELLED", measured_usage)
            raise
        except _ProxyFailure as failure:
            self._revoke(failure.code)
            self._finish(row_id, "failed", failure.code, measured_usage)
            raise ValueError("Translation provider request failed") from None
        except Exception:
            self._revoke("TRANSLATION_PROVIDER_FAILED")
            self._finish(row_id, "failed", "TRANSLATION_PROVIDER_FAILED", measured_usage)
            raise ValueError("Translation provider failed") from None
