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
CONTENTS = re.compile(r"^(?:(?:table\s+of\s+)?contents|目录|目錄)\s*[:.]?$", re.I)


def _caps_title(text: str) -> bool:
    """Small capitals often use a smaller, non-bold font than body text."""
    letters = [character for character in text if character.isalpha()]
    return bool(
        3 <= len(letters)
        and len(text.split()) <= 14
        and all(not character.islower() for character in letters)
        and not re.search(r"[=,;!?。；]", text)
    )


def _contents_entry(text: str) -> bool:
    value = " ".join(text.split())
    # A trailing page number alone is not sufficient: require an outline
    # prefix or dot leaders, and at least one alphabetic title character.
    return bool(
        re.search(r"[A-Za-z\u4e00-\u9fff]", value)
        and re.search(r"\s\d{1,3}\s*$", value)
        and (
            NUMBERED.match(value)
            or LETTERED.match(value)
            or re.search(r"(?:\.\s*){3,}|…|·{2,}", value)
        )
    )


def _mark_contents(blocks: list[dict[str, Any]]) -> None:
    """Keep contents text as material, without promoting its entries to chapters."""
    pages: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for block in blocks:
        if not block["excluded"]:
            pages[block["page_index"]].append(block)
    contents_pages: set[int] = set()
    for page_number, page in pages.items():
        entries = []
        for block in page:
            lines = [line for line in block.get("lines", []) if line["text"].strip()]
            flattened = " ".join(block["text"].split())
            if not lines or not _contents_entry(flattened):
                continue
            last = lines[-1]
            # The page label may be a separate PDF "line" on the same
            # baseline. Require its right-aligned position, or dot leaders.
            detached_page = bool(
                len(lines) > 1
                and re.fullmatch(r"\d{1,3}", last["text"].strip())
                and last["bbox"][0] > block["bbox"][0] + 60
                and last["bbox"][3] <= block["bbox"][1] + 40
            )
            if detached_page or re.search(r"(?:\.\s*){3,}|…|·{2,}", flattened):
                entries.append(block)
        titles = [block for block in page if CONTENTS.fullmatch(_normalized(block["text"]))]
        leaders = sum(bool(re.search(r"(?:\.\s*){3,}|…|·{2,}", b["text"])) for b in entries)
        if not entries or not (
            titles or leaders >= 2 or page_number - 1 in contents_pages and len(entries) >= 3
        ):
            continue
        contents_pages.add(page_number)
        for block in page:
            if block in entries or block in titles:
                block["kind"] = "contents"
                block["contents_entry"] = True


def _contents_hints(blocks: list[dict[str, Any]]) -> dict[str, tuple[int, int, str]]:
    """Extract conservative heading hints from printed contents rows.

    Some PDFs render body headings with the same typography as ordinary prose.
    The printed contents page is still a useful, local signal in that case,
    but its rows must never become sections themselves.  We keep only an
    exact normalized title, the outline level, and the approximate printed
    page.  The hint is applied later only to a body block on or after that
    page, and the original block text remains the source of truth.
    """
    hints: dict[str, tuple[int, int, str]] = {}
    row_pattern = re.compile(
        r"^\s*(?P<prefix>(?:\d+(?:\.\d+)*|[A-Z]))[.)]?\s+"
        r"(?P<title>.+?)\s+(?:\.{2,}|…|·{2,}|\s)*?(?P<page>\d{1,3})\s*$",
        re.I,
    )
    for block in blocks:
        if not block.get("contents_entry") or block.get("excluded"):
            continue
        value = " ".join(str(block.get("text", "")).split())
        match = row_pattern.match(value)
        if not match:
            # A detached page number can be represented as a final line in a
            # block while the title itself has no dot leaders.
            lines = [
                " ".join(str(line.get("text", "")).split())
                for line in block.get("lines", [])
                if str(line.get("text", "")).strip()
            ]
            if len(lines) >= 2 and re.fullmatch(r"\d{1,3}", lines[-1]):
                value = " ".join(lines[:-1] + [lines[-1]])
                match = row_pattern.match(value)
        if not match:
            continue
        prefix = match.group("prefix")
        title = " ".join(match.group("title").split())
        if not title:
            continue
        try:
            printed_page = max(1, int(match.group("page")))
        except ValueError:
            continue
        level = prefix.count(".") + 1
        full_title = _normalized(f"{prefix} {title}")
        role = _role(title)
        # Keep the first row for a title. Duplicate contents pages are common
        # in appendices and should not make the parser oscillate levels.
        hints.setdefault(full_title, (level, printed_page - 1, role))
        if prefix.isdigit():
            hints.setdefault(_normalized(f"{prefix}. {title}"), (level, printed_page - 1, role))
    return hints


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
        if numbered_prefix:
            previous_bbox = selected[-1]["bbox"]
            next_bbox = line["bbox"]
            same_row = abs(previous_bbox[1] - next_bbox[1]) <= max(first_size, size) * 0.4
            adjacent = (
                same_row
                and 0 <= next_bbox[0] - previous_bbox[2] <= body_size * 4
                or not same_row
                and abs(next_bbox[0] - previous_bbox[0]) <= body_size
                and 0 <= next_bbox[1] - previous_bbox[3] <= body_size
            )
            if not adjacent:
                break
        # A detached number is only joined to a typographically plausible title,
        # not to an ordinary body sentence or numbered bibliography item.
        if (
            numbered_prefix
            and not same_style
            and _role(line["text"].strip()) == "other"
            and not _caps_title(line["text"].strip())
        ):
            break
        selected.append(line)
    return selected


