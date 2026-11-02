"""ResearchGraph Studio reference contracts (design-time Pydantic v2).

Do not treat these DTOs as database models or as an implemented knowledge engine.
IDs, authorization, source anchoring and graph revision validation require server logic.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KnownState(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"
    CONFLICTING = "conflicting"


class SourceValidationStatus(str, Enum):
    UNVERIFIED = "unverified"
    SOURCE_VERIFIED = "source_verified"
    NEEDS_EVIDENCE = "needs_evidence"
    SOURCE_UNAVAILABLE = "source_unavailable"
    INVALID_ANCHOR = "invalid_anchor"


class ReviewStatus(str, Enum):
    UNREVIEWED = "unreviewed"
    PROPOSED = "proposed"
    NEEDS_REVIEW = "needs_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class Condition(StrictModel):
    dimension: str = Field(min_length=1)
    value: str | None
    value_type: Literal["text", "integer", "float", "boolean"] = "text"
    unit: str | None = None
    known_state: KnownState
    evidence_span_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_known_has_value_and_evidence(self) -> "Condition":
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
    origin: Literal[
        "author_claim", "authors_experimental_result", "authors_hypothesis",
        "cited_claim", "background", "unknown"
    ]
    claim_type: Literal[
        "definition", "method_claim", "empirical_claim", "observation",
        "theoretical_claim", "limitation", "other"
    ]
    modality: Literal["asserted", "suggested", "conditional", "speculative", "negated", "unknown"]
    scope: str | None = None
    evidence: list[EvidenceReference] = Field(min_length=1)
    conditions: list[Condition] = Field(default_factory=list)
    method_local_refs: list[str] = Field(default_factory=list)
    experiment_local_ref: str | None = None
    limitations: list[str] = Field(default_factory=list)


class ConceptDraft(StrictModel):
    local_ref: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    evidence_span_ids: list[str] = Field(min_length=1)


class MethodDraft(StrictModel):
    local_ref: str
    name: str
    mechanism: str | None = None
    evidence_span_ids: list[str] = Field(min_length=1)


class FindingDraft(StrictModel):
    local_ref: str
    statement: str
    experiment_local_ref: str | None = None
    metric_name: str | None = None
    value: str | None = None
    unit: str | None = None
    baseline: str | None = None
    evidence_span_ids: list[str] = Field(min_length=1)


class ExperimentDraft(StrictModel):
    local_ref: str
    label: str
    task: str | None = None
    protocol: str | None = None
    method_local_refs: list[str] = Field(default_factory=list)
    conditions: list[Condition] = Field(default_factory=list)
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


class DimensionComparison(StrictModel):
    name: str
    source_value: str | None
    target_value: str | None
    comparison: Literal["same", "different", "unknown", "not_applicable"]
    impact: Literal["neutral", "limits_direct_comparison", "supports_comparison", "unknown"]
    evidence_ids: list[str] = Field(default_factory=list)


class ComparabilityReport(StrictModel):
    source_claim_id: str
    target_claim_id: str
    topic_overlap: Literal["same", "related", "unrelated", "unknown"]
    overall: Literal["comparable", "limited", "not_comparable", "unknown"]
    dimensions: list[DimensionComparison] = Field(default_factory=list)
    unknown_dimensions: list[str] = Field(default_factory=list)
    rationale: str


class RelationInference(StrictModel):
    source_claim_id: str
    target_claim_id: str
    decision: Literal["PROPOSE_RELATION", "NO_DECISION"]
    relation_type: Literal["SUPPORTS", "CONTRADICTS", "QUALIFIES", "EXTENDS", "RELATED"] | None
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    suggested_review: str | None = None

    @model_validator(mode="after")
    def relation_decision_consistency(self) -> "RelationInference":
        if self.decision == "NO_DECISION" and self.relation_type is not None:
            raise ValueError("NO_DECISION cannot assert a relation")
        if self.decision == "PROPOSE_RELATION" and (not self.relation_type or not self.evidence_ids):
            raise ValueError("proposed relation needs relation type and evidence")
        return self


class CitedPoint(StrictModel):
    statement: str
    epistemic_type: Literal["paper_claim", "model_synthesis", "user_insight", "unknown"]
    citation_ids: list[str] = Field(default_factory=list)


class QueryAnswer(StrictModel):
    answer: str
    points: list[CitedPoint] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    followups: list[str] = Field(default_factory=list)


class KnowledgeCandidate(StrictModel):
    candidate_type: Literal["research_question", "insight", "hypothesis", "synthesis"]
    text: str
    dependency_ids: list[str] = Field(default_factory=list)
    epistemic_type: Literal["user_question", "personal_interpretation", "ai_synthesis", "unverified_hypothesis"]
    why_save: str
    duplicate_risk: Literal["low", "medium", "high", "unknown"] = "unknown"


class KnowledgeCandidateBatch(StrictModel):
    candidates: list[KnowledgeCandidate] = Field(default_factory=list)


class LintFindingDraft(StrictModel):
    issue_type: str
    severity: Literal["info", "warning", "error", "critical"]
    affected_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str
    proposed_fix: str | None = None
    risk: Literal["nonsemantic", "scientific_meaning", "permission", "unknown"]


class LintDraftBatch(StrictModel):
    findings: list[LintFindingDraft] = Field(default_factory=list)


class ReadingSection(StrictModel):
    heading: str
    markdown: str
    dependency_ids: list[str] = Field(default_factory=list)
    authorship_label: Literal["paper_based", "user_note", "model_synthesis", "mixed"]


class ReadingSynthesisDraft(StrictModel):
    paper_id: str
    title: str
    sections: list[ReadingSection] = Field(default_factory=list)
    unresolved_evidence_ids: list[str] = Field(default_factory=list)


class WikiRevisionProposal(StrictModel):
    page_id: str
    section_id: str
    change_type: Literal["add", "revise", "deprecate", "no_change"]
    new_markdown: str
    dependency_ids: list[str] = Field(default_factory=list)
    rationale: str
    semantic_risk: Literal["low", "medium", "high"]
    requires_review: bool


class EntityAlignment(StrictModel):
    source_local_ref: str
    candidate_concept_id: str | None = None
    decision: Literal["same_as", "related_to", "distinct", "insufficient"]
    rationale: str
    evidence_span_ids: list[str] = Field(default_factory=list)


class EntityAlignmentBatch(StrictModel):
    alignments: list[EntityAlignment] = Field(default_factory=list)


class StructureSection(StrictModel):
    section_id: str
    role: Literal["abstract", "introduction", "method", "experiment", "results", "discussion", "limitation", "conclusion", "other"]
    paragraph_ids: list[str] = Field(default_factory=list)


class PaperOutline(StrictModel):
    sections: list[StructureSection] = Field(default_factory=list)
    unresolved_sections: list[str] = Field(default_factory=list)
