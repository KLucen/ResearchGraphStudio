"""Section-first reading inputs, bounded by model capacity rather than source characters."""

import json
from collections import Counter
from typing import Any

PLANNER = "section-context-v1"
Entry = dict[str, str]
Metadata = dict[str, dict[str, Any]]


def context_bytes(entries: list[Entry], metadata: Metadata) -> int:
    """Use the transport's conservative UTF-8 estimate, including table structure."""
    tables = {}
    sources = []
    for entry in entries:
        context = metadata.get(entry["id"], {})
        sources.append(
            {
                "id": entry["id"],
                "text": entry["text"],
                **{k: v for k, v in context.items() if k != "table"},
            }
        )
        if "table" in context:
            tables[context["context_group"]] = context["table"]
    return len(
        json.dumps(
            {"allowed_evidence": sources, "source_tables": tables}, ensure_ascii=False
        ).encode("utf-8")
    )


def split_context_group(entries: list[Entry], metadata: Metadata) -> list[list[Entry]] | None:
    """Never split the evidence belonging to one paragraph or one detected table."""
    groups = [metadata.get(e["id"], {}).get("context_group", e["id"]) for e in entries]
    remaining = Counter(groups)
    crossing: set[str] = set()
    candidates = []
    target = context_bytes(entries, metadata) / 2
    prefix = 0
    seen_tables = set()
    for index, entry in enumerate(entries[:-1], 1):
        group = groups[index - 1]
        remaining[group] -= 1
        if remaining[group]:
            crossing.add(group)
        else:
            crossing.discard(group)
        context = metadata.get(entry["id"], {})
        # Linear work even for very long sections: use a weighted midpoint,
        # then measure each resulting request exactly in the capacity planner.
        prefix += len(entry["text"].encode("utf-8")) + len(
            json.dumps(
                {k: v for k, v in context.items() if k != "table"}, ensure_ascii=False
            ).encode("utf-8")
        )
        if "table" in context and group not in seen_tables:
            seen_tables.add(group)
            prefix += len(json.dumps(context["table"], ensure_ascii=False).encode("utf-8"))
        if not crossing:
            candidates.append((abs(prefix - target), index))
    if not candidates:
        return None
    middle = min(candidates)[1]
    return [entries[:middle], entries[middle:]]


def plan_reading_sections(
    entries: list[Entry],
    metadata: Metadata,
    *,
    context_window: int | None,
    max_output_tokens: int | None,
    overhead: int,
) -> list[list[Entry]]:
    """Keep a cross-page section together unless the configured model cannot fit it.

    No guessed model limit is used when endpoint capabilities are unknown. A
    table/paragraph that cannot fit is reported explicitly, never cut or dropped.
    """
    sections: list[list[Entry]] = []
    context_groups = [metadata.get(e["id"], {}).get("context_group", e["id"]) for e in entries]
    last = {group: index for index, group in enumerate(context_groups)}
    section_groups = [metadata.get(e["id"], {}).get("section_group", e["section"]) for e in entries]
    open_until = -1
    for index, entry in enumerate(entries):
        # A table's heading and rows can have different heuristic section labels.
        # Merge those section windows rather than cutting their shared context.
        if not sections or (
            section_groups[index - 1] != section_groups[index] and index > open_until
        ):
            sections.append([])
        sections[-1].append(entry)
        open_until = max(open_until, last[context_groups[index]])
    if not context_window:
        return sections
    # Reserve the documented output capacity when it fits. The provider still
    # computes the exact remaining budget for the final serialized request.
    output_reserve = (
        max_output_tokens
        if max_output_tokens and max_output_tokens < context_window
        else max(128, context_window // 4)
    )
    available = context_window - output_reserve - overhead
    if available <= 0:
        raise ValueError("模型上下文无法容纳 Prompt、Schema 与输出预留，请检查模型能力配置")
    result = []
    pending = list(reversed(sections))
    while pending:
        section = pending.pop()
        if context_bytes(section, metadata) <= available:
            result.append(section)
            continue
        children = split_context_group(section, metadata)
        if not children:
            raise ValueError("完整原文段落或表格超过模型上下文，未截断原文；请使用更大上下文模型")
        pending.extend(reversed(children))
    return result
