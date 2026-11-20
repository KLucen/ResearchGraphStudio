from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreate(InputModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    experience_mode: Literal["lite"] = "lite"

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("项目名称不能为空")
        return value


class ProjectView(ProjectCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    experience_mode: Literal["lite"] = "lite"
    created_at: str


class ProjectList(BaseModel):
    items: list[ProjectView]
    next_cursor: int | None


class JobCreate(InputModel):
    kind: Literal["diagnostics"] = "diagnostics"


class JobView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    kind: str
    project_id: str | None
    status: Literal["queued", "running", "succeeded", "failed", "cancelled", "interrupted"]
    stage: (
        Literal[
            "queued",
            "starting",
            "reading",
            "parsing",
            "checking",
            "saving",
            "diagnostics",
            "generating",
            "recognizing",
            "document_source",
            "preparing_provider",
            "model_parsing",
            "document_rendering",
            "document_connecting",
            "document_uploading",
            "document_waiting",
            "document_receiving",
            "document_batching",
            "document_repairing",
            "document_boundary",
            "validating_document",
            "saving_document",
            "indexing",
            "completed",
            "failed",
            "interrupted",
            "paused",
        ]
        | None
    ) = None
    attempt: int
    error: str | None
    result: dict[str, Any] | None
    resume_adapter_available: bool = False
    created_at: str
    updated_at: str

    @field_validator("stage", mode="before")
    @classmethod
    def retired_translation_stage(cls, value: Any, info: ValidationInfo) -> Any:
        # Old translation workers persisted service phases that were never in
        # the public Job DTO. Present them through generic phases without
        # changing immutable terminal history or adding an active feature.
        if info.data.get("kind") == "pdf_translation" and value in {
            "starting_service",
            "stopping_service",
        }:
            return {
                "succeeded": "completed",
                "failed": "failed",
                "cancelled": "interrupted",
                "interrupted": "interrupted",
            }.get(
                str(info.data.get("status", "")),
                "starting" if value == "starting_service" else "saving",
            )
        return value


class JobList(BaseModel):
    items: list[JobView]
    next_cursor: str | None


class WorkspaceCleanup(BaseModel):
    removed: int = 0
    busy: int = 0
    retained: int = 0
    errors: int = 0


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    protocol_version: int
    schema_version: str
    database: Literal["ready"] = "ready"
    fts5: bool
    temporary_files: WorkspaceCleanup | None = None


class PdfImport(InputModel):
    path: str = Field(min_length=1, max_length=4096)
    mode: Literal["reference", "managed"] = "reference"
    # The native host keeps the real path; the web layer only sends this opaque
    # selection identity together with the post-import choices.
    selection_id: str | None = Field(default=None, min_length=1, max_length=200)
    post_import_plan: "PdfPostImportPlan | None" = None


class SourceSnapshot(InputModel):
    paper_id: str | None = Field(default=None, max_length=36)
    file_name: str | None = Field(default=None, max_length=512)
    page_count: int | None = Field(default=None, ge=1, le=100000)
    provider_file_id: str | None = Field(default=None, max_length=240)
    source_generation: int | None = Field(default=None, ge=0)


class ImportPlan(InputModel):
    postprocess_contract_version: Literal[2, 3, 4] = 4
    overview: bool = False
    reading: bool = False
    translation_mode: Literal["full", "none"] = "none"
    modality: Literal["auto", "required", "text", "pdf", "image"] = "text"
    require_multimodal: bool = False
    allow_network: bool = False
    provider_profile_id: str | None = Field(default=None, max_length=160)
    document_batching: bool = False
    pages_per_batch: int = Field(default=5, ge=2, le=8)
    allow_format_repair: bool = False
    allow_boundary_review: bool = True

    @model_validator(mode="after")
    def validate_translation(self) -> "ImportPlan":
        if self.translation_mode == "full" and not self.reading:
            raise ValueError("只有选择全文精读后才能生成逐段中文翻译")
        if self.modality == "auto":
            self.modality = "pdf"
        elif self.modality == "required":
            self.modality = "pdf"
            self.require_multimodal = True
        if self.require_multimodal and self.modality == "text":
            raise ValueError("需要多模态时，modality 不能为 text")
        return self


class PdfPostImportPlan(InputModel):
    """Desktop import choices translated into the model-first plan."""

    parse: bool = True
    overview: bool = False
    reading: bool = False
    translation_mode: Literal["full", "none"] = "none"
    modality: Literal["auto", "required"] = "auto"
    extract_formulas: Literal[True] = True
    extract_tables: Literal[True] = True
    # Sending a PDF to a configured model is an explicit user authorization.
    # Keep this separate from the extraction choices so merely opening the
    # import panel never creates a network request or a paid task.
    allow_network: bool = False
    provider_profile_id: str | None = Field(default=None, max_length=160)
    document_batching: bool = True
    pages_per_batch: int = Field(default=5, ge=2, le=8)
    allow_format_repair: bool = False
    allow_boundary_review: bool = True

    @model_validator(mode="after")
    def validate_translation(self) -> "PdfPostImportPlan":
        if self.translation_mode == "full" and not self.reading:
            raise ValueError("只有选择全文精读后才能生成逐段中文翻译")
        return self


class ImportSessionCreate(InputModel):
    source_kind: Literal["pdf", "zotero"] = "pdf"
    selection_id: str = Field(min_length=1, max_length=200)
    source_snapshot: SourceSnapshot = Field(default_factory=SourceSnapshot)
    plan: ImportPlan = Field(default_factory=ImportPlan)


class PaperParseRequest(InputModel):
    mode: Literal["local", "model"]
    post_import_plan: PdfPostImportPlan | None = None

    @model_validator(mode="after")
    def validate_parse_mode(self) -> "PaperParseRequest":
        if self.mode == "model" and (
            self.post_import_plan is None
            or not self.post_import_plan.parse
            or not self.post_import_plan.allow_network
        ):
            raise ValueError("模型解析需要选择模型解析并明确允许发送 PDF")
        if self.mode == "local" and self.post_import_plan is not None:
            raise ValueError("本地解析不接受模型生成计划，请选择本地解析或模型解析")
        return self


class ImportPlanItemView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    item_kind: Literal["document_parse", "paper_overview", "paper_reading", "translation"]
    status: Literal["planned", "queued", "running", "succeeded", "failed", "interrupted", "paused"]
    config: dict[str, Any]
    job_id: str | None
    attempt: int
    error: str | None
    result: dict[str, Any] | None
    created_at: str
    updated_at: str


class ImportSessionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    source_kind: Literal["pdf", "zotero"]
    selection_id: str
    source_snapshot: SourceSnapshot
    plan: ImportPlan
    status: Literal["planned", "queued", "running", "succeeded", "failed", "interrupted", "paused"]
    error: str | None
    created_at: str
    updated_at: str
    items: list[ImportPlanItemView] = Field(default_factory=list)


class PaperView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    title: str
    created_at: str


class PaperList(BaseModel):
    items: list[PaperView]
    next_cursor: int | None


class RevisionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    paper_id: str
    sha256: str
    parser_version: str
    page_count: int
    warnings: list[str]
    created_at: str


class SourceAction(InputModel):
    expected_generation: int = Field(ge=0)


class SourceRelocate(SourceAction):
    path: str = Field(min_length=1, max_length=4096)


class FileCheck(BaseModel):
    state: Literal["available", "changed", "missing", "unreadable", "too_large", "unstable"]
    observed_sha256: str | None


class SourceCheck(BaseModel):
    checked_at: str
    original: FileCheck
    managed: FileCheck | None


class SourceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    revision_id: str
    path: str
    mode: Literal["reference", "managed"]
    generation: int
    last_check: SourceCheck | None


class PaperDetail(BaseModel):
    paper: PaperView
    revisions: list[RevisionView]
    sources: list[SourceView]
    zotero_links: list[dict[str, str]] = []


class ChunkView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    revision_id: str
    page_index: int
    page_label: str
    block_index: int
    text: str
    bbox: list[float]


class ChunkList(BaseModel):
    items: list[ChunkView]
    next_cursor: int | None


class SectionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_version_id: str
    title: str
    ordinal: int
    role: str
    parent_id: str | None
    level: int
    start_page: int
    end_page: int
    excluded: bool
    text: str = ""
    chunk_ids: list[str] = Field(default_factory=list)


class EvidenceView(BaseModel):
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


class DocumentStructure(BaseModel):
    document_version_id: str
    sections: list[SectionView]
    evidence: list[EvidenceView] = Field(default_factory=list)
    structured_document: dict[str, Any] | None = None


class SectionList(BaseModel):
    document_version_id: str
    sections: list[SectionView]


class SearchHit(BaseModel):
    chunk_id: str
    section_id: str
    document_version_id: str
    paper_id: str
    text: str
    page_index: int
    page_label: str
    score: float


class SearchResults(BaseModel):
    query: str
    items: list[SearchHit]
