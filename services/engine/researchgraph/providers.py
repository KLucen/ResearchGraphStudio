"""Bounded text-only providers: no tools, database handles or filesystem capabilities."""

import asyncio
import base64
import binascii
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Protocol

import httpx

from researchgraph.model_adapters import adapt_request, with_documented_limits
from researchgraph.model_capabilities import ModelCapabilities, parse_capabilities


class Provider(Protocol):
    name: str
    model: str

    async def complete(self, prompt: str, data: dict[str, Any], schema: dict[str, Any]) -> str: ...


class MockProvider:
    """Explicit test double, never selected by Lite production tasks."""

    name = "mock"
    model = "offline-test-fixture"

    async def complete(self, prompt: str, data: dict[str, Any], schema: dict[str, Any]) -> str:
        if schema.get("title") == "ConnectionTest":
            return '{"ok":true}'
        raise ValueError("MockProvider requires an explicit test fixture")


class ProviderError(ValueError):
    def __init__(
        self,
        category: str,
        message: str,
        retry_after: int | None = None,
        *,
        timeout_phase: str | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.retry_after = retry_after
        self.timeout_phase = timeout_phase


def require_document_capability(
    provider: Provider,
    modality: str,
    *,
    require_multimodal: bool = False,
) -> None:
    """Reject document inputs a configured provider cannot actually receive.

    The ordinary ``complete`` protocol remains text-only for compatibility. A
    model-first import may therefore run against a text fixture whose source is
    already represented as untrusted text JSON, while a PDF/image request must
    be explicitly advertised by the provider configuration. The caller should
    surface ``error_code`` instead of falling back to local PDF parsing.
    """

    if modality not in {"text", "pdf", "image"}:
        raise ProviderError("document_capability", "不支持的文档输入类型")
    capabilities = getattr(provider, "capabilities", None)
    document_input = getattr(capabilities, "document_input", "text")
    multimodal = bool(getattr(capabilities, "multimodal", False))
    document_transport = getattr(capabilities, "document_transport", "none")
    if modality == "text":
        if require_multimodal and not multimodal:
            raise ProviderError(
                "document_capability",
                "当前模型不具备多模态能力，已按选择暂停；未回退本地解析",
            )
        return
    if modality == "pdf" and document_input not in {"pdf", "image"}:
        raise ProviderError(
            "document_capability",
            "当前模型未声明 PDF/文档输入能力；未回退本地解析",
        )
    if modality in {"pdf", "image"} and document_transport != "chat_file":
        raise ProviderError(
            "document_capability",
            "当前模型未声明可用的文件传输方式；未回退本地解析",
        )
    if modality == "image" and not (multimodal or document_input == "image"):
        raise ProviderError(
            "document_capability",
            "当前模型未声明图像输入能力；未回退本地解析",
        )
    if require_multimodal and not multimodal:
        raise ProviderError(
            "document_capability",
            "当前模型未声明多模态能力，已按选择暂停；未回退本地解析",
        )


class ConfiguredProvider:
    name = "configured"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        key: str | None = None,
        parameters: dict[str, Any] | None = None,
        provider_name: str = "configured",
    ) -> None:
        self.name = provider_name
        self.base_url = (
            base_url if base_url is not None else os.environ.get("RGS_MODEL_BASE_URL", "")
        ).rstrip("/")
        self.model = model if model is not None else os.environ.get("RGS_MODEL_NAME", "")
        self.key = key if key is not None else os.environ.get("RGS_MODEL_API_KEY", "")
        self.parameters = parameters or {"temperature": 0, "timeout_seconds": 30, "json_mode": True}
        self.usage: dict[str, int] = {}
        self.capabilities = with_documented_limits(
            self.base_url,
            self.model,
            ModelCapabilities.model_validate(self.parameters.get("capabilities", {})),
        )
        self.capabilities_checked = False
        self.request_metadata: dict[str, Any] = {}
        self.partial_output: str | None = None
        parsed = urllib.parse.urlparse(self.base_url)
        if (
            not self.model
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not (
                parsed.scheme == "https"
                or (
                    parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
                )
            )
        ):
            raise ValueError("请配置 RGS_MODEL_BASE_URL 与 RGS_MODEL_NAME；远端模型必须使用 HTTPS")

    async def prepare(self) -> None:
        """Metadata requests contain only the model ID; redirects cannot receive credentials."""
        if self.capabilities_checked:
            return
        self.capabilities_checked = True
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        try:
            async with httpx.AsyncClient(
                trust_env=False, follow_redirects=False, timeout=5
            ) as client:
                async with client.stream(
                    "GET", self.base_url + "/models", headers=headers
                ) as response:
                    if response.status_code != 200:
                        return
                    raw = bytearray()
                    async for part in response.aiter_bytes():
                        raw.extend(part)
                        if len(raw) > 2_000_000:
                            return
            data = json.loads(raw).get("data", [])
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("id") == self.model:
                        discovered = parse_capabilities(item)
                        if discovered.source != "provider_default":
                            self.capabilities = ModelCapabilities(
                                max_output_tokens=discovered.max_output_tokens
                                or self.capabilities.max_output_tokens,
                                context_window=discovered.context_window
                                or self.capabilities.context_window,
                                # Preserve document transport declared by the
                                # frozen profile.  Standard /models metadata
                                # usually reports only token limits; rebuilding
                                # the object without these fields would silently
                                # turn a PDF-capable provider back into text-only.
                                document_input=(
                                    discovered.document_input
                                    if discovered.document_input != "text"
                                    else self.capabilities.document_input
                                ),
                                multimodal=discovered.multimodal or self.capabilities.multimodal,
                                document_transport=(
                                    discovered.document_transport
                                    if discovered.document_transport != "none"
                                    else self.capabilities.document_transport
                                ),
                                source=discovered.source
                                if discovered.max_output_tokens and discovered.context_window
                                else f"{discovered.source}+{self.capabilities.source}",
                            )
                        return
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            # Standard OpenAI /models does not expose token limits. Never guess.
            return

    def _build_body(
        self, prompt: str, data: dict[str, Any], schema: dict[str, Any]
    ) -> dict[str, Any]:
        """Build the OpenAI-compatible request body in one place.

        The synchronous helper below is retained for integrations that used the old
        private test hook. Production extraction uses ``complete`` so cancellation
        closes the async socket instead of leaving a worker thread behind.
        """
        output_audit = None
        response_format = None
        supplied_schema = schema
        if self.parameters.get("output_policy") is not None:
            from researchgraph.structured_output import checked_policy, response_format_for

            try:
                policy = checked_policy(
                    self.parameters["output_policy"],
                    self.name,
                    self.base_url,
                    self.model,
                    self.parameters,
                )
                response_format, output_audit = response_format_for(schema, policy)
            except ValueError as error:
                raise ProviderError("structured_output_unsupported", str(error)) from None
            if response_format and response_format["type"] == "json_schema":
                supplied_schema = response_format["json_schema"]["schema"]
                prompt += (
                    "\nNative strict output requires every schema property to be present. "
                    "Use null only where the provided schema explicitly permits it; "
                    "do not invent values for unknown fields."
                )
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": re.sub(
                        r"## User data[^\n]*\n.*?(?=\n## )",
                        "## Runtime input\n"
                        "Read the separate user JSON's untrusted_source_data fields. "
                        "The output_schema defines the required response.\n",
                        prompt,
                        flags=re.S,
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"untrusted_source_data": data, "output_schema": supplied_schema},
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        for parameter in ("temperature", "top_p", "reasoning_effort"):
            if self.parameters.get(parameter) is not None:
                body[parameter] = self.parameters[parameter]
        if output_audit and output_audit["mode"] == "native_json_schema":
            # The exact documented non-reasoning models do not accept this knob.
            body.pop("reasoning_effort", None)
        output_limit = self.capabilities.max_output_tokens
        if output_limit and self.capabilities.context_window:
            # Conservative estimate includes schema/instructions and non-ASCII source.
            input_estimate = len(json.dumps(body["messages"], ensure_ascii=False).encode("utf-8"))
            output_limit = min(
                output_limit, self.capabilities.context_window - input_estimate - 512
            )
            if output_limit < 128:
                raise ProviderError("context_limit", "模型上下文不足，需缩小当前批次")
        if output_limit:
            name = "max_completion_tokens" if self.name == "openai" else "max_tokens"
            body[name] = output_limit
        self.request_metadata = {
            "output_limit": output_limit,
            "limit_source": self.capabilities.source,
            "context_window": self.capabilities.context_window,
            "legacy_manual_limit_ignored": self.parameters.get("max_output_tokens"),
            "input_bytes": len(json.dumps(body["messages"], ensure_ascii=False).encode("utf-8")),
            "source_characters": sum(
                len(e.get("text", "")) for e in data.get("allowed_evidence", [])
            ),
            "evidence_count": len(data.get("allowed_evidence", [])),
        }
        if output_audit is not None:
            self.request_metadata["structured_output"] = output_audit
            if response_format is not None:
                body["response_format"] = response_format
        elif self.parameters.get("json_mode", True):
            body["response_format"] = {"type": "json_object"}
        self.request_metadata.update(
            adapt_request(self.base_url, self.model, self.parameters, body)
        )
        return body

    def _request(self, prompt: str, data: dict[str, Any], schema: dict[str, Any]) -> str:
        """Compatibility transport for legacy callers and unit tests.

        New extraction calls do not use this path. It deliberately mirrors the
        response validation rules while keeping the old monkeypatchable surface.
        """
        body = self._build_body(prompt, data, schema)
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.key}"} if self.key else {}),
            },
            method="POST",
        )
        timeout = self.parameters.get("timeout_seconds", 30)
        try:
            with urllib.request.build_opener().open(request, timeout=timeout) as response:
                raw = response.read(2_000_001)
        except TimeoutError:
            raise ProviderError("timeout", "模型请求超时，请检查网络或缩小批次") from None
        except OSError:
            raise ProviderError("network", "模型网络连接失败，请检查网络或代理") from None
        if len(raw) > 2_000_000:
            raise ProviderError("response", "模型响应超过 2 MB 限制")
        try:
            envelope = json.loads(raw)
            content = envelope["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            raise ProviderError("response", "模型响应结构无效") from None
        if not isinstance(content, str):
            raise ProviderError("response", "模型没有返回文本 JSON")
        if self.key and self.key in content:
            raise ValueError("模型响应包含凭据，已拒绝保存")
        return content

    async def complete(self, prompt: str, data: dict[str, Any], schema: dict[str, Any]) -> str:
        self.usage = {}
        self.partial_output = None
        self.request_metadata = {}
        await self.prepare()
        body = self._build_body(prompt, data, schema)
        from researchgraph.chat_stream import ChatStream

        body.update(stream=True, stream_options={"include_usage": True})
        self.request_metadata.update(
            transport="chat-sse-v1", total_timeout_seconds=self.total_timeout
        )
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        started = time.monotonic()
        phase = "connection"
        response_bytes = 0
        stream: ChatStream | None = None

        async def trace(event: str, _info: dict[str, Any]) -> None:
            nonlocal phase
            if "send_request_body.complete" in event:
                phase = "response_headers"
                self.request_metadata["request_sent_seconds"] = round(time.monotonic() - started, 3)
            elif "send_request" in event:
                phase = "request_write"

        try:
            timeout = self.parameters.get("timeout_seconds", 30)
            # Async transport closes the socket on cancellation; retries cannot
            # overlap a still-running urllib thread from a previous attempt.
            async with (
                asyncio.timeout(self.total_timeout),
                httpx.AsyncClient(
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx.Timeout(timeout, connect=min(timeout, 15)),
                ) as client,
            ):
                async with client.stream(
                    "POST",
                    self.base_url + "/chat/completions",
                    json=body,
                    headers=headers,
                    extensions={"trace": trace},
                ) as response:
                    phase = "response_body"
                    self.request_metadata["response_headers_seconds"] = round(
                        time.monotonic() - started, 3
                    )
                    code = response.status_code
                    if 300 <= code < 400:
                        raise ProviderError(
                            "client", "服务重定向被拒绝，未向其他地址发送文本或密钥"
                        )
                    if code == 429:
                        after = response.headers.get("Retry-After", "")
                        raise ProviderError(
                            "rate_limit",
                            "模型请求受限（HTTP 429）",
                            int(after) if after.isdigit() else None,
                        )
                    if code >= 500:
                        raise ProviderError("server", f"模型服务暂时不可用（HTTP {code}）")
                    if code >= 400:
                        raise ProviderError(
                            "client", f"模型请求被拒绝（HTTP {code}），请检查配置或额度"
                        )
                    raw = bytearray()
                    if "text/event-stream" in response.headers.get("content-type", ""):
                        stream = ChatStream(
                            accept_refusal=self.parameters.get("output_policy") is not None
                        )
                    async for part in response.aiter_bytes():
                        response_bytes += len(part)
                        # SSE envelopes repeat per token; bound wire traffic separately
                        # from retained text so streaming does not reduce usable output.
                        if response_bytes > (32_000_000 if stream else 2_000_000):
                            raise ProviderError("response", "模型响应超过传输大小限制")
                        self.request_metadata.setdefault(
                            "first_byte_seconds", round(time.monotonic() - started, 3)
                        )
                        self.request_metadata["last_byte_seconds"] = round(
                            time.monotonic() - started, 3
                        )
                        if stream:
                            stream.feed(part)
                            self.request_metadata.update(
                                content_characters=stream.content_characters,
                                reasoning_characters=stream.reasoning_characters,
                            )
                        else:
                            # Some compatible servers ignore stream and return one JSON response.
                            raw.extend(part)
            envelope = stream.envelope() if stream else json.loads(raw)
            self.usage = {
                k: v
                for k, v in envelope.get("usage", {}).items()
                if k in {"prompt_tokens", "completion_tokens", "total_tokens"}
                and type(v) is int
                and v >= 0
            }
            details = envelope.get("usage", {}).get("completion_tokens_details", {})
            if isinstance(details, dict) and type(details.get("reasoning_tokens")) is int:
                self.usage["reasoning_tokens"] = max(0, details["reasoning_tokens"])
            message = envelope["choices"][0]["message"]
            finish_reason = envelope["choices"][0].get("finish_reason")
            self.request_metadata["finish_reason"] = (
                finish_reason
                if finish_reason in {"stop", "length", "content_filter"}
                else "unknown"
            )
            if self.parameters.get("output_policy") is not None and (
                message.get("refusal") or finish_reason == "content_filter"
            ):
                self.request_metadata["structured_output_refused"] = True
                raise ProviderError(
                    "structured_output_refused", "模型拒绝返回本次结构化结果；未自动重发或降级"
                )
            content = message["content"]
            if isinstance(content, str) and self.key and self.key in content:
                raise ValueError("模型响应包含凭据，已拒绝保存")
            if envelope["choices"][0].get("finish_reason") == "length":
                self.partial_output = content if isinstance(content, str) else None
                raise ProviderError(
                    "output_limit", "模型服务截断了响应（可能包含推理预算），当前批次需要拆分恢复"
                )
            if not isinstance(content, str):
                raise ValueError("模型没有返回文本 JSON")


            if self.key and self.key in content:
                raise ValueError("模型响应包含凭据，已拒绝保存")
            return content
        except TimeoutError:
            self.request_metadata["timeout_phase"] = "total"
            raise ProviderError(
                "timeout",
                f"模型生成达到总时限（{self.total_timeout:g} 秒）；已停止等待",
                timeout_phase="total",
            ) from None
        except httpx.TimeoutException as error:
            if isinstance(error, httpx.ConnectTimeout):
                phase = "connection"
            elif isinstance(error, httpx.WriteTimeout):
                phase = "request_write"
            elif isinstance(error, httpx.PoolTimeout):
                phase = "connection_pool"
            elif isinstance(error, httpx.ReadTimeout) and phase != "response_body":
                phase = "response_headers"
            self.request_metadata["timeout_phase"] = phase
            label = {
                "connection": "建立连接",
                "request_write": "发送请求",
                "connection_pool": "等待连接",
                "response_headers": "等待模型响应",
                "response_body": "读取模型响应",
            }[phase]
            raise ProviderError(
                "timeout", f"{label}超时（{timeout} 秒）；已保存批次保留", timeout_phase=phase
            ) from None
        except httpx.RequestError:
            if response_bytes:
                raise ProviderError(
                    "incomplete_stream", "模型响应中途断开，已保留部分输出；未自动重发"
                ) from None
            raise ProviderError("network", "模型网络连接失败，请检查网络或代理") from None
        except (
            KeyError,
            IndexError,
            TypeError,
            AttributeError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            raise ProviderError("response", "模型响应结构无效") from None
        finally:
            if stream:
                partial = "".join(stream.parts)
                self.partial_output = partial if not (self.key and self.key in partial) else None
            self.request_metadata.update(
                elapsed_seconds=round(time.monotonic() - started, 3), response_bytes=response_bytes
            )

    async def complete_document(
        self, payload: dict[str, Any], schema: dict[str, Any] | None = None
    ) -> str:
        """Send a PDF/document as an explicitly enabled chat file input.

        OpenAI-compatible chat endpoints do not uniformly support files.  The
        caller must therefore advertise ``capabilities.document_transport`` as
        ``chat_file`` before this method is reachable.  The local path is read
        only by the engine and is never included in the prompt; the provider
        receives a data URL in the user content.
        """
        modality = str(payload.get("modality") or "pdf")
        if modality != "pdf":
            raise ProviderError("document_capability", "当前文档传输仅支持 PDF 文件")
        require_document_capability(
            self,
            modality,
            require_multimodal=bool(payload.get("require_multimodal", False)),
        )
        path_value = payload.get("path")
        if isinstance(payload.get("document_base64"), str):
            encoded = payload["document_base64"]
            filename = str(payload.get("file_name") or "paper.pdf")
            # Bound and validate caller-supplied base64 before embedding it in
            # a request; do not allocate a decoded buffer of unbounded size.
            max_encoded = ((50 * 1024 * 1024 + 2) // 3) * 4
            if len(encoded) > max_encoded:
                raise ProviderError("document_input", "PDF 超过 50 MiB 限制")
            try:
                raw_size = len(base64.b64decode(encoded, validate=True))
            except (binascii.Error, ValueError):
                raise ProviderError("document_input", "模型文档任务的 PDF 编码无效") from None
            if raw_size > 50 * 1024 * 1024:
                raise ProviderError("document_input", "PDF 超过 50 MiB 限制")
        else:
            if not isinstance(path_value, str):
                raise ProviderError("document_input", "模型文档任务缺少本地文件引用")
            path = Path(path_value)
            if not path.is_absolute() or path.suffix.lower() != ".pdf" or not path.is_file():
                raise ProviderError("document_input", "模型文档任务的 PDF 文件不可读")
            try:
                raw = await asyncio.to_thread(path.read_bytes)
            except OSError as exc:
                raise ProviderError("document_input", "模型文档任务无法读取 PDF") from exc
            if len(raw) > 50 * 1024 * 1024:
                raise ProviderError("document_input", "PDF 超过 50 MiB 限制")
            encoded = base64.b64encode(raw).decode("ascii")
            filename = path.name
        if schema is None:
            from researchgraph.model_document_contracts import ModelDocumentParseInput

            schema = ModelDocumentParseInput.model_json_schema()
        prompt = (
            "你是论文文档转录模型。只根据用户提供的 PDF 文件输出严格 JSON，"
            "按章节顺序给出正文段落，并尽量提取公式和表格。不要生成数据库 ID，"
            "不要补猜无法观察到的公式、表格或图片内容。公式至少保留原文或线性形式，"
            "表格无法确认结构时保留 raw_table_text 并标记 degraded 或 needs_review。"
        )
        # _build_body applies output-policy validation and endpoint-specific
        # limits.  Replace only the user message with the file-aware content.
        body = self._build_body(
            prompt,
            {
                "source_snapshot": payload.get("source_snapshot", {}),
                "modality": payload.get("modality", "pdf"),
            },
            schema,
        )
        original_user_content = body["messages"][1]["content"]
        try:
            output_schema = json.loads(original_user_content).get("output_schema", schema)
        except (TypeError, ValueError):
            output_schema = schema
        body["messages"][1]["content"] = [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "source_snapshot": payload.get("source_snapshot", {}),
                        "modality": payload.get("modality", "pdf"),
                        "output_schema": output_schema,
                    },
                    ensure_ascii=False,
                ),
            },
            {
                "type": "file",
                "file": {
                    "filename": filename,
                    "file_data": f"data:application/pdf;base64,{encoded}",
                },
            },
        ]
        body["stream"] = False
        body.pop("stream_options", None)
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        timeout = self.parameters.get("timeout_seconds", 30)
        try:
            async with asyncio.timeout(self.total_timeout):
                async with httpx.AsyncClient(
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx.Timeout(timeout, connect=min(timeout, 15)),
                ) as client:
                    response = await client.post(
                        self.base_url + "/chat/completions", json=body, headers=headers
                    )
        except TimeoutError:
            raise ProviderError("timeout", "模型文档请求达到总时限") from None
        except httpx.TimeoutException as exc:
            raise ProviderError("timeout", "模型文档请求超时") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("network", "模型文档网络连接失败") from exc
        if response.status_code >= 400:
            raise ProviderError("client", f"模型文档请求被拒绝（HTTP {response.status_code}）")
        try:
            envelope = response.json()
            content = envelope["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("response", "模型文档响应结构无效") from exc
        if not isinstance(content, str):
            raise ProviderError("response", "模型文档响应不是 JSON 文本")
        if self.key and self.key in content:
            raise ValueError("模型响应包含凭据，已拒绝保存")
        usage = envelope.get("usage")
        if isinstance(usage, dict):
            self.usage = {
                key: value
                for key, value in usage.items()
                if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                and type(value) is int
                and value >= 0
            }
        self.request_metadata = {
            "transport": "chat-file-v1",
            "file_name": filename,
            "file_bytes": len(encoded) * 3 // 4,
            "finish_reason": envelope.get("choices", [{}])[0].get("finish_reason", "unknown"),
        }
        return content

    @property
    def total_timeout(self) -> float:
        """Separate the inactivity timeout from a bounded active-generation deadline."""
        timeout = float(self.parameters.get("timeout_seconds", 30))
        return min(max(timeout * 2, timeout + 5), 300)
