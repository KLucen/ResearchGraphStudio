"""Bounded Chat Completions SSE assembly; partial JSON is never a completed response."""

import codecs
import json
from typing import Any


class ChatStream:
    def __init__(self) -> None:
        self.decoder = codecs.getincrementaldecoder("utf-8")()
        self.buffer = ""
        self.event: list[str] = []
        self.parts: list[str] = []
        self.reasoning_characters = 0
        self.content_characters = 0
        self.content_bytes = 0
        self.finish_reason: str | None = None
        self.done = False
        self.usage: dict[str, Any] = {}

    def feed(self, part: bytes) -> None:
        self.buffer += self.decoder.decode(part)
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            line = line.rstrip("\r")
            if not line:
                self.dispatch()
            elif line.startswith("data:"):
                self.event.append(line[5:].lstrip(" "))

    def dispatch(self) -> None:
        from researchgraph.providers import ProviderError

        if not self.event:
            return
        raw, self.event = "\n".join(self.event), []
        if raw == "[DONE]":
            self.done = True
            return
        if self.done:
            raise ProviderError("response", "模型在流结束后继续返回数据")
        value = json.loads(raw)
        if not isinstance(value, dict) or value.get("error"):
            raise ProviderError("incomplete_stream", "模型流返回错误，已停止；未自动重发")
        if isinstance(value.get("usage"), dict):
            self.usage = value["usage"]
        choices = value.get("choices", [])
        if not isinstance(choices, list) or len(choices) > 1:
            raise ProviderError("response", "模型流包含无法识别的多路结果")
        if not choices:
            return
        choice = choices[0]
        if not isinstance(choice, dict):
            raise ProviderError("response", "模型流结果格式无效")
        if choice.get("index", 0) != 0:
            raise ProviderError("response", "模型流返回了非预期的结果序号")
        delta = choice.get("delta", {})
        if not isinstance(delta, dict):
            raise ProviderError("response", "模型流增量格式无效")
        if delta.get("tool_calls") or delta.get("function_call"):
            raise ProviderError("response", "模型返回了工具调用，抽取仅允许 JSON 文本")
        text = delta.get("content")
        if text is not None:
            if not isinstance(text, str) or (self.finish_reason is not None and text):
                raise ProviderError("response", "模型流文本格式或结束顺序无效")
            self.content_bytes += len(text.encode("utf-8"))
            if self.content_bytes > 2_000_000:
                raise ProviderError("response", "模型文本超过 2 MB 限制")
            self.parts.append(text)
            self.content_characters += len(text)
        reasoning = delta.get("reasoning_content", delta.get("reasoning"))
        if isinstance(reasoning, str):
            # Keep counters only; reasoning is not scientific content or an evidence source.
            self.reasoning_characters += len(reasoning)
        if choice.get("finish_reason") is not None:
            self.finish_reason = choice["finish_reason"]

    def envelope(self) -> dict[str, Any]:
        from researchgraph.providers import ProviderError

        self.buffer += self.decoder.decode(b"", final=True)
        if self.buffer.startswith("data:"):
            self.event.append(self.buffer[5:].strip())
        self.dispatch()
        if not self.done or self.finish_reason not in {"stop", "length"}:
            raise ProviderError(
                "incomplete_stream", "模型响应流未正常完成；部分输出已保留，未入库或自动重发"
            )
        return {
            "choices": [
                {"message": {"content": "".join(self.parts)}, "finish_reason": self.finish_reason}
            ],
            "usage": self.usage,
        }
