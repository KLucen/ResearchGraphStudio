"""Structured input and immutable mapping to the existing source authority."""

from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.knowledge_models import EvidenceSpan, Section
from researchgraph.knowledge_store import KnowledgeError, KnowledgeStore, stable_id, text_hash
from researchgraph.models import AttachmentRevision, Chunk, now
from researchgraph.structure_models import DocumentParse

SCHEMA = "pdf-structure-1"
PLANNER = "section-context-v1"


def current_structure(session: Session, version_id: str) -> DocumentParse | None:
    return session.scalar(
        select(DocumentParse)
        .where(DocumentParse.document_version_id == version_id)
        .order_by(DocumentParse.created_at.desc(), DocumentParse.id)
    )


def apply_structure(
    store: KnowledgeStore, version_id: str, source_hash: str, structure: dict[str, Any]
) -> DocumentParse:
    session = store.session
    version = session.get(AttachmentRevision, version_id)
    if not version or version.sha256 != source_hash or structure.get("schema_version") != SCHEMA:
        raise KnowledgeError("PARSE_SOURCE_MISMATCH", "结构解析与文献版本不匹配")
    parser = str(structure["parser_version"])
    artifact_id = stable_id("document-parse", version_id + ":" + parser)
    existing = session.get(DocumentParse, artifact_id)
    if existing:
        return existing
    chunks = {
        (c.page_index, c.block_index): c
        for c in session.scalars(select(Chunk).where(Chunk.revision_id == version_id))
    }
    data = deepcopy(structure)
    seen = set()
    mapped = set()
    for block in data["blocks"]:
        key = (block["page_index"], block["block_index"])
        chunk = chunks.get(key)
        if (
            not chunk
            or chunk.text != block["text"]
            or chunk.bbox != block["bbox"]
            or block["ref"] in seen
            or key in mapped
        ):
            raise KnowledgeError("PARSE_ANCHOR_MISMATCH", "结构文本与已有原文块不一致，旧证据保持")
        seen.add(block["ref"])
        mapped.add(key)
        block["chunk_id"] = chunk.id
    if len(seen) != len(chunks):
        raise KnowledgeError("PARSE_ANCHOR_MISMATCH", "结构解析未覆盖全部原文块")
    refs = {s["id"] for s in data["sections"]}
    if len(refs) != len(data["sections"]):
        raise KnowledgeError("INVALID_SECTION", "章节引用重复")
    by_ref = {s["id"]: s for s in data["sections"]}
    for section in data["sections"]:
        if section.get("parent_id") and section["parent_id"] not in refs:
            raise KnowledgeError("INVALID_SECTION", "章节父节点不存在")
        section["section_id"] = stable_id("structured-section", artifact_id + section["id"])
        ancestors = {section["id"]}
        parent = section.get("parent_id")
        while parent:
            if parent in ancestors or parent not in by_ref:
                raise KnowledgeError("INVALID_SECTION", "章节树存在循环或缺失父节点")
            ancestors.add(parent)
            parent = by_ref[parent].get("parent_id")
    if any(b["section_ref"] not in refs for b in data["blocks"]):
        raise KnowledgeError("INVALID_SECTION", "原文块的章节不存在")
    if any(
        t["section_ref"] not in refs or not set(t["block_refs"]) <= seen for t in data["tables"]
    ):
        raise KnowledgeError("INVALID_TABLE", "表格引用不属于当前解析")
    artifact = DocumentParse(
        id=artifact_id,
        document_version_id=version_id,
        parser_version=parser,
        source_sha256=source_hash,
        data=data,
        created_at=now(),
    )
    session.add(artifact)
    session.flush()
    return artifact


def index_structure(store: KnowledgeStore, artifact: DocumentParse) -> None:
    """Only index a newly imported version; never rewrite existing evidence anchors."""
    session = store.session
    sections = {s["id"]: s for s in artifact.data["sections"]}
    for ordinal, section in enumerate(sections.values()):
        session.add(
            Section(
                id=section["section_id"],
                document_version_id=artifact.document_version_id,
                title=section["title"],
                ordinal=ordinal,
                role=section["role"],
                parser="structured-sections-v1",
            )
        )
    session.flush()
    for block in artifact.data["blocks"]:
        text = block["text"]
        if not text:
            continue
        session.add(
            EvidenceSpan(
                id=stable_id("evidence", f"{block['chunk_id']}:0:{len(text)}"),
                document_version_id=artifact.document_version_id,
                section_id=sections[block["section_ref"]]["section_id"],
                paragraph_id=block["chunk_id"],
                page_index=block["page_index"],
                start_offset=0,
                end_offset=len(text),
                quote=text,
                text_sha256=text_hash(text),
                normalization="identity-v1",
                bbox_list=[block["bbox"]],
            )
        )


def section_entries(
    artifact: DocumentParse, spans: list[EvidenceSpan]
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    blocks = {b["chunk_id"]: b for b in artifact.data["blocks"]}
    sections = {s["id"]: s for s in artifact.data["sections"]}
    entries = []
    metadata = {}
    for span in spans:
        block = blocks.get(span.paragraph_id)
        if not block or block.get("excluded"):
            continue
        section = sections[block["section_ref"]]
        if section.get("excluded") or section["role"] == "references":
            continue
        path = [section["title"]]
        chapter = section
        parent = section.get("parent_id")
        while parent:
            path.insert(0, sections[parent]["title"])
            if sections[parent]["level"] > 0:
                chapter = sections[parent]
            parent = sections[parent].get("parent_id")
        entry = {"id": span.id, "text": span.quote, "section": section["section_id"]}
        entries.append((block["ordinal"], span.start_offset, entry))
        metadata[span.id] = {
            "section_path": path,
            "section_ref": section["id"],
            "section_group": chapter["section_id"],
            "context_group": block["ref"],
            "context_complete": True,
        }
    entries.sort(key=lambda e: (e[0], e[1]))
    for table in artifact.data["tables"]:
        refs = set(table["block_refs"])
        # A detected grid may overlap excluded headers or bibliography material.
        # Keep the full grid in the artifact, but never leak excluded text through
        # source_tables after filtering the evidence input.
        partial = table.get("excluded", False) or any(
            b.get("excluded")
            or sections[b["section_ref"]].get("excluded")
            or sections[b["section_ref"]]["role"] == "references"
            for b in artifact.data["blocks"]
            if b["ref"] in refs
        )
        for span in spans:
            block = blocks.get(span.paragraph_id)
            if span.id in metadata and block and block["ref"] in refs:
                metadata[span.id].update(
                    context_group=table["ref"],
                    context_complete=not partial and table["structure_status"] == "resolved",
                    **({"table": table} if not partial else {}),
                )
    return [e[2] for e in entries], metadata
