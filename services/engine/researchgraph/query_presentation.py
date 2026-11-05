"""Readable Query sources, separate from frozen retrieval/context identities.

Callers must validate the retrieval/context before building this local-only view.
Existing extraction translations are reused; this module never translates or
dispatches a model request and never changes a historical snapshot/hash.
"""

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.graph_projection import display_data
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeNode, NodeEvidence, Section
from researchgraph.models import AttachmentRevision, Paper
from researchgraph.query_source_scope import paper_ids_from_sources


def source_presentation(
    session: Session,
    project_id: str,
    retrieval: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    papers = {p.id: p for p in session.scalars(select(Paper).where(Paper.project_id == project_id))}
    version_papers = {
        row[0]: row[1]
        for row in session.execute(
            select(AttachmentRevision.id, AttachmentRevision.paper_id).where(
                AttachmentRevision.paper_id.in_(papers)
            )
        )
    }
    # Only use nodes already admitted to this particular validated retrieval.
    node_ids = {n["id"] for n in retrieval.get("graph", {}).get("nodes", [])}
    node_ids.update(h["object_id"] for h in retrieval["hits"] if h["source_kind"] == "knowledge")
    nodes = {
        n.id: n
        for n in session.scalars(select(KnowledgeNode).where(KnowledgeNode.id.in_(node_ids)))
        if n.paper_id in papers
    }
    links: dict[str, list[str]] = defaultdict(list)
    for link in session.scalars(select(NodeEvidence).where(NodeEvidence.node_id.in_(nodes))):
        links[link.node_id].append(link.evidence_id)
    evidence_ids = {eid for eids in links.values() for eid in eids}
    evidence_ids.update(
        r["id"] for r in (context or {}).get("references", []) if r["type"] == "evidence"
    )
    spans = {
        e.id: e
        for e in session.scalars(select(EvidenceSpan).where(EvidenceSpan.id.in_(evidence_ids)))
    }
    evidence_summaries: dict[str, list[str]] = defaultdict(list)
    chunk_summaries: dict[str, list[str]] = defaultdict(list)
    node_summaries: dict[str, str] = {}
    # This local-only warning also protects historical answers without changing
    # their frozen context, raw response or original v1 validation protocol.
    from researchgraph.query_numeric_layout import freeze_layout, warnings_by_reference

    layout_refs = list((context or {}).get("references", []))
    if context is None:
        for hit in retrieval["hits"]:
            oid, kind = hit["object_id"], hit["source_kind"]
            if kind == "knowledge" and oid in nodes:
                layout_refs.append(
                    {
                        "ref": hit["entry_id"],
                        "type": "node",
                        "id": oid,
                        "document_version_id": nodes[oid].document_version_id,
                        "evidence_ids": links[oid],
                    }
                )
            elif kind == "chunk":
                layout_refs.append(
                    {
                        "ref": hit["entry_id"],
                        "type": "chunk",
                        "id": oid,
                        "document_version_id": hit["data"]["document_version_id"],
                        "quote": hit["text"],
                    }
                )
    layout_warnings = warnings_by_reference(freeze_layout(session, layout_refs))
    source_warnings: dict[tuple[str, str], list[str]] = defaultdict(list)
    for ref in layout_refs:
        source_warnings[(ref["type"], ref["id"])].extend(layout_warnings.get(ref["ref"], []))
    for nid, node in nodes.items():
        value = display_data(session, node).get("summary_zh")
        if not isinstance(value, str) or not value.strip():
            continue
        value = value.strip()
        node_summaries[nid] = value
        for eid in links[nid]:
            span = spans.get(eid)
            if span and span.document_version_id == node.document_version_id:
                evidence_summaries[eid].append(value)
                chunk_summaries[span.paragraph_id].append(value)

    def display(kind: str, oid: str, data: dict[str, Any], original: str) -> dict[str, Any]:
        pid = data.get("paper_id")
        section_path = data.get("section_path") or []
        page_index = data.get("page_index")
        summaries: list[str] = []
        if kind == "node" and oid in nodes:
            node = nodes[oid]
            pid = node.paper_id
            cited = [spans[e] for e in sorted(links[oid]) if e in spans]
            original = "\n\n".join(dict.fromkeys(s.quote for s in cited)) or node.text
            summaries = [node_summaries[oid]] if oid in node_summaries else []
            if cited:
                pages = {span.page_index for span in cited}
                page_index = next(iter(pages)) if len(pages) == 1 else None
                section_path = list(
                    dict.fromkeys(
                        section.title
                        for span in cited
                        if (section := session.get(Section, span.section_id)) is not None
                    )
                )
        elif kind == "evidence":
            summaries = evidence_summaries[oid]
            span = spans.get(oid)
            if span:
                section = session.get(Section, span.section_id)
                section_path = [section.title] if section else []
        elif kind == "chunk":
            summaries = chunk_summaries[oid]
        summary = "\n".join(dict.fromkeys(summaries)) or None
        return {
            "title": papers[pid].title
            if pid in papers
            else data.get("title") or data.get("relative_path") or "来源材料",
            "original": original,
            "summary_zh": summary,
            "summary_origin": "extracted_translation" if summary else None,
            "paper_id": pid,
            "paper_ids": paper_ids_from_sources(
                [{**data, "type": kind, "id": oid, "paper_id": pid}],
                set(papers),
                version_papers,
            ),
            "page_index": page_index,
            "section_path": section_path,
            "layout_warnings": list(dict.fromkeys(source_warnings[(kind, oid)])),
        }

    hits = {}
    for hit in retrieval["hits"]:
        kind = "node" if hit["source_kind"] == "knowledge" else hit["source_kind"]
        original = (
            nodes[hit["object_id"]].text
            if kind == "node" and hit["object_id"] in nodes
            else hit["text"]
        )
        hits[hit["entry_id"]] = display(kind, hit["object_id"], hit["data"], original)
    references = {}
    for ref in (context or {}).get("references", []):
        references[ref["ref"]] = display(
            ref["type"],
            ref["id"],
            ref,
            ref.get("quote") or ref.get("text") or ref.get("title") or "",
        )
    return {"hits": hits, "references": references}
