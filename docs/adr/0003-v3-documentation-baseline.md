# ADR 0003：采用 v3 文档基线并保留工程与历史

日期：2026-11-02（Asia/Shanghai）。状态：文档基线已采用；v3 工程迁移尚未执行。

用户提供了 [v3 自动建图与轻量图谱规范包](../README.md)，要求据此删除、整理或合并相关文档。旧 v2 规范与新包并列会造成产品流程、Prompt 编号和阶段计划冲突；现有 P0–P3 工程、运行契约和验证结果仍需继承。

1. 以 v3 为唯一当前设计入口，根目录 README、AGENTS 和 [docs 导航](../README.md)统一引用。适用的工程约束合并到 AGENTS，不整体覆盖原有环境、权限和安全规则。
2. 将旧 v2 规范、Prompt、Schema、示例和测试整体移至 `docs/archive/v2/`，保持包内结构；添加历史标记并修复链接，不销毁需求依据、审核决策或历史验收。
3. 按用户追加要求将 v3 章节直接放到 `docs/`，参考资产放到 `docs/schemas/`、`prompts/`、`examples/`、`tests/`。原包 README 合并进文档导航，清单与哈希按新路径重建；设计含义和契约不变，原始输入备份留在本机忽略目录。参考 SQL、指令模板、DTO 不作为自动迁移或立即开发授权。发现的冲突登记在[整理映射](../migration/v3-documentation-map.md)，实施前明确兼容方案。
4. v3 采用完整领域模型、抽取 DTO、轻量 GraphProjection 分层；默认展示通过来源校验的未审核知识，AI 推理仍是候选。短标签和可选人工纠错不意味着丢弃 Evidence、Condition、Experiment、Finding、原始模型输出或已有审核历史。
5. 本次不修改运行代码、数据库、生成 API 或运行 Prompt。当前 Alembic head 仍为 0008。后续先执行 v3 M0 工程审计，再决定加性迁移与接口适配；不能仅根据文档宣称现有代码存在强制审核阻塞。
6. 文档验证使用独立的 v2/v3 契约测试进程、链接检查和哈希核对。本轮不构建安装器、不运行真实模型、不 Commit/Push，也不启动 P4/P5。

本决定补充而非撤销 [v2-0001](0001-unified-knowledge-engine.md)、[v2-0002](0002-phase3-models-and-reasoning.md)的有效工程约束。旧 `docs/decisions/` 编号保持；`docs/00_decisions_and_scope.md` 中的 ADR-RG-003 是原规范自己的标识，不与本目录编号混用。
