import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api, type CloseReadingView } from "../src/api";
import { SectionCloseReading } from "../src/SectionCloseReading";
import {
  readingSource,
  readingComplete,
  readingPartial,
  readingState,
  readingConcept,
  readingCheck,
} from "../src/closeReadingFixtures";
import "../src/style.css";
declare global {
  interface Window {
    __readingCalls: unknown[];
    __readingNavigation: unknown[];
  }
}
window.__readingCalls = [];
window.__readingNavigation = [];
const scenario =
  new URLSearchParams(location.search).get("scenario") || "cached";
let generated = false;
let state = structuredClone(readingState);
const complete = structuredClone(readingComplete);
complete.analysis!.paragraphs[1].translation_zh +=
  " <script>此处仅显示文本</script>";
api.sectionParagraphs = async () => structuredClone(readingSource);
api.conceptUnderstanding = async () => [structuredClone(readingConcept)];
api.readingState = async () => structuredClone(state);
api.saveReadingState = async (_paper, _section, body) => {
  state = { ...state, ...body };
  return structuredClone(state);
};
api.understandingCheck = async () => null;
api.generateUnderstandingCheck = async (_paper, _section, body) => {
  window.__readingCalls.push({ kind: "A03", body });
  return structuredClone(readingCheck);
};
api.closeReading = async (_paper, _section, _version, _ids, resultId) => {
  if (resultId)
    return {
      ...structuredClone(complete),
      id: resultId,
      range: { ...complete.range, paragraph_ids: ["p2"] },
    };
  if (scenario === "empty" && !generated) return null;
  if (scenario === "partial" && !generated)
    return structuredClone(readingPartial);
  if (scenario === "stale")
    return { ...structuredClone(complete), status: "STALE" };
  return structuredClone(complete);
};
api.generateCloseReading = async (_paper, _section, body) => {
  window.__readingCalls.push({ kind: "A02", body });
  generated = true;
  return {
    ...structuredClone(complete),
    id: body.retry_missing_of ? "repair" : complete.id,
    range: { ...complete.range, paragraph_ids: body.paragraph_ids },
  } as CloseReadingView;
};
const client = new QueryClient({
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
});
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <div style={{ maxWidth: 1320, padding: 24, margin: "0 auto" }}>
        <SectionCloseReading
          paperId="paper"
          revisionId="v"
          sectionId="s"
          title="2. Synthetic Methods"
          connected
          onOpenGraph={(nodeId) => window.__readingNavigation.push({ nodeId })}
          onAskParagraph={(paragraph) =>
            window.__readingNavigation.push({
              paragraphId: paragraph.paragraph_id,
            })
          }
        />
      </div>
    </QueryClientProvider>
  </StrictMode>,
);
