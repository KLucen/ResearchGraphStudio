"""Narrow HTTP adapter for an independently installed zotero-pdf2zh 4.1.8 server.

No upstream source is bundled. Only loopback service URLs and basename downloads
are accepted; API credentials never leave ResearchGraph's task-scoped proxy.
"""

import base64
import json
import math
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote

import httpx

from researchgraph.core import KnowledgeError
from researchgraph.translation_contracts import TranslationHealth, TranslationSettings, output_kinds

MAX_OUTPUT_BYTES = 200 * 1024 * 1024
MAX_JSON_BYTES = 2 * 1024 * 1024


class TranslationBridge:
    def __init__(
        self,
        service_url: str,
        *,
        before_request: Callable[[], Awaitable[None]] | None = None,
        service_token: str | None = None,
        expected_version: str = "4.1.8",
    ) -> None:
        self.service_url = TranslationSettings(service_url=service_url).service_url
        self.before_request = before_request
        self.headers = {"Authorization": f"Bearer {service_token}"} if service_token else {}
        self.expected_version = expected_version

    async def _json(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                trust_env=False, follow_redirects=False, timeout=30
            ) as client:
                if self.before_request is not None:
                    await self.before_request()
                async with client.stream(
                    method, self.service_url + path, json=body, headers=self.headers
                ) as response:
                    if response.status_code != 200:
                        raise KnowledgeError(
                            "TRANSLATION_SERVICE_FAILED", "本机翻译服务未返回成功响应"
                        )
                    raw = bytearray()
                    async for part in response.aiter_bytes():
                        raw.extend(part)
                        if len(raw) > MAX_JSON_BYTES:
                            raise ValueError("response too large")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("object required")
            return value
        except KnowledgeError:
            raise
        except (httpx.HTTPError, ValueError, TypeError):
            raise KnowledgeError(
                "TRANSLATION_SERVICE_UNAVAILABLE",
                "无法读取本机翻译服务；请确认独立服务正在运行且地址正确",
            ) from None

    async def check(self) -> TranslationHealth:
        try:
            health = await self._json("GET", "/health")
            version = str(health.get("version", ""))
            if health.get("status") != "ok" or version != self.expected_version:
                return TranslationHealth(
                    available=False,
                    status="unsupported_version",
                    version=version or None,
                    message="翻译服务版本与当前运行适配器不一致，请检查安装版本与启动模式",
                )
            tasks = await self._json("GET", "/api/tasks")
            if tasks.get("status") != "success" or not isinstance(tasks.get("tasks"), list):
                raise KnowledgeError("TRANSLATION_SERVICE_PROTOCOL", "翻译服务任务协议不兼容")
            active = sum(
                1 for item in tasks["tasks"] if isinstance(item, dict) and item.get("active")
            )
            return TranslationHealth(
                available=True,
                status="busy" if active else "ready",
                version=version,
                active_tasks=active,
                message="外部服务有活动任务，请等待其结束" if active else "本机翻译服务可用",
            )
        except KnowledgeError as error:
            if error.code == "TRANSLATION_RUNTIME_OWNERSHIP_LOST":
                raise
            return TranslationHealth(
                available=False,
                status="unavailable",
                message="无法确认本机翻译服务状态；请检查地址与服务版本",
            )

    async def submit(
        self,
        content: bytes,
        stem: str,
        proxy_url: str,
        proxy_token: str,
        model: str,
        *,
        output_mode: str = "both",
    ) -> dict[str, Any]:
        kinds = output_kinds(output_mode)
        return await self._json(
            "POST",
            "/translate",
            {
                "fileName": stem + ".pdf",
                "fileContent": base64.b64encode(content).decode("ascii"),
                "asyncJob": True,
                "engine": "pdf2zh_next",
                "next_service": "openai",
                "sourceLang": "en",
                "targetLang": "zh-CN",
                "mono": "mono" in kinds,
                "dual": "dual" in kinds,
                "noMono": "mono" not in kinds,
                "noDual": "dual" not in kinds,
                "dualMode": "LR",
                "noWatermark": True,
                "qps": 1,
                "poolSize": 1,
                "disableGlossary": True,
                "ignoreCache": True,
                "llm_api": {
                    "apiKey": proxy_token,
                    "apiUrl": proxy_url,
                    "model": model,
                    "extraData": {
                        "openai_timeout": 120,
                        "openai_enable_json_mode": False,
                        "openai_send_temprature": False,
                        "openai_send_reasoning_effort": False,
                    },
                },
            },
        )

    async def poll(self, task_id: str) -> dict[str, Any] | None:
        tasks = await self._json("GET", "/api/tasks")
        for item in tasks.get("tasks", []):
            if isinstance(item, dict) and item.get("taskId") == task_id:
                return item
        history = await self._json("GET", "/api/history")
        for item in history.get("history", []):
            if isinstance(item, dict) and item.get("taskId") == task_id:
                return {**item, "active": False, "finished": True}
        return None

    async def download(self, filename: str) -> bytes:
        if (
            not filename
            or len(filename) > 200
            or "/" in filename
            or "\\" in filename
            or ":" in filename
            or not filename.endswith(".pdf")
            or filename in {".", ".."}
        ):
            raise KnowledgeError("TRANSLATION_OUTPUT_INVALID", "翻译服务返回了无效文件名")
        try:
            async with httpx.AsyncClient(
                trust_env=False, follow_redirects=False, timeout=60
            ) as client:
                if self.before_request is not None:
                    await self.before_request()
                async with client.stream(
                    "GET",
                    self.service_url + "/translatedFile/" + quote(filename, safe=""),
                    headers=self.headers,
                ) as response:
                    if response.status_code != 200:
                        raise ValueError("download failed")
                    content = bytearray()
                    async for part in response.aiter_bytes():
                        content.extend(part)
                        if len(content) > MAX_OUTPUT_BYTES:
                            raise ValueError("output too large")
            return bytes(content)
        except KnowledgeError:
            raise
        except (httpx.HTTPError, ValueError):
            raise KnowledgeError(
                "TRANSLATION_DOWNLOAD_FAILED", "无法安全下载译文 PDF，或文件超过 200 MiB"
            ) from None


def progress_value(value: Any) -> float:
    if type(value) not in {int, float} or not math.isfinite(value):
        return 0
    return min(99.0, max(0.0, float(value)))


def output_names(result: dict[str, Any], stem: str, *, output_mode: str = "both") -> dict[str, str]:
    expected = set(output_kinds(output_mode))
    nested = result.get("result")
    files = result.get("fileList")
    if files is None and isinstance(nested, dict):
        files = nested.get("fileList")
    if not isinstance(files, list):
        raise KnowledgeError("TRANSLATION_OUTPUT_INVALID", "翻译结果未包含可验证文件列表")
    outputs: dict[str, str] = {}
    for name in files:
        if not isinstance(name, str):
            raise KnowledgeError("TRANSLATION_OUTPUT_INVALID", "翻译结果文件名格式不兼容")
        for kind, suffix in (("mono", "mono"), ("dual", "LR_dual")):
            if kind in expected and name == f"{stem}.no_watermark.zh-CN.{suffix}.pdf":
                if kind in outputs:
                    raise KnowledgeError("TRANSLATION_OUTPUT_INVALID", "翻译结果含重复文件")
                outputs[kind] = name
    if set(outputs) != expected:
        raise KnowledgeError("TRANSLATION_OUTPUT_INVALID", "缺少当前任务所选输出模式的 PDF")
    return outputs
