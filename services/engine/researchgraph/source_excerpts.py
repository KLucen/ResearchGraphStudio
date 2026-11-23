"""Versioned callers share deterministic ranges for verbatim model citations."""

import re
from typing import Any


def _excerpt_ranges(text: str) -> list[tuple[int, int]]:
    """Partition each existing source into verbatim spans with quote-length bounds."""
    boundaries = [m.end() for m in re.finditer(r"[.!?。！？](?=\s|$)|\r?\n", text)]
    if not boundaries or boundaries[-1] != len(text):
        boundaries.append(len(text))
    start = 0
    ranges: list[tuple[int, int]] = []
    for end in boundaries:
        if not text[start:end].strip() and end < len(text):
            continue
        while end - start > 1200:
            limit = start + 1200
            space = text.rfind(" ", start + 600, limit)
            split = limit if space < 0 else space + 1
            ranges.append((start, split))
            start = split
        if start < end:
            ranges.append((start, end))
        start = end
    return ranges


def source_excerpts(manifest: dict[str, Any]) -> dict[str, tuple[str, int, int]]:
    excerpts: dict[str, tuple[str, int, int]] = {}
    for source in manifest["sources"]:
        for left, right in _excerpt_ranges(source["text"]):
            excerpts[f"q{len(excerpts) + 1}"] = (source["ref"], left, right)
    return excerpts


def excerpt_quote(text: str, start: int, end: int) -> tuple[str, int] | None:
    """Resolve the literal quote and its overlapping occurrence at an exact range."""
    span = text[start:end]
    quote = span.strip()
    if not quote:
        return None
    start += len(span) - len(span.lstrip())
    offset = text.find(quote)
    occurrence = 0
    while 0 <= offset < start:
        offset = text.find(quote, offset + 1)
        occurrence += 1
    if offset != start:
        raise ValueError("Frozen excerpt does not reproduce source text")
    return quote, occurrence
