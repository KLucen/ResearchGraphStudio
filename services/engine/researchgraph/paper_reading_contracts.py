"""One explicitly requested whole-paper reading note, separate from legacy A02."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import Field

from researchgraph.close_reading_contracts import (
    ParagraphAnalysis,
    ReadingBudget,
    SectionArgument,
    validate_analysis,
)
from researchgraph.core import StrictModel
from researchgraph.section_guide_contracts import GuideUsage, strict_json

SCHEMA_VERSION: Literal["paper_reading_analysis.v1"] = "paper_reading_analysis.v1"
PROMPT_VERSION = "A04_paper_reading_notes_v1"
TASK_KIND = "paper_reading_notes"


class PaperReadingAnalysis(StrictModel):
    schema_version: Literal["paper_reading_analysis.v1"]
    paragraphs: list[ParagraphAnalysis]
    paper_argument: SectionArgument | None


class PaperReadingGenerate(StrictModel):
    document_version_id: str | None = None
    allow_network: bool = False
    force_regenerate: bool = False


class PaperReadingView(StrictModel):
    id: str
    paper_id: str
    document_version_id: str
    source_hash: str
    input_hash: str
    projection_version: str
    projection_hash: str
    schema_version: str
    prompt_version: str
    provider_id: str
    model_id: str
    status: Literal["PENDING", "COMPLETED", "INCOMPLETE", "FAILED", "STALE"]
    analysis: PaperReadingAnalysis | None
    paragraph_count: int
    missing_paragraph_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    usage: GuideUsage
    estimated: ReadingBudget
    generated_at: str
    cache_hit: bool = False
    new_calls: int = 0
    job_id: str | None = None
    error_code: str | None = None
    error: str | None = None
    stale_reason: str | None = None


def paper_analysis_schema() -> dict[str, Any]:
    schema = PaperReadingAnalysis.model_json_schema()
    # The provider must supply the whole-paper summary. Null exists only in
    # our local representation of an independently validated partial result.
    schema["properties"]["paper_argument"] = {"$ref": "#/$defs/SectionArgument"}
    return schema


def _partial_paper(raw: str) -> dict[str, Any]:
    """Retain complete JSON values, without repairing a truncated response."""

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError("Duplicate JSON key")
            value[key] = item
        return value

    def constant(_value: str) -> Any:
        raise ValueError("Nonfinite JSON constant")

    decoder = json.JSONDecoder(object_pairs_hook=pairs, parse_constant=constant)
    cursor = 0

    def whitespace() -> None:
        nonlocal cursor
        while cursor < len(raw) and raw[cursor].isspace():
            cursor += 1

    whitespace()
    if cursor >= len(raw) or raw[cursor] != "{":
        raise ValueError("Expected a JSON object")
    cursor += 1
    root: dict[str, Any] = {}
    try:
        while True:
            whitespace()
            key, cursor = decoder.raw_decode(raw, cursor)
            if key not in {"schema_version", "paragraphs", "paper_argument"} or key in root:
                raise ValueError("Invalid or duplicate root field")
            whitespace()
            if cursor >= len(raw) or raw[cursor] != ":":
                break
            cursor += 1
            whitespace()
            if key != "paragraphs":
                root[key], cursor = decoder.raw_decode(raw, cursor)
            else:
                if cursor >= len(raw) or raw[cursor] != "[":
                    break
                cursor += 1
                root[key] = []
                while True:
                    whitespace()
                    if cursor < len(raw) and raw[cursor] == "]":
                        cursor += 1
                        break
                    item, cursor = decoder.raw_decode(raw, cursor)
                    root[key].append(item)
                    whitespace()
                    if cursor < len(raw) and raw[cursor] == ",":
                        cursor += 1
                        continue
                    if cursor < len(raw) and raw[cursor] == "]":
                        cursor += 1
                        break
                    return root
            whitespace()
            if cursor < len(raw) and raw[cursor] == ",":
                cursor += 1
                continue
            break
    except json.JSONDecodeError:
        pass
    if root.get("schema_version") != SCHEMA_VERSION or not isinstance(root.get("paragraphs"), list):
        raise ValueError("No independently readable paper analysis")
    return root


def validate_paper_analysis(
    raw: str, *, paragraphs: list[dict[str, Any]], allowed_graph_node_ids: set[str]
) -> tuple[PaperReadingAnalysis, list[str], list[str], bool]:
    truncated = False
    try:
        payload = strict_json(raw)
    except json.JSONDecodeError:
        payload = _partial_paper(raw)
        truncated = True
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != SCHEMA_VERSION
        or set(payload) - {"schema_version", "paragraphs", "paper_argument"}
    ):
        raise ValueError("Invalid paper analysis root")
    # Reuse the exact source quote, duplicate-ID, coverage and graph-ID checks
    # used by A02. This conversion is local only; raw_output is never rewritten.
    analysis, missing, warnings = validate_analysis(
        json.dumps(
            {
                "schema_version": "section_reading_analysis.v1",
                "paragraphs": payload.get("paragraphs"),
                "section_argument": payload.get("paper_argument"),
            },
            ensure_ascii=False,
        ),
        paragraphs=paragraphs,
        allowed_graph_node_ids=allowed_graph_node_ids,
    )
    if truncated:
        warnings.append("RESPONSE_JSON_INCOMPLETE")
    warnings = [
        "PAPER_ARGUMENT_MISSING_OR_INVALID"
        if warning == "SECTION_ARGUMENT_MISSING_OR_INVALID"
        else warning
        for warning in warnings
    ]
    complete = (
        not missing
        and analysis.section_argument is not None
        and not any(
            warning
            in {
                "RESPONSE_JSON_INCOMPLETE",
                "PARAGRAPH_OUTSIDE_RANGE_REMOVED",
                "PARAGRAPH_ORDER_NORMALIZED_BY_LOCAL_SOURCE",
            }
            for warning in warnings
        )
    )
    return (
        PaperReadingAnalysis(
            schema_version=SCHEMA_VERSION,
            paragraphs=analysis.paragraphs,
            paper_argument=analysis.section_argument,
        ),
        missing,
        list(dict.fromkeys(warnings)),
        complete,
    )
