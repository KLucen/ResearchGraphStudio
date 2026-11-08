"""Explicit external-source commands contain authorized roots, never absolute paths or evidence."""

from typing import Literal

from pydantic import Field, model_validator

from researchgraph.knowledge_contracts import StrictModel


class ExternalDocumentPreview(StrictModel):
    root_id: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)


class ExternalDocumentRegister(ExternalDocumentPreview):
    expected_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    title: str = Field(min_length=1)
    attribution: Literal["user_view", "external_source"]
    document_id: str | None = Field(default=None, min_length=1)
    base_version_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def explicit_baseline(self) -> "ExternalDocumentRegister":
        if not self.title.strip():
            raise ValueError("external document titles cannot be blank")
        if bool(self.document_id) != bool(self.base_version_id):
            raise ValueError("an update requires both document and base version IDs")
        return self
