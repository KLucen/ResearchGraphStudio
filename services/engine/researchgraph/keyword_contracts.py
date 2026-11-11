"""Strict contracts for the optional D02 English search-keyword helper."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from researchgraph.core import StrictModel

SCHEMA_VERSION = "search_keywords.v1"
PROMPT_VERSION = "d02_search_keywords_v1"
TASK_KIND = "search_keywords"
TASK_NAME = "D02_SEARCH_KEYWORDS_V1"


class SearchKeywordsDraft(StrictModel):
    """Only short English terms are allowed; this is not a QA response."""

    english_queries: list[str] = Field(min_length=1, max_length=5)

    @field_validator("english_queries")
    @classmethod
    def clean_and_unique(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = " ".join(value.split()).strip()
            if not item:
                raise ValueError("english_queries must not contain blank values")
            if len(item) > 120:
                raise ValueError("english keyword is too long")
            key = item.casefold()
            if key in seen:
                raise ValueError("english_queries must be unique")
            seen.add(key)
            cleaned.append(item)
        return cleaned


class KeywordGenerate(StrictModel):
    document_version_id: str | None = None
    section_id: str | None = None
    question: str = Field(min_length=1, max_length=3000)
    local_hit_count: int = Field(default=0, ge=0, le=1000)
    allow_network: bool = False
    retry_failed: bool = False
    force_regenerate: bool = False

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("问题不能为空")
        return value.strip()

    @model_validator(mode="after")
    def must_be_local_miss(self) -> KeywordGenerate:
        if self.local_hit_count > 0:
            raise ValueError("D02 仅用于本地检索无命中时")
        return self


class KeywordUsage(StrictModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    calls: int = 0
    retry_count: int = 0
    cost: float | None = None
    usage_source: Literal["provider", "estimated", "unknown"] = "unknown"


class KeywordView(StrictModel):
    id: str | None
    paper_id: str
    document_version_id: str
    section_id: str | None = None
    question: str
    local_hit_count: int
    source_hash: str
    input_hash: str
    schema_version: str
    prompt_version: str
    provider_id: str
    model_id: str
    status: str | None
    keywords: SearchKeywordsDraft | None = None
    usage: KeywordUsage
    generated_at: str | None
    cache_hit: bool = False
    job_id: str | None = None
    error_code: str | None = None
    error: str | None = None
    stale_reason: str | None = None


def keyword_schema() -> dict[str, Any]:
    return {
        "title": "SearchKeywordsDraft",
        "type": "object",
        "additionalProperties": False,
        "required": ["english_queries"],
        "properties": {
            "english_queries": {
                "type": "array",
                "minItems": 1,
                "maxItems": 5,
                "items": {"type": "string", "minLength": 1, "maxLength": 120},
            }
        },
    }


def strict_json(raw: str) -> Any:
    def unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise ValueError("Duplicate JSON key")
            output[key] = value
        return output

    def invalid_constant(_value: str) -> Any:
        raise ValueError("Non-finite JSON constant")

    return json.loads(raw, object_pairs_hook=unique_keys, parse_constant=invalid_constant)


def validate_response(raw: str) -> SearchKeywordsDraft:
    return SearchKeywordsDraft.model_validate(strict_json(raw), strict=True)
