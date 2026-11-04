"""Semantic-only finish DTOs: trusted identity and graph membership stay in code."""

from pathlib import Path
from typing import Any

from pydantic import Field, model_validator

from researchgraph.reading_contracts import (
    Association,
    CoreSelectionProposal,
    Ref,
    SelectionHint,
    StrictModel,
    unique,
)
from researchgraph.reading_prompt_contract import assert_generated_rules
from researchgraph.reading_prompt_contract import generated_rules as schema_rules

POLICY = "semantic-reading-1"
INTEGRATION_PROMPT = "P12_reading_associations_v1"
LEGACY_RANKING_PROMPT = "P13_reading_ranking_v1"
RANKING_PROMPT = "P13_reading_ranking_v2"


class SemanticAssociation(StrictModel):
    source_ref: Ref
    target_ref: Ref
    relation: Association
    evidence_refs: list[Ref] = Field(min_length=1)
    rationale: str = Field(min_length=1)


class SemanticDuplicate(StrictModel):
    candidate_refs: list[Ref] = Field(min_length=2)
    representative_ref: Ref
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def distinct_candidates(self) -> "SemanticDuplicate":
        unique(self.candidate_refs)
        if self.representative_ref not in self.candidate_refs:
            raise ValueError("duplicate representative is outside its group")
        return self


class SemanticIntegration(StrictModel):
    associations: list[SemanticAssociation]
    duplicates: list[SemanticDuplicate]
    warnings: list[str]


class ContributionHint(SelectionHint):
    # Reuse the domain's exact reasons, disposition and text validation. Only the
    # transport name changes; it is a request-local alias, never a database ID.
    root_claim_id: Ref = Field(alias="claim_ref")


class ContributionRanking(StrictModel):
    ranked_claims: list[ContributionHint]
    warnings: list[str]

    @model_validator(mode="after")
    def distinct_claims(self) -> "ContributionRanking":
        unique([h.root_claim_id for h in self.ranked_claims])
        return self


def schema_for(stage: str) -> dict[str, Any]:
    return (SemanticIntegration if stage == "P12" else ContributionRanking).model_json_schema(
        by_alias=True
    )


def generated_rules(stage: str) -> str:
    if stage not in {"P12", "P13"}:
        raise ValueError("未知语义阶段")
    return schema_rules(schema_for(stage), POLICY + "/" + stage)


def assert_prompt_contract(stage: str, prompt: str | None = None) -> None:
    expected = generated_rules(stage)
    if prompt is None:
        name = INTEGRATION_PROMPT if stage == "P12" else RANKING_PROMPT
        prompt = (Path(__file__).parent / "prompts" / (name + ".md")).read_text(encoding="utf-8")
    assert_generated_rules(prompt, expected)


def _ref(value: str, aliases: dict[str, str], *, evidence: bool = False) -> str:
    if value not in aliases:
        from researchgraph.reading_stage_validation import StageValidationError

        raise StageValidationError(
            "evidence" if evidence else "context",
            "EVIDENCE_NOT_ALLOWED" if evidence else "CANDIDATE_NOT_ALLOWED",
            "模型引用了当前输入之外的短编号；未猜测或替换",
        )
    return aliases[value]


def bind_integration(value: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    proposal = SemanticIntegration.model_validate(value)
    candidates, evidence = context["candidate_aliases"], context["evidence_aliases"]
    return {
        "contract_version": "reading-integration-1.0",
        "document_version_id": context["document_version_id"],
        "input_revision": context["input_revision"],
        "units": [],
        "associations": [
            {
                "source_id": _ref(a.source_ref, candidates),
                "target_id": _ref(a.target_ref, candidates),
                "relation": a.relation,
                "evidence_ids": [_ref(e, evidence, evidence=True) for e in a.evidence_refs],
                "rationale": a.rationale,
            }
            for a in proposal.associations
        ],
        "duplicates": [
            {
                "candidate_ids": [_ref(r, candidates) for r in d.candidate_refs],
                "representative_id": _ref(d.representative_ref, candidates),
                "rationale": d.rationale,
            }
            for d in proposal.duplicates
        ],
        "warnings": proposal.warnings,
    }


def bind_ranking(value: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    ranking = ContributionRanking.model_validate(value)
    aliases = context["claim_aliases"]
    if {h.root_claim_id for h in ranking.ranked_claims} != set(aliases):
        from researchgraph.reading_stage_validation import StageValidationError

        raise StageValidationError(
            "context", "RESPONSE_ROOTS_MISMATCH", "核心排序没有完整且唯一地覆盖输入结论"
        )
    return CoreSelectionProposal(
        document_version_id=context["document_version_id"],
        input_revision=context["input_revision"],
        recommendations=[
            SelectionHint(**{**h.model_dump(), "root_claim_id": _ref(h.root_claim_id, aliases)})
            for h in ranking.ranked_claims
        ],
        coverage_gaps=list(dict.fromkeys([*context["coverage_gaps"], *ranking.warnings])),
    ).model_dump(mode="json")
