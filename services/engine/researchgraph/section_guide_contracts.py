"""Strict A01 section reading guide contract and validation."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from researchgraph.core import StrictModel

SCHEMA_VERSION = "reading_guide.v1"
PROMPT_VERSION = "a01_section_guide_v1"
TASK_KIND = "section_guide"
TASK_NAME = "A01_SECTION_GUIDE_V1"
Depth = Literal["quick", "standard", "deep"]


class DifficultTerm(StrictModel):
    term_en: str = Field(min_length=1, max_length=100)
    hint_zh: str = Field(min_length=1, max_length=160)


class ReadingGuideDraft(StrictModel):
    section_id: str = Field(min_length=1, max_length=200)
    overview_zh: str = Field(min_length=1, max_length=400)
    key_points: list[str] = Field(min_length=1, max_length=4)
    reading_questions: list[str] = Field(min_length=2, max_length=3)
    difficult_terms: list[DifficultTerm] = Field(default_factory=list, max_length=3)
    evidence_span_ids: list[str] = Field(default_factory=list, max_length=8)
    needs_more_context: bool = False
    caveats: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("key_points", "reading_questions", "caveats")
    @classmethod
    def nonblank_items(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("guide list items must not be blank")
        return values

    @field_validator("evidence_span_ids")
    @classmethod
    def unique_evidence_ids(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("evidence_span_ids must be unique")
        return values

    @model_validator(mode="after")
    def quick_shape_is_checked_by_caller(self) -> ReadingGuideDraft:
        return self


class GuideGenerate(StrictModel):
    document_version_id: str | None = None
    section_id: str = Field(min_length=1, max_length=200)
    depth: Depth = "standard"
    allow_network: bool = False
    retry_failed: bool = False
    force_regenerate: bool = False


class GuideUsage(StrictModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    calls: int = 0
    retry_count: int = 0
    cost: float | None = None
    usage_source: Literal["provider", "unknown"] = "unknown"


class GuideEvidence(StrictModel):
    span_id: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=320)


class GuideView(StrictModel):
    id: str | None
    paper_id: str
    document_version_id: str
    section_id: str
    depth: Depth
    source_hash: str
    input_hash: str
    schema_version: str
    prompt_version: str
    provider_id: str
    model_id: str
    status: Literal["PENDING", "COMPLETED", "FAILED", "STALE"] | None
    guide: ReadingGuideDraft | None = None
    usage: GuideUsage
    generated_at: str | None
    cache_hit: bool = False
    job_id: str | None = None
    error_code: str | None = None
    error: str | None = None
    stale_reason: str | None = None
    evidence: list[GuideEvidence] = Field(default_factory=list, max_length=8)


def guide_schema() -> dict[str, Any]:
    return {
        "title": "ReadingGuideDraft",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "section_id",
            "overview_zh",
            "key_points",
            "reading_questions",
        ],
        "properties": {
            "section_id": {"type": "string", "minLength": 1, "maxLength": 200},
            "overview_zh": {"type": "string", "minLength": 1, "maxLength": 400},
            "key_points": {
                "type": "array",
                "minItems": 1,
                "maxItems": 4,
                "items": {"type": "string", "minLength": 1},
            },
            "reading_questions": {
                "type": "array",
                "minItems": 2,
                "maxItems": 3,
                "items": {"type": "string", "minLength": 1},
            },
            "difficult_terms": {
                "type": "array",
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["term_en", "hint_zh"],
                    "properties": {
                        "term_en": {"type": "string", "minLength": 1, "maxLength": 100},
                        "hint_zh": {"type": "string", "minLength": 1, "maxLength": 160},
                    },
                },
            },
            "evidence_span_ids": {
                "type": "array",
                "maxItems": 8,
                "items": {"type": "string", "minLength": 1},
            },
            "needs_more_context": {"type": "boolean"},
            "caveats": {
                "type": "array",
                "maxItems": 4,
                "items": {"type": "string", "minLength": 1},
            },
        },
    }


def strict_json(raw: str) -> Any:
    def unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate JSON key")
            value[key] = item
        return value

    def invalid_constant(_value: str) -> Any:
        raise ValueError("Non-finite JSON constant")

    return json.loads(raw, object_pairs_hook=unique_keys, parse_constant=invalid_constant)


def validate_response(
    raw: str,
    *,
    requested_section_id: str,
    allowed_span_ids: set[str],
    depth: Depth,
) -> ReadingGuideDraft:
    guide = ReadingGuideDraft.model_validate(strict_json(raw), strict=True)
    if guide.section_id != requested_section_id:
        raise ValueError("guide section_id differs from explicitly requested section")
    unknown = set(guide.evidence_span_ids) - allowed_span_ids
    if unknown:
        raise ValueError(f"model cited span IDs outside this request: {sorted(unknown)}")
    if depth == "quick" and len(guide.key_points) > 2:
        raise ValueError("quick guide must contain at most two key points")
    return guide
