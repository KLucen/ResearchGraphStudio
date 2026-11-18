import { invoke } from "@tauri-apps/api/core";
import type { ReadingHighlight } from "./readingHighlights";

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
export type PaperManagementResult = {
  ok: boolean;
  paper_id: string;
  backup_file: string | null;
  removed: Record<string, number>;
  retained_personal_metadata: number;
  retained_managed_files: number;
};
export type PaperList = { items: Paper[]; next_cursor: number | null };
export type PostImportPlan = {
  parse: true;
  overview: boolean;
  reading: boolean;
  translation_mode: "full" | "none";
  modality: "auto" | "required";
  extract_formulas: true;
  extract_tables: true;
  allow_network: boolean;
  provider_profile_id?: string | null;
};

export type PdfSelection = {
  selection_id: string;
  file_name: string;
};

export type ImportPlanItem = {
  id: string;
  item_kind:
    "document_parse" | "paper_overview" | "paper_reading" | "translation";
  status:
    | "planned"
    | "queued"
    | "running"
    | "succeeded"
    | "failed"
    | "interrupted"
    | "paused";
  config: Record<string, unknown>;
  job_id: string | null;
  attempt: number;
  error: string | null;
  result: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};
export type ImportSession = {
  id: string;
  project_id: string;
  source_kind: "pdf" | "zotero";
  selection_id: string;
  source_snapshot: {
    paper_id?: string | null;
    file_name?: string | null;
    page_count?: number | null;
    provider_file_id?: string | null;
  };
  plan: {
    overview: boolean;
    reading: boolean;
    translation_mode: "full" | "none";
    modality: string;
    require_multimodal: boolean;
    allow_network: boolean;
  };
  status:
    | "planned"
    | "queued"
    | "running"
    | "succeeded"
    | "failed"
    | "interrupted"
    | "paused";
  error: string | null;
  created_at: string;
  updated_at: string;
  items: ImportPlanItem[];
};
export type ModelDocumentSegment = {
  id: string;
  chapter_ref: string;
  chapter_title: string;
  chapter_level: number;
  chapter_order: number;
  kind: string;
  ordinal: number;
  text: string | null;
  latex: string | null;
  mathml: string | null;
  raw_table_text: string | null;
  table_data: Record<string, unknown> | null;
  locator: Record<string, unknown> | null;
  status: string;
  warnings: string[];
};
export type ModelDocumentParse = {
  id: string;
  import_session_id: string;
  parse_version: string;
  modality: string;
  status: string;
  warnings: string[];
  error_code: string | null;
  error: string | null;
  segments: ModelDocumentSegment[];
};
export type ModelDocumentOutput = {
  id: string;
  import_session_id: string;
  parse_id: string;
  item_kind: "paper_overview" | "paper_reading" | "translation" | string;
  status: string;
  output_json: {
    summary?: string | null;
    sections?: { chapter_ref: string; text: string; role?: string | null }[];
    contributions?: string[];
    findings?: string[];
    limitations?: string[];
    translations?: {
      chapter_ref: string;
      source_text: string;
      translation_zh: string;
    }[];
  } | null;
  error_code: string | null;
  error: string | null;
};
export type ModelDocumentSegmentEdit = Partial<
  Pick<
    ModelDocumentSegment,
    "text" | "latex" | "mathml" | "raw_table_text" | "table_data"
  >
>;

