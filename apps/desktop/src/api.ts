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
export type GuideDepth = "quick" | "standard" | "deep";
export type DifficultTerm = { term_en: string; hint_zh: string };
export type ReadingGuide = {
  section_id: string;
  overview_zh: string;
  key_points: string[];
  reading_questions: string[];
  difficult_terms: DifficultTerm[];
  evidence_span_ids: string[];
  needs_more_context: boolean;
  caveats: string[];
};
export type GuideUsage = {
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  calls: number;
  retry_count: number;
  cost: number | null;
  usage_source: "provider" | "unknown";
};
export type GuideEvidence = {
  span_id: string;
  page_start: number;
  page_end: number;
  quote: string;
};
export type SectionGuide = {
  id: string | null;
  paper_id: string;
  document_version_id: string;
  section_id: string;
  depth: GuideDepth;
  source_hash: string;
  input_hash: string;
  schema_version: string;
  prompt_version: string;
  provider_id: string;
  model_id: string;
  status: "PENDING" | "COMPLETED" | "FAILED" | "STALE" | null;
  guide: ReadingGuide | null;
  usage: GuideUsage;
  generated_at: string | null;
  cache_hit: boolean;
  job_id: string | null;
  error_code: string | null;
  error: string | null;
  stale_reason: string | null;
  evidence: GuideEvidence[];
};
export type QAScope = "selection" | "section" | "paper";
export type QAEvidenceCitation = { span_id: string; reason_zh: string };
export type QAAnswer = {
  answer_zh: string;
  evidence_citations: QAEvidenceCitation[];
  insufficient_evidence: boolean;
  uncertainty_zh: string;
  suggest_expand_scope: boolean;
};
export type QAEvidence = {
  span_id: string;
  page_start: number;
  page_end: number;
  quote: string;
};
export type QAUsage = {
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  calls: number;
  retry_count: number;
  cost: number | null;
  usage_source: "provider" | "unknown";
};
export type QAView = {
  id: string | null;
  paper_id: string;
  document_version_id: string;
  section_id: string | null;
  scope: QAScope;
  question: string;
  status: "PENDING" | "COMPLETED" | "FAILED" | "STALE" | null;
  answer: QAAnswer | null;
  usage: QAUsage;
  source_hash: string;
  input_hash: string;
  prompt_version: string;
  schema_version: string;
  provider_id: string;
  model_id: string;
  job_id: string | null;
  error_code: string | null;
  error: string | null;
  retrieval_spans: QAEvidence[];
  cache_hit: boolean;
};
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
export type SearchKeywords = { english_queries: string[] };
export type KeywordView = {
  id: string | null;
  paper_id: string;
  document_version_id: string;
  section_id: string | null;
  question: string;
  local_hit_count: number;
  source_hash: string;
  input_hash: string;
  schema_version: string;
  prompt_version: string;
  provider_id: string;
  model_id: string;
  status: "PENDING" | "COMPLETED" | "FAILED" | "STALE" | null;
  keywords: SearchKeywords | null;
  usage: {
    input_tokens: number | null;
    output_tokens: number | null;
    total_tokens: number | null;
    calls: number;
    retry_count: number;
    cost: number | null;
    usage_source: "provider" | "estimated" | "unknown";
  };
  generated_at: string | null;
  cache_hit: boolean;
  job_id: string | null;
  error_code: string | null;
  error: string | null;
  stale_reason: string | null;
};
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

