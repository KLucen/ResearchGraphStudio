import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "../src/App";
import { api } from "../src/api";
import {
  knowledgeApi,
  type KnowledgeLayout,
  type KnowledgeSettings,
} from "../src/knowledgeApi";
import {
  knowledgePapers,
  knowledgeReport,
  knowledgeSettings,
} from "../src/knowledgeFixtures";
import "../src/style.css";

declare global {
  interface Window {
    __knowledgeModelCalls: unknown[];
    __knowledgeLayoutWrites: number;
  }
}
window.__knowledgeModelCalls = [];
window.__knowledgeLayoutWrites = 0;
const load = <T,>(key: string, fallback: T): T =>
  JSON.parse(localStorage.getItem(`kb-fixture:${key}`) ?? "null") ?? fallback;
const store = (key: string, value: unknown) =>
  localStorage.setItem(`kb-fixture:${key}`, JSON.stringify(value));
let papers = load("papers", knowledgePapers());
let report = load("report", knowledgeReport());
let settings = load("settings", knowledgeSettings);
api.host = async () => ({
  running: true,
  data_dir: "synthetic-data",
  error: null,
});
api.health = async () => ({ status: "ok" }) as never;
api.projects = async () => ({
  items: [
    {
      id: "project-1",
      name: "合成研究项目",
      description: "可分发回归材料",
      experience_mode: "lite",
      created_at: "2026-11-20",
    },
  ],
  next_cursor: null,
});
api.papers = async () => ({ items: [], next_cursor: null });
api.jobs = async () => [];
api.liteUsageGlobal = async () =>
  ({
    calls_known: true,
    calls: 0,
    input_tokens: 0,
    output_tokens: 0,
    cache_hits: 0,
    retry_count: 0,
    unrecorded_runs: 0,
    cost_known: false,
    cost_estimate: null,
    unknown_usage_calls: 0,
    roles: [],
  }) as never;
knowledgeApi.library = async () => ({
  id: "personal",
  name: "个人研究知识库",
  settings,
  created_at: "2026-11-20",
  updated_at: "2026-11-20",
});
knowledgeApi.saveSettings = async (value: KnowledgeSettings) => {
  settings = value;
  store("settings", value);
  return knowledgeApi.library();
};
knowledgeApi.papers = async (filters = {}) => {
  const visible = papers.filter(
    (paper) =>
      (filters.include_archived || !paper.archived) &&
      (!filters.search || paper.title.includes(filters.search)) &&
      (!filters.collection_id ||
        paper.collection_ids.includes(filters.collection_id)),
  );
  return { items: visible, total: visible.length };
};
knowledgeApi.paper = async (id) => papers.find((paper) => paper.id === id)!;
knowledgeApi.updatePaper = async (id, body) => {
  papers = papers.map((paper) =>
    paper.id === id ? { ...paper, ...body } : paper,
  );
  store("papers", papers);
  return papers.find((paper) => paper.id === id)!;
};
knowledgeApi.reports = async () => ({ items: [report], total: 1 });
knowledgeApi.report = async () => report;
knowledgeApi.updateReport = async (_id, body) => {
  report = { ...report, ...body };
  store("report", report);
  return report;
};
knowledgeApi.runs = async () => ({ items: [], total: 0 });
knowledgeApi.collections = async () => ({
  items: [
    {
      id: "collection-1",
      name: "方法比较",
      description: "",
      created_at: "2026-11-20",
    },
  ],
});
knowledgeApi.setCollection = async (id, paperId, included) => {
  papers = papers.map((paper) =>
    paper.id === paperId
      ? {
          ...paper,
          collection_ids: included
            ? [...paper.collection_ids, id]
            : paper.collection_ids.filter((item) => item !== id),
        }
      : paper,
  );
  store("papers", papers);
  return {};
};
knowledgeApi.sources = async () => ({
  items: [
    {
      paper_id: "paper-A",
      project_id: "project-1",
      title: "合成论文 A",
      sources: [
        {
          source_kind: "local_revision",
          source_id: "revision-A",
          label: "本地解析材料",
          overview_result_id: "overview-A",
          has_overview: true,
        },
        {
          source_kind: "model_parse",
          source_id: "parse-A",
          label: "模型解析材料",
          has_overview: false,
        },
      ],
    },
  ],
});
knowledgeApi.collect = async () => papers[0];
knowledgeApi.extract = async (body) => {
  window.__knowledgeModelCalls.push({ kind: "extract", ...body });
  return { id: "run-1", status: "queued", created_at: "2026-11-20" };
};
knowledgeApi.connect = async (versionId, body) => {
  window.__knowledgeModelCalls.push({ kind: "connect", versionId, ...body });
  return { id: "run-2", status: "queued", created_at: "2026-11-20" };
};
const initialLayout: KnowledgeLayout = {
  view_key: "library:all:all",
  layout: {
    viewport: { x: 80, y: 80, zoom: 0.75 },
    positions: [
      { node_id: "paper:library-A", x: 90, y: 160, pinned: true },
      { node_id: "paper:library-B", x: 550, y: 160, pinned: true },
      ...["A", "B"].flatMap((letter) =>
        Array.from({ length: 5 }, (_, i) => ({
          node_id: `version:version-${letter}:${letter}-${i}`,
          x: 180 + (i % 3) * 120,
          y: 100 + Math.floor(i / 3) * 180,
          pinned: true,
        })),
      ),
    ],
  },
};
knowledgeApi.layout = async (view_key) =>
  load(`layout:${view_key}`, { ...initialLayout, view_key });
knowledgeApi.saveLayout = async (value) => {
  window.__knowledgeLayoutWrites++;
  store(`layout:${value.view_key}`, value);
  return value;
};
knowledgeApi.export = async () => ({ papers, report });
knowledgeApi.usage = api.liteUsageGlobal;
createRoot(document.getElementById("root")!).render(
  <QueryClientProvider
    client={
      new QueryClient({
        defaultOptions: {
          queries: { retry: false },
          mutations: { retry: false },
        },
      })
    }
  >
    <App />
  </QueryClientProvider>,
);
