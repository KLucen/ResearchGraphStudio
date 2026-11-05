"""Strict P07 decoding and evidence/attribution binding, independent of storage."""

import copy
from typing import Any

from pydantic import ValidationError

from researchgraph.knowledge_store import KnowledgeError, digest, text_hash
from researchgraph.query_answer_contracts import AnswerWire
from researchgraph.query_contracts import QueryAnswer
from researchgraph.reading_prompt_contract import assert_generated_rules
from researchgraph.reading_prompt_contract import generated_rules as schema_rules
from researchgraph.reading_transport import loads

PROMPT = "P07_query_grounded_v1"
LAYOUT_PROMPT = "P07_query_grounded_v2"
POLICY = "query-grounded-semantic-1"


def output_schema(refs: list[str] | None = None) -> dict[str, Any]:
    schema = AnswerWire.model_json_schema()
    if refs is not None:
        schema["$defs"]["AnswerPassageWire"]["properties"]["source_refs"]["items"]["enum"] = refs
    return schema


def generated_rules(refs: list[str] | None = None) -> str:
    return schema_rules(output_schema(refs), POLICY)


def assert_prompt_contract(prompt: str) -> None:
    assert_generated_rules(prompt, generated_rules())


def decode(raw: str) -> AnswerWire:
    try:
        value = loads(raw)
    except (ValueError, TypeError):
        raise KnowledgeError("QUERY_JSON_INVALID", "回答不是唯一键的严格 JSON 对象") from None
    try:
        return AnswerWire.model_validate(value, strict=True)
    except ValidationError:
        raise KnowledgeError("QUERY_SCHEMA_INVALID", "回答字段或类型未通过输出契约校验") from None


def _root_kinds(ref: dict[str, Any], references: dict[str, dict[str, Any]]) -> set[str]:
    kind = ref["type"]
    if kind in {"chunk", "evidence"}:
        return {"paper"} if ref.get("paper_id") and ref.get("document_version_id") else set()
    if kind == "note":
        return {"note"}
    if kind == "node":
        roots: set[str] = set()
        for eid in ref.get("evidence_ids", []):
            for evidence in references.values():
                if evidence["type"] == "evidence" and evidence["id"] == eid:
                    roots.update(_root_kinds(evidence, references))
        return roots
    if kind == "passage":
        return {
            "note" if root.get("source_kind") == "note" or root.get("type") == "note" else "paper"
            for root in ref.get("roots", [])
            if root.get("source_kind") in {"note", "paper"}
            or root.get("type") in {"note", "chunk", "evidence"}
        }
    return set()  # Paper title/metadata alone never grounds a scientific paragraph.


def validate_semantics(wire: AnswerWire, context: dict[str, Any]) -> None:
    if "numeric_layout" in context:
        from researchgraph.query_numeric_layout import validate_numeric_layout

        validate_numeric_layout(wire.passages, context["numeric_layout"], include_cautions=False)
    refs = {ref["ref"]: ref for ref in context["references"]}
    for passage in wire.passages:
        if set(passage.source_refs) - refs.keys():
            raise KnowledgeError("QUERY_REFERENCE_UNKNOWN", "回答引用了本次清单以外的来源编号")
        selected = [refs[ref] for ref in passage.source_refs]
        roots = set().union(*(_root_kinds(ref, refs) for ref in selected))
        if passage.attribution == "user_view":
            if "note" not in roots:
                raise KnowledgeError("QUERY_ATTRIBUTION_INVALID", "个人观点缺少授权笔记根来源")
        elif "paper" not in roots:
            raise KnowledgeError("QUERY_GROUNDING_INVALID", "科学段落缺少原始论文证据")
        elif "note" in roots:
            raise KnowledgeError(
                "QUERY_ATTRIBUTION_INVALID", "个人观点与科学段落必须分段并保留各自归属"
            )
        if passage.attribution in {"paper_author", "citation_report"}:
            # Multiple papers or previously generated synthesis cannot silently
            # become a single author's statement. Raw text attribution remains
            # a model judgment and is explicitly not scientific truth validation.
            papers = {ref.get("paper_id") for ref in selected if ref.get("paper_id")}
            papers.update(
                root["paper_id"]
                for ref in selected
                for root in ref.get("roots", [])
                if root.get("paper_id")
            )
            if len(papers) > 1 or any(
                ref["type"] == "passage" and ref.get("attribution") == "model_synthesis"
                for ref in selected
            ):
                raise KnowledgeError(
                    "QUERY_ATTRIBUTION_INVALID", "跨文献或 AI 综合必须保留综合归属"
                )
            for ref in selected:
                if ref["type"] == "node":
                    cited = ref.get("authorship") in {"cited_author", "cited_other"} or ref.get(
                        "origin"
                    ) in {"cited_claim", "cited_work"}
                    if cited and passage.attribution != "citation_report":
                        raise KnowledgeError(
                            "QUERY_ATTRIBUTION_INVALID", "他人观点转述不能归为本论文作者主张"
                        )
                    if (
                        passage.attribution == "paper_author"
                        and ref.get("authorship") != "paper_author"
                    ):
                        raise KnowledgeError(
                            "QUERY_ATTRIBUTION_INVALID", "未知作者归属不能提升为论文作者主张"
                        )


