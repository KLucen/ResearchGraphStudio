"""Rebuildable local retrieval over source authority, never the paginated canvas.

The index is derived data. Every retrieval refreshes current source eligibility
and document permissions before ranking; it cannot grant permission by caching.
"""

import hashlib
import json
import re
from collections.abc import Sequence
from typing import Any
from uuid import NAMESPACE_URL, UUID

from sqlalchemy import bindparam, select, text
from sqlalchemy.orm import Session

from researchgraph.document_structure import current_structure
from researchgraph.knowledge_models import EvidenceSpan, KnowledgeNode, Section
from researchgraph.knowledge_store import KnowledgeError, digest, text_hash
from researchgraph.models import AttachmentRevision, Chunk, Paper, Project
from researchgraph.query_graph import _expand_graph, eligible_nodes

INDEX_POLICY = "query-index-1"


def scope_versions(
    session: Session,
    project_id: str,
    paper_ids: list[str],
    version_ids: list[str] | None = None,
) -> dict[str, AttachmentRevision]:
    if session.get(Project, project_id) is None:
        raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")
    papers = list(session.scalars(select(Paper).where(Paper.project_id == project_id)))
    allowed = {p.id for p in papers}
    if set(paper_ids) - allowed:
        raise KnowledgeError("QUERY_SCOPE_MISMATCH", "论文不属于本项目")
    selected = set(paper_ids) if paper_ids else allowed
    versions = list(
        session.scalars(
            select(AttachmentRevision)
            .where(AttachmentRevision.paper_id.in_(selected))
            .order_by(AttachmentRevision.created_at.desc(), AttachmentRevision.id.desc())
        )
    )
    current: dict[str, AttachmentRevision] = {}
    for version in versions:
        current.setdefault(version.paper_id, version)
    if version_ids and set(version_ids) - {v.id for v in current.values()}:
        raise KnowledgeError("QUERY_SCOPE_MISMATCH", "请求的文献版本不属于当前范围或已更新")
    return {v.id: v for v in current.values() if not version_ids or v.id in version_ids}


def strings(value: Any) -> list[str]:
    """Index original and auxiliary translation without losing either language."""
    result: list[str] = []
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, list):
            pending.extend(reversed(item))
        elif isinstance(item, dict):
            pending.extend(reversed(item.values()))
    return result


