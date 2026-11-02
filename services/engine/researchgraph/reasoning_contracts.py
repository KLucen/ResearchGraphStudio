"""P03–P05 DTOs; scientific relations remain proposals until explicit review."""

from typing import Any, Literal

from pydantic import ConfigDict, Field, model_validator

from researchgraph.knowledge_contracts import EvidenceView, ModelRunView, NodeView, StrictModel


class DimensionComparison(StrictModel):
    name: str = Field(min_length=1)
    source_value: str | None
    target_value: str | None
    comparison: Literal["same", "different", "unknown", "not_applicable"]
    impact: Literal["neutral", "limits_direct_comparison", "supports_comparison", "unknown"]
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)


class ComparabilityReport(StrictModel):
    source_claim_id: str
    target_claim_id: str
    topic_overlap: Literal["same", "related", "unrelated", "unknown"]
    overall: Literal["comparable", "limited", "not_comparable", "unknown"]
    dimensions: list[DimensionComparison] = Field(default_factory=list, max_length=50)
    unknown_dimensions: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1, max_length=10000)
    rationale_zh: str = Field(default="", max_length=10000)


class RelationInference(StrictModel):
    source_claim_id: str
    target_claim_id: str
    decision: Literal["PROPOSE_RELATION", "NO_DECISION"]
    relation_type: Literal["SUPPORTS", "CONTRADICTS", "QUALIFIES", "EXTENDS", "RELATED"] | None
    reason: str = Field(min_length=1, max_length=10000)
    reason_zh: str = Field(default="", max_length=10000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    unresolved_questions: list[str] = Field(default_factory=list)
    suggested_review: str | None = None

    @model_validator(mode="after")
    def consistency(self) -> "RelationInference":
        if (self.decision == "NO_DECISION") != (self.relation_type is None):
            raise ValueError("NO_DECISION must have no relation type")
        if self.decision == "PROPOSE_RELATION" and not self.evidence_ids:
            raise ValueError("A proposed relation needs evidence")
        return self


class EntityAlignment(StrictModel):
    source_local_ref: str
    candidate_concept_id: str | None = None
    decision: Literal["same_as", "related_to", "distinct", "insufficient"]
    rationale: str = Field(min_length=1, max_length=10000)
    rationale_zh: str = Field(default="", max_length=10000)
    evidence_span_ids: list[str] = Field(default_factory=list, max_length=100)


class EntityAlignmentBatch(StrictModel):
    alignments: list[EntityAlignment] = Field(max_length=1)


class CandidateRequest(StrictModel):
    source_id: str
    include_test_data: bool = True
    query: str = Field(default="", max_length=300)
    top_k: int = Field(default=10, ge=1, le=30)


class CandidateList(StrictModel):
    items: list[NodeView]
    strategy: str = "fts5-bm25-or-v1"
    graph_revision: int


class InferenceRequest(StrictModel):
    source_id: str
    target_id: str
    provider: Literal["mock", "project"] = "project"
    allow_network: bool = False


class SemanticReviewRequest(StrictModel):
    proposal_id: str
    kind: Literal["relation", "alignment"]
    expected_revision: int = Field(ge=1)
    action: Literal["accept", "reject"]
    reason: str = Field(min_length=1, max_length=2000)


class ProposalView(StrictModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    attempt_id: str
    project_id: str
    source_id: str
    target_id: str
    relation_type: str
    rationale: str
    evidence_ids: list[str]
    review_status: str
    revision: int
    created_at: str
    stale: bool = False


class AttemptView(StrictModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    source_id: str
    target_id: str
    mode: str
    comparison: dict[str, Any] | None
    output: dict[str, Any]
    snapshot: dict[str, Any]
    model_run_ids: list[str]
    created_at: str


class SemanticReviewView(StrictModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    action: str
    reason: str
    before: dict[str, Any]
    after: dict[str, Any]
    created_at: str


class ProposalDetail(StrictModel):
    proposal: ProposalView
    attempt: AttemptView
    runs: list[ModelRunView]
    reviews: list[SemanticReviewView]


class ReasoningHistory(StrictModel):
    attempts: list[AttemptView]
    relations: list[ProposalView]
    alignments: list[ProposalView]


class GraphView(StrictModel):
    nodes: list[NodeView]
    relations: list[ProposalView]
    papers: dict[str, str]
    next_cursor: str | None
    graph_revision: int
    scope: str = "bounded; only edges with both endpoints in this view"


class ContextView(StrictModel):
    root_id: str
    nodes: list[NodeView]
    dependencies: list[list[str]]
    dimensions: dict[str, dict[str, Any]]
    root_evidence_ids: list[str]
    evidence: list[EvidenceView]
