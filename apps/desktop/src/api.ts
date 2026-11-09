import { invoke } from "@tauri-apps/api/core";

export type Project = {
  id: string;
  name: string;
  description: string;
  experience_mode: "lite";
  created_at: string;
};
export type ProjectList = { items: Project[]; next_cursor: number | null };
export type Paper = {
  id: string;
  project_id: string;
  title: string;
  created_at: string;
};
export type PaperList = { items: Paper[]; next_cursor: number | null };
export type Revision = {
  id: string;
  paper_id: string;
  sha256: string;
  parser_version: string;
  page_count: number;
  warnings: string[];
  created_at: string;
};
export type SourceCheck = {
  original: { state: string };
  managed: { state: string } | null;
  checked_at: string;
};
export type Source = {
  id: string;
  revision_id: string;
  path: string;
  mode: "reference" | "managed";
  generation: number;
  last_check: SourceCheck | null;
};
export type PaperDetail = {
  paper: Paper;
  revisions: Revision[];
  sources: Source[];
  zotero_links?: { url?: string; item_key?: string; attachment_key?: string }[];
};
export type Chunk = {
  id: string;
  revision_id: string;
  page_index: number;
  page_label: string;
  block_index: number;
  text: string;
  bbox: number[];
};
export type ChunkList = { items: Chunk[]; next_cursor: number | null };
export type Section = {
  id: string;
  title: string;
  ordinal: number;
  role: string;
  parent_id: string | null;
  level: number;
  start_page: number | null;
  end_page: number | null;
  excluded: boolean;
  text: string;
  chunk_ids: string[];
};
export type Structure = { document_version_id: string; sections: Section[] };
export type SearchHit = {
  chunk_id: string;
  section_id: string | null;
  document_version_id: string;
  paper_id: string;
  text: string;
  page_index: number;
  page_label: string;
  score: number;
};
export type SearchResult = { items: SearchHit[]; query: string };
export type Job = {
  id: string;
  kind: string;
  project_id: string | null;
  status:
    "queued" | "running" | "succeeded" | "failed" | "cancelled" | "interrupted";
  stage: string | null;
  attempt: number;
  error: string | null;
  result: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};
export type JobList = { items: Job[]; next_cursor: string | null };
export type Health = {
  status: "ok";
  version: string;
  protocol_version: number;
  schema_version: string;
  database: "ready";
  fts5: boolean;
};
export type LiteUsage = {
  project_id: string;
  paper_id: string | null;
  calls: number;
  retry_count: number;
  cache_hits: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  unknown_usage_calls: number;
  calls_known: boolean;
  unrecorded_runs: number;
  unattributed_runs: number;
  estimated_usage_calls: number;
  cost_estimate: number | null;
  cost_known: boolean;
  by_kind: {
    task_kind: string;
    calls: number;
    retry_count: number;
    cache_hits: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    unknown_usage_calls: number;
    calls_known: boolean;
    unrecorded_runs: number;
    unattributed_runs: number;
    estimated_usage_calls: number;
    cost_estimate: number | null;
    cost_known: boolean;
  }[];
};
export type HostStatus = {
  running: boolean;
  data_dir: string;
  error: string | null;
};

export type OverviewNode = {
  id: string;
  type: "RESEARCH_QUESTION" | "CONCEPT" | "METHOD" | "CONTRIBUTION" | "FINDING";
  label_zh: string;
  label_en: string | null;
  description_zh: string;
  basis: "EXPLICIT" | "INFERRED";
};
export type OverviewEdge = {
  id: string;
  source: string;
  target: string;
  type:
    | "INVESTIGATES"
    | "USES"
    | "ANALYZES"
    | "YIELDS"
    | "CONTRIBUTES_TO"
    | "RELATED_TO";
  basis: "EXPLICIT" | "INFERRED";
};
export type PaperOverview = {
  schema_version: "paper_overview_graph.v1";
  paper_card: {
    research_question: string;
    motivation: string;
    method_summary: string;
    contributions: string[];
    main_findings: string[];
    limitations: string[];
  };
  graph: { nodes: OverviewNode[]; edges: OverviewEdge[] };
};
export type OverviewView = {
  id: string | null;
  paper_id: string;
  document_version_id: string;
  status: "PENDING" | "COMPLETED" | "FAILED" | null;
  pdf_hash: string | null;
  input_hash: string | null;
  schema_version: string | null;
  prompt_version: string | null;
  provider_id: string | null;
  model_id: string | null;
  generated_at: string | null;
  cache_hit: boolean;
  graph_status: string | null;
  paper_card: PaperOverview["paper_card"] | null;
  graph: PaperOverview["graph"] | null;
  usage: {
    input_tokens: number | null;
    output_tokens: number | null;
    total_tokens: number | null;
    calls: number;
    retry_count: number;
    cost: number | null;
    usage_source: "provider" | "unknown";
  } | null;
  job_id: string | null;
  error_code: string | null;
  error: string | null;
};
export type OverviewLayout = {
  overview_result_id: string;
  positions: { node_id: string; x: number; y: number; pinned: boolean }[];
  viewport?: { x: number; y: number; zoom: number } | null;
};

