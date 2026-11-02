# 文档导航

最新实现：[新版范围与抽取恢复验收](schema-scope-verification-20261102.md)、[ADR0013](adr/0013-current-schema-and-bounded-recovery.md)。正常建图使用新版候选；旧数据不删除，旧阅读任务继续时升级未完成部分。以下历史记录的旧任务冻结规则仅用于历史重现。

> 2026-11-02 实现更新：R1–R4 已接入，R5 部分验收；Schema head 0010，产品入口 paper-reading-v1。P02_reading_extract/P12_reading_integration/P13_reading_selection 为独立运行模板，旧任务模板不改。默认分层图谱、全部候选搜索与显示偏好已可用，无人工审核。下一步限于 R5 全文质量/响应可靠性与安装反馈，未进入 P4/P5。当前正式库 275 条知识在隔离迁移中逐行保持。报告见 docs/reading-implementation-verification-20261102.md（相对仓库根）。

当前设计为 **v3.3 阅读辅助知识图谱**：辅助阅读、理解和整理科研论文，覆盖不同论文类型，不预设具体研究方向。目标是选择论文直接自动生成知识图谱，流程不包含人工审核。决策见 [ADR 0008](adr/0008-reading-knowledge-graph.md)。

## 当前目标与实际工程

目标流程：来源/完整证据 → 候选抽取 → 论文级整合 → 自动关键性选择 → Paper→核心结论→支撑知识的分层图谱。未选候选仍保留并可被后续 Query 检索；Wiki 使用逐段证据和版本依赖。

**R0 规范已落地到 R1–R4，R5 部分验收。** 软件运行 Alembic 0010、paper-reading-v1 和独立 P02/P12/P13；旧任务保留 unified-v3.1/P02 3.2。下一步补充全文质量、响应可靠性及安装反馈，P4 Query/P5 Lint/Wiki 未开始。实际进度见 [progress](progress.md)。

## 当前设计入口

| 内容 | 文档 |
| --- | --- |
| 决策与产品流程 | [00 范围](00_decisions_and_scope.md) · [01 产品](01_product_design.md) |
| 统一引擎与数据 | [02 架构](02_architecture_and_workflows.md) · [03 Schema](03_schema_design.md) |
| 分层阅读交互 | [04 图谱](04_graph_interaction_spec.md) |
| 模型任务与自动整合 | [05 Prompt](05_prompt_engineering.md) · [13 个模板](prompts/) |
| 开发顺序 | [06 计划 R0–R5](06_development_migration_plan.md) |
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
