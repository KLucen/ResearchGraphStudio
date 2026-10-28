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
