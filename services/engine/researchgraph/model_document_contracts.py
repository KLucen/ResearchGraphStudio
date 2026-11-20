"""Schema and conservative validation for model-derived document output."""

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ModelDocumentSegmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    chapter_ref: str = Field(min_length=1, max_length=160)
    chapter_title: str = Field(min_length=1, max_length=400)
    chapter_level: int = Field(default=1, ge=1, le=12)
    chapter_order: int = Field(default=0, ge=0)
    kind: Literal["paragraph", "table", "formula", "figure", "caption"]
    ordinal: int = Field(default=0, ge=0)
    text: str | None = Field(default=None, max_length=1_000_000)
    latex: str | None = Field(default=None, max_length=100_000)
    mathml: str | None = Field(default=None, max_length=200_000)
    raw_table_text: str | None = Field(default=None, max_length=500_000)
    table_data: dict[str, Any] | None = None
    locator: dict[str, Any] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    status: Literal["ok", "degraded", "unavailable", "needs_review", "failed"] = "ok"
    warnings: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("chapter_ref", "chapter_title")
    @classmethod
    def nonblank_chapter_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("blank_chapter_identity")
        return value

    @field_validator("locator", "table_data")
    @classmethod
    def json_material(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        def check(item: Any, depth: int = 0) -> None:
            if depth > 32:
                raise ValueError("material_nesting_limit")
            if item is None or type(item) in {str, int, bool}:
                return
            if type(item) is float:
                if not math.isfinite(item):
                    raise ValueError("nonfinite_material")
            elif isinstance(item, list):
                for child in item:
                    check(child, depth + 1)
            elif isinstance(item, dict):
                for key, child in item.items():
                    if not isinstance(key, str):
                        raise ValueError("material_object_key")
                    check(child, depth + 1)
            else:
                raise ValueError("material_json_type")

        check(value)
        return value

    @field_validator("locator")
    @classmethod
    def locator_shape(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return value

        def pages(item: dict[str, Any]) -> None:
            if "page_start" in item or "page_end" in item:
                start, end = item.get("page_start"), item.get("page_end")
                if type(start) is not int or type(end) is not int or not 1 <= start <= end <= 2048:
                    raise ValueError("locator_page_range")

        def bbox(item: Any) -> None:
            if (
                not isinstance(item, list)
                or len(item) != 4
                or any(type(number) not in {int, float} for number in item)
                or any(not math.isfinite(number) for number in item)
                or item[2] < item[0]
                or item[3] < item[1]
            ):
                raise ValueError("locator_bbox")

        pages(value)
        if "page_index" in value and (
            type(value["page_index"]) is not int or not 0 <= value["page_index"] < 2048
        ):
            raise ValueError("locator_page_index")
        if "bbox" in value:
            bbox(value["bbox"])
        if "bbox_list" in value:
            if not isinstance(value["bbox_list"], list):
                raise ValueError("locator_bbox_list")
            for item in value["bbox_list"]:
                bbox(item)
        if "source_parts" in value:
            if not isinstance(value["source_parts"], list):
                raise ValueError("locator_source_parts")
            for item in value["source_parts"]:
                if not isinstance(item, dict) or not {"page_start", "page_end"} <= item.keys():
                    raise ValueError("locator_source_parts")
                pages(item)
        return value

    @model_validator(mode="after")
    def validate_material(self) -> "ModelDocumentSegmentInput":
        if self.kind == "paragraph" and not (self.text and self.text.strip()):
            raise ValueError("段落必须包含文本")
        if self.kind == "formula" and not any(
            value and value.strip() for value in (self.text, self.latex, self.mathml)
        ):
            raise ValueError("公式必须至少包含原文、LaTeX 或 MathML")
        if self.kind == "table" and not (
            self.table_data is not None
            or (self.raw_table_text and self.raw_table_text.strip())
            or (self.text and self.text.strip())
        ):
            raise ValueError("表格必须包含结构化内容或原始表格文本")
        if self.kind in {"figure", "caption"} and not (
            (self.text and self.text.strip()) or self.locator is not None
        ):
            raise ValueError("图像材料必须包含图注文本或定位信息")
        return self


def validate_chapter_identity(segments: list[ModelDocumentSegmentInput]) -> None:
    """A chapter reference cannot silently refer to two different sections."""
    identities: dict[str, tuple[str, int, int]] = {}
    orders: dict[int, str] = {}
    for segment in segments:
        identity = (segment.chapter_title, segment.chapter_level, segment.chapter_order)
        if segment.chapter_ref in identities and identities[segment.chapter_ref] != identity:
            raise ValueError("chapter_identity_conflict")
        if segment.chapter_order in orders and orders[segment.chapter_order] != segment.chapter_ref:
            raise ValueError("chapter_order_conflict")
        identities[segment.chapter_ref] = identity
        orders[segment.chapter_order] = segment.chapter_ref


class ModelDocumentParseInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    parse_version: str = Field(min_length=1, max_length=80)
    modality: Literal["text", "pdf", "image"] = "text"
    segments: list[ModelDocumentSegmentInput] = Field(min_length=1, max_length=20_000)
    warnings: list[str] = Field(default_factory=list, max_length=128)

    @model_validator(mode="after")
    def validate_order(self) -> "ModelDocumentParseInput":
        validate_chapter_identity(self.segments)
        previous: tuple[int, int, int] | None = None
        positions: set[tuple[str, int]] = set()
        for segment in self.segments:
            position = (segment.chapter_ref, segment.ordinal)
            if position in positions:
                raise ValueError("duplicate_segment_ordinal")
            positions.add(position)
            key = (segment.chapter_order, segment.chapter_level, segment.ordinal)
            if previous is not None and key < previous:
                raise ValueError("解析段落必须按章节顺序提交")
            previous = key
        return self
