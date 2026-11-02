"""ResearchGraph Studio P1/P2 runtime contracts adapted from the v2 reference.

DTOs are validated separately from database objects.
IDs, authorization, source anchoring and graph revision validation require server logic.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KnownState(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"
    CONFLICTING = "conflicting"


class SourceValidationStatus(StrEnum):
    UNVERIFIED = "unverified"
    SOURCE_VERIFIED = "source_verified"
    NEEDS_EVIDENCE = "needs_evidence"
    SOURCE_UNAVAILABLE = "source_unavailable"
    INVALID_ANCHOR = "invalid_anchor"


class ReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    PROPOSED = "proposed"
    NEEDS_REVIEW = "needs_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class Condition(StrictModel):
    dimension: str = Field(min_length=1)
    dimension_zh: str | None = None
    value: str | None
    value_zh: str | None = None
    value_type: Literal["text", "integer", "float", "boolean"] = "text"
    unit: str | None = None
    unit_zh: str | None = None
    known_state: KnownState
    evidence_span_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_known_has_value_and_evidence(self) -> Condition:
        if self.known_state == KnownState.KNOWN:
            if not self.value or not self.evidence_span_ids:
                raise ValueError("known condition requires a nonempty value and evidence")
        elif self.known_state in (KnownState.UNKNOWN, KnownState.NOT_APPLICABLE):
            if self.value is not None:
                raise ValueError("unknown/not_applicable condition cannot invent value")
        return self


class EvidenceReference(StrictModel):
    evidence_span_id: str = Field(min_length=1)
    role: Literal["direct", "context", "cited_other", "limitation"] = "direct"


class ClaimDraft(StrictModel):
    local_ref: str = Field(min_length=1)
    statement: str = Field(min_length=10)
    statement_zh: str | None = None
    origin: Literal[
        "author_claim",
        "authors_experimental_result",
        "authors_hypothesis",
        "cited_claim",
        "background",
        "unknown",
    ]
    claim_type: Literal[
        "definition",
        "method_claim",
        "empirical_claim",
        "observation",
        "theoretical_claim",
        "limitation",
        "other",
    ]
    modality: Literal["asserted", "suggested", "conditional", "speculative", "negated", "unknown"]
    scope: str | None = None
    scope_zh: str | None = None
    evidence: list[EvidenceReference] = Field(min_length=1)
    conditions: list[Condition] = Field(default_factory=list)
    method_local_refs: list[str] = Field(default_factory=list)
    experiment_local_ref: str | None = None
    limitations: list[str] = Field(default_factory=list)
    limitations_zh: list[str] = Field(default_factory=list)


class ConceptDraft(StrictModel):
    local_ref: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    canonical_name_zh: str | None = None
    aliases: list[str] = Field(default_factory=list)
    evidence_span_ids: list[str] = Field(min_length=1)


class MethodDraft(StrictModel):
    local_ref: str
    name: str
    name_zh: str | None = None
    mechanism: str | None = None
    mechanism_zh: str | None = None
    evidence_span_ids: list[str] = Field(min_length=1)


class FindingDraft(StrictModel):
    local_ref: str
    statement: str
    statement_zh: str | None = None
    experiment_local_ref: str | None = None
    metric_name: str | None = None
    metric_name_zh: str | None = None
    value: str | None = None
    unit: str | None = None
    baseline: str | None = None
    baseline_zh: str | None = None
    evidence_span_ids: list[str] = Field(min_length=1)


class ExperimentDraft(StrictModel):
    local_ref: str
    label: str
    task: str | None = None
    protocol: str | None = None
    method_local_refs: list[str] = Field(default_factory=list)
    conditions: list[Condition] = Field(default_factory=list)
    evidence_span_ids: list[str] = Field(min_length=1)


class ResearchQuestionDraft(StrictModel):
    local_ref: str
    statement: str = Field(min_length=1)
    statement_zh: str | None = None
    origin: Literal["author_claim", "cited_claim"] = "author_claim"
    evidence_span_ids: list[str] = Field(min_length=1)


class ExtractionBatch(StrictModel):
    paper_id: str
    schema_version: str
    concepts: list[ConceptDraft] = Field(default_factory=list)
    methods: list[MethodDraft] = Field(default_factory=list)
    experiments: list[ExperimentDraft] = Field(default_factory=list)
    claims: list[ClaimDraft] = Field(default_factory=list)
    findings: list[FindingDraft] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    research_questions: list[ResearchQuestionDraft] = Field(default_factory=list)


class StructureSection(StrictModel):
    section_id: str
    role: Literal[
        "abstract",
        "introduction",
        "method",
        "experiment",
        "results",
        "discussion",
        "limitation",
        "conclusion",
        "other",
    ]
    paragraph_ids: list[str] = Field(default_factory=list)


class PaperOutline(StrictModel):
    sections: list[StructureSection] = Field(default_factory=list)
    unresolved_sections: list[str] = Field(default_factory=list)


class ExtractionRequest(StrictModel):
    document_version_id: str
    provider: Literal["mock", "configured", "project"] = "project"
    allow_network: bool = False
    pipeline: Literal["legacy-v2", "unified-v3", "paper-reading-v1"] = "unified-v3"
    density: Literal["concise", "standard", "detailed"] = "standard"
    paper_type: Literal[
        "empirical", "methodological", "theoretical", "review", "mixed", "unknown"
    ] = "unknown"


class ReviewRequest(StrictModel):
    node_id: str
    expected_revision: int = Field(ge=1)
    expected_graph_revision: int = Field(ge=0)
    action: Literal["accept", "reject", "revise"]
    reason: str = Field(min_length=1, max_length=2000)
    # Full typed payload for revise; no persistent IDs/states can be supplied here.
    payload: dict[str, Any] | None = None


class EvidenceView(StrictModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_version_id: str
    section_id: str
    paragraph_id: str
    page_index: int
    start_offset: int
    end_offset: int
    quote: str
    text_sha256: str
    normalization: str
    bbox_list: list[list[float]]


class SectionView(StrictModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_version_id: str
    title: str
    ordinal: int
    role: str
    parser: str


class DocumentStructure(StrictModel):
    document_version_id: str
    sections: list[SectionView]
    evidence: list[EvidenceView]


class NodeView(StrictModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    paper_id: str
    document_version_id: str
    kind: str
    text: str
    payload: dict[str, Any]
    origin: str
    authorship: str
    source_status: SourceValidationStatus
    review_status: ReviewStatus
    issues: list[str]
    dimension: str | None
    known_state: KnownState | None
    value: str | None
    unit: str | None
    model_run_id: str | None
    revision: int
    created_at: str
    updated_at: str


class KnowledgeList(StrictModel):
    items: list[NodeView]
    graph_revision: int


class ModelRunView(StrictModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    job_id: str
    document_version_id: str
    provider: str
    model: str
    prompt_name: str
    prompt_hash: str
    schema_version: str
    input_hash: str
    parameters: dict[str, Any]
    status: str
    raw_output: str | None
    error: str | None
    created_at: str
    finished_at: str | None


class ReviewView(StrictModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    node_id: str
    action: str
    actor: str
    reason: str
    before: dict[str, Any]
    after: dict[str, Any]
    created_at: str


class NodeDetail(StrictModel):
    node: NodeView
    evidence: list[EvidenceView]
    reviews: list[ReviewView]
    model_run: ModelRunView | None
    graph_revision: int
