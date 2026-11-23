export const readingHighlightTypes = {
  THESIS: { label: "核心论点", color: "var(--rgs-reading-thesis)" },
  CONCEPT: { label: "概念定义", color: "var(--rgs-reading-concept)" },
  EVIDENCE: { label: "论据与结果", color: "var(--rgs-reading-evidence)" },
  COUNTERARGUMENT: {
    label: "反驳与局限",
    color: "var(--rgs-reading-counterargument)",
  },
  METHOD: { label: "方法与过程", color: "var(--rgs-reading-method)" },
} as const;

export type HighlightType = keyof typeof readingHighlightTypes;
export type ReadingHighlight = {
  type: HighlightType;
  quote_en: string;
  occurrence_index: number;
};
export type HighlightSegment = {
  text: string;
  start: number;
  type: HighlightType | null;
};

export type ReadingHighlightRange = ReadingHighlight & {
  index: number;
  start: number;
  end: number;
};

export function readingHighlightRanges(
  text: string,
  highlights: ReadingHighlight[],
): ReadingHighlightRange[] {
  return highlights.flatMap((highlight, index) => {
    if (
      !Object.hasOwn(readingHighlightTypes, highlight.type) ||
      !highlight.quote_en ||
      !Number.isSafeInteger(highlight.occurrence_index) ||
      highlight.occurrence_index < 0
    )
      return [];
    let start = -1;
    for (
      let occurrence = 0;
      occurrence <= highlight.occurrence_index;
      occurrence++
    ) {
      start = text.indexOf(highlight.quote_en, start + 1);
      if (start < 0) return [];
    }
    return [
      { ...highlight, index, start, end: start + highlight.quote_en.length },
    ];
  });
}

// Preserve every annotation identity, including adjacent marks of the same type
// and fully overlapping ranges. Color precedence stays the same as the legacy
// renderer, while all covered annotations retain a source anchor.
export function readingAnnotationSegments(
  text: string,
  ranges: ReadingHighlightRange[],
) {
  const priority = Object.keys(readingHighlightTypes);
  const boundaries = [
    ...new Set([
      0,
      text.length,
      ...ranges.flatMap(({ start, end }) => [start, end]),
    ]),
  ].sort((a, b) => a - b);
  return boundaries.slice(0, -1).map((start, i) => {
    const end = boundaries[i + 1];
    const covered = ranges
      .filter((range) => range.start <= start && range.end >= end)
      .sort(
        (a, b) =>
          priority.indexOf(a.type) - priority.indexOf(b.type) ||
          a.index - b.index,
      );
    return {
      start,
      text: text.slice(start, end),
      type: covered[0]?.type ?? null,
      highlightIndices: covered.map((range) => range.index),
    };
  });
}

// Exact local text is authoritative. Earlier enum types win overlapping text;
// ties use the response order. Splitting at boundaries preserves every byte of
// the displayed source, including whitespace and repeated occurrences.
export function highlightSegments(
  text: string,
  highlights: ReadingHighlight[],
): HighlightSegment[] {
  const priority = Object.keys(readingHighlightTypes);
  const intervals = highlights.flatMap((highlight, index) => {
    if (
      !priority.includes(highlight.type) ||
      !highlight.quote_en ||
      !Number.isSafeInteger(highlight.occurrence_index) ||
      highlight.occurrence_index < 0
    )
      return [];
    let start = -1;
    for (
      let occurrence = 0;
      occurrence <= highlight.occurrence_index;
      occurrence++
    ) {
      start = text.indexOf(highlight.quote_en, start + 1);
      if (start < 0) return [];
    }
    return [
      {
        start,
        end: start + highlight.quote_en.length,
        type: highlight.type,
        index,
      },
    ];
  });
  const boundaries = [
    ...new Set([
      0,
      text.length,
      ...intervals.flatMap((item) => [item.start, item.end]),
    ]),
  ].sort((a, b) => a - b);
  const segments: HighlightSegment[] = [];
  for (let i = 0; i < boundaries.length - 1; i++) {
    const start = boundaries[i];
    const end = boundaries[i + 1];
    const selected = intervals
      .filter((item) => item.start <= start && item.end >= end)
      .sort(
        (a, b) =>
          priority.indexOf(a.type) - priority.indexOf(b.type) ||
          a.index - b.index,
      )[0];
    const type = selected?.type ?? null;
    const last = segments[segments.length - 1];
    if (last && last.type === type) last.text += text.slice(start, end);
    else segments.push({ text: text.slice(start, end), start, type });
  }
  return segments;
}
