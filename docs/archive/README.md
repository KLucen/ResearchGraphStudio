# 历史文档索引

当前设计从 [v3.3 阅读辅助设计](../README.md)进入；实际状态从[进度](../progress.md)进入。本目录保存被替代的设计材料，历史指令、阶段编号、目标指标不作为当前施工命令。

| 材料 | 处置与用途 |
| --- | --- |
| [原 v3 平铺设计](v3/README.md) | 2026-11-02 R0 前 52 项设计/Schema/Prompt/示例/测试快照；当前规则已由阅读辅助设计替代 |
| [v2 规范包](v2/README.md) | 三份设计主文档、Agent 模板、10 个 Prompt、11 份契约文件、2 个示例、1 份测试随原入口一同归档，共 29 文件；内部相对结构保留 |
| [早期需求基线](../design/requirements-baseline.md)与[领域约定](../design/domain-model.md) | 原路径保留并标为历史，供需求和旧 API 演变追溯 |
| [来源登记](../design/source-register.md)与 [QA 原件](../../QA.md) | 保留来源、原始哈希及核验限制，不改写原件 |
| [旧 decisions](../decisions/)与 [v2/v3 ADR](../adr/) | 保留编号、采用时间和适用范围，不删除仍有效的 Tauri、来源、任务与数据安全决策 |
| [v1→v2 评估](../migration/v1_to_v2_assessment.md)与 [P1 交接](../handovers/2026-10-31-phase1-status.md) | 历史工程快照，不能替代下一次 v2→v3 工程审计 |
| [P0](../phase0-verification.md)、[P1/P2](../phase1-verification.md)、[P3](../phase3-verification.md)验收与[环境快照](../environment/) | 保留实际执行证据；新设计不反向改写历史结果 |
| [旧实验协议](../../experiments/README.md) | 保留 E1–E6 编号和原假设，后续按 v3 目标补充实验映射 |

`development-plan-v0.3.md` 和 `development-plan-v0.4.md` 在本轮开始前已经删除，本轮不恢复，也不把它们计入新增归档。[v0.3 历史版本](https://github.com/KLucen/ResearchGraphStudio/blob/8e15a9583a7a6becff9d49800af3717eee867121/docs/development-plan-v0.3.md)与 [v0.4 历史版本](https://github.com/KLucen/ResearchGraphStudio/blob/8e15a9583a7a6becff9d49800af3717eee867121/docs/development-plan-v0.4.md)通过固定 Git 引用保留。

旧 v2 内容仅在归档中维护；`docs/01_product_design.md` 现由 v3 产品设计使用，新计划和 Schema 分别位于 `docs/06_development_migration_plan.md`、`docs/03_schema_design.md`。不再保留旧 v2 计划和契约的重复现行入口。迁移对应见[文档整理映射](../migration/v3-documentation-map.md)。