def _heading(
    block: dict[str, Any],
    body_size: float,
    bookmarks: dict[tuple[int, str], int],
    contents_hints: dict[str, tuple[int, int, str]] | None = None,
) -> tuple[int, str] | None:
    if block.get("contents_entry") or block.get("kind") == "contents":
        return None
    lines = _heading_lines(block, body_size)
    covered_by_table = False
    if block["kind"] == "table" and lines:
        leading_bbox = lines[0]["bbox"]
        area = max(1.0, (leading_bbox[2] - leading_bbox[0]) * (leading_bbox[3] - leading_bbox[1]))
        covered_by_table = any(
            _overlap(leading_bbox, region) >= area * 0.5
            for region in block.get("table_regions", [block["bbox"]])
        )
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

    unnumbered = re.sub(r"^(?:\d+(?:\.\d+)*|[A-Z](?:\.\d+)*)[.)]?\s+", "", text)
    bookmark = bookmarks.get((block["page_index"], _normalized(text))) or bookmarks.get(
        (block["page_index"], _normalized(unnumbered))
    )
    if bookmark:
        return accept(bookmark, "appendix" if LETTERED.match(text) else _role(unnumbered))
    if covered_by_table:
        return None
    number = NUMBERED.match(text)
    letter = LETTERED.match(text)
    title = number[2] if number else letter[2] if letter else text
    role = _role(title)
    # A printed contents row can recover a body heading whose font is
    # indistinguishable from prose.  Require an exact normalized title and a
    # body page at/after the recorded page so contents rows themselves never
    # become chapters.  This is only a navigation hint; source text and
    # offsets remain bound to the original block.
    hint = None
    if contents_hints:
        hint = contents_hints.get(_normalized(text)) or contents_hints.get(
            _normalized(f"{text.split(maxsplit=1)[0]} {title}")
        )
    if hint and block.get("kind") != "contents":
        hint_level, hint_page, hint_role = hint
        if int(block.get("page_index", 0)) >= hint_page:
            return accept(hint_level, hint_role)
    appendix_heading = bool(
        APPENDIX.match(text)
        and (bold and size >= body_size - 0.15 or size > body_size + 0.5 or _caps_title(text))
        and not re.search(r"[.;!?。；]$", text)
    )
    if appendix_heading:
        return accept(1, "appendix")
    if role == "appendix":
        role = "other"
    if (role != "other" or re.fullmatch(ROLES["other"], title, re.I)) and (
        size >= body_size - 0.15 or _caps_title(title)
    ):
        prefix = number[1] if number else letter[1] if letter else ""
        return accept(prefix.count(".") + 1, "appendix" if letter else role)
    # Reject quantities, ordinary numbered sentences and bibliography entries.
    if re.search(r"\b(?:19|20)\d{2}\b", text) or re.search(r"[.;!?。；]$", text):
        return None
    if number and (
        bold
        and size >= body_size - 0.15
        or size > body_size + 0.5
        or _caps_title(title)
        and size >= body_size * 0.72
        and ("." not in number[1] or len(title.split()) > 1)
    ):
        if re.match(r"^(?:mg|kg|mm|cm|nm|ml|ms|hz|kpa|mpa|%)(?:\s|$)", title, re.I):
            return None
        return accept(number[1].count(".") + 1, role)
    if letter and (
        bold
        and size >= body_size - 0.15
        or size > body_size + 0.5
        or _caps_title(title)
        and size >= body_size * 0.72
        and ("." not in letter[1] or len(title.split()) > 1)
    ):
        return accept(letter[1].count(".") + 1, "appendix")
    if size > body_size + 1 or bold and size >= body_size:
        if len(text.split()) <= 14 and not re.search(r"[,;=]", text):
            # Preserve the front-page paper title as metadata, not a containing chapter.
            if block["page_index"] == 0 and block["bbox"][1] < 300 and size > body_size * 1.5:
                block["kind"] = "document_title"
                return None
            return accept(1, role)
    return None


