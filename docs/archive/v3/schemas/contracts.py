"""ResearchGraph v3 reference contracts.

These contracts are executable examples, not a replacement for the current DB
schema. The service must additionally check evidence ownership and exact PDF
span alignment, and must allocate durable IDs outside model output.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NodeKind(str, Enum):
    Paper = "Paper"
    Concept = "Concept"
    Method = "Method"
    Claim = "Claim"
    ResearchQuestion = "ResearchQuestion"


class SourceStatus(str, Enum):
    anchored = "anchored"
    needs_evidence = "needs_evidence"
    source_unavailable = "source_unavailable"
    invalid_anchor = "invalid_anchor"


class ReviewStatus(str, Enum):
    unreviewed = "unreviewed"
    accepted = "accepted"
    edited = "edited"
    rejected = "rejected"
    superseded = "superseded"


class KnowledgeOrigin(str, Enum):
    paper_author = "paper_author"
    citation_report = "citation_report"
    user = "user"
    model = "model"


class ConditionState(str, Enum):
    known = "known"
    unknown = "unknown"
    not_applicable = "not_applicable"
    conflicting = "conflicting"


class ConditionCandidate(StrictModel):
    dimension: str = Field(min_length=1)
    state: ConditionState
    value_en: str | None = None
    value_zh: str | None = None
    unit: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_known_state(self) -> "ConditionCandidate":
        if self.state == ConditionState.known and (
            not self.value_en and not self.value_zh or not self.evidence_ids
        ):
            raise ValueError("known condition requires a value and evidence")
        if self.state in (ConditionState.unknown, ConditionState.not_applicable):
            if self.value_en is not None or self.value_zh is not None:
                raise ValueError("unknown/not_applicable condition must not assert a value")
        return self


class FindingCandidate(StrictModel):
    finding_en: str = Field(min_length=1)
    finding_zh: str = Field(min_length=1)
    metric_en: str | None = None
    metric_zh: str | None = None
    reported_value: str | None = None
    baseline: str | None = None
    unit: str | None = None
    evidence_ids: list[str] = Field(min_length=1)


class ClaimDetail(StrictModel):
    statement_en: str = Field(min_length=1)
    statement_zh: str = Field(min_length=1)
    modality: Literal["asserted", "conditional", "suggested", "speculative", "negated", "unknown"]
    scope_en: str | None = None
    scope_zh: str | None = None
    conditions: list[ConditionCandidate] = Field(default_factory=list)
    findings: list[FindingCandidate] = Field(default_factory=list)


class ExtractedNode(StrictModel):
    local_ref: str = Field(min_length=1)
    kind: NodeKind
    label_zh: str = Field(min_length=1)
    label_en: str = Field(min_length=1)
    summary_zh: str = Field(min_length=1)
    summary_en: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    origin: KnowledgeOrigin
    claim_detail: ClaimDetail | None = None

    @model_validator(mode="after")
    def consistent_kind_and_evidence(self) -> "ExtractedNode":
        if self.kind == NodeKind.Claim and self.claim_detail is None:
            raise ValueError("Claim node requires claim_detail")
        if self.kind != NodeKind.Claim and self.claim_detail is not None:
            raise ValueError("Only Claim may contain claim_detail")
        if self.kind != NodeKind.Paper and not self.evidence_ids:
            raise ValueError("Extracted knowledge nodes require source evidence IDs")
        return self


class GraphLinkCandidate(StrictModel):
    source_local_ref: str
    target_local_ref: str
    relation: Literal[
        "ABOUT", "USES_METHOD", "INVOLVES_CONCEPT", "STUDIES",
        "RELATED_TO", "QUESTIONS", "HAS_METHOD"
    ]
    evidence_ids: list[str] = Field(default_factory=list)


class KnowledgeExtractionBatch(StrictModel):
    document_version_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    items: list[ExtractedNode] = Field(default_factory=list)
    links: list[GraphLinkCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_local_refs(self) -> "KnowledgeExtractionBatch":
        refs = [x.local_ref for x in self.items]
        if len(refs) != len(set(refs)):
            raise ValueError("local_ref must be unique within batch")
        allowed = set(refs)
        for link in self.links:
            if link.source_local_ref not in allowed or link.target_local_ref not in allowed:
                raise ValueError("links must reference existing local_refs")
        return self


class EvidenceSpan(StrictModel):
    id: str
    document_version_id: str
    paragraph_id: str
    page_index: int = Field(ge=0)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    quote: str = Field(min_length=1)
    text_sha256: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def check_offsets(self) -> "EvidenceSpan":
        if self.end_offset <= self.start_offset:
            raise ValueError("end must be after start")
        return self


class GraphNode(StrictModel):
    id: str
    kind: NodeKind
    label_zh: str
    label_en: str
    detail_ref: str
    source_status: SourceStatus
    review_status: ReviewStatus
    knowledge_origin: KnowledgeOrigin
    badges: list[str] = Field(default_factory=list)
    size: float = Field(default=1.0, gt=0)


class GraphEdge(StrictModel):
    id: str
    source: str
    target: str
    relation: str
    epistemic_status: Literal["source_reported", "model_inferred", "user_confirmed"]
    review_status: ReviewStatus
    is_dashed: bool
    detail_ref: str

    @model_validator(mode="after")
    def inferred_edges_styled(self) -> "GraphEdge":
        if self.epistemic_status == "model_inferred" and self.review_status == ReviewStatus.unreviewed:
            if not self.is_dashed:
                raise ValueError("unreviewed model-inferred edges must be dashed")
        if self.relation == "NO_DECISION":
            raise ValueError("NO_DECISION is not a graph relation edge")
        return self


class GraphFilter(StrictModel):
    scope: Literal["project", "paper", "concept", "question", "local"]
    id: str
    depth: int = Field(ge=0, le=5)


class GraphProjection(StrictModel):
    project_id: str
    graph_revision: int = Field(ge=0)
    filter: GraphFilter
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    has_more: bool
    next_cursor: str | None = None

    @model_validator(mode="after")
    def check_edges_resolve(self) -> "GraphProjection":
        ids = {n.id for n in self.nodes}
        if len(ids) != len(self.nodes):
            raise ValueError("graph node IDs must be unique")
        if any(e.source not in ids or e.target not in ids for e in self.edges):
            raise ValueError("graph edges must link nodes present in this projection")
        return self


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


class RelationDecision(str, Enum):
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
    def enforce_decision_semantics(self) -> "RelationInference":
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


class JobBatchRecord(StrictModel):
    job_id: str
    batch_id: str
    chunk_id: str
    input_hash: str
    document_version_id: str
    prompt_version: str
    model_id: str
    state: Literal[
        "queued", "running", "validated", "committed", "retryable_failed", "terminal_failed", "needs_repair"
    ]
    committed_revision: int | None = Field(default=None, ge=0)
    attempts: int = Field(default=0, ge=0)
    last_error_code: str | None = None


def iter_all_evidence_ids(batch: KnowledgeExtractionBatch) -> set[str]:
    """Collect all IDs referenced by the model; does not verify quote alignment."""
    refs: set[str] = set()
    for item in batch.items:
        refs.update(item.evidence_ids)
        if item.claim_detail:
            for c in item.claim_detail.conditions:
                refs.update(c.evidence_ids)
            for f in item.claim_detail.findings:
                refs.update(f.evidence_ids)
    for link in batch.links:
        refs.update(link.evidence_ids)
    return refs


def require_allowed_evidence(batch: KnowledgeExtractionBatch, allowed: set[str]) -> None:
    invalid = iter_all_evidence_ids(batch) - allowed
    if invalid:
        raise ValueError(f"model referenced unknown/out-of-scope evidence IDs: {sorted(invalid)}")


def verify_span_exact(span: EvidenceSpan, normalized_paragraph: str) -> bool:
    """A minimal exact-offset check; production must also validate source hash/version."""
    return normalized_paragraph[span.start_offset : span.end_offset] == span.quote



class OutlineSection(StrictModel):
    local_ref: str
    heading: str
    heading_zh: str
    paragraph_ids: list[str]
    section_type: Literal[
        "abstract", "introduction", "related_work", "method", "experiment",
        "result", "discussion", "conclusion", "references", "other"
    ]


class PaperOutline(StrictModel):
    paper_id: str
    sections: list[OutlineSection]
    warnings: list[str] = Field(default_factory=list)


class TranslationRepair(StrictModel):
    node_id: str
    label_zh: str
    summary_zh: str
    translation_status: Literal["machine_generated", "needs_review"]
    warnings: list[str] = Field(default_factory=list)


class QueryCitation(StrictModel):
    ref_id: str
    supports: str


class QueryAnswer(StrictModel):
    answer_zh: str
    answer_en: str | None = None
    citations: list[QueryCitation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    knowledge_status: Literal["source_grounded", "mixed_sources", "insufficient"]
    candidate_insights: list[str] = Field(default_factory=list)


class DistilledKnowledgeCandidate(StrictModel):
    local_ref: str
    kind: Literal["Insight", "Synthesis", "ResearchQuestion", "Hypothesis"]
    title_zh: str
    content_zh: str
    epistemic_status: Literal["model_suggested", "user_authored", "source_reported"]
    depends_on: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class QueryDistillation(StrictModel):
    candidates: list[DistilledKnowledgeCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LintIssueDraft(StrictModel):
    issue_type: Literal[
        "overgeneralization", "incorrect_attribution", "incomparable_claims",
        "entity_merge_error", "translation_mismatch", "stale_synthesis", "other"
    ]
    severity: Literal["low", "medium", "high"]
    affected_ids: list[str] = Field(min_length=1)
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)
    suggested_action: str
    requires_review: bool


class LintIssueBatch(StrictModel):
    issues: list[LintIssueDraft] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ReadingSynthesisDraft(StrictModel):
    title: str
    frontmatter: dict[str, str | int | list[str]]
    markdown_body: str
    dependency_ids: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WikiEditDraft(StrictModel):
    section_id: str
    operation: Literal["replace", "append", "mark_stale"]
    new_text: str
    depends_on: list[str] = Field(default_factory=list)
    reason: str


class WikiDeltaProposal(StrictModel):
    wiki_page_id: str
    base_content_hash: str
    edits: list[WikiEditDraft] = Field(default_factory=list)
    requires_review: bool
    warnings: list[str] = Field(default_factory=list)


class NodeDetail(StrictModel):
    id: str
    kind: NodeKind
    label_zh: str
    label_en: str
    full_text_en: str | None = None
    translation_zh: str | None = None
    source_status: SourceStatus
    review_status: ReviewStatus
    knowledge_origin: KnowledgeOrigin
    conditions: list[ConditionCandidate] = Field(default_factory=list)
    findings: list[FindingCandidate] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    related_node_refs: list[str] = Field(default_factory=list)
    zotero_item_key: str | None = None
    document_version_id: str | None = None


class NodeLayout(StrictModel):
    node_id: str
    x: float
    y: float
    pinned: bool = False


class GraphLayoutSnapshot(StrictModel):
    project_id: str
    view_id: str
    layout_version: int = Field(ge=1)
    positions: list[NodeLayout]
    zoom: float = Field(default=1.0, gt=0)
    pan_x: float = 0
    pan_y: float = 0

if __name__ == "__main__":
    import pathlib
    out = pathlib.Path(__file__).resolve().parent / "generated"
    out.mkdir(exist_ok=True)
    for cls in [
        KnowledgeExtractionBatch, GraphProjection, ComparabilityReport,
        RelationInference, EntityAlignmentBatch, EvidenceSpan, JobBatchRecord,
        PaperOutline, TranslationRepair, QueryAnswer, QueryDistillation,
        LintIssueBatch, ReadingSynthesisDraft, WikiDeltaProposal,
        NodeDetail, GraphLayoutSnapshot,
    ]:
        (out / f"{cls.__name__}.schema.json").write_text(
            __import__("json").dumps(cls.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print("generated", len(list(out.glob("*.schema.json"))), "JSON Schema documents")
