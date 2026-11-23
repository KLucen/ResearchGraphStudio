export type PaperCardKind =
  | "research_problem"
  | "core_contribution"
  | "architecture_algorithm"
  | "data_experimental_setup"
  | "evaluation"
  | "key_concept"
  | "main_result"
  | "strength"
  | "weakness"
  | "author_limitation";

export type PaperCardPosition = {
  source_id: string;
  chapter_ref: string | null;
  chapter_title: string | null;
  page_start: number | null;
  page_end: number | null;
  source_offset_start: number;
  source_offset_end: number;
  local_offsets: {
    chunk_id: string;
    span_ids: string[];
    page: number;
    start_offset: number;
    end_offset: number;
  }[];
  source_hash: string;
  unit_id?: string | null;
  granularity?: "local_fragments" | "reading_unit" | "model_segment";
  segment_id?: string | null;
  locator?: Record<string, unknown> | null;
};

export type PaperCardEvidence = {
  source_id: string;
  quote_en: string;
  occurrence_index: number;
  translation_zh: string | null;
  translation_status: "auxiliary" | "not_provided";
  position: PaperCardPosition;
};

export type DetailedPaperCard = {
  id: string;
  kind: PaperCardKind;
  attribution: "AUTHOR" | "ANALYSIS";
  title_zh: string;
  title_en: string | null;
  body_zh: string;
  reading_guide_zh: string;
  evidence: PaperCardEvidence[];
};

export type PaperCardSet = {
  schema_version: "paper-card-set-2";
  prompt_version: string;
  article_overview_zh: string;
  overview_card_ids: string[];
  card_set_intro_zh: string;
  coverage_notes: string[];
  cards: DetailedPaperCard[];
  source_kind: "local_revision" | "model_parse";
  source_id: string;
  source_fingerprint: string;
  source_warnings: string[];
  semantic_accuracy: "unverified";
};

export const paperCardCategories: {
  kind: PaperCardKind;
  label: string;
  en: string;
}[] = [
  { kind: "research_problem", label: "研究问题", en: "Research Problem" },
  { kind: "core_contribution", label: "核心贡献", en: "Core Contributions" },
  {
    kind: "architecture_algorithm",
    label: "架构与算法",
    en: "Architecture / Algorithm",
  },
  {
    kind: "data_experimental_setup",
    label: "数据与实验设置",
    en: "Data / Experimental Setup",
  },
  { kind: "evaluation", label: "评估方式", en: "Evaluation" },
  { kind: "key_concept", label: "关键概念", en: "Key Concepts" },
  { kind: "main_result", label: "主要结果", en: "Main Results" },
  { kind: "strength", label: "优点", en: "Strengths" },
  { kind: "weakness", label: "不足与待核查", en: "Weaknesses / Questions" },
  {
    kind: "author_limitation",
    label: "作者自述局限",
    en: "Authors’ Limitations",
  },
];
