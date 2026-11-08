import { invoke } from "@tauri-apps/api/core";
import { request, type Evidence } from "./api";
import type { Attribution, QueryRequest } from "./queryApi";

export type LintScope = {
  paper_ids: string[];
  document_ids: string[];
  include_personal: boolean;
};
export type LintRun = {
  id: string;
  project_id: string;
  status: string;
  phase?: "scanning" | "rebuilding_dependencies" | "finished";
  timings?: Record<string, number>;
  scope: LintScope;
  rule_version: string;
  event_sequence: number;
  input_hash: string;
  total: number;
  processed: number;
  progress: number;
  counts: { error: number; warning: number; info: number };
  diff: { new: number; persistent: number; resolved: number };
  previous_run_id: string | null;
  errors: Record<string, unknown>[];
  created_at: string;
  updated_at: string;
  finished_at: string | null;
};
export type LintRepairStep = {
  id: string;
  title: string;
  description: string;
  action?: string;
  automated?: boolean;
  requires_model?: boolean | null;
};
export type LintRepairPlan = {
  status: "informational" | "actionable" | "blocked";
  summary: string;
  steps: LintRepairStep[];
  safeguards: string[];
};
export type LintIssue = {
  id: string;
  fingerprint: string;
  code: string;
  rule_version: string;
  severity: "error" | "warning" | "info";
  category: string;
  object_type: string;
  object_id: string;
  paper_id?: string | null;
  location: Record<string, unknown>;
  message: string;
  suggestion: string;
  repair_plan?: LintRepairPlan | null;
  lifecycle: string;
  deterministic: boolean;
};
export type P5Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};
export type P5OffsetPage<T> = {
  items: T[];
  total: number;
  offset: number;
  limit: number;
};
export type DependencyEdge = {
  id: string;
  dependent_type: string;
  dependent_id: string;
  source_type: string;
  source_id: string;
  role: string;
  category: string;
  state: string;
};
export type P5Dependency = {
  type: string;
  id: string;
  quote?: string | null;
  start?: number | null;
  end?: number | null;
  sha256?: string | null;
  revision?: number | null;
};
export type WikiCondition = {
  dimension: string;
  state: "known" | "unknown" | "not_applicable" | "conflicting";
  value: string | null;
  unit: string | null;
};
export type WikiPassage = {
  heading: string;
  text: string;
  attribution: Attribution;
  dependencies: P5Dependency[];
  caveats: string[];
  conditions: WikiCondition[];
  links?: string[];
};
export type WikiSection = WikiPassage & {
  section_id: string;
  stale: boolean;
};
export type WikiPageSummary = {
  page_id: string;
  title: string;
  head_version_id: string | null;
  saved_version_id: string | null;
  published_version_id: string | null;
  file_state: string;
  content_hash: string;
};
export type WikiPageView = {
  page_id: string;
  title: string;
  version_id: string;
  head_version_id: string;
  saved_version_id: string | null;
  revision: number;
  state: string;
  content_state: string;
  content_hash: string;
  markdown: string;
  sections: WikiSection[];
  versions: {
    version_id: string;
    revision: number;
    state: string;
    content_hash: string;
  }[];
  diff: string | Record<string, unknown>;
  file: Record<string, unknown> | null;
  [key: string]: unknown;
};
export type WikiRoot = {
  root_id: string;
  path: string;
  active: boolean;
  revision: number;
};
export type WikiPublication = {
  operation_id: string;
  state: string;
  error?: string | null;
  [key: string]: unknown;
};
export type WorkflowKind = "lint_semantic" | "wiki_synthesis" | "wiki_delta";
export type P5Suggestion = {
  code: string;
  severity: string;
  affected_ids: string[];
  evidence_ids: string[];
  evidence_dependencies?: P5Dependency[];
  rationale: string;
  suggested_action: string;
  uncertainty: string;
};
export type WorkflowView = {
  id: string;
  kind: WorkflowKind;
  status: string;
  input_hash: string;
  job_id: string | null;
  result: {
    draft?: { title: string; passages: WikiPassage[] };
    patch?: {
      base_version_id: string;
      base_content_hash: string;
      operations: Record<string, unknown>[];
    };
    suggestions?: P5Suggestion[];
    coverage_gaps?: string[];
    limitations?: string[];
    model_run_id?: string;
    [key: string]: unknown;
  } | null;
  model_runs: {
    id: string;
    status: string;
    usage: Record<string, number>;
    duration_seconds: number | null;
    error_code: string | null;
    error: string | null;
    cost_known: boolean;
  }[];
  can_continue: boolean;
  error_code: string | null;
  error: string | null;
  question?: string;
  created_at?: string;
  updated_at?: string;
};
export type WorkflowRequest = {
  kind: WorkflowKind;
  query: QueryRequest;
  lint_run_id?: string;
  page_id?: string;
  base_version_id?: string;
  affected_section_ids?: string[];
  personal_sources?: PersonalSelection;
};

