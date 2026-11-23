import { useState } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api, defaultPostImportPlan } from "../src/api";
import { ImportPostProcessingPlan } from "../src/ImportPostProcessingPlan";
import { JobHistory } from "../src/JobHistory";
import { PaperParsing } from "../src/PaperParsing";
import "../src/style.css";
declare global {
  interface Window {
    __parseCalls: unknown[];
  }
}
window.__parseCalls = [];
Object.defineProperty(window, "__TAURI_INTERNALS__", {
  value: {
    invoke: async (
      _command: string,
      args: { method: string; path: string },
    ) => {
      if (args.method !== "GET" || args.path !== "/api/v1/settings/models")
        throw new Error("Unexpected native request");
      return {
        profiles: [
          {
            id: "pdf",
            name: "Synthetic PDF",
            model: "file-fixture",
            parameters: {
              document_timeout_seconds: 600,
              document_total_timeout_seconds: 1800,
              capabilities: {
                document_input: "image",
                multimodal: true,
                document_transport: "chat_images",
              },
            },
          },
        ],
        roles: { document_parse: "pdf" },
      };
    },
  },
});
api.parsePaper = async (_paperId, body) => {
  window.__parseCalls.push(body);
  return { id: "synthetic-job", status: "queued" } as never;
};
const batchFixture = new URLSearchParams(window.location.search).has("batch");
api.job = async () => {
  const timestamp = "2026-11-21T00:00:00Z";
  return {
    id: "synthetic-job",
    kind: batchFixture ? "llm_document_parse" : "pdf_import",
    project_id: "p",
    status: batchFixture ? "running" : "failed",
    stage: batchFixture ? "document_waiting" : "failed",
    attempt: 1,
    error: batchFixture ? null : "Synthetic local read failure",
    created_at: timestamp,
    updated_at: timestamp,
    result: batchFixture
      ? {
          document_batches: {
            total: 4,
            completed: 1,
            current: 2,
            page_start: 5,
            page_end: 9,
            requests_sent: 3,
            request_budget: 11,
            repairs_used: 1,
            boundaries_completed: 0,
            boundaries_total: 3,
            phase: "waiting",
            validation_errors: [
              {
                path: "segments[3].kind",
                code: "literal_error",
                input: "PRIVATE_SYNTHETIC_RESPONSE",
              },
              { path: "private fixture response", code: "missing" },
              { path: "segments[0].text", code: "private fixture response" },
            ],
            raw_body: "PRIVATE_SYNTHETIC_RESPONSE",
          },
        }
      : {
          document_request: {
            elapsed_seconds: 90.19,
            read_timeout_seconds: 90,
          },
        },
  };
};
api.projectJobs = async () => ({
  items: [await api.job("synthetic-job")],
  next_cursor: null,
});
function Fixture() {
  const [plan, setPlan] = useState(defaultPostImportPlan);
  const [source, setSource] = useState<"local" | "model">("local");
  return (
    <main style={{ padding: 20, maxWidth: 900, margin: "0 auto" }}>
      <h1>论文解析</h1>
      <ImportPostProcessingPlan value={plan} onChange={setPlan} />
      <div style={{ height: 1000 }}>滚动后的论文管理</div>
      <PaperParsing
        paperId="synthetic-paper"
        projectId="p"
        connected
        hasLocal
        hasModel={
          !new URLSearchParams(window.location.search).has("local-only")
        }
        source={source}
        onViewSource={setSource}
        onQueued={() => {}}
      />
      {batchFixture && <JobHistory projectId="p" connected title="任务记录" />}
    </main>
  );
}
createRoot(document.getElementById("root")!).render(
  <QueryClientProvider
    client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
  >
    <Fixture />
  </QueryClientProvider>,
);
