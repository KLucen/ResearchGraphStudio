"""Versioned runtime DTOs for paper-reading-v1, derived from reading-1.0.

Kept independent of legacy unified DTOs to preserve resumable task signatures.
"""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Ref = Annotated[str, Field(min_length=1, max_length=160)]
Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
PaperType = Literal["empirical", "methodological", "theoretical", "review", "mixed", "unknown"]
SourceStatus = Literal["anchored", "needs_evidence", "source_unavailable", "invalid_anchor"]
LegacyReviewStatus = Literal["unreviewed", "accepted", "edited", "rejected", "superseded"]
GraphRole = Literal["core", "supporting", "retrieval_only"]
NodeKind = Literal[
    "Claim",
    "Method",
    "Concept",
    "ResearchQuestion",
    "Experiment",
    "Condition",
    "Finding",
    "Metric",
    "Argument",
    "Limitation",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


def unique(values: list[str]) -> None:
    if len(values) != len(set(values)):
        raise ValueError("duplicate references")


class SourceText(StrictModel):
    """Original-language semantic text, not an exact quote or an anchor."""

    original: str = Field(min_length=1)
    language: str = Field(min_length=2, max_length=35)
    zh: str | None = None


class EvidenceSpan(StrictModel):
    id: Ref
    document_version_id: Ref
    paragraph_id: Ref
    page_index: int = Field(ge=0)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    quote: str = Field(min_length=1)
    text_sha256: Hash  # Complete normalized paragraph's UTF-8 SHA-256.

    @model_validator(mode="after")
    def ordered_offsets(self) -> EvidenceSpan:
        if self.end_offset <= self.start_offset:
            raise ValueError("end must be after start")
        return self


def verify_span_exact(span: EvidenceSpan, normalized_paragraph: str) -> bool:
    return (
        span.end_offset <= len(normalized_paragraph)
        and hashlib.sha256(normalized_paragraph.encode()).hexdigest() == span.text_sha256
        and normalized_paragraph[span.start_offset : span.end_offset] == span.quote
    )


class SourceTable(StrictModel):
    id: Ref
    document_version_id: Ref
    raw_text: str
    evidence_ids: list[Ref]
    structure_status: Literal["resolved", "partial", "unresolved"]
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    caption: str | None = None
    notes: list[str] = Field(default_factory=list)
    unresolved_reason: str | None = None

    @model_validator(mode="after")
    def unresolved_structure(self) -> SourceTable:
        if self.structure_status != "resolved" and not self.unresolved_reason:
            raise ValueError("partial/unresolved table requires a reason")
        return self


class OutlineSection(StrictModel):
    local_ref: Ref
    heading: SourceText
    paragraph_ids: list[Ref] = Field(min_length=1)
    section_type: Literal[
        "abstract",
        "introduction",
        "related_work",
        "method",
        "experiment",
        "result",
        "theory",
        "proof",
        "review",
        "discussion",
        "conclusion",
        "references",
        "other",
    ]


class PaperOutline(StrictModel):
    document_version_id: Ref
    paper_type: PaperType
    sections: list[OutlineSection]
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_sections(self) -> PaperOutline:
        unique([s.local_ref for s in self.sections])
        unique([p for s in self.sections for p in s.paragraph_ids])
        return self


class EvidenceInput(StrictModel):
    id: Ref
    text: str = Field(min_length=1)
    context_group: Ref | None = None
    context_complete: bool = True


class ExtractionRequest(StrictModel):
    contract_version: Literal["reading-extraction-1.0"]
    document_version_id: Ref
    chunk_id: Ref
    paper_type: PaperType
    section: str
    allowed_evidence: list[EvidenceInput] = Field(min_length=1, max_length=128)
    vocabulary: list[SourceText] = Field(default_factory=list)
    max_items_hint: int = Field(default=24, ge=1, le=100)

    @model_validator(mode="after")
    def unique_evidence(self) -> ExtractionRequest:
        unique([e.id for e in self.allowed_evidence])
        return self


class CandidateBase(StrictModel):
    local_ref: Ref
    label: SourceText
    summary: SourceText
    origin: Literal["paper_author", "citation_report"]
    evidence_ids: list[Ref] = Field(min_length=1)
    uncertainties: list[str] = Field(default_factory=list)


class ClaimCandidate(CandidateBase):
    kind: Literal["Claim"]
    statement: SourceText
    contribution_type: Literal[
        "empirical_result",
        "method_contribution",
        "theoretical_result",
        "review_synthesis",
        "limitation",
        "background",
    ]
    modality: Literal["asserted", "conditional", "suggested", "speculative", "negated", "unknown"]
    scope: SourceText | None = None


class MethodCandidate(CandidateBase):
    kind: Literal["Method"]
    method_role: Literal["proposed", "adapted", "used", "compared", "unknown"]


class ConceptCandidate(CandidateBase):
    kind: Literal["Concept"]
    aliases: list[str] = Field(default_factory=list)


class QuestionCandidate(CandidateBase):
    kind: Literal["ResearchQuestion"]


class ExperimentCandidate(CandidateBase):
    kind: Literal["Experiment"]
    protocol: SourceText


class ConditionAlternative(StrictModel):
    value: SourceText
    evidence_ids: list[Ref] = Field(min_length=1)


class ConditionCandidate(CandidateBase):
    kind: Literal["Condition"]
    dimension: str = Field(min_length=1)
    state: Literal["known", "unknown", "not_applicable", "conflicting"]
    value: SourceText | None = None
    unit: str | None = None
    alternatives: list[ConditionAlternative] = Field(default_factory=list)

    @model_validator(mode="after")
    def condition_state(self) -> ConditionCandidate:
        if self.state == "known" and (self.value is None or self.alternatives):
            raise ValueError("known condition requires one supported value")
        if self.state in {"unknown", "not_applicable"} and (
            self.value is not None or self.unit is not None or self.alternatives
        ):
            raise ValueError("unknown/not_applicable cannot assert values")
        if self.state == "conflicting" and (self.value is not None or len(self.alternatives) < 2):
            raise ValueError("conflicting requires evidenced alternatives")
        return self


class FindingCandidate(CandidateBase):
    kind: Literal["Finding"]
    result: SourceText
    reported_value: str | None = None  # Preserve lexical number/range/uncertainty.
    unit: str | None = None
    baseline: SourceText | None = None


class MetricCandidate(CandidateBase):
    kind: Literal["Metric"]
    unit: str | None = None


class ArgumentCandidate(CandidateBase):
    kind: Literal["Argument"]
    argument_type: Literal["derivation", "proof", "literature_comparison", "explanation"]


class LimitationCandidate(CandidateBase):
    kind: Literal["Limitation"]
    limitation_type: Literal["scope", "uncertainty", "negative_result", "open_question"]


Candidate = Annotated[
    ClaimCandidate
    | MethodCandidate
    | ConceptCandidate
    | QuestionCandidate
    | ExperimentCandidate
    | ConditionCandidate
    | FindingCandidate
    | MetricCandidate
    | ArgumentCandidate
    | LimitationCandidate,
    Field(discriminator="kind"),
]
Association = Literal[
    "SUPPORTED_BY",
    "ASSOCIATED_METHOD",
    "HAS_CONDITION",
    "REPORTS_FINDING",
    "MEASURED_WITH",
    "ABOUT_CONCEPT",
    "ADDRESSES",
    "LIMITED_BY",
]


class GraphLinkCandidate(StrictModel):
    source_local_ref: Ref
    target_local_ref: Ref
    relation: Association
    evidence_ids: list[Ref] = Field(min_length=1)


def check_relation(source: str, target: str, relation: str) -> None:
    endpoints = {
        "SUPPORTED_BY": ({"Claim"}, {"Experiment", "Finding", "Argument"}),
        "ASSOCIATED_METHOD": ({"Claim", "Experiment"}, {"Method"}),
        "HAS_CONDITION": ({"Claim", "Experiment", "Method", "Argument"}, {"Condition"}),
        "REPORTS_FINDING": ({"Experiment"}, {"Finding"}),
        "MEASURED_WITH": ({"Finding"}, {"Metric"}),
        "ABOUT_CONCEPT": ({"Claim", "Method", "ResearchQuestion", "Argument"}, {"Concept"}),
        "ADDRESSES": ({"Claim"}, {"ResearchQuestion"}),
        "LIMITED_BY": ({"Claim", "Method", "Experiment", "Argument"}, {"Limitation"}),
    }
    left, right = endpoints[relation]
    if source not in left or target not in right:
        raise ValueError("association endpoint types do not match")


class KnowledgeExtractionBatch(StrictModel):
    contract_version: Literal["reading-extraction-1.0"]
    document_version_id: Ref
    chunk_id: Ref
    items: list[Candidate] = Field(default_factory=list, max_length=100)
    links: list[GraphLinkCandidate] = Field(default_factory=list, max_length=300)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def local_refs(self) -> KnowledgeExtractionBatch:
        unique([i.local_ref for i in self.items])
        kinds = {i.local_ref: i.kind for i in self.items}
        for edge in self.links:
            if edge.source_local_ref not in kinds or edge.target_local_ref not in kinds:
                raise ValueError("unknown local reference")
            check_relation(
                kinds[edge.source_local_ref], kinds[edge.target_local_ref], edge.relation
            )
        return self


def require_allowed_evidence(batch: KnowledgeExtractionBatch, request: ExtractionRequest) -> None:
    if (batch.document_version_id, batch.chunk_id) != (
        request.document_version_id,
        request.chunk_id,
    ):
        raise ValueError("source version or chunk mismatch")
    refs = {e for item in batch.items for e in item.evidence_ids}
    for item in batch.items:
        if isinstance(item, ConditionCandidate):
            refs.update(e for a in item.alternatives for e in a.evidence_ids)
    refs.update(e for link in batch.links for e in link.evidence_ids)
    if refs - {e.id for e in request.allowed_evidence}:
        raise ValueError("unknown/out-of-scope evidence")


class QualityAssessment(StrictModel):
    relevance: Literal["main_contribution", "necessary_support", "context", "unresolved"]
    evidence_completeness: Literal["sufficient", "limited", "insufficient"]
    duplicate_status: Literal["distinct", "duplicate", "unresolved"]
    blocking_issues: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)
    assessed_by: Literal["rules", "model_assisted"]
    policy_version: Ref


