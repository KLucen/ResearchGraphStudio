import { request, type Job, type LiteUsage } from "./api";
import type { GraphData } from "./graphTypes";

export type KnowledgeSourceKind = "local_revision" | "model_parse";
export type KnowledgeSettings = {
  auto_collect: boolean;
  auto_connect: boolean;
  allow_network: boolean;
  scope: "project" | "all" | "collection";
  collection_id: string | null;
  max_candidates: number;
  max_requests_per_run: number;
  max_input_tokens: number;
  max_output_tokens: number;
  total_request_limit: number;
};
export type KnowledgeLibrary = {
  id: string;
  name: string;
  settings: KnowledgeSettings;
  created_at: string;
  updated_at: string;
};
export type KnowledgeCollection = {
  id: string;
  name: string;
  description: string;
  created_at: string;
};
export type KnowledgeSourceRef = {
  id?: string;
  source_id?: string;
  source_ref?: string;
  source_kind?: string;
  quote?: string;
  quote_en?: string;
  text?: string;
  page?: number | null;
  page_start?: number | null;
  section_id?: string | null;
  segment_id?: string | null;
  [key: string]: unknown;
};
export type KnowledgeContent = {
  graph?: GraphData;
  paper_card?: {
    research_question?: string;
    motivation?: string;
    method_summary?: string;
    contributions?: string[];
    main_findings?: string[];
    limitations?: string[];
  };
  source_refs?: KnowledgeSourceRef[];
  sources?: KnowledgeSourceRef[];
  warnings?: string[];
  [key: string]: unknown;
};
export type KnowledgeVersion = {
  id: string;
  library_paper_id: string;
  source_kind: string;
  source_id: string;
  source_paper_id: string | null;
  project_id: string | null;
  source_fingerprint: string;
  schema_version: string;
  evidence_status: "legacy" | "grounded";
  content: KnowledgeContent;
  created_at: string;
  provider_id?: string | null;
  model_id?: string | null;
  job_id?: string | null;
};
export type KnowledgePaper = {
  id: string;
  title: string;
  note: string;
  archived: boolean;
  project_ids: string[];
  source_links: {
    paper_id: string | null;
    original_paper_id: string;
    project_id: string;
    source_available: boolean;
  }[];
  collection_ids: string[];
  current_version: KnowledgeVersion | null;
  versions: KnowledgeVersion[];
};
export type KnowledgeSourceOptions = {
  paper_id: string;
  project_id: string;
  title: string;
  sources: {
    source_kind: KnowledgeSourceKind;
    source_id: string;
    label: string;
    overview_result_id?: string | null;
    has_overview: boolean;
  }[];
};
export type KnowledgeRelation = {
  id: string;
  type: string;
  source_version_id?: string;
  target_version_id?: string;
  source_node_id?: string;
  target_node_id?: string;
  target_library_paper_id?: string;
  target_title?: string;
  explanation_zh?: string;
  explanation?: string;
  limitations?: string;
  limitations_zh?: string;
  source_refs?: KnowledgeSourceRef[];
  target_refs?: KnowledgeSourceRef[];
  [key: string]: unknown;
};
export type KnowledgeReport = {
  id: string;
  title: string;
  library_paper_id?: string;
  version_id?: string;
  status: string;
  read: boolean;
  pinned: boolean;
  note: string;
  created_at: string;
  summary?: { text_zh: string; relation_ids: string[] }[];
  summary_zh?: string;
  relations?: KnowledgeRelation[];
  content?: Record<string, unknown>;
  coverage?: Record<string, unknown>;
  stale?: boolean;
  [key: string]: unknown;
};
export type KnowledgeRun = {
  id: string;
  kind?: string;
  status: string;
  error?: string | null;
  job_id?: string | null;
  library_paper_id?: string;
  created_at: string;
  [key: string]: unknown;
};
export type KnowledgeLayout = {
  view_key: string;
  layout: {
    positions: { node_id: string; x: number; y: number; pinned: boolean }[];
    viewport: { x: number; y: number; zoom: number } | null;
  };
};
const base = "/api/v1/knowledge";
const identity = (value: string) => encodeURIComponent(value);
export const knowledgeApi = {
  library: () => request<KnowledgeLibrary>("GET", `${base}/library`),
  saveSettings: (settings: KnowledgeSettings) =>
    request<KnowledgeLibrary>(
      "PATCH",
      `${base}/library`,
      settings,
      crypto.randomUUID(),
    ),
  papers: (
    filters: {
      project_id?: string;
      collection_id?: string;
      search?: string;
      include_archived?: boolean;
      offset?: number;
      limit?: number;
    } = {},
  ) => {
    const query = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== "") query.set(key, String(value));
    });
    query.set("limit", String(filters.limit ?? 50));
    return request<{ items: KnowledgePaper[]; total: number }>(
      "GET",
      `${base}/papers?${query}`,
    );
  },
  paper: (id: string) =>
    request<KnowledgePaper>("GET", `${base}/papers/${identity(id)}`),
  updatePaper: (
    id: string,
    body: {
      title?: string;
      note?: string;
      archived?: boolean;
      current_version_id?: string;
    },
  ) =>
    request<KnowledgePaper>(
      "PATCH",
      `${base}/papers/${identity(id)}`,
      body,
      crypto.randomUUID(),
    ),
  deletePaper: (id: string) =>
    request<{ ok: boolean }>(
      "DELETE",
      `${base}/papers/${identity(id)}`,
      null,
      crypto.randomUUID(),
    ),
  collect: (body: {
    paper_id: string;
    source_kind: KnowledgeSourceKind;
    source_id: string;
    overview_result_id?: string;
  }) =>
    request<KnowledgePaper>(
      "POST",
      `${base}/papers/collect`,
      body,
      crypto.randomUUID(),
    ),
  sources: (projectId?: string) =>
    request<{ items: KnowledgeSourceOptions[] }>(
      "GET",
      `${base}/source-options${projectId ? `?project_id=${identity(projectId)}` : ""}`,
    ),
  extract: (body: {
    paper_id: string;
    source_kind: KnowledgeSourceKind;
    source_id: string;
    allow_network: boolean;
  }) =>
    request<Job | KnowledgeRun>(
      "POST",
      `${base}/extract`,
      body,
      crypto.randomUUID(),
    ),
  connect: (
    versionId: string,
    body: { allow_network: boolean; force_regenerate?: boolean },
  ) =>
    request<Job | KnowledgeRun>(
      "POST",
      `${base}/versions/${identity(versionId)}/connect`,
      body,
      crypto.randomUUID(),
    ),
  collections: () =>
    request<{ items: KnowledgeCollection[] }>("GET", `${base}/collections`),
  createCollection: (name: string) =>
    request<KnowledgeCollection>(
      "POST",
      `${base}/collections`,
      { name, description: "" },
      crypto.randomUUID(),
    ),
  setCollection: (collectionId: string, paperId: string, included: boolean) =>
    request<unknown>(
      included ? "PUT" : "DELETE",
      `${base}/collections/${identity(collectionId)}/papers/${identity(paperId)}`,
      null,
      crypto.randomUUID(),
    ),
  reports: async () => {
    const first = await request<{
      items: KnowledgeReport[];
      total: number;
      unread?: number;
    }>("GET", `${base}/reports?limit=200&offset=0`);
    const items = [...first.items];
    while (items.length < first.total) {
      const page = await request<{ items: KnowledgeReport[]; total: number }>(
        "GET",
        `${base}/reports?limit=200&offset=${items.length}`,
      );
      if (!page.items.length) break;
      items.push(...page.items);
    }
    return { ...first, items };
  },
  report: (id: string) =>
    request<KnowledgeReport>("GET", `${base}/reports/${identity(id)}`),
  updateReport: (
    id: string,
    body: { read?: boolean; pinned?: boolean; note?: string },
  ) =>
    request<KnowledgeReport>(
      "PATCH",
      `${base}/reports/${identity(id)}`,
      body,
      crypto.randomUUID(),
    ),
  runs: () =>
    request<{ items: KnowledgeRun[]; total: number }>("GET", `${base}/runs`),
  retryRun: (id: string) =>
    request<KnowledgeRun>(
      "POST",
      `${base}/runs/${identity(id)}/retry`,
      { allow_network: true },
      crypto.randomUUID(),
    ),
  layout: (viewKey: string) =>
    request<KnowledgeLayout>(
      "GET",
      `${base}/layout?view_key=${identity(viewKey)}`,
    ),
  saveLayout: (value: KnowledgeLayout) =>
    request<KnowledgeLayout>(
      "PUT",
      `${base}/layout`,
      value,
      crypto.randomUUID(),
    ),
  export: () => request<Record<string, unknown>>("GET", `${base}/export`),
  usage: () => request<LiteUsage>("GET", `${base}/usage`),
};
