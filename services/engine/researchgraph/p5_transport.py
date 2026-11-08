"""Strict P5 outputs, grounded with the same current evidence gates as Query."""

import copy
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from researchgraph.knowledge_store import KnowledgeError, digest
from researchgraph.p5_contracts import DeltaWire, SemanticLintWire, SynthesisWire, WikiPassageWire
from researchgraph.query_answer_wire import bind_answer
from researchgraph.query_documents import validate_dependencies
from researchgraph.query_save import _root_dependencies
from researchgraph.query_saved_lifecycle import reference_dependency
from researchgraph.reading_prompt_contract import assert_generated_rules, generated_rules
from researchgraph.reading_transport import loads

POLICY = "reading-workflows-1"
PROMPTS = {
    "lint_semantic": "P09_reading_lint_v1",
    "wiki_synthesis": "P10_reading_synthesis_v1",
    "wiki_delta": "P11_reading_delta_v1",
}
CONTRACTS: dict[str, type[BaseModel]] = {
    "lint_semantic": SemanticLintWire,
    "wiki_synthesis": SynthesisWire,
    "wiki_delta": DeltaWire,
}


def output_schema(
    kind: str, context: dict[str, Any] | None = None, targets: list[str] | None = None
) -> dict[str, Any]:
    schema = CONTRACTS[kind].model_json_schema()
    refs = [r["ref"] for r in context["references"]] if context else None
    for definition in schema.get("$defs", {}).values():
        properties = definition.get("properties", {})
        for name in ("source_refs", "affected_refs", "evidence_refs"):
            if name in properties and refs is not None:
                properties[name]["items"]["enum"] = refs
        for name in ("section_ref", "after_section_ref"):
            if name in properties and targets is not None:
                properties[name]["enum"] = targets
    return schema


def load_prompt(kind: str) -> str:
    prompt = (Path(__file__).parent / "prompts" / (PROMPTS[kind] + ".md")).read_text(
        encoding="utf-8"
    )
    assert_generated_rules(prompt, generated_rules(output_schema(kind), POLICY))
    return prompt


def _decode(kind: str, raw: str) -> Any:
    try:
        data = loads(raw)
    except (ValueError, TypeError):
        raise KnowledgeError("P5_JSON_INVALID", "模型返回的内容不是严格唯一键JSON") from None
    try:
        return CONTRACTS[kind].model_validate(data, strict=True)
    except ValidationError:
        raise KnowledgeError("P5_SCHEMA_INVALID", "模型输出未通过本阶段Schema校验") from None


def _passage(
    session: Session,
    project_id: str,
    wire: WikiPassageWire,
    context: dict[str, Any],
    workflow_id: str,
) -> dict[str, Any]:
    answer = bind_answer(
        json.dumps(
            {"passages": [wire.model_dump(exclude={"heading", "conditions"})], "limitations": []},
            ensure_ascii=False,
        ),
        context,
        query_id=workflow_id,
        answer_id="p5-validation",
        revision=1,
    )
    if answer.knowledge_status == "insufficient":
        raise KnowledgeError("P5_EVIDENCE_INSUFFICIENT", "整理段落缺少可验证的完整原文支撑")
    result = answer.passages[0]
    refs = {r["ref"]: r for r in context["references"]}
    bound = [reference_dependency(refs[r]) for r in result.source_refs]
    dependencies = _root_dependencies(session, [d for d in bound if d is not None])
    checked = validate_dependencies(
        session, project_id, dependencies, context["request"]["include_personal"], "model"
    )
    if checked["content_state"] != "valid":
        raise KnowledgeError("P5_DEPENDENCY_INVALID", "整理来源或用途权限已改变")
    if any(r.get("source_kind") == "external" for r in checked["roots"]):
        result.caveats.append("外部资料仅核验快照与授权，来源内容及科学语义未经证明。")
    # Condition values are model-authored semantics, with the same known-layout
    # guard as prose. Typed states and valid references do not prove scientific truth.
    if wire.conditions and "numeric_layout" in context:
        from researchgraph.query_answer_contracts import AnswerPassageWire
        from researchgraph.query_numeric_layout import validate_numeric_layout

        validate_numeric_layout(
            [
                AnswerPassageWire(
                    text=" ".join(str(v) for v in c.model_dump().values() if v is not None),
                    attribution=wire.attribution,
                    source_refs=wire.source_refs,
                    limitations=[],
                )
                for c in wire.conditions
            ],
            context["numeric_layout"],
        )
    return {
        "heading": wire.heading,
        "text": result.text,
        "attribution": result.attribution,
        "dependencies": dependencies,
        "caveats": result.caveats,
        "conditions": [c.model_dump() for c in wire.conditions],
        "links": [],
    }


