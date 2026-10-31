from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreate(InputModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)

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
    stage: Literal["starting", "reading", "parsing", "checking", "saving", "diagnostics"] | None = (
        None
    )
    attempt: int
    error: str | None
    result: dict[str, str | bool] | None
    created_at: str
    updated_at: str


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