export type PersonalSelection = {
  version: "p5-personal-sources-1";
  note_ids: string[];
  annotation_ids: string[];
  external_version_ids: string[];
};
export const emptyPersonalSelection = (): PersonalSelection => ({
  version: "p5-personal-sources-1",
  note_ids: [],
  annotation_ids: [],
  external_version_ids: [],
});
export type PersonalSource = {
  type: "note" | "annotation" | "external";
  id: string;
  label: string;
  text?: string;
  sha256?: string;
  allow_local?: boolean;
  redacted?: boolean;
  allow_model: boolean;
  authorization_revision: number;
  root_id?: string;
  relative_path?: string;
  highlight?: string;
  anchor_status?: string;
  evidence_id?: string;
  document_id?: string;
};
export type LintDocument = {
  id: string;
  title: string;
  kind: string;
  status: string;
  current_version_id: string | null;
  latest_version_id: string | null;
};
export type ExternalDocument = {
  document_id: string;
  version_id: string;
  current_version_id: string;
  title: string;
  revision: number;
  attribution: "user_view" | "external_source";
  content_state: "unverified" | "invalid";
  source_verified: false;
  root_id: string;
  relative_path: string;
  sha256: string;
  text: string;
  file_state: string;
  versions: {
    version_id: string;
    revision: number;
    sha256: string;
    title: string;
    attribution: string;
  }[];
};
export type ExternalPreview = {
  root_id: string;
  relative_path: string;
  sha256: string;
  text: string;
  source_verified: false;
  file_state: string;
};

const base = (projectId: string) => `/api/v1/projects/${projectId}`;
const query = (values: Record<string, string | number | undefined>) => {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  return params.toString();
};

