/** Synthetic, distributable knowledge fixtures for UI and renderer regression. */
import type {
  KnowledgePaper,
  KnowledgeReport,
  KnowledgeSettings,
} from "./knowledgeApi";

export const knowledgeSettings: KnowledgeSettings = {
  auto_collect: false,
  auto_connect: false,
  allow_network: false,
  scope: "project",
  collection_id: null,
  max_candidates: 8,
  max_requests_per_run: 2,
  max_input_tokens: 48000,
  max_output_tokens: 6000,
  total_request_limit: 20,
};
const kinds = [
  "RESEARCH_QUESTION",
  "CONCEPT",
  "METHOD",
  "CONTRIBUTION",
  "FINDING",
];
const labels = [
  "研究什么问题",
  "合成概念",
  "合成方法",
  "作者贡献",
  "有条件的结果",
];
export function knowledgePapers(): KnowledgePaper[] {
  return ["A", "B"].map((letter) => {
    const id = `library-${letter}`;
    const version = {
      id: `version-${letter}`,
      library_paper_id: id,
      source_kind: "local_revision",
      source_id: `revision-${letter}`,
      source_paper_id: `paper-${letter}`,
      project_id: "project-1",
      source_fingerprint: `fingerprint-${letter}`,
      schema_version: "paper-knowledge-1",
      evidence_status: "grounded" as const,
      created_at: "2026-11-20T09:00:00Z",
      content: {
        graph: {
          nodes: [
            {
              id: `paper:${id}`,
              type: "PAPER",
              label_zh: `合成论文 ${letter}`,
            },
            ...kinds.map((type, i) => ({
              id: `${letter}-${i}`,
              type,
              label_zh: `${letter} ${labels[i]}`,
              description_zh: `${letter} 的合成知识说明 ${i}`,
              source_refs: [
                { source_id: "s1", quote: `${letter} synthetic source text.` },
              ],
            })),
          ],
          edges: [],
        },
        sources: [
          {
            ref: "s1",
            kind: "local_span",
            chapter_title: "合成方法章节",
            page_start: 2,
            text: `${letter} synthetic source text.`,
          },
        ],
        warnings: [],
      },
    };
    return {
      id,
      title: `合成论文 ${letter}`,
      note: "",
      archived: false,
      project_ids: ["project-1"],
      source_links: [
        {
          paper_id: `paper-${letter}`,
          original_paper_id: `paper-${letter}`,
          project_id: "project-1",
          source_available: true,
        },
      ],
      collection_ids: [],
      current_version: version,
      versions: [version],
    };
  });
}
export function knowledgeReport(): KnowledgeReport {
  return {
    id: "report-1",
    library_paper_id: "library-B",
    version_id: "version-B",
    title: "合成论文 B 与已有研究的联系",
    status: "completed",
    read: false,
    pinned: false,
    note: "",
    stale: false,
    created_at: "2026-11-20T10:00:00Z",
    summary: [
      {
        text_zh: "两篇论文的方法具有共同步骤，结果条件仍有差异。",
        relation_ids: ["relation-1"],
      },
    ],
    relations: [
      {
        id: "relation-1",
        type: "RELATED_METHOD",
        source_version_id: "version-B",
        target_version_id: "version-A",
        source_node_id: "B-2",
        target_node_id: "A-2",
        target_title: "合成论文 A",
        target_library_paper_id: "library-A",
        explanation_zh: "两种合成方法共享准备步骤。",
        limitations_zh: "任务条件不同，不能判断一篇优于另一篇。",
        source_refs: [
          {
            quote: "B synthetic source text.",
            source_id: "s1",
            source: {
              kind: "paragraph",
              ref: "s1",
              chapter_title: "合成方法章节",
              page_start: 2,
              origin: { unit_id: "unit-B" },
            },
          },
        ],
        target_refs: [
          {
            quote: "A synthetic source text.",
            source_id: "s1",
            source: {
              kind: "paragraph",
              ref: "s1",
              chapter_title: "模型方法章节",
              page_start: null,
              origin: { segment_id: "segment-A", parse_id: "parse-A" },
            },
          },
        ],
      },
    ],
    coverage: {
      eligible: 1,
      selected: 1,
      compared: 1,
      excluded_legacy: 0,
      scope: "project",
    },
  };
}

export function detailedKnowledgeReport(): KnowledgeReport {
  const report = knowledgeReport();
  return {
    ...report,
    id: "report-detailed",
    title: "合成论文 B 的详细联系汇报",
    created_at: "2026-11-21T10:00:00Z",
    relations: report.relations?.map((relation) => ({
      ...relation,
      id: "relation-detailed",
      source_library_paper_id: "library-B",
      source_title: "合成论文 B",
      explanation_zh: "两篇论文采用相近的数据准备步骤。",
      detail: {
        source_zh: "新增论文按任务类型组织样本，并在每组内统一输入格式。",
        target_zh: "已有论文先统一输入格式，再按来源分组保存样本。",
        comparison_zh:
          "两种方案都在模型运行前规范输入，分组依据与预处理顺序有差异。",
        conditions_zh:
          "已有摘录覆盖了准备步骤。验证集和评估指标的可比性仍需核查。",
        follow_up_zh: "可核查两种分组在同一数据划分下能否复用。",
      },
    })),
    summary: [
      {
        text_zh: "方法在输入规范上相近，分组规则有差异。",
        relation_ids: ["relation-detailed"],
      },
    ],
  };
}
