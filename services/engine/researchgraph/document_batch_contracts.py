"""Versioned batch contracts; diagnostic paths never contain model-provided keys."""

import json
import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from researchgraph.model_document_contracts import (
    ModelDocumentSegmentInput,
    validate_chapter_identity,
)


class BatchValidationError(ValueError):
    """Only bounded field paths and stable codes are safe to persist or display."""

    def __init__(self, safe_errors: list[dict[str, str]]) -> None:
        super().__init__("模型批次响应未通过契约校验")
        self.safe_errors = safe_errors[:32]


class BatchSegment(ModelDocumentSegmentInput):
    model_config = ConfigDict(extra="forbid", strict=True)

    page_start: int = Field(ge=1, le=2048)
    page_end: int = Field(ge=1, le=2048)
    continues_before: bool = False
    continues_after: bool = False

    @model_validator(mode="after")
    def valid_pages(self) -> "BatchSegment":
        if self.page_end < self.page_start:
            raise ValueError("page_range")
        if self.locator and any(
            key in self.locator and self.locator[key] != getattr(self, key)
            for key in ("page_start", "page_end")
        ):
            raise ValueError("locator_page_range_mismatch")
        return self


class BatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal["document-batch-1"]
    page_start: int = Field(ge=1, le=2048)
    page_end: int = Field(ge=1, le=2048)
    segments: list[BatchSegment] = Field(max_length=1000)
    warnings: list[str] = Field(default_factory=list, max_length=128)
    unavailable_pages: list[int] = Field(default_factory=list, max_length=2048)

    @model_validator(mode="after")
    def valid_contents(self) -> "BatchResult":
        validate_chapter_identity(list(self.segments))
        if self.page_end < self.page_start:
            raise ValueError("page_range")
        if not self.segments and not any(w.strip() for w in self.warnings):
            raise ValueError("empty_batch_warning_required")
        previous: tuple[int, int] | None = None
        covered: set[int] = set()
        for segment in self.segments:
            if not self.page_start <= segment.page_start <= segment.page_end <= self.page_end:
                raise ValueError("segment_page_range")
            key = (segment.page_start, segment.ordinal)
            if previous is not None and key < previous:
                raise ValueError("segment_order")
            previous = key
            covered.update(range(segment.page_start, segment.page_end + 1))
        unavailable = set(self.unavailable_pages)
        expected = set(range(self.page_start, self.page_end + 1))
        if (
            len(unavailable) != len(self.unavailable_pages)
            or not unavailable <= expected
            or unavailable & covered
            or covered | unavailable != expected
            or (unavailable and not any(w.strip() for w in self.warnings))
        ):
            raise ValueError("core_page_coverage")
        return self


class BoundaryResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal["document-boundary-1"]
    action: Literal["merge", "separate", "uncertain"]
    separator: Literal["space", "newline", "none"]
    reason: Literal[
        "continuation",
        "distinct_content",
        "overlap_duplicate",
        "uncertain",
        "table_header_repeat",
    ]


_SAFE_FIELDS = (
    set(BatchResult.model_fields)
    | set(BatchSegment.model_fields)
    | set(BoundaryResult.model_fields)
)
_SAFE_CODES = {
    "missing",
    "extra_forbidden",
    "literal_error",
    "string_type",
    "string_too_short",
    "string_too_long",
    "int_type",
    "int_parsing",
    "int_from_float",
    "float_type",
    "float_parsing",
    "bool_type",
    "bool_parsing",
    "list_type",
    "dict_type",
    "model_type",
    "greater_than_equal",
    "less_than_equal",
    "too_long",
    "too_short",
    "finite_number",
    "value_error",
    "json_invalid",
    "duplicate_key",
    "nonfinite_number",
    "page_range_mismatch",
}


def _safe_validation_error(exc: ValidationError) -> BatchValidationError:
    errors: list[dict[str, str]] = []
    for error in exc.errors(include_input=False, include_context=False, include_url=False)[:32]:
        parts: list[str] = []
        for item in error.get("loc", ()):
            if type(item) is int:
                parts.append(f"[{item}]")
            elif item in _SAFE_FIELDS:
                parts.append(("." if parts else "") + str(item))
            else:
                # Never echo an unknown field name: it can contain source text.
                break
        code = str(error.get("type", "value_error"))
        errors.append(
            {"path": "".join(parts) or "$", "code": code if code in _SAFE_CODES else "value_error"}
        )
    return BatchValidationError(errors)


def _decode(raw: str | dict[str, Any]) -> dict[str, Any]:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise BatchValidationError([{"path": "$", "code": "duplicate_key"}])
            result[key] = value
        return result

    def invalid_constant(_value: str) -> Any:
        raise BatchValidationError([{"path": "$", "code": "nonfinite_number"}])

    def finite_float(value: str) -> float:
        result = float(value)
        if not math.isfinite(result):
            invalid_constant(value)
        return result

    if isinstance(raw, str):
        try:
            result = json.loads(
                raw,
                object_pairs_hook=object_pairs,
                parse_constant=invalid_constant,
                parse_float=finite_float,
            )
        except (ValueError, RecursionError) as exc:
            if isinstance(exc, BatchValidationError):
                raise
            raise BatchValidationError([{"path": "$", "code": "json_invalid"}]) from None
    else:
        result = raw
    if not isinstance(result, dict):
        raise BatchValidationError([{"path": "$", "code": "model_type"}])
    return result


def validate_batch(raw: str | dict[str, Any], start: int, end: int) -> BatchResult:
    try:
        result = BatchResult.model_validate(_decode(raw))
    except ValidationError as exc:
        raise _safe_validation_error(exc) from None
    if result.page_start != start or result.page_end != end:
        raise BatchValidationError([{"path": "page_start", "code": "page_range_mismatch"}])
    return result


def validate_boundary(raw: str | dict[str, Any]) -> BoundaryResult:
    try:
        return BoundaryResult.model_validate(_decode(raw))
    except ValidationError as exc:
        raise _safe_validation_error(exc) from None
