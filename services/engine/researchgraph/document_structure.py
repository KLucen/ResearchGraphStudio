"""Validated section tree stored alongside immutable PDF chunks."""

from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.core import KnowledgeError, stable_id, text_hash
from researchgraph.models import AttachmentRevision, Chunk, EvidenceSpan, Section, now
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
    session: Session, version_id: str, source_hash: str, structure: dict[str, Any]
) -> DocumentParse:
    version = session.get(AttachmentRevision, version_id)
    if not version or version.sha256 != source_hash or structure.get("schema_version") != SCHEMA:
        raise KnowledgeError("PARSE_SOURCE_MISMATCH", "结构解析与文献版本不匹配")
    parser = str(structure.get("parser_version", "unknown"))
    artifact_id = stable_id("document-parse", version_id + ":" + parser)
    existing = session.get(DocumentParse, artifact_id)
    if existing:
        return existing
    blocks = structure.get("blocks", [])
    chunks = {
        (c.page_index, c.block_index): c
        for c in session.scalars(select(Chunk).where(Chunk.revision_id == version_id))
    }
    refs = {str(item.get("id")): item for item in structure.get("sections", [])}
    if len(refs) != len(structure.get("sections", [])):
        raise KnowledgeError("INVALID_SECTION", "章节引用重复")
    data = deepcopy(structure)
    section_ids: dict[str, str] = {}
    for item in data.get("sections", []):
        ref = str(item["id"])
        section_ids[ref] = stable_id("structured-section", artifact_id + ref)
    for item in data.get("sections", []):
        parent = item.get("parent_id")
        if parent and parent not in section_ids:
            raise KnowledgeError("INVALID_SECTION", "章节父节点不存在")
        item["section_id"] = section_ids[str(item["id"])]
    blocks = data.get("blocks", [])
    seen = set()
    for item in data.get("sections", []):
        ancestors = {str(item["id"])}
        parent = item.get("parent_id")
        while parent:
            if parent in ancestors or parent not in refs:
                raise KnowledgeError("INVALID_SECTION", "章节树存在循环或缺失父节点")
            ancestors.add(parent)
            parent = refs[parent].get("parent_id")
    for block in blocks:
        key = (int(block["page_index"]), int(block["block_index"]))
        chunk = chunks.get(key)
        if key in seen or not chunk or chunk.text != block["text"] or chunk.bbox != block["bbox"]:
            raise KnowledgeError("PARSE_ANCHOR_MISMATCH", "结构文本与 PDF 原文块不一致")
        seen.add(key)
        block["chunk_id"] = chunk.id
        if block.get("section_ref") not in section_ids:
            raise KnowledgeError("INVALID_SECTION", "原文块的章节不存在")
    if len(blocks) != len(chunks):
        raise KnowledgeError("PARSE_ANCHOR_MISMATCH", "结构解析未覆盖全部原文块")
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
    index_structure(session, artifact)
    return artifact


def index_structure(session: Session, artifact: DocumentParse) -> None:
    existing = {
        s.id
        for s in session.scalars(
            select(Section).where(Section.document_version_id == artifact.document_version_id)
        )
    }
    sections = {str(s["id"]): s for s in artifact.data.get("sections", [])}
    for ordinal, item in enumerate(artifact.data.get("sections", [])):
        sid = item["section_id"]
        if sid in existing:
            continue
        parent = sections.get(str(item.get("parent_id"))) if item.get("parent_id") else None
        session.add(
            Section(
                id=sid,
                document_version_id=artifact.document_version_id,
                title=str(item.get("title", "")),
                ordinal=int(item.get("ordinal", ordinal)),
                role=str(item.get("role", "other")),
                parser="structured-sections-v1",
                parent_id=parent.get("section_id") if parent else None,
                level=int(item.get("level", 0)),
                start_page=int(item.get("start_page", 0)),
                end_page=int(item.get("end_page", item.get("start_page", 0))),
                excluded=bool(item.get("excluded", False)),
            )
        )
    session.flush()
    for block in artifact.data.get("blocks", []):
        text = block.get("text", "")
        if not text:
            continue
        eid = stable_id("span", f"{block['chunk_id']}:0:{len(text)}")
        if session.get(EvidenceSpan, eid) is None:
            session.add(
                EvidenceSpan(
                    id=eid,
                    document_version_id=artifact.document_version_id,
                    section_id=sections[str(block["section_ref"])]["section_id"],
                    paragraph_id=block["chunk_id"],
                    page_index=int(block["page_index"]),
                    start_offset=0,
                    end_offset=len(text),
                    quote=text,
                    text_sha256=text_hash(text),
                    normalization="identity-v1",
                    bbox_list=[block["bbox"]],
                )
            )
    session.flush()


def section_entries(artifact: DocumentParse) -> list[dict[str, Any]]:
    sections = {str(s["id"]): s for s in artifact.data.get("sections", [])}
    out = []
    for block in artifact.data.get("blocks", []):
        if block.get("excluded"):
            continue
        section = sections.get(str(block.get("section_ref")))
        if not section or section.get("excluded") or section.get("role") == "references":
            continue
        out.append(
            {
                "id": block.get("chunk_id"),
                "text": block.get("text", ""),
                "section": section.get("section_id"),
            }
        )
    return out