class CandidateRecord(StrictModel):
    """Store-owned envelope; local_ref only retains the original batch identity."""

    id: Ref
    document_version_id: Ref
    revision: int = Field(ge=1)
    content: Candidate
    source_status: SourceStatus
    validation_status: Literal["valid", "quarantined", "superseded"]
    legacy_review_status: LegacyReviewStatus | None = None
    quality: QualityAssessment
    model_run_id: Ref
    canonical_id: Ref | None = None


class AssociationProposal(StrictModel):
    source_id: Ref
    target_id: Ref
    relation: Association
    evidence_ids: list[Ref] = Field(min_length=1)
    rationale: str = Field(min_length=1)


class DuplicateProposal(StrictModel):
    candidate_ids: list[Ref] = Field(min_length=2)
    representative_id: Ref
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def representative_member(self) -> DuplicateProposal:
        unique(self.candidate_ids)
        if self.representative_id not in self.candidate_ids:
            raise ValueError("representative must belong to duplicate group")
        return self


class UnitProposal(StrictModel):
    local_ref: Ref
    root_claim_id: Ref
    member_ids: list[Ref]
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def distinct_members(self) -> UnitProposal:
        unique(self.member_ids)
        if self.root_claim_id in self.member_ids:
            raise ValueError("root is not its own member")
        return self


