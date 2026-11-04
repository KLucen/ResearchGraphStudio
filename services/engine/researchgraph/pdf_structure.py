"""Deterministic PDF layout sidecar; original blocks and coordinates remain immutable.

The returned local references are scoped to this parse artifact. They are not database IDs.
Structure recovery is conservative: no OCR, scientific interpretation, or invented cells.
"""

import math
import re
from collections import Counter, defaultdict
from typing import Any

SCHEMA_VERSION = "pdf-structure-1"
NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)(?:[.)]?\s+)(\S.*)$")
APPENDIX = re.compile(r"^(?:appendi(?:x|ces)\b|supplement(?:ary)?\b|附录|附錄)", re.I)
LETTERED = re.compile(r"^([A-Z](?:\.\d+)*)(?:[.)]?\s+)(\S.*)$")
ROLES = {
    "abstract": r"abstract|摘要",
    "introduction": r"introduction|引言|绪论|緒論",
    "method": r"methods?|methodology|materials?\s+and\s+methods?|方法|研究方法|材料与方法",
    "experiment": r"experiments?|experimental\s+(?:setup|settings?|results?)|实验|实验设置",
    "result": r"results?|results?\s+and\s+discussion|结果|结果与讨论",
    "discussion": r"discussion|discussions|讨论",
    "conclusion": r"conclusions?|conclusions?\s+and\s+(?:future\s+work|discussion)|结论|结语",
    "references": r"references?|bibliography|literature\s+cited|参考文献|參考文獻",
    "other": r"background|related\s+work|acknowledge?ments?|limitations?|附注|致谢",
}


def _normalized(text: str) -> str:
    return " ".join(text.split()).strip().casefold()


def _rect(value: Any) -> list[float]:
    return [float(v) for v in value]


def _overlap(a: list[float], b: list[float]) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def _page_blocks(page: Any) -> list[dict[str, Any]]:
    raw = [b for b in page.get_text("blocks", sort=True) if b[6] == 0 and b[4].strip()]
    rich = [b for b in page.get_text("dict", sort=True)["blocks"] if b.get("type") == 0]
    blocks = []
    for index, block in enumerate(raw):
        bbox = _rect(block[:4])
        matching: dict[str, Any] = max(
            rich, key=lambda b: _overlap(bbox, list(b["bbox"])), default={}
        )
        lines = []
        if matching and _overlap(bbox, list(matching["bbox"])):
            for line in matching.get("lines", []):
                spans = [
                    {
                        "text": s["text"],
                        "font": s["font"],
                        "size": round(float(s["size"]), 3),
                        "bold": bool(s.get("flags", 0) & 16),
                        "bbox": _rect(s["bbox"]),
                    }
                    for s in line.get("spans", [])
                ]
                lines.append(
                    {
                        "text": "".join(s["text"] for s in spans),
                        "bbox": _rect(line["bbox"]),
                        "spans": spans,
                    }
                )
        blocks.append(
            {
                "ref": f"p{page.number}:b{index}",
                "page_index": page.number,
                "page_label": page.get_label(),
                "block_index": index,
                "text": block[4],
                "bbox": bbox,
                "kind": "paragraph",
                "section_ref": "s0",
                "excluded": False,
                "lines": lines,
            }
        )
    return blocks


def _reading_order(blocks: list[dict[str, Any]], width: float) -> list[dict[str, Any]]:
    """Read each column completely, split into vertical bands by spanning material."""
    middle = width / 2
    left = [b for b in blocks if b["bbox"][2] <= middle + 12]
    right = [b for b in blocks if b["bbox"][0] >= middle - 12]
    # Require repeated starts on both sides; an isolated right-aligned label is no column.
    if len(left) < 2 or len(right) < 2:
        return sorted(blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))
    spanning = [b for b in blocks if b not in left and b not in right]
    pending = list(blocks)
    result = []

    def band(items: list[dict[str, Any]]) -> None:
        result.extend(
            sorted(
                items,
                key=lambda b: (
                    b["bbox"][0] >= middle - 12,
                    b["bbox"][1],
                    b["bbox"][0],
                ),
            )
        )

    for boundary in sorted(spanning, key=lambda b: (b["bbox"][1], b["bbox"][0])):
        before = [b for b in pending if b != boundary and b["bbox"][3] <= boundary["bbox"][1]]
        band(before)
        pending = [b for b in pending if b not in before and b != boundary]
        result.append(boundary)
    band(pending)
    return result


