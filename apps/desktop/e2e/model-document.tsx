import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  api,
  type ImportSession,
  type ModelChapterReadingState,
  type ModelChapterReadingStates,
  type ModelDocumentParse,
  type ModelDocumentOutput,
  type ModelDocumentSegment,
} from "../src/api";
import { ModelDocumentPanel } from "../src/ModelDocumentPanel";
import { Papers } from "../src/Papers";
import { paperReadingDocument } from "../src/paperReadingFixtures";
import { readingState } from "../src/closeReadingFixtures";
import "../src/style.css";

// Distributable fixtures only: no PDF, Provider, user database or model request.
declare global {
  interface Window {
    __modelDocumentProgressWrites: ModelChapterReadingState[];
    __modelDocumentProgressReads: number;
    __modelDocumentGenerationRequests: {
      item_kind: string;
      translation_mode: string;
    }[];
  }
}
window.__modelDocumentProgressWrites = [];
window.__modelDocumentProgressReads = 0;
window.__modelDocumentGenerationRequests = [];
const fixtureMode =
  new URLSearchParams(window.location.search).get("mode") ?? "complete";
const workspaceMode = new URLSearchParams(window.location.search).get(
  "workspace",
);
const sessionId = "browser-model-session";
const parseId = "browser-model-parse";
const storageKey = "researchgraph-e2e-model-chapter-progress";
const timestamp = "2026-11-18T06:00:00Z";
const chapters = [
  { ref: "introduction", title: "1 Introduction", level: 1 },
  { ref: "scope", title: "1.1 Scope", level: 2 },
  { ref: "methods", title: "2 Methods", level: 1 },
  { ref: "results", title: "3 Results", level: 1 },
];
function segment(
  chapter: (typeof chapters)[number],
  ordinal: number,
  values: Partial<ModelDocumentSegment>,
): ModelDocumentSegment {
  return {
    id: `${chapter.ref}-${ordinal}`,
    chapter_ref: chapter.ref,
    chapter_title: chapter.title,
    chapter_level: chapter.level,
    chapter_order: chapters.indexOf(chapter),
    kind: "paragraph",
    ordinal,
    text: null,
    latex: null,
    mathml: null,
    raw_table_text: null,
    table_data: null,
    locator: {
      page_start: chapters.indexOf(chapter) + 1,
      page_end: chapters.indexOf(chapter) + 1,
    },
    status: "ok",
    warnings: [],
    ...values,
  };
}
const document: ModelDocumentParse = {
  id: parseId,
  import_session_id: sessionId,
  parse_version: "browser-synthetic-1",
  modality: "pdf",
  status: "succeeded",
  warnings: [],
  error_code: null,
  error: null,
  segments: [
    segment(chapters[0], 0, {
      text: "Synthetic source introduction. The core claim introduces a concept. Evidence supports the result under a limitation.",
    }),
    ...Array.from({ length: 4 }, (_, index) =>
      segment(chapters[0], index + 1, {
        text: `Reading passage ${index + 1}. ${"A bounded synthetic experiment compares an observed outcome under an explicit condition. The source remains available when progress is marked. ".repeat(5)}`,
      }),
    ),
    segment(chapters[1], 0, {
      text: "Synthetic source scope. This subsection belongs to Introduction and has no separate major-chapter progress control.",
    }),
    segment(chapters[2], 0, {
      text: "Synthetic source methods. The objective below is an invented fixture.",
    }),
    segment(chapters[2], 1, {
      kind: "formula",
      text: "Synthetic least-squares objective",
      latex: String.raw`L(\theta) = \sum_{i=1}^{n}(y_i - f_{\theta}(x_i))^2`,
    }),
    segment(chapters[3], 0, {
      text: "Synthetic source results. These values are fixtures, not measured scientific performance.",
    }),
    segment(chapters[3], 1, {
      kind: "table",
      raw_table_text: "Method | Score\nBaseline | 1.0\nSynthetic | 2.0",
      table_data: {
        columns: ["Method", "Score"],
        rows: [
          ["Baseline", "1.0"],
          ["Synthetic", "2.0"],
        ],
      },
    }),
  ],
};
const session: ImportSession = {
  id: sessionId,
  project_id: "browser-project",
  source_kind: "zotero",
  selection_id: "browser-selection",
  source_snapshot: { paper_id: "browser-paper" },
  plan: {
    overview: false,
    reading: fixtureMode !== "unselected",
    translation_mode: fixtureMode === "complete" ? "full" : "none",
    modality: "auto",
    require_multimodal: false,
    allow_network: true,
  },
  status: "succeeded",
  error: null,
  created_at: timestamp,
  updated_at: timestamp,
  items: [],
};
api.importSession = async () => structuredClone(session);
api.modelDocumentParse = async () => structuredClone(document);
const paragraphs = document.segments.filter(
  (value) => value.kind === "paragraph",
);
const readingOutput: ModelDocumentOutput = {
  id: "browser-reading",
  import_session_id: sessionId,
  parse_id: parseId,
  item_kind: "paper_reading",
  status: "succeeded",
  output_json: {
    schema_version: "model-document-reading-1",
    item_kind: "paper_reading",
    paragraphs: paragraphs.map((value, index) => ({
      paragraph_id: value.id,
      translation_zh: null,
      paragraph_function: index === 0 ? "STATE_CLAIM" : "PRESENT_EVIDENCE",
      logic_role_zh: `第${index + 1}段合成论证批注：说明作者主张的支撑关系。`,
      critical_note_zh: index === 0 ? "对照原文核查适用条件。" : "",
      reading_question_zh: null,
      highlights:
        index === 0
          ? [
              { type: "THESIS", quote_en: "core claim", occurrence_index: 0 },
              { type: "CONCEPT", quote_en: "concept", occurrence_index: 0 },
              { type: "EVIDENCE", quote_en: "Evidence", occurrence_index: 0 },
              {
                type: "COUNTERARGUMENT",
                quote_en: "limitation",
                occurrence_index: 0,
              },
            ]
          : [],
      related_graph_node_ids: [],
    })),
    paper_argument: {
      logic_chain_zh: [
        "合成论文提出待讨论的问题。",
        "用给定合成结果说明支撑及局限。",
      ],
      core_claim_zh: "合成核心主张，仅用于浏览器展示验证。",
      strong_point_zh: null,
      question_to_verify_zh: "哪些条件限制结论？",
    },
  },
  error_code: null,
  error: null,
};
const translationOutput: ModelDocumentOutput = {
  id: "browser-translation",
  import_session_id: sessionId,
  parse_id: parseId,
  item_kind: "translation",
  status: "succeeded",
  output_json: {
    schema_version: "model-document-translation-1",
    item_kind: "translation",
    translations: paragraphs.map((value, index) => ({
      paragraph_id: value.id,
      chapter_ref: value.chapter_ref,
      source_text: value.text!,
      translation_zh:
        index === 0
          ? "合成译文：核心主张引入概念，论据在限定条件下支撑结果。"
          : `第${index + 1}段合成译文：原段落与阅读笔记通过段落标识对应。`,
    })),
  },
  error_code: null,
  error: null,
};
api.modelDocumentOutputs = async () =>
  structuredClone(
    fixtureMode === "unselected"
      ? []
      : fixtureMode === "no-translation"
        ? [readingOutput]
        : [readingOutput, translationOutput],
  );
