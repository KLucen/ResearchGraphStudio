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
    attempt: int
    error: str | None
    result: dict[str, str | bool] | None
    created_at: str
    updated_at: str


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    protocol_version: int
    schema_version: str
    database: Literal["ready"] = "ready"
    fts5: bool


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


class SourceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    revision_id: str
    path: str
    mode: Literal["reference", "managed"]


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
