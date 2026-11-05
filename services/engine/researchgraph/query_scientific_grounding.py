"""Versioned, program-derived citation groups and conservative scientific roles.

These groups certify existing provenance and parser structure, never scientific
entailment. They do not infer table columns, formulae, terminology or new facts.
"""

from typing import Any

from sqlalchemy.orm import Session

from researchgraph.document_structure import current_structure
from researchgraph.knowledge_models import KnowledgeNode
from researchgraph.knowledge_store import KnowledgeError, digest

POLICY = "query-scientific-grounding-1"
BINDING_POLICY = "query-scientific-binding-1"
BACKGROUND_NOTICE = "引用含背景定义；背景介绍不等于本论文新贡献，不能据此认定新的科学结论。"
EXPANSION_NOTICE = "程序已补齐所引知识的原文根及已检测表格组；引用完整不等于科学语义已获证明。"


def _invalid() -> KnowledgeError:
    return KnowledgeError("QUERY_SCIENTIFIC_GUIDANCE_INVALID", "科学来源分组与当前证据清单不一致")


def freeze_guidance(session: Session, context: dict[str, Any]) -> dict[str, Any]:
    """Freeze only roles and source groups that are already validated in context."""
    refs = context["references"]
    by_object = {(r["type"], r["id"]): r["ref"] for r in refs}
    nodes = {n["id"]: n for n in context["graph"]["nodes"]}
    root_links, roles = [], []
    for ref in refs:
        direct = set()
        if ref["type"] == "node":
            node = nodes.get(ref["id"])
            if node is None:
                # A document can supply a validated node root independently of
                # the graph projection. Match its frozen identity, not presence
                # on a particular graph path, before reading its stored roles.
                stored = session.get(KnowledgeNode, ref["id"])
                if (
                    stored is None
                    or stored.revision != ref["revision"]
                    or stored.paper_id != ref["paper_id"]
                    or stored.document_version_id != ref["document_version_id"]
                    or digest(stored.payload) != ref["payload_hash"]
                    or stored.authorship != ref["authorship"]
                    or stored.origin != ref["origin"]
                ):
                    raise _invalid()
                node = {
                    "kind": stored.kind,
                    "payload": stored.payload,
                    "authorship": stored.authorship,
                    "origin": stored.origin,
                }
            payload = node["payload"]
            roles.append(
                {
                    "ref": ref["ref"],
                    "kind": node["kind"],
                    "authorship": node["authorship"],
                    "origin": node["origin"],
                    "contribution_type": payload.get("contribution_type"),
                    "modality": payload.get("modality"),
                    "legacy_claim_type": payload.get("claim_type"),
                    "legacy_claim_origin": payload.get("origin"),
                }
            )
            for eid in ref["evidence_ids"]:
                target = by_object.get(("evidence", eid))
                if target is None:
                    raise _invalid()
                direct.add(target)
        elif ref["type"] == "evidence":
            target = by_object.get(("chunk", ref["paragraph_id"]))
            if target is None:
                raise _invalid()
            direct.add(target)
        elif ref["type"] == "passage":
            for root in ref.get("roots", []):
                key = (root.get("type"), root.get("id"))
                target = by_object.get(key)
                if target:
                    direct.add(target)
        if direct:
            root_links.append({"ref": ref["ref"], "source_refs": sorted(direct)})

    artifacts = {}
    tables = []
    for supplied in context["tables"]:
        vid = supplied["document_version_id"]
        if vid not in artifacts:
            artifacts[vid] = current_structure(session, vid)
        artifact = artifacts[vid]
        table = supplied["data"]
        if artifact is None or artifact.id != supplied["parse_id"]:
            raise _invalid()
        blocks = {b["ref"]: b["chunk_id"] for b in artifact.data["blocks"]}
        members = set()
        for block_ref in table["block_refs"]:
            target = by_object.get(("chunk", blocks.get(block_ref)))
            if target is None:
                raise _invalid()
            members.add(target)
        tables.append(
            {
                "document_version_id": vid,
                "parse_id": artifact.id,
                "table_ref": table["ref"],
                "structure_sha256": digest(table),
                "status": table["structure_status"],
                "header_names": table.get("header", {}).get("names", []),
                "source_refs": sorted(members),
                "meaning": "detected_parser_structure_not_scientific_truth",
            }
        )
    return {
        "policy": POLICY,
        "source_roles": roles,
        "root_links": root_links,
        "table_groups": tables,
        "undetected_tables": "unknown_not_reconstructed_from_plain_text_spacing",
        "formula_meaning": "not_proved_by_source_identity_or_typography",
    }


def citation_closure(source_refs: list[str], context: dict[str, Any]) -> list[str]:
    """Add existing paper roots/groups only; never invent refs or semantic edges."""
    guidance = context.get("scientific_guidance")
    if guidance is None:
        return list(source_refs)
    allowed = {r["ref"] for r in context["references"]}
    if guidance.get("policy") != POLICY or set(source_refs) - allowed:
        raise _invalid()
    links = {link["ref"]: set(link["source_refs"]) for link in guidance["root_links"]}
    groups = [set(table["source_refs"]) for table in guidance["table_groups"]]
    if set(links) - allowed or any(group - allowed for group in [*links.values(), *groups]):
        raise _invalid()
    selected = set(source_refs)
    while True:
        expanded = selected | set().union(*(links.get(ref, set()) for ref in selected))
        for group in groups:
            if expanded.intersection(group):
                expanded.update(group)
        if expanded == selected:
            break
        selected = expanded
    # Keep model order, with program-added refs in stable manifest order.
    return [
        *source_refs,
        *(r["ref"] for r in context["references"] if r["ref"] in selected - set(source_refs)),
    ]


def background_refs(source_refs: list[str], context: dict[str, Any]) -> list[str]:
    guidance = context.get("scientific_guidance")
    if not guidance:
        return []
    return sorted(
        role["ref"]
        for role in guidance["source_roles"]
        if role["ref"] in source_refs
        and (
            role["contribution_type"] == "background" or role["legacy_claim_origin"] == "background"
        )
    )
