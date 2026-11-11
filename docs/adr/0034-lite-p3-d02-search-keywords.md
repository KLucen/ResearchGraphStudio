# ADR 0034：Lite P3 D02 可选英文关键词辅助

日期：2026-11-10（Asia/Shanghai）

状态：已实现，待真实 Provider 验证

## 决策

Lite D02 只作为 D01 局部问答前的本地检索辅助。客户端先运行当前作用域的 SQLite/FTS5 检索；只有服务端再次确认没有命中，且用户明确允许一次模型调用时，才创建 `search_keywords` 任务。任务只向 Provider 发送用户问题、论文标题和可选章节标题，不发送 PDF 正文、EvidenceSpan、批注或整篇文献。

模型只能返回 `SearchKeywordsDraft`：1–5 个去重的短英文关键词或短语。服务端拒绝重复 JSON key、未知字段、空词、超长词和非 JSON 响应。关键词结果保存为独立的 `lite_keyword_records`，缓存键绑定项目、论文、文献版本、章节、问题输入、Prompt、Schema、Provider、模型、配置和源哈希；缓存命中记录 0 新调用和 0 新 Token。

完成后关键词只重新运行本地 FTS5，并在桌面端展示命中片段。D02 不生成问答、不会自动扩大 `section → paper` 作用域，也不把关键词当作证据或科学结论。生成任务失败、取消或重启时保留记录和 raw 输出，不自动重发。

## 接口与数据

- `POST /api/v1/papers/{paper_id}/qa/keywords`：需要 `allow_network=true`，返回 `KeywordView`；首次通常为 `PENDING`。
- `GET /api/v1/papers/{paper_id}/qa/keywords`：按文献版本/章节读取历史记录。
- `GET /api/v1/papers/{paper_id}/qa/keywords/{keyword_id}`：轮询单条任务，完成时 `keywords.english_queries` 可用于本地重检索。
- Alembic `lite0004` 新增 `lite_keyword_records`，复用 `LiteCacheEntry` 和 `LiteTokenUsage`。

## 验收边界

D02 专项测试使用匿名论文和合成 Provider，覆盖严格契约、上下文不含正文、usage 记录、缓存身份与服务端本地命中阻断。当前真实 Provider 调用、真实 Token/费用、复杂版面和用户原生安装体验仍未验收；`unknown` 继续表示信息缺口，不据此推断矛盾或补造实验条件。
