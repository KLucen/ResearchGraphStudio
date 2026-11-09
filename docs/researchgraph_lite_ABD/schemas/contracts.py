"""ResearchGraph Lite A+B+D reference contracts (Pydantic v2).

This is a standalone specification and contract test reference, not a drop-in
migration or claim that the currently deployed application implements it.
All document IDs, pages, spans, and provenance must be assigned/checked by the
backend, not invented by a language model.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SupportState(str, Enum):
    SUPPORTED = "supported"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


class CardField(StrictModel):
    text_zh: str = Field(max_length=250)
    evidence_span_ids: list[str] = Field(default_factory=list, max_length=5)
    status: SupportState

    @model_validator(mode="after")
    def evidence_consistency(self):
        if self.status == SupportState.SUPPORTED and (
            not self.text_zh or not self.evidence_span_ids
        ):
            raise ValueError("supported card field requires text and evidence")
        if self.status == SupportState.NOT_FOUND and self.evidence_span_ids:
            raise ValueError("not_found cannot cite evidence")
        return self


class PaperCardDraft(StrictModel):
    research_question: CardField
    motivation: CardField
    method: CardField
    contributions: list[CardField] = Field(max_length=3)
    results: list[CardField] = Field(max_length=3)
    limitations: list[CardField] = Field(max_length=3)
    overall_note: str = Field(default="", max_length=100)


class DifficultTerm(StrictModel):
    term_en: str = Field(min_length=1, max_length=100)
    hint_zh: str = Field(min_length=1, max_length=160)


class ReadingGuideDraft(StrictModel):
    section_id: str = Field(min_length=1)
    overview_zh: str = Field(min_length=1, max_length=400)
    key_points: list[str] = Field(min_length=1, max_length=4)
    reading_questions: list[str] = Field(min_length=2, max_length=3)
    difficult_terms: list[DifficultTerm] = Field(default_factory=list, max_length=3)
    evidence_span_ids: list[str] = Field(default_factory=list, max_length=8)
    needs_more_context: bool = False
    caveats: list[str] = Field(default_factory=list, max_length=4)


class EvidenceCitation(StrictModel):
    span_id: str = Field(min_length=1)
    reason_zh: str = Field(min_length=1, max_length=100)


class QAAnswerDraft(StrictModel):
    answer_zh: str = Field(min_length=1, max_length=1800)
    evidence_citations: list[EvidenceCitation] = Field(default_factory=list, max_length=5)
    insufficient_evidence: bool
    uncertainty_zh: str = Field(default="", max_length=400)
    suggest_expand_scope: bool = False

    @model_validator(mode="after")
    def evidence_for_answer(self):
        if not self.insufficient_evidence and not self.evidence_citations:
            raise ValueError("supported QA answer requires citation")
        return self


class SearchKeywordsDraft(StrictModel):
    english_queries: list[str] = Field(min_length=1, max_length=5)


class QueryScope(str, Enum):
    SELECTION = "selection"
    SECTION = "section"
    PAPER = "paper"


class AllowedSpan(StrictModel):
    span_id: str = Field(min_length=1)
    document_version_id: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    text_en: str = Field(min_length=1)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)

    @model_validator(mode="after")
    def page_order(self):
        if self.page_end < self.page_start:
            raise ValueError("page_end must not be earlier than page_start")
        return self


class CardInput(StrictModel):
    paper_title: str = Field(min_length=1)
    allowed_spans: list[AllowedSpan] = Field(min_length=1, max_length=30)
    language: Literal["zh-CN"] = "zh-CN"


class GuideInput(StrictModel):
    paper_title: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    section_heading: str = Field(min_length=1)
    depth: Literal["quick", "standard", "deep"] = "standard"
    allowed_spans: list[AllowedSpan] = Field(min_length=1, max_length=20)


class QAInput(StrictModel):
    question: str = Field(min_length=1, max_length=3000)
    scope: QueryScope = QueryScope.SECTION
    paper_title: str = Field(min_length=1)
    allowed_spans: list[AllowedSpan] = Field(min_length=1, max_length=5)
    optional_short_card: str | None = Field(default=None, max_length=1000)


class TokenUsage(StrictModel):
    task_run_id: str
    model_id: str
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    usage_source: Literal["provider", "estimated", "unknown"]
    retry_attempts: int = Field(default=0, ge=0)
    cache_hit: bool = False

    @model_validator(mode="after")
    def provider_usage_consistency(self):
        if self.usage_source == "provider" and (
            self.input_tokens is None or self.output_tokens is None
        ):
            raise ValueError("provider usage requires both token counts")
        return self


def iter_evidence_ids(payload: PaperCardDraft | ReadingGuideDraft | QAAnswerDraft):
    if isinstance(payload, PaperCardDraft):
        for field in (payload.research_question, payload.motivation, payload.method):
            yield from field.evidence_span_ids
        for group in (payload.contributions, payload.results, payload.limitations):
            for item in group:
                yield from item.evidence_span_ids
    elif isinstance(payload, ReadingGuideDraft):
        yield from payload.evidence_span_ids
    elif isinstance(payload, QAAnswerDraft):
        for cite in payload.evidence_citations:
            yield cite.span_id


def validate_references(
    output: PaperCardDraft | ReadingGuideDraft | QAAnswerDraft,
    allowed_span_ids: set[str],
    *,
    requested_section_id: str | None = None,
) -> None:
    """Must be run after model JSON validation and before persistence."""
    unknown = set(iter_evidence_ids(output)) - allowed_span_ids
    if unknown:
        raise ValueError(f"model cited span IDs outside this request: {sorted(unknown)}")
    if isinstance(output, ReadingGuideDraft) and (
        requested_section_id is None or output.section_id != requested_section_id
    ):
        raise ValueError("guide section_id differs from explicitly requested section")


def compute_cache_key(parts: dict) -> str:
    """Caller must pass only non-secret, stable, source/version-aware parts."""
    encoded = json.dumps(
        parts, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