def _normalize_cautions(
    wire: AnswerWire, context: dict[str, Any]
) -> tuple[AnswerWire, list[dict[str, Any]]]:
    """Replace only numeric spans in dedicated cautions; never alter answer prose."""
    if "numeric_layout" not in context:
        return wire, []
    from researchgraph.query_numeric_layout import DISPLAY_NOTICE, normalize_caution

    wire = wire.model_copy(deep=True)
    fields = []
    for index, passage in enumerate(wire.passages):
        affected = False
        for number, value in enumerate(passage.limitations):
            normalized, matches = normalize_caution(value, context["numeric_layout"])
            if matches:
                passage.limitations[number] = normalized
                fields.append({"path": f"passages.{index}.limitations.{number}", "spans": matches})
                affected = True
        if affected and DISPLAY_NOTICE not in passage.limitations:
            passage.limitations.append(DISPLAY_NOTICE)
    for index, value in enumerate(wire.limitations):
        normalized, matches = normalize_caution(value, context["numeric_layout"])
        if matches:
            wire.limitations[index] = normalized
            fields.append({"path": f"limitations.{index}", "spans": matches})
    if fields and DISPLAY_NOTICE not in wire.limitations:
        wire.limitations.append(DISPLAY_NOTICE)
    return wire, fields


def display_normalization(
    raw: str | None, context: dict[str, Any], bound: QueryAnswer
) -> dict[str, Any] | None:
    """Deterministic audit, regenerated at publish/GET/cache/save boundaries."""
    if raw is None:
        return None
    _, fields = _normalize_cautions(decode(raw), context)
    if not fields:
        return None
    from researchgraph.query_numeric_layout import DISPLAY_RULE

    return {
        "rule": DISPLAY_RULE,
        "raw_sha256": text_hash(raw),
        "offset_unit": "unicode-codepoint-zero-based-half-open",
        "fields": fields,
        "replacement_count": sum(len(field["spans"]) for field in fields),
        "bound_sha256": digest(bound.model_dump(mode="json")),
    }


def bind_answer(
    raw: str | None,
    context: dict[str, Any],
    *,
    query_id: str,
    answer_id: str,
    revision: int,
    deterministic_limitations: list[str] | None = None,
) -> QueryAnswer:
    wire = (
        decode(raw)
        if raw is not None
        else AnswerWire(
            passages=[], limitations=deterministic_limitations or ["没有可用于回答的原始证据"]
        )
    )
    validate_semantics(wire, context)
    wire, _ = _normalize_cautions(wire, context)
    limitations = list(dict.fromkeys([*wire.limitations, *context.get("coverage_gaps", [])]))
    if wire.passages and any(
        ref.get("current_file_status") == "not_checked" for ref in context["references"]
    ):
        limitations.append("当前 PDF 文件未重新核验；引用依据为已保存的不可变证据")
    if not context.get("capacity", {}).get("sufficient", True):
        limitations.append("完整证据上下文超过当前已知模型容量；未截断必要证据")
    if not wire.passages or context["status"] != "ready":
        knowledge_status = "insufficient"
        if not limitations:
            limitations.append("当前检索范围没有足够证据，未生成科学结论")
    else:
        knowledge_status = (
            "mixed_sources"
            if any(p.attribution == "user_view" for p in wire.passages)
            else "source_grounded"
        )
    return QueryAnswer.model_validate(
        {
            "answer_version_id": answer_id,
            "query_run_id": query_id,
            "revision": revision,
            "input_hash": context["input_hash"],
            "status": "validated",
            "knowledge_status": knowledge_status,
            "passages": [
                {
                    "local_ref": f"A{index:05d}",
                    "text": passage.text,
                    "attribution": passage.attribution,
                    "source_refs": passage.source_refs,
                    "caveats": list(
                        dict.fromkeys(
                            [
                                *passage.limitations,
                                "引用身份和证据锚点已核验；不等于科学事实认证",
                            ]
                        )
                    ),
                }
                for index, passage in enumerate(wire.passages, 1)
            ],
            "limitations": limitations,
        }
    )


def model_input(context: dict[str, Any]) -> dict[str, Any]:
    """Keep complete groups and full provenance; only declared short refs are legal output."""
    return {
        "question": context["request"]["question"],
        "evidence_context": copy.deepcopy(context),
        "contract_rules": generated_rules([ref["ref"] for ref in context["references"]]),
        "input_context_hash": digest(context),
    }
