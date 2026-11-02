> 历史目录整理记录。当前设计及新旧代码适配见 [v3→阅读辅助映射](v3_to_reading_assessment.md)；下文旧契约缺口是当时审计，不代表本版仍未设计。

# v3 文档整理与兼容索引

日期：2026-11-02（Asia/Shanghai）。范围：文档基线切换、归档、去重和版本澄清；**不是 v2→v3 工程审计报告**。没有执行数据库迁移，也未宣称 M0–M6 已完成。

## 当前目录布局

按用户追加要求，取消独立规范包外层目录；原包 `docs/` 的 10 份章节直接移至仓库 `docs/`，schemas/prompts/examples/tests 分别落在 `docs` 下同名目录。53 份文件搬移，原包 README 合并到现有文档导航；CHANGELOG、Agent 模板、下一轮指令模板、忽略示例及清单也放到 `docs/`。旧 v2 归档保留。

| 内容 | 当前路径 |
| --- | --- |
| 产品、架构、交互、迁移和验证章节 | `docs/00_decisions_and_scope.md` 至 `docs/09_reference_implementation_notes.md` |
| Pydantic、JSON Schema、参考 SQL | `docs/schemas/`（保留 `generated/`） |
| Prompt / 合成示例 / 契约测试 | `docs/prompts/` / `docs/examples/` / `docs/tests/` |
| 导航 / 资产清单 / 哈希 | `docs/README.md` / `docs/MANIFEST.md` / `docs/SHA256SUMS.txt` |

## 旧 v2 材料去向与合并

| 原材料 | 处理 | 当前对应 |
| --- | --- | --- |
| `docs/README.md` | 旧内容移至 `archive/v2/README.md`，原路径重建为导航 | [当前文档入口](../README.md) |
| 旧 v2 `docs/01_product_design.md` | 旧内容归档至 `archive/v2/`；原路径用于 v3 产品设计 | v3 [决策](../00_decisions_and_scope.md)、[产品](../01_product_design.md)、[交互](../04_graph_interaction_spec.md) |
| `docs/02_development_plan.md` | 归档至 `archive/v2/` | v3 [架构](../02_architecture_and_workflows.md)、[迁移计划](../06_development_migration_plan.md)、[验证](../08_validation_and_security.md) |
| `docs/03_knowledge_schema_and_prompts.md` | 归档至 `archive/v2/` | v3 [Schema](../03_schema_design.md)、[Prompt 规范](../05_prompt_engineering.md) |
| `docs/AGENTS.template.md` | 归档；v3 模板适用条目合并到根 AGENTS | [协作约定](../../AGENTS.md) |
| `docs/prompts/`、`schemas/`、`examples/`、`tests/` | 整体迁至 `archive/v2/`，保留彼此依赖 | 当前 `docs/` 下同名目录；运行代码不引用归档包 |
| `docs/design/`、`decisions/`、旧 ADR、迁移评估、交接 | 原路径保留，标明历史适用范围 | [历史索引](../archive/README.md) |
| `docs/api.md`、模型配置、安全、验收及环境记录 | 保留当前运行说明与执行证据；修复陈旧状态和链接 | [实际进度](../progress.md) |
| 根 README、AGENTS、进度、开发日志、实验入口 | 统一指向 v3；保留旧结果与协议 | [基线 ADR](../adr/0003-v3-documentation-baseline.md) |

共归档 29 个 v2 文件。移除的是原路径下重复的现行设计入口，没有删除旧规范内容。归档 Markdown 仅调整标识和相对链接；契约、Prompt、测试、示例保持原内容。既有两份 v0.x 计划删除保留，不归因于本轮。

## 设计、运行与版本

v3 的自动建图、五类默认节点（Paper、Concept、Method、Claim、ResearchQuestion）、按需双语详情及独立布局是目标。完整 Condition/Experiment/Finding/Evidence 仍保存在领域层，不因默认画布精简而删除。现有审核、模型结果和用户修改必须保留；NO_DECISION 不形成科学边。

