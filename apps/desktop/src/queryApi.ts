import { request, type Job } from "./api";
import type { GlobalModels } from "./ModelSettings";

export type Attribution =
  "paper_author" | "citation_report" | "user_view" | "model_synthesis";
export type QueryRequest = {
  project_id: string;
  question: string;
  paper_ids: string[];
  include_personal: boolean;
  purpose: "local" | "model";
  limit: number;
};
export type QueryReference = {
  ref: string;
  type: string;
  id: string;
  quote?: string;
  text?: string;
  title?: string;
  paper_id?: string;
  document_version_id?: string;
  page_index?: number;
  start?: number;
  end?: number;
  evidence_ids?: string[];
  section_path?: string[];
  current_file_status?: string;
  content_state?: string;
  file_state?: string;
  authorship?: string;
  origin?: string;
};
export type QueryHit = {
  entry_id: string;
  source_kind: string;
  object_id: string;
  text: string;
  reasons: string[];
  data: Record<string, unknown>;
};
export type QuerySourceDisplay = {
  title: string;
  original: string;
  summary_zh: string | null;
  summary_origin: "extracted_translation" | null;
  paper_id?: string | null;
  paper_ids?: string[];
  page_index?: number | null;
  section_path: string[];
  layout_warnings?: string[];
  graph_presence?: {
    state: "in_graph" | "retrieval_only" | "not_applicable";
    representation: "node" | "evidence" | null;
    node_ids: string[];
    graph_roles: string[];
    graph_revision: number;
  };
};
export type QueryPresentation = {
  hits: Record<string, QuerySourceDisplay>;
  references: Record<string, QuerySourceDisplay>;
};
export type QueryRetrieval = {
  status: string;
  hits: QueryHit[];
  independent_sources: string[];
  graph: {
    nodes: { id: string; kind: string; text: string }[];
    paths: unknown[];
  };
  presentation?: QueryPresentation;
};
export type QueryBrowseRequest = {
  request: QueryRequest;
  page: number;
  page_size: 10;
  display_paper_ids: string[];
  expected_result_hash?: string | null;
};
export type QueryBrowsePage = {
  status: string;
  hits: QueryHit[];
  presentation: QueryPresentation;
  total: number;
  page: number;
  page_size: 10;
  total_pages: number;
  result_hash: string;
  graph_node_count: number;
  independent_sources: string[];
  scope_coverage?: Record<string, unknown> | null;
};
export type QueryPreparation = {
  query_id: string;
  status: string;
  input_hash: string;
  presentation?: QueryPresentation;
  snapshot: {
    request: QueryRequest;
    retrieval: QueryRetrieval;
    context: {
      references: QueryReference[];
      coverage_gaps: string[];
      status: string;
    };
    model: { model: string } | null;
  };
  error: string | null;
};
export type QueryPassage = {
  local_ref: string;
  text: string;
  attribution: Attribution;
  source_refs: string[];
  caveats: string[];
};
export type QueryAnswer = {
  answer_version_id: string;
  query_run_id: string;
  revision: number;
  input_hash: string;
  status: "validated" | "incomplete" | "invalid";
  knowledge_status: "source_grounded" | "mixed_sources" | "insufficient";
  passages: QueryPassage[];
  limitations: string[];
};
export type QueryAnswerView = {
  query_id: string;
  status: string;
  job_id: string | null;
  answer: QueryAnswer | null;
  model_runs: {
    id: string;
    sequence: number;
    status: string;
    usage: Record<string, number>;
    duration_seconds: number | null;
    finish_reason: string | null;
    error_code: string | null;
    error: string | null;
    cost_known: boolean;
  }[];
  can_continue: boolean;
  error_code: string | null;
  error: string | null;
  request_count: number;
  request_limit: number;
};
export type QueryHistoryItem = {
  query_id: string;
  question: string;
  created_at: string;
  status: string;
  job_id: string | null;
  paper_ids?: string[];
};
export type QueryDocumentPassage = {
  id: string;
  document_id: string;
  version_id: string;
  title: string;
  kind: string;
  content_state: string;
  text?: string;
};
export type SavedReading = {
  saved_id: string;
  kind: string;
  title: string;
  document_id: string;
  version_id: string;
  revision: number;
  created_at: string;
  source_query_id: string;
  answer_version_id: string;
  content_state: string;
  file_state: string;
  annotation?: string;
  metadata_revision?: number;
  removed_at?: string | null;
  paper_ids?: string[];
  passages: {
    id: string;
    local_ref: string;
    text: string;
    attribution: Attribution;
    caveats: string[];
    content_state: string;
    issues: string[];
    paper_ids?: string[];
  }[];
};
export type QuerySave = {
  source_query_id: string;
  answer_version_id: string;
  selected_passage_refs: string[];
  expected_input_hash: string;
  kind: "synthesis" | "insight";
  target_document_id: string | null;
  base_version_id: string | null;
};
export type DerivedGraph = {
  nodes: {
    id: string;
    kind: string;
    label: string;
    source_id?: string;
    saved_id?: string;
    layer: string;
  }[];
  edges: {
    id: string;
    source: string;
    target: string;
    relation: string;
    epistemic_status: string;
  }[];
};

