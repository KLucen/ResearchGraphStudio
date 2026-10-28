# 数据契约

Pydantic/FastAPI 是单一来源。openapi.json 由 scripts/export-contracts.py 导出，generated.ts 由 openapi-typescript 生成；禁止手工修改生成文件。

在仓库根目录执行 `pwsh -File scripts/check-phase0.ps1` 会重新生成并检查消费者类型；CI 额外使用 Git diff 检查契约漂移。

Phase 0 已实现 Project、Job、Health，调用规则见[API](../../docs/api.md)。后续证据、Claim/Review、RelationAssertion 和 Wiki 按[领域模型](../../docs/design/domain-model.md)扩展。Job 运行状态不复用知识审核六态或 Wiki 发布态。
