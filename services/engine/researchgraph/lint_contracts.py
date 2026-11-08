"""Program-owned Lint contracts, distinct from optional P09 model suggestions."""

from typing import Any, Literal

from pydantic import Field

from researchgraph.knowledge_contracts import StrictModel


class LintRequest(StrictModel):
    paper_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    include_personal: bool = False


class LintAdvance(StrictModel):
    max_items: int = Field(default=25, ge=1, le=100)


class LintDocumentView(StrictModel):
    id: str
    title: str
    kind: str
    status: str
    current_version_id: str | None
    latest_version_id: str | None


class LintDocumentPage(StrictModel):
    items: list[LintDocumentView]
    total: int
    page: int
    page_size: int


class LintRepairStep(StrictModel):
    id: str
    title: str
    description: str
    action: str
    automated: bool = False
    requires_model: bool | None = False


class LintRepairPlan(StrictModel):
    status: Literal["informational", "actionable", "blocked"]
    summary: str
    steps: list[LintRepairStep] = Field(default_factory=list)
    safeguards: list[str] = Field(default_factory=list)


class LintRunView(StrictModel):
    id: str
    project_id: str
    status: Literal["queued", "running", "completed", "partial", "cancelled", "input_stale"]
    phase: Literal["scanning", "rebuilding_dependencies", "finished"] = "scanning"
    timings: dict[str, float] = Field(default_factory=dict)
    scope: dict[str, Any]
    rule_version: str
    event_sequence: int
    input_hash: str
    total: int
    processed: int
    progress: float
    counts: dict[str, int]
    diff: dict[str, int]
    previous_run_id: str | None
    errors: list[dict[str, Any]]
    created_at: str
    updated_at: str
    finished_at: str | None


class LintIssueView(StrictModel):
    id: str
    fingerprint: str
    code: str
    rule_version: str
    severity: Literal["error", "warning", "info"]
    category: Literal[
        "evidence", "support", "dependency", "file", "condition", "link", "unverifiable"
    ]
    object_type: str
    object_id: str
    paper_id: str | None
    location: dict[str, Any]
    message: str
    suggestion: str
    repair_plan: LintRepairPlan | None = None
    lifecycle: Literal["new", "persistent", "resolved", "input_stale"]
    deterministic: Literal[True] = True


class LintRunPage(StrictModel):
    items: list[LintRunView]
    total: int
    page: int
    page_size: int


class LintIssuePage(StrictModel):
    items: list[LintIssueView]
    total: int
    page: int
    page_size: int