class PaperIntegrationProposal(StrictModel):
    contract_version: Literal["reading-integration-1.0"]
    document_version_id: Ref
    input_revision: int = Field(ge=0)
    units: list[UnitProposal]
    associations: list[AssociationProposal] = Field(default_factory=list)
    duplicates: list[DuplicateProposal] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unit_references(self) -> PaperIntegrationProposal:
        unique([u.local_ref for u in self.units])
        unique([u.root_claim_id for u in self.units])
        return self


def validate_integration_context(
    proposal: PaperIntegrationProposal,
    candidates: dict[str, CandidateRecord],
    allowed_evidence: set[str],
    input_revision: int,
) -> None:
    if proposal.input_revision != input_revision:
        raise ValueError("stale integration revision")
    ids = {u.root_claim_id for u in proposal.units}
    ids.update(i for u in proposal.units for i in u.member_ids)
    ids.update(i for a in proposal.associations for i in (a.source_id, a.target_id))
    ids.update(i for d in proposal.duplicates for i in d.candidate_ids)
    if ids - candidates.keys():
        raise ValueError("unknown candidate")
    if any(candidates[i].document_version_id != proposal.document_version_id for i in ids):
        raise ValueError("cross-document integration")
    for unit in proposal.units:
        if candidates[unit.root_claim_id].content.kind != "Claim":
            raise ValueError("unit root must be a Claim")
    for edge in proposal.associations:
        check_relation(
            candidates[edge.source_id].content.kind,
            candidates[edge.target_id].content.kind,
            edge.relation,
        )
        if set(edge.evidence_ids) - allowed_evidence:
            raise ValueError("unknown association evidence")
    # Additionally validate semantic support and paths before materializing units.


