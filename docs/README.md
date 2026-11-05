# 文档导航

2026-11-05 后续优化以 [P4改进验收](p4-followup-verification-20261105.md) 和 [ADR0028](adr/0028-query-scientific-guidance-and-citation-closure.md) 为准：已按新授权推送验收快照8d67ed1；新P07v3/冻结科学指导/可审计引用根补齐与本调用表示优化单独验证。旧质量分母/Prompt/raw保持，未测或性能未达标不记通过，不进入P5。

优化源码75061d2已推送，全量934 Python/124 React、本机P95=1.583589秒；新真实19段16支持/3部分，预算结束不再追加。178运行源与封存新包一致，独立CI run41959965368的构建与实际安装全部通过，新包用户原生反馈按报告单列。

2026-11-05 最新：[P4 最终回归与真实验收](p4-final-acceptance-20261105.md)记录当前安装版用户正常反馈、十题真实结果及数值错误修复补验；[ADR0027](adr/0027-query-layout-aware-numerical-grounding.md)说明新 P07 v2/冻结版式风险与旧 v1 兼容。性能优化保留完整验源，当前 head0014，不进入 P5。此前“新包原生待反馈”按各历史包理解；本轮新构建包的反馈另列。

2026-11-04 最新：本地问答历史“无效响应”实际为SQLite锁竞争，修复见[ADR0026](adr/0026-query-read-snapshots-and-worker-locks.md)及[锁修复验收](query-history-lock-verification-20261104.md)。8个纯读取路径/模型等待检查使用受保护快照，写入仍保留IMMEDIATE；正常worker及冻结HTTP并发已测，新包用户原生待反馈。head0014不变、零新真实调用，不进入P5。

2026-11-04 当前：P4-Q01～Q07 已接入，Q08 继续处理安装反馈与阅读交互。本轮增加各板块独立论文筛选、全部合法命中分页（每页 10 条）、来源的默认图谱标记、按论文分组回答及两层引用折叠，Alembic head 保持 **0014**。设计见 [ADR0025](adr/0025-query-browsing-and-paper-grouped-answers.md)，实际验证与限制见[本轮报告](p4-query-browsing-verification-20261104.md)。此前可读来源、整组问答、批注/移除见 [ADR0024](adr/0024-query-reading-cards-and-saved-lifecycle.md)及[反馈报告](p4-query-feedback-verification-20261104.md)；[ADR0023](adr/0023-grounded-query-and-explicit-saving.md)和[P4实际报告](p4-query-verification-20261104.md)保留前次交付记录。P5 Lint/Wiki 未启动，新包原生确认不以旧包反馈代替。

更新：2026-11-04（Asia/Shanghai）。[ADR0022](adr/0022-query-foundation-and-versioned-context.md)及[基础验收](p4-query-foundation-verification-20261104.md)保留 Q01～Q04/head0012 的历史范围；当前在此基础上完成 Q05～Q07，领域 `reading-extraction-1.0`、入口 `paper-reading-v1` 及历史抽取协议保持。Q08 的实际结果与未测项统一见本轮报告，不能用历史成绩代替。

本轮先将 R5 成果推送至 `main` 的 `80552d3`，[对应 CI](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41778202007) 的构建和独立安装验收均通过。随后新增的 Query 基础改动尚未再次 Commit/Push，不能将 R5 的远端成绩算作 Query 增量验收。最终命令、测试结果和限制以 [progress](progress.md)、[开发日志](../DEVELOPMENT_LOG.md)及实际报告为准。

## 当前目标与实际工程

产品辅助阅读、理解和整理不同类型的科研论文，不预设研究方向。当前设计为 **v3.3 阅读辅助知识图谱**，决策见 [ADR0008](adr/0008-reading-knowledge-graph.md)。新流程没有人工审核、待审队列或接受/驳回步骤。

已接入的论文流程为：来源与结构解析 → 保留原文/证据 → 候选抽取 → 论文级整合 → 自动核心选择 → Paper→核心 Claim→有据支撑的图谱。图谱组织结论、方法、实验、条件、结果和限制；画布只是交互视图，分页、折叠、隐藏与未入默认图都不限制完整合法知识检索。

Query 本轮已接入：

- **Q01**：项目级运行契约和执行记录、加性迁移、最小不可变文档/段落登记、根依赖及内容/文件双维状态。普通 Query、笔记授权和扫描审计不推进科学图修订。
- **Q02**：可重建 FTS5/精确检索索引，覆盖合法候选的原语言/已有中文/别名、题名、原文/表格、有效文档及用途允许的笔记；默认不读取私人笔记。
- **Q03**：从文本或 Wiki 根命中沿完整合法图路径补齐支撑，保留共享成员、条件四态、不同归属及重验后的科学关系；导航线和 `NO_DECISION` 不充当科学依据。
- **Q04**：`query-context-1` 冻结版本、hash、证据/只读 Chunk 区间、章节/表格、路径、用途授权与短编号映射；缓存读取和重放实时终验，不为查询创建论文知识。