export const defaultPostImportPlan = (): PostImportPlan => ({
  parse: true,
  overview: true,
  reading: false,
  translation_mode: "none",
  modality: "auto",
  extract_formulas: true,
  extract_tables: true,
  allow_network: false,
  provider_profile_id: null,
});
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
export type ReadingSourceBlock = {
  chunk_id: string;
  span_ids: string[];
  page: number;
  start_offset: number;
  end_offset: number;
  text: string;
  text_hash: string;
  bbox: number[];
};
export type DocumentReadingUnit = {
  id: string;
  kind: "paragraph" | "heading" | "material";
  material_type:
    | "table"
    | "figure"
    | "formula"
    | "caption"
    | "figure_label"
    | "running"
    | "reference"
    | "contents"
    | "unresolved"
    | null;
  section_id: string | null;
  heading_level?: number | null;
  text: string;
  page_start: number;
  page_end: number;
  ordinal: number;
  source_hash: string;
  sources: ReadingSourceBlock[];
  regions: { page: number; bbox: number[] }[];
  join_reason: string | null;
  confidence: "high" | "suspected";
  reason: string | null;
  solution: string | null;
  /** Optional local/verified LaTeX representation for a detected formula. */
  formula_latex?: string | null;
  /** `recognized` is safe to render; other states keep the original source visible. */
  formula_status?:
    | "recognized"
    | "detected"
    | "uncertain"
    | "unavailable"
    | "source_only"
    | "latex_unavailable"
    | "needs_review"
    | "failed"
    | null;
  formula_confidence?: "high" | "medium" | "low" | "suspected" | null;
  formula_source_text?: string | null;
  formula_id?: string | null;
};
export type FormulaPreview = {
  formula_id: string;
  revision_id: string;
  page: number;
  bbox: number[];
  mime_type: "image/png";
  data_base64: string;
  source_text_hash?: string;
};
export type FormulaRecognitionItem = {
  formula_id: string;
  revision_id: string;
  page: number;
  bbox: number[];
  source_text: string;
  source_text_hash: string;
  status: "recognized" | "needs_review" | "failed";
  latex: string | null;
  recognizer: string | null;
  error_code: string | null;
  message: string;
};
export type FormulaRecognitionResponse = {
  revision_id: string;
  source_sha256: string;
  status: "completed" | "partial" | "unavailable" | "failed";
  recognizer: string | null;
  items: FormulaRecognitionItem[];
  warnings: string[];
  reading_document_refresh_required: boolean;
  model_calls: number;
};
export type FormulaRecognitionJob = Omit<Job, "result"> & {
  result:
    | (Partial<FormulaRecognitionResponse> & {
        revision_id: string;
        processed: number;
        total: number | null;
      })
    | null;
};
export type DocumentReadingView = {
  paper_id: string;
  document_version_id: string;
  projection_version: string;
  source_hash: string;
  projection_hash: string;
  sections: {
    section_id: string;
    parent_id?: string | null;
    title: string;
    level: number;
    role: string;
  }[];
  units: DocumentReadingUnit[];
  warnings: string[];
  refreshed_at: string | null;
};
export type PaperReadingView = {
  id: string;
  paper_id: string;
  document_version_id: string;
  source_hash: string;
  input_hash: string;
  projection_version: string;
  projection_hash: string;
  schema_version: string;
  prompt_version: string;
  provider_id: string;
  model_id: string;
  status: "PENDING" | "COMPLETED" | "INCOMPLETE" | "FAILED" | "STALE";
  analysis: {
    schema_version: "paper_reading_analysis.v1";
    paragraphs: ParagraphAnalysis[];
    paper_argument: SectionReadingAnalysis["section_argument"];
  } | null;
  paragraph_count: number;
  missing_paragraph_ids: string[];
  warnings: string[];
  usage: GuideUsage;
  estimated: ReadingBudget;
  generated_at: string;
  cache_hit: boolean;
  job_id: string | null;
  error_code: string | null;
  error: string | null;
  stale_reason: string | null;
  new_calls: number;
};
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
  reader_context?: Record<string, unknown> | null;
};
export type ReadingParagraph = {
  paragraph_id: string;
  text_en: string;
  text_hash: string;
  page_start: number;
  page_end: number;
  ordinal: number;
  span_ids: string[];
};
export type SectionParagraphs = {
  paper_id: string;
  document_version_id: string;
  section_id: string;
  source_hash: string;
  paragraphs: ReadingParagraph[];
  section_title: string;
  estimated_source_tokens: number;
  suggested_max_source_tokens: number;
};
export type ParagraphFunction =
  | "INTRODUCE_PROBLEM"
  | "DEFINE_CONCEPT"
  | "STATE_CLAIM"
  | "EXPLAIN_METHOD"
  | "PRESENT_EVIDENCE"
  | "HANDLE_OBJECTION"
  | "DISCUSS_LIMITATION"
  | "SUMMARIZE_TRANSITION"
  | "OTHER";
