"""Conservative reading order, paragraph joins and folded non-prose materials.

This projection is disposable and independently versioned. Chunk, Section,
EvidenceSpan, existing reading results, and external PDF bytes are immutable.
All displayed source fragments retain their exact offsets, coordinates and hash.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchgraph.core import KnowledgeError, stable_id, text_hash
from researchgraph.document_structure import current_structure
from researchgraph.models import (
    AttachmentRevision,
    Chunk,
    EvidenceSpan,
    Paper,
    PaperSource,
    Section,
    now,
)
from researchgraph.pdf_structure import _reading_order, _typography
from researchgraph.reading_document_models import ReadingDocumentProjection
from researchgraph.reading_projection_contracts import (
    PROJECTION_VERSION,
    DocumentReadingView,
    ReadingDocumentSection,
    ReadingRegion,
    ReadingSource,
    ReadingUnit,
)
from researchgraph.source_files import MAX_BYTES

CAPTION = re.compile(
    r"^(?:(?:fig(?:ure)?|table|plate)\.?\s*\d+[A-Za-z]?|[图圖表]\s*\d+)[.:：]", re.I
)
CAPTION_PREFIX = re.compile(
    r"^(?:(?:fig(?:ure)?|table|plate)\.?\s*\d+[A-Za-z]?|[图圖表]\s*\d+)\s+", re.I
)
NUMBER_LABEL = re.compile(r"^[+−-]?(?:\d+(?:[.,]\d+)?|\.\d+)(?:\s*[%°])?$")
KEYED_LABEL = re.compile(r"^[A-Za-z]\d+\s*[:：]\s*[^.!?;\n]{1,50}$")
TERMINAL = re.compile(r"""[.!?。！？;；:：][\])\}"'’”]*$""")


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _clean(text: str) -> str:
    # Preserve the hyphen itself: removing it would guess whether a technical
    # word was hyphenated. Only layout whitespace is normalized for display.
    return " ".join(re.sub(r"-\s*\n\s*(?=[A-Za-z])", "-", text).split())


def _overlap(first: list[float], second: list[float]) -> float:
    return max(0.0, min(first[2], second[2]) - max(first[0], second[0])) * max(
        0.0, min(first[3], second[3]) - max(first[1], second[1])
    )


def _area(bbox: list[float]) -> float:
    return max(1.0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))


def _scope(
    session: Session, paper_id: str, revision_id: str | None
) -> tuple[AttachmentRevision, list[Chunk], list[Section], dict[str, list[EvidenceSpan]]]:
    if session.get(Paper, paper_id) is None:
        raise KnowledgeError("PAPER_NOT_FOUND", "论文不存在")
    revision = (
        session.get(AttachmentRevision, revision_id)
        if revision_id
        else session.scalar(
            select(AttachmentRevision)
            .where(AttachmentRevision.paper_id == paper_id)
            .order_by(AttachmentRevision.created_at.desc(), AttachmentRevision.id)
        )
    )
    if revision is None or revision.paper_id != paper_id:
        raise KnowledgeError("REVISION_NOT_FOUND", "文献版本不存在或不属于当前论文")
    chunks = list(
        session.scalars(
            select(Chunk)
            .where(Chunk.revision_id == revision.id)
            .order_by(Chunk.page_index, Chunk.block_index)
        )
    )
    sections = list(
        session.scalars(
            select(Section)
            .where(Section.document_version_id == revision.id)
            .order_by(Section.ordinal, Section.id)
        )
    )
    by_chunk: dict[str, list[EvidenceSpan]] = defaultdict(list)
    for span in session.scalars(
        select(EvidenceSpan)
        .where(EvidenceSpan.document_version_id == revision.id)
        .order_by(EvidenceSpan.start_offset, EvidenceSpan.end_offset)
    ):
        by_chunk[span.paragraph_id].append(span)
    known_sections = {section.id for section in sections}
    if set(by_chunk) - {chunk.id for chunk in chunks}:
        raise KnowledgeError("READING_SOURCE_INVALID", "原文索引引用了当前版本以外的文字块")
    for chunk in chunks:
        cursor = 0
        for span in by_chunk[chunk.id]:
            if (
                span.start_offset != cursor
                or span.end_offset <= span.start_offset
                or span.end_offset > len(chunk.text)
                or span.quote != chunk.text[span.start_offset : span.end_offset]
                or span.text_sha256 != text_hash(span.quote)
                or span.page_index != chunk.page_index
                or span.normalization != "identity-v1"
                or span.section_id not in known_sections
            ):
                raise KnowledgeError(
                    "READING_SOURCE_INVALID", "原始块、定位或哈希不一致，请重新解析"
                )
            cursor = span.end_offset
        if cursor != len(chunk.text):
            raise KnowledgeError("READING_SOURCE_INVALID", "原文索引未完整覆盖文字块，请重新解析")
    return revision, chunks, sections, by_chunk


