"""Local, zero-model-call reading state DTOs."""

from typing import Literal

from pydantic import Field, field_validator

from researchgraph.core import StrictModel

SelfLevel = Literal["UNSET", "UNSURE", "PARTIAL", "CONFIDENT"]
CheckResult = Literal["NOT_CHECKED", "ADEQUATE", "PARTIAL", "MISCONCEPTION", "UNCERTAIN"]
Progress = Literal["NOT_STARTED", "READING", "COMPLETED"]


class ReadingQuestion(StrictModel):
    paragraph_id: str | None = None
    text: str = Field(min_length=1, max_length=1200)
    resolved: bool = False

    @field_validator("text")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question must not be blank")
        return value


class ReadingStatePut(StrictModel):
    document_version_id: str | None = None
    overview_result_id: str | None = None
    progress: Progress = "NOT_STARTED"
    self_assessment: SelfLevel = "UNSET"
    unresolved_concept_ids: list[str] = Field(default_factory=list, max_length=12)
    questions: list[ReadingQuestion] = Field(default_factory=list, max_length=40)

    @field_validator("unresolved_concept_ids")
    @classmethod
    def unique_concepts(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(not item.strip() for item in value):
            raise ValueError("Concept IDs must be nonblank and unique")
        return value


class ReadingStateView(StrictModel):
    paper_id: str
    document_version_id: str
    section_id: str
    progress: Progress = "NOT_STARTED"
    self_assessment: SelfLevel = "UNSET"
    unresolved_concept_ids: list[str] = Field(default_factory=list)
    questions: list[ReadingQuestion] = Field(default_factory=list)
    updated_at: str | None = None
    source_hash: str
    source_changed: bool = False
    overview_result_id: str | None = None
    unresolved_unlinked_ids: list[str] = Field(default_factory=list)


class RelatedSection(StrictModel):
    section_id: str
    title: str


class ConceptUnderstandingPut(StrictModel):
    document_version_id: str | None = None
    overview_result_id: str
    self_level: SelfLevel = "UNSET"
    note_zh: str = Field(default="", max_length=1600)


class ConceptUnderstandingView(StrictModel):
    id: str | None = None
    paper_id: str
    document_version_id: str
    overview_result_id: str | None
    graph_node_id: str
    node_label_zh: str
    node_label_en: str | None = None
    self_level: SelfLevel = "UNSET"
    last_check_result: CheckResult = "NOT_CHECKED"
    note_zh: str = ""
    last_check_note_zh: str = ""
    updated_at: str | None = None
    association_status: Literal["CURRENT", "NEEDS_RELINK"]
    has_unresolved_question: bool = False
    related_sections: list[RelatedSection] = Field(default_factory=list)


class ReaderContext(StrictModel):
    strategy: Literal["BRIDGE_GAPS", "CONNECT_ARGUMENT", "CRITICAL_READING", "REVISIT_DEFINITIONS"]
    unresolved_concepts: list[str] = Field(default_factory=list, max_length=3)
    prior_misunderstanding_summary: str = Field(default="", max_length=240)
    preferred_focus: str = Field(max_length=200)
