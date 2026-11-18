"""Local, source-mapped reading units; original PDF blocks are never rewritten."""

from typing import Literal

from pydantic import Field

from researchgraph.core import StrictModel

PROJECTION_VERSION = "reading-document-2"


class ReadingSource(StrictModel):
    chunk_id: str
    span_ids: list[str]
    page: int = Field(ge=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    text: str
    text_hash: str
    bbox: list[float]


class ReadingRegion(StrictModel):
    page: int = Field(ge=1)
    bbox: list[float]


class ReadingUnit(StrictModel):
    id: str
    kind: Literal["paragraph", "heading", "material"]
    material_type: (
        Literal[
            "table",
            "figure",
            "formula",
            "caption",
            "figure_label",
            "running",
            "reference",
            "contents",
            "unresolved",
        ]
        | None
    ) = None
    section_id: str
    heading_level: int | None = None
    text: str
    page_start: int
    page_end: int
    ordinal: int
    source_hash: str
    sources: list[ReadingSource]
    regions: list[ReadingRegion] = Field(default_factory=list)
    join_reason: str | None = None
    confidence: Literal["high", "suspected"] = "high"
    reason: str | None = None
    solution: str | None = None
    formula_latex: str | None = None
    formula_status: Literal[
        "source_only",
        "latex_unavailable",
        "recognized",
        "needs_review",
        "failed",
    ] | None = None
    formula_confidence: Literal["suspected", "high"] | None = None
    formula_source_text: str | None = None
    formula_id: str | None = None


class ReadingDocumentSection(StrictModel):
    section_id: str
    parent_id: str | None = None
    title: str
    level: int
    role: str


class DocumentReadingView(StrictModel):
    paper_id: str
    document_version_id: str
    projection_version: str = PROJECTION_VERSION
    source_hash: str
    projection_hash: str
    sections: list[ReadingDocumentSection]
    units: list[ReadingUnit]
    warnings: list[str]
    refreshed_at: str | None = None
