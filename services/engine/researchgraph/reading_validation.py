"""Lossless duplicate handling and quarantine of invalid navigation suggestions."""

import json
from typing import Any, Self

from pydantic import model_validator

from researchgraph.reading_contracts import (
    KnowledgeExtractionBatch,
    check_relation,
)


class _BatchFields(KnowledgeExtractionBatch):
    """Validate the complete envelope before checking cross-item references."""

    @model_validator(mode="after")
    def local_refs(self) -> Self:
        return self


def validate_batch(
    raw: str,
    allowed: set[str],
    *,
    removed_duplicates: list[dict[str, int]] | None = None,
    compact: bool = False,
    wire_changes: list[dict[str, str]] | None = None,
) -> tuple[KnowledgeExtractionBatch, list[dict[str, Any]]]:
    from researchgraph.unified_store import evidence_ids

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Reading batch must be an object")
    # A model-added envelope note is not a waiver of any evidence/Schema check.
    # Preserve it as untrusted metadata in warnings and keep raw_output unchanged.
    if "waiver" in data and isinstance(data["waiver"], str) and len(data["waiver"]) <= 4096:
        if isinstance(data.get("warnings", []), list):
            data = dict(data)
            note = data.pop("waiver")
            data["warnings"] = [*data.get("warnings", []), "模型附加说明（不参与校验）：" + note]
            if wire_changes is not None:
                wire_changes.append({"path": "waiver", "rule": "envelope-note-to-warning-v1"})
    if "items" not in data or "links" not in data:
        raise ValueError("Schema 校验失败：必须显式返回 items 和 links 数组")
    original = data
    if compact:
        from researchgraph.reading_wire import expand

        data = expand(data, wire_changes)
    # All fields, list limits and evidence are checked BEFORE removing anything.
    fields = _BatchFields.model_validate(data)
    if evidence_ids(data) - allowed:
        raise ValueError("Reading output referenced evidence outside the input whitelist")
    first: dict[str, tuple[int, str]] = {}
    kept_items, duplicates = [], []
    for index, (item, raw_item) in enumerate(
        zip(fields.items, original.get("items", []), strict=True)
    ):
        # Compare the original JSON, not coerced values or a semantic similarity score.
        encoded = json.dumps(raw_item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        previous = first.get(item.local_ref)
        if previous:
            prior_index, prior_encoded = previous
            if encoded != prior_encoded:
                raise ValueError(
                    f"Schema 校验失败：第 {prior_index + 1} 与第 {index + 1} 条候选使用了相同"
                    " local_ref，但内容不同；未合并或猜测关系，请查看模型运行记录"
                )
            duplicates.append({"kept_index": prior_index, "removed_index": index})
        else:
            first[item.local_ref] = (index, encoded)
            kept_items.append(data["items"][index])
    data = {**data, "items": kept_items}
    kinds = {i.local_ref: i.kind for i in fields.items}
    kept, quarantined = [], []
    for index, edge in enumerate(fields.links):
        source, target = kinds.get(edge.source_local_ref), kinds.get(edge.target_local_ref)
        try:
            if not source or not target:
                raise ValueError("unknown local reference")
            check_relation(source, target, edge.relation)
        except ValueError:
            quarantined.append(
                {
                    "index": index,
                    "source_kind": source,
                    "target_kind": target,
                    "relation": edge.relation,
                    "reason": "invalid_endpoint_types_or_reference",
                }
            )
        else:
            kept.append(data["links"][index])
    if quarantined:
        data = {
            **data,
            "links": kept,
            "warnings": [
                *data.get("warnings", []),
                f"{len(quarantined)} 条模型关联未通过端点规则，已隔离；候选和原始响应保留",
            ],
        }
    validated = KnowledgeExtractionBatch.model_validate(data)
    if removed_duplicates is not None:
        removed_duplicates.extend(duplicates)
    return validated, quarantined


def reusable_reading_output(raw: str, data: dict[str, Any], allowed: set[str]) -> bool:
    """Revalidate a saved failed response; Store still verifies source text at commit."""
    try:
        batch, _ = validate_batch(
            raw, allowed, compact=data.get("wire_format") == "reading-compact-1"
        )
        return (batch.document_version_id, batch.chunk_id) == (
            data.get("document_version_id"),
            data.get("chunk_id"),
        )
    except (ValueError, TypeError):
        return False


def validate_integration(raw: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    from researchgraph.reading_contracts import PaperIntegrationProposal

    data = json.loads(raw)
    audit: list[dict[str, str]] = []
    normalize_stage_notes(data, "warnings", ("limitations",), audit)
    if isinstance(data, dict) and isinstance(data.get("units"), list):
        for index, unit in enumerate(data["units"]):
            if not isinstance(unit, dict) or not isinstance(unit.get("member_ids"), list):
                continue
            root = unit.get("root_claim_id")
            if isinstance(root, str) and root in unit["member_ids"]:
                unit["member_ids"] = [nid for nid in unit["member_ids"] if nid != root]
                audit.append(
                    {"path": f"units.{index}.member_ids", "rule": "remove-root-self-membership-v1"}
                )
    # References, fields and duplicates remain strict after removing self membership.
    return PaperIntegrationProposal.model_validate(data).model_dump(mode="json"), audit


def normalize_stage_notes(
    data: Any, target: str, aliases: tuple[str, ...], audit: list[dict[str, str]]
) -> None:
    if not isinstance(data, dict) or not isinstance(data.get(target, []), list):
        return
    for alias in aliases:
        notes = data.get(alias)
        if isinstance(notes, list) and len(notes) <= 100 and all(isinstance(n, str) for n in notes):
            data[target] = [*data.get(target, []), *notes]
            del data[alias]
            audit.append({"path": alias, "rule": f"stage-notes-to-{target}-v1"})


def validate_selection(raw: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    from researchgraph.reading_contracts import CoreSelectionProposal

    data = json.loads(raw)
    audit: list[dict[str, str]] = []
    if isinstance(data, dict) and data.get("contract_version") in (
        "reading-selection-1.0",
        "paper-reading-v1",
    ):
        del data["contract_version"]
        audit.append({"path": "contract_version", "rule": "redundant-selection-version-v1"})
    normalize_stage_notes(data, "coverage_gaps", ("warnings", "limitations"), audit)
    return CoreSelectionProposal.model_validate(data).model_dump(mode="json"), audit


def isolate_integration_proposals(
    value: dict[str, Any], data: dict[str, Any]
) -> list[dict[str, Any]]:
    """Discard invalid organizational suggestions, never repair an ID or scientific content."""
    allowed = {n["id"] for n in data["candidates"]}
    roots = set(data["root_claim_ids"])
    evidence = {e["id"] for e in data["allowed_evidence"]}
    audit: list[dict[str, Any]] = []
    units = []
    for index, unit in enumerate(value["units"]):
        if unit["root_claim_id"] not in roots:
            audit.append({"path": f"units.{index}", "reason": "root_outside_window"})
            continue
        invalid = set(unit["member_ids"]) - allowed
        if invalid:
            audit.append(
                {
                    "path": f"units.{index}.member_ids",
                    "reason": "members_outside_window",
                    "count": len(invalid),
                }
            )
            unit["member_ids"] = [nid for nid in unit["member_ids"] if nid in allowed]
        units.append(unit)
    value["units"] = units
    for field in ("associations", "duplicates"):
        kept = []
        for index, proposal in enumerate(value[field]):
            ids = (
                {proposal["source_id"], proposal["target_id"]}
                if field == "associations"
                else set(proposal["candidate_ids"])
            )
            if ids - allowed or (
                field == "associations" and set(proposal["evidence_ids"]) - evidence
            ):
                audit.append({"path": f"{field}.{index}", "reason": "reference_outside_window"})
            else:
                kept.append(proposal)
        value[field] = kept
    if audit:
        value["warnings"].append(f"{len(audit)} 项整合建议引用窗口外内容，已隔离；未猜测或替换 ID")
    return audit
