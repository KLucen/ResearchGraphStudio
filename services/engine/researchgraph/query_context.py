"""Q04: immutable, replayable evidence manifests, without model or science writes."""

import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.document_structure import current_structure
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeNode, NoteSnapshot
from researchgraph.knowledge_store import KnowledgeError, digest, text_hash, validate_evidence
from researchgraph.models import Chunk, Paper
from researchgraph.query_graph import eligible_nodes, expand_graph
from researchgraph.query_retrieval import chunk_metadata, scope_versions

CONTEXT_POLICY = "query-context-1"


def build_context(
    session: Session,
    request: dict[str, Any],
    retrieval: dict[str, Any],
    *,
    model_snapshot: dict[str, Any] | None = None,
    include_layout: bool = False,
    include_scientific_guidance: bool = False,
) -> dict[str, Any]:
    from researchgraph.query_documents import read_notes, read_passages, validate_dependencies

    project_id = request["project_id"]
    versions = scope_versions(
        session, project_id, request.get("paper_ids", []), request.get("document_version_ids", [])
    )
    paper_scope = {v.paper_id for v in versions.values()}
    personal, purpose = request.get("include_personal", False), request.get("purpose", "local")
    personal_selection = retrieval.get("p5_personal_sources")
    selected_personal: dict[tuple[str, str], dict[str, Any]] | None = None
    if personal_selection is not None:
        from researchgraph.p5_personal import selected_sources

        selected_personal = {
            (s["type"], s["id"]): s
            for s in selected_sources(session, project_id, personal_selection, purpose=purpose)
        }
    docs = {
        p["id"]: p
        for p in read_passages(session, project_id, include_personal=personal, purpose=purpose)
        if p["content_state"] == "valid"
    }
    notes = {
        p["id"]: p
        for p in read_notes(session, project_id, include_personal=personal, purpose=purpose)
    }
    graph = retrieval["graph"]
    current_graph = expand_graph(
        session,
        project_id,
        sorted(paper_scope),
        graph.get("seed_node_ids", []),
        graph.get("seed_chunk_ids", []),
    )
    if digest(graph) != digest(current_graph):
        raise KnowledgeError("QUERY_CONTEXT_CHANGED", "图谱支撑路径或候选已变化，请重新检索")
    candidates = {n.id: n for n in eligible_nodes(session, project_id, sorted(paper_scope))}
    references: dict[tuple[str, str], dict[str, Any]] = {}
    used_versions: set[str] = set()
    coverage: list[str] = []
    metadata = {vid: chunk_metadata(session, vid) for vid in versions}

    def add_chunk(cid: str) -> None:
        if ("chunk", cid) in references:
            return
        chunk = session.get(Chunk, cid)
        if chunk is None or chunk.revision_id not in versions:
            raise KnowledgeError("QUERY_SOURCE_INVALID", "原文块不属于本次项目/文献范围")
        meta = metadata[chunk.revision_id].get(cid, {})
        if meta.get("excluded"):
            raise KnowledgeError("QUERY_SOURCE_EXCLUDED", "参考文献或页眉页脚不能作当前科学证据")
        used_versions.add(chunk.revision_id)
        references[("chunk", cid)] = {
            "type": "chunk",
            "id": cid,
            "document_version_id": chunk.revision_id,
            "paper_id": versions[chunk.revision_id].paper_id,
            "sha256": text_hash(chunk.text),
            "start": 0,
            "end": len(chunk.text),
            "quote": chunk.text,
            "page_index": chunk.page_index,
            "bbox": chunk.bbox,
            "section_path": meta.get("section_path", []),
            "section_ref": meta.get("section_ref"),
            "current_file_status": "not_checked",
            "parse_id": meta.get("parse_id"),
            "parse_hash": meta.get("parse_hash"),
        }

    def add_evidence(eid: str) -> None:
        span = session.get(EvidenceSpan, eid)
        if span is None or span.document_version_id not in versions:
            raise KnowledgeError("QUERY_SOURCE_INVALID", "证据不属于本次来源清单")
        validate_evidence(session, span, span.document_version_id)
        add_chunk(span.paragraph_id)
        references[("evidence", eid)] = {
            "type": "evidence",
            "id": eid,
            "document_version_id": span.document_version_id,
            "paper_id": versions[span.document_version_id].paper_id,
            "paragraph_id": span.paragraph_id,
            "sha256": span.text_sha256,
            "start": span.start_offset,
            "end": span.end_offset,
            "quote": span.quote,
            "page_index": span.page_index,
            "section_id": span.section_id,
            "bbox_list": span.bbox_list,
            "current_file_status": "not_checked",
        }

    def add_node(nid: str) -> None:
        node = candidates.get(nid)
        if node is None or node.document_version_id not in versions:
            raise KnowledgeError("QUERY_SOURCE_INVALID", "知识来源或有效性已变化")
        from researchgraph.knowledge_models import NodeEvidence

        eids = sorted(
            session.scalars(select(NodeEvidence.evidence_id).where(NodeEvidence.node_id == nid))
        )
        references[("node", nid)] = {
            "type": "node",
            "id": nid,
            "revision": node.revision,
            "document_version_id": node.document_version_id,
            "paper_id": node.paper_id,
            "payload_hash": digest(node.payload),
            "text": node.text,
            "authorship": node.authorship,
            "origin": node.origin,
            "issues": node.issues,
            "evidence_ids": eids,
        }
        for eid in eids:
            add_evidence(eid)

    def add_document(oid: str) -> None:
        passage = docs.get(oid)
        if passage is None:
            raise KnowledgeError("QUERY_DOCUMENT_INVALID", "文档依赖/授权已变化或不是有效保存版本")
        state = validate_dependencies(
            session, project_id, passage["dependencies"], include_personal=personal, purpose=purpose
        )
        if state["content_state"] != "valid":
            raise KnowledgeError("QUERY_DOCUMENT_INVALID", "文档根依赖不再有效")
        if personal_selection is not None:
            from researchgraph.p5_personal import assert_selected_roots

            assert_selected_roots(state["roots"], personal_selection)
        references[("passage", oid)] = {
            "type": "passage",
            **passage,
            "sha256": text_hash(passage["text"]),
        }
        for root in state["roots"]:
            if root.get("type") == "chunk":
                add_chunk(root["id"])
            elif root.get("type") == "evidence":
                add_evidence(root["id"])
            elif root.get("type") == "node":
                add_node(root["id"])
            elif root.get("type") == "note":
                # Dependency validation carries purpose checks; historical internal
                # documents may cite a still-authorized immutable note snapshot.
                note = session.get(NoteSnapshot, root["id"])
                if not note:
                    raise KnowledgeError("QUERY_PERMISSION_CHANGED", "笔记根快照不存在")
                references[("note", root["id"])] = {**root, "text": note.text}
            elif root.get("type") in {"annotation", "external"}:
                if selected_personal is None:
                    if root["type"] == "annotation":
                        from researchgraph.p5_personal import annotation_source

                        source = annotation_source(session, project_id, root["id"], purpose=purpose)
                    else:
                        from researchgraph.external_documents import validate_external_version

                        source = validate_external_version(
                            session,
                            project_id,
                            root["id"],
                            include_personal=personal,
                            purpose=purpose,
                        )
                else:
                    chosen_source = selected_personal.get((root["type"], root["id"]))
                    if chosen_source is None:
                        raise KnowledgeError(
                            "P5_PERSONAL_SOURCE_NOT_SELECTED", "个人来源未被明确选中"
                        )
                    source = chosen_source
                references[(root["type"], root["id"])] = source

    for hit in retrieval["hits"]:
        kind, oid = hit["source_kind"], hit["object_id"]
        if kind == "chunk":
            add_chunk(oid)
            chunk = session.get(Chunk, oid)
            if chunk is None or hit["data"].get("sha256") != text_hash(chunk.text):
                raise KnowledgeError("QUERY_CONTEXT_CHANGED", "原文哈希已变化")
        elif kind == "knowledge":
            add_node(oid)
            node = session.get(KnowledgeNode, oid)
            if (
                node is None
                or hit["data"].get("revision") != node.revision
                or hit["data"].get("payload_hash") != digest(node.payload)
            ):
                raise KnowledgeError("QUERY_CONTEXT_CHANGED", "知识版本已变化")
        elif kind in {"wiki", "synthesis"}:
            add_document(oid)
        elif kind == "note":
            note = notes.get(oid)
            if selected_personal is not None and ("note", oid) not in selected_personal:
                raise KnowledgeError("P5_PERSONAL_SOURCE_NOT_SELECTED", "笔记未被明确选中")
            if note is None or note["sha256"] != hit["data"].get("sha256"):
                raise KnowledgeError("QUERY_PERMISSION_CHANGED", "笔记快照或用途授权已变化")
            references[("note", oid)] = {"type": "note", **note}
        elif kind in {"annotation", "external"}:
            source = selected_personal.get((kind, oid)) if selected_personal is not None else None
            if not personal or source is None or source != hit["data"]:
                raise KnowledgeError("QUERY_PERSONAL_NOT_AUTHORIZED", "个人来源选择或授权已变化")
            references[(kind, oid)] = source
        elif kind == "paper":
            paper = session.get(Paper, oid)
            if not paper or paper.id not in paper_scope or paper.title != hit["text"]:
                raise KnowledgeError("QUERY_CONTEXT_CHANGED", "论文元数据已变化")
            references[("paper", oid)] = {"type": "paper", "id": oid, "title": paper.title}
    for node in graph["nodes"]:
        add_node(node["id"])
    for edge in [*graph["associations"], *graph["relations"]]:
        for eid in edge["evidence_ids"]:
            add_evidence(eid)

    # Include all headers/cells/notes in a detected table group. Never slice a row
    # away from its header to make the context fit a model.
    tables = []
    for vid in sorted(used_versions):
        artifact = current_structure(session, vid)
        if artifact is None:
            continue
        block_to_chunk = {b["ref"]: b["chunk_id"] for b in artifact.data["blocks"]}
        chunks = {oid for kind, oid in references if kind == "chunk"}
        for table in artifact.data["tables"]:
            if set(table["block_refs"]) - block_to_chunk.keys():
                raise KnowledgeError("QUERY_PARSE_INVALID", "表格原文或表头块缺失")
            ids = {block_to_chunk[b] for b in table["block_refs"] if b in block_to_chunk}
            if not ids.intersection(chunks):
                continue
            excluded = table.get("excluded") or any(
                metadata[vid].get(cid, {}).get("excluded") for cid in ids
            )
            if excluded:
                coverage.append("表格含排除材料，未将其作为完整数值证据")
                continue
            for cid in sorted(ids):
                add_chunk(cid)
            tables.append({"document_version_id": vid, "parse_id": artifact.id, "data": table})
            if table["structure_status"] != "resolved" or not any(
                table.get("header", {}).get("names", [])
            ):
                coverage.append("表格结构不完整；不能据此推断列含义、单位或数值")

    refs = [
        {"ref": f"S{index:05d}", **ref}
        for index, (_, ref) in enumerate(sorted(references.items()), 1)
    ]
    source_versions = [
        {
            "id": vid,
            "paper_id": versions[vid].paper_id,
            "sha256": versions[vid].sha256,
            "parser_version": versions[vid].parser_version,
        }
        for vid in sorted(used_versions)
    ]
    # This optional field marks the new explicit-scope protocol. Historical
    # retrieval snapshots must retain their original manifest/hash on replay.
    scope_coverage = None
    if "scope_coverage" in retrieval:
        supplied = retrieval["scope_coverage"]
        requested = supplied.get("requested_paper_ids") if isinstance(supplied, dict) else None
        allowed = (
            paper_scope
            if request.get("document_version_ids")
            else set(request.get("paper_ids", [])) or paper_scope
        )
        if (
            not (request.get("paper_ids") or request.get("document_version_ids"))
            or not isinstance(requested, list)
            or any(not isinstance(pid, str) for pid in requested)
            or len(requested) != len(set(requested))
            or not paper_scope.issubset(requested)
            or set(requested) != allowed
        ):
            raise KnowledgeError("QUERY_SCOPE_MISMATCH", "查询覆盖范围与显式选定论文不一致")
        # Paper titles and private notes are not scientific paper coverage.
        # Valid document/node citations have already expanded to these roots;
        # do not trust retrieval's claimed covered/missing lists.
        covered = {
            ref["paper_id"]
            for ref in refs
            if ref["type"] in {"chunk", "evidence"}
            and isinstance(ref.get("quote"), str)
            and ref["quote"].strip()
        }
        missing = sorted(set(requested) - covered)
        scope_coverage = {
            "requested_paper_ids": sorted(requested),
            "covered_paper_ids": sorted(covered.intersection(requested)),
            "missing_paper_ids": missing,
        }
        if missing:
            coverage.append("显式选定论文缺少可验证的正文根证据：" + "、".join(missing))
    manifest: dict[str, Any] = {
        "policy": CONTEXT_POLICY,
        "project_id": project_id,
        "request": {
            **request,
            "paper_ids": sorted(paper_scope),
            "document_version_ids": sorted(versions),
        },
        "scope_versions": [
            {
                "id": vid,
                "paper_id": versions[vid].paper_id,
                "sha256": versions[vid].sha256,
                "parser_version": versions[vid].parser_version,
            }
            for vid in sorted(versions)
        ],
        "source_versions": source_versions,
        "references": refs,
        "graph": graph,
        "tables": tables,
        "coverage_gaps": sorted(set(coverage)),
        "independent_sources": retrieval.get("independent_sources", []),
        "model_snapshot_hash": digest(model_snapshot) if model_snapshot else None,
        "scientific_validation": "identity_and_evidence_only_not_truth",
    }
    if scope_coverage is not None:
        manifest["scope_coverage"] = scope_coverage
        # Preserve a deliberately selected paper even when it has no PDF
        # version yet; the normalized request must replay the same missing set.
        manifest["request"]["paper_ids"] = scope_coverage["requested_paper_ids"]
        manifest["request"]["document_version_ids"] = sorted(
            request.get("document_version_ids", [])
        )
    if personal_selection is not None:
        manifest["p5_personal_sources"] = personal_selection
        manifest["personal_source_snapshots"] = list((selected_personal or {}).values())
    if include_layout:
        from researchgraph.query_numeric_layout import freeze_layout

        manifest["numeric_layout"] = freeze_layout(session, refs)
    if include_scientific_guidance:
        from researchgraph.query_scientific_grounding import freeze_guidance

        manifest["scientific_guidance"] = freeze_guidance(session, manifest)
    # Local context has no arbitrary character budget. If a known model capacity
    # is insufficient, stop with the complete context retained for inspection.
    estimated = math.ceil(len(str(manifest).encode("utf-8")) / 3)
    capabilities = (model_snapshot or {}).get("parameters", {}).get("capabilities", {})
    window = capabilities.get("context_window")
    output = capabilities.get("max_output_tokens")
    capacity = window - (output or 0) if window else None
    manifest["capacity"] = {
        "estimated_input_tokens": estimated,
        "context_window": window,
        "reserved_output_tokens": output,
        "sufficient": capacity is None or estimated <= capacity,
        "policy": "complete-groups-no-truncation-1",
    }
    manifest["status"] = (
        "insufficient"
        if coverage or not manifest["capacity"]["sufficient"]
        else "ready"
        if any(
            ref["type"] in {"chunk", "evidence", "note", "annotation", "external"} for ref in refs
        )
        else "no_evidence"
    )
    manifest["input_hash"] = digest(manifest)
    return manifest


def validate_context(
    session: Session,
    manifest: dict[str, Any],
    retrieval: dict[str, Any],
    *,
    model_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    old = dict(manifest)
    claimed = old.pop("input_hash", None)
    if not claimed or digest(old) != claimed:
        raise KnowledgeError("QUERY_MANIFEST_INVALID", "上下文清单哈希或引用已变化")
    current = build_context(
        session,
        manifest["request"],
        retrieval,
        model_snapshot=model_snapshot,
        include_layout="numeric_layout" in manifest,
        include_scientific_guidance="scientific_guidance" in manifest,
    )
    if current["input_hash"] != manifest["input_hash"]:
        raise KnowledgeError(
            "QUERY_CONTEXT_CHANGED", "来源、知识、权限或文档状态已变化，请重新检索"
        )
    return {
        "valid": True,
        "input_hash": claimed,
        "reference_count": len(current["references"]),
        "status": current["status"],
    }
