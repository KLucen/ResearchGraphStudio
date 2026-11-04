# 文档导航

2026-11-04 R5三项实际补验收见[新报告](r5-acceptance-verification-20261104.md)：当前模型两篇P13v3各一次通过、零重复P02/P12、再继续零调用；32+2已知错误均保留候选但不进入默认图谱，5组同义结论各一核心代表。新包隔离检查与用户三项反馈通过；部分覆盖/有限证据、strict/干净机及外部补充原文限制分别保留，不进入P4/P5。

2026-11-04 历史任务续接反馈修复见[实际核验](history-retry-verification-20261104.md)：旧 `Claim.kind_note_unused=null` 失败记录已有34/34成功后继，保留原错误作为历史；续接返回已完成任务时界面直接展示并定位，不重复抽取。分页外处理中的后继独立刷新，核心排序未完成不标成完整完成。

2026-11-04 R5 协议修复见[ADR0021](adr/0021-keyed-ranking-and-bounded-correction.md)：新 P13v3 使用程序固定槽位与严格 Schema，局部失败有一次定向格式修复，持久账本限制每构建最多两个请求槽位；旧排序失败可独立续接并重验复用 P12。协议实现轮未调用模型，随后本轮按用户要求补做2次真实请求，结果与交付见[progress](progress.md)。