export type ParagraphAnalysis = {
  paragraph_id: string;
  translation_zh: string;
  paragraph_function: ParagraphFunction;
  logic_role_zh: string;
  critical_note_zh: string;
  reading_question_zh: string | null;
  highlights: ReadingHighlight[];
  related_graph_node_ids: string[];
};
export type SectionReadingAnalysis = {
  schema_version: "section_reading_analysis.v1";
  paragraphs: ParagraphAnalysis[];
  section_argument: {
    logic_chain_zh: string[];
    core_claim_zh: string | null;
    strong_point_zh: string | null;
    question_to_verify_zh: string | null;
  } | null;
};
export type ReadingRange = {
  paragraph_ids: string[];
  range_label: string;
  full_section: boolean;
  range_hash: string;
};
export type ReadingBudget = {
  estimated_input_tokens: number;
  estimated_output_tokens: number;
  estimated_total_tokens: number;
  estimated_source_tokens: number;
  estimate_only: boolean;
  warning: string | null;
};
export type CloseReadingView = {
  id: string | null;
  paper_id: string;
  document_version_id: string;
  section_id: string;
  range: ReadingRange;
  status: "PENDING" | "COMPLETED" | "INCOMPLETE" | "FAILED" | "STALE" | null;
  analysis: SectionReadingAnalysis | null;
  missing_paragraph_ids: string[];
  warnings: string[];
  usage: GuideUsage;
  cache_hit: boolean;
  job_id: string | null;
  error_code: string | null;
  error: string | null;
  estimated: ReadingBudget;
  retry_of: string | null;
  new_calls?: number;
};
export type SelfAssessment = "UNSET" | "UNSURE" | "PARTIAL" | "CONFIDENT";
export type CheckResult =
  "NOT_CHECKED" | "ADEQUATE" | "PARTIAL" | "MISCONCEPTION" | "UNCERTAIN";
