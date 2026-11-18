"""Validated section tree stored alongside immutable PDF chunks."""

from copy import deepcopy
from typing import Any

from sqlalchemy import case, select
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
        .order_by(
            DocumentParse.created_at.desc(),
            case((DocumentParse.parser_version.endswith(";structure-v2"), 1), else_=0).desc(),
            DocumentParse.id,
        )
    )


def active_section_rows(session: Session, version_id: str) -> list[Section]:
    """Return the current parse tree without mixing preserved historical trees."""
    artifact = current_structure(session, version_id)
    statement = select(Section).where(Section.document_version_id == version_id)
    if artifact is None:
        return list(session.scalars(statement.order_by(Section.ordinal, Section.id)))
    version = session.get(AttachmentRevision, version_id)
    if version is None or artifact.source_sha256 != version.sha256:
        raise KnowledgeError("PARSE_SOURCE_MISMATCH", "结构解析与文献版本不匹配")
    entries = artifact.data.get("sections", [])
    ids = [item.get("section_id") for item in entries]
    if any(not isinstance(sid, str) for sid in ids) or len(set(ids)) != len(ids):
        raise KnowledgeError("INVALID_SECTION", "当前章节身份缺失或重复")
    rows = {row.id: row for row in session.scalars(statement.where(Section.id.in_(ids)))}
    if set(rows) != set(ids):
        raise KnowledgeError("INVALID_SECTION", "当前章节索引缺失")
    refs = {item.get("id"): item for item in entries}
    for ordinal, item in enumerate(entries):
        row = rows[item["section_id"]]
        parent = refs.get(item.get("parent_id"))
        if (
            row.title != item.get("title", "")
            or row.level != item.get("level", 0)
            or row.role != item.get("role", "other")
            or row.ordinal != item.get("ordinal", ordinal)
            or row.parent_id != (parent.get("section_id") if parent else None)
            or row.excluded != bool(item.get("excluded", False))
        ):
            raise KnowledgeError("INVALID_SECTION", "当前章节属性与结构版本不一致")
    return [rows[sid] for sid in ids]


def _contents_section_ids(artifact: DocumentParse) -> set[str]:
    """Find sections that only represent a printed table-of-contents page.

    Older ``structure-v1`` artifacts were created before TOC blocks were
    marked as material.  They remain readable historical artifacts, but their
    TOC rows must not leak into the current navigation tree.  Re-running the
    deterministic contents marker over a copy is safe: it does not change the
    persisted artifact or any source identity.
    """
    data = artifact.data if isinstance(artifact.data, dict) else {}
    raw_blocks = data.get("blocks", [])
    if not isinstance(raw_blocks, list):
        return set()
    blocks = deepcopy(raw_blocks)
    try:
        from researchgraph.pdf_structure import _mark_contents

        _mark_contents(blocks)
    except Exception:
        # A malformed historical artifact must still be readable.  Existing
        # v2 markers remain useful even when the compatibility probe cannot be
        # applied to all old block fields.
        pass
    content_refs = {
        str(block.get("ref"))
        for block in blocks
        if block.get("contents_entry") or block.get("kind") in {"contents", "toc_entry"}
    }
    if not content_refs:
        return set()
    sections = data.get("sections", [])
    if not isinstance(sections, list):
        return set()
    block_refs_by_section: dict[str, set[str]] = {}
    for block in blocks:
        section_ref = block.get("section_ref")
        block_ref = block.get("ref")
        if isinstance(section_ref, str) and isinstance(block_ref, str):
            block_refs_by_section.setdefault(section_ref, set()).add(block_ref)
    hidden_refs: set[str] = set()
    for item in sections:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        source_refs = {str(value) for value in item.get("block_refs", []) if isinstance(value, str)}
        if not source_refs:
            source_refs = block_refs_by_section.get(item["id"], set())
        if source_refs and source_refs <= content_refs:
            hidden_refs.add(item["id"])
        title = " ".join(str(item.get("title", "")).split()).casefold()
        if title in {"contents", "table of contents", "目录", "目錄"}:
            hidden_refs.add(item["id"])
    if not hidden_refs:
        return set()
    # A v1 parser could make every TOC row a child of the Contents heading;
    # hide those descendants even if their block_refs were omitted.
    changed = True
    while changed:
        changed = False
        for item in sections:
            if not isinstance(item, dict):
                continue
            item_id, parent = item.get("id"), item.get("parent_id")
            if isinstance(item_id, str) and parent in hidden_refs and item_id not in hidden_refs:
                hidden_refs.add(item_id)
                changed = True
    return hidden_refs


