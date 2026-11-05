import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { mockIPC } from "@tauri-apps/api/mocks";
import { QueryPanel } from "../src/QueryPanel";
import type { Job } from "../src/api";
import type {
  QueryAnswerView,
  QueryPreparation,
  QueryRetrieval,
  QueryRequest,
  QueryReference,
  SavedReading,
} from "../src/queryApi";
import "../src/style.css";

type IPCRequest = {
  method: string;
  path: string;
  body: Record<string, unknown> | null;
  idempotencyKey: string | null;
};
declare global {
  interface Window {
    queryHarness: {
      requests: IPCRequest[];
      unexpected: string[];
      graphFocuses: string[];
    };
  }
}

// Synthetic, distributable fixtures only. Unexpected IPC is rejected: this
// harness cannot access an engine, local files, credentials, or a real model.
const project = "synthetic-query";
const now = "2026-11-04T08:00:00+08:00";
const storageKey = "researchgraph.synthetic-query.fixture";
const mode = new URLSearchParams(location.search).get("mode") ?? "success";
const browseSources: QueryReference[] = Array.from({ length: 24 }, (_, i) => ({
  ref: `S${String(i + 1).padStart(5, "0")}`,
  type: "evidence",
  id: `browse-evidence-${i + 1}`,
  quote: `Synthetic source ${i + 1}.`,
  paper_id: i === 23 ? "paper-2" : "paper-1",
  document_version_id: i === 23 ? "version-2" : "version-1",
  page_index: i,
}));
const retrieval: QueryRetrieval = {
  status: "matched",
  hits: [
    {
      entry_id: "hit-claim",
      source_kind: "knowledge",
      object_id: "claim",
      text: "合成方法在20 C下有效。",
      reasons: ["exact_term"],
      data: {},
    },
  ],
  independent_sources: ["paper-1:version-1", "paper-2:version-2"],
  graph: {
    nodes: [{ id: "claim", kind: "claim", text: "合成有效性" }],
    paths: [],
  },
  presentation: {
    hits: {
      "hit-claim": {
        title: "合成论文1",
        original: "The synthetic method works at 20 C.",
        summary_zh: "合成方法在20 C下有效。",
        summary_origin: "extracted_translation",
        paper_id: "paper-1",
        page_index: 1,
        section_path: ["Results"],
      },
    },
    references: {
      S00001: {
        title: "合成论文1",
        original: "Synthetic result under 20 C.",
        summary_zh: "已有中文要点：该结果在20 C下报告。",
        summary_origin: "extracted_translation",
        paper_id: "paper-1",
        page_index: 1,
        section_path: ["Results"],
      },
    },
  },
};
const emptyState: {
  prepared: QueryPreparation | null;
  answer: QueryAnswerView | null;
  saved: SavedReading[];
} = {
  prepared: null,
  answer: null,
  saved: [],
};
let state = JSON.parse(
  sessionStorage.getItem(storageKey) ?? JSON.stringify(emptyState),
) as typeof emptyState;
function persist() {
  sessionStorage.setItem(storageKey, JSON.stringify(state));
}
function reject(message: string): never {
  window.queryHarness.unexpected.push(message);
  throw new Error(message);
}
function job(status: Job["status"]): Job {
  return {
    id: "job",
    project_id: project,
    kind: "query_answer",
    status,
    stage: "reasoning",
    attempt: 1,
    error: null,
    result: null,
    resume_adapter_available: false,
    created_at: now,
    updated_at: now,
  };
}
function answer(success: boolean): QueryAnswerView {
  const result: QueryAnswerView = {
    query_id: "query",
    status: success ? "succeeded" : mode === "running" ? "running" : "failed",
    job_id: "job",
    can_continue: !success && mode !== "running",
    error_code: success || mode === "running" ? null : "MODEL_TIMEOUT",
    error:
      success || mode === "running"
        ? null
        : "模型请求超时，供应商费用未知；可手动继续一次。",
    request_count: success && mode === "timeout" ? 2 : 1,
    request_limit: 2,
    model_runs: [
      {
        id: "model-run",
        sequence: 1,
        status: success ? "succeeded" : "failed",
        usage: success
          ? { prompt_tokens: 100, completion_tokens: 20, total_tokens: 120 }
          : {},
        duration_seconds: 1.2,
        finish_reason: success ? "stop" : null,
        error_code: success ? null : "MODEL_TIMEOUT",
        error: null,
        cost_known: false,
      },
    ],
    answer: success
      ? {
          answer_version_id: "answer-1",
          query_run_id: "query",
          revision: 1,
          input_hash: "a".repeat(64),
          status: "validated",
          knowledge_status: "source_grounded",
          passages: [
            {
              local_ref: "p1",
              text: "作者报告：合成方法在20 C条件下有效。",
              attribution: "paper_author",
              source_refs: ["S00001"],
              caveats: ["不能外推其他温度"],
            },
          ],
          limitations: ["两篇来源中仅一篇报告温度"],
        }
      : null,
  };
  if (success && mode === "browse" && result.answer) {
    result.answer.passages = Array.from({ length: 14 }, (_, i) => ({
      local_ref: `p${i + 1}`,
      text: i === 13 ? "两篇论文的综合比较。" : `分页回答${i + 1}。`,
      attribution: i === 13 ? "model_synthesis" : "paper_author",
      source_refs:
        i === 0
          ? browseSources.slice(0, 23).map((r) => r.ref)
          : i === 12
            ? [browseSources[23].ref]
            : i === 13
              ? [browseSources[0].ref, browseSources[23].ref]
              : [browseSources[i].ref],
      caveats: [],
    }));
  }
  return result;
}
window.queryHarness = { requests: [], unexpected: [], graphFocuses: [] };
mockIPC((command, args) => {
  if (command !== "engine_request")
    return reject(`Unexpected IPC command ${command}`);
  const request = args as IPCRequest;
  window.queryHarness.requests.push(structuredClone(request));
  const url = new URL(request.path, "http://synthetic.invalid");
  const path = url.pathname;
  const body = request.body ?? {};
  if (path.endsWith("/settings/models"))
    return {
      profiles: [],
      roles: { extraction: "synthetic", reasoning: "synthetic" },
    };
  if (path === `/api/v1/projects/${project}/papers`) {
    const page = url.searchParams.get("cursor") === "2" ? 2 : 0;
    return {
      items: [1, 2, 3].slice(page, page + 2).map((n) => ({
        id: `paper-${n}`,
        project_id: project,
        title: `合成论文${n}`,
        created_at: now,
      })),
      next_cursor: page ? null : 2,
    };
  }
  if (path.endsWith("/query/search")) return structuredClone(retrieval);
  if (path.endsWith("/query/search/page")) {
    const page = Number(body.page ?? 1);
    const filter = (body.display_paper_ids ?? []) as string[];
    const hits =
      mode === "browse"
        ? Array.from({ length: 23 }, (_, i) => ({
            ...retrieval.hits[0],
            entry_id: `browse-hit-${i + 1}`,
            object_id: `browse-node-${i + 1}`,
            text: `分页来源${i + 1}`,
            data: { paper_id: `paper-${(i % 3) + 1}` },
          }))
        : structuredClone(retrieval.hits);
    const displays = Object.fromEntries(
      hits.map((hit, i) => [
        hit.entry_id,
        {
          ...retrieval.presentation!.hits["hit-claim"],
          title: mode === "browse" ? `合成论文${(i % 3) + 1}` : "合成论文1",
          paper_id: mode === "browse" ? `paper-${(i % 3) + 1}` : "paper-1",
          paper_ids: [mode === "browse" ? `paper-${(i % 3) + 1}` : "paper-1"],
          original:
            mode === "browse"
              ? `Synthetic preview ${i + 1}.`
              : retrieval.presentation!.hits["hit-claim"].original,
          summary_zh:
            mode === "browse"
              ? `分页来源${i + 1}`
              : retrieval.presentation!.hits["hit-claim"].summary_zh,
          graph_presence: {
            state: i % 2 ? "retrieval_only" : "in_graph",
            representation: i % 2 ? null : "node",
            node_ids: i % 2 ? [] : [hit.object_id],
            graph_roles: i % 2 ? [] : ["core"],
            graph_revision: 1,
          },
        },
      ]),
    );
    const selected = hits.filter(
      (hit) =>
        !filter.length || filter.includes(displays[hit.entry_id].paper_id),
    );
    const items = selected.slice((page - 1) * 10, page * 10);
    return {
      status: selected.length ? "matched" : "no_evidence",
      hits: items,
      total: selected.length,
      page,
      page_size: 10,
      total_pages: Math.max(1, Math.ceil(selected.length / 10)),
      result_hash: "b".repeat(64),
      graph_node_count: 12,
      independent_sources: retrieval.independent_sources,
      presentation: {
        hits: Object.fromEntries(
          items.map((hit) => [hit.entry_id, displays[hit.entry_id]]),
        ),
        references: {},
      },
    };
  }
  if (path.endsWith("/query/prepare")) {
    if (body.purpose !== "model")
      return reject("Generation preparation must use model purpose");
    state.prepared = {
      query_id: "query",
      status: "prepared",
      input_hash: "a".repeat(64),
      error: null,
      presentation: retrieval.presentation,
      snapshot: {
        request: body as unknown as QueryRequest,
        retrieval,
        context: {
          status: "ready",
          coverage_gaps: ["仅覆盖已解析原文"],
          references: [
            {
              ref: "S00001",
              type: "evidence",
              id: "evidence",
              quote: "Synthetic result under 20 C.",
              paper_id: "paper-1",
              document_version_id: "version-1",
              page_index: 1,
              start: 0,
              end: 28,
              current_file_status: "not_checked",
            },
          ],
        },
        model: { model: "synthetic-no-network" },
      },
    };
    if (mode === "browse") {
      state.prepared.snapshot.context.references = browseSources;
      state.prepared.presentation!.references = Object.fromEntries(
        browseSources.map((source) => [
          source.ref,
          {
            title: source.paper_id === "paper-1" ? "合成论文1" : "合成论文2",
            original: source.quote!,
            summary_zh: `中文证据${source.id}`,
            summary_origin: "extracted_translation",
            paper_id: source.paper_id,
            paper_ids: [source.paper_id!],
            section_path: ["Results"],
          },
        ]),
      );
    }
    persist();
    return structuredClone(state.prepared);
  }
  if (path.endsWith("/query/runs/query/generate")) {
    if (!state.prepared || body.allow_network !== true)
      return reject("Missing preparation or consent");
    if (state.answer?.status === "succeeded")
      return structuredClone(job("succeeded"));
    state.answer = answer(
      mode === "success" ||
        mode === "browse" ||
        body.continue_requested === true,
    );
    persist();
    return structuredClone(
      job(
        state.answer.status === "running"
          ? "running"
          : state.answer.status === "failed"
            ? "failed"
            : "succeeded",
      ),
    );
  }
  if (path.endsWith("/query/runs/query/answer")) {
    return structuredClone(
      state.answer ?? {
        query_id: "query",
        status: "not_started",
        job_id: null,
        can_continue: false,
        answer: null,
        model_runs: [],
        error: null,
        error_code: null,
        request_count: 0,
        request_limit: 2,
      },
    );
  }
  if (path.endsWith("/query/runs/query")) {
    if (!state.prepared) return reject("Unknown synthetic query");
    return structuredClone(state.prepared);
  }
  if (path.endsWith("/query/runs")) {
    return {
      items: state.prepared
        ? [
            {
              query_id: "query",
              question: state.prepared.snapshot.request.question,
              created_at: now,
              status: state.answer?.status ?? "prepared",
              job_id: state.answer?.job_id ?? null,
              paper_ids: ["paper-1"],
            },
          ]
        : [],
      next_cursor: null,
    };
  }
  if (path.endsWith("/query/documents")) return { items: [] };
  if (path.endsWith("/query/runs/query/save")) {
    if (
      body.expected_input_hash !== state.answer?.answer?.input_hash ||
      !Array.isArray(body.selected_passage_refs) ||
      !body.selected_passage_refs.includes("p1")
    )
      return reject("Save must bind validated selected passage");
    if (!state.saved.length)
      state.saved.push({
        saved_id: "saved-1",
        title: "合成阅读综合",
        kind: "synthesis",
        document_id: "document",
        version_id: "document-v1",
        revision: 1,
        created_at: now,
        source_query_id: "query",
        answer_version_id: "answer-1",
        content_state: "valid",
        paper_ids: ["paper-1"],
        file_state: "not_exported",
        annotation: "",
        metadata_revision: 0,
        removed_at: null,
        passages: [
          {
            id: "saved-p1",
            local_ref: "p1",
            text: state.answer!.answer!.passages[0].text,
            attribution: "paper_author",
            caveats: ["不能外推其他温度"],
            content_state: "valid",
            paper_ids: ["paper-1"],
            issues: [],
          },
        ],
      });
    persist();
    return structuredClone(state.saved[0]);
  }
  if (path.endsWith("/query/saved"))
    return structuredClone({
      items: state.saved.filter((item) => !item.removed_at),
    });
  if (path.endsWith("/query/saved/saved-1"))
    return structuredClone(state.saved[0]);
  if (path.endsWith("/query/saved/saved-1/annotation")) {
    const saved = state.saved[0];
    if (
      request.method !== "PUT" ||
      !saved ||
      saved.removed_at ||
      body.expected_revision !== (saved.metadata_revision ?? 0) ||
      typeof body.annotation !== "string"
    )
      return reject("Annotation requires the saved metadata baseline");
    saved.annotation = body.annotation;
    saved.metadata_revision = (saved.metadata_revision ?? 0) + 1;
    persist();
    return structuredClone(saved);
  }
  if (path.endsWith("/query/saved/saved-1/remove")) {
    const saved = state.saved[0];
    if (
      request.method !== "POST" ||
      !saved ||
      body.expected_revision !== (saved.metadata_revision ?? 0)
    )
      return reject("Removal requires the saved metadata baseline");
    saved.removed_at = now;
    saved.metadata_revision = (saved.metadata_revision ?? 0) + 1;
    persist();
    return {
      saved_id: saved.saved_id,
      removed_at: saved.removed_at,
      metadata_revision: saved.metadata_revision,
    };
  }
  if (path.endsWith("/query/derived-graph"))
    return {
      nodes: state.saved.some((item) => !item.removed_at)
        ? [
            {
              id: "source-claim",
              kind: "Claim",
              label: "来源：合成结论",
              source_id: "claim",
              layer: "source",
            },
            {
              id: "saved-1",
              kind: "Synthesis",
              label: "合成阅读综合",
              saved_id: "saved-1",
              layer: "derived",
            },
            {
              id: "source-chunk",
              kind: "chunk",
              label: "原文：合成证据",
              source_id: "chunk",
              layer: "source_reference",
            },
          ]
        : [],
      edges: state.saved.some((item) => !item.removed_at)
        ? [
            {
              id: "derived",
              source: "saved-1",
              target: "source-claim",
              relation: "DERIVED_FROM",
              epistemic_status: "derived_reference",
            },
            {
              id: "derived-chunk",
              source: "saved-1",
              target: "source-chunk",
              relation: "DERIVED_FROM",
              epistemic_status: "derived_reference",
            },
          ]
        : [],
    };
  if (path === "/api/v1/papers/paper-1")
    return {
      paper: {
        id: "paper-1",
        project_id: project,
        title: "合成论文1",
        created_at: now,
      },
      revisions: [],
      sources: [],
      zotero_links: [],
    };
  if (path === "/api/v1/evidence/evidence/preview") throw "合成离线附件";
  if (path === "/api/v1/jobs/job/cancel") {
    if (!state.answer) return reject("No job to cancel");
    state.answer = {
      ...state.answer,
      status: "cancelled",
      can_continue: false,
    };
    persist();
    return structuredClone(job("cancelled"));
  }
  return reject(`Unexpected API request ${request.method} ${path}`);
});

function Harness() {
  const [focus, setFocus] = useState("");
  return (
    <main style={{ margin: "0 auto", padding: 24, maxWidth: 1160 }}>
      <p>自动化回归 · 全部为合成资料 · 不连接模型或数据库</p>
      {focus && <p role="status">图谱定位：{focus}</p>}
      <QueryPanel
        projectId={project}
        connected
        onGraphNode={(id) => {
          window.queryHarness.graphFocuses.push(id);
          setFocus(id);
        }}
      />
    </main>
  );
}
const client = new QueryClient({
  defaultOptions: {
    queries: { retry: false, refetchOnWindowFocus: false },
    mutations: { retry: false },
  },
});
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>
  </StrictMode>,
);