const base = (projectId: string) => `/api/v1/projects/${projectId}/query`;
export const queryApi = {
  models: () => request<GlobalModels>("GET", "/api/v1/settings/models"),
  search: (projectId: string, body: QueryRequest) =>
    request<QueryRetrieval>("POST", `${base(projectId)}/search`, body),
  browse: (projectId: string, body: QueryBrowseRequest) =>
    request<QueryBrowsePage>("POST", `${base(projectId)}/search/page`, body),
  prepare: (projectId: string, body: QueryRequest, key: string) =>
    request<QueryPreparation>("POST", `${base(projectId)}/prepare`, body, key),
  run: (projectId: string, id: string) =>
    request<QueryPreparation>("GET", `${base(projectId)}/runs/${id}`),
  generate: (
    projectId: string,
    id: string,
    continueRequested: boolean,
    key: string,
  ) =>
    request<Job>(
      "POST",
      `${base(projectId)}/runs/${id}/generate`,
      { allow_network: true, continue_requested: continueRequested },
      key,
    ),
  answer: (projectId: string, id: string) =>
    request<QueryAnswerView>("GET", `${base(projectId)}/runs/${id}/answer`),
  history: (projectId: string, cursor: string | null = null) =>
    request<{ items: QueryHistoryItem[]; next_cursor: string | null }>(
      "GET",
      `${base(projectId)}/runs?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
    ),
  documents: (projectId: string, personal: boolean) =>
    request<{ items: QueryDocumentPassage[] }>(
      "GET",
      `${base(projectId)}/documents?include_personal=${personal}`,
    ),
  save: (projectId: string, id: string, body: QuerySave, key: string) =>
    request<{
      saved_id: string;
      kind: string;
      document_id: string;
      version_id: string;
      revision: number;
    }>("POST", `${base(projectId)}/runs/${id}/save`, body, key),
  saved: (projectId: string, personal: boolean) =>
    request<{ items: SavedReading[] }>(
      "GET",
      `${base(projectId)}/saved?include_personal=${personal}`,
    ),
  savedDetail: (projectId: string, id: string, personal: boolean) =>
    request<SavedReading>(
      "GET",
      `${base(projectId)}/saved/${id}?include_personal=${personal}`,
    ),
  annotate: (
    projectId: string,
    id: string,
    body: { annotation: string; expected_revision: number },
    key: string,
    personal: boolean,
  ) =>
    request<SavedReading>(
      "PUT",
      `${base(projectId)}/saved/${id}/annotation?include_personal=${personal}`,
      body,
      key,
    ),
  remove: (
    projectId: string,
    id: string,
    body: { expected_revision: number },
    key: string,
    personal: boolean,
  ) =>
    request<{
      saved_id: string;
      removed_at: string;
      metadata_revision: number;
    }>(
      "POST",
      `${base(projectId)}/saved/${id}/remove?include_personal=${personal}`,
      body,
      key,
    ),
  derived: (projectId: string, personal: boolean) =>
    request<DerivedGraph>(
      "GET",
      `${base(projectId)}/derived-graph?include_personal=${personal}`,
    ),
};
