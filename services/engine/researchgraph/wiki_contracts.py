"""Program-bound Wiki editing and publication commands; no model-supplied paths."""

from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from researchgraph.knowledge_contracts import StrictModel
from researchgraph.query_contracts import DocumentPassageInput

Sha = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class WikiCondition(StrictModel):
    dimension: str = Field(min_length=1)
    state: Literal["known", "unknown", "not_applicable", "conflicting"]
    value: str | None = None
    unit: str | None = None

    @model_validator(mode="after")
    def explicit_value(self) -> "WikiCondition":
        if not self.dimension.strip():
            raise ValueError("condition dimensions cannot be blank")
        if self.state == "known" and (self.value is None or not self.value.strip()):
            raise ValueError("known conditions require a value")
        if self.state in {"unknown", "not_applicable"} and (
            self.value is not None or self.unit is not None
        ):
            raise ValueError("unknown or inapplicable conditions cannot claim a value or unit")
        return self


class WikiPassageInput(DocumentPassageInput):
    # local_ref is allocated by the program, never used as a formal model ID.
    local_ref: str = "new"
    heading: str = ""
    conditions: list[WikiCondition] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def distinct_links(self) -> "WikiPassageInput":
        if len(self.links) != len(set(self.links)) or any(not v.strip() for v in self.links):
            raise ValueError("links must be distinct page IDs")
        return self


class WikiDraftInput(StrictModel):
    title: str = Field(min_length=1)
    passages: list[WikiPassageInput] = Field(min_length=1)
    provenance: dict[str, Any] = Field(default_factory=dict)


class WikiReplace(StrictModel):
    op: Literal["replace"]
    section_id: str = Field(min_length=1)
    passage: WikiPassageInput


class WikiAppend(StrictModel):
    op: Literal["append"]
    after_section_id: str | None = None
    passage: WikiPassageInput


class WikiMarkStale(StrictModel):
    op: Literal["mark_stale"]
    section_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


WikiEdit = Annotated[WikiReplace | WikiAppend | WikiMarkStale, Field(discriminator="op")]


class WikiPatchInput(StrictModel):
    base_version_id: str = Field(min_length=1)
    base_content_hash: Sha
    operations: list[WikiEdit] = Field(min_length=1)
    provenance: dict[str, Any] = Field(default_factory=dict)


class WikiSaveCommand(StrictModel):
    version_id: str = Field(min_length=1)
    expected_head_version_id: str = Field(min_length=1)
    expected_content_hash: Sha


class WikiRootCommand(StrictModel):
    path: str = Field(min_length=1)


class WikiPublishCommand(StrictModel):
    root_id: str = Field(min_length=1)
    version_id: str = Field(min_length=1)
    expected_content_hash: Sha
    expected_target_hash: Sha | None = None