class UnitMembership(StrictModel):
    member_id: Ref
    association_ids: list[Ref] = Field(min_length=1)


class KnowledgeUnit(StrictModel):
    id: Ref
    document_version_id: Ref
    root_claim_id: Ref
    revision: int = Field(ge=1)
    memberships: list[UnitMembership]
    integration_run_id: Ref | None = None


class SelectionHint(StrictModel):
    root_claim_id: Ref
    recommendation: Literal["suggest_core", "keep_retrievable", "needs_context"]
    reasons: list[
        Literal[
            "main_contribution",
            "answers_paper_question",
            "necessary_limitation",
            "negative_result",
            "redundant",
            "background",
            "insufficient_support",
            "uncertain_attribution",
        ]
    ] = Field(min_length=1)
    rationale: str = Field(min_length=1)


class CoreSelectionProposal(StrictModel):
    document_version_id: Ref
    input_revision: int = Field(ge=0)
    recommendations: list[SelectionHint]
    coverage_gaps: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def one_hint_per_root(self) -> CoreSelectionProposal:
        unique([h.root_claim_id for h in self.recommendations])
        return self


class SelectionEntry(StrictModel):
    candidate_id: Ref
    graph_role: GraphRole
    selected_by: Literal["automatic", "user_preference"]
    reason: str = Field(min_length=1)


class GraphSelection(StrictModel):
    contract_version: Literal["reading-selection-1.0"]
    id: Ref
    document_version_id: Ref
    knowledge_revision: int = Field(ge=0)
    selection_revision: int = Field(ge=1)
    policy_version: Ref
    density: Literal["concise", "standard", "detailed"]
    build_state: Literal["partial", "complete"]
    coverage_gaps: list[str]
    entries: list[SelectionEntry]
    units: list[KnowledgeUnit]

    @model_validator(mode="after")
    def coverage_and_units(self) -> GraphSelection:
        unique([e.candidate_id for e in self.entries])
        unique([u.id for u in self.units])
        unique([u.root_claim_id for u in self.units])
        roles = {e.candidate_id: e.graph_role for e in self.entries}
        if {i for i, role in roles.items() if role == "core"} != {
            u.root_claim_id for u in self.units
        }:
            raise ValueError("each core Claim requires exactly one unit")
        members = set()
        for unit in self.units:
            if unit.document_version_id != self.document_version_id:
                raise ValueError("cross-document unit")
            unique([m.member_id for m in unit.memberships])
            for member in unit.memberships:
                if (
                    member.member_id == unit.root_claim_id
                    or roles.get(member.member_id) != "supporting"
                ):
                    raise ValueError("unit members must be supporting candidates")
                members.add(member.member_id)
        if {i for i, role in roles.items() if role == "supporting"} != members:
            raise ValueError("supporting candidates require a unit membership")
        return self


def validate_selection_context(
    selection: GraphSelection, records: dict[str, CandidateRecord]
) -> None:
    if {e.candidate_id for e in selection.entries} != set(records):
        raise ValueError("selection must account for the complete input candidate snapshot")
    for entry in selection.entries:
        record = records[entry.candidate_id]
        if record.document_version_id != selection.document_version_id:
            raise ValueError("selection source mismatch")
        if entry.graph_role == "retrieval_only":
            continue
        if (
            record.source_status != "anchored"
            or record.validation_status != "valid"
            or record.legacy_review_status in {"rejected", "superseded"}
        ):
            raise ValueError("unverified or historically excluded candidate cannot be published")
        if record.quality.blocking_issues:
            raise ValueError("blocking quality issue")
        if entry.graph_role == "core":
            if not isinstance(record.content, ClaimCandidate):
                raise ValueError("core must be a Claim")
            if (
                record.content.origin != "paper_author"
                or record.quality.duplicate_status != "distinct"
            ):
                raise ValueError("attribution and duplicate gates failed")
            if record.quality.evidence_completeness == "insufficient":
                raise ValueError("insufficient evidence for core")
            if record.quality.evidence_completeness == "limited" and not record.quality.caveats:
                raise ValueError("limited evidence needs visible caveats")
            if entry.selected_by == "automatic" and record.quality.relevance != "main_contribution":
                raise ValueError("automatic core requires paper-level relevance")


class SelectionPreference(StrictModel):
    document_version_id: Ref
    candidate_id: Ref
    expected_selection_revision: int = Field(ge=1)
    action: Literal["include_core", "exclude_core", "reset_automatic"]
    reason: str = Field(min_length=1)
