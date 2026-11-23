import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api, type OverviewView } from "../src/api";
import { PaperOverview } from "../src/PaperOverview";
import { syntheticCardSet } from "../src/paperCardSetFixtures";
import "../src/style.css";

declare global {
  interface Window {
    __cardRequests: { kind: string; args: unknown[] }[];
    __cardNavigation: { sectionId: string; paragraphId?: string }[];
  }
}
window.__cardRequests = [];
window.__cardNavigation = [];
const query = new URLSearchParams(location.search);
const source = query.get("source") === "model" ? "model" : "local";
const scenario = query.get("scenario") ?? "completed";
const data = syntheticCardSet();
data.source_kind = source === "model" ? "model_parse" : "local_revision";
if (source === "model") {
  for (const card of data.cards) {
    for (const item of card.evidence) {
      item.position.page_start = null;
      item.position.page_end = null;
      item.position.segment_id = "model-segment-" + item.source_id;
      item.position.local_offsets = [];
    }
  }
}
const completed: OverviewView = {
  id: "card-result-1",
  paper_id: "paper",
  document_version_id: "revision",
  status: "COMPLETED",
  pdf_hash: "",
  input_hash: "",
  schema_version: data.schema_version,
  prompt_version: data.prompt_version,
  provider_id: "synthetic",
  model_id: "synthetic",
  generated_at: "2026-11-21T08:00:00Z",
  cache_hit: true,
  graph_status: "NOT_ENOUGH_INFO",
  paper_card: null,
  graph: null,
  card_set: data,
  usage: null,
  job_id: "synthetic-job",
  error_code: null,
  error: null,
};
const legacy: OverviewView = {
  ...completed,
  schema_version: "paper_overview_graph.v1",
  card_set: null,
  paper_card: {
    research_question: "LEGACY_GRAPH_CARD_MUST_NOT_APPEAR",
    motivation: "old",
    method_summary: "old",
    contributions: [],
    main_findings: [],
    limitations: [],
  },
  graph: {
    nodes: [
      {
        id: "old-node",
        type: "METHOD",
        label_zh: "OLD_GRAPH_MUST_NOT_APPEAR",
        label_en: null,
        description_zh: "old",
        basis: "EXPLICIT",
      },
    ],
    edges: [],
  },
};
const read = async () =>
  structuredClone(
    scenario === "legacy" ? legacy : scenario === "empty" ? null : completed,
  );
api.overview = async () =>
  (await read()) ?? {
    ...structuredClone(completed),
    status: null,
    schema_version: null,
    card_set: null,
    id: null,
  };
api.modelOverview = read;
const generate =
  (kind: string) =>
  async (...args: Parameters<typeof api.generateOverview>) => {
    window.__cardRequests.push({ kind, args });
    return {
      ...structuredClone(completed),
      status: "PENDING" as const,
      card_set: null,
    };
  };
api.generateOverview = generate("local-generate");
api.generateModelOverview = generate("model-generate");
for (const name of [
  "overviewLayout",
  "modelOverviewLayout",
  "saveOverviewLayout",
  "saveModelOverviewLayout",
  "resetOverviewLayout",
  "resetModelOverviewLayout",
] as const) {
  Object.assign(api, {
    [name]: async (...args: unknown[]) => {
      window.__cardRequests.push({ kind: name, args });
      throw new Error("Overview must not access graph layouts");
    },
  });
}
const client = new QueryClient({
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
});
function Harness() {
  const [resultId, setResultId] = useState("card-result-1");
  return (
    <main style={{ maxWidth: 1240, padding: 20, margin: "0 auto" }}>
      <button
        onClick={() => {
          const id =
            resultId === "card-result-1" ? "card-result-2" : "card-result-1";
          setResultId(id);
          client.setQueryData(
            [
              source === "model" ? "model-overview" : "overview",
              "paper",
              "revision",
            ],
            { ...structuredClone(completed), id },
          );
        }}
      >
        切换合成结果版本
      </button>
      <PaperOverview
        paperId="paper"
        revisionId="revision"
        projectId="project"
        source={source}
        connected
        onOpenSection={(sectionId, paragraphId) =>
          window.__cardNavigation.push({ sectionId, paragraphId })
        }
      />
    </main>
  );
}
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>
  </StrictMode>,
);