def chunk_metadata(session: Session, version_id: str) -> dict[str, dict[str, Any]]:
    artifact = current_structure(session, version_id)
    if artifact:
        version = session.get(AttachmentRevision, version_id)
        if (
            not version
            or artifact.source_sha256 != version.sha256
            or artifact.data.get("schema_version") != "pdf-structure-1"
            or artifact.data.get("parser_version") != artifact.parser_version
        ):
            raise KnowledgeError("QUERY_PARSE_INVALID", "结构解析不属于当前文献来源")
        parse_hash = digest(artifact.data)
        sections = {s["id"]: s for s in artifact.data["sections"]}
        chunks = {
            c.id: c for c in session.scalars(select(Chunk).where(Chunk.revision_id == version_id))
        }
        if len(sections) != len(artifact.data["sections"]):
            raise KnowledgeError("QUERY_PARSE_INVALID", "解析章节身份重复")
        result = {}
        block_refs = set()
        for block in artifact.data["blocks"]:
            chunk = chunks.get(block["chunk_id"])
            if (
                not chunk
                or chunk.text != block["text"]
                or chunk.bbox != block["bbox"]
                or chunk.page_index != block["page_index"]
                or chunk.block_index != block["block_index"]
                or block["chunk_id"] in result
                or block["ref"] in block_refs
                or block["section_ref"] not in sections
            ):
                raise KnowledgeError("QUERY_PARSE_INVALID", "结构解析的块与不可变原文不匹配")
            block_refs.add(block["ref"])
            section = sections[block["section_ref"]]
            path: list[str] = []
            seen: set[str] = set()
            cursor: dict[str, Any] | None = section
            excluded = bool(block.get("excluded"))
            while cursor:
                if cursor["id"] in seen:
                    raise KnowledgeError("INVALID_SECTION", "章节路径存在循环")
                seen.add(cursor["id"])
                excluded = (
                    excluded
                    or bool(cursor.get("excluded"))
                    or cursor.get("role") in {"references", "header", "footer"}
                )
                path.insert(0, cursor["title"])
                if cursor.get("parent_id") and cursor["parent_id"] not in sections:
                    raise KnowledgeError("QUERY_PARSE_INVALID", "解析章节父节点缺失")
                cursor = sections.get(cursor.get("parent_id"))
            result[block["chunk_id"]] = {
                "excluded": excluded,
                "section_path": path,
                "section_ref": section["id"],
                "block_ref": block["ref"],
                "parse_id": artifact.id,
                "parse_hash": parse_hash,
            }
        if result.keys() != chunks.keys():
            raise KnowledgeError("QUERY_PARSE_INVALID", "结构解析未精确覆盖版本原文")
        for table in artifact.data["tables"]:
            if not table["block_refs"] or set(table["block_refs"]) - block_refs:
                raise KnowledgeError("QUERY_PARSE_INVALID", "表格原文块或表头引用缺失")
            rows = table.get("rows", [])
            for cell in table.get("cells", []):
                row, column = cell.get("row"), cell.get("column")
                height, width = cell.get("row_span"), cell.get("col_span")
                if (
                    any(type(v) is not int for v in (row, column, height, width))
                    or row < 0
                    or column < 0
                    or height < 1
                    or width < 1
                    or row + height > len(rows)
                    or any(column + width > len(r) for r in rows[row : row + height])
                    or set(cell.get("block_refs", [])) - set(table["block_refs"])
                ):
                    raise KnowledgeError("QUERY_PARSE_INVALID", "表格单元格引用或行列跨度不合法")
        return result
    # Legacy sources have section identity through their immutable evidence.
    result = {}
    for span, section in session.execute(
        select(EvidenceSpan, Section)
        .join(Section, Section.id == EvidenceSpan.section_id)
        .where(EvidenceSpan.document_version_id == version_id)
    ):
        result[span.paragraph_id] = {
            "excluded": section.role
            in {"references", "header", "footer", "page_header", "page_footer"},
            "section_path": [section.title],
            "section_ref": section.id,
        }
    return result


def collect_entries(
    session: Session,
    project_id: str,
    *,
    include_personal: bool = False,
    purpose: str = "local",
    _validated_nodes: list[KnowledgeNode] | None = None,
) -> list[dict[str, Any]]:
    from researchgraph.query_documents import read_notes, read_passages

    versions = scope_versions(session, project_id, [])
    entries: list[dict[str, Any]] = []
    # The UUIDv5 namespace and project prefix are invariant in this one call.
    # Copy only the SHA-1 state, never source eligibility or generated entries.
    id_prefix = hashlib.sha1(NAMESPACE_URL.bytes, usedforsecurity=False)
    id_prefix.update(f"researchgraph/{INDEX_POLICY}/{project_id}:".encode())

    def add(kind: str, oid: str, content: str, aliases: str, data: dict[str, Any]) -> None:
        identifier = id_prefix.copy()
        identifier.update(f"{kind}:{oid}".encode())
        entries.append(
            {
                "id": str(UUID(bytes=identifier.digest()[:16], version=5)),
                "project_id": project_id,
                "source_kind": kind,
                "object_id": oid,
                "text": content,
                "aliases": aliases,
                "data": data,
            }
        )

    papers = {p.id: p for p in session.scalars(select(Paper).where(Paper.project_id == project_id))}
    for version in versions.values():
        identity = {"paper_id": version.paper_id, "document_version_id": version.id}
        add("paper", version.paper_id, papers[version.paper_id].title, "", identity)
        metadata = chunk_metadata(session, version.id)
        # Indexing needs these source scalars, not 20,000 transient ORM states.
        # Structured metadata/anchor validation above remains unchanged.
        for chunk in session.execute(
            select(Chunk.id, Chunk.text, Chunk.page_index).where(Chunk.revision_id == version.id)
        ):
            meta = metadata.get(chunk.id, {})
            if meta.get("excluded"):
                continue
            add(
                "chunk",
                chunk.id,
                chunk.text,
                "",
                {
                    **identity,
                    **meta,
                    "sha256": text_hash(chunk.text),
                    "start": 0,
                    "end": len(chunk.text),
                    "page_index": chunk.page_index,
                },
            )
    for node in (
        eligible_nodes(session, project_id, list(papers))
        if _validated_nodes is None
        else _validated_nodes
    ):
        if node.paper_id not in papers:
            continue
        if node.document_version_id not in versions:
            continue
        content = "\n".join(dict.fromkeys([node.text, *strings(node.payload)]))
        add(
            "knowledge",
            node.id,
            content,
            "\n".join(strings(node.payload.get("aliases", []))),
            {
                "paper_id": node.paper_id,
                "document_version_id": node.document_version_id,
                "kind": node.kind,
                "revision": node.revision,
                "payload_hash": digest(node.payload),
                "authorship": node.authorship,
            },
        )
    for passage in read_passages(
        session, project_id, include_personal=include_personal, purpose=purpose
    ):
        if passage["content_state"] != "valid":
            continue
        add(passage.get("kind", "wiki"), passage["id"], passage["text"], "", passage)
    for note in read_notes(session, project_id, include_personal=include_personal, purpose=purpose):
        add("note", note["id"], note["text"], note["relative_path"], note)
    return sorted(entries, key=lambda entry: entry["id"])


