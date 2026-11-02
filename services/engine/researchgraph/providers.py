"""Bounded text-only providers: no tools, database handles or filesystem capabilities."""

import asyncio
import json
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Protocol

import httpx

from researchgraph.model_adapters import adapt_request, with_documented_limits
from researchgraph.model_capabilities import ModelCapabilities, parse_capabilities


class Provider(Protocol):
    name: str
    model: str

    async def complete(self, prompt: str, data: dict[str, Any], schema: dict[str, Any]) -> str: ...


class MockProvider:
    name = "mock"
    model = "offline-extractive-fixture-v1"

    async def complete(self, prompt: str, data: dict[str, Any], schema: dict[str, Any]) -> str:
        await asyncio.sleep(0)
        if data.get("contract_version") == "reading-extraction-1.0" or schema.get("title") in {
            "PaperIntegrationProposal",
            "CoreSelectionProposal",
        }:
            from researchgraph.reading_mock import complete as reading_complete

            result = reading_complete(schema["title"], data)
            if data.get("wire_format") == "reading-compact-1":
                from researchgraph.reading_wire import compact_fixture

                result = compact_fixture(result)
            return json.dumps(result, ensure_ascii=False)
        if schema.get("title") == "KnowledgeExtractionBatch":
            from researchgraph.unified_mock import complete as unified_complete

            return json.dumps(unified_complete(data), ensure_ascii=False)
        if schema.get("title") == "TranslationRepair":
            return json.dumps(
                {
                    "items": [
                        {
                            "node_ref": x["node_ref"],
                            "label_zh": "离线补译验证",
                            "summary_zh": "Mock 仅验证显示字段更新，不代表真实翻译。",
                        }
                        for x in data["items"]
                    ]
                },
                ensure_ascii=False,
            )
        if schema.get("title") == "ConnectionTest":
            return '{"ok":true}'
        if schema.get("title") in {
            "EntityAlignmentBatch",
            "ComparabilityReport",
            "RelationInference",
        }:
            from researchgraph.reasoning_mock import complete

            return json.dumps(complete(schema["title"], data), ensure_ascii=False)
        if schema.get("title") == "PaperOutline":
            return json.dumps(
                {
                    "sections": [
                        dict(section_id=s["id"], role="other", paragraph_ids=s["paragraph_ids"])
                        for s in data["sections"]
                    ],
                    "unresolved_sections": [],
                }
            )
        claims, methods, findings = [], [], []
        concepts: list[dict[str, Any]] = []
        for index, evidence in enumerate(data["evidence_texts"]):
            text, eid = evidence["quote"].strip(), evidence["id"]
            if len(text) < 10:
                continue
            cited = bool(re.search(r"\b(?:et al|prior work|previous work)\b", text, re.I))
            method_refs = []
            if re.search(r"\b(?:method|algorithm|approach|framework)\b", text, re.I):
                ref = f"method-{index}"
                methods.append(
                    {
                        "local_ref": ref,
                        "name": text.splitlines()[0],
                        "mechanism": text,
                        "evidence_span_ids": [eid],
                    }
                )
                method_refs = [ref]
            if re.search(r"\b(?:result|accuracy|improv|achiev|success|score)\w*\b", text, re.I):
                # Deliberately conservative: no synthetic metric values invented by the mock.
                findings.append(
                    {"local_ref": f"finding-{index}", "statement": text, "evidence_span_ids": [eid]}
                )
            claims.append(
                {
                    "local_ref": f"claim-{index}",
                    "statement": text,
                    "origin": "cited_claim" if cited else "unknown",
                    "claim_type": "other",
                    "modality": "unknown",
                    "evidence": [
                        {"evidence_span_id": eid, "role": "cited_other" if cited else "direct"}
                    ],
                    "conditions": [],
                    "method_local_refs": method_refs,
                    "limitations": ["MockProvider 原文摘录，仅验证流程，未作科学语义抽取。"],
                }
            )
        return json.dumps(
            {
                "paper_id": data["paper_id"],
                "schema_version": data["schema_version"],
                "concepts": concepts,
                "methods": methods,
                "claims": claims,
                "findings": findings,
                "open_questions": [],
            },
            ensure_ascii=False,
        )


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
                        {"untrusted_source_data": data, "output_schema": schema}, ensure_ascii=False
                    ),
                },
            ],
        }
        for parameter in ("temperature", "top_p", "reasoning_effort"):
            if self.parameters.get(parameter) is not None:
                body[parameter] = self.parameters[parameter]
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
        if self.parameters.get("json_mode", True):
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
                        stream = ChatStream()
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
            content = envelope["choices"][0]["message"]["content"]
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

    @property
    def total_timeout(self) -> float:
        """Separate the inactivity timeout from a bounded active-generation deadline."""
        timeout = float(self.parameters.get("timeout_seconds", 30))
        return min(max(timeout * 2, timeout + 5), 300)


def provider_for(name: str, allow_network: bool) -> Provider:
    if name == "mock":
        return MockProvider()
    if name != "configured" or not allow_network:
        raise ValueError("真实模型需要明确同意发送当前论文的解析文本")
    return ConfiguredProvider()