def _exclude_running_material(pages: list[list[dict[str, Any]]], heights: list[float]) -> None:
    repeats: dict[tuple[str, str], set[int]] = defaultdict(set)
    keys: dict[str, tuple[str, str]] = {}
    for page, blocks in enumerate(pages):
        for block in blocks:
            bbox = block["bbox"]
            zone = "header" if bbox[3] < 65 else "footer" if bbox[1] > heights[page] - 60 else ""
            text = _normalized(block["text"])
            if zone and len(text) < 180:
                key = (zone, re.sub(r"\d+", "#", text))
                keys[block["ref"]] = key
                repeats[key].add(page)
            if zone and re.fullmatch(r"(?:page\s*)?\d+(?:\s*(?:of|/)\s*\d+)?", text):
                block.update(kind=zone, excluded=True)
    threshold = max(2, math.ceil(len(pages) * 0.6))
    for blocks in pages:
        for block in blocks:
            candidate_key = keys.get(block["ref"])
            if candidate_key and len(repeats[candidate_key]) >= threshold:
                block.update(kind=candidate_key[0], excluded=True)


def _body_size(blocks: list[dict[str, Any]]) -> float:
    sizes: Counter[float] = Counter()
    for block in blocks:
        if block["excluded"] or block["kind"] == "table":
            continue
        leading = [line["text"].strip() for line in block["lines"][:2]]
        if leading:
            title = " ".join(leading) if re.fullmatch(r"[\d.]+[.)]?", leading[0]) else leading[0]
            number = NUMBERED.match(title)
            # A long, small-font bibliography must not redefine the main text
            # size and turn every ordinary body paragraph into a heading.
            if _role(number[2] if number else title) == "references":
                break
        for line in block["lines"]:
            for span in line["spans"]:
                sizes[round(span["size"] * 2) / 2] += len(span["text"].strip())
    return sizes.most_common(1)[0][0] if sizes else 11.0


def _role(text: str) -> str:
    if APPENDIX.match(text):
        return "appendix"
    for role, pattern in ROLES.items():
        if re.fullmatch(pattern + r"\s*[:.]?", text, re.I):
            return role
    return "other"


def _typography(lines: list[dict[str, Any]]) -> tuple[float, float]:
    """Measure the main text, so an inline symbol cannot promote a whole paragraph."""
    spans = [s for line in lines for s in line["spans"] if s["text"].strip()]
    total = sum(len(s["text"].strip()) for s in spans)
    if not total:
        return 0.0, 0.0
    weights: Counter[float] = Counter()
    for span in spans:
        weights[round(span["size"] * 2) / 2] += len(span["text"].strip())
    size = weights.most_common(1)[0][0]
    bold = sum(len(s["text"].strip()) for s in spans if s["bold"]) / total
    return size, bold


def _heading_lines(block: dict[str, Any], body_size: float) -> list[dict[str, Any]]:
    """A heading and its following paragraph may share one immutable PDF block."""
    lines = [line for line in block["lines"] if line["text"].strip()]
    if not lines:
        return []
    first = lines[0]
    selected = [first]
    first_size, first_bold = _typography(selected)
    for line in lines[1:3]:
        text = " ".join(item["text"].strip() for item in selected)
        number = NUMBERED.match(text)
        title = number[2] if number else text
        # Named headings are complete even when the next body line happens to
        # use the same font. This is essential for merged References blocks.
        if _role(title) != "other" or re.fullmatch(ROLES["other"], title, re.I):
            break
        size, bold = _typography([line])
        same_style = abs(size - first_size) <= 0.5 and (
            first_bold >= 0.85
            and bold >= 0.85
            or first_size > body_size + 0.75
            and size > body_size + 0.75
        )
        numbered_prefix = bool(re.fullmatch(r"(?:\d+(?:\.\d+)*|[A-Z](?:\.\d+)*)[.)]?", text))
        if not same_style and not numbered_prefix:
            break
        joined = text + " " + line["text"].strip()
        if len(joined) > 160 or len(joined.split()) > 18:
            break
        # A detached number is only joined to a typographically plausible title,
        # not to an ordinary body sentence or numbered bibliography item.
        if numbered_prefix and not same_style and _role(line["text"].strip()) == "other":
            break
        selected.append(line)
    return selected


