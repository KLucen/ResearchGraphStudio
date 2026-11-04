"""Keyed ranking transport; the program, rather than a model list, owns identity.

Only this versioned transport supports private, per-claim recovery. A valid slot
is not a publishable response: aggregate binding still requires every frozen
claim and subsequent domain/source/support validation.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, TypeAdapter, ValidationError, create_model

from researchgraph.reading_contracts import CoreSelectionProposal, SelectionHint, StrictModel
from researchgraph.reading_prompt_contract import assert_generated_rules
from researchgraph.reading_prompt_contract import generated_rules as schema_rules
from researchgraph.reading_transport import loads

PROMPT = "P13_reading_ranking_v3"
POLICY = "reading-ranking-keyed-1"
_TEMPLATE_REFS = ("c0001",)
_ALIAS = re.compile(r"c[0-9]{4,}\Z")


def _assessment_model() -> Any:
    # Exact disposition/reasons/rationale constraints come from the domain DTO,
    # so adding a legal domain reason cannot silently diverge from this wire.
    fields: dict[str, Any] = {
        name: (field.annotation, copy.deepcopy(field))
        for name, field in SelectionHint.model_fields.items()
        if name != "root_claim_id"
    }
    fields["priority"] = (Annotated[int, Field(strict=True, ge=0, le=100)], ...)
    return create_model("ContributionAssessment", __base__=StrictModel, **fields)


ContributionAssessment = _assessment_model()
_WARNINGS = TypeAdapter(list[str])


class RankingWireError(ValueError):
    """Fixed safe envelope errors; no untrusted field names or text are echoed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RankingValidation:
    assessments: dict[str, dict[str, Any]]
    errors: dict[str, list[dict[str, str]]]
    warnings: list[str]

    @property
    def complete(self) -> bool:
        return not self.errors


def _refs(claim_refs: Iterable[str] | None) -> list[str]:
    refs = list(_TEMPLATE_REFS if claim_refs is None else claim_refs)
    if (
        not refs
        or any(not isinstance(ref, str) or _ALIAS.fullmatch(ref) is None for ref in refs)
        or len(refs) != len(set(refs))
    ):
        raise RankingWireError("RANKING_CONTEXT_INVALID", "排序短编号上下文无效")
    return refs


def output_schema(claim_refs: Iterable[str] | None = None) -> dict[str, Any]:
    """Freeze the entire expected identity set in ordinary object properties.

    This works with native strict output as well as the separately tested JSON
    compatibility path. No uniqueness or exact-coverage constraint is left as
    an invisible Python-only instruction to the model.
    """
    refs = _refs(claim_refs)
    assessment = ContributionAssessment.model_json_schema()
    definitions = assessment.pop("$defs", {})
    definitions["ContributionAssessment"] = assessment
    return {
        "title": "KeyedContributionRanking",
        "type": "object",
        "properties": {
            "assessments": {
                "type": "object",
                "properties": {ref: {"$ref": "#/$defs/ContributionAssessment"} for ref in refs},
                "required": refs,
                "additionalProperties": False,
            },
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["assessments", "warnings"],
        "additionalProperties": False,
        "$defs": definitions,
    }


def generated_rules(claim_refs: Iterable[str] | None = None) -> str:
    return schema_rules(output_schema(claim_refs), POLICY)


def assert_prompt_contract(prompt: str | None = None) -> None:
    """Check static domain rules; each request supplies its exact keyed rules."""
    if prompt is None:
        prompt = (Path(__file__).parent / "prompts" / (PROMPT + ".md")).read_text(encoding="utf-8")
    assert_generated_rules(prompt, generated_rules())


def _diagnostics(error: ValidationError) -> list[dict[str, str]]:
    allowed = set(ContributionAssessment.model_fields)
    result = []
    for issue in error.errors(include_input=False, include_context=False, include_url=False)[:4]:
        path = []
        for token in issue["loc"][:3]:
            if type(token) is int and 0 <= token <= 999_999:
                path.append(str(token))
            elif isinstance(token, str) and token in allowed:
                path.append(token)
            else:
                path.append("<unknown>")
                break
        # The type comes from Pydantic's registered built-in validators; there
        # are no user/model supplied messages, inputs, contexts or key names.
        result.append({"path": ".".join(path) or "$", "type": issue["type"]})
    return result


def split_validate(raw: str, claim_refs: Iterable[str]) -> RankingValidation:
    """Validate an envelope before retaining any known independently valid slot.

    Unknown keys, unknown identities, duplicate JSON keys and invalid warning
    types reject the whole envelope. Missing/invalid known slots are private
    repair work, never defaults, accepted recommendations or a completed stage.
    """
    refs = _refs(claim_refs)
    try:
        value = loads(raw)
    except (ValueError, TypeError) as error:
        code = (
            "RANKING_DUPLICATE_KEY"
            if "Duplicate JSON key" in str(error)
            else "RANKING_INVALID_JSON"
        )
        raise RankingWireError(code, "排序响应不是唯一键的严格 JSON 对象") from error
    if set(value) != {"assessments", "warnings"} or not isinstance(value.get("assessments"), dict):
        raise RankingWireError("RANKING_ENVELOPE_INVALID", "排序响应的根字段或类型不符合契约")
    try:
        warnings = _WARNINGS.validate_python(value["warnings"], strict=True)
    except ValidationError as error:
        raise RankingWireError(
            "RANKING_ENVELOPE_INVALID", "排序响应的 warnings 必须为字符串数组"
        ) from error
    slots = value["assessments"]
    if set(slots) - set(refs):
        raise RankingWireError("RANKING_ALIAS_UNKNOWN", "排序响应含输入之外的短编号")
    good, errors = {}, {}
    for ref in refs:
        if ref not in slots:
            errors[ref] = [{"path": "$", "type": "missing"}]
            continue
        try:
            good[ref] = ContributionAssessment.model_validate(slots[ref], strict=True).model_dump(
                mode="json"
            )
        except ValidationError as error:
            errors[ref] = _diagnostics(error)
    return RankingValidation(good, errors, warnings)


def bind_ranking(
    assessments: dict[str, dict[str, Any]],
    context: dict[str, Any],
    *,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Revalidate all slots, bind immutable identity, and order ties in input order."""
    aliases = context["claim_aliases"]
    refs = _refs(aliases)
    if set(assessments) != set(refs):
        raise RankingWireError("RANKING_INCOMPLETE", "排序尚未完整覆盖全部输入结论")
    # This also revalidates private checkpoints without trusting their status.
    checked = split_validate(
        json.dumps(
            {"assessments": assessments, "warnings": warnings if warnings is not None else []},
            ensure_ascii=False,
        ),
        refs,
    )
    if not checked.complete:
        raise RankingWireError("RANKING_INVALID_ASSESSMENT", "排序结论仍有未修复字段")
    order = sorted(refs, key=lambda ref: -checked.assessments[ref]["priority"])
    return CoreSelectionProposal(
        document_version_id=context["document_version_id"],
        input_revision=context["input_revision"],
        recommendations=[
            SelectionHint(
                root_claim_id=aliases[ref],
                **{k: v for k, v in checked.assessments[ref].items() if k != "priority"},
            )
            for ref in order
        ],
        coverage_gaps=list(dict.fromkeys([*context["coverage_gaps"], *checked.warnings])),
    ).model_dump(mode="json")
