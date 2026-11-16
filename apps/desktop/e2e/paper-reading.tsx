import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "../src/api";
import { PaperCloseReading } from "../src/PaperCloseReading";
import {
  paperReadingDocument,
  paperReadingComplete,
} from "../src/paperReadingFixtures";
import "../src/style.css";
declare global {
  interface Window {
    __paperReadingCalls: unknown[];
    __paperReadingLocalRefresh: number;
    __paperReadingNavigation: unknown[];
  }
}
window.__paperReadingCalls = [];
window.__paperReadingLocalRefresh = 0;
window.__paperReadingNavigation = [];
const scenario =
  new URLSearchParams(location.search).get("scenario") || "cached";
let generated = false;
const local = structuredClone(paperReadingDocument);
const complete = structuredClone(paperReadingComplete);
complete.analysis!.paragraphs[1].translation_zh +=
  " <script>只显示文字</script>";
api.readingDocument = async () => structuredClone(local);
api.refreshReadingDocument = async () => {
  window.__paperReadingLocalRefresh += 1;
  local.projection_hash = "refreshed-local-projection";
  return structuredClone(local);
};
api.paperReadingNotes = async () =>
  scenario === "empty" && !generated ? null : structuredClone(complete);
api.generatePaperReadingNotes = async (_paper, body) => {
  window.__paperReadingCalls.push(body);
  generated = true;
  return structuredClone(complete);
};
const client = new QueryClient({
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
});
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <div style={{ maxWidth: 1320, padding: 24, margin: "0 auto" }}>
        <PaperCloseReading
          paperId="paper"
          revisionId="v"
          connected
          onOpenGraph={(nodeId) =>
            window.__paperReadingNavigation.push({ nodeId })
          }
          onAskParagraph={(sectionId, paragraph) =>
            window.__paperReadingNavigation.push({
              sectionId,
              paragraphId: paragraph.paragraph_id,
            })
          }
        />
      </div>
    </QueryClientProvider>
  </StrictMode>,
);