def validate_output(session: Session, workflow: Any, run_id: str, raw: str) -> dict[str, Any]:
    decoded = _decode(workflow.kind, raw)
    context = workflow.snapshot["context"]
    provenance = {
        "workflow_id": workflow.id,
        "model_run_id": run_id,
        "input_hash": workflow.input_hash,
        "kind": PROMPTS[workflow.kind],
        "source_revisions": workflow.snapshot["source_revisions"],
    }
    if isinstance(decoded, SynthesisWire):
        if not decoded.passages:
            raise KnowledgeError(
                "P5_EVIDENCE_INSUFFICIENT", "模型未生成有据段落；缺口已保留原始记录"
            )
        passages = [
            _passage(session, workflow.project_id, p, context, workflow.id)
            for p in decoded.passages
        ]
        return {
            "draft": {"title": decoded.title, "passages": passages, "provenance": provenance},
            "coverage_gaps": decoded.coverage_gaps,
            "model_run_id": run_id,
        }
    if isinstance(decoded, DeltaWire):
        targets = workflow.snapshot["targets"]
        used: set[str] = set()
        operations = []
        for edit in decoded.edits:
            ref = edit.after_section_ref if edit.op == "append" else edit.section_ref
            if ref not in targets or (edit.op != "append" and ref in used):
                raise KnowledgeError("P5_DELTA_SCOPE_INVALID", "更新引用了范围外或冲突的段落编号")
            if edit.op != "append":
                used.add(ref)
            if edit.op == "mark_stale":
                operations.append(
                    {"op": edit.op, "section_id": targets[ref], "reason": edit.reason}
                )
            else:
                operations.append(
                    {
                        "op": edit.op,
                        "after_section_id" if edit.op == "append" else "section_id": targets[ref],
                        "passage": _passage(
                            session, workflow.project_id, edit.passage, context, workflow.id
                        ),
                    }
                )
        base = workflow.snapshot["base"]
        return {
            "patch": {
                "base_version_id": base["version_id"],
                "base_content_hash": base["content_hash"],
                "operations": operations,
            },
            "coverage_gaps": decoded.coverage_gaps,
            "model_run_id": run_id,
            "provenance": provenance,
        }
    refs = {r["ref"]: r for r in context["references"]}
    suggestions = []
    for issue in decoded.issues:
        if (set(issue.affected_refs) | set(issue.evidence_refs)) - refs.keys():
            raise KnowledgeError("P5_REFERENCE_UNKNOWN", "诊断引用了本次清单之外的对象")
        if len(set(issue.affected_refs)) != len(issue.affected_refs) or len(
            set(issue.evidence_refs)
        ) != len(issue.evidence_refs):
            raise KnowledgeError("P5_REFERENCE_DUPLICATE", "诊断引用编号重复")
        # Evidence must reach a verified root, never just a title or neighbouring node.
        roots = [reference_dependency(refs[r]) for r in issue.evidence_refs]
        checked = validate_dependencies(
            session,
            workflow.project_id,
            [d for d in roots if d is not None],
            context["request"]["include_personal"],
            "model",
        )
        if checked["content_state"] != "valid" or not checked["roots"]:
            raise KnowledgeError("P5_GROUNDING_INVALID", "语义建议缺少有效原文或授权笔记依据")
        value = issue.model_dump(exclude={"affected_refs", "evidence_refs"})
        value.update(
            {
                "affected_ids": [refs[r]["id"] for r in issue.affected_refs],
                "evidence_ids": [refs[r]["id"] for r in issue.evidence_refs],
                "evidence_dependencies": [
                    reference_dependency(refs[r]) for r in issue.evidence_refs
                ],
                "kind": "model_suggestion",
                "model_run_id": run_id,
                "fingerprint": digest(issue.model_dump()),
            }
        )
        suggestions.append(value)
    return {"suggestions": suggestions, "limitations": decoded.limitations, "model_run_id": run_id}


def make_wire(
    kind: str,
    context: dict[str, Any],
    base: dict[str, Any] | None,
    targets: dict[str, str],
    lint: dict[str, Any] | None,
) -> dict[str, Any]:
    result = {
        "evidence_context": copy.deepcopy(context),
        "contract_rules": generated_rules(output_schema(kind, context, list(targets)), POLICY),
    }
    if base:
        result["affected_sections"] = base["model_sections"]
    if lint:
        result["deterministic_diagnostics"] = lint
    return result
