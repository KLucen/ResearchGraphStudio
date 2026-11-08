"""Versioned P09/P10/P11 semantic transport; identities and file actions are program-owned."""

from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from researchgraph.knowledge_contracts import StrictModel
from researchgraph.query_answer_contracts import AnswerPassageWire
from researchgraph.query_contracts import QueryRequest

WorkflowKind = Literal["lint_semantic", "wiki_synthesis", "wiki_delta"]


class PersonalSources(StrictModel):
    version: Literal["p5-personal-sources-1"] = "p5-personal-sources-1"
    note_ids: list[str] = Field(default_factory=list)
    annotation_ids: list[str] = Field(default_factory=list)
    external_version_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def distinct(self) -> "PersonalSources":
        for values in (self.note_ids, self.annotation_ids, self.external_version_ids):
            if len(values) != len(set(values)) or any(not v.strip() for v in values):
                raise ValueError("personal sources require distinct nonempty snapshot IDs")
        return self


class WorkflowPrepare(StrictModel):
    kind: WorkflowKind
    query: QueryRequest
    lint_run_id: str | None = None
    page_id: str | None = None
    base_version_id: str | None = None
    affected_section_ids: list[str] = Field(default_factory=list)
    personal_sources: PersonalSources | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def explicit_scope(self) -> "WorkflowPrepare":
        if self.query.purpose != "model":
            raise ValueError("P5 model workflows require explicit model purpose")
        if (
            self.personal_sources
            and not self.query.include_personal
            and any(
                (
                    self.personal_sources.note_ids,
                    self.personal_sources.annotation_ids,
                    self.personal_sources.external_version_ids,
                )
            )
        ):
            raise ValueError("selected personal sources require include_personal")
        if self.kind == "wiki_delta":
            if not self.page_id or not self.base_version_id or not self.affected_section_ids:
                raise ValueError("delta requires a page, baseline and explicit section scope")
        elif self.page_id or self.base_version_id or self.affected_section_ids:
            raise ValueError("only delta workflows can target an existing page")
        if self.kind != "lint_semantic" and self.lint_run_id:
            raise ValueError("lint run is only valid for semantic lint")
        if self.kind == "lint_semantic" and not self.lint_run_id:
            raise ValueError("semantic lint requires a deterministic report")
        if len(set(self.affected_section_ids)) != len(self.affected_section_ids):
            raise ValueError("affected sections must be distinct")
        return self


class WorkflowGenerate(StrictModel):
    allow_network: Literal[True]
    continue_requested: bool = False


class WikiConditionWire(StrictModel):
    dimension: str = Field(min_length=1)
    state: Literal["known", "unknown", "not_applicable", "conflicting"]
    value: str | None
    unit: str | None

    @model_validator(mode="after")
    def known_value(self) -> "WikiConditionWire":
        if self.state == "known" and (not self.value or not self.value.strip()):
            raise ValueError("known conditions require a value")
        if self.state in {"unknown", "not_applicable"} and (
            self.value is not None or self.unit is not None
        ):
            raise ValueError("unknown or inapplicable conditions cannot claim a value or unit")
        return self


class WikiPassageWire(AnswerPassageWire):
    heading: str
    conditions: list[WikiConditionWire]


class SynthesisWire(StrictModel):
    title: str = Field(min_length=1)
    passages: list[WikiPassageWire]
    coverage_gaps: list[str]

    @model_validator(mode="after")
    def not_invented(self) -> "SynthesisWire":
        if not self.title.strip() or (not self.passages and not self.coverage_gaps):
            raise ValueError("empty syntheses must explain missing support")
        return self


class ReplaceWire(StrictModel):
    op: Literal["replace"]
    section_ref: str
    passage: WikiPassageWire


class AppendWire(StrictModel):
    op: Literal["append"]
    after_section_ref: str
    passage: WikiPassageWire


class StaleWire(StrictModel):
    op: Literal["mark_stale"]
    section_ref: str
    reason: str = Field(min_length=1)


class DeltaWire(StrictModel):
    edits: list[Annotated[ReplaceWire | AppendWire | StaleWire, Field(discriminator="op")]]
    coverage_gaps: list[str]


class SemanticIssueWire(StrictModel):
    code: Literal[
        "overgeneralization",
        "incorrect_attribution",
        "translation_mismatch",
        "possible_duplicate",
        "possible_numeric_misreading",
        "insufficient_context",
        "other",
    ]
    severity: Literal["warning", "info"]
    affected_refs: list[str] = Field(min_length=1)
    evidence_refs: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    suggested_action: str = Field(min_length=1)
    uncertainty: str = Field(min_length=1)


class SemanticLintWire(StrictModel):
    issues: list[SemanticIssueWire]
    limitations: list[str]


class WorkflowModelView(StrictModel):
    id: str
    status: str
    usage: dict[str, int]
    duration_seconds: float | None
    error_code: str | None
    error: str | None
    cost_known: Literal[False] = False


class WorkflowView(StrictModel):
    id: str
    kind: WorkflowKind
    status: str
    historical_status: str
    input_hash: str
    job_id: str | None
    result: dict[str, Any] | None
    question: str
    created_at: str
    updated_at: str
    error_code: str | None
    error: str | None
    request_count: int
    request_limit: Literal[2] = 2
    can_continue: bool
    model_runs: list[WorkflowModelView]


class WorkflowList(StrictModel):
    items: list[WorkflowView]