export type TranslationLaunchMode = "bundled" | "managed" | "manual";
export type TranslationOutputMode = "dual" | "mono";
export type TranslationSettings = {
  enabled: boolean;
  service_url: string;
  launch_mode?: TranslationLaunchMode;
  python_path?: string | null;
  server_path?: string | null;
};
export type TranslationServiceCheck = {
  available: boolean;
  status: string;
  version: string | null;
  active_tasks: number;
  message: string;
};
export type TranslationInput = {
  document_version_id: string;
  profile_id: string;
  output_mode: TranslationOutputMode;
  page_start?: number;
  page_end?: number;
  max_calls: number;
  max_input_tokens: number;
};
export type TranslationPreparation = {
  paper_id: string;
  document_version_id: string;
  source_hash: string;
  page_start: number;
  page_end: number;
  page_count: number;
  source_characters: number;
  estimated_input_tokens: number;
  estimate_is_limit: false;
  estimate_note: string;
  profile_id: string;
  model_id: string;
  cache_hit: boolean;
  cached_translation_id: string | null;
  service_ready: boolean;
  active_tasks: number;
  warnings: string[];
  prepare_fingerprint: string;
  launch_mode?: TranslationLaunchMode;
  output_mode?: TranslationOutputMode | "both";
};
export type TranslationView = {
  id: string;
  paper_id: string;
  document_version_id: string;
  source_hash: string;
  profile_id: string;
  model_id: string;
  status:
    | "PENDING"
    | "RUNNING"
    | "COMPLETED"
    | "FAILED"
    | "CANCELLED"
    | "INTERRUPTED";
  page_start: number;
  page_end: number;
  page_count: number;
  progress: number;
  stage: string | null;
  job_id: string | null;
  external_task_id: string | null;
  external_state: "not_started" | "active" | "completed" | "failed" | "unknown";
  cache_hit: boolean;
  error_code: string | null;
  error: string | null;
  warnings: string[];
  artifacts: {
    kind: "mono" | "dual";
    sha256: string;
    size_bytes: number;
    page_count: number;
  }[];
  usage: {
    calls: number;
    retry_count: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    unknown_usage_calls: number;
    cost_estimate: number | null;
    cost_known: boolean;
  };
  max_calls: number;
  max_input_tokens: number;
  created_at: string;
  updated_at: string;
  launch_mode?: TranslationLaunchMode;
  output_mode?: TranslationOutputMode | "both";
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
  translationSettings: () =>
    request<TranslationSettings>("GET", "/api/v1/settings/translation"),
  saveTranslationSettings: (body: TranslationSettings) =>
    request<TranslationSettings>("PUT", "/api/v1/settings/translation", body),
  checkTranslationService: () =>
    request<TranslationServiceCheck>(
      "POST",
      "/api/v1/settings/translation/check",
    ),
  translations: (paperId: string, revisionId: string) =>
    request<TranslationView[]>(
      "GET",
      `/api/v1/papers/${paperId}/translations?document_version_id=${encodeURIComponent(revisionId)}`,
    ),
  prepareTranslation: (paperId: string, body: TranslationInput) =>
    request<TranslationPreparation>(
      "POST",
      `/api/v1/papers/${paperId}/translations/prepare`,
      body,
    ),
  createTranslation: (
    paperId: string,
    body: TranslationInput & {
      expected_fingerprint: string;
      allow_network: boolean;
      exclusive_service: boolean;
    },
  ) =>
    request<TranslationView>(
      "POST",
      `/api/v1/papers/${paperId}/translations`,
      body,
      crypto.randomUUID(),
    ),
  cancelTranslation: (paperId: string, id: string) =>
    request<TranslationView>(
      "POST",
      `/api/v1/papers/${paperId}/translations/${id}/cancel`,
      {},
      crypto.randomUUID(),
    ),
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
  expandSearchKeywords: (
    paperId: string,
    body: {
      document_version_id: string;
      section_id?: string;
      question: string;
      allow_network: boolean;
    },
  ) =>
    request<KeywordView>(
      "POST",
      `/api/v1/papers/${paperId}/qa/keywords`,
      body,
      crypto.randomUUID(),
    ),
  keyword: (paperId: string, keywordId: string) =>
    request<KeywordView>(
      "GET",
      `/api/v1/papers/${paperId}/qa/keywords/${encodeURIComponent(keywordId)}`,
    ),
  sectionGuide: (
    paperId: string,
    sectionId: string,
    revisionId: string,
    depth: GuideDepth = "standard",
  ) =>
    request<SectionGuide | null>(
      "GET",
      `/api/v1/papers/${paperId}/sections/${sectionId}/guide?document_version_id=${encodeURIComponent(revisionId)}&depth=${depth}`,
    ),
  sectionGuides: (
    paperId: string,
    revisionId: string,
    sectionId?: string,
    depth?: GuideDepth,
  ) => {
    const params = new URLSearchParams({
      document_version_id: revisionId,
    });
    if (sectionId) params.set("section_id", sectionId);
    if (depth) params.set("depth", depth);
    return request<SectionGuide[]>(
      "GET",
      `/api/v1/papers/${paperId}/section-guides?${params.toString()}`,
    );
  },
  generateSectionGuide: (
    paperId: string,
    sectionId: string,
    revisionId: string,
    depth: GuideDepth,
    allowNetwork: boolean,
    retryFailed = false,
    forceRegenerate = false,
  ) =>
    request<SectionGuide>(
      "POST",
      `/api/v1/papers/${paperId}/sections/${sectionId}/guide/generate`,
      {
        document_version_id: revisionId,
        section_id: sectionId,
        depth,
        allow_network: allowNetwork,
        retry_failed: retryFailed,
        force_regenerate: forceRegenerate,
      },
      crypto.randomUUID(),
    ),
  qa: (
    paperId: string,
    revisionId: string,
    sectionId?: string,
    scope: QAScope = "section",
  ) => {
    const params = new URLSearchParams({
      document_version_id: revisionId,
      scope,
    });
    if (sectionId) params.set("section_id", sectionId);
    return request<QAView[]>(
      "GET",
      `/api/v1/papers/${paperId}/qa?${params.toString()}`,
    );
  },
  askQA: (
    paperId: string,
    body: {
      document_version_id: string;
      section_id?: string;
      scope: QAScope;
      question: string;
      selection_span_ids?: string[];
      allow_network: boolean;
      retry_failed?: boolean;
      force_regenerate?: boolean;
      optional_short_card?: string | null;
    },
  ) =>
    request<QAView>(
      "POST",
      `/api/v1/papers/${paperId}/qa/ask`,
      body,
      crypto.randomUUID(),
    ),
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
  liteUsageGlobal: () => request<LiteUsage>("GET", "/api/v1/lite/usage"),
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