export type ReadingQuestion = {
  paragraph_id?: string | null;
  text: string;
  resolved: boolean;
};
export type ReadingState = {
  paper_id: string;
  document_version_id: string;
  section_id: string;
  progress: "NOT_STARTED" | "READING" | "COMPLETED";
  self_assessment: SelfAssessment;
  unresolved_concept_ids: string[];
  questions: ReadingQuestion[];
  updated_at: string | null;
  source_hash: string;
  source_changed: boolean;
  overview_result_id: string | null;
  unresolved_unlinked_ids: string[];
};
export type ConceptUnderstanding = {
  id: string | null;
  paper_id: string;
  document_version_id: string;
  overview_result_id: string | null;
  graph_node_id: string;
  node_label_zh: string | null;
  node_label_en: string | null;
  self_level: SelfAssessment;
  last_check_result: CheckResult;
  note_zh: string;
  last_check_note_zh: string;
  association_status: "CURRENT" | "NEEDS_RELINK";
  related_sections: { section_id: string; title: string }[];
  has_unresolved_question?: boolean;
  updated_at: string | null;
};
export type UnderstandingCheckView = {
  id: string | null;
  status: "PENDING" | "COMPLETED" | "FAILED" | "STALE" | null;
  check: {
    check_result: Exclude<CheckResult, "NOT_CHECKED">;
    correct_points_zh: string[];
    missing_or_mistaken_zh: string[];
    feedback_zh: string;
    follow_up_question_zh: string;
  } | null;
  usage: GuideUsage;
  cache_hit: boolean;
  error_code: string | null;
  error: string | null;
  range: ReadingRange;
  user_explanation: string;
  graph_node_ids: string[];
  overview_result_id: string | null;
  estimated: ReadingBudget;
  new_calls?: number;
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
  readingDocument: (paperId: string, revisionId: string) =>
    request<DocumentReadingView>(
      "GET",
      `/api/v1/papers/${paperId}/reading-document?document_version_id=${encodeURIComponent(revisionId)}`,
    ),
  refreshReadingDocument: (paperId: string, revisionId: string) =>
    request<DocumentReadingView>(
      "POST",
      `/api/v1/papers/${paperId}/reading-document/refresh`,
      { document_version_id: revisionId },
      crypto.randomUUID(),
    ),
  paperReadingNotes: (paperId: string, revisionId: string) =>
    request<PaperReadingView | null>(
      "GET",
      `/api/v1/papers/${paperId}/reading-notes?document_version_id=${encodeURIComponent(revisionId)}`,
    ),
  generatePaperReadingNotes: (
    paperId: string,
    body: {
      document_version_id: string;
      allow_network: boolean;
      force_regenerate: boolean;
    },
  ) =>
    request<PaperReadingView>(
      "POST",
      `/api/v1/papers/${paperId}/reading-notes/generate`,
      body,
      crypto.randomUUID(),
    ),
  structure: (id: string) =>
    request<Structure>("GET", `/api/v1/revisions/${id}/sections`),
  sections: (id: string) =>
    request<Structure>("GET", `/api/v1/revisions/${id}/sections`),
  formulaPreview: (revisionId: string, formulaId: string) =>
    request<FormulaPreview>(
      "GET",
      `/api/v1/revisions/${revisionId}/formulas/${formulaId}/preview`,
    ),
  recognizeFormulas: (
    revisionId: string,
    body: { formula_ids?: string[]; force?: boolean } = {},
  ) =>
    request<FormulaRecognitionResponse>(
      "POST",
      `/api/v1/revisions/${revisionId}/formulas/recognize`,
      body,
      crypto.randomUUID(),
    ),
  formulaRecognitionJob: (revisionId: string) =>
    request<FormulaRecognitionJob | null>(
      "GET",
      `/api/v1/revisions/${revisionId}/formulas/recognize/jobs`,
    ),
  startFormulaRecognition: (
    revisionId: string,
    body: { formula_ids?: string[]; force?: boolean } = {},
  ) =>
    request<FormulaRecognitionJob>(
      "POST",
      `/api/v1/revisions/${revisionId}/formulas/recognize/jobs`,
      body,
      crypto.randomUUID(),
    ),
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
    adaptive = false,
  ) =>
    request<SectionGuide | null>(
      "GET",
      `/api/v1/papers/${paperId}/sections/${sectionId}/guide?document_version_id=${encodeURIComponent(revisionId)}&depth=${depth}&adaptive=${adaptive}`,
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
    adaptive = false,
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
        adaptive,
      },
      crypto.randomUUID(),
    ),
  sectionParagraphs: (paperId: string, sectionId: string, revisionId: string) =>
    request<SectionParagraphs>(
      "GET",
      `/api/v1/papers/${paperId}/sections/${sectionId}/paragraphs?document_version_id=${encodeURIComponent(revisionId)}`,
    ),
  closeReading: (
    paperId: string,
    sectionId: string,
    revisionId: string,
    paragraphIds: string[],
    resultId?: string,
  ) =>
    request<CloseReadingView | null>(
      "GET",
      `/api/v1/papers/${paperId}/sections/${sectionId}/close-reading?${new URLSearchParams({ document_version_id: revisionId, paragraph_ids: paragraphIds.join(","), ...(resultId ? { result_id: resultId } : {}) })}`,
    ),
  generateCloseReading: (
    paperId: string,
    sectionId: string,
    body: {
      document_version_id: string;
      paragraph_ids: string[];
      allow_network: boolean;
      force_regenerate?: boolean;
      retry_missing_of?: string;
    },
  ) =>
    request<CloseReadingView>(
      "POST",
      `/api/v1/papers/${paperId}/sections/${sectionId}/close-reading/generate`,
      body,
      crypto.randomUUID(),
    ),
  readingState: (paperId: string, sectionId: string, revisionId: string) =>
    request<ReadingState>(
      "GET",
      `/api/v1/papers/${paperId}/sections/${sectionId}/reading-state?document_version_id=${encodeURIComponent(revisionId)}`,
    ),
  saveReadingState: (
    paperId: string,
    sectionId: string,
    body: Pick<
      ReadingState,
      | "document_version_id"
      | "progress"
      | "self_assessment"
      | "unresolved_concept_ids"
      | "questions"
    > & { overview_result_id?: string },
  ) =>
    request<ReadingState>(
      "PUT",
      `/api/v1/papers/${paperId}/sections/${sectionId}/reading-state`,
      body,
      crypto.randomUUID(),
    ),
  conceptUnderstanding: (
    paperId: string,
    revisionId: string,
    overviewResultId?: string,
  ) => {
    const params = new URLSearchParams({ document_version_id: revisionId });
    if (overviewResultId) params.set("overview_result_id", overviewResultId);
    return request<ConceptUnderstanding[]>(
      "GET",
      `/api/v1/papers/${paperId}/concept-understanding?${params}`,
    );
  },
  saveConceptUnderstanding: (
    paperId: string,
    nodeId: string,
    body: {
      document_version_id?: string;
      overview_result_id: string;
      self_level: SelfAssessment;
      note_zh: string;
    },
  ) =>
    request<ConceptUnderstanding>(
      "PUT",
      `/api/v1/papers/${paperId}/concept-understanding/${encodeURIComponent(nodeId)}`,
      body,
      crypto.randomUUID(),
    ),
  understandingCheck: (
    paperId: string,
    sectionId: string,
    revisionId: string,
    checkId: string,
    paragraphIds: string[] = [],
  ) =>
    request<UnderstandingCheckView | null>(
      "GET",
      `/api/v1/papers/${paperId}/sections/${sectionId}/understanding-check?${new URLSearchParams({ document_version_id: revisionId, ...(checkId ? { result_id: checkId } : { paragraph_ids: paragraphIds.join(",") }) })}`,
    ),
  generateUnderstandingCheck: (
    paperId: string,
    sectionId: string,
    body: {
      document_version_id: string;
      paragraph_ids: string[];
      user_explanation: string;
      allow_network: boolean;
      graph_node_ids?: string[];
      overview_result_id?: string;
    },
  ) =>
    request<UnderstandingCheckView>(
      "POST",
      `/api/v1/papers/${paperId}/sections/${sectionId}/understanding-check/generate`,
      body,
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
  selectPdfImport: () => invoke<PdfSelection | null>("select_pdf_import"),
  submitPdfImport: (
    projectId: string,
    mode: "reference" | "managed",
    selectionId: string,
    postImportPlan?: PostImportPlan,
  ) =>
    invoke<Job | null>("submit_pdf_import", {
      projectId,
      mode,
      selectionId,
      postImportPlan,
      idempotencyKey: crypto.randomUUID(),
    }),
  importPdf: async (
    projectId: string,
    mode: "reference" | "managed",
    postImportPlan?: PostImportPlan,
  ) => {
    const selection = await invoke<PdfSelection | null>("select_pdf_import");
    if (!selection) return null;
    return invoke<Job | null>("submit_pdf_import", {
      projectId,
      mode,
      selectionId: selection.selection_id,
      postImportPlan,
      idempotencyKey: crypto.randomUUID(),
    });
  },
  papers: (projectId: string, cursor = 0) =>
    request<PaperList>(
      "GET",
      `/api/v1/projects/${projectId}/papers?cursor=${cursor}&limit=50`,
    ),
  importSessions: (projectId: string) =>
    request<ImportSession[]>(
      "GET",
      `/api/v1/projects/${projectId}/import-sessions`,
    ),
  importSession: (sessionId: string) =>
    request<ImportSession>(
      "GET",
      `/api/v1/import-sessions/${encodeURIComponent(sessionId)}`,
    ),
  modelDocumentParse: (sessionId: string) =>
    request<ModelDocumentParse>(
      "GET",
      `/api/v1/import-sessions/${encodeURIComponent(sessionId)}/document-parse`,
    ),
  modelDocumentOutputs: (sessionId: string) =>
    request<ModelDocumentOutput[]>(
      "GET",
      `/api/v1/import-sessions/${encodeURIComponent(sessionId)}/document-outputs`,
    ),
  updateModelDocumentSegment: (
    sessionId: string,
    segmentId: string,
    body: ModelDocumentSegmentEdit,
  ) =>
    request<ModelDocumentSegment>(
      "PATCH",
      `/api/v1/import-sessions/${encodeURIComponent(sessionId)}/document-segments/${encodeURIComponent(segmentId)}`,
      body,
    ),
  updateModelDocumentOutput: (
    sessionId: string,
    outputId: string,
    outputJson: NonNullable<ModelDocumentOutput["output_json"]>,
  ) =>
    request<ModelDocumentOutput>(
      "PATCH",
      `/api/v1/import-sessions/${encodeURIComponent(sessionId)}/document-outputs/${encodeURIComponent(outputId)}`,
      { output_json: outputJson },
    ),
  updatePaper: (paperId: string, body: { title: string }) =>
    request<PaperManagementResult>(
      "PATCH",
      `/api/v1/papers/${encodeURIComponent(paperId)}`,
      body,
    ),
  clearPaperLegacyContent: (paperId: string) =>
    request<PaperManagementResult>(
      "DELETE",
      `/api/v1/papers/${encodeURIComponent(paperId)}/legacy-content`,
    ),
  deletePaper: (paperId: string) =>
    request<PaperManagementResult>(
      "DELETE",
      `/api/v1/papers/${encodeURIComponent(paperId)}`,
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
