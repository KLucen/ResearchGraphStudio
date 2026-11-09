# 文档导航

更新：2026-11-09（Asia/Shanghai）。当前为 **ResearchGraph Lite P0（A+B+D）**，Alembic head `0022`。新项目默认本地解析/章节/FTS5 索引且 0 次 LLM 调用；旧项目 `legacy` 和历史图谱保持可读。完整 P5/Lint/Wiki 作为旧兼容能力保留但不再是 Lite 默认路径；B/A/D 业务仍待后续阶段。当前状态集中维护在[实施进度](progress.md)，本页提供文档入口。

Lite P0 迁移评估见[文档](migration/lite_from_v3_assessment.md)，决策见[ADR0031](adr/0031-researchgraph-lite-p0.md)。

## 先读哪些文档

| 目的 | 入口 |
| --- | --- |
| 了解产品和实际进度 | [根 README](../README.md) · [实施进度](progress.md) |
| Lite 迁移与当前基线 | [Lite 规范](researchgraph_lite_ABD/README.md) · [迁移评估](migration/lite_from_v3_assessment.md) · [重构前基线](current_project_baseline.md) · [ADR0031](adr/0031-researchgraph-lite-p0.md) |
| 接续当前开发 | [根协作规则](../AGENTS.md) · [下一轮续接](CODEX_NEXT_TURN.md) · [开发日志](../DEVELOPMENT_LOG.md) |
| 查看最新 P5 验证和操作步骤 | [Lint 性能与进度报告](p5-lint-performance-verification-20261107.md) · [P5 实施报告](p5-verification-20261105.md) · [扫描反馈修复](p5-scan-feedback-verification-20261105.md) |
| 查阅历史结果 | [历史报告索引](archive/reports/README.md) · [完整旧进度](archive/reports/progress-through-20261105.md) · [历史设计索引](archive/README.md) |

产品辅助科研论文阅读，不预设研究方向。Lite 默认先本地解析和索引；下述 v3.3/00–09 完整模式设计仍保留“论文→核心结论→有据支撑”的历史兼容边界。原文、表格、证据和模型原输出不删除；旧 Query/Wiki/Lint 的授权、来源和写入要求继续适用，但不会因打开 Lite 论文而自动执行。

## 当前设计与运行说明

| 内容 | 文档 |
| --- | --- |
| 决策与产品 | [00 范围](00_decisions_and_scope.md) · [01 产品](01_product_design.md) |
| 统一引擎与数据 | [02 架构](02_architecture_and_workflows.md) · [03 Schema](03_schema_design.md) |
| 图谱与阅读交互 | [04 交互](04_graph_interaction_spec.md) |
| 模型任务与协议 | [05 Prompt](05_prompt_engineering.md) · [模型配置](model-configuration.md) |
| 阶段任务与退出条件 | [06 实施计划](06_development_migration_plan.md) |
| API/事件 | [07 设计与实现差异](07_api_and_events.md) · [运行 API](api.md) · [生成 OpenAPI](../packages/contracts/openapi.json) |
| 验证、安全与工程 | [08 验证](08_validation_and_security.md) · [09 实施注记](09_reference_implementation_notes.md) · [敏感内容检查](security-checks.md) |
| 文档生命周期与依赖诊断 | [ADR0018](adr/0018-query-wiki-and-obsidian-lifecycle.md) · [P5 ADR0029](adr/0029-lint-wiki-workflows-and-managed-publication.md) · [Lint 性能 ADR0030](adr/0030-lint-performance-and-progress.md) |

设计 `v3.3`、应用 `0.0.1`、数据库迁移号、领域/传输/Prompt 版本分别管理。当前设计描述产品和实现边界；实际运行请求以 Pydantic、[OpenAPI](../packages/contracts/openapi.json) 和 [api.md](api.md) 为准。

## 参考资产与决策

| 资产 | 用途 |
| --- | --- |
| [参考 Pydantic](schemas/contracts.py) / [JSON Schema](schemas/generated/) / [SQL](schemas/sqlite_reference.sql) | 可执行设计参考，不能直接代替运行 DTO 或在用户库执行 SQL |
| [参考 Prompt](prompts/) / [运行 Prompt](../services/engine/researchgraph/prompts/) | 设计模板与版本化运行模板分开；不覆盖历史 Prompt/hash |
| [合成示例](examples/README.md) / [参考测试](tests/test_contracts.py) | 结构与边界验证，不等于真实科学质量 |
| [ADR](adr/) / [旧 decisions](decisions/) | 记录决策采用时间、适用范围及后续替代；不能把旧阶段限制当当前指令 |
| [v3→v3.3 变化](CHANGELOG_FROM_V3.md) / [兼容映射](migration/v3_to_reading_assessment.md) | 设计和旧实现的对应 |
| [MANIFEST](MANIFEST.md) / [SHA256SUMS](SHA256SUMS.txt) | 当前规范资产的 LF 字节与哈希清单，不是所有报告或软件发布清单 |

Query 决策沿 [ADR0022](adr/0022-query-foundation-and-versioned-context.md)～[ADR0028](adr/0028-query-scientific-guidance-and-citation-closure.md) 演进；阅读流程沿 [ADR0008](adr/0008-reading-knowledge-graph.md)、[ADR0014](adr/0014-structured-pdf-and-support-graph.md)、[ADR0017](adr/0017-semantic-protocol-and-stage-recovery.md) 和 [ADR0021](adr/0021-keyed-ranking-and-bounded-correction.md) 维护。历史失败和成绩从报告索引进入，不在多份当前文档中重复叠加。

参考资产需要变更时，使用 Conda 项目环境分进程检查：

```powershell
conda run -n researchgraph-studio python docs/schemas/contracts.py
conda run -n researchgraph-studio python -m pytest docs/tests -q
conda run -n researchgraph-studio python -m pytest docs/archive/v3/tests -q
conda run -n researchgraph-studio python -m pytest docs/archive/v2/tests -q
```

## 归档和维护规则

- 当前 00–09、运行说明、进度和续接文件维护最新状态；测试分母、包 hash 和未测项以对应报告为准。
- 已结束轮次的报告放在 [archive/reports](archive/reports/README.md)，保留失败、调用预算、授权和未知结果。旧报告里的“当前/head/未进入 P5”只适用于报告日期。
- [v2](archive/v2/README.md)、[原 v3](archive/v3/README.md)、[迁移评估](migration/)与[环境快照](environment/)保留追溯；历史来源登记和 [QA 原件](../QA.md)不因整理改写。
- 冗余的 `AGENTS.template.md` 已由根 [AGENTS.md](../AGENTS.md)替代；`CHANGELOG_FROM_V2.md` 的跳转页已移除，直接访问[历史变化原文](archive/v3/CHANGELOG_FROM_V2.md)。
- Zotero、私人笔记和用户原文默认只读；读取、模型用途与发布目录授权分开。密钥仅存 OS 凭据，私人材料、运行库、模型 raw、日志和安装器不进入源码。
- 真实 strict、复杂版面/无 OCR、跨平台/干净机和 S1–S4 外部原文仍按报告保留限制，[来源登记](design/source-register.md)不能冒充已核验结果。