def _layout(
    session: Session,
    revision: AttachmentRevision,
    chunks: list[Chunk],
    spans: dict[str, list[EvidenceSpan]],
) -> dict[str, Any]:
    artifact = current_structure(session, revision.id)
    if artifact:
        if artifact.source_sha256 != revision.sha256:
            raise KnowledgeError("READING_SOURCE_INVALID", "结构解析与当前文献哈希不一致")
        data = deepcopy(artifact.data)
        by_id = {chunk.id: chunk for chunk in chunks}
        seen: set[str] = set()
        for block in data.get("blocks", []):
            chunk = by_id.get(block.get("chunk_id"))
            if (
                not chunk
                or chunk.id in seen
                or chunk.text != block.get("text")
                or chunk.bbox != block.get("bbox")
                or chunk.page_index != block.get("page_index")
                or chunk.block_index != block.get("block_index")
            ):
                raise KnowledgeError("READING_SOURCE_INVALID", "结构文字块与原始定位不一致")
            seen.add(chunk.id)
            block["section_id"] = spans[chunk.id][0].section_id
        if seen != set(by_id):
            raise KnowledgeError("READING_SOURCE_INVALID", "结构解析未覆盖全部原始块")
        return data
    return {
        "blocks": [
            {
                "ref": f"p{chunk.page_index}:b{chunk.block_index}",
                "chunk_id": chunk.id,
                "section_id": spans[chunk.id][0].section_id,
                "page_index": chunk.page_index,
                "block_index": chunk.block_index,
                "text": chunk.text,
                "bbox": chunk.bbox,
                "kind": "paragraph",
                "lines": [],
                "excluded": False,
            }
            for chunk in chunks
        ],
        "tables": [],
        "figures": [],
        "warnings": ["旧解析缺少精细版面信息；可点击本地重新整理，原文与历史数据保持。"],
    }


def _scan_pdf(
    session: Session, revision: AttachmentRevision, data_dir: Path | None
) -> tuple[dict[str, Any] | None, list[str]]:
    """Read only a registered source with exactly the revision's bytes.

    No paths are accepted from the client. The stable in-memory snapshot is
    hashed before MuPDF sees it, and no source or managed file is written.
    """
    import pymupdf

    from researchgraph.pdf_structure import parse_structure

    sources = list(
        session.scalars(
            select(PaperSource)
            .where(
                PaperSource.paper_id == revision.paper_id, PaperSource.revision_id == revision.id
            )
            .order_by(PaperSource.id)
        )
    )
    candidates: list[Path] = []
    for source in sources:
        candidates.append(Path(source.path))
        if source.managed_path:
            path = Path(source.managed_path)
            # Managed paths must stay inside the application data directory.
            if data_dir is not None and path.resolve().is_relative_to(data_dir.resolve()):
                candidates.append(path)
    for path in dict.fromkeys(candidates):
        if not path.is_absolute() or path.suffix.lower() != ".pdf":
            continue
        try:
            with path.open("rb") as stream:
                content = stream.read(MAX_BYTES + 1)
            if len(content) > MAX_BYTES or hashlib.sha256(content).hexdigest() != revision.sha256:
                continue
            with pymupdf.open(stream=content, filetype="pdf") as document:
                if document.needs_pass or document.page_count != revision.page_count:
                    continue
                fresh = parse_structure(document)
            return fresh, []
        except (OSError, ValueError, RuntimeError):
            continue
    return None, [
        "当前版本的原始 PDF 不可用或字节已变化；已按保存的原始块重新整理。"
        "图片区域信息可能不完整，请在 Zotero 中核对原文件后再次本地整理。"
    ]


