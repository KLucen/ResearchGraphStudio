"""Bounded text-only providers: no tools, database handles or filesystem capabilities."""

import asyncio
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Protocol


class Provider(Protocol):
    name: str
    model: str

    async def complete(self, prompt: str, data: dict[str, Any], schema: dict[str, Any]) -> str: ...


class MockProvider:
    name = "mock"
    model = "offline-extractive-fixture-v1"

    async def complete(self, prompt: str, data: dict[str, Any], schema: dict[str, Any]) -> str:
        await asyncio.sleep(0)
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


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise ValueError("服务重定向被拒绝，避免向其他地址发送授权文本或密钥")


class ConfiguredProvider:
    name = "configured"

    def __init__(self) -> None:
        self.base_url = os.environ.get("RGS_MODEL_BASE_URL", "").rstrip("/")
        self.model = os.environ.get("RGS_MODEL_NAME", "")
        self.key = os.environ.get("RGS_MODEL_API_KEY", "")
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

    async def complete(self, prompt: str, data: dict[str, Any], schema: dict[str, Any]) -> str:
        return await asyncio.to_thread(self._request, prompt, data, schema)

    def _request(self, prompt: str, data: dict[str, Any], schema: dict[str, Any]) -> str:
        body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
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
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        try:
            with opener.open(request, timeout=30) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError("模型响应超过 2 MB 限制")
            content = json.loads(raw)["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ValueError("模型没有返回文本 JSON")
            return content
        except urllib.error.HTTPError as error:
            raise ValueError(f"模型 HTTP {error.code}，请检查配置或额度") from None
        except (urllib.error.URLError, KeyError, IndexError, TypeError) as error:
            raise ValueError("模型请求失败或响应结构无效") from error


def provider_for(name: str, allow_network: bool) -> Provider:
    if name == "mock":
        return MockProvider()
    if name != "configured" or not allow_network:
        raise ValueError("真实模型需要明确同意发送当前论文的解析文本")
    return ConfiguredProvider()
