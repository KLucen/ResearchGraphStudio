# ADR 0033：Lite P3 D01 局部证据问答

日期：2026-11-10

## 状态

已实施，D02 英文关键词扩展和真实 Provider 验收仍待后续阶段。

## 决策

Lite D01 使用现有章节解析结果和 SQLite FTS5 做本地检索，再把最多 5 个短 `EvidenceSpan` 发送给一次模型请求。默认作用域为 `section`，也支持 `paper`；`selection` 只接受服务端确认过的当前文献版本 Span ID。模型不能访问文件路径、数据库或未传入全文。

回答严格校验 `QAAnswerDraft`：支持性回答必须带引用，引用必须属于本次请求的 Span 白名单；证据不足使用 `insufficient_evidence=true`，可以提示用户手动扩大作用域，系统不自动扩大检索或追加更昂贵请求。无本地命中时直接保存证据缺口结果，不触发模型调用。

问答结果保存到独立 `lite_qa_records` 表，和 `lite_cache_entries`、`lite_token_usage` 绑定项目、论文版本、作用域、问题、检索输入、Prompt、Schema、Provider、模型、配置指纹和源哈希。缓存命中不产生新调用或 Token。问答只用于阅读历史与复习，不写入 KnowledgeStore、Claim 或 Relation。

任务沿用现有 Job/worker 生命周期，支持显式网络授权、失败/取消/重启状态、raw 输出保留和有限重试入口；GET 查询只读。桌面端默认展示当前小节问答，并明确显示作用域、处理状态、页码/Span 引用和证据不足提示。

## 结果与限制

- Alembic head 从 `lite0002` 增加到 `lite0003`。
- D02 关键词扩展、预算控件和真实模型质量/Token/价格尚未验收。
- 测试使用匿名/合成 PDF 和合成 Provider；本轮真实 Provider 调用和 Token 均为 0。
- 复杂公式、表格、图像和 OCR 仍需显示证据受限，不据缺失内容推断实验条件或矛盾。