export const p5Api = {
  lintDocuments: (projectId: string, page: number, includePersonal: boolean) =>
    request<P5Page<LintDocument>>(
      "GET",
      `${base(projectId)}/lint/documents?${query({ page, page_size: 10, include_personal: String(includePersonal) })}`,
    ),
  personalSources: (projectId: string, page: number) =>
    request<P5Page<PersonalSource>>(
      "GET",
      `${base(projectId)}/p5/personal-sources?page=${page}&page_size=10`,
    ),
  annotationGrant: (
    projectId: string,
    id: string,
    body: {
      allow_model: boolean;
      allow_local?: boolean;
      expected_revision: number;
    },
    key: string,
  ) =>
    request<{
      annotation_id: string;
      allow_model: boolean;
      allow_local?: boolean;
      revision: number;
    }>("POST", `${base(projectId)}/p5/annotations/${id}/grant`, body, key),
  externalDocuments: (projectId: string) =>
    request<{ items: ExternalDocument[]; total: number }>(
      "GET",
      `${base(projectId)}/external-documents?include_personal=true`,
    ),
  externalDocument: (projectId: string, id: string, versionId = "") =>
    request<ExternalDocument>(
      "GET",
      `${base(projectId)}/external-documents/${id}?${query({ include_personal: "true", version_id: versionId })}`,
    ),
  externalPreview: (
    projectId: string,
    body: { root_id: string; relative_path: string },
  ) =>
    request<ExternalPreview>(
      "POST",
      `${base(projectId)}/external-documents/preview?include_personal=true`,
      body,
    ),
  externalRegister: (
    projectId: string,
    body: {
      root_id: string;
      relative_path: string;
      expected_sha256: string;
      title: string;
      attribution: "user_view" | "external_source";
      document_id?: string;
      base_version_id?: string;
    },
    key: string,
  ) =>
    request<ExternalDocument>(
      "POST",
      `${base(projectId)}/external-documents?include_personal=true`,
      body,
      key,
    ),
  lintRuns: (projectId: string, page: number) =>
    request<P5Page<LintRun>>(
      "GET",
      `${base(projectId)}/lint/runs?page=${page}&page_size=10`,
    ),
  lintStart: (projectId: string, scope: LintScope, key: string) =>
    request<LintRun>("POST", `${base(projectId)}/lint/runs`, scope, key),
  lintRun: (projectId: string, id: string) =>
    request<LintRun>("GET", `${base(projectId)}/lint/runs/${id}`),
  lintAdvance: (projectId: string, id: string, key: string) =>
    request<LintRun>(
      "POST",
      `${base(projectId)}/lint/runs/${id}/advance`,
      { max_items: 100 },
      key,
    ),
  lintCancel: (projectId: string, id: string, key: string) =>
    request<LintRun>(
      "POST",
      `${base(projectId)}/lint/runs/${id}/cancel`,
      {},
      key,
    ),
  lintIssues: (
    projectId: string,
    id: string,
    filters: {
      page: number;
      severity?: string;
      category?: string;
      lifecycle?: string;
      paper_id?: string;
    },
  ) =>
    request<P5Page<LintIssue>>(
      "GET",
      `${base(projectId)}/lint/runs/${id}/issues?${query({ ...filters, page_size: 10 })}`,
    ),
  lintDependencies: (
    projectId: string,
    objectType: string,
    objectId: string,
    page: number,
    direction: "dependents" | "dependencies",
  ) =>
    request<P5Page<DependencyEdge>>(
      "GET",
      `${base(projectId)}/lint/dependencies?${query({ object_type: objectType, object_id: objectId, page, page_size: 10, direction })}`,
    ),
  rebuildDependencies: (projectId: string, key: string) =>
    request<{ edge_count: number; change_count: number }>(
      "POST",
      `${base(projectId)}/lint/dependencies/rebuild`,
      {},
      key,
    ),
  wikiPages: (projectId: string, page = 1, includePersonal = false) =>
    request<P5OffsetPage<WikiPageSummary>>(
      "GET",
      `${base(projectId)}/wiki/pages?${query({ offset: (page - 1) * 10, limit: 10, include_personal: includePersonal ? "true" : "false" })}`,
    ),
  wikiPage: (
    projectId: string,
    id: string,
    versionId = "",
    includePersonal = false,
  ) =>
    request<WikiPageView>(
      "GET",
      `${base(projectId)}/wiki/pages/${id}?${query({ version_id: versionId, include_personal: includePersonal ? "true" : "false" })}`,
    ),
  wikiSave: (
    projectId: string,
    id: string,
    body: {
      version_id: string;
      expected_head_version_id: string;
      expected_content_hash: string;
    },
    key: string,
  ) =>
    request<WikiPageView>(
      "POST",
      `${base(projectId)}/wiki/pages/${id}/save`,
      body,
      key,
    ),
  wikiRoots: (projectId: string) =>
    request<{ items: WikiRoot[] }>("GET", `${base(projectId)}/wiki/roots`),
  authorizeOutput: (projectId: string) =>
    invoke<WikiRoot | null>("wiki_authorize_output", { projectId }),
  revokeOutput: (projectId: string, rootId: string, key: string) =>
    request<WikiRoot>(
      "POST",
      `${base(projectId)}/wiki/roots/${rootId}/revoke`,
      {},
      key,
    ),
  wikiPublish: (
    projectId: string,
    id: string,
    body: {
      root_id: string;
      version_id: string;
      expected_content_hash: string;
      expected_target_hash: string | null;
    },
    key: string,
  ) =>
    request<WikiPublication>(
      "POST",
      `${base(projectId)}/wiki/pages/${id}/publish`,
      body,
      key,
    ),
  wikiRecover: (projectId: string, id: string, key: string) =>
    request<WikiPublication>(
      "POST",
      `${base(projectId)}/wiki/publications/${id}/recover`,
      {},
      key,
    ),
  wikiPublications: (projectId: string, pageId: string, page: number) =>
    request<P5OffsetPage<WikiPublication>>(
      "GET",
      `${base(projectId)}/wiki/publications?${query({ page_id: pageId, offset: (page - 1) * 10, limit: 10 })}`,
    ),
  inspectWikiFile: (projectId: string, id: string, key: string) =>
    request<{
      observation_id: string;
      attribution: string;
      source_verified: false;
      text: string;
      diff: string;
    }>("POST", `${base(projectId)}/wiki/pages/${id}/inspect-file`, {}, key),
  workflows: (projectId: string) =>
    request<{ items: WorkflowView[] }>("GET", `${base(projectId)}/workflows`),
  prepare: (projectId: string, body: WorkflowRequest, key: string) =>
    request<WorkflowView>(
      "POST",
      `${base(projectId)}/workflows/prepare`,
      body,
      key,
    ),
  workflow: (projectId: string, id: string) =>
    request<WorkflowView>("GET", `${base(projectId)}/workflows/${id}`),
  generate: (
    projectId: string,
    id: string,
    continueRequested: boolean,
    key: string,
  ) =>
    request<import("./api").Job>(
      "POST",
      `${base(projectId)}/workflows/${id}/generate`,
      { allow_network: true, continue_requested: continueRequested },
      key,
    ),
  materialize: (projectId: string, id: string, key: string) =>
    request<WikiPageView>(
      "POST",
      `${base(projectId)}/workflows/${id}/materialize`,
      {},
      key,
    ),
  evidence: (id: string) => request<Evidence>("GET", `/api/v1/evidence/${id}`),
};
