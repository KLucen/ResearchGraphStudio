"""P5 scope assembly: all selected legal sources, independent of canvas and lexical top-k."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.query_contracts import QueryRequest
from researchgraph.query_graph import expand_graph
from researchgraph.query_retrieval import collect_entries, scope_versions
from researchgraph.reading_models import ReadingHead


def collect_scope(
    session: Session,
    project_id: str,
    query: QueryRequest,
    *,
    exclude_document_id: str | None = None,
    personal_sources: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from researchgraph.knowledge_store import KnowledgeError
    from researchgraph.p5_personal import assert_selected_roots, selected_sources

    selected = (
        selected_sources(session, project_id, personal_sources)
        if personal_sources is not None
        else None
    )
    versions = scope_versions(session, project_id, query.paper_ids, query.document_version_ids)
    papers = {v.paper_id for v in versions.values()}
    hits = []
    for entry in collect_entries(
        session, project_id, include_personal=query.include_personal, purpose="model"
    ):
        kind, data = entry["source_kind"], entry["data"]
        if exclude_document_id and data.get("document_id") == exclude_document_id:
            continue  # The update baseline is historical context, never its own new evidence.
        if query.source_kinds and kind not in query.source_kinds:
            continue
        if (
            kind == "knowledge"
            and query.knowledge_kinds
            and data.get("kind") not in query.knowledge_kinds
        ):
            continue
        if kind in {"paper", "chunk", "knowledge"}:
            if data.get("document_version_id") not in versions:
                continue
        elif kind in {"wiki", "synthesis"}:
            roots = {
                r["document_version_id"]
                for r in data.get("roots", [])
                if r.get("document_version_id")
            }
            if roots - versions.keys() or (query.paper_ids and not roots):
                continue
            if (
                query.document_version_ids
                and data.get("document_version_id") not in query.document_version_ids
            ):
                # Document selectors describe paper versions in the existing Query contract.
                if not roots.intersection(query.document_version_ids):
                    continue
        elif kind == "note" and not query.include_personal:
            continue
        if personal_sources is not None:
            if kind == "note" and entry["object_id"] not in personal_sources.get("note_ids", []):
                continue
            try:
                assert_selected_roots(data.get("roots", []), personal_sources)
            except KnowledgeError:
                continue
        hits.append(
            {
                "entry_id": entry["id"],
                "source_kind": kind,
                "object_id": entry["object_id"],
                "text": entry["text"],
                "data": data,
                "score": 1.0,
                "bm25": 0.0,
                "reasons": ["explicit_wiki_source_scope"],
                "matched_terms": [],
            }
        )
    for source in selected or []:
        if source["type"] == "note":
            continue  # Existing note entries already passed the selected snapshot filter.
        hits.append(
            {
                "entry_id": f"{source['type']}:{source['id']}",
                "source_kind": source["type"],
                "object_id": source["id"],
                "text": source["text"],
                "data": source,
                "score": 1.0,
                "bm25": 0.0,
                "reasons": ["explicit_personal_source_scope"],
                "matched_terms": [],
            }
        )
    hits.sort(key=lambda h: (h["source_kind"], h["object_id"]))
    nodes = [h["object_id"] for h in hits if h["source_kind"] == "knowledge"]
    chunks = [h["object_id"] for h in hits if h["source_kind"] == "chunk"]
    graph = expand_graph(session, project_id, sorted(papers), nodes, chunks)
    wanted = sorted(set(query.paper_ids) or papers)
    result = {
        "status": "matched" if hits else "no_evidence",
        "hits": hits,
        "graph": graph,
        "terms": [],
        "independent_sources": ["paper:" + v for v in sorted(versions)],
        "ranking_policy": "wiki-complete-source-scope-1",
    }
    if query.paper_ids or query.document_version_ids:
        result["scope_coverage"] = {"requested_paper_ids": wanted}
    if personal_sources is not None:
        result["p5_personal_sources"] = personal_sources
    return result


def selection_map(session: Session, context: dict[str, Any]) -> dict[str, Any]:
    papers = {v["paper_id"] for v in context["scope_versions"]}
    heads = {
        h.paper_id: h
        for h in session.scalars(select(ReadingHead).where(ReadingHead.paper_id.in_(papers)))
    }
    return {
        v["id"]: {
            "paper_id": v["paper_id"],
            "source_sha256": v["sha256"],
            "selection_revision": heads[v["paper_id"]].revision if v["paper_id"] in heads else None,
            "selection_id": heads[v["paper_id"]].selection_id if v["paper_id"] in heads else None,
        }
        for v in context["scope_versions"]
    }
