"""Bounded view DTOs, distinct from the full scientific domain contracts."""

from typing import Any, Literal

from pydantic import Field, model_validator

from researchgraph.knowledge_contracts import EvidenceView, NodeView, StrictModel

VisualKind = Literal["Paper", "Concept", "Method", "Claim", "ResearchQuestion"]


def default_kinds() -> list[VisualKind]:
    return ["Paper", "Concept", "Method", "Claim", "ResearchQuestion"]


class ProjectionQuery(StrictModel):
    kinds: list[VisualKind] = Field(
        default_factory=default_kinds,
        min_length=1,
        max_length=5,
    )
    search: str = Field(default="", max_length=160)
    paper_id: str = Field(default="", max_length=36)
    focus_id: str = Field(default="", max_length=36)
    depth: int = Field(default=1, ge=0, le=3)
    include_ai_candidates: bool = True
    diagnostics: bool = False
    include_test_data: bool = False
    include_paper_context: bool = False
    limit: int = Field(default=60, ge=1, le=120)
    cursor: str = Field(default="", max_length=1000)


class ProjectionNode(StrictModel):
    id: str
    paper_id: str
    kind: VisualKind
    label_zh: str
    label_en: str
    detail_ref: str
    source_status: str
    review_status: str
    knowledge_origin: str
    badges: list[str]


class ProjectionEdge(StrictModel):
    id: str
    source: str
    target: str
    relation: str
    label_zh: str
    epistemic_status: Literal["source_reported", "model_inferred", "user_confirmed"]
    review_status: str
    is_dashed: bool
    detail_ref: str | None = None


class GraphProjection(StrictModel):
    project_id: str
    graph_revision: int
    nodes: list[ProjectionNode]
    edges: list[ProjectionEdge]
    has_more: bool
    next_cursor: str | None
    context_node_ids: list[str] = Field(default_factory=list)


class ProjectionDetail(StrictModel):
    id: str
    paper_id: str
    title: str
    document_version_ids: list[str]
    zotero_url: str | None
    node: NodeView | None
    display: dict[str, Any]
    related: list[NodeView]
    evidence: list[EvidenceView]
    counts: dict[str, int]
    graph_revision: int


class LayoutPosition(StrictModel):
    node_id: str = Field(min_length=1, max_length=36)
    x: float = Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)
    y: float = Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)
    pinned: bool = False


class LayoutRequest(StrictModel):
    expected_version: int = Field(ge=0)
    positions: list[LayoutPosition] = Field(max_length=2000)
    zoom: float = Field(gt=0, le=4, allow_inf_nan=False)
    pan_x: float = Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)
    pan_y: float = Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)

    @model_validator(mode="after")
    def unique_positions(self) -> "LayoutRequest":
        if len({p.node_id for p in self.positions}) != len(self.positions):
            raise ValueError("Duplicate layout node")
        return self


class LayoutView(StrictModel):
    version: int = 0
    positions: list[LayoutPosition] = Field(default_factory=list)
    zoom: float = 1
    pan_x: float = 0
    pan_y: float = 0