def _source(
    block: dict[str, Any], start: int, end: int, spans: dict[str, list[EvidenceSpan]]
) -> ReadingSource:
    fragment = block["text"][start:end]
    return ReadingSource(
        chunk_id=block["chunk_id"],
        span_ids=[
            span.id
            for span in spans[block["chunk_id"]]
            if span.start_offset < end and span.end_offset > start
        ],
        page=int(block["page_index"]) + 1,
        start_offset=start,
        end_offset=end,
        text=fragment,
        text_hash=text_hash(fragment),
        bbox=block["bbox"],
    )


def _finish(unit: ReadingUnit) -> ReadingUnit:
    identity = {
        "version": PROJECTION_VERSION,
        "kind": unit.kind,
        "sources": [
            [source.chunk_id, source.start_offset, source.end_offset, source.text_hash]
            for source in unit.sources
        ],
        "regions": [region.model_dump() for region in unit.regions],
    }
    unit.id = stable_id("reading-unit", _hash(identity))
    unit.source_hash = _hash(
        {
            **identity,
            "text": unit.text,
            "material_type": unit.material_type,
            "join_reason": unit.join_reason,
        }
    )
    return unit


def _unit(
    block: dict[str, Any],
    spans: dict[str, list[EvidenceSpan]],
    start: int = 0,
    end: int | None = None,
    *,
    kind: str = "paragraph",
    material_type: str | None = None,
    confidence: str = "high",
    reason: str | None = None,
    solution: str | None = None,
) -> ReadingUnit:
    source = _source(block, start, len(block["text"]) if end is None else end, spans)
    return _finish(
        ReadingUnit(
            id="",
            kind=cast(Any, kind),
            material_type=cast(Any, material_type),
            section_id=block["section_id"],
            text=_clean(source.text),
            page_start=source.page,
            page_end=source.page,
            ordinal=0,
            source_hash="",
            sources=[source],
            regions=[ReadingRegion(page=source.page, bbox=source.bbox)],
            confidence=cast(Any, confidence),
            reason=reason,
            solution=solution,
        )
    )


def _heading_end(block: dict[str, Any]) -> int:
    """Split a mixed heading/body block only at exactly recoverable line ends."""
    lines = block.get("lines", [])
    if not lines:
        return len(block["text"])
    # _heading_lines used the original parser's dominant text size. The stored
    # heading_text is authoritative for how many leading lines were selected.
    title = _clean(str(block.get("heading_text", block["text"])))
    cursor, consumed = 0, []
    for line in lines:
        value = str(line.get("text", ""))
        offset = block["text"].find(value, cursor)
        if offset < cursor:
            return len(block["text"])
        consumed.append(value)
        cursor = int(offset) + len(value)
        if _clean(" ".join(consumed)) == title:
            while cursor < len(block["text"]) and block["text"][cursor].isspace():
                cursor += 1
            return cursor
        if len(_clean(" ".join(consumed))) > len(title):
            break
    return len(block["text"])


def _near_region(block: dict[str, Any], regions: list[dict[str, Any]]) -> bool:
    bbox = block["bbox"]
    return any(
        int(region["page_index"]) == int(block["page_index"])
        and _overlap(
            bbox,
            [
                region["bbox"][0] - 10,
                region["bbox"][1] - 10,
                region["bbox"][2] + 10,
                region["bbox"][3] + 10,
            ],
        )
        / _area(bbox)
        >= 0.5
        for region in regions
    )


