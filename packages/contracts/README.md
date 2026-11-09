# Lite 数据契约

Pydantic/FastAPI 是单一来源。`openapi.json` 由 `scripts/export-contracts.py` 导出，`generated.ts` 由 `openapi-typescript` 生成；禁止手工修改生成文件。

当前契约覆盖项目、论文、PDF/章节/FTS、任务、模型设置、Lite 用量、PaperCard 和 LightGraph 布局。没有 Evidence 节点、完整知识图谱、跨论文 Query、Lint 或 Wiki 路由。
