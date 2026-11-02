# 文档导航

当前设计为 **v3.3 阅读辅助知识图谱**：辅助阅读、理解和整理科研论文，覆盖不同论文类型，不预设具体研究方向。目标是选择论文直接自动生成知识图谱，流程不包含人工审核。决策见 [ADR 0008](adr/0008-reading-knowledge-graph.md)。

## 当前目标与实际工程

目标流程：来源/完整证据 → 候选抽取 → 论文级整合 → 自动关键性选择 → Paper→核心结论→支撑知识的分层图谱。未选候选仍保留并可被后续 Query 检索；Wiki 使用逐段证据和版本依赖。

**本轮 R0 是规范与参考契约交付，不是新流程已经运行。** 代码仍为 P3/v3 M0–M5 核心及稳定性增量；M6 有未验收项。运行 Alembic 0009、DTO unified-v3.1、P02 3.2。下一步 R1 候选/单元/选择持久化和旧数据适配，随后 R2–R5；P4 Query/P5 Lint/Wiki 未开始。实际进度见 [progress](progress.md)。

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

- [根 README](../README.md)、[运行 API](api.md)、[模型设置](model-configuration.md)、[开发日志](../DEVELOPMENT_LOG.md)、[安全检查](security-checks.md)。
- [抽取可靠性](extraction-reliability-verification-20261102.md)：真实 Schema 任务副本 4/4 成功；另一响应超时任务仍 6/17，不宣称解决。
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
