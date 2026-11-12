# ResearchGraph Lite · A+B+D 开发规范包

> 版本：v1.0 / 2026-11-09；状态：目标架构与迁移设计，**不是已开发功能验收报告**。

本包基于原 ResearchGraph Studio v2/v3 设计以及现有 P2/P3 桌面工程，重新聚焦**A 章节式 AI 导读、B 极简论文知识卡片、D 按需证据问答**。在当前干净工程中，Lite 只保留本地阅读基础和后续 A/B/D 所需接口；旧完整工程、业务代码和应用数据通过 `backup/pre-lite-refactor` 回退，不加载或迁移到 Lite 数据库。目标是把每篇论文的强制前置 LLM 调用从原估计的 30万～80万 Token 降到 **0 Token**（仅本地解析时）；如用户主动生成卡片、三节导读与三次问答，设计预算为 **2.1万～4.5万 Token**，需真实测量验证。

## 2026-11-12 当前边界

基础 A/B/D 按需调用原则保持。PaperCard + LightGraph、章节导读、局部证据问答、英文关键词辅助和全局模型配置继续保留；按用户要求撤下全文 PDF 翻译界面、业务 API、执行器与安装资源，不再提供单独翻译流水线。

论文阅读工作区置顶，论文信息放在后方默认折叠。保留 `lite0008` 迁移链以兼容已有 Lite 数据库，不降级或重新初始化，不删除论文、成果、布局、历史翻译行、任务快照、用量或生成文件，也不重放旧翻译任务。适用边界见 [ADR0040](../adr/0040-remove-pdf-translation.md) 和 [撤下说明](../pdf-translation.md)。测试与安装结果以 [进度](../progress.md) 的实际记录为准，不以此规范代替验收。

## 目录及阅读顺序

1. `docs/01_product_design.md` — 产品定位、交互、流程图、功能边界、场景。
2. `docs/02_schema_and_api.md` — 精简 Schema、证据追踪、缓存、接口和兼容策略。
3. `docs/03_prompt_spec.md` — 提示词编排、输入安全、输出契约、故障策略。
4. `docs/04_progressive_migration.md` — 基于现有工程的 Lite P0–P4 迁移与验收。
5. `docs/05_token_budget_and_evaluation.md` — 实际计量、预算、节流、对比实验。
6. `prompts/` — B01 卡片、A01 章节导读、D01 证据问答；加 D02 可选搜索关键词简化。
7. `schemas/contracts.py`、`schemas/generated/` — Pydantic v2 参考契约及 JSON Schema。
8. `schemas/sqlite_reference.sql` — 仅供设计参考的增量表，不可直接覆盖现有迁移。
9. `examples/`、`tests/` — **虚构样例**与最小契约测试。
当前状态以 `docs/progress.md` 和 `docs/adr/0032-lite-clean-engine-and-paper-overview.md` 为准；迁移阶段的接续指令已移除。

## 首要产品决议

- Zotero 是原始 PDF 的权威来源，ResearchGraph 仅读取并本地索引；默认索引流程不长期复制完整 PDF，不内置 PDF 阅读器。直接导入 PDF 仍可作为备用入口。
- 不再将完整科研图谱、跨论文 RelationAssertion、全量 Lint 和 Wiki 生成作为单篇论文的必经步骤；这些旧模块和数据不进入活跃 Lite 工程，仅在备份分支中保留以便回退。
- 默认只解析和索引（0 LLM Token）；卡片、导读、问答均明确由用户触发。缓存命中不重发。
- B 是快速了解论文的快照；A 是逐小节阅读引导（非全篇总结）；D 是经限定范围检索的临时问答，不再默认带入大量旧 GraphRAG 上下文。
- 中文解释为主，英文证据不变；回答与卡片都保留可回查的 Section/Span ID。
- LLM 不生成正式主键、PDF 页码或绝对文件路径；来源引用由本地索引验证，找不到就说明不足。
- 不自动改动 Zotero、Obsidian 私人笔记或旧 KnowledgeStore。密钥/私有论文数据不提交 GitHub。

## 设计原则

最小模型输入、最少模型调用、来源可追溯、可中断可恢复、费用有上限、对现有项目增量迁移。前端要能明确区分：**本地提取**、**AI已生成**、**缓存命中**、**未生成**、**生成失败**。
