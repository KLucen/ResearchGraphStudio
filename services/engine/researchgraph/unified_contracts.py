"""v3 section DTO adapter: complete domain details survive the lightweight view."""

from typing import Literal

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from researchgraph.knowledge_contracts import StrictModel


class UnifiedCondition(StrictModel):
    dimension: str = Field(min_length=1, max_length=100)
    state: Literal["known", "unknown", "not_applicable", "conflicting"]
    value_en: str | None = None
    value_zh: str | None = None
    unit: str | None = None
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def consistent(self) -> "UnifiedCondition":
        if self.state == "known" and (not self.value_en or not self.evidence_ids):
            raise ValueError("Known conditions require original value and evidence")
        if self.state in {"unknown", "not_applicable"} and (
            self.value_en is not None or self.value_zh is not None
        ):
            raise ValueError("Unknown conditions cannot assert values")
        return self


class UnifiedFinding(StrictModel):
    finding_en: str = Field(min_length=1)
    finding_zh: str = ""
    metric_en: str | None = None
    metric_zh: str | None = None
    reported_value: str | None = None
    baseline: str | None = None
    unit: str | None = None
    evidence_ids: list[str] = Field(min_length=1, max_length=100)


class UnifiedExperiment(StrictModel):
    label: str = Field(min_length=1)
    task: str | None = None
    protocol: str | None = None
    conditions: list[UnifiedCondition] = Field(default_factory=list, max_length=40)
    findings: list[UnifiedFinding] = Field(default_factory=list, max_length=40)
    evidence_ids: list[str] = Field(min_length=1, max_length=100)


class UnifiedClaim(StrictModel):
    statement_en: str = Field(min_length=10)
    statement_zh: str = ""
    modality: Literal["asserted", "conditional", "suggested", "speculative", "negated", "unknown"]
    scope_en: str | None = None
    scope_zh: str | None = None
    conditions: list[UnifiedCondition] = Field(default_factory=list, max_length=40)
    findings: list[UnifiedFinding] = Field(default_factory=list, max_length=40)
    experiments: list[UnifiedExperiment] = Field(default_factory=list, max_length=20)


class UnifiedMethod(StrictModel):
    mechanism_en: str | None = None
    mechanism_zh: str | None = None
    experiments: list[UnifiedExperiment] = Field(default_factory=list, max_length=20)


class UnifiedItem(StrictModel):
    local_ref: str = Field(min_length=1, max_length=80)
    kind: Literal["Concept", "Method", "Claim", "ResearchQuestion"]
    label_en: str = Field(min_length=1, max_length=200)
    label_zh: str = Field(default="", max_length=100)
    summary_en: str = Field(min_length=1, max_length=12000)
    summary_zh: str = Field(default="", max_length=12000)
    evidence_ids: list[str] = Field(min_length=1, max_length=100)
    origin: Literal["paper_author", "citation_report"]
    claim_detail: UnifiedClaim | None = None
    method_detail: UnifiedMethod | None = None

    @model_validator(mode="after")
    def details_match(self) -> "UnifiedItem":
        if (self.kind == "Claim") != (self.claim_detail is not None):
            raise ValueError("Claim needs claim_detail; other kinds cannot carry it")
        if self.kind != "Method" and self.method_detail is not None:
            raise ValueError("Only Method may contain method_detail")
        return self


class UnifiedLink(StrictModel):
    source_local_ref: str
    target_local_ref: str
    relation: Literal[
        "ABOUT",
        "USES_METHOD",
        "INVOLVES_CONCEPT",
        "STUDIES",
        "RELATED_TO",
        "QUESTIONS",
        "HAS_METHOD",
    ]
    evidence_ids: list[str] = Field(min_length=1, max_length=100)


class KnowledgeExtractionBatch(StrictModel):
    document_version_id: str
    chunk_id: str
    items: list[UnifiedItem] = Field(default_factory=list, max_length=80)
    links: list[UnifiedLink] = Field(default_factory=list, max_length=200)
    warnings: list[str] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def links_resolve(self) -> "KnowledgeExtractionBatch":
        refs = {item.local_ref: item for item in self.items}
        if len(refs) != len(self.items):
            raise ValueError("Duplicate local ref")
        for index, link in enumerate(self.links):
            for field in ("source_local_ref", "target_local_ref"):
                if getattr(link, field) not in refs:
                    raise PydanticCustomError(
                        "local_ref_missing",
                        "links[{index}].{field} references missing local_ref: {ref}",
                        {"index": index, "field": field, "ref": getattr(link, field)[:80]},
                    )
            if link.source_local_ref == link.target_local_ref:
                raise ValueError("Self link is not supported")
            if (
                link.relation in {"USES_METHOD", "HAS_METHOD"}
                and refs[link.target_local_ref].kind != "Method"
            ):
                raise ValueError("Method link requires Method target")
        return self


class TranslationItem(StrictModel):
    node_ref: str
    label_zh: str = Field(min_length=1, max_length=100)
    summary_zh: str = Field(min_length=1, max_length=12000)


class TranslationRepair(StrictModel):
    items: list[TranslationItem] = Field(min_length=1, max_length=30)
