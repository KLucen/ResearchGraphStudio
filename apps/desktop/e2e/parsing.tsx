import { useState } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api, defaultPostImportPlan } from "../src/api";
import { ImportPostProcessingPlan } from "../src/ImportPostProcessingPlan";
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
api.job = async () => {
  const batchFixture = new URLSearchParams(window.location.search).has("batch");
  return {
    id: "synthetic-job",
    status: "failed",
    error: "Synthetic local read failure",
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
  } as never;
};
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
