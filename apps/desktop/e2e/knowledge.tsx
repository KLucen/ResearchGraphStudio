import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "../src/App";
import { api, type Job } from "../src/api";
import { archiveApi, type ArchiveItem } from "../src/archiveApi";
import {
  knowledgeApi,
  type KnowledgeCollection,
  type KnowledgeLayout,
  type KnowledgeSettings,
} from "../src/knowledgeApi";
import {
  knowledgePapers,
  knowledgeReport,
  knowledgeSettings,
} from "../src/knowledgeFixtures";
import { topicGraphApi } from "../src/knowledgeTopicGraph";
import "../src/style.css";

declare global {
  interface Window {
    __knowledgeModelCalls: unknown[];
    __knowledgeLayoutWrites: number;
    __knowledgeJobActions: unknown[];
    __knowledgeLocalRecoveryCalls: unknown[];
    __knowledgeTopicContextReads: {
      collectionId: string;
      paperIds: string[];
    }[];
  }
}
window.__knowledgeModelCalls = [];
window.__knowledgeLayoutWrites = 0;
window.__knowledgeJobActions = [];
window.__knowledgeLocalRecoveryCalls = [];
window.__knowledgeTopicContextReads = [];
const load = <T,>(key: string, fallback: T): T =>
  JSON.parse(localStorage.getItem(`kb-fixture:${key}`) ?? "null") ?? fallback;
const store = (key: string, value: unknown) =>
  localStorage.setItem(`kb-fixture:${key}`, JSON.stringify(value));
let papers = load("papers", knowledgePapers());
let topics = load<KnowledgeCollection[]>("collections", [
  {
    id: "collection-1",
    name: "方法比较",
    description: "",
    created_at: "2026-11-20",
  },
]);
let archivedItems = load<ArchiveItem[]>("archivedItems", []);
let removedArchiveJobs = load<string[]>("removedArchiveJobs", []);
let report = load("report", knowledgeReport());
let settings = load("settings", knowledgeSettings);
api.host = async () => ({
  running: true,
  data_dir: "synthetic-data",
  error: null,
});
api.health = async () =>
  ({
    status: "ok",
    active_jobs: (await api.jobs()).filter((job) =>
      ["queued", "running"].includes(job.status),
    ).length,
  }) as never;
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
api.jobs = async () =>
  load<Job[]>("jobs", []).filter(
    (job) =>
      !archivedItems.some(
        (item) => item.kind === "job" && item.target_id === job.id,
      ) && !removedArchiveJobs.includes(job.id),
  );
api.jobsPage = async () => ({ items: await api.jobs(), next_cursor: null });
archiveApi.list = async (kind, offset, limit) => {
  const items = archivedItems.filter((item) => !kind || item.kind === kind);
  return { items: items.slice(offset, offset + limit), total: items.length };
};
archiveApi.stage = async (kind, id) => {
  const title =
    (kind === "knowledge_collection"
      ? topics.find((topic) => topic.id === id)?.name
      : undefined) ??
    load<Job[]>("jobs", []).find((job) => job.id === id)?.result?.title ??
    id;
  const item: ArchiveItem = {
    id: crypto.randomUUID(),
    kind,
    target_id: id,
    title: String(title),
    archived_at: "2026-11-22T01:00:00Z",
    project_id: null,
    status: "archived",
  };
  archivedItems = [...archivedItems, item];
  store("archivedItems", archivedItems);
  return item;
};
archiveApi.restore = async (id) => {
  archivedItems = archivedItems.filter((item) => item.id !== id);
  store("archivedItems", archivedItems);
  return { ok: true };
};
archiveApi.purge = async (id) => {
  const item = archivedItems.find((entry) => entry.id === id);
  if (item?.kind === "job") {
    removedArchiveJobs = [...removedArchiveJobs, item.target_id];
    store("removedArchiveJobs", removedArchiveJobs);
  }
  return archiveApi.restore(id);
};
api.jobAction = async (id, action) => {
  window.__knowledgeJobActions.push({ id, action });
  return load<Job[]>("jobs", []).find((job) => job.id === id)!;
};
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
  const offset = filters.offset ?? 0;
  const limit = filters.limit ?? 50;
  return {
    items: visible.slice(offset, offset + limit),
    total: visible.length,
  };
};
knowledgeApi.paper = async (id) => papers.find((paper) => paper.id === id)!;
topicGraphApi.externalPapers = async (collectionId, paperIds) => {
  window.__knowledgeTopicContextReads.push({ collectionId, paperIds });
  const items = paperIds.flatMap((id) => {
    const paper = papers.find((item) => item.id === id);
    return !paper?.current_version ||
      paper.archived ||
      paper.collection_ids.includes(collectionId)
      ? []
      : [{ id, title: paper.title, version_id: paper.current_version.id }];
  });
  return { items: items.slice(0, 12), has_more: items.length > 12 };
};
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
knowledgeApi.runs = async () => load("runs", { items: [], total: 0 });
knowledgeApi.localRecovery = async (runId) => {
  window.__knowledgeLocalRecoveryCalls.push({ action: "preview", runId });
  return load("localRecovery", {
    version: "knowledge-local-recovery-1",
    available: false,
    original_nodes: 0,
    original_edges: 0,
    kept_nodes: 0,
    kept_edges: 0,
    excluded_edges: [],
  });
};
knowledgeApi.recoverLocal = async (runId, previewFingerprint) => {
  window.__knowledgeLocalRecoveryCalls.push({
    action: "recover",
    runId,
    previewFingerprint,
  });
  return load("recoveryResult", {
    version_id: "version-recovered",
    library_paper_id: "library-A",
    status: "partial" as const,
    local_recovery: {
      version: "knowledge-local-recovery-1" as const,
      available: false,
      original_nodes: 19,
      original_edges: 20,
      kept_nodes: 19,
      kept_edges: 9,
      excluded_edges: [],
      published_version_id: "version-recovered",
    },
  });
};
knowledgeApi.collections = async () => ({
  items: topics.filter(
    (topic) =>
      !archivedItems.some(
        (item) =>
          item.kind === "knowledge_collection" && item.target_id === topic.id,
      ),
  ),
});
knowledgeApi.createCollection = async (name, description = "") => {
  const topic = {
    id: crypto.randomUUID(),
    name,
    description,
    created_at: "2026-11-24",
  };
  topics = [...topics, topic];
  store("collections", topics);
  return topic;
};
knowledgeApi.updateCollection = async (id, body) => {
  topics = topics.map((topic) =>
    topic.id === id ? { ...topic, ...body } : topic,
  );
  store("collections", topics);
  return topics.find((topic) => topic.id === id)!;
};
knowledgeApi.changeCollectionMembership = async (id, body) => {
  let added = 0;
  let removed = 0;
  papers = papers.map((paper) => {
    if (!body.paper_ids.includes(paper.id)) return paper;
    const current = new Set(paper.collection_ids);
    if (body.action === "remove") {
      if (current.delete(id)) removed++;
    } else {
      if (!current.has(id)) added++;
      current.add(id);
      if (body.action === "move")
        for (const source of body.source_collection_ids)
          if (current.delete(source)) removed++;
    }
    return { ...paper, collection_ids: [...current] };
  });
  store("papers", papers);
  return { ok: true, added, removed };
};
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
          y: 100 + Math.floor(i / 3) * 180 + (letter === "A" ? 0 : 90),
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