def _heading(
    block: dict[str, Any], body_size: float, bookmarks: dict[tuple[int, str], int]
) -> tuple[int, str] | None:
    lines = _heading_lines(block, body_size)
    if block["kind"] == "table" and lines:
        leading_bbox = lines[0]["bbox"]
        area = max(1.0, (leading_bbox[2] - leading_bbox[0]) * (leading_bbox[3] - leading_bbox[1]))
        if any(
            _overlap(leading_bbox, region) >= area * 0.5
            for region in block.get("table_regions", [block["bbox"]])
        ):
            return None
    text = " ".join(" ".join(line["text"].split()) for line in lines)
    if not text:
        text = " ".join(block["text"].split())
    if not text or len(text) > 160 or len(text.split()) > 18:
        return None
    if re.fullmatch(r"(?:\d+(?:\.\d+)*|[A-Z](?:\.\d+)*)[.)]?", text):
        return None
    size, bold_share = _typography(lines)
    bold = bold_share >= 0.85

    def accept(level: int, role: str) -> tuple[int, str]:
        block["heading_text"], block["heading_size"] = text, size
        return level, role

    bookmark = bookmarks.get((block["page_index"], _normalized(text)))
    if bookmark:
        return accept(bookmark, _role(re.sub(r"^[\d.]+\s*", "", text)))
    number = NUMBERED.match(text)
    letter = LETTERED.match(text)
    title = number[2] if number else letter[2] if letter else text
    role = _role(title)
    if APPENDIX.match(text) and not re.search(r"[.;!?。；]$", text):
        return accept(1, "appendix")
    if role != "other" or re.fullmatch(ROLES["other"], title, re.I):
        return accept(number[1].count(".") + 1 if number else 1, role)
    # Reject quantities, ordinary numbered sentences and bibliography entries.
    if re.search(r"\b(?:19|20)\d{2}\b", text) or re.search(r"[.;!?。；]$", text):
        return None
    if number and (bold and size >= body_size - 0.15 or size > body_size + 0.5):
        if re.match(r"^(?:mg|kg|mm|cm|nm|ml|ms|hz|kpa|mpa|%)(?:\s|$)", title, re.I):
            return None
        return accept(number[1].count(".") + 1, role)
    if letter and (bold and size >= body_size - 0.15 or size > body_size + 0.5):
        return accept(letter[1].count(".") + 1, "appendix")
    if size > body_size + 1 or bold and size >= body_size:
        if len(text.split()) <= 14 and not re.search(r"[,;=]", text):
            # Preserve the front-page paper title as metadata, not a containing chapter.
            if block["page_index"] == 0 and block["bbox"][1] < 300 and size > body_size * 1.5:
                block["kind"] = "document_title"
                return None
            return accept(1, role)
    return None


def _sections(blocks: list[dict[str, Any]], document: Any) -> list[dict[str, Any]]:
    bookmarks = {}
    for level, title, page in document.get_toc():
        bookmarks[(page - 1, _normalized(title))] = level
    sections: list[dict[str, Any]] = [
        {
            "id": "s0",
            "ref": "s0",
            "parent_id": None,
            "level": 0,
            "title": "Document",
            "role": "document",
            "start_page": 0,
            "end_page": max(0, len(document) - 1),
            "block_refs": [],
            "excluded": False,
        }
    ]
    stack = [sections[0]]
    body_size = _body_size(blocks)
    headings = {
        block["ref"]: _heading(block, body_size, bookmarks)
        for block in blocks
        if not block["excluded"]
    }
    heading_sizes = sorted(
        {
            block["heading_size"]
            for block in blocks
            if headings.get(block["ref"]) and block["lines"]
        },
        reverse=True,
    )
    reference_level: int | None = None
    for ordinal, block in enumerate(blocks):
        block["ordinal"] = ordinal
        heading = headings.get(block["ref"])
        if heading:
            level, role = heading
            text = block["heading_text"]
            if (
                role == "other"
                and not NUMBERED.match(text)
                and not re.fullmatch(ROLES["other"], text, re.I)
                and (block["page_index"], _normalized(text)) not in bookmarks
            ):
                size = block["heading_size"]
                level = 1 + sum(value > size + 0.5 for value in heading_sizes)
            if reference_level is not None:
                if role == "appendix" or role in {"conclusion", "discussion"}:
                    reference_level = None
                    level = 1
                else:
                    # A bold publication title is not the end of the bibliography.
                    level = max(level, reference_level + 1)
            while len(stack) > 1 and stack[-1]["level"] >= level:
                stack.pop()
            excluded = role == "references" or bool(stack[-1]["excluded"])
            section = {
                "id": f"s{len(sections)}",
                "ref": f"s{len(sections)}",
                "parent_id": stack[-1]["id"],
                "level": level,
                "title": text,
                "role": role,
                "start_page": block["page_index"],
                "end_page": block["page_index"],
                "block_refs": [],
                "excluded": excluded,
            }
            sections.append(section)
            stack.append(section)
            block["kind"] = "heading"
            if role == "references":
                reference_level = level
        current = stack[-1]
        current["block_refs"].append(block["ref"])
        for ancestor in stack:
            ancestor["end_page"] = max(ancestor["end_page"], block["page_index"])
        block["section_ref"] = current["id"]
        block["excluded"] = block["excluded"] or current["excluded"]
    return sections