| 标识 | 含义与本轮状态 |
| --- | --- |
| v3.0 规范包 | 当前产品设计；未等同于发布或完成的代码 |
| v3 领域 3.0 / 图谱投影 1.0 / 抽取 1.0 | 新参考契约的独立版本，正式映射待 M0 |
| knowledge-v2.1 / Alembic 0008 | 当前运行领域契约和数据库 head，本轮未修改 |
| 应用 0.0.1 / 协议 1 | 当前工程版本，不随文档归档提升 |
| v3 M0–M6 | 对现有 P2/P3 的增量路线；不等于重新执行 P0–P6 |

[已实现 API](../api.md)继续以运行 Pydantic 和生成的 OpenAPI/TypeScript 为依据。[v3 API/事件](../07_api_and_events.md)是目标，不保证现有后端可调用。参考 SQLite SQL 不可直接对用户库执行。

## Prompt 对应

| 旧 v2 编号与名称 | v3 编号与名称 |
| --- | --- |
| P01_paper_outline | P01_section_outline（可选） |
| P02_extract_scientific_knowledge | P02_unified_section_extract |
| P03_normalize_entities | P03_entity_alignment |
| 无独立对应任务 | P04_label_translation_repair |
| P04_compare_conditions | P05_comparability |
| P05_infer_relation | P06_relation_inference |
| P06_query_grounded_answer | P07_graph_grounded_query |
| P07_query_distill_candidate | P08_query_distillation |
| P08_graph_evidence_lint | P09_graph_lint |
| P09_reading_synthesis | P10_reading_synthesis |
| P10_wiki_revision | P11_wiki_delta |

运行时仍使用 [engine/prompts](../../services/engine/researchgraph/prompts/) 的旧 P01–P05。历史 ModelRun/缓存身份依赖 Prompt 内容与哈希，不能只按新编号改名或把模板覆盖过去。Query/Lint/Wiki 模板存在不代表功能已开发。

## 实施前必须澄清的参考契约差异

1. [图谱交互](../04_graph_interaction_spec.md)同时将双击用于固定/解锁和焦点展开。后续已按用户要求在 [ADR 0005](../adr/0005-model-capabilities-resume-force-graph.md)裁定：双击固定/解除、独立按钮聚焦、拖动实时联动。
2. 文本/P02 提到 MethodDetail、Experiment、Metric 等嵌套细节，但 [参考 contracts.py](../schemas/contracts.py)未完整建模这些对象，且采用 `extra="forbid"`。正式适配需保留现有领域对象并补齐明确的 DTO 映射，不能为通过参考模型删去实验信息。
3. 产品要求英文回退和按需翻译修复，而 ExtractedNode 的 `label_zh`、`summary_zh` 及 Claim 中文陈述为非空必填。需明确翻译缺失时的暂存/投影适配及契约版本，不得静默关闭严格校验。
4. 文档有 `source_text_hash` 命名，EvidenceSpan 参考字段为 `text_sha256`。正式接口应明确转换和哈希输入，避免误把两字段直接互换。
5. v2 已允许来源通过的未审核作者主张写入；v3 对“旧审核前置”的概述不能代替代码审计。M0 应核查实际显示过滤与流程入口后确定改动。

## 核验与边界

搬移前验证原 v3 包 52 项哈希；搬移后更新路径、合并 README，并重建当前 52 项 SHA256SUMS 与 MANIFEST（清单本身不纳入自身哈希）。设计含义和参考契约保持；文档入口、路径引用及测试命令按新布局调整。归档前保存本轮已有文件的哈希和路径映射，核对运行代码、已有未提交改动及 QA 原件未被本轮改写；备份位于本机忽略目录，不进入仓库。

参考契约使用 Conda 的两个独立 pytest 进程，避免同名 `contracts` 模块和测试文件发生导入冲突；并在内存中比较参考 Pydantic 与 16 份 v3 JSON Schema，检查 Markdown 链接与差异空白。实际执行结果见[进度](../progress.md)及[本轮日志](../../DEVELOPMENT_LOG.md)。

S1–S4 四份外部原文登记路径不可用，保留旧登记值，未重新核验内容或哈希。未重跑应用/真实模型/安装验收；未 Commit/Push。下一次开发应先完成 M0 代码与数据兼容审计，再推进投影与详情，继续停留在既有 P2/P3 范围。