def rebuild_index(
    session: Session,
    project_id: str,
    *,
    include_personal: bool = False,
    purpose: str = "local",
    _validated_nodes: list[KnowledgeNode] | None = None,
    _compute_fingerprint: bool = True,
) -> dict[str, Any]:
    """Synchronize only derived rows, keeping unchanged entries and source bytes."""
    entries = collect_entries(
        session,
        project_id,
        include_personal=include_personal,
        purpose=purpose,
        _validated_nodes=_validated_nodes,
    )
    return _synchronize_index(session, project_id, entries, _compute_fingerprint)


def _synchronize_index(
    session: Session,
    project_id: str,
    entries: list[dict[str, Any]],
    compute_fingerprint: bool,
) -> dict[str, Any]:
    """Synchronize this invocation's complete validated source collection."""
    old = {
        row["id"]: row
        for row in session.execute(
            text("SELECT * FROM query_index_entries WHERE project_id=:p"), {"p": project_id}
        ).mappings()
    }
    fts_rows = {
        row["entry_id"]: (row["text"], row["aliases"])
        for row in session.execute(
            text("SELECT entry_id,text,aliases FROM query_fts WHERE project_id=:p"),
            {"p": project_id},
        ).mappings()
    }
    wanted = {entry["id"] for entry in entries}
    pending = []
    encode_data = json.JSONEncoder(ensure_ascii=False, sort_keys=True).encode
    for entry in entries:
        previous = old.get(entry["id"])
        data = encode_data(entry["data"])
        if (
            previous
            and all(previous[k] == entry[k] for k in ("text", "aliases"))
            and previous["data"] == data
            and fts_rows.get(entry["id"]) == (entry["text"], entry["aliases"])
        ):
            continue
        pending.append({**entry, "data": data})
    dirty = sorted(
        (old.keys() - wanted)
        | (fts_rows.keys() - wanted)
        | {entry["id"] for entry in pending if entry["id"] in old or entry["id"] in fts_rows}
    )
    # FTS entry_id is UNINDEXED. Deleting it once per source made a cold rebuild
    # quadratic; batch deletes and inserts preserve the same authoritative diff.
    for start in range(0, len(dirty), 900):
        batch = dirty[start : start + 900]
        for table, column in [("query_index_entries", "id"), ("query_fts", "entry_id")]:
            session.execute(
                text(f"DELETE FROM {table} WHERE project_id=:p AND {column} IN :ids").bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"p": project_id, "ids": batch},
            )
    if pending:
        session.execute(
            text(
                "INSERT INTO query_index_entries"
                "(id,project_id,source_kind,object_id,text,aliases,data) "
                "VALUES (:id,:project_id,:source_kind,:object_id,:text,:aliases,:data)"
            ),
            pending,
        )
        session.execute(
            text(
                "INSERT INTO query_fts(entry_id,project_id,text,aliases) "
                "VALUES (:id,:project_id,:text,:aliases)"
            ),
            pending,
        )
    return {
        "policy": INDEX_POLICY,
        "entries": len(entries),
        "updated": len(pending),
        "removed": len(old.keys() - wanted),
        # Retrieve discards this diagnostic: hashing all eligible entries again
        # adds cost without contributing to source or snapshot validation.
        "fingerprint": digest(entries) if compute_fingerprint else None,
    }