def _tables(page: Any, blocks: list[dict[str, Any]], warnings: list[str]) -> list[dict[str, Any]]:
    result = []
    try:
        finder = page.find_tables()
        for index, table in enumerate(finder.tables):
            rows = [[cell if cell is not None else "" for cell in row] for row in table.extract()]
            bbox = _rect(table.bbox)
            header = table.header
            regions = [bbox] + [_rect(v) for v in header.cells if v]
            source = [b for b in blocks if any(_overlap(b["bbox"], region) for region in regions)]
            cells = []
            xs = sorted({round(c[v], 3) for c in table.cells if c for v in (0, 2)})
            ys = sorted({round(c[v], 3) for c in table.cells if c for v in (1, 3)})
            seen = set()
            for r, row in enumerate(table.rows):
                for c, cell in enumerate(row.cells):
                    if not cell or tuple(cell) in seen:
                        continue
                    seen.add(tuple(cell))
                    rect = _rect(cell)
                    cells.append(
                        {
                            "row": r,
                            "column": c,
                            "row_span": max(1, sum(rect[1] <= y < rect[3] for y in ys[:-1])),
                            "col_span": max(1, sum(rect[0] <= x < rect[2] for x in xs[:-1])),
                            "bbox": rect,
                            "text": rows[r][c],
                            "block_refs": [b["ref"] for b in source if _overlap(b["bbox"], rect)],
                        }
                    )
            result.append(
                {
                    "ref": f"p{page.number}:t{index}",
                    "page_index": page.number,
                    "bbox": bbox,
                    "section_ref": source[0]["section_ref"] if source else "s0",
                    "block_refs": [b["ref"] for b in source],
                    "excluded": bool(source) and all(b["excluded"] for b in source),
                    "rows": rows,
                    "header": {
                        "names": [v if v is not None else "" for v in header.names],
                        "external": bool(header.external),
                        "cells": [_rect(v) if v else None for v in header.cells],
                    },
                    "cells": cells,
                    "structure_status": "resolved" if rows and cells else "partial",
                    "notes": ["表头与网格由版面推断；不代表数值或科学语义已验证。"],
                }
            )
            for block in source:
                block.setdefault("table_regions", []).extend(regions)
                if block["kind"] == "paragraph":
                    block["kind"] = "table"
    except Exception:
        warnings.append(f"PDF 第 {page.number + 1} 页表格结构解析失败，原始文字与坐标仍保留。")
    return result


def parse_structure(document: Any) -> dict[str, Any]:
    """Recover cross-page sections and detected table grids without altering source text."""
    import pymupdf

    warnings = ["章节与阅读顺序由目录及版面推断；公式、图片与未识别表格未作语义解析。"]
    pages = [_page_blocks(page) for page in document]
    heights = [float(page.rect.height) for page in document]
    _exclude_running_material(pages, heights)
    ordered = []
    for page, blocks in zip(document, pages, strict=True):
        if not blocks:
            warnings.append(f"PDF 第 {page.number + 1} 页无可提取文本，可能需要 OCR。")
        ordered.extend(_reading_order(blocks, float(page.rect.width)))
    tables = []
    for page, blocks in zip(document, pages, strict=True):
        tables.extend(_tables(page, blocks, warnings))
    sections = _sections(ordered, document)
    by_ref = {block["ref"]: block for block in ordered}
    for table in tables:
        members = [by_ref[ref] for ref in table["block_refs"]]
        table["section_ref"] = members[0]["section_ref"] if members else "s0"
        table["excluded"] = bool(members) and all(block["excluded"] for block in members)
    return {
        "schema_version": SCHEMA_VERSION,
        "parser_version": f"pymupdf/{pymupdf.VersionBind};structure-v1",
        "sections": sections,
        "blocks": ordered,
        "tables": tables,
        "warnings": warnings,
    }