上述基础供 **Q05** 的 P07 有据回答使用，发送前、收到原响应后及缓存恢复时均终验，最多两个持久请求槽位，失败不自动重发。**Q06** 将问题、来源、答案和保存组织成组，来源显示原文及已有中文要点，历史导航有可见加载/失败状态；本轮各板块独立按论文筛选并每页展示 10 条，本地预览可遍历全部合法词面命中，图谱标记基于完整默认阅读投影，回答按真实引用归组且引用默认两层折叠。**Q07** 通过 KnowledgeStore 保存所选段落及根依赖，并提供独立衍生图层、个人批注和移除；跨页或筛选不会丢失已勾选段落。批注不改模型答案，移除穿透后续检索与依赖，历史/raw/证据保留。保存采用确定性复制，不追加 P08 模型调用；本轮展示增量没有新增真实模型请求，也不改变冻结回答上下文。**Q08** 本轮回归和新包状态见[分页与分组验证报告](p4-query-browsing-verification-20261104.md)，前次反馈保留在反馈报告，具体门槛见[开发计划](06_development_migration_plan.md)。

## 完整生命周期与文档边界

目标流程见[项目介绍流程图](../README.md#从论文到阅读知识)和[产品设计](01_product_design.md)：论文 → 原文/证据/候选 → 自动知识图谱 → 图谱驱动 Query → 明确保存衍生综合 → 整理 Wiki → 授权导出 Markdown；Lint 横向检查来源、支撑、依赖和文件状态。显式保存综合已接入，Wiki 生成/发布及 Lint 仍属 P5 后续任务，流程图不是整条生命周期的完成证明。

[ADR0018](adr/0018-query-wiki-and-obsidian-lifecycle.md) 明确 Wiki 是有版本和逐段依赖的阅读文档，不是图谱本身，也不是整个 Obsidian Vault。Q01～Q04 先提供文档只读适配与状态消费，P5 再扩展生成和发布。内部有效版本可在文件缺失或外改时继续使用，但必须标出文件状态；外部新文本不会继承旧 manifest。个人资料用途授权沿根依赖穿透，不能借 Wiki 或综合绕过撤权。

默认 Query 只读。明确“保存为阅读知识”才经同一 Knowledge Store 新增 Synthesis/Insight 等衍生对象，不重写作者 Claim；指定内部文档目标需核对基线版本。P5 的主题整理、Wiki 生成和 Markdown 导出尚未启动。参考契约不能直接代替运行 API。

## 当前设计入口

| 内容 | 文档 |
| --- | --- |
| 决策与产品流程 | [00 范围](00_decisions_and_scope.md) · [01 产品](01_product_design.md) |
| 统一引擎与数据 | [02 架构](02_architecture_and_workflows.md) · [03 Schema](03_schema_design.md) |
| 图谱交互 | [04 图谱](04_graph_interaction_spec.md) |
| 模型任务 | [05 Prompt](05_prompt_engineering.md) · [参考模板](prompts/) · [运行模板](../services/engine/researchgraph/prompts/) |
| 开发顺序 | [06 P4/P5 任务与验收](06_development_migration_plan.md) |
| API/验证/工程 | [07 接口](07_api_and_events.md) · [运行 API](api.md) · [08 验证](08_validation_and_security.md) · [09 注记](09_reference_implementation_notes.md) |
| Query | [基础 ADR0022](adr/0022-query-foundation-and-versioned-context.md) · [回答/保存 ADR0023](adr/0023-grounded-query-and-explicit-saving.md) · [反馈修复 ADR0024](adr/0024-query-reading-cards-and-saved-lifecycle.md) · [浏览与分组 ADR0025](adr/0025-query-browsing-and-paper-grouped-answers.md) · [前次实际报告](p4-query-verification-20261104.md) · [反馈验收](p4-query-feedback-verification-20261104.md) · [本轮浏览验收](p4-query-browsing-verification-20261104.md) |
| 可执行参考 | [Pydantic](schemas/contracts.py) · [JSON Schema](schemas/generated/) · [SQL 草案](schemas/sqlite_reference.sql) · [示例](examples/README.md) · [测试](tests/test_contracts.py) |
| 变更与兼容 | [变化摘要](CHANGELOG_FROM_V3.md) · [代码映射](migration/v3_to_reading_assessment.md) · [规范验证](reading-design-verification-20261102.md) |

## R5 与既有功能的历史验收

R1～R4 已接入，R5 三项补验收在记录范围内通过。[R5 实际报告](r5-acceptance-verification-20261104.md)记录当时当前模型两篇 P13v3 各一次成功、零重复 P02/P12、成功后再继续零调用；32 条语义无支持与 2 条上标误读保留为候选但不入默认图，5 组同义结论各有一个核心代表。新包隔离检查和用户三项反馈通过。部分覆盖/有限证据提示继续保留，不扩大为全模型、全论文科学质量认证，也不替代后续真实 Query 验收。

- [历史续接反馈修复](history-retry-verification-20261104.md)：旧 `Claim.kind_note_unused=null` 失败已有成功后继，界面显示实际续接结果，不要求重复抽取。
- [键控贡献评估 ADR0021](adr/0021-keyed-ranking-and-bounded-correction.md)与[协议验收](ranking-protocol-verification-20261104.md)：程序固定完整槽位、严格 Schema、一次定向修复与最多两个持久请求槽位；旧协议和 raw 保留。[旧 R5 失败记录](r5-final-verification-20261103.md)不改写为成功。
- [支撑完整性 ADR0019](adr/0019-support-path-revalidation.md)、[证据感知选择 ADR0020](adr/0020-evidence-aware-core-selection.md)、[图谱工作区验收](graph-workspace-verification-20261103.md)。
- [语义协议 ADR0017](adr/0017-semantic-protocol-and-stage-recovery.md)与[验收](semantic-reliability-verification-20261103.md)：P02 只输出语义、程序组单元、统一终验及冻结输出策略，历史 head0011 不代表当前 head。
- [结构解析 ADR0014](adr/0014-structured-pdf-and-support-graph.md)与[验收](structured-reading-verification-20261103.md)：跨页章节和表格旁表，References 不抽取，默认显示合法支撑。
- [完整上下文 ADR0015](adr/0015-complete-reading-context.md)与[验收](complete-context-verification-20261103.md)、[旧 P13 精确 JSON 恢复 ADR0016](adr/0016-selection-json-syntax-recovery.md)与[验收](selection-json-verification-20261103.md)。
- [紧凑输出](compact-output-verification-20261102.md)、[流式与超时恢复](tencent-recovery-verification-20261102.md)、[阅读响应恢复](reading-response-verification-20261102.md)、[当前 Schema 范围](schema-scope-verification-20261102.md)。这些是对应轮次成绩，当前结果查 progress。
- [抽取可靠性](extraction-reliability-verification-20261102.md)、[稳定性](stability-verification-20261102.md)、[图谱/输出优化](refinement-verification-20261102.md)、[v3 M0～M6](v3-verification.md)、[P3](phase3-verification.md)、[P1/P2](phase1-verification.md)、[P0](phase0-verification.md)、[环境](environment-check.md)。

## 版本与归档

[原 v3 资产](archive/v3/README.md)、[v2 规范](archive/v2/README.md)和[历史索引](archive/README.md)保留追溯；编号映射见[整理记录](migration/v3-documentation-map.md)。主设计继续在 docs 原目录维护，不新建版本包目录。

设计、DTO、Prompt、应用 0.0.1 与 Alembic 迁移号分别管理。原文、Chunk/EvidenceSpan、历史任务签名及 raw 不因迁移或 Query 开发重写。参考测试分进程执行，不能代替应用回归、真实模型或安装验收：

```powershell
conda run -n researchgraph-studio python docs/schemas/contracts.py
conda run -n researchgraph-studio python -m pytest docs/tests -q
conda run -n researchgraph-studio python -m pytest docs/archive/v3/tests -q
conda run -n researchgraph-studio python -m pytest docs/archive/v2/tests -q
```

## 数据所有权与安全

Zotero 权威管理文献/PDF/批注，ResearchGraph 只读访问；SQLite 保存来源证据、候选、模型历史、图谱组织及文档/查询记录。Obsidian 私人笔记只读，Query 本地读取与模型外发用途分开，外发默认关闭。当前尚无 Wiki 文件发布能力。

密钥只存 OS 凭据管理器；私人材料、运行库、模型 raw、日志与安装器不进源码。Commit/Push 前检查实际内容和暂存区，未经新授权不 Push。真实 strict、复杂版面/无 OCR、跨平台/干净机与 S1～S4 四份不可用补充原文仍属限制，保留[来源登记](design/source-register.md)历史，不冒充核验通过。

[根 README](../README.md)、[模型设置](model-configuration.md)、[安全检查](security-checks.md)、[开发日志](../DEVELOPMENT_LOG.md)提供工程操作；[MANIFEST](MANIFEST.md)与[SHA256SUMS](SHA256SUMS.txt)维护规范资产清单。[协作附录](AGENTS.template.md)、[下一轮续接](CODEX_NEXT_TURN.md)用于接续已有工程，不能代替用户开发或上传授权。
