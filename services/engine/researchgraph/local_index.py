"""Deterministic local text indexing and scope-limited search; no model calls."""

import re
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, Query
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from researchgraph.core import KnowledgeError
from researchgraph.document_structure import (
    active_section_rows,
    block_section_refs,
    current_navigation_rows,
    current_structure,
    section_model_spans,
    section_spans,
)
from researchgraph.models import AttachmentRevision, Chunk, EvidenceSpan, Paper, Project, Section
from researchgraph.schemas import (
    DocumentStructure,
    EvidenceView,
    SearchHit,
    SearchResults,
    SectionList,
    SectionView,
)
from researchgraph.storage import read_session
from researchgraph.structure_upgrade import ensure_structure_v2


def index_document(session: Session, revision_id: str) -> None:
    version = session.get(AttachmentRevision, revision_id)
    if version is None:
        raise KnowledgeError("DOCUMENT_NOT_FOUND", "文献版本不存在")
    session.execute(
        text("DELETE FROM chunk_fts WHERE document_version_id = :revision"),
        {"revision": revision_id},
    )
    artifact = current_structure(session, revision_id)
    if artifact is None:
        return
    active_section_rows(session, revision_id)
    sections = {s["id"]: s for s in artifact.data.get("sections", [])}
    chunks = {
        c.id: c for c in session.scalars(select(Chunk).where(Chunk.revision_id == revision_id))
    }
    for block in artifact.data.get("blocks", []):
        section = sections.get(block.get("section_ref"))
        containing = [sections.get(ref) for ref in block_section_refs(block, sections)]
        chunk = chunks.get(block.get("chunk_id"))
        if (
            not section
            or not chunk
            or block.get("excluded")
            or section.get("excluded")
            or section.get("role") == "references"
            or any(
                not entry or entry.get("excluded") or entry.get("role") == "references"
                for entry in containing
            )
        ):
            continue
        if (
            chunk.text != block.get("text")
            or chunk.page_index != block.get("page_index")
            or chunk.bbox != block.get("bbox")
            or chunk.block_index != block.get("block_index")
        ):
            raise KnowledgeError("PARSE_ANCHOR_MISMATCH", "章节与原文索引不一致")
        session.execute(
            text(
                "INSERT INTO chunk_fts("
                "chunk_id,paper_id,document_version_id,section_id,text) "
                "VALUES (:c,:p,:d,:s,:t)"
            ),
            {
                "c": chunk.id,
                "p": version.paper_id,
                "d": revision_id,
                "s": section["section_id"],
                "t": chunk.text,
            },
        )


def section_views(
    session: Session, revision_id: str, *, include_text: bool = True, section_id: str | None = None
) -> list[SectionView]:
    if session.get(AttachmentRevision, revision_id) is None:
        raise KnowledgeError("DOCUMENT_NOT_FOUND", "文献版本不存在")
    # Keep legacy printed-contents rows out of navigation even when the
    # registered PDF is temporarily unavailable for the one-time v2 upgrade.
    rows = current_navigation_rows(session, revision_id)
    if section_id is not None:
        rows = [row for row in rows if row.id == section_id]
        if not rows:
            raise KnowledgeError("SECTION_NOT_FOUND", "章节已不在当前目录中，请刷新后重新选择")
    out = []
    for row in rows:
        view = SectionView.model_validate(row)
        if include_text:
            selected = section_spans(session, row)
            view.text = "\n".join(span.quote for span in selected)
            view.chunk_ids = [span.paragraph_id for span in selected]
        out.append(view)
    return out


