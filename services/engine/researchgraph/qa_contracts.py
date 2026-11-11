"""Strict Lite D01 grounded QA contracts and validation."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from researchgraph.core import StrictModel

SCHEMA_VERSION = "grounded_qa.v1"
PROMPT_VERSION = "d01_grounded_qa_v1"
TASK_KIND = "grounded_qa"
TASK_NAME = "D01_GROUNDED_QA_V1"
QueryScope = Literal["selection", "section", "paper"]


class AllowedSpan(StrictModel):
    span_id: str = Field(min_length=1, max_length=200)
    document_version_id: str = Field(min_length=1, max_length=200)
    section_id: str = Field(min_length=1, max_length=200)
    text_en: str = Field(min_length=1, max_length=4000)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)

    @model_validator(mode="after")
    def page_order(self) -> AllowedSpan:
        if self.page_end < self.page_start:
            raise ValueError("page_end must not be earlier than page_start")
        return self


class EvidenceCitation(StrictModel):
    span_id: str = Field(min_length=1, max_length=200)
    reason_zh: str = Field(min_length=1, max_length=100)


class QAAnswerDraft(StrictModel):
    answer_zh: str = Field(min_length=1, max_length=1800)
    evidence_citations: list[EvidenceCitation] = Field(default_factory=list, max_length=5)
    insufficient_evidence: bool
    uncertainty_zh: str = Field(default="", max_length=400)
    suggest_expand_scope: bool = False

    @field_validator("answer_zh", "uncertainty_zh")
    @classmethod
    def nonblank_if_present(cls, value: str) -> str:
        if value and not value.strip():
            raise ValueError("text fields must not contain only whitespace")
        return value

    @field_validator("evidence_citations")
    @classmethod
    def unique_citations(cls, values: list[EvidenceCitation]) -> list[EvidenceCitation]:
        ids = [item.span_id for item in values]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence citations must be unique")
        return values

    @model_validator(mode="after")
    def evidence_for_answer(self) -> QAAnswerDraft:
        if not self.insufficient_evidence and not self.evidence_citations:
            raise ValueError("supported QA answer requires citation")
        return self


class QAGenerate(StrictModel):
    document_version_id: str | None = None
    section_id: str | None = None
    scope: QueryScope = "section"
    question: str = Field(min_length=1, max_length=3000)
    selection_span_ids: list[str] = Field(default_factory=list, max_length=5)
    optional_short_card: str | None = Field(default=None, max_length=1000)
    allow_network: bool = False
    retry_failed: bool = False
    force_regenerate: bool = False

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("问题不能为空")
        return value.strip()

    @field_validator("selection_span_ids")
    @classmethod
    def unique_selection(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("selection_span_ids must be unique")
        return values

    @model_validator(mode="after")
    def scope_requirements(self) -> QAGenerate:
        if self.scope == "selection" and not self.selection_span_ids:
            raise ValueError("selection scope requires selection_span_ids")
        if self.scope != "selection" and self.selection_span_ids:
            raise ValueError("selection_span_ids only applies to selection scope")
        return self


class QAUsage(StrictModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    calls: int = 0
    retry_count: int = 0
    cost: float | None = None
    usage_source: Literal["provider", "estimated", "unknown"] = "unknown"


class QAEvidence(StrictModel):
    span_id: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=4000)
    section_id: str


class QAView(StrictModel):
    id: str | None
    paper_id: str
    document_version_id: str
    section_id: str | None = None
    scope: QueryScope
    question: str
    source_hash: str
    input_hash: str
    schema_version: str
    prompt_version: str
    provider_id: str
    model_id: str
    status: Literal["PENDING", "COMPLETED", "FAILED", "STALE"] | None
    answer: QAAnswerDraft | None = None
    usage: QAUsage
    generated_at: str | None
    cache_hit: bool = False
    job_id: str | None = None
    error_code: str | None = None
    error: str | None = None
    stale_reason: str | None = None
    retrieval_spans: list[QAEvidence] = Field(default_factory=list, max_length=5)


def qa_schema() -> dict[str, Any]:
    return {
        "title": "QAAnswerDraft",
        "type": "object",
        "additionalProperties": False,
        "required": ["answer_zh", "insufficient_evidence"],
        "properties": {
            "answer_zh": {"type": "string", "minLength": 1, "maxLength": 1800},
            "evidence_citations": {
                "type": "array",
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["span_id", "reason_zh"],
                    "properties": {
                        "span_id": {"type": "string", "minLength": 1, "maxLength": 200},
                        "reason_zh": {"type": "string", "minLength": 1, "maxLength": 100},
                    },
                },
            },
            "insufficient_evidence": {"type": "boolean"},
            "uncertainty_zh": {"type": "string", "maxLength": 400},
            "suggest_expand_scope": {"type": "boolean"},
        },
    }


def strict_json(raw: str) -> Any:
    def unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(_value: str) -> Any:
        raise ValueError("Non-finite JSON constant")

    return json.loads(raw, object_pairs_hook=unique_keys, parse_constant=invalid_constant)


def validate_response(raw: str, *, allowed_span_ids: set[str]) -> QAAnswerDraft:
    answer = QAAnswerDraft.model_validate(strict_json(raw), strict=True)
    unknown = {item.span_id for item in answer.evidence_citations} - allowed_span_ids
    if unknown:
        raise ValueError(f"model cited span IDs outside this request: {sorted(unknown)}")
    return answer
