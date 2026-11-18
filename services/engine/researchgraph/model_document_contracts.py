"""Schema and conservative validation for model-derived document output."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelDocumentSegmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


class ModelDocumentParseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parse_version: str = Field(min_length=1, max_length=80)
    modality: Literal["text", "pdf", "image"] = "text"
    segments: list[ModelDocumentSegmentInput] = Field(min_length=1, max_length=20_000)
    warnings: list[str] = Field(default_factory=list, max_length=128)

    @model_validator(mode="after")
    def validate_order(self) -> "ModelDocumentParseInput":
        previous: tuple[int, int, int] | None = None
        for segment in self.segments:
            key = (segment.chapter_order, segment.chapter_level, segment.ordinal)
            if previous is not None and key < previous:
                raise ValueError("解析段落必须按章节顺序提交")
            previous = key
        return self
