"""P07 semantic transport and safe execution views; identities are program-owned."""

from typing import Literal

from pydantic import Field, model_validator

from researchgraph.knowledge_contracts import StrictModel
from researchgraph.query_contracts import QueryAnswer


class AnswerPassageWire(StrictModel):
    text: str = Field(min_length=1)
    attribution: Literal["paper_author", "citation_report", "user_view", "model_synthesis"]
    source_refs: list[str] = Field(min_length=1)
    limitations: list[str]

    @model_validator(mode="after")
    def meaningful(self) -> "AnswerPassageWire":
        if not self.text.strip() or any(not ref.strip() for ref in self.source_refs):
            raise ValueError("passages require text and nonblank source references")
        if len(self.source_refs) != len(set(self.source_refs)):
            raise ValueError("passage source references must be distinct")
        if any(not value.strip() for value in self.limitations):
            raise ValueError("limitations must be nonblank")
        return self


class AnswerWire(StrictModel):
    passages: list[AnswerPassageWire]
    limitations: list[str]

    @model_validator(mode="after")
    def explain_insufficient(self) -> "AnswerWire":
        if any(not value.strip() for value in self.limitations):
            raise ValueError("limitations must be nonblank")
        if not self.passages and not self.limitations:
            raise ValueError("an empty answer must explain missing support")
        return self


class QueryModelExecutionView(StrictModel):
    id: str
    sequence: int
    status: str
    usage: dict[str, int] = Field(default_factory=dict)
    duration_seconds: float | None = None
    finish_reason: str | None = None
    error_code: str | None = None
    error: str | None = None
    cost_known: bool = False


class QueryAnswerView(StrictModel):
    query_id: str
    status: Literal[
        "not_started",
        "queued",
        "running",
        "succeeded",
        "failed",
        "interrupted",
        "cancelled",
        "insufficient",
    ]
    job_id: str | None = None
    answer: QueryAnswer | None = None
    model_runs: list[QueryModelExecutionView] = Field(default_factory=list)
    can_continue: bool = False
    error_code: str | None = None
    error: str | None = None
    request_count: int = 0
    request_limit: int = 2