api.generateModelDocumentOutput = async (_sessionId, itemKind, body) => {
  window.__modelDocumentGenerationRequests.push({
    item_kind: itemKind,
    translation_mode: body.translation_mode,
  });
  return {
    id: "browser-reading-job",
    project_id: "browser-project",
    kind: "llm_document_postprocess",
    status: "queued",
    stage: "queued",
    attempt: 1,
    error: null,
    result: null,
    created_at: timestamp,
    updated_at: timestamp,
  };
};
function storedStates(): ModelChapterReadingStates {
  const saved = localStorage.getItem(storageKey);
  return saved
    ? (JSON.parse(saved) as ModelChapterReadingStates)
    : { parse_id: parseId, items: [] };
}
api.modelChapterReadingStates = async () => {
  window.__modelDocumentProgressReads += 1;
  return structuredClone(storedStates());
};
api.saveModelChapterReadingState = async (_sessionId, body) => {
  const value = { ...body, updated_at: timestamp };
  const previous = storedStates();
  localStorage.setItem(
    storageKey,
    JSON.stringify({
      parse_id: parseId,
      items: [
        ...previous.items.filter(
          (item) => item.chapter_ref !== body.chapter_ref,
        ),
        {
          chapter_ref: body.chapter_ref,
          progress: body.progress,
          updated_at: timestamp,
        },
      ],
    } satisfies ModelChapterReadingStates),
  );
  window.__modelDocumentProgressWrites.push(value);
  return structuredClone(value);
};
if (workspaceMode) {
  const paper = {
    id: "browser-paper",
    project_id: "browser-project",
    title: "A synthetic paper for reading workspace verification",
    created_at: timestamp,
  };
  api.papers = async () => ({ items: [paper], next_cursor: null });
  api.paper = async () => ({
    paper,
    revisions:
      workspaceMode === "model-only"
        ? []
        : [
            {
              id: "local-revision",
              paper_id: paper.id,
              sha256: "fixture-only",
              parser_version: "browser-synthetic-1",
              page_count: 4,
              warnings: [],
              created_at: timestamp,
            },
          ],
    sources: [],
    zotero_links: [],
  });
  api.importSessions = async () =>
    workspaceMode === "local" ? [] : [structuredClone(session)];
  const emptyOverview = async () =>
    ({ status: null, id: null, paper_card: null, graph: null }) as never;
  api.overview = emptyOverview;
  api.modelOverview = emptyOverview;
  api.readingDocument = async () => structuredClone(paperReadingDocument);
  api.paperReadingNotes = async () => null as never;
  api.readingState = async () => structuredClone(readingState);
  api.sections = async () => ({
    document_version_id: "local-revision",
    sections: [
      {
        id: "local-section",
        title: "Local source chapter",
        ordinal: 0,
        role: "results",
        parent_id: null,
        level: 1,
        start_page: 0,
        end_page: 0,
        excluded: false,
        text: "Synthetic local source text",
        chunk_ids: [],
      },
    ],
  });
  api.sectionParagraphs = async () => ({ paragraphs: [] }) as never;
  api.qa = async () => [];
}
const client = new QueryClient({
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
});
createRoot(window.document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <main style={{ maxWidth: 1280, padding: 24, margin: "0 auto" }}>
        {workspaceMode ? (
          <Papers
            projectId="browser-project"
            initialPaperId="browser-paper"
            connected
          />
        ) : (
          <ModelDocumentPanel
            sessionId={sessionId}
            connected
            activeView="reading"
            sessionStatus="succeeded"
            sessionError={null}
          />
        )}
      </main>
    </QueryClientProvider>
  </StrictMode>,
);
