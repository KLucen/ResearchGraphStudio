# ADR v2-0001：保留旧工程的统一 Knowledge Engine

> v2 实施决策记录：下文范围与编号对应当时版本。后续全局安全配置和 P3 见 [ADR v2-0002](0002-phase3-models-and-reasoning.md)，当前 v3 文档基线见 [ADR 0003](0003-v3-documentation-baseline.md)；仍有效的数据与证据约束继续保留。

日期：2026-11-01（Asia/Shanghai）。状态：采用。依据：新版产品、开发计划和知识契约；范围 P1 兼容补全与 P2。

1. 保留 Tauri/React/FastAPI、`services/engine/researchgraph`、Conda `researchgraph-studio`、SQLite/Alembic；不新增服务、uv、Neo4j 或多 Agent。
2. Ingest/未来 Query/Lint 是统一 Knowledge Engine 的工作流。新证据/知识/审核/事件/revision 只经 KnowledgeStore 事务入口；既有 PDF 来源服务负责原件/版本导入，不复制事实库。
3. Paper、AttachmentRevision、Chunk 分别映射 Paper、DocumentVersion、paragraph。保留旧 API/ID/原文；新增 0005 加性表与可空事件字段，不重写旧数据。升级前沿用 SQLite 一致备份。
4. 证据规范化 identity-v1：原文原样、Unicode 字符偏移、全文 SHA-256。bbox 为解析块边界；不宣称词级/字级精度。章节索引保守，P01 不生成新位置。未来更强解析必须另建版本/映射。
5. 来源状态与审核状态分开。已验证作者主张以 unreviewed 保存；unknown/数值/归属疑点标 needs_review。模型不能输出正式 ID、权限、审核事件或修改 accepted 数据。人工修改创建历史版本与 ReviewDecision，原始 ModelRun 永久保留。
6. 节点表按 kind/paper/version/status/revision 与条件维度可查询，payload 经专用 DTO 校验，证据链接和依赖独立表。后续关系/综合可扩展类型；本轮不实现 P3+。
7. 抽取按有界片段批次执行 P01/P02，记录 Prompt/Schema/模型/参数/输入哈希/原始输出/错误，只有整批通过校验才提交；失败可重试，成功重复运行复用知识，不覆盖审核。
8. Zotero 仅固定 loopback Local API GET，导入 PDF 仍需用户原生选取授权。注释保留原始来源 ID/位置/评论，无法唯一定位时 unresolved。Obsidian 仅授权目录只读快照，不进入论文科学证据上下文。
9. 默认 MockProvider 明确标记为离线流程验证。真实 OpenAI-compatible Provider 需用户配置和每次抽取明确同意文本传输；密钥只由环境提供，不写数据库/日志/Git。

取代旧 ADR 0003 中 Zotero 延至 Phase 4 及旧单轴审核/关系枚举作为当前实施依据的部分。保留旧 ADR 历史，不重编号；本目录为 v2 决策，旧 `docs/decisions/` 仍可追溯。

验证：迁移备份/失败回滚、原 API 回归、权限边界、证据篡改/非法 ID、未知条件、归属、数值待审、并发 revision、重跑去重、失败/超时/非法 JSON、审核历史和重启持久化。最终执行结果见 `../progress.md`。