def _heading_candidates(
    block: dict[str, Any],
    body_size: float,
    bookmarks: dict[tuple[int, str], int],
    contents_hints: dict[str, tuple[int, int, str]] | None = None,
) -> list[dict[str, Any]]:
    """Find independently verifiable title lines without splitting immutable blocks.

    A middle-of-block candidate must have an explicit numbered/named/bookmarked
    title. Arbitrary bold phrases in source paragraphs are never scanned as
    unnumbered headings. Every candidate binds an exact original character range.
    """
    if block.get("contents_entry") or block.get("excluded"):
        return []
    lines = block.get("lines", [])
    if not lines:
        heading = _heading(block, body_size, bookmarks, contents_hints)
        if heading is None:
            return []
        start = len(block["text"]) - len(block["text"].lstrip())
        end = len(block["text"].rstrip())
        return [
            {
                "start_offset": start,
                "end_offset": end,
                "text": block["heading_text"],
                "level": heading[0],
                "role": heading[1],
                "size": block.get("heading_size", body_size),
                "bbox": block["bbox"],
            }
        ]
    offsets: list[tuple[int, int] | None] = []
    cursor = 0
    for line in lines:
        value = str(line.get("text", ""))
        start = block["text"].find(value, cursor)
        if not value.strip() or start < cursor:
            offsets.append(None)
            continue
        end = start + len(value)
        offsets.append((start, end))
        cursor = end
    candidates: list[dict[str, Any]] = []
    consumed = -1
    for index, line in enumerate(lines):
        offset = offsets[index]
        if offset is None or offset[0] < consumed:
            continue
        value = " ".join(str(line["text"]).split())
        if index and not (
            NUMBERED.match(value)
            or LETTERED.match(value)
            or re.fullmatch(r"(?:\d+(?:\.\d+)*|[A-Z](?:\.\d+)*)[.)]?", value)
            or _role(value) != "other"
            or (block["page_index"], _normalized(value)) in bookmarks
        ):
            continue
        probe = {
            **block,
            "lines": lines[index:],
            "bbox": line["bbox"],
            "text": block["text"][offset[0] :],
        }
        heading = _heading(probe, body_size, bookmarks, contents_hints)
        if heading is None:
            if index == 0 and probe.get("kind") == "document_title":
                block["kind"] = "document_title"
            continue
        selected = _heading_lines(probe, body_size)
        last = index + len(selected) - 1
        if last >= len(offsets):
            continue
        last_offset = offsets[last]
        if last_offset is None:
            continue
        end = last_offset[1]
        original = block["text"][offset[0] : end]
        if " ".join(original.split()) != probe["heading_text"]:
            continue
        candidates.append(
            {
                "start_offset": offset[0],
                "end_offset": end,
                "text": probe["heading_text"],
                "level": heading[0],
                "role": heading[1],
                "size": probe["heading_size"],
                "bbox": [
                    min(item["bbox"][0] for item in selected),
                    min(item["bbox"][1] for item in selected),
                    max(item["bbox"][2] for item in selected),
                    max(item["bbox"][3] for item in selected),
                ],
            }
        )
        consumed = end
    return candidates


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
    _mark_contents(blocks)
    contents_hints = _contents_hints(blocks)
    for block in blocks:
        block["heading_candidates"] = _heading_candidates(
            block, body_size, bookmarks, contents_hints
        )
    heading_sizes = sorted(
        {
            candidate["size"]
            for block in blocks
            for candidate in block["heading_candidates"]
            if block["lines"]
        },
        reverse=True,
    )
    reference_level: int | None = None
    for ordinal, block in enumerate(blocks):
        block["ordinal"] = ordinal
        initial = stack[-1]
        leading_section = None
        for candidate in block["heading_candidates"]:
            level, role = candidate["level"], candidate["role"]
            text = candidate["text"]
            if (
                role == "other"
                and not NUMBERED.match(text)
                and not LETTERED.match(text)
                and not re.fullmatch(ROLES["other"], text, re.I)
                and (block["page_index"], _normalized(text)) not in bookmarks
            ):
                size = candidate["size"]
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
            candidate["level"] = level
            candidate["section_ref"] = section["id"]
            if leading_section is None:
                leading_section = section
                if not block["text"][: candidate["start_offset"]].strip():
                    block["kind"] = "heading"
                    block["heading_text"] = text
                    block["heading_size"] = candidate["size"]
            if role == "references":
                reference_level = level
        current = (
            leading_section
            if block["kind"] == "heading" and leading_section is not None
            else initial
        )
        current["block_refs"].append(block["ref"])
        current["end_page"] = max(current["end_page"], block["page_index"])
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
            occupied = sum(bool(value.strip()) for row in rows for value in row)
            slots = sum(len(row) for row in rows)
            grid_area = max(1.0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
            distinct_cells = {tuple(cell) for cell in table.cells if cell}
            containing_cell = len(distinct_cells) > 1 and any(
                (cell[2] - cell[0]) * (cell[3] - cell[1]) >= grid_area * 0.95
                for cell in distinct_cells
            )
            # MuPDF can turn figure lines into one page-sized cell containing
            # captions, paragraphs and headings. Such a degenerate grid is not
            # usable table structure; preserve source text/graphics instead.
            if (
                occupied == 0
                or containing_cell
                or occupied == 1
                and (slots > 2 or bbox[3] - bbox[1] > 100)
            ):
                warnings.append(
                    f"PDF 第 {page.number + 1} 页检测到退化表格区域，未将其正文整体标为表格；"
                    "请对照原页确认图表。"
                )
                continue
            header = table.header
            regions = [bbox] + [_rect(v) for v in header.cells if v]
            touching = [b for b in blocks if any(_overlap(b["bbox"], region) for region in regions)]
            source = []
            partial = []
            for block in touching:
                block_bbox = block["bbox"]
                block_area = max(
                    1.0, (block_bbox[2] - block_bbox[0]) * (block_bbox[3] - block_bbox[1])
                )
                coverage = _overlap(block_bbox, bbox)
                if header.external:
                    # External header cells form a separate, non-overlapping
                    # row. Do not count internal cells twice with the grid.
                    coverage += sum(_overlap(block_bbox, region) for region in regions[1:])
                if coverage >= block_area * 0.5:
                    source.append(block)
                else:
                    partial.append(block["ref"])
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
                    "partial_block_refs": partial,
                    "excluded": bool(source) and all(b["excluded"] for b in source),
                    "rows": rows,
                    "header": {
                        "names": [v if v is not None else "" for v in header.names],
                        "external": bool(header.external),
                        "cells": [_rect(v) if v else None for v in header.cells],
                    },
                    "cells": cells,
                    "structure_status": "resolved" if rows and cells else "partial",
                    "notes": ["表头与网格由版面推断；不代表数值或科学语义已验证。"]
                    + (
                        ["部分原文块仅与表格边界相交，已保留原文和定位，未将整块正文视为表格。"]
                        if partial
                        else []
                    ),
                }
            )
            for block in source:
                block.setdefault("table_regions", []).extend(regions)
                if block["kind"] == "paragraph":
                    block["kind"] = "table"
    except Exception:
        warnings.append(f"PDF 第 {page.number + 1} 页表格结构解析失败，原始文字与坐标仍保留。")
    return result