def _geometric_caption(block: dict[str, Any], regions: list[dict[str, Any]]) -> bool:
    """Undelimited captions require both geometry and smaller typography.

    'Figure 1 shows ...' is a common narrative sentence. A prefix alone must
    never remove it from the body; uncertain cases remain ordinary prose.
    """
    size, _bold = _typography(block.get("lines", []))
    if size <= 0 or size > 10.5:
        return False
    bbox = block["bbox"]
    for region in regions:
        if int(region["page_index"]) != int(block["page_index"]):
            continue
        figure = region["bbox"]
        horizontal = max(0.0, min(bbox[2], figure[2]) - max(bbox[0], figure[0]))
        width = min(bbox[2] - bbox[0], figure[2] - figure[0])
        below = 0 <= bbox[1] - figure[3] <= 45
        above = 0 <= figure[1] - bbox[3] <= 30
        if width > 0 and horizontal >= width * 0.8 and (below or above):
            return True
    return False


def _classify(
    block: dict[str, Any],
    sections: dict[str, Section],
    tables: list[dict[str, Any]],
    figures: list[dict[str, Any]],
) -> tuple[str, str | None, str, str | None, str | None]:
    text = _clean(block["text"])
    section = sections[block["section_id"]]
    if section.role == "references" or section.excluded:
        return (
            "material",
            "reference",
            "high",
            "参考文献或排除章节，保留原文以备核对。",
            "需要时展开原始材料；不进入全文精读模型输入。",
        )
    if block.get("kind") in {"header", "footer"} or block.get("excluded"):
        return (
            "material",
            "running",
            "high",
            "重复页眉、页脚或页码。",
            "原文与页码保留在材料区，不当作正文段落。",
        )
    if CAPTION.match(text) or (
        CAPTION_PREFIX.match(text) and _geometric_caption(block, [*tables, *figures])
    ):
        return (
            "material",
            "caption",
            "high",
            "按图表编号识别出的图注或表注。",
            "请在原始 PDF 对照图表；本轮只整理原始文字，不分析图表含义。",
        )
    if block.get("kind") == "table" or any(
        block.get("ref") in table.get("block_refs", []) for table in tables
    ):
        return (
            "material",
            "table",
            "high",
            "位于检测到的表格区域。",
            "展开核对原始文字和页码；单元格与数值关系仍需在原始 PDF 中确认。",
        )
    near_figure = _near_region(block, figures)
    short_label = len(text) <= 70 and len(text.split()) <= 8
    numeric = bool(NUMBER_LABEL.fullmatch(text))
    keyed = bool(KEYED_LABEL.fullmatch(text))
    if numeric or keyed or near_figure and short_label and not TERMINAL.search(text):
        return (
            "material",
            "figure_label",
            "suspected",
            "疑似图内数值、坐标轴或图例标签，不能单独解释为正文。",
            "展开保留的原文并到对应 PDF 页查看；若实际是正文，"
            "可反馈版面样例改进规则，系统不会猜补语义。",
        )
    if block.get("kind") in {"heading", "document_title"}:
        return "heading", None, "high", None, None
    return "paragraph", None, "high", None, None


def _line_geometry(block: dict[str, Any], first: bool) -> tuple[list[float], float]:
    lines = [line for line in block.get("lines", []) if str(line.get("text", "")).strip()]
    if lines:
        line = lines[0 if first else -1]
        size, _bold = _typography([line])
        return cast(list[float], line["bbox"]), size or 11.0
    return cast(list[float], block["bbox"]), 11.0


