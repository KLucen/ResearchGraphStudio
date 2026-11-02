"""Design v3.3 reference contracts, not runtime models or an Alembic migration.

JSON Schema validates shape. Context checks below illustrate additional server
gates; evidence IDs alone cannot prove scientific support or extraction quality.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
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


class GraphNode(StrictModel):
    id: Ref
    kind: NodeKind | Literal["Paper", "Evidence"]
    label: SourceText
    role: GraphRole | Literal["paper", "evidence"]
    detail_ref: Ref
    source_status: SourceStatus
    validation_status: Literal["valid", "quarantined", "superseded"]
    unit_ids: list[Ref] = Field(default_factory=list)


class GraphEdge(StrictModel):
    id: Ref
    source: Ref
    target: Ref
    relation: Literal["HAS_CORE_CLAIM", "UNIT_MEMBER", "SOURCE_EVIDENCE", "SCIENCE_RELATION"]
    unit_id: Ref | None = None
    assertion_id: Ref | None = None
    epistemic_status: Literal["navigation", "source_reported", "model_inferred"]
    is_dashed: bool = False


class GraphProjection(StrictModel):
    contract_version: Literal["reading-projection-2.0"]
    project_id: Ref
    paper_id: Ref
    document_version_id: Ref
    knowledge_revision: int = Field(ge=0)
    selection_revision: int = Field(ge=1)
    build_state: Literal["partial", "complete"]
    expanded_unit_ids: list[Ref]
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    next_cursor: str | None = None

    @model_validator(mode="after")
    def graph_topology(self) -> GraphProjection:
        unique([n.id for n in self.nodes])
        unique([e.id for e in self.edges])
        nodes = {n.id: n for n in self.nodes}
        if self.paper_id not in nodes or nodes[self.paper_id].kind != "Paper":
            raise ValueError("projection requires paper context")
        for node in self.nodes:
            if node.role == "retrieval_only":
                raise ValueError("retrieval-only is outside the default projection")
            if node.role == "core" and node.kind != "Claim":
                raise ValueError("only Claim may be a core node")
        reached = set()
        for edge in self.edges:
            if edge.source not in nodes or edge.target not in nodes:
                raise ValueError("projection edge endpoint missing")
            source, target = nodes[edge.source], nodes[edge.target]
            if target.kind == "Paper":
                raise ValueError("paper is not a child")
            if source.kind == "Paper" and edge.relation != "HAS_CORE_CLAIM":
                raise ValueError("paper may only connect directly to core Claims")
            if edge.relation == "HAS_CORE_CLAIM":
                if source.kind != "Paper" or target.role != "core":
                    raise ValueError("invalid paper/core hierarchy")
                if edge.epistemic_status != "navigation":
                    raise ValueError("hierarchy is navigation, not scientific support")
            elif edge.relation in {"UNIT_MEMBER", "SOURCE_EVIDENCE"}:
                if source.role != "core" or target.role not in {"supporting", "evidence"}:
                    raise ValueError("detail nodes must attach to a core Claim")
                if (
                    edge.unit_id not in self.expanded_unit_ids
                    or edge.unit_id not in source.unit_ids
                    or edge.unit_id not in target.unit_ids
                ):
                    raise ValueError("membership outside expanded unit")
                if edge.epistemic_status != "navigation":
                    raise ValueError("unit grouping is not a scientific assertion")
            elif edge.relation == "SCIENCE_RELATION":
                if source.role != "core" or target.role != "core" or not edge.assertion_id:
                    raise ValueError("science relation requires Claim endpoints and assertion")
                if edge.epistemic_status == "navigation":
                    raise ValueError("science relation must declare its origin")
                if edge.epistemic_status == "model_inferred" and not edge.is_dashed:
                    raise ValueError("model-inferred relation must be dashed")
            if edge.relation != "SCIENCE_RELATION":
                reached.add(edge.target)
        if set(nodes) - {self.paper_id} - reached:
            raise ValueError("orphan projection node")
        return self


class VersionedDependency(StrictModel):
    ref_id: Ref
    revision: int = Field(ge=1)
    source_kind: Literal["paper", "note", "wiki"] = "paper"
    document_version_id: Ref | None = None
    snapshot_id: Ref | None = None

    @model_validator(mode="after")
    def source_identity(self) -> VersionedDependency:
        if self.source_kind == "paper":
            if self.document_version_id is None or self.snapshot_id is not None:
                raise ValueError("paper dependency requires a document version")
        elif self.snapshot_id is None or self.document_version_id is not None:
            raise ValueError("note/wiki dependency requires a snapshot")
        return self


class GroundedPassage(StrictModel):
    local_ref: Ref
    text: SourceText
    attribution: Literal["paper_author", "citation_report", "user_view", "model_synthesis"]
    dependencies: list[VersionedDependency] = Field(min_length=1)
    evidence_ids: list[Ref] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def attribution_sources(self) -> GroundedPassage:
        if self.attribution == "user_view":
            if not any(d.source_kind == "note" for d in self.dependencies):
                raise ValueError("user view requires an authorized note snapshot")
        elif not self.evidence_ids:
            raise ValueError("scientific passage requires original evidence")
        return self


class RetrievalHit(StrictModel):
    ref_id: Ref
    document_version_id: Ref
    graph_role: GraphRole | Literal["evidence"]
    source_status: SourceStatus
    validation_status: Literal["valid", "quarantined", "superseded"]
    evidence_ids: list[Ref]
    legacy_excluded: bool = False


def eligible_query_hits(hits: list[RetrievalHit]) -> list[RetrievalHit]:
    return [
        h
        for h in hits
        if h.source_status == "anchored"
        and h.validation_status == "valid"
        and not h.legacy_excluded
    ]


class QueryAnswer(StrictModel):
    passages: list[GroundedPassage]
    limitations: list[str]
    knowledge_status: Literal["source_grounded", "mixed_sources", "insufficient"]


class ReadingSynthesisDraft(StrictModel):
    title: str = Field(min_length=1)
    scope: Literal["paper", "concept", "method", "comparison"]
    passages: list[GroundedPassage]
    knowledge_revision: int = Field(ge=0)
    selection_revision: int = Field(ge=1)
    coverage_gaps: list[str]


class WikiEditDraft(StrictModel):
    section_id: Ref
    operation: Literal["replace", "append", "mark_stale"]
    passages: list[GroundedPassage]
    reason: str = Field(min_length=1)


class WikiDeltaProposal(StrictModel):
    wiki_page_id: Ref
    base_content_hash: Hash
    edits: list[WikiEditDraft]
    requires_explicit_publish: Literal[True]
    warnings: list[str] = Field(default_factory=list)


class TranslationRepair(StrictModel):
    candidate_id: Ref
    source_revision: int = Field(ge=1)
    label_zh: str
    summary_zh: str
    warnings: list[str] = Field(default_factory=list)


class QueryDistillation(StrictModel):
    passages: list[GroundedPassage]
    warnings: list[str] = Field(default_factory=list)


class LintIssue(StrictModel):
    affected_ids: list[Ref] = Field(min_length=1)
    issue_type: Literal[
        "unsupported_core",
        "orphan_member",
        "incorrect_attribution",
        "overgeneralization",
        "duplicate",
        "translation_mismatch",
        "stale_dependency",
        "other",
    ]
    rationale: str
    evidence_ids: list[Ref]
    suggested_action: str


class LintIssueBatch(StrictModel):
    issues: list[LintIssue]
    warnings: list[str] = Field(default_factory=list)


class NodeDetail(StrictModel):
    candidate: CandidateRecord
    memberships: list[Ref]
    graph_role: GraphRole
    evidence: list[EvidenceSpan]


class NodeLayout(StrictModel):
    node_id: Ref
    x: float
    y: float
    pinned: bool = False


class GraphLayoutSnapshot(StrictModel):
    project_id: Ref
    view_id: Ref
    layout_revision: int = Field(ge=1)
    positions: list[NodeLayout]
    zoom: float = Field(default=1, gt=0)
    pan_x: float = 0
    pan_y: float = 0


class JobBatchRecord(StrictModel):
    job_id: Ref
    batch_id: Ref
    input_hash: Hash
    document_version_id: Ref
    prompt_version: Ref
    schema_version: Ref
    model_id: Ref
    stage: Literal["indexing", "extracting", "integrating", "selecting", "publishing"]
    state: Literal["queued", "running", "committed", "failed", "cancelled"]
    committed_revision: int | None = Field(default=None, ge=0)
    attempts: int = Field(default=0, ge=0)
    last_error_code: str | None = None

    @model_validator(mode="after")
    def committed_checkpoint(self) -> JobBatchRecord:
        if self.state == "committed" and self.committed_revision is None:
            raise ValueError("committed stage requires a durable checkpoint")
        return self


class ModelRunRecord(StrictModel):
    id: Ref
    prompt_id: Ref
    prompt_version: Ref
    prompt_sha256: Hash
    schema_version: Ref
    input_sha256: Hash
    model_id: Ref
    status: Literal["received", "validated", "failed"]
    raw_output_ref: Ref | None = None
    error_code: str | None = None
    reported_total_tokens: int | None = Field(default=None, ge=0)


class ComparisonDimension(StrictModel):
    name: str
    source_value: str | None = None
    target_value: str | None = None
    comparison: Literal["same", "different", "unknown", "not_applicable"]
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)


class ComparabilityReport(StrictModel):
    left_claim_id: str
    right_claim_id: str
    overall: Literal["comparable", "limited", "not_comparable", "unknown"]
    dimensions: list[ComparisonDimension]
    rationale: str
    unresolved_dimensions: list[str] = Field(default_factory=list)


class RelationDecision(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    QUALIFIES = "QUALIFIES"
    EXTENDS = "EXTENDS"
    RELATED = "RELATED"
    NO_DECISION = "NO_DECISION"


class RelationInference(StrictModel):
    left_claim_id: str
    right_claim_id: str
    decision: RelationDecision
    relation_type: RelationDecision | None
    rationale: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_decision_semantics(self) -> RelationInference:
        if self.decision == RelationDecision.NO_DECISION:
            if self.relation_type is not None:
                raise ValueError("NO_DECISION must not create a relation edge")
        elif self.relation_type != self.decision:
            raise ValueError("relation_type must equal the decision")
        return self


class EntityAlignment(StrictModel):
    left_id: str
    right_id: str
    decision: Literal["same_entity", "related_but_distinct", "different", "uncertain"]
    canonical_en: str | None = None
    canonical_zh: str | None = None
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)


class EntityAlignmentBatch(StrictModel):
    decisions: list[EntityAlignment]
    warnings: list[str] = Field(default_factory=list)


class IntegrationRequest(StrictModel):
    document_version_id: Ref
    input_revision: int = Field(ge=0)
    paper_type: PaperType
    candidates: list[CandidateRecord]
    allowed_evidence: list[EvidenceInput]
    coverage_gaps: list[str]


class SelectionRequest(StrictModel):
    document_version_id: Ref
    input_revision: int = Field(ge=0)
    paper_type: PaperType
    density: Literal["concise", "standard", "detailed"]
    root_candidates: list[CandidateRecord]
    units: list[KnowledgeUnit]
    coverage_gaps: list[str]


class SourceAssociation(AssociationProposal):
    id: Ref
    document_version_id: Ref


def validate_unit_memberships(
    unit: KnowledgeUnit,
    records: dict[str, CandidateRecord],
    associations: dict[str, SourceAssociation],
) -> None:
    included = {unit.root_claim_id, *(m.member_id for m in unit.memberships)}
    if included - records.keys():
        raise ValueError("unknown unit candidate")
    if records[unit.root_claim_id].content.kind != "Claim":
        raise ValueError("unit root must be a Claim")
    if any(records[i].document_version_id != unit.document_version_id for i in included):
        raise ValueError("cross-document member")
    for member in unit.memberships:
        adjacency: dict[str, set[str]] = {}
        for aid in member.association_ids:
            if aid not in associations:
                raise ValueError("unknown unit association")
            edge = associations[aid]
            if edge.document_version_id != unit.document_version_id:
                raise ValueError("cross-document association")
            if edge.source_id not in included or edge.target_id not in included:
                raise ValueError("association outside unit")
            check_relation(
                records[edge.source_id].content.kind,
                records[edge.target_id].content.kind,
                edge.relation,
            )
            adjacency.setdefault(edge.source_id, set()).add(edge.target_id)
        reached = {unit.root_claim_id}
        while True:
            expanded = reached | {b for a in reached for b in adjacency.get(a, set())}
            if expanded == reached:
                break
            reached = expanded
        if member.member_id not in reached:
            raise ValueError("unreachable unit member")


def validate_passage_context(
    passage: GroundedPassage,
    allowed_dependencies: list[VersionedDependency],
    allowed_evidence: dict[str, str],
) -> None:
    for dependency in passage.dependencies:
        if dependency not in allowed_dependencies:
            raise ValueError("unknown or stale passage dependency")
    versions = {d.document_version_id for d in passage.dependencies if d.source_kind == "paper"}
    for eid in passage.evidence_ids:
        if eid not in allowed_evidence or allowed_evidence[eid] not in versions:
            raise ValueError("evidence does not belong to a supplied paper dependency")


def validate_selection_proposal(proposal: CoreSelectionProposal, request: SelectionRequest) -> None:
    if (proposal.document_version_id, proposal.input_revision) != (
        request.document_version_id,
        request.input_revision,
    ):
        raise ValueError("stale or cross-document selection proposal")
    if {h.root_claim_id for h in proposal.recommendations} != {
        r.id for r in request.root_candidates
    }:
        raise ValueError("selection suggestions must account for every supplied root")


CONTRACTS = (
    EvidenceSpan,
    SourceTable,
    PaperOutline,
    ExtractionRequest,
    KnowledgeExtractionBatch,
    CandidateRecord,
    IntegrationRequest,
    PaperIntegrationProposal,
    KnowledgeUnit,
    SelectionRequest,
    CoreSelectionProposal,
    GraphSelection,
    SelectionPreference,
    GraphProjection,
    ComparabilityReport,
    RelationInference,
    EntityAlignmentBatch,
    SourceAssociation,
    RetrievalHit,
    QueryAnswer,
    QueryDistillation,
    LintIssueBatch,
    ReadingSynthesisDraft,
    WikiDeltaProposal,
    TranslationRepair,
    NodeDetail,
    GraphLayoutSnapshot,
    JobBatchRecord,
    ModelRunRecord,
)


def export_schemas() -> None:
    out = Path(__file__).parent / "generated"
    out.mkdir(exist_ok=True)
    for contract in CONTRACTS:
        (out / f"{contract.__name__}.schema.json").write_text(
            json.dumps(contract.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"Generated {len(CONTRACTS)} reference schemas (not runtime API).")


if __name__ == "__main__":
    export_schemas()