export async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  key?: string,
): Promise<T> {
  try {
    return await invoke<T>("engine_request", {
      method,
      path,
      body: body ?? null,
      idempotencyKey: key ?? null,
    });
  } catch (error) {
    throw new Error(
      typeof error === "string"
        ? error
        : "本地服务暂时不可用，请检查连接后重试",
    );
  }
}

export const api = {
  structure: (id: string) =>
    request<Structure>("GET", `/api/v1/revisions/${id}/sections`),
  sections: (id: string) =>
    request<Structure>("GET", `/api/v1/revisions/${id}/sections`),
  search: (
    paperId: string,
    query: string,
    revisionId?: string,
    sectionId?: string,
  ) => {
    const params = new URLSearchParams({ q: query, limit: "5" });
    if (revisionId) params.set("revision_id", revisionId);
    if (sectionId) params.set("section_id", sectionId);
    return request<SearchResult>(
      "GET",
      `/api/v1/papers/${paperId}/search?${params.toString()}`,
    );
  },
  zoteroStatus: () =>
    request<{ connected: boolean; error?: string }>(
      "GET",
      "/api/v1/integrations/zotero/status",
    ),
  checkSource: (source: Source) =>
    request<Job>(
      "POST",
      `/api/v1/sources/${source.id}/check`,
      { expected_generation: source.generation },
      crypto.randomUUID(),
    ),
  relocateSource: (source: Source) =>
    invoke<Job | null>("relocate_source_file", {
      sourceId: source.id,
      expectedGeneration: source.generation,
      idempotencyKey: crypto.randomUUID(),
    }),
  projectJobs: (projectId: string, cursor: string | null = null) =>
    request<JobList>(
      "GET",
      `/api/v1/projects/${projectId}/jobs?limit=10${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
    ),
  importPdf: (projectId: string, mode: "reference" | "managed") =>
    invoke<Job | null>("import_pdf_file", {
      projectId,
      mode,
      idempotencyKey: crypto.randomUUID(),
    }),
  papers: (projectId: string, cursor = 0) =>
    request<PaperList>(
      "GET",
      `/api/v1/projects/${projectId}/papers?cursor=${cursor}&limit=50`,
    ),
  liteUsage: (projectId: string, paperId?: string) =>
    request<LiteUsage>(
      "GET",
      `/api/v1/projects/${projectId}/lite/usage${paperId ? `?paper_id=${encodeURIComponent(paperId)}` : ""}`,
    ),
  paper: (paperId: string) =>
    request<PaperDetail>("GET", `/api/v1/papers/${paperId}`),
  chunks: (revisionId: string, cursor = 0) =>
    request<ChunkList>(
      "GET",
      `/api/v1/revisions/${revisionId}/chunks?cursor=${cursor}&limit=50`,
    ),
  host: () => invoke<HostStatus>("host_status"),
  restart: () => invoke<HostStatus>("restart_engine"),
  health: () => request<Health>("GET", "/api/v1/health"),
  projects: (cursor = 0) =>
    request<ProjectList>("GET", `/api/v1/projects?cursor=${cursor}&limit=50`),
  createProject: (body: { name: string; description: string }, key: string) =>
    request<Project>(
      "POST",
      "/api/v1/projects",
      { ...body, experience_mode: "lite" },
      key,
    ),
  jobs: () => request<Job[]>("GET", "/api/v1/jobs"),
  job: (id: string) => request<Job>("GET", `/api/v1/jobs/${id}`),
  diagnose: (key: string) =>
    request<Job>("POST", "/api/v1/jobs", { kind: "diagnostics" }, key),
  jobAction: (id: string, action: "cancel" | "retry", key: string) =>
    request<Job>("POST", `/api/v1/jobs/${id}/${action}`, null, key),
  overview: (paperId: string, revisionId?: string) =>
    request<OverviewView>(
      "GET",
      `/api/v1/papers/${paperId}/overview${revisionId ? `?document_version_id=${encodeURIComponent(revisionId)}` : ""}`,
    ),
  generateOverview: (
    paperId: string,
    revisionId: string,
    allowNetwork: boolean,
    retryFailed = false,
    forceRegenerate = false,
  ) =>
    request<OverviewView>(
      "POST",
      `/api/v1/papers/${paperId}/overview/generate`,
      {
        document_version_id: revisionId,
        allow_network: allowNetwork,
        retry_failed: retryFailed,
        force_regenerate: forceRegenerate,
      },
      crypto.randomUUID(),
    ),
  overviewLayout: (paperId: string, resultId: string) =>
    request<OverviewLayout>(
      "GET",
      `/api/v1/papers/${paperId}/overview/graph/layout?overview_result_id=${encodeURIComponent(resultId)}`,
    ),
  saveOverviewLayout: (paperId: string, layout: OverviewLayout) =>
    request<OverviewLayout>(
      "PUT",
      `/api/v1/papers/${paperId}/overview/graph/layout`,
      layout,
      crypto.randomUUID(),
    ),
  resetOverviewLayout: (paperId: string, resultId: string) =>
    request<OverviewLayout>(
      "POST",
      `/api/v1/papers/${paperId}/overview/graph/layout/reset`,
      { overview_result_id: resultId },
      crypto.randomUUID(),
    ),
};
