export const readingHighlightTypes = {
  THESIS: { label: "核心论点", color: "#eab308" },
  CONCEPT: { label: "概念定义", color: "#dc2626" },
  EVIDENCE: { label: "论据与结果", color: "#2563eb" },
  COUNTERARGUMENT: { label: "反驳与局限", color: "#16a34a" },
  METHOD: { label: "方法与过程", color: "#9333ea" },
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