def _continuation(
    previous: ReadingUnit,
    current: ReadingUnit,
    by_chunk: dict[str, dict[str, Any]],
    geometry: dict[int, dict[str, Any]],
    page_bodies: dict[int, list[str]],
) -> str | None:
    if previous.section_id != current.section_id or not previous.text or not current.text:
        return None
    if TERMINAL.search(previous.text):
        return None
    first_word = re.match(r"[\s\"'‘“(\[]*([A-Za-z]+)", current.text)
    if not first_word or not first_word[1][0].islower():
        return None
    left = by_chunk[previous.sources[-1].chunk_id]
    right = by_chunk[current.sources[0].chunk_id]
    if left["chunk_id"] == right["chunk_id"]:
        return None
    last_line, left_size = _line_geometry(left, False)
    first_line, right_size = _line_geometry(right, True)
    if abs(left_size - right_size) > 0.6:
        return None
    lbox, rbox = left["bbox"], right["bbox"]
    lwidth, rwidth = lbox[2] - lbox[0], rbox[2] - rbox[0]
    if lwidth <= 20 or rwidth <= 20:
        return None
    # A nearly full final line plus lowercase continuation is needed. A short
    # final line is generally a deliberate paragraph break even without '.'
    if last_line[2] < lbox[2] - max(8.0, lwidth * 0.12):
        return None
    if first_line[0] > rbox[0] + max(3.0, right_size * 0.35):
        return None
    lpage, rpage = left["page_index"], right["page_index"]
    if lpage == rpage:
        if abs(lbox[0] - rbox[0]) <= max(4.0, left_size * 0.4):
            gap = rbox[1] - lbox[3]
            if -1 <= gap <= left_size * 1.6:
                return "adjacent_block_continuation"
            return None
        width = float(geometry[lpage]["width"])
        if lbox[2] <= width / 2 + 12 and rbox[0] >= width / 2 - 12:
            height = float(geometry[lpage]["height"])
            if (
                geometry[lpage].get("inferred")
                or lbox[3] < height * 0.68
                or rbox[1] > height * 0.25
            ):
                return None
            body = page_bodies[lpage]
            left_column = [cid for cid in body if by_chunk[cid]["bbox"][2] <= width / 2 + 12]
            right_column = [cid for cid in body if by_chunk[cid]["bbox"][0] >= width / 2 - 12]
            if (
                left_column
                and right_column
                and left["chunk_id"] == left_column[-1]
                and right["chunk_id"] == right_column[0]
            ):
                if min(lwidth, rwidth) / max(lwidth, rwidth) >= 0.8:
                    return "column_continuation"
        return None
    if rpage == lpage + 1:
        left_margin = float(lbox[0])
        right_margin = float(rbox[0])
        # The last right column flows into the first left column on the next
        # page. Compare column-relative margins, not their absolute x values.
        if (
            left_margin >= float(geometry[lpage]["width"]) / 2 - 12
            and right_margin < float(geometry[rpage]["width"]) / 2 - 12
        ):
            left_margin -= float(geometry[lpage]["width"]) / 2
        if (
            geometry[lpage].get("inferred")
            or geometry[rpage].get("inferred")
            or lbox[3] < float(geometry[lpage]["height"]) * 0.68
            or rbox[1] > float(geometry[rpage]["height"]) * 0.25
            or abs(left_margin - right_margin) > 18
        ):
            return None
        if any(
            region[1] >= lbox[3] - 3 and region[2] - region[0] >= lwidth * 0.5
            for region in geometry[lpage].get("material_regions", [])
        ) or any(
            region[3] <= rbox[1] + 3 and region[2] - region[0] >= rwidth * 0.5
            for region in geometry[rpage].get("material_regions", [])
        ):
            return None
        if page_bodies[lpage][-1] != left["chunk_id"] or page_bodies[rpage][0] != right["chunk_id"]:
            return None
        if min(lwidth, rwidth) / max(lwidth, rwidth) < 0.8:
            return None
        # For a real two-column page, only its final (right) column can flow to
        # the next page. Body ordering above already enforces that condition.
        return "cross_page_continuation"
    return None