完整产品流程见[项目介绍中的流程图](../README.md#从论文到阅读知识)及[产品设计](01_product_design.md)：论文 → 原文/证据/候选 → 自动构建论文知识图谱 → 图谱驱动的 Query → 明确保存为衍生综合 → 整理 Wiki → 授权导出 Markdown；Lint 横向检查证据、支撑结构、依赖和文件状态。

知识图谱提供结论单元、支撑路径、跨论文关联与条件比较结构，支撑 Query 的扩展检索、Wiki 的内容组织和 Lint 的结构检查。画布是交互入口，完整有效知识仍可检索，未选候选不会因未显示而丢失。

P4 Query 与 P5 Lint/Wiki 的详细待开发任务、实现方法、依赖顺序和验收门槛集中在[开发计划](06_development_migration_plan.md)。P4分Q01–Q08，P5分L01–L04/W01–W05；实际仍在P3/R5，本轮只重写计划与介绍，没有把参考契约记成已实现，也未开始后续Phase。

Query读取Wiki状态、问答沉淀形式及Obsidian检查边界见[ADR0018](adr/0018-query-wiki-and-obsidian-lifecycle.md)：Wiki是以图谱与已保存综合为组织依据的阅读文档，Markdown是其可导出表达；保存回答新增有据衍生知识，可在独立衍生图层查看，整理Wiki/导出Markdown分别明确。P4先建最小文档读取/状态，P5扩展生成发布。内容有效性和文件同步分开；授权受管Markdown与独立私人只读笔记区分，不把整个Obsidian Vault都当作Wiki。

最新 R5 协议修复与交付见[本轮验收](ranking-protocol-verification-20261104.md)，上轮真实质量失败见[历史记录](r5-final-verification-20261103.md)，支撑路径规则见[ADR0019](adr/0019-support-path-revalidation.md)。用户已反馈上一安装包三篇同显、悬停拖动、颜色图例、全屏Esc、重启知识布局五项全部通过；新包、真实科学质量与strict分别记录。界面改动历史见[图谱工作区验收](graph-workspace-verification-20261103.md)，仍不进入 P4/P5。

本轮实现设计见 [ADR0017：语义协议、程序组图与阶段恢复](adr/0017-semantic-protocol-and-stage-recovery.md)。新 P02v4 只输出语义，身份由程序绑定；P12 仅关系/重复提案，程序沿全部已验证路径组单元，P13 仅贡献建议。Provider 输出策略冻结，首次失败视图明确 provisional/pending/partial，新/缓存共用完整终验。旧协议与成功检查点保留，head0011/领域1.0不变；本轮实测由 progress 另记，真实 strict API 尚未验证。

最新改造、实际测试与安装包见[语义协议与阶段恢复验收](semantic-reliability-verification-20261103.md)；前轮见[P13 JSON 响应恢复验收](selection-json-verification-20261103.md)、[完整整合/选择上下文验收](complete-context-verification-20261103.md)和[结构解析、默认支撑与响应恢复验收](structured-reading-verification-20261103.md)。

当前增量：[结构文档与支撑图谱 ADR0014](adr/0014-structured-pdf-and-support-graph.md)。跨页章节、行及表格结构作为版本化解析旁表保存，References 不参与抽取；新任务移除 6000 字符/48 证据目标，默认展示结论的方法、实验、条件、结果和指标。实际测试、真实调用及安装状态以 [progress](progress.md) 为准。前轮交付记录见[新版范围与抽取恢复验收](schema-scope-verification-20261102.md)。

[完整整合/选择上下文 ADR0015](adr/0015-complete-reading-context.md) 继续移除 P12/P13 的固定软件预算：新 P12 全部候选/完整引用证据一窗，P13 全部单元一次；旧冻结窗口及检查点复用，真实模型容量和有界超时不取消。

历史 [P13 严格解析及单字符语法恢复 ADR0016](adr/0016-selection-json-syntax-recovery.md) 在旧 P13 正常/恢复后均拒绝重复键与 NaN/Infinity，仅处理已确认的末尾 coverage_gaps 完整非空字符串数组漏 `]`。其“其他阶段不变”为当轮范围；新语义三阶段均严格解码，无通用语法恢复。raw与审计保留，完整重验才复用，不推断语义完整；实际历史结果见该报告，本轮结果见 progress。

当前设计为 **v3.3 阅读辅助知识图谱**：辅助阅读、理解和整理科研论文，覆盖不同论文类型，不预设具体研究方向。目标是选择论文直接自动生成知识图谱，流程不包含人工审核。决策见 [ADR 0008](adr/0008-reading-knowledge-graph.md)。

## 当前目标与实际工程

当前已接入：来源/完整证据 → 候选抽取 → 论文级整合 → 自动关键性选择 → Paper→核心结论→支撑知识的分层图谱；R5本轮三项补验收在明确范围内通过，限制见新报告。

后续待实现：Query依据问题检索并沿完整图结构补齐条件/方法/证据，同时读取有效Wiki、保存综合和授权个人资料；明确保存后经同一Store新增衍生知识。Wiki用图谱结构组织文档，逐段追踪根证据；Lint检查知识与文档/文件的不同状态。详见[实施顺序](06_development_migration_plan.md)。

**R0规范已落地到R1–R4；R5三项补验收已完成，不扩大为全模型/全论文科学质量认证。** 当前 Alembic head0011、领域reading-extraction-1.0、入口paper-reading-v1；新模板为P02_reading_extract_compact_v4/P12_reading_associations_v1/P13_reading_ranking_v3，旧v1/v2冻结计划保持原协议。新选择带原文、疑点与数字排版风险，见[ADR0020](adr/0020-evidence-aware-core-selection.md)，键控评估及恢复见ADR0021。此前v2失败记录保持，本轮v3成功另记，不追加模型调用；P4 Query/P5 Lint/Wiki未开始。

## 当前设计入口

| 内容 | 文档 |
| --- | --- |
| 决策与产品流程 | [00 范围](00_decisions_and_scope.md) · [01 产品](01_product_design.md) |
| 统一引擎与数据 | [02 架构](02_architecture_and_workflows.md) · [03 Schema](03_schema_design.md) |
| 分层阅读交互 | [04 图谱](04_graph_interaction_spec.md) |
| 模型任务与自动整合 | [05 Prompt](05_prompt_engineering.md) · [13 个模板](prompts/) |
| 开发顺序 | [06 当前 R5 与后续 P4/P5 计划](06_development_migration_plan.md) |
| API/验证/工程 | [07 目标接口](07_api_and_events.md) · [08 验证](08_validation_and_security.md) · [09 注记](09_reference_implementation_notes.md) |
| 可执行参考 | [Pydantic](schemas/contracts.py) · [JSON Schema](schemas/generated/) · [SQL 草案](schemas/sqlite_reference.sql) · [合成示例](examples/README.md) · [测试](tests/test_contracts.py) |
| 变更与兼容 | [变化摘要](CHANGELOG_FROM_V3.md) · [代码映射](migration/v3_to_reading_assessment.md) · [本轮规范验证](reading-design-verification-20261102.md) |

## 已实现工程与历史验收

- [输出能力与Schema精简](compact-output-verification-20261102.md)：移除32K/64K二次限额，统一继续入口；紧凑格式无损展开，真实响应保存12候选/10有效关联，全文待验收。见[ADR0012](adr/0012-compact-extraction-and-model-output-ceiling.md)。
- [腾讯云超时与空图谱恢复](tencent-recovery-verification-20261102.md)：单个真实失败子批约9.5秒通过；明确流式/思考策略、续接成功批次和部分图谱，全文待验收。见 [ADR 0011](adr/0011-tencent-streaming-and-reading-recovery.md)。
- [阅读响应恢复](reading-response-verification-20261102.md)：精确重复去重与失败结果复用，真实响应副本 20 候选/24 关联通过，零新调用；全文和安装反馈待验收。规则见 [ADR 0010](adr/0010-reading-response-deduplication.md)。
- [根 README](../README.md)、[运行 API](api.md)、[模型设置](model-configuration.md)、[开发日志](../DEVELOPMENT_LOG.md)、[安全检查](security-checks.md)。
- [抽取可靠性](extraction-reliability-verification-20261102.md)：当轮真实 Schema 任务副本 4/4 成功；另一响应超时任务当时 6/17。当前状态见上方新报告，历史结果不改写。
- [图谱与抽取稳定性](stability-verification-20261102.md)、[图谱/输出预算优化](refinement-verification-20261102.md)、[v3 M0–M6 验收](v3-verification.md)。
- [P3](phase3-verification.md)、[P1/P2](phase1-verification.md)、[P0](phase0-verification.md)、[环境](environment-check.md)。这些是原执行记录，不能作为新设计验收。

## 版本与归档

[原 v3 资产](archive/v3/README.md)、[v2 规范](archive/v2/README.md)、[历史索引](archive/README.md)保留旧规则；原 v3 编号映射见 [整理记录](migration/v3-documentation-map.md)。当前设计在 docs 原目录维护，不新建版本包文件夹作为主入口。

参考 contracts.py 不是运行 API。新旧 Prompt 通过版本适配接入，不直接覆盖 [运行模板](../services/engine/researchgraph/prompts/)。设计、DTO、Prompt、应用 0.0.1 和数据库迁移号分别管理。

```powershell
conda run -n researchgraph-studio python docs/schemas/contracts.py
conda run -n researchgraph-studio python -m pytest docs/tests -q
conda run -n researchgraph-studio python -m pytest docs/archive/v3/tests -q
conda run -n researchgraph-studio python -m pytest docs/archive/v2/tests -q
```

三个测试目录分进程执行，避免 contracts 模块同名冲突。参考测试不替代应用回归、真实模型或安装验收。

## 数据所有权与安全

Zotero 权威管理文献/PDF/批注，ResearchGraph 只读访问；SQLite 保存持久证据、候选、模型历史与图谱组织；Obsidian 私人笔记只读，导出只写用户授权目录。图谱选择不删除证据，也不意味着长期复制 Zotero PDF。

密钥只存 OS 凭据管理器；私人资料/运行库/模型输出/日志/安装器不进仓库。用户未授权不得 Push。四份外部补充原文登记路径仍不可用，保留[来源登记](design/source-register.md)及 QA 历史，不冒充核验通过。

## 清单与下一步模板

[MANIFEST](MANIFEST.md) 与 [SHA256SUMS](SHA256SUMS.txt)覆盖当前设计及参考资产，排除归档/运行报告；[AGENTS 模板](AGENTS.template.md)、[下一轮模板](CODEX_NEXT_TURN.md)仅在用户要求开发时使用。
