"""A02/A03 wire contracts and conservative independently validated partial results."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Literal

from pydantic import Field, ValidationError, field_validator

from researchgraph.core import StrictModel
from researchgraph.section_guide_contracts import GuideUsage, strict_json

SCHEMA_VERSION: Literal["section_reading_analysis.v1"] = "section_reading_analysis.v1"
PROMPT_VERSION = "A02_bilingual_argument_annotation_v1"
TASK_KIND = "section_close_reading"
CHECK_SCHEMA_VERSION = "understanding_check.v1"
CHECK_PROMPT_VERSION = "A03_understanding_check_v1"
CHECK_TASK_KIND = "understanding_check"
HighlightType = Literal["THESIS", "CONCEPT", "EVIDENCE", "COUNTERARGUMENT", "METHOD"]
ParagraphFunction = Literal[
    "INTRODUCE_PROBLEM",
    "DEFINE_CONCEPT",
    "STATE_CLAIM",
    "EXPLAIN_METHOD",
    "PRESENT_EVIDENCE",
    "HANDLE_OBJECTION",
    "DISCUSS_LIMITATION",
    "SUMMARIZE_TRANSITION",
    "OTHER",
]
CheckResult = Literal["ADEQUATE", "PARTIAL", "MISCONCEPTION", "UNCERTAIN"]


class ArgumentHighlight(StrictModel):
    type: HighlightType
    quote_en: str = Field(min_length=1, max_length=1200)
    occurrence_index: int = Field(ge=0)


class ParagraphAnalysis(StrictModel):
    paragraph_id: str = Field(min_length=1, max_length=200)
    translation_zh: str = Field(min_length=1)
    paragraph_function: ParagraphFunction
    logic_role_zh: str = Field(min_length=1, max_length=1200)
    critical_note_zh: str = Field(max_length=1600)
    reading_question_zh: str | None = Field(max_length=1000)
    highlights: list[ArgumentHighlight] = Field(max_length=30)
    related_graph_node_ids: list[str] = Field(max_length=20)

    @field_validator("translation_zh", "logic_role_zh")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("required text cannot be blank")
        return value


class SectionArgument(StrictModel):
    logic_chain_zh: list[str] = Field(min_length=2, max_length=5)
    core_claim_zh: str | None = Field(max_length=1600)
    strong_point_zh: str | None = Field(max_length=1600)
    question_to_verify_zh: str | None = Field(max_length=1600)

    @field_validator("logic_chain_zh")
    @classmethod
    def nonblank(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 1200 for value in values):
            raise ValueError("logic chain items must be short nonblank strings")
        return values


class SectionReadingAnalysis(StrictModel):
    schema_version: Literal["section_reading_analysis.v1"]
    paragraphs: list[ParagraphAnalysis]
    section_argument: SectionArgument | None


class UnderstandingCheck(StrictModel):
    check_result: CheckResult
    correct_points_zh: list[str] = Field(max_length=8)
    missing_or_mistaken_zh: list[str] = Field(max_length=8)
    feedback_zh: str = Field(min_length=1, max_length=2400)
    follow_up_question_zh: str = Field(min_length=1, max_length=1200)

    @field_validator("feedback_zh", "follow_up_question_zh")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("feedback cannot be blank")
        return value

    @field_validator("correct_points_zh", "missing_or_mistaken_zh")
    @classmethod
    def short_items(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 1200 for value in values):
            raise ValueError("feedback points must be short nonblank strings")
        return values


class CloseReadingGenerate(StrictModel):
    document_version_id: str | None = None
    paragraph_ids: list[str] = Field(min_length=1, max_length=100)
    allow_network: bool = False
    force_regenerate: bool = False
    retry_missing_of: str | None = None

    @field_validator("paragraph_ids")
    @classmethod
    def unique_ids(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)) or any(not value.strip() for value in values):
            raise ValueError("paragraph_ids must be unique nonblank IDs")
        return values


class UnderstandingCheckGenerate(CloseReadingGenerate):
    user_explanation: str = Field(min_length=1, max_length=4000)
    graph_node_ids: list[str] = Field(default_factory=list, max_length=3)
    overview_result_id: str | None = None

    @field_validator("user_explanation")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("user_explanation cannot be blank")
        return value


class ReadingParagraph(StrictModel):
    paragraph_id: str
    text_en: str
    text_hash: str
    page_start: int
    page_end: int
    ordinal: int
    span_ids: list[str]


class ParagraphsView(StrictModel):
    paper_id: str
    document_version_id: str
    section_id: str
    section_title: str
    source_hash: str
    paragraphs: list[ReadingParagraph]
    estimated_source_tokens: int
    suggested_max_source_tokens: int = 2000


class ReadingRange(StrictModel):
    paragraph_ids: list[str]
    range_label: str
    full_section: bool
    range_hash: str


class ReadingBudget(StrictModel):
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_total_tokens: int
    estimated_source_tokens: int
    estimate_only: bool = True
    warning: str | None = None


class CloseReadingView(StrictModel):
    id: str
    paper_id: str
    document_version_id: str
    section_id: str
    source_hash: str
    input_hash: str
    schema_version: str
    prompt_version: str
    provider_id: str
    model_id: str
    status: Literal["PENDING", "COMPLETED", "INCOMPLETE", "FAILED", "STALE"]
    range: ReadingRange
    analysis: SectionReadingAnalysis | None
    missing_paragraph_ids: list[str]
    warnings: list[str]
    usage: GuideUsage
    new_calls: int = 0
    estimated: ReadingBudget
    generated_at: str
    cache_hit: bool = False
    job_id: str | None = None
    error_code: str | None = None
    error: str | None = None
    stale_reason: str | None = None
    retry_of: str | None = None


class UnderstandingCheckView(StrictModel):
    id: str
    paper_id: str
    document_version_id: str
    section_id: str
    source_hash: str
    input_hash: str
    schema_version: str
    prompt_version: str
    provider_id: str
    model_id: str
    status: Literal["PENDING", "COMPLETED", "FAILED", "STALE"]
    range: ReadingRange
    user_explanation: str
    check: UnderstandingCheck | None
    graph_node_ids: list[str]
    overview_result_id: str | None
    usage: GuideUsage
    new_calls: int = 0
    estimated: ReadingBudget
    generated_at: str
    cache_hit: bool = False
    job_id: str | None = None
    error_code: str | None = None
    error: str | None = None
    stale_reason: str | None = None


def analysis_schema() -> dict[str, Any]:
    schema = SectionReadingAnalysis.model_json_schema()
    # A missing summary is a local partial-result representation, never an
    # allowed omission in the provider contract.
    schema["properties"]["section_argument"] = {"$ref": "#/$defs/SectionArgument"}
    return schema


def check_schema() -> dict[str, Any]:
    return UnderstandingCheck.model_json_schema()


def _partial_root(raw: str) -> dict[str, Any]:
    """Read only complete values in a truncated root/paragraph array.

    No missing brackets/quotes or text are manufactured. The scanner follows
    JSON grammar from character zero, and never searches arbitrary substrings
    for plausible paragraph objects. Duplicate/nonfinite JSON remains rejected.
    """

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def constant(_value: str) -> Any:
        raise ValueError("Non-finite JSON constant")

    decoder = json.JSONDecoder(object_pairs_hook=pairs, parse_constant=constant)
    offset = 0

    def whitespace() -> None:
        nonlocal offset
        while offset < len(raw) and raw[offset].isspace():
            offset += 1

    whitespace()
    if offset >= len(raw) or raw[offset] != "{":
        raise ValueError("Expected a JSON object")
    offset += 1
    root: dict[str, Any] = {}
    try:
        while True:
            whitespace()
            key, offset = decoder.raw_decode(raw, offset)
            if (
                not isinstance(key, str)
                or key not in {"schema_version", "paragraphs", "section_argument"}
                or key in root
            ):
                raise ValueError("Invalid or duplicate root key")
            whitespace()
            if offset >= len(raw) or raw[offset] != ":":
                break
            offset += 1
            whitespace()
            if key == "paragraphs":
                if offset >= len(raw) or raw[offset] != "[":
                    break
                offset += 1
                root[key] = []
                while True:
                    whitespace()
                    if offset < len(raw) and raw[offset] == "]":
                        offset += 1
                        break
                    item, offset = decoder.raw_decode(raw, offset)
                    root[key].append(item)
                    whitespace()
                    if offset < len(raw) and raw[offset] == ",":
                        offset += 1
                        continue
                    if offset < len(raw) and raw[offset] == "]":
                        offset += 1
                        break
                    return root
            else:
                root[key], offset = decoder.raw_decode(raw, offset)
            whitespace()
            if offset < len(raw) and raw[offset] == ",":
                offset += 1
                continue
            break
    except json.JSONDecodeError:
        pass
    if root.get("schema_version") != SCHEMA_VERSION or not isinstance(root.get("paragraphs"), list):
        raise ValueError("No independently matched partial analysis")
    return root


def validate_analysis(
    raw: str, *, paragraphs: list[dict[str, Any]], allowed_graph_node_ids: set[str]
) -> tuple[SectionReadingAnalysis, list[str], list[str]]:
    warnings: list[str] = []
    try:
        payload = strict_json(raw)
    except json.JSONDecodeError:
        payload = _partial_root(raw)
        warnings.append("RESPONSE_JSON_INCOMPLETE")
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Invalid analysis schema_version")
    if set(payload) - {"schema_version", "paragraphs", "section_argument"}:
        raise ValueError("Unexpected analysis root fields")
    items = payload.get("paragraphs")
    if not isinstance(items, list):
        raise ValueError("Invalid paragraphs array")
    source = {item["paragraph_id"]: item["text_en"] for item in paragraphs}
    counts = Counter(
        item.get("paragraph_id")
        for item in items
        if isinstance(item, dict) and isinstance(item.get("paragraph_id"), str)
    )
    valid: dict[str, ParagraphAnalysis] = {}
    observed_order: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            warnings.append("PARAGRAPH_SCHEMA_INVALID")
            continue
        paragraph_id = item.get("paragraph_id")
        if not isinstance(paragraph_id, str) or paragraph_id not in source:
            warnings.append("PARAGRAPH_OUTSIDE_RANGE_REMOVED")
            continue
        if counts[paragraph_id] != 1:
            warnings.append(f"PARAGRAPH_DUPLICATE:{paragraph_id}")
            continue
        candidate = dict(item)
        raw_highlights = candidate.get("highlights")
        raw_node_ids = candidate.get("related_graph_node_ids")
        if not isinstance(raw_highlights, list) or not isinstance(raw_node_ids, list):
            warnings.append(f"PARAGRAPH_SCHEMA_INVALID:{paragraph_id}")
            continue
        candidate["highlights"], candidate["related_graph_node_ids"] = [], []
        try:
            paragraph = ParagraphAnalysis.model_validate(candidate, strict=True)
            if " ".join(paragraph.translation_zh.split()) == " ".join(source[paragraph_id].split()):
                raise ValueError("English source cannot be published as its Chinese translation")
        except (ValidationError, TypeError, ValueError):
            warnings.append(f"PARAGRAPH_SCHEMA_INVALID:{paragraph_id}")
            continue
        for highlight_item in raw_highlights[:30]:
            try:
                highlight = ArgumentHighlight.model_validate(highlight_item, strict=True)
                starts: list[int] = []
                cursor = 0
                while (found := source[paragraph_id].find(highlight.quote_en, cursor)) >= 0:
                    starts.append(found)
                    cursor = found + 1
                if highlight.occurrence_index >= len(starts):
                    raise ValueError("Highlight not present at requested occurrence")
                paragraph.highlights.append(highlight)
            except (ValidationError, TypeError, ValueError):
                warnings.append(f"HIGHLIGHT_INVALID_REMOVED:{paragraph_id}")
        if len(raw_highlights) > 30:
            warnings.append(f"HIGHLIGHT_LIMIT_EXCEEDED:{paragraph_id}")
        for node_id in raw_node_ids:
            if isinstance(node_id, str) and node_id in allowed_graph_node_ids:
                if node_id not in paragraph.related_graph_node_ids:
                    paragraph.related_graph_node_ids.append(node_id)
            else:
                warnings.append(f"GRAPH_NODE_INVALID_REMOVED:{paragraph_id}")
        valid[paragraph_id] = paragraph
        observed_order.append(paragraph_id)
    selected_ids = list(source)
    if observed_order != [item for item in selected_ids if item in valid]:
        warnings.append("PARAGRAPH_ORDER_NORMALIZED_BY_LOCAL_SOURCE")
    try:
        argument = SectionArgument.model_validate(payload.get("section_argument"), strict=True)
    except (ValidationError, TypeError, ValueError):
        argument = None
        warnings.append("SECTION_ARGUMENT_MISSING_OR_INVALID")
    missing = [item for item in selected_ids if item not in valid]
    result = SectionReadingAnalysis(
        schema_version=SCHEMA_VERSION,
        paragraphs=[valid[item] for item in selected_ids if item in valid],
        section_argument=argument,
    )
    return result, missing, list(dict.fromkeys(warnings))