def _assemble(
    paper_id: str,
    revision: AttachmentRevision,
    layout: dict[str, Any],
    sections: list[Section],
    spans: dict[str, list[EvidenceSpan]],
    refreshed_at: str | None,
    extra_warnings: list[str],
) -> DocumentReadingView:
    by_section = {section.id: section for section in sections}
    blocks = layout["blocks"]
    by_chunk = {block["chunk_id"]: block for block in blocks}
    by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for block in blocks:
        by_page[block["page_index"]].append(block)
    geometry = {item["page_index"]: item for item in layout.get("page_geometry", [])}
    for page, items in by_page.items():
        if page not in geometry:
            geometry[page] = {
                "page_index": page,
                "width": max(item["bbox"][2] for item in items)
                + min(item["bbox"][0] for item in items),
                "height": max(item["bbox"][3] for item in items) + 60,
                "inferred": True,
            }
    for page, page_geometry in geometry.items():
        page_geometry["material_regions"] = [
            region["bbox"]
            for region in [*layout.get("tables", []), *layout.get("figures", [])]
            if region["page_index"] == page
        ]
    ordered = [
        block
        for page in sorted(by_page)
        for block in _reading_order(by_page[page], float(geometry[page]["width"]))
    ]
    units: list[ReadingUnit] = []
    tables, figures = layout.get("tables", []), layout.get("figures", [])
    for block in ordered:
        kind, material, confidence, reason, solution = _classify(block, by_section, tables, figures)
        heading_end = _heading_end(block) if kind == "heading" else len(block["text"])
        units.append(
            _unit(
                block,
                spans,
                end=heading_end,
                kind=kind,
                material_type=material,
                confidence=confidence,
                reason=reason,
                solution=solution,
            )
        )
        if heading_end < len(block["text"]) and block["text"][heading_end:].strip():
            units.append(_unit(block, spans, start=heading_end))
    page_bodies: dict[int, list[str]] = defaultdict(list)
    for unit in units:
        if unit.kind == "paragraph":
            for source in unit.sources:
                if source.chunk_id not in page_bodies[source.page - 1]:
                    page_bodies[source.page - 1].append(source.chunk_id)
    merged: list[ReadingUnit] = []
    previous: ReadingUnit | None = None
    # Running headers/footers may occur between two continuous page fragments.
    # Other materials interrupt joining, because adjacency is no longer certain.
    for unit in units:
        join = (
            _continuation(previous, unit, by_chunk, geometry, page_bodies)
            if previous and unit.kind == "paragraph"
            else None
        )
        if join and previous:
            separator = "" if previous.text.endswith("-") else " "
            previous.text += separator + unit.text
            previous.sources.extend(unit.sources)
            previous.regions.extend(unit.regions)
            previous.page_end = unit.page_end
            reasons = (previous.join_reason or "").split("+")
            previous.join_reason = "+".join(
                dict.fromkeys([value for value in reasons if value] + [join])
            )
            _finish(previous)
        else:
            merged.append(unit)
            if unit.kind == "paragraph":
                previous = unit
            elif unit.material_type != "running":
                previous = None
    for figure in figures:
        page = int(figure["page_index"])
        nearest = [unit for unit in merged if unit.page_start <= page + 1 <= unit.page_end]
        section_id = nearest[0].section_id if nearest else sections[0].id if sections else ""
        region = ReadingRegion(page=page + 1, bbox=figure["bbox"])
        merged.append(
            _finish(
                ReadingUnit(
                    id="",
                    kind="material",
                    material_type="figure",
                    section_id=section_id,
                    text="",
                    page_start=page + 1,
                    page_end=page + 1,
                    ordinal=0,
                    source_hash="",
                    sources=[],
                    regions=[region],
                    confidence=figure.get("confidence", "suspected"),
                    reason="检测到嵌入图片区域。"
                    if figure.get("kind") == "image"
                    else "检测到疑似矢量图形区域；也可能是非正文绘制元素。",
                    solution="请在对应 PDF 页查看图片或图表；当前只定位、不分析图像，"
                    "也不将图内文字猜补为正文。扫描页需要另行 OCR。",
                )
            )
        )
    for ordinal, unit in enumerate(merged, start=1):
        unit.ordinal = ordinal
    warnings = list(dict.fromkeys([*layout.get("warnings", []), *extra_warnings]))
    if not layout.get("page_geometry"):
        warnings.append(
            "旧解析未保存页面尺寸，阅读顺序使用原始块坐标估计；本地重新整理可补全版面信息。"
        )
    readable = [unit for unit in merged if unit.kind == "paragraph"]
    if not readable:
        warnings.append(
            "当前版本没有可精读正文；图像或扫描页需要在原始 PDF 中核对，并另行进行 OCR。"
        )
    result = DocumentReadingView(
        paper_id=paper_id,
        document_version_id=revision.id,
        source_hash=revision.sha256,
        projection_hash="",
        sections=[
            ReadingDocumentSection(section_id=s.id, title=s.title, level=s.level, role=s.role)
            for s in sections
        ],
        units=merged,
        warnings=warnings,
        refreshed_at=refreshed_at,
    )
    # Transient local file-availability warnings do not change scientific
    # source identity. Classified units and their source maps do.
    content = result.model_dump(exclude={"projection_hash", "refreshed_at", "warnings"})
    result.projection_hash = _hash(content)
    return result


