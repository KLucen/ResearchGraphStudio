"""Strict public DTOs for the durable personal research library."""

from typing import Any, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from researchgraph.core import StrictModel


class LibrarySettings(StrictModel):
    auto_collect: bool = False
    auto_connect: bool = False
    allow_network: bool = False
    scope: Literal["project", "all", "collection"] = "project"
    collection_id: str | None = Field(default=None, min_length=1, max_length=36)
    max_candidates: int = Field(default=8, ge=1, le=50)
    max_requests_per_run: int | None = Field(default=2, ge=1, le=8)
    max_input_tokens: int | None = Field(default=48_000, ge=1024, le=2_000_000)
    max_output_tokens: int | None = Field(default=6000, ge=256, le=200_000)
    total_request_limit: int = Field(default=20, ge=1, le=100_000)

    @model_validator(mode="after")
    def configured_scope(self) -> Self:
        if (self.auto_collect or self.auto_connect) and not self.allow_network:
            raise ValueError("自动构建知识或关联需要明确允许模型网络请求")
        if self.scope == "collection" and not self.collection_id:
            raise ValueError("专题范围需要选择专题")
        return self


class LibraryView(StrictModel):
    id: str
    name: str
    settings: LibrarySettings
    created_at: str
    updated_at: str


class KnowledgeVersionView(StrictModel):
    id: str
    library_paper_id: str
    source_kind: str
    source_id: str
    source_paper_id: str
    project_id: str
    source_fingerprint: str
    snapshot_hash: str
    schema_version: str
    evidence_status: Literal["legacy", "grounded"]
    content: dict[str, Any]
    provider_id: str | None = None
    model_id: str | None = None
    job_id: str | None = None
    created_at: str


class LibrarySourceLinkView(StrictModel):
    paper_id: str | None
    original_paper_id: str
    project_id: str
    source_available: bool


class LibraryPaperView(StrictModel):
    id: str
    title: str
    note: str
    archived: bool
    project_ids: list[str]
    source_links: list[LibrarySourceLinkView]
    collection_ids: list[str]
    current_version: KnowledgeVersionView | None
    versions: list[KnowledgeVersionView]
    created_at: str
    updated_at: str


class LibraryPaperList(StrictModel):
    items: list[LibraryPaperView]
    total: int


class LibraryPaperUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    note: str | None = Field(default=None, max_length=20_000)
    archived: bool | None = None
    current_version_id: str | None = Field(default=None, min_length=1, max_length=36)


class CollectOverview(StrictModel):
    paper_id: str = Field(min_length=1, max_length=36)
    source_kind: Literal["local_revision", "model_parse"]
    source_id: str = Field(min_length=1, max_length=120)
    overview_result_id: str | None = Field(default=None, min_length=1, max_length=36)


class CollectionCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class CollectionUpdate(CollectionCreate):
    description: str = Field(max_length=2000)


class CollectionView(CollectionCreate):
    id: str
    created_at: str


class CollectionList(StrictModel):
    items: list[CollectionView]


class CollectionMembershipUpdate(StrictModel):
    paper_ids: list[UUID] = Field(min_length=1, max_length=100)
    action: Literal["add", "remove", "move"]
    source_collection_ids: list[UUID] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def valid_selection(self) -> Self:
        if len(set(self.paper_ids)) != len(self.paper_ids) or len(
            set(self.source_collection_ids)
        ) != len(self.source_collection_ids):
            raise ValueError("专题或论文选择重复")
        if (self.action == "move") != bool(self.source_collection_ids):
            raise ValueError("移动论文时需要明确选择原专题，其他操作无需原专题")
        return self


class CollectionMembershipResult(StrictModel):
    ok: Literal[True] = True
    added: int = Field(ge=0)
    removed: int = Field(ge=0)


class LibraryPosition(StrictModel):
    node_id: str = Field(min_length=1, max_length=240)
    x: float = Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)
    y: float = Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)
    pinned: bool = False


class LibraryViewport(StrictModel):
    x: float = Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)
    y: float = Field(ge=-1_000_000, le=1_000_000, allow_inf_nan=False)
    zoom: float = Field(ge=0.05, le=10, allow_inf_nan=False)


class LibraryLayout(StrictModel):
    positions: list[LibraryPosition] = Field(default_factory=list, max_length=2000)
    viewport: LibraryViewport | None = None

    @model_validator(mode="after")
    def unique_positions(self) -> Self:
        if len({position.node_id for position in self.positions}) != len(self.positions):
            raise ValueError("Duplicate library layout node")
        return self


class LibraryLayoutView(StrictModel):
    view_key: str = Field(default="all", min_length=1, max_length=120)
    layout: LibraryLayout = Field(default_factory=LibraryLayout)


class LibraryExport(StrictModel):
    schema_version: Literal["knowledge-library-export-1"] = "knowledge-library-export-1"
    library: LibraryView
    papers: list[LibraryPaperView]
    collections: list[CollectionView]
    reports: list[dict[str, Any]] = Field(default_factory=list)
    layouts: list[LibraryLayoutView] = Field(default_factory=list)


class LibraryActionResult(StrictModel):
    ok: bool = True
