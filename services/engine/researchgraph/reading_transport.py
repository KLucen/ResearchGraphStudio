"""Source-free model DTOs, bound to immutable source identity by the application.

This protocol is only for its versioned Prompt. Historical compact responses and
their frozen Schema/signatures keep using reading_wire unchanged.
"""

import copy
import json
import re
from pathlib import Path
from typing import Any

from researchgraph import reading_wire
from researchgraph.reading_prompt_contract import assert_generated_rules
from researchgraph.reading_prompt_contract import generated_rules as schema_rules

PROMPT = "P02_reading_extract_compact_v4"
FORMAT = "reading-semantic-1"
CONTEXT_KEYS = {"document_version_id", "chunk_id", "source_language"}
BOUND_FIELDS = {"contract_version", "wire_format", *CONTEXT_KEYS}
ROOT_FIELDS = {"items", "links", "warnings"}


def output_schema() -> dict[str, Any]:
    """Derive all scientific fields and constraints from the existing domain DTO."""
    schema = reading_wire.current_output_schema()
    for field in BOUND_FIELDS:
        schema["properties"].pop(field, None)
    schema["required"] = [f for f in schema["required"] if f not in BOUND_FIELDS]
    source_text = schema["$defs"]["SourceText"]
    source_text["description"] = (
        "A string is authoritative text in the input's source_language, without translation."
    )
    object_text = source_text["anyOf"][0]
    object_text["properties"]["language"]["description"] = (
        "Omit when equal to the source_language supplied in input; override for other languages."
    )
    schema["title"] = "ReadingSemanticBatch"
    return schema


def detect_language(text: str) -> str:
    """A transport default from script counts, never a scientific language judgment."""
    chinese = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\U00020000-\U0002ebef]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return "zh" if chinese > latin else "en" if latin else "und"


def loads(raw: str) -> dict[str, Any]:
    """Strict JSON only; no punctuation repair, field dropping or text rewriting."""

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key; model response rejected")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError("Non-JSON constant; model response rejected")

    value = json.loads(raw, object_pairs_hook=unique, parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise ValueError("模型输出必须为知识对象")
    return value


def bind(
    data: dict[str, Any],
    *,
    document_version_id: str,
    chunk_id: str,
    source_language: str,
    changes: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Bind trusted request identity before unchanged domain/evidence validation.

    No caller may obtain source identity from model JSON. Unknown fields and
    invalid types fail rather than being hidden by the trusted envelope.
    """
    if set(data) - ROOT_FIELDS:
        raise ValueError("Schema 校验失败：语义输出仅允许 items、links、warnings")
    if any(not isinstance(data.get(field), list) for field in ("items", "links")):
        raise ValueError("Schema 校验失败：必须显式返回 items 和 links 数组")
    if "warnings" in data and not isinstance(data["warnings"], list):
        raise ValueError("Schema 校验失败：warnings 必须为数组")
    if (
        not isinstance(document_version_id, str)
        or not 1 <= len(document_version_id) <= 160
        or not isinstance(chunk_id, str)
        or not 1 <= len(chunk_id) <= 160
        or not isinstance(source_language, str)
        or not 2 <= len(source_language) <= 35
    ):
        raise ValueError("可信抽取上下文缺少有效版本、批次或默认语言")
    # Binding adds defaults and can make different wire objects look identical.
    # Reject conflicting raw references first; exact duplicates may continue to
    # the ordinary full validation/deduplication, which records removed indices.
    first: dict[str, str] = {}
    for item in data["items"]:
        if not isinstance(item, dict) or not isinstance(item.get("local_ref"), str):
            continue
        ref = item["local_ref"]
        encoded = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if ref in first and first[ref] != encoded:
            raise ValueError("Schema 校验失败：相同 local_ref 的原始候选内容不同，未规范化合并")
        first[ref] = encoded
    value = {
        **copy.deepcopy(data),
        "contract_version": "reading-extraction-1.0",
        "wire_format": reading_wire.FORMAT,
        "document_version_id": document_version_id,
        "chunk_id": chunk_id,
        "source_language": source_language,
    }
    if changes is not None:
        changes.extend(
            {"path": field, "rule": "engine-bound-source-v1"} for field in sorted(BOUND_FIELDS)
        )
    return reading_wire.expand(value, changes)


def fixture(data: dict[str, Any], language: str = "en") -> dict[str, Any]:
    """Exact-value fixture encoder for explicit offline providers, not product use."""
    value = reading_wire.compact_fixture(data, language)
    return {key: item for key, item in value.items() if key not in BOUND_FIELDS}


def generated_contract() -> str:
    """The Prompt's structural rules are generated from the very output Schema sent."""
    return schema_rules(output_schema(), FORMAT)


def assert_prompt_contract(prompt: str | None = None) -> None:
    if prompt is None:
        prompt = (Path(__file__).parent / "prompts" / (PROMPT + ".md")).read_text(encoding="utf-8")
    assert_generated_rules(prompt, generated_contract())