def retrieve(
    session: Session,
    project_id: str,
    question: str,
    paper_ids: list[str],
    *,
    version_ids: list[str] | None = None,
    include_personal: bool = False,
    purpose: str = "local",
    limit: int | None = 20,
    source_kinds: Sequence[str] | None = None,
    knowledge_kinds: Sequence[str] | None = None,
    include_comparison: bool = True,
) -> dict[str, Any]:
    from researchgraph.query_documents import read_notes, read_passages

    versions = scope_versions(session, project_id, paper_ids, version_ids)
    scope = {v.paper_id for v in versions.values()}
    # Explicit papers without a parsed/current attachment still belong to the
    # user's requested scope and must appear as missing, not disappear silently.
    requested_scope = set(paper_ids) if paper_ids and not version_ids else scope
    # A local list, never a Session cache: the next retrieve revalidates current
    # sources again even within the same transaction. The synchronous index and
    # graph phases do not mutate scientific rows between these checks.
    project_nodes = eligible_nodes(session, project_id, [])
    entries = collect_entries(
        session,
        project_id,
        include_personal=include_personal,
        purpose=purpose,
        _validated_nodes=project_nodes,
    )
    _synchronize_index(session, project_id, entries, False)
    question = question.strip()
    if not question:
        empty: dict[str, Any] = {
            "status": "empty",
            "hits": [],
            "graph": _expand_graph(
                session, project_id, list(scope), [], [], validated_nodes=project_nodes
            ),
            "terms": [],
        }
        if paper_ids or version_ids:
            empty["scope_coverage"] = {
                "requested_paper_ids": sorted(requested_scope),
                "covered_paper_ids": [],
                "missing_paper_ids": sorted(requested_scope),
            }
            empty["ranking_policy"] = "lexical-graph-scoped-2"
        return empty
    tokens = re.findall(r"[\w]+(?:[.%/−-][\w]+)*", question.casefold())
    # unicode61 does not segment Chinese sentences. Exact CJK bigrams provide
    # deterministic local recall using stored translations, without an LLM call.
    grams = [
        run[i : i + 2]
        for run in re.findall(r"[\u3400-\u9fff]+", question)
        for i in range(len(run) - 1)
    ]
    terms = list(dict.fromkeys([*tokens, *grams]))
    fts: dict[str, float] = {}
    if terms:
        # Only program-quoted terms reach MATCH. Never interpolate user SQL/FTS syntax.
        expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        for fts_row in session.execute(
            text(
                "SELECT entry_id,bm25(query_fts) AS rank FROM query_fts "
                "WHERE query_fts MATCH :q AND project_id=:p ORDER BY rank,entry_id"
            ),
            {"q": expression, "p": project_id},
        ).mappings():
            fts[fts_row["entry_id"]] = float(fts_row["rank"])
    # Recheck transitive personal permissions for every expression layer, before ranking.
    docs = {
        p["id"]: p
        for p in read_passages(
            session, project_id, include_personal=include_personal, purpose=purpose
        )
        if p["content_state"] == "valid"
    }
    notes = {
        p["id"]: p
        for p in read_notes(session, project_id, include_personal=include_personal, purpose=purpose)
    }
    hits = []
    # Synchronization just checked the complete source collection. Ranking this
    # same local collection avoids rereading/decoding all derived rows while
    # preserving FTS recovery and the fresh permissions checks above.
    for row in entries:
        data = row["data"]
        kind, oid = row["source_kind"], row["object_id"]
        if source_kinds and kind not in source_kinds:
            continue
        if kind == "knowledge" and knowledge_kinds and data.get("kind") not in knowledge_kinds:
            continue
        if kind in {"paper", "chunk", "knowledge"}:
            if data.get("document_version_id") not in versions:
                continue
        elif kind == "note":
            if oid not in notes or paper_ids:
                continue
        else:
            passage = docs.get(oid)
            if passage is None:
                continue
            roots = passage.get("roots", [])
            root_versions = {
                r.get("document_version_id") for r in roots if r.get("document_version_id")
            }
            if root_versions - versions.keys() or (paper_ids and not root_versions):
                continue
            data = passage
        haystack = (row["text"] + "\n" + row["aliases"]).casefold()
        exact = bool(question.casefold() in haystack)
        matched = [term for term in terms if term in haystack]
        if not exact and not matched and row["id"] not in fts:
            continue
        reasons = (
            (["exact_phrase"] if exact else [])
            + (["exact_term"] if matched else [])
            + (["fts_bm25"] if row["id"] in fts else [])
        )
        # Stable fusion: exact phrase, term coverage, then local BM25; no model rewriting.
        score = 5.0 * exact + len(matched) / max(1, len(terms)) + (1.0 if row["id"] in fts else 0.0)
        hits.append(
            {
                "entry_id": row["id"],
                "source_kind": kind,
                "object_id": oid,
                "text": row["text"],
                "data": data,
                "score": score,
                "bm25": fts.get(row["id"], 0.0),
                "reasons": reasons,
                "matched_terms": matched,
            }
        )
    hits.sort(key=lambda h: (-h["score"], h["bm25"], h["entry_id"]))

    def paper_roots(hit: dict[str, Any]) -> set[str]:
        """Scientific source coverage; a title match alone provides no evidence."""
        data = hit["data"]
        vids = {
            r["document_version_id"]
            for r in data.get("roots", [])
            if r.get("document_version_id") in versions
        }
        if hit["source_kind"] in {"chunk", "knowledge"}:
            vids.add(data.get("document_version_id"))
        return {versions[vid].paper_id for vid in vids if vid in versions}

    explicit_scope = bool(paper_ids or version_ids)
    if explicit_scope and limit is not None:
        # Reserve the highest-ranked genuine match for each selected paper;
        # shared documents may cover more than one paper. Never fabricate a
        # match or silently increase the caller's result limit.
        selected_hits: dict[str, dict[str, Any]] = {}
        covered: set[str] = set()
        for paper_id in sorted(requested_scope):
            if paper_id in covered or len(selected_hits) >= limit:
                continue
            best = next((h for h in hits if paper_id in paper_roots(h)), None)
            if best:
                selected_hits[best["entry_id"]] = best
                covered.update(paper_roots(best))
        for hit in hits:
            if len(selected_hits) >= limit:
                break
            selected_hits.setdefault(hit["entry_id"], hit)
        # Preserve the prior relevance order within the chosen balanced set.
        hits = [h for h in hits if h["entry_id"] in selected_hits]
    elif limit is not None:
        hits = hits[:limit]
    node_seeds = [h["object_id"] for h in hits if h["source_kind"] == "knowledge"]
    chunk_seeds = [h["object_id"] for h in hits if h["source_kind"] == "chunk"]
    for hit in hits:
        for root in hit["data"].get("roots", []):
            if root.get("type") == "chunk":
                chunk_seeds.append(root["id"])
            elif root.get("type") == "evidence":
                span = session.get(EvidenceSpan, root["id"])
                if span and span.document_version_id in versions:
                    chunk_seeds.append(span.paragraph_id)
            elif root.get("type") == "node":
                node_seeds.append(root["id"])
    graph = _expand_graph(
        session,
        project_id,
        list(scope),
        node_seeds,
        chunk_seeds,
        validated_nodes=project_nodes,
        include_comparison=include_comparison,
    )
    # Retain layer hits, but independence is counted by root source identity, never by Wiki copies.
    roots = set()
    for hit in hits:
        data = hit["data"]
        if hit["source_kind"] == "note":
            roots.add("note:" + hit["object_id"])
        if data.get("document_version_id"):
            roots.add("paper:" + data["document_version_id"])
        for root in data.get("roots", []):
            if root.get("document_version_id"):
                roots.add("paper:" + root["document_version_id"])
            elif root.get("type") == "note":
                roots.add("note:" + str(root["id"]))
    roots.update("paper:" + node["document_version_id"] for node in graph["nodes"])
    result = {
        "status": "matched" if hits else "no_evidence",
        "hits": hits,
        "graph": graph,
        "terms": terms,
        "independent_sources": sorted(roots),
        "ranking_policy": "lexical-graph-scoped-2" if explicit_scope else "lexical-graph-1",
    }
    if explicit_scope:
        covered = {p for h in hits for p in paper_roots(h)} | {
            node["paper_id"] for node in graph["nodes"]
        }
        result["scope_coverage"] = {
            "requested_paper_ids": sorted(requested_scope),
            "covered_paper_ids": sorted(requested_scope & covered),
            "missing_paper_ids": sorted(requested_scope - covered),
        }
    return result
