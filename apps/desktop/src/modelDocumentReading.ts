import type {
  ModelDocumentOutput,
  ModelDocumentParse,
  ModelDocumentSegment,
  SectionReadingAnalysis,
} from "./api";
import type { ReadingParagraphAnalysis } from "./ReadingContent";

export type ModelReadingAnalysis = {
  schema_version: "model-document-reading-1";
  item_kind: "paper_reading";
  paragraphs: ReadingParagraphAnalysis[];
  paper_argument: NonNullable<SectionReadingAnalysis["section_argument"]>;
};
type ModelTranslations = {
  schema_version: "model-document-translation-1";
  translations: {
    paragraph_id: string;
    chapter_ref: string;
    source_text: string;
    translation_zh: string;
  }[];
};

export function modelReadingData(
  parse: ModelDocumentParse,
  outputs: ModelDocumentOutput[],
) {
  const source = [...parse.segments]
    .sort((a, b) => a.chapter_order - b.chapter_order || a.ordinal - b.ordinal)
    .filter((segment) => segment.kind === "paragraph" && segment.text?.trim());
  // API history is oldest first. A failed newer generation must not hide the
  // latest previously validated result, while a newer success replaces it.
  const current = [...outputs]
    .reverse()
    .filter(
      (output) => output.parse_id === parse.id && output.status === "succeeded",
    );
  const readingCandidates = [...outputs]
    .reverse()
    .filter(
      (output) =>
        output.parse_id === parse.id &&
        output.item_kind === "paper_reading" &&
        ["succeeded", "partial"].includes(output.status),
    );
  // The API revalidates persisted contracts. This adapter also binds the visible
  // slots to the current parse; legacy chapter prose never becomes annotations.
  const readingResult = readingCandidates
    .map((output) => ({
      output,
      data: output.output_json as unknown as ModelReadingAnalysis | null,
    }))
    .find(
      ({ data }) =>
        data?.schema_version === "model-document-reading-1" &&
        Array.isArray(data.paragraphs) &&
        data.paragraphs.length === source.length &&
        data.paragraphs.every(
          (paragraph, index) => paragraph.paragraph_id === source[index].id,
        ),
    );
  const reading = readingResult?.data;
  const readingOutput = readingResult?.output;
  const translations = new Map<string, string>();
  const translated = current
    .filter((output) => output.item_kind === "translation")
    .map((output) => output.output_json as unknown as ModelTranslations | null)
    .find(
      (data) =>
        data?.schema_version === "model-document-translation-1" &&
        Array.isArray(data.translations) &&
        data.translations.length === source.length &&
        data.translations.every(
          (translation, index) =>
            translation.paragraph_id === source[index].id &&
            translation.chapter_ref === source[index].chapter_ref &&
            translation.source_text === source[index].text,
        ),
    );
  for (const translation of translated?.translations ?? []) {
    translations.set(translation.paragraph_id, translation.translation_zh);
  }
  return {
    reading,
    readingOutput,
    translations,
    analyses: new Map(
      (reading?.paragraphs ?? []).map((paragraph) => [
        paragraph.paragraph_id,
        paragraph,
      ]),
    ),
    numbers: new Map(source.map((segment, index) => [segment.id, index + 1])),
    legacy: current.filter((output) => {
      const data = output.output_json as unknown as Record<
        string,
        unknown
      > | null;
      return (
        !data?.schema_version &&
        ["paper_reading", "translation"].includes(output.item_kind)
      );
    }),
  };
}

export function modelSegmentPageLabel(segment: ModelDocumentSegment) {
  const start = segment.locator?.page_start ?? segment.locator?.page;
  const rawEnd = segment.locator?.page_end ?? start;
  if (!Number.isSafeInteger(start) || (start as number) < 1)
    return "模型提取稿 · 未提供页码";
  const end =
    Number.isSafeInteger(rawEnd) && (rawEnd as number) >= (start as number)
      ? rawEnd
      : start;
  return start === end
    ? `PDF 第 ${start} 页 · 模型提取稿`
    : `PDF 第 ${start}–${end} 页 · 模型提取稿`;
}
