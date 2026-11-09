"""Strict joint overview contract: one card and one small, evidence-free graph."""

import json
import unicodedata
from typing import Annotated, Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from researchgraph.core import StrictModel, stable_id

SCHEMA_VERSION = "paper_overview_graph.v1"
PROMPT_VERSION = "paper_overview_with_light_graph_v1"
TASK_KIND = "paper_overview"
TASK_NAME = "PAPER_OVERVIEW_WITH_LIGHT_GRAPH_V1"
NodeType = Literal["RESEARCH_QUESTION", "CONCEPT", "METHOD", "CONTRIBUTION", "FINDING"]
EdgeType = Literal["INVESTIGATES", "USES", "ANALYZES", "YIELDS", "CONTRIBUTES_TO", "RELATED_TO"]
Basis = Literal["EXPLICIT", "INFERRED"]
LocalNodeID = Annotated[str, Field(pattern=r"^n[1-9][0-9]*$")]
LocalEdgeID = Annotated[str, Field(pattern=r"^e[1-9][0-9]*$")]
ShortItem = Annotated[str, Field(max_length=180)]


def normalized_label(label: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", label).split()).casefold()


class PaperCard(StrictModel):
    research_question: str = Field(max_length=300)
    motivation: str = Field(max_length=300)
    method_summary: str = Field(max_length=360)
    contributions: list[ShortItem] = Field(max_length=3)
    main_findings: list[ShortItem] = Field(max_length=3)
    limitations: list[ShortItem] = Field(max_length=2)


class LightNode(StrictModel):
    id: str
    type: NodeType
    label_zh: str = Field(min_length=1, max_length=48)
    label_en: str | None = Field(max_length=80)
    description_zh: str = Field(min_length=1, max_length=180)
    basis: Basis

    @field_validator("label_zh", "description_zh")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Labels and descriptions cannot be blank")
        return value


class LightEdge(StrictModel):
    id: str
    source: str
    target: str
    type: EdgeType
    basis: Basis


class LocalNode(LightNode):
    id: LocalNodeID


class LocalEdge(LightEdge):
    id: LocalEdgeID
    source: LocalNodeID
    target: LocalNodeID


RELATION_ENDPOINTS: dict[str, tuple[str, str]] = {
    "INVESTIGATES": ("RESEARCH_QUESTION", "CONCEPT"),
    "USES": ("RESEARCH_QUESTION", "METHOD"),
    "ANALYZES": ("METHOD", "CONCEPT"),
    "YIELDS": ("METHOD", "FINDING"),
    "CONTRIBUTES_TO": ("FINDING", "CONTRIBUTION"),
}


def validate_graph(nodes: list[Any], edges: list[Any]) -> None:
    by_id = {node.id: node for node in nodes}
    identities = {(node.type, normalized_label(node.label_zh)) for node in nodes}
    if len(by_id) != len(nodes) or len(identities) != len(nodes):
        raise ValueError("Duplicate node ID or label")
    if len({edge.id for edge in edges}) != len(edges):
        raise ValueError("Duplicate edge ID")
    if len({(edge.source, edge.target, edge.type) for edge in edges}) != len(edges):
        raise ValueError("Duplicate edge")
    for edge in edges:
        if edge.source not in by_id or edge.target not in by_id or edge.source == edge.target:
            raise ValueError("Invalid edge endpoint or self-loop")
        pair = (by_id[edge.source].type, by_id[edge.target].type)
        if edge.type == "RELATED_TO":
            if pair[0] == pair[1] or pair in RELATION_ENDPOINTS.values():
                raise ValueError("RELATED_TO requires distinct types without a specific relation")
        elif pair != RELATION_ENDPOINTS[edge.type]:
            raise ValueError("Invalid relation direction or endpoint type")


class LightGraph(StrictModel):
    nodes: list[LightNode] = Field(max_length=12)
    edges: list[LightEdge] = Field(max_length=16)

    @model_validator(mode="after")
    def graph_constraints(self) -> Self:
        validate_graph(self.nodes, self.edges)
        return self


class LocalGraph(StrictModel):
    nodes: list[LocalNode] = Field(max_length=12)
    edges: list[LocalEdge] = Field(max_length=16)

    @model_validator(mode="after")
    def graph_constraints(self) -> Self:
        validate_graph(self.nodes, self.edges)
        return self


class PaperOverviewDraft(StrictModel):
    schema_version: Literal["paper_overview_graph.v1"]
    paper_card: PaperCard
    graph: LocalGraph


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


def validate_response(raw: str, paper_id: str) -> tuple[PaperCard, LightGraph]:
    draft = PaperOverviewDraft.model_validate(strict_json(raw), strict=True)
    ids = {
        node.id: stable_id(
            "light-node", f"{paper_id}/{node.type}/{normalized_label(node.label_zh)}"
        )
        for node in draft.graph.nodes
    }
    graph = LightGraph(
        nodes=[
            LightNode(**{**node.model_dump(), "id": ids[node.id]}) for node in draft.graph.nodes
        ],
        edges=[
            LightEdge(
                **{
                    **edge.model_dump(),
                    "id": stable_id(
                        "light-edge",
                        f"{paper_id}/{ids[edge.source]}/{edge.type}/{ids[edge.target]}",
                    ),
                    "source": ids[edge.source],
                    "target": ids[edge.target],
                }
            )
            for edge in draft.graph.edges
        ],
    )
    return draft.paper_card, graph


class OverviewGenerate(StrictModel):
    document_version_id: str | None = None
    allow_network: bool = False
    retry_failed: bool = False
    force_regenerate: bool = False


class OverviewUsage(StrictModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    calls: int = 0
    retry_count: int = 0
    cost: float | None = None
    usage_source: Literal["provider", "unknown"] = "unknown"


class OverviewView(StrictModel):
    id: str
    paper_id: str
    document_version_id: str
    pdf_hash: str
    input_hash: str
    schema_version: str
    prompt_version: str
    provider_id: str
    model_id: str
    status: Literal["PENDING", "COMPLETED", "FAILED"]
    graph_status: Literal["READY", "NOT_ENOUGH_INFO"]
    paper_card: PaperCard | None = None
    graph: LightGraph | None = None
    usage: OverviewUsage
    generated_at: str
    cache_hit: bool = False
    job_id: str | None = None
    error_code: str | None = None
    error: str | None = None


class GraphPosition(StrictModel):
    node_id: str
    x: float = Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)
    y: float = Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)
    pinned: bool = False


class GraphViewport(StrictModel):
    x: float = Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)
    y: float = Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)
    zoom: float = Field(ge=0.05, le=10, allow_inf_nan=False)


class LayoutInput(StrictModel):
    overview_result_id: str
    positions: list[GraphPosition] = Field(max_length=12)
    viewport: GraphViewport | None = None

    @model_validator(mode="after")
    def unique_positions(self) -> Self:
        if len({position.node_id for position in self.positions}) != len(self.positions):
            raise ValueError("Duplicate layout node")
        return self


class LayoutReset(StrictModel):
    overview_result_id: str


class LayoutView(LayoutInput):
    pass