def figure_regions(
    page: Any, tables: list[dict[str, Any]], warnings: list[str]
) -> list[dict[str, Any]]:
    """Locate raster images and vector clusters, without reading their meaning.

    A vector cluster is deliberately only *suspected* graphical material. Table
    grids already recovered above are excluded, and no pixels or image bytes
    are copied into the database. These APIs are present in pinned PyMuPDF 1.26.7.
    """
    regions: list[dict[str, Any]] = []
    try:
        for image in page.get_image_info():
            bbox = _rect(image["bbox"])
            if bbox[2] - bbox[0] >= 16 and bbox[3] - bbox[1] >= 16:
                regions.append({"bbox": bbox, "kind": "image", "confidence": "high"})
    except Exception:
        warnings.append(f"PDF 第 {page.number + 1} 页图片区域识别失败；请对照原页。")
    try:
        drawings = page.get_drawings()
        for region in page.cluster_drawings(drawings=drawings):
            bbox = _rect(region)
            area = max(1.0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
            if bbox[2] - bbox[0] < 24 or bbox[3] - bbox[1] < 24:
                continue
            if any(_overlap(bbox, table["bbox"]) / area >= 0.75 for table in tables):
                continue
            if any(_overlap(bbox, image["bbox"]) / area >= 0.75 for image in regions):
                continue
            regions.append({"bbox": bbox, "kind": "vector", "confidence": "suspected"})
    except Exception:
        warnings.append(f"PDF 第 {page.number + 1} 页矢量区域识别失败；图内标签可能未被分离。")
    return [
        {"ref": f"p{page.number}:f{index}", "page_index": page.number, **region}
        for index, region in enumerate(regions)
    ]


def parse_structure(document: Any, revision_id: str | None = None) -> dict[str, Any]:
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
    figures = []
    formulas = []
    for page, blocks in zip(document, pages, strict=True):
        page_tables = _tables(page, blocks, warnings)
        tables.extend(page_tables)
        figures.extend(figure_regions(page, page_tables, warnings))
        # Formula candidates are source-faithful layout hints only.  The
        # recognizer is intentionally not invoked during PDF import.
        try:
            from researchgraph.formula_api import _candidate_blocks, formula_candidate_id

            for index, candidate in enumerate(_candidate_blocks(page)):
                page_index = page.number
                source_text = str(candidate["text"])
                bbox = [round(float(value), 3) for value in candidate["bbox"]]
                # Ingest has no revision identity yet.  Keep a deterministic
                # placeholder there; reading refreshes always pass the actual
                # revision and the projection recomputes the API identity when
                # it consumes an older structure artifact.
                formula_identity = formula_candidate_id(
                    revision_id or "unbound", page_index, bbox, source_text
                )
                formulas.append(
                    {
                        "ref": f"p{page.number}:m{index}",
                        "id": formula_identity,
                        "formula_id": formula_identity,
                        "page_index": page_index,
                        "bbox": bbox,
                        "text": source_text,
                        "confidence": candidate["confidence"],
                        "status": "latex_unavailable",
                    }
                )
        except Exception:
            warnings.append(
                f"PDF 第 {page.number + 1} 页公式区域识别失败；原始文字和 PDF 原图仍保留。"
            )
    sections = _sections(ordered, document)
    mixed_pages = sorted(
        {
            block["page_index"] + 1
            for block in ordered
            if len(block.get("heading_candidates", [])) > 1
            or any(
                candidate["start_offset"] > 0 for candidate in block.get("heading_candidates", [])
            )
        }
    )
    if mixed_pages:
        warnings.append(
            "部分标题与正文共用原始文字块（PDF 第 "
            + "、".join(str(page) for page in mixed_pages)
            + " 页）；已保留标题精确字符定位，旧块级章节引用仍需按原文范围核对。"
        )
    by_ref = {block["ref"]: block for block in ordered}
    for table in tables:
        members = [by_ref[ref] for ref in table["block_refs"]]
        table["section_ref"] = members[0]["section_ref"] if members else "s0"
        table["excluded"] = bool(members) and all(block["excluded"] for block in members)
    return {
        "schema_version": SCHEMA_VERSION,
        "parser_version": f"pymupdf/{pymupdf.VersionBind};structure-v2",
        "sections": sections,
        "blocks": ordered,
        "tables": tables,
        "figures": figures,
        "formulas": formulas,
        "page_geometry": [
            {
                "page_index": page.number,
                "width": float(page.rect.width),
                "height": float(page.rect.height),
            }
            for page in document
        ],
        "warnings": warnings,
    }
