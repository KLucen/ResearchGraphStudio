"""Bounded view DTOs, distinct from the full scientific domain contracts."""

from typing import Any, Literal

from pydantic import Field, model_validator

from researchgraph.knowledge_contracts import EvidenceView, NodeView, StrictModel

VisualKind = Literal[
    "Paper",
    "Concept",
    "Method",
    "Claim",
    "ResearchQuestion",
    "Experiment",
    "Condition",
    "Finding",
    "Metric",
    "Argument",
    "Limitation",
]


def default_kinds() -> list[VisualKind]:
    return [
        "Paper",
        "Concept",
        "Method",
        "Claim",
        "ResearchQuestion",
        "Experiment",
        "Condition",
        "Finding",
        "Metric",
        "Argument",
        "Limitation",
    ]


class ProjectionQuery(StrictModel):
    view: Literal["legacy", "paper_backbone"] = "legacy"
    expanded_unit_ids: list[str] = Field(default_factory=list, max_length=120)
    collapsed_unit_ids: list[str] = Field(default_factory=list, max_length=120)
    kinds: list[VisualKind] = Field(
        default_factory=default_kinds,
        min_length=1,
        max_length=11,
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
    graph_role: str = "legacy"
    unit_ids: list[str] = Field(default_factory=list)


class ProjectionEdge(StrictModel):
    id: str
    source: str
    target: str
    relation: str
    label_zh: str
    epistemic_status: Literal["source_reported", "model_inferred", "user_confirmed", "navigation"]
    review_status: str
    is_dashed: bool
    detail_ref: str | None = None


class PaperBuildStatus(StrictModel):
    paper_id: str
    title: str
    document_version_id: str | None
    candidate_count: int
    published_units: int
    extraction_job_id: str | None
    extraction_status: str | None
    completed_batches: int
    total_batches: int
    extraction_incomplete: bool
    active: bool
    ranking_status: str = "unknown"
    selection_mode: str = "ranked"


class GraphProjection(StrictModel):
    contract_version: str = "graph-projection-v3"
    selections: dict[str, int] = Field(default_factory=dict)
    coverage_gaps: list[str] = Field(default_factory=list)
    build_state: str = "legacy"
    paper_builds: list[PaperBuildStatus] = Field(default_factory=list)
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