def search(
    session: Session,
    project_id: str,
    query: str,
    paper_id: str | None = None,
    revision_id: str | None = None,
    section_id: str | None = None,
    limit: int = 5,
) -> list[SearchHit]:
    terms = list(dict.fromkeys(re.findall(r"\w+", query, re.UNICODE)))[:50]
    if not terms:
        return []
    if paper_id:
        paper = session.get(Paper, paper_id)
        if paper is None or paper.project_id != project_id:
            raise KnowledgeError("PAPER_NOT_FOUND", "文献不存在")
    if revision_id:
        version = session.get(AttachmentRevision, revision_id)
        paper = session.get(Paper, version.paper_id) if version else None
        if (
            not version
            or not paper
            or paper.project_id != project_id
            or paper_id
            and version.paper_id != paper_id
        ):
            raise KnowledgeError("DOCUMENT_NOT_FOUND", "文献版本不属于当前论文")
    scoped_chunks: list[str] | None = None
    if section_id:
        section = session.get(Section, section_id)
        version = session.get(AttachmentRevision, section.document_version_id) if section else None
        paper = session.get(Paper, version.paper_id) if version else None
        if (
            not section
            or not version
            or not paper
            or paper.project_id != project_id
            or paper_id
            and paper.id != paper_id
            or revision_id
            and version.id != revision_id
        ):
            raise KnowledgeError("SECTION_NOT_FOUND", "章节不属于当前论文范围")
        scoped_chunks = list(
            dict.fromkeys(span.paragraph_id for span in section_model_spans(session, section))
        )
        if not scoped_chunks:
            return []
    sql = (
        "SELECT f.chunk_id,f.paper_id,f.document_version_id,f.section_id,f.text,"
        "bm25(chunk_fts) AS score,c.page_index,c.page_label "
        "FROM chunk_fts f JOIN chunks c ON c.id=f.chunk_id "
        "JOIN papers p ON p.id=f.paper_id "
        "WHERE p.project_id=:project_id AND chunk_fts MATCH :q"
    )
    params: dict[str, object] = {
        "project_id": project_id,
        "q": " OR ".join('"' + term + '"' for term in terms),
    }
    for name, value in (
        ("paper_id", paper_id),
        ("document_version_id", revision_id),
    ):
        if value:
            sql += f" AND f.{name}=:{name}"
            params[name] = value
    if scoped_chunks is not None:
        placeholders = []
        for index, chunk_id in enumerate(scoped_chunks):
            key = f"scope_chunk_{index}"
            placeholders.append(f":{key}")
            params[key] = chunk_id
        sql += " AND f.chunk_id IN (" + ",".join(placeholders) + ")"
    sql += " ORDER BY score,f.chunk_id LIMIT :limit"
    params["limit"] = max(1, min(limit, 50))
    return [
        SearchHit.model_validate(dict(row)) for row in session.execute(text(sql), params).mappings()
    ]


def register_local_index_api(
    app: FastAPI, engine: Callable[[], Engine], data_dir: Path | None = None
) -> None:
    @app.get("/api/v1/papers/{paper_id}/search", response_model=SearchResults)
    def paper_search(
        paper_id: str,
        q: str = Query(min_length=1, max_length=500),
        revision_id: str | None = None,
        section_id: str | None = None,
        limit: int = Query(5, ge=1, le=50),
    ) -> SearchResults:
        with read_session(engine()) as session:
            paper = session.get(Paper, paper_id)
            if paper is None:
                raise KnowledgeError("PAPER_NOT_FOUND", "文献不存在")
            return SearchResults(
                query=q,
                items=search(
                    session, paper.project_id, q, paper_id, revision_id, section_id, limit
                ),
            )

    @app.get("/api/v1/projects/{project_id}/search", response_model=SearchResults)
    def project_search(
        project_id: str,
        q: str = Query(min_length=1, max_length=500),
        paper_id: str | None = None,
        revision_id: str | None = None,
        section_id: str | None = None,
        limit: int = Query(5, ge=1, le=50),
    ) -> SearchResults:
        with read_session(engine()) as session:
            if session.get(Project, project_id) is None:
                raise KnowledgeError("PROJECT_NOT_FOUND", "项目不存在")
            return SearchResults(
                query=q,
                items=search(session, project_id, q, paper_id, revision_id, section_id, limit),
            )

    @app.get("/api/v1/revisions/{revision_id}/sections", response_model=SectionList)
    def revision_sections(
        revision_id: str, include_text: bool = True, section_id: str | None = None
    ) -> SectionList:
        # Existing Lite databases may still have the old parse where printed
        # contents entries were promoted to chapters. Upgrade once from the
        # registered, hash-checked PDF before returning the tree.
        if include_text and section_id is None:
            with read_session(engine()) as session:
                revision = session.get(AttachmentRevision, revision_id)
                paper_id = revision.paper_id if revision else None
            if paper_id:
                ensure_structure_v2(engine(), paper_id, revision_id, data_dir)
        # The QA directory and its single-section preview use committed rows
        # only. Opening them must never synchronously reopen or upgrade a PDF.
        with read_session(engine()) as session:
            return SectionList(
                document_version_id=revision_id,
                sections=section_views(
                    session, revision_id, include_text=include_text, section_id=section_id
                ),
            )

    @app.get("/api/v1/revisions/{revision_id}/structure", response_model=DocumentStructure)
    def structure(revision_id: str) -> DocumentStructure:
        with read_session(engine()) as session:
            revision = session.get(AttachmentRevision, revision_id)
            paper_id = revision.paper_id if revision else None
        if paper_id:
            ensure_structure_v2(engine(), paper_id, revision_id, data_dir)
        with read_session(engine()) as session:
            sections = section_views(session, revision_id)
            artifact = current_structure(session, revision_id)
            return DocumentStructure(
                document_version_id=revision_id,
                sections=sections,
                evidence=[
                    EvidenceView.model_validate(x)
                    for x in session.scalars(
                        select(EvidenceSpan).where(EvidenceSpan.document_version_id == revision_id)
                    )
                ],
                structured_document=artifact.data if artifact else None,
            )