def build_reading_document(
    session: Session,
    paper_id: str,
    revision_id: str | None,
    refresh: bool = False,
    data_dir: Path | None = None,
) -> DocumentReadingView:
    """Build/validate the local reading layer without making any model request."""
    revision, chunks, sections, spans = _scope(session, paper_id, revision_id)
    layout = _layout(session, revision, chunks, spans)
    row = session.scalar(
        select(ReadingDocumentProjection).where(
            ReadingDocumentProjection.document_version_id == revision.id,
            ReadingDocumentProjection.projection_version == PROJECTION_VERSION,
        )
    )
    if row and not isinstance(row.data, dict):
        raise KnowledgeError("READING_SOURCE_INVALID", "阅读整理缓存损坏，请重新整理")
    saved_scan = row.data.get("scan") if row and row.source_hash == revision.sha256 else None
    if isinstance(saved_scan, dict):
        if row is None or row.data.get("scan_hash") != _hash(saved_scan):
            if not refresh:
                raise KnowledgeError(
                    "READING_SOURCE_INVALID", "图表定位缓存校验失败，请本地重新整理"
                )
            saved_scan = None
    if isinstance(saved_scan, dict):
        for key in ("figures", "tables", "page_geometry"):
            if key in saved_scan:
                layout[key] = deepcopy(saved_scan[key])
    warnings: list[str] = list(row.data.get("scan_warnings", [])) if row else []
    scan = saved_scan if isinstance(saved_scan, dict) else None
    refreshed_at = row.data.get("refreshed_at") if row else None
    if refresh:
        fresh, warnings = _scan_pdf(session, revision, data_dir)
        if fresh:
            # Existing raw text and sections remain authoritative. Only geometry
            # and graphical-region metadata are refreshed from the same bytes.
            scan = {key: fresh.get(key, []) for key in ("figures", "tables", "page_geometry")}
            for key, value in scan.items():
                layout[key] = deepcopy(value)
            refreshed_at = now()
    view = _assemble(paper_id, revision, layout, sections, spans, refreshed_at, warnings)
    if row is None:
        row = ReadingDocumentProjection(
            id=stable_id("reading-document", revision.id + PROJECTION_VERSION),
            document_version_id=revision.id,
            projection_version=PROJECTION_VERSION,
            source_hash=revision.sha256,
            projection_hash=view.projection_hash,
            data={},
            created_at=now(),
            updated_at=now(),
        )
        session.add(row)
    updated_data = {
        "view": view.model_dump(),
        "scan": scan,
        "scan_hash": _hash(scan) if scan else None,
        "scan_warnings": warnings,
        "refreshed_at": refreshed_at,
    }
    if (
        row.source_hash != revision.sha256
        or row.projection_hash != view.projection_hash
        or row.data != updated_data
    ):
        row.source_hash = revision.sha256
        row.projection_hash = view.projection_hash
        row.data = updated_data
        row.updated_at = now()
    session.flush()
    return view
