"""Runtime contracts for local Query preparation; no answer generation is implied."""

from typing import Any, Literal

from pydantic import Field, model_validator

from researchgraph.knowledge_contracts import StrictModel

Purpose = Literal["local", "model"]
ContentState = Literal["valid", "stale", "invalid", "unverified"]
FileState = Literal["not_exported", "in_sync", "modified", "missing", "conflict", "unavailable"]


class QueryRequest(StrictModel):
    project_id: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=12000)
    paper_ids: list[str] = Field(default_factory=list)
    document_version_ids: list[str] = Field(default_factory=list)
    source_kinds: list[Literal["paper", "knowledge", "chunk", "wiki", "synthesis", "note"]] = Field(
        default_factory=list
    )
    knowledge_kinds: list[
        Literal[
            "claim",
            "method",
            "finding",
            "condition",
            "experiment",
            "metric",
            "concept",
            "research_question",
            "argument",
            "limitation",
        ]
    ] = Field(default_factory=list)
    include_personal: bool = False
    purpose: Purpose = "local"
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def nonblank(self) -> "QueryRequest":
        if not self.question.strip():
            raise ValueError("question must not be blank")
        for ids in (
            self.paper_ids,
            self.document_version_ids,
            self.source_kinds,
            self.knowledge_kinds,
        ):
            if len(ids) != len(set(ids)) or any(not value.strip() for value in ids):
                raise ValueError("source scope must contain distinct nonempty IDs")
        return self


class QueryDependency(StrictModel):
    type: Literal["chunk", "evidence", "node", "note", "passage"]
    id: str = Field(min_length=1)
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    # An absent new guard must not change historical document request hashes.
    payload_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$", exclude_if=lambda value: value is None
    )
    revision: int | None = Field(default=None, ge=1)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=1)
    quote: str | None = None

    @model_validator(mode="after")
    def identity(self) -> "QueryDependency":
        if self.type == "node":
            if self.revision is None:
                raise ValueError("node dependency requires a revision")
        elif self.sha256 is None:
            raise ValueError("source dependency requires a hash")
        if self.type != "node" and self.payload_sha256 is not None:
            raise ValueError("payload hash is only valid for node references")
        if self.type == "chunk":
            if self.start is None or self.end is None or self.end <= self.start or not self.quote:
                raise ValueError("chunk dependency requires an exact nonempty interval")
        elif any(v is not None for v in (self.start, self.end, self.quote)):
            raise ValueError("interval fields are only valid for chunk references")
        return self


class DocumentPassageInput(StrictModel):
    local_ref: str = Field(min_length=1)
    text: str = Field(min_length=1)
    attribution: Literal["paper_author", "citation_report", "user_view", "model_synthesis"]
    dependencies: list[QueryDependency] = Field(min_length=1)
    caveats: list[str] = Field(default_factory=list)


class DocumentSaveRequest(StrictModel):
    project_id: str = Field(min_length=1)
    kind: Literal["wiki", "synthesis"] = "wiki"
    title: str = Field(min_length=1)
    document_id: str | None = None
    base_version_id: str | None = None
    passages: list[DocumentPassageInput] = Field(min_length=1)
    state: Literal["draft", "saved"] = "saved"

    @model_validator(mode="after")
    def unique_passages(self) -> "DocumentSaveRequest":
        if len({p.local_ref for p in self.passages}) != len(self.passages):
            raise ValueError("passage local_ref must be unique")
        if not self.title.strip() or any(not p.text.strip() for p in self.passages):
            raise ValueError("document title and passage text must not be blank")
        return self


class NoteGrantRequest(StrictModel):
    allow_local: bool = True
    allow_model: bool = False


class QueryPreparationView(StrictModel):
    query_id: str
    status: Literal["prepared", "insufficient", "failed"]
    input_hash: str
    snapshot: dict[str, Any]
    error: str | None = None
    presentation: dict[str, Any] = Field(default_factory=dict)


class GroundedQueryPassage(StrictModel):
    """Future P07 semantic output references only the current prepared manifest."""

    local_ref: str = Field(min_length=1)
    text: str = Field(min_length=1)
    attribution: Literal["paper_author", "citation_report", "user_view", "model_synthesis"]
    source_refs: list[str] = Field(min_length=1)
    caveats: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def distinct_references(self) -> "GroundedQueryPassage":
        if not self.text.strip() or len(self.source_refs) != len(set(self.source_refs)):
            raise ValueError("passage must have nonblank text and distinct manifest references")
        if any(not value.strip() for value in self.source_refs):
            raise ValueError("manifest references must be nonempty")
        return self


class QueryAnswer(StrictModel):
    """Program-bound answer identity; defining this DTO does not generate an answer."""

    answer_version_id: str = Field(min_length=1)
    query_run_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["validated", "incomplete", "invalid"]
    knowledge_status: Literal["source_grounded", "mixed_sources", "insufficient"]
    passages: list[GroundedQueryPassage] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_content(self) -> "QueryAnswer":
        if len({p.local_ref for p in self.passages}) != len(self.passages):
            raise ValueError("answer passage references must be unique")
        if not self.passages and self.knowledge_status != "insufficient":
            raise ValueError("an empty answer is insufficient")
        if self.knowledge_status == "insufficient" and not any(s.strip() for s in self.limitations):
            raise ValueError("insufficient answers must explain the missing support")
        if self.status != "validated" and self.knowledge_status != "insufficient":
            raise ValueError("unvalidated output cannot claim grounded knowledge")
        personal = any(p.attribution == "user_view" for p in self.passages)
        if self.knowledge_status == "source_grounded" and personal:
            raise ValueError("personal views must not become paper-grounded answers")
        if self.knowledge_status == "mixed_sources" and not personal:
            raise ValueError("mixed-source answers must retain personal attribution")
        return self


class QuerySaveCommand(StrictModel):
    """Explicit selected-passage save; the original question and evidence remain linked."""

    source_query_id: str = Field(min_length=1)
    answer_version_id: str = Field(min_length=1)
    selected_passage_refs: list[str] = Field(min_length=1)
    expected_input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    kind: Literal["synthesis", "insight"] = "synthesis"
    target_document_id: str | None = None
    base_version_id: str | None = None

    @model_validator(mode="after")
    def explicit_target(self) -> "QuerySaveCommand":
        if len(set(self.selected_passage_refs)) != len(self.selected_passage_refs) or any(
            not value.strip() for value in self.selected_passage_refs
        ):
            raise ValueError("saved passage references must be distinct and nonempty")
        if (self.target_document_id is None) != (self.base_version_id is None):
            raise ValueError("updating a document requires its explicit baseline version")
        if self.target_document_id == "" or self.base_version_id == "":
            raise ValueError("document target and baseline must be nonempty")
        return self


class SavedReadingAnnotation(StrictModel):
    annotation: str = Field(max_length=12000)
    expected_revision: int = Field(ge=0, strict=True)


class SavedReadingRemoval(StrictModel):
    expected_revision: int = Field(ge=0, strict=True)
