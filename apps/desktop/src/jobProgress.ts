import type { Job } from "./api";

const stages: Record<string, string> = {
  starting: "准备任务",
  reading: "读取 PDF",
  parsing: "解析原文",
  checking: "检查文件",
  saving: "保存结果",
  indexing: "建立本地索引",
  diagnostics: "检查存储",
  generating: "生成论文概览",
  guide: "生成章节导读",
  document_source: "读取 Zotero PDF 附件",
  preparing_provider: "准备文档解析模型",
  model_parsing: "模型正在解析 PDF，等待完整结果返回",
  document_rendering: "正在准备 PDF 页面图片",
  document_connecting: "正在连接文档解析服务",
  document_uploading: "正在发送论文材料",
  document_waiting: "论文材料已发送，等待模型响应",
  document_receiving: "正在接收模型解析结果",
  document_batching: "按页顺序解析并保存批次检查点",
  document_repairing: "正在修复当前批次的返回格式",
  document_boundary: "正在复核相邻批次的截断与续接",
  validating_document: "校验模型返回的章节、公式与表格",
  saving_document: "保存章节正文、公式与表格",
};

const generation: Record<string, string> = {
  section_guide: "生成章节导读",
  paper_reading_notes: "一次生成全文译文与精读笔记",
  section_close_reading: "生成所选范围译文与批注",
  understanding_check: "检查用户复述",
  grounded_qa: "生成局部证据问答",
  search_keywords: "生成英文关键词",
  llm_document_postprocess: "根据模型章节生成所选阅读内容",
};

export function jobStageLabel(job: Pick<Job, "kind" | "stage">): string {
  if (job.stage === "generating" && Object.hasOwn(generation, job.kind))
    return generation[job.kind];
  return job.stage && Object.hasOwn(stages, job.stage)
    ? stages[job.stage]
    : "正在处理";
}
