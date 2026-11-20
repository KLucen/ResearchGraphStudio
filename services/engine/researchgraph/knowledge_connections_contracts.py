"""Small grounded connection DTO; no free-form unsupported report paragraphs."""

from typing import Literal

from pydantic import Field

from researchgraph.core import StrictModel

ConnectionType = Literal[
    "SAME_PROBLEM",
    "RELATED_CONCEPT",
    "RELATED_METHOD",
    "COMPLEMENTARY_METHODS",
    "COMPARABLE_RESULTS",
    "RESEARCH_OPPORTUNITY",
]


class ConnectionDraft(StrictModel):
    ref: str = Field(pattern=r"^r[1-9][0-9]*$")
    target_ref: str = Field(pattern=r"^p[1-9][0-9]*$")
    source_node_id: str = Field(min_length=1, max_length=160)
    target_node_id: str = Field(min_length=1, max_length=160)
    type: ConnectionType
    explanation_zh: str = Field(min_length=1, max_length=1200)
    limitations_zh: str = Field(min_length=1, max_length=800)
    source_ref_ids: list[str] = Field(min_length=1, max_length=12)
    target_ref_ids: list[str] = Field(min_length=1, max_length=12)


class ConnectionSummaryDraft(StrictModel):
    text_zh: str = Field(min_length=1, max_length=1200)
    relation_refs: list[str] = Field(min_length=1, max_length=24)


class ConnectionsDraft(StrictModel):
    schema_version: Literal["knowledge-connections-1"]
    relations: list[ConnectionDraft] = Field(max_length=40)
    summary: list[ConnectionSummaryDraft] = Field(max_length=10)
    no_relation_reason_zh: str | None = Field(default=None, max_length=800)


class KnowledgeExtractInput(StrictModel):
    paper_id: str = Field(min_length=1, max_length=36)
    source_kind: Literal["local_revision", "model_parse"]
    source_id: str = Field(min_length=1, max_length=36)
    allow_network: bool = False


class KnowledgeConnectInput(StrictModel):
    allow_network: bool = False
    force_regenerate: bool = False


class KnowledgeRetryInput(StrictModel):
    allow_network: bool = False


class KnowledgeReportEdit(StrictModel):
    read: bool | None = None
    pinned: bool | None = None
    note: str | None = Field(default=None, max_length=5000)
