import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { mockIPC } from "@tauri-apps/api/mocks";
import type { components } from "../../../packages/contracts/generated";
import { GraphWorkspace } from "../src/GraphWorkspace";
import "../src/style.css";

type Graph = components["schemas"]["GraphProjection"];
type Layout = components["schemas"]["LayoutView"];
type Paper = components["schemas"]["PaperView"];
type IPCRequest = {
  method: string;
  path: string;
  body: Record<string, unknown> | null;
};

declare global {
  interface Window {
    workspaceHarness: {
      requests: IPCRequest[];
      retainedNode?: Element;
    };
  }
}

// All source and graph fixtures are synthetic. This IPC boundary deliberately
// cannot contact a native engine, read a local database, or invoke an LLM.
const papers: Paper[] = ["一", "二", "三"].map((number, index) => ({
  id: `paper-${index + 1}`,
  project_id: "synthetic-workspace",
  title: `合成论文${number}`,
  created_at: "2026-11-03T08:00:00+08:00",
}));
const nodes: Graph["nodes"] = papers.flatMap((paper) =>
  (["Paper", "Claim", "Method", "Condition"] as const).map((kind, index) => ({
    id: index ? `${paper.id}-${kind}` : paper.id,
    paper_id: paper.id,
    kind,
    label_zh: index ? `${paper.title} ${kind}` : paper.title,
    label_en: `${paper.id} ${kind}`,
    detail_ref: `/api/v1/projects/synthetic-workspace/graph/nodes/${index ? `${paper.id}-${kind}` : paper.id}`,
    source_status: "source_verified",
    review_status: "not_applicable",
    knowledge_origin: "source",
    badges: [],
    graph_role: index === 0 ? "paper" : index === 1 ? "core" : "supporting",
    unit_ids: index ? [`${paper.id}-unit`] : [],
  })),
);
const graph: Graph = {
  contract_version: "reading-projection-2.0",
  project_id: "synthetic-workspace",
  graph_revision: 1,
  nodes,
  edges: papers.flatMap((paper) =>
    (["Claim", "Method", "Condition"] as const).map((kind, index) => ({
      id: `${paper.id}-edge-${kind}`,
      source: index ? `${paper.id}-Claim` : paper.id,
      target: `${paper.id}-${kind}`,
      relation: index ? "UNIT_MEMBER" : "HAS_CORE_CLAIM",
      label_zh: index ? "结论支撑" : "核心结论",
      epistemic_status: "navigation",
      review_status: "not_applicable",
      is_dashed: false,
      detail_ref: null,
    })),
  ),
  paper_builds: papers.map((paper) => ({
    paper_id: paper.id,
    title: paper.title,
    document_version_id: `${paper.id}-version`,
    candidate_count: 3,
    published_units: 1,
    extraction_job_id: null,
    extraction_status: "succeeded",
    completed_batches: 1,
    total_batches: 1,
    extraction_incomplete: false,
    active: false,
    ranking_status: "complete",
    selection_mode: "ranked",
  })),
  selections: Object.fromEntries(papers.map((paper) => [paper.id, 1])),
  coverage_gaps: [],
  context_node_ids: [],
  build_state: "complete",
  has_more: false,
  next_cursor: null,
};
const initialLayout: Layout = {
  version: 1,
  zoom: 1,
  pan_x: 55,
  pan_y: 40,
  positions: nodes.map((node, index) => ({
    node_id: node.id,
    x: 90 + Math.floor(index / 4) * 210,
    y: 65 + (index % 4) * 100,
    pinned: node.id === "paper-1-Claim",
  })),
};
const layoutStorageKey = "researchgraph.synthetic-workspace.server-layout";
// Persist only this synthetic engine fixture across a page reload so the real
// workspace can prove it restores the API's saved layout, not a retained DOM.
let layout: Layout = JSON.parse(
  sessionStorage.getItem(layoutStorageKey) ?? JSON.stringify(initialLayout),
) as Layout;

window.workspaceHarness = { requests: [] };
mockIPC((command, args) => {
  if (command !== "engine_request")
    throw new Error(`Unexpected synthetic IPC command: ${command}`);
  const request = args as IPCRequest;
  window.workspaceHarness.requests.push(structuredClone(request));
  const url = new URL(request.path, "http://synthetic.invalid");
  const path = url.pathname;
  const body = request.body ?? {};
  if (path.endsWith("/papers") && path.includes("/projects/")) {
    const cursor = Number(url.searchParams.get("cursor") ?? 0);
    return structuredClone({
      items: papers.slice(cursor, cursor + 2),
      next_cursor: cursor === 0 ? 2 : null,
    });
  }
  if (path.endsWith("/graph/projection")) {
    const visible = graph.nodes.filter(
      (node) => !body.paper_id || node.paper_id === body.paper_id,
    );
    const ids = new Set(visible.map((node) => node.id));
    return structuredClone({
      ...graph,
      nodes: visible,
      edges: graph.edges.filter(
        (edge) => ids.has(edge.source) && ids.has(edge.target),
      ),
      paper_builds: graph.paper_builds?.filter(
        (paper) => !body.paper_id || paper.paper_id === body.paper_id,
      ),
    });
  }
  if (path.endsWith("/graph/layout")) {
    if (request.method === "POST") {
      if (body.expected_version !== layout.version)
        throw new Error("Synthetic layout revision conflict");
      layout = {
        version: layout.version + 1,
        positions: body.positions as Layout["positions"],
        zoom: body.zoom as number,
        pan_x: body.pan_x as number,
        pan_y: body.pan_y as number,
      };
      sessionStorage.setItem(layoutStorageKey, JSON.stringify(layout));
    }
    return structuredClone(layout);
  }
  if (path.includes("/graph/nodes/")) {
    const node = nodes.find(
      (candidate) => candidate.id === path.split("/").at(-1),
    );
    if (!node) throw new Error("Unknown synthetic graph node");
    return {
      id: node.id,
      paper_id: node.paper_id,
      title: node.label_zh,
      document_version_ids: [`${node.paper_id}-version`],
      zotero_url: null,
      node: null,
      display: {
        label_zh: node.label_zh,
        label_en: node.label_en,
        summary_zh: "仅用于界面回归的合成知识。",
      },
      related: [],
      evidence: [],
      counts: {},
      graph_revision: 1,
    };
  }
  if (path.endsWith("/graph-selection")) {
    const paperId = path.split("/").at(-2)!;
    return {
      selection_revision: 1,
      document_version_id: `${paperId}-version`,
      density: "standard",
      build_state: "complete",
      build: {
        candidate_count: 3,
        extraction_incomplete: false,
        completed_batches: 1,
        total_batches: 1,
        active: false,
      },
    };
  }
  if (path.endsWith("/candidates")) return { items: [], next_cursor: null };
  if (path.startsWith("/api/v1/papers/")) {
    const paper = papers.find(
      (candidate) => candidate.id === path.split("/").at(-1),
    );
    if (!paper) throw new Error("Unknown synthetic paper");
    return { paper, revisions: [], sources: [], zotero_links: [] };
  }
  if (path.endsWith("/jobs")) return { items: [], next_cursor: null };
  throw new Error(
    `Unexpected synthetic API request: ${request.method} ${path}`,
  );
});

const client = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <main style={{ margin: "0 auto", padding: 24, maxWidth: 1200 }}>
        <GraphWorkspace projectId="synthetic-workspace" connected />
      </main>
    </QueryClientProvider>
  </StrictMode>,
);
