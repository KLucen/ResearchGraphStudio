"""Freeze complete, already parsed paper text without rereading or uploading PDFs."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.core import KnowledgeError, digest, text_hash
from researchgraph.model_document_models import LlmDocumentParse, LlmDocumentSegment
from researchgraph.model_document_overview import model_document_paper
from researchgraph.models import AttachmentRevision, Paper
from researchgraph.reading_projection import build_reading_document


def build_knowledge_sources(
    db: Session, paper_id: str, source_kind: str, source_version_id: str
) -> dict[str, Any]:
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise KnowledgeError("KNOWLEDGE_SOURCE_MISSING", "论文已不存在，不能构建知识图谱")
    sources: list[dict[str, Any]] = []
    warnings: list[str] = []
    if source_kind == "local_revision":
        revision = db.get(AttachmentRevision, source_version_id)
        if revision is None or revision.paper_id != paper_id:
            raise KnowledgeError("KNOWLEDGE_SOURCE_MISMATCH", "本地解析版本与论文不匹配")
        view = build_reading_document(db, paper_id, source_version_id, persist=False)
        sections = {section.section_id: section for section in view.sections}
        for unit in view.units:
            section = sections.get(unit.section_id)
            if (
                unit.kind == "heading"
                or unit.material_type in {"reference", "running", "contents", "unresolved"}
                or (section and section.role in {"references", "reference"})
                or not unit.text.strip()
            ):
                continue
            sources.append(
                {
                    "text": unit.text,
                    "kind": unit.material_type or unit.kind,
                    "chapter_ref": unit.section_id,
                    "chapter_title": section.title if section else "",
                    "page_start": unit.page_start,
                    "page_end": unit.page_end,
                    "origin": {
                        "unit_id": unit.id,
                        "source_hash": unit.source_hash,
                        "projection_version": view.projection_version,
                        "sources": [source.model_dump() for source in unit.sources],
                        "confidence": unit.confidence,
                        "formula_status": unit.formula_status,
                    },
                }
            )
        warnings.extend(view.warnings)
        source_identity = {
            "revision_sha256": revision.sha256,
            "parser_version": revision.parser_version,
            "projection_hash": view.projection_hash,
        }
    elif source_kind == "model_parse":
        parse = db.get(LlmDocumentParse, source_version_id)
        owner = model_document_paper(db, parse) if parse else None
        if parse is None or owner is None or owner.id != paper_id or parse.status != "succeeded":
            raise KnowledgeError("KNOWLEDGE_SOURCE_MISMATCH", "模型解析版本尚未成功或与论文不匹配")
        segments = db.scalars(
            select(LlmDocumentSegment)
            .where(LlmDocumentSegment.parse_id == parse.id)
            .order_by(
                LlmDocumentSegment.chapter_order,
                LlmDocumentSegment.ordinal,
                LlmDocumentSegment.id,
            )
        ).all()
        excluded_level: int | None = None
        last_chapter: str | None = None
        for segment in segments:
            if segment.chapter_ref != last_chapter:
                last_chapter = segment.chapter_ref
                if excluded_level is not None and segment.chapter_level <= excluded_level:
                    excluded_level = None
                title = re.sub(r"^\s*(?:\d+[.)]?\s*)?", "", segment.chapter_title).strip()
                if re.fullmatch(r"references?|bibliography|参考文献|參考文獻", title, re.I):
                    excluded_level = segment.chapter_level
            if excluded_level is not None:
                continue
            text = segment.raw_table_text or segment.text or segment.latex or segment.mathml
            if not text or not text.strip():
                warnings.append(f"模型材料 {segment.id} 没有可引用文本，未猜测图片内容")
                continue
            sources.append(
                {
                    "text": text,
                    "kind": segment.kind,
                    "chapter_ref": segment.chapter_ref,
                    "chapter_title": segment.chapter_title,
                    "page_start": None,
                    "page_end": None,
                    "origin": {
                        "segment_id": segment.id,
                        "parse_id": parse.id,
                        "locator": segment.locator,
                        "status": segment.status,
                        "warnings": segment.warnings,
                        "content_hash": digest(
                            {
                                "text": segment.text,
                                "latex": segment.latex,
                                "mathml": segment.mathml,
                                "raw_table_text": segment.raw_table_text,
                                "table_data": segment.table_data,
                            }
                        ),
                    },
                }
            )
        warnings.extend(parse.warnings or [])
        warnings.append("来源为已保存的模型解析；引文匹配不代表已核验原 PDF 的科学含义")
        source_identity = {"parse_version": parse.parse_version}
    else:
        raise KnowledgeError("KNOWLEDGE_SOURCE_KIND_INVALID", "请选择本地解析或模型解析内容")
    if not sources:
        raise KnowledgeError("KNOWLEDGE_SOURCE_EMPTY", "所选解析没有可引用的完整正文材料")
    for index, source in enumerate(sources, 1):
        source["ref"] = f"s{index}"
        source["text_hash"] = text_hash(source["text"])
    manifest: dict[str, Any] = {
        "manifest_version": "knowledge-sources-1",
        "paper_id": paper.id,
        "project_id": paper.project_id,
        "paper_title": paper.title,
        "source_kind": source_kind,
        "source_id": source_version_id,
        "source_identity": source_identity,
        "sources": sources,
        "warnings": list(dict.fromkeys(warnings)),
    }
    manifest["source_fingerprint"] = digest(manifest)
    return manifest


def revalidate_knowledge_sources(db: Session, manifest: dict[str, Any]) -> None:
    current = build_knowledge_sources(
        db, manifest["paper_id"], manifest["source_kind"], manifest["source_id"]
    )
    if current != manifest:
        raise KnowledgeError("KNOWLEDGE_SOURCE_CHANGED", "所选解析内容已变化，请重新构建知识图谱")
