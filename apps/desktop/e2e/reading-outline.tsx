import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "../src/api";
import { PaperCloseReading } from "../src/PaperCloseReading";
import { KnowledgeReading } from "../src/KnowledgeReading";
import { ReadingOutline } from "../src/ReadingOutline";
import { paperReadingDocument } from "../src/paperReadingFixtures";
import "../src/style.css";

declare global {
  interface Window {
    __outlineModelCalls: number;
    __outlineQAScopes: string[];
  }
}
window.__outlineModelCalls = 0;
window.__outlineQAScopes = [];
const scenario =
  new URLSearchParams(location.search).get("scenario") || "paper";
const local = structuredClone(paperReadingDocument);
const paragraph = local.units.find((unit) => unit.kind === "paragraph")!;
local.sections = Array.from({ length: 18 }, (_, index) => ({
  section_id: `s${index + 1}`,
  title: `Section ${index + 1}`,
  level: (index % 3) + 1,
  parent_id: index % 3 === 0 ? null : `s${index}`,
  role: "body",
}));
local.units = local.sections.flatMap((section, index) => [
  {
    ...structuredClone(paragraph),
    id: `h${index + 1}`,
    kind: "heading" as const,
    section_id: section.section_id,
    text: section.title,
    ordinal: index * 2,
  },
  {
    ...structuredClone(paragraph),
    id: `p${index + 1}`,
    section_id: section.section_id,
    text: `Local paragraph for ${section.title}. The source and its reading position are preserved. `.repeat(
      12,
    ),
    ordinal: index * 2 + 1,
  },
]);
local.warnings = [];
api.readingDocument = async () => structuredClone(local);
api.paperReadingNotes = async () => null;
api.sections = async () => ({
  document_version_id: "v",
  sections: local.sections.map((section, index) => ({
    id: section.section_id,
    title: section.title,
    level: section.level,
    parent_id: section.parent_id ?? null,
    role: "body",
    ordinal: index,
    start_page: index,
    end_page: index,
    excluded: false,
    text: `Original source for ${section.title}. `.repeat(300),
    chunk_ids: [`c${index}`],
  })),
});
api.sectionGuide = async () => null;
api.qa = async (_paper, _revision, _section, scope) => {
  window.__outlineQAScopes.push(scope || "section");
  return [];
};
const forbiddenGeneration = async () => {
  window.__outlineModelCalls += 1;
  throw new Error("No model request is expected from reading navigation.");
};
api.generatePaperReadingNotes = forbiddenGeneration;
api.generateSectionGuide = forbiddenGeneration;
api.askQA = forbiddenGeneration;

const client = new QueryClient({
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
});
const shortEntries = [
  { id: "intro", label: "Introduction", targetId: "short-intro" },
  { id: "last", label: "Final short section", targetId: "short-last" },
];
const treeEntries = [
  {
    id: "chapter-1",
    label: "1 Introduction",
    targetId: "tree-chapter-1",
    level: 1,
    parentId: null,
  },
  {
    id: "sub-1",
    label: "1.1 Context",
    targetId: "tree-sub-1",
    level: 2,
    parentId: "chapter-1",
  },
  {
    id: "detail-1",
    label: "1.1.1 Detail",
    targetId: "tree-detail-1",
    level: 1,
    parentId: "sub-1",
  },
  {
    id: "chapter-2",
    label: "2 Methods",
    targetId: "tree-chapter-2",
    level: 1,
    parentId: null,
  },
  { id: "sub-2", label: "2.1 Setup", targetId: "tree-sub-2", level: 2 },
  {
    id: "detail-2",
    label: "2.1.1 Parameters",
    targetId: "tree-detail-2",
    level: 3,
  },
];
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "238px minmax(0, 1fr)",
          gap: 24,
          maxWidth: 1500,
          margin: "0 auto",
        }}
      >
        <aside
          style={{ padding: 24, background: "#f0f4eb" }}
          aria-label="研究项目"
        >
          个人研究空间
        </aside>
        <main style={{ padding: "24px 24px 48px", minWidth: 0, marginLeft: 0 }}>
          {scenario === "qa" ? (
            <KnowledgeReading
              paperId="paper"
              versionId="v"
              connected
              panel="qa"
              initialSectionId="s1"
            />
          ) : scenario === "tree" ? (
            <ReadingOutline entries={treeEntries} trackScroll>
              {treeEntries.map((entry) => (
                <section key={entry.id} style={{ minHeight: 650 }}>
                  <h2 id={entry.targetId} tabIndex={-1}>
                    {entry.label}
                  </h2>
                  <p data-reading-anchor>
                    Local source for {entry.label}. Hierarchy navigation does
                    not generate model requests.
                  </p>
                </section>
              ))}
            </ReadingOutline>
          ) : scenario === "short" ? (
            <ReadingOutline entries={shortEntries} trackScroll>
              <section style={{ minHeight: 1200 }}>
                <h2 id="short-intro" tabIndex={-1}>
                  Introduction
                </h2>
                <p>Long initial local section.</p>
              </section>
              <section style={{ minHeight: 110 }}>
                <h2 id="short-last" tabIndex={-1}>
                  Final short section
                </h2>
                <p>Short last paragraph.</p>
              </section>
            </ReadingOutline>
          ) : (
            <PaperCloseReading paperId="paper" revisionId="v" connected />
          )}
          {/* Leave page scroll space to isolate the source panel's own scrolling. */}
          {scenario === "qa" && (
            <div style={{ height: 1200 }} aria-hidden="true" />
          )}
        </main>
      </div>
    </QueryClientProvider>
  </StrictMode>,
);