def current_navigation_rows(session: Session, version_id: str) -> list[Section]:
    """Return current sections with printed-contents entries removed.

    This is a projection-only compatibility guard for old local parse trees.
    It never deletes Section rows or changes historical model inputs; an
    explicit local refresh can still publish a new ``structure-v2`` artifact.
    """
    rows = active_section_rows(session, version_id)
    artifact = current_structure(session, version_id)
    if artifact is None:
        return rows
    hidden_refs = _contents_section_ids(artifact)
    if not hidden_refs:
        return rows
    entries = {
        str(item.get("id")): item
        for item in artifact.data.get("sections", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    hidden_ids = {
        str(entries[ref].get("section_id"))
        for ref in hidden_refs
        if ref in entries and isinstance(entries[ref].get("section_id"), str)
    }
    return [row for row in rows if row.id not in hidden_ids]


def block_section_refs(block: dict[str, Any], sections: dict[str, dict[str, Any]]) -> set[str]:
    """Validate local heading anchors and retain every containing block scope."""
    primary = block.get("section_ref")
    if not isinstance(primary, str) or primary not in sections:
        raise KnowledgeError("INVALID_SECTION", "原文块的章节身份缺失")
    refs = {primary}
    cursor = 0
    source = block.get("text", "")
    candidates = block.get("heading_candidates", [])
    if not isinstance(source, str) or not isinstance(candidates, list):
        raise KnowledgeError("PARSE_ANCHOR_MISMATCH", "章节标题的原文或候选格式无效")
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise KnowledgeError("PARSE_ANCHOR_MISMATCH", "章节标题候选格式无效")
        start, end, ref = (
            candidate.get("start_offset"),
            candidate.get("end_offset"),
            candidate.get("section_ref"),
        )
        if (
            type(start) is not int
            or type(end) is not int
            or not isinstance(ref, str)
            or ref not in sections
            or not cursor <= start < end <= len(source)
            or not isinstance(candidate.get("text"), str)
            or " ".join(source[start:end].split()) != candidate["text"]
            or candidate["text"] != sections[ref].get("title")
            or type(candidate.get("level")) is not int
            or candidate["level"] != sections[ref].get("level")
            or candidate.get("role") != sections[ref].get("role")
        ):
            raise KnowledgeError("PARSE_ANCHOR_MISMATCH", "章节标题的原始字符范围或引用不一致")
        refs.add(ref)
        cursor = end
    return refs


def source_block_boundary(
    session: Session, version_id: str, spans: list[EvidenceSpan], section_id: str | None = None
) -> dict[str, Any] | None:
    """Describe shared complete source blocks without claiming exact section spans."""
    artifact = current_structure(session, version_id)
    if artifact is None:
        return None
    sections = {row.id: row for row in active_section_rows(session, version_id)}
    # Historical section requests preserve their original frozen input identity.
    if section_id is not None and section_id not in sections:
        return None
    selected = {span.paragraph_id for span in spans}
    refs = {str(item["id"]): item for item in artifact.data.get("sections", [])}
    shared = [
        block["chunk_id"]
        for block in artifact.data.get("blocks", [])
        if block.get("chunk_id") in selected and len(block_section_refs(block, refs)) > 1
    ]
    if not shared:
        return None
    requested = sections.get(section_id) if section_id else None
    return {
        "policy": "whole_original_blocks",
        "requested_section_id": section_id,
        "requested_heading": requested.title if requested else None,
        "shared_chunk_ids": shared,
        "note": "原始证据按完整文字块保留；这些块跨越多个小节，可能包含相邻小节内容。"
        "所选标题仅用于定位，不代表整块文字均属于该小节。请依据块内实际标题区分，"
        "无法区分时保留信息不足，不扩大结论范围。",
    }


def section_model_spans(session: Session, section: Section) -> list[EvidenceSpan]:
    """Never send a mixed readable/excluded block as a selected-section context."""
    spans = section_spans(session, section)
    boundary = source_block_boundary(session, section.document_version_id, spans, section.id)
    if boundary is None:
        return spans
    shared = set(boundary["shared_chunk_ids"])
    return [
        span for span in spans if span.paragraph_id not in shared or span_is_readable(session, span)
    ]


def section_spans(session: Session, section: Section) -> list[EvidenceSpan]:
    """Map current sections to immutable spans; historical section IDs stay readable.

    A new parse owns new Section rows, while the original Span section identity
    continues to identify the source of historical model responses.
    """
    artifact = current_structure(session, section.document_version_id)
    current = (
        {item.get("section_id"): item for item in artifact.data.get("sections", [])}
        if artifact
        else {}
    )
    if artifact is None or section.id not in current:
        historical = list(
            session.scalars(
                select(EvidenceSpan)
                .where(
                    EvidenceSpan.document_version_id == section.document_version_id,
                    EvidenceSpan.section_id == section.id,
                )
                .order_by(
                    EvidenceSpan.page_index, EvidenceSpan.paragraph_id, EvidenceSpan.start_offset
                )
            )
        )
        if artifact is not None:
            # Preserve historical ownership and ordering, while still rejecting
            # changed source bytes/anchors after a newer tree has been added.
            by_original: dict[str, list[EvidenceSpan]] = {}
            for span in historical:
                by_original.setdefault(span.paragraph_id, []).append(span)
            for chunk_id, original_spans in by_original.items():
                chunk = session.get(Chunk, chunk_id)
                cursor = 0
                for span in original_spans:
                    if (
                        chunk is None
                        or chunk.revision_id != section.document_version_id
                        or span.start_offset != cursor
                        or span.end_offset <= cursor
                        or span.end_offset > len(chunk.text)
                        or span.quote != chunk.text[span.start_offset : span.end_offset]
                        or span.text_sha256 != text_hash(span.quote)
                        or span.page_index != chunk.page_index
                        or span.normalization != "identity-v1"
                        or span.bbox_list != [chunk.bbox]
                    ):
                        raise KnowledgeError(
                            "PARSE_ANCHOR_MISMATCH", "历史章节原文定位或哈希不一致"
                        )
                    cursor = span.end_offset
                if chunk is None or cursor != len(chunk.text):
                    raise KnowledgeError("PARSE_ANCHOR_MISMATCH", "历史章节原文未完整覆盖文字块")
        return historical
    # Validate the parse identity even for a section which has no text blocks.
    active_section_rows(session, section.document_version_id)
    ref = current[section.id].get("id")
    refs = {str(item["id"]): item for item in current.values()}
    blocks = []
    for block in artifact.data.get("blocks", []):
        block_refs = block_section_refs(block, refs)
        if ref in block_refs:
            blocks.append(block)
    chunk_ids = [block.get("chunk_id") for block in blocks]
    if len(set(chunk_ids)) != len(chunk_ids) or any(not isinstance(cid, str) for cid in chunk_ids):
        raise KnowledgeError("PARSE_ANCHOR_MISMATCH", "当前章节原文块身份缺失或重复")
    chunks = {
        row.id: row
        for row in session.scalars(
            select(Chunk).where(
                Chunk.revision_id == section.document_version_id, Chunk.id.in_(chunk_ids)
            )
        )
    }
    by_chunk: dict[str, list[EvidenceSpan]] = {cid: [] for cid in chunk_ids}
    for span in session.scalars(
        select(EvidenceSpan)
        .where(
            EvidenceSpan.document_version_id == section.document_version_id,
            EvidenceSpan.paragraph_id.in_(chunk_ids),
        )
        .order_by(EvidenceSpan.start_offset, EvidenceSpan.end_offset, EvidenceSpan.id)
    ):
        by_chunk[span.paragraph_id].append(span)
    out = []
    for block in blocks:
        chunk = chunks.get(block["chunk_id"])
        if (
            chunk is None
            or chunk.text != block.get("text")
            or chunk.bbox != block.get("bbox")
            or chunk.page_index != block.get("page_index")
            or chunk.block_index != block.get("block_index")
        ):
            raise KnowledgeError("PARSE_ANCHOR_MISMATCH", "当前章节与原始文字块不一致")
        cursor = 0
        for span in by_chunk[chunk.id]:
            original_section = session.get(Section, span.section_id)
            if (
                span.start_offset != cursor
                or span.end_offset <= cursor
                or span.end_offset > len(chunk.text)
                or span.quote != chunk.text[span.start_offset : span.end_offset]
                or span.text_sha256 != text_hash(span.quote)
                or span.page_index != chunk.page_index
                or span.normalization != "identity-v1"
                or span.bbox_list != [chunk.bbox]
                or original_section is None
                or original_section.document_version_id != section.document_version_id
            ):
                raise KnowledgeError("PARSE_ANCHOR_MISMATCH", "当前章节原文定位或哈希不一致")
            cursor = span.end_offset
            out.append(span)
        if cursor != len(chunk.text):
            raise KnowledgeError("PARSE_ANCHOR_MISMATCH", "当前章节原文片段未完整覆盖文字块")
    return out


def span_is_readable(session: Session, span: EvidenceSpan) -> bool:
    """Check current local classification without changing frozen Span identity."""
    artifact = current_structure(session, span.document_version_id)
    if artifact is None:
        section = session.get(Section, span.section_id)
        return bool(section and not section.excluded and section.role != "references")
    sections = {row.id: row for row in active_section_rows(session, span.document_version_id)}
    refs = {item.get("id"): item.get("section_id") for item in artifact.data.get("sections", [])}
    block = next(
        (
            item
            for item in artifact.data.get("blocks", [])
            if item.get("chunk_id") == span.paragraph_id
        ),
        None,
    )
    if block is None or block.get("excluded"):
        return False
    entries = {str(item["id"]): item for item in artifact.data.get("sections", [])}
    containing = [sections.get(refs.get(ref, "")) for ref in block_section_refs(block, entries)]
    if any(
        not section or section.excluded or section.role == "references" for section in containing
    ):
        return False
    section = next((item for item in containing if item is not None), None)
    return bool(section and any(item.id == span.id for item in section_spans(session, section)))


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
        block_section_refs(block, refs)
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
