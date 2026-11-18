# ADR0046：首次读取时一次性升级旧 PDF 章节结构

日期：2026-11-16（Asia/Shanghai）。状态：采用。

## 问题

`structure-v2` 已经修复了混合字号标题、印刷目录和附录后的章节识别，但已有论文仍可能只有早期 `structure-v1` 存档。普通打开论文时如果始终复用旧解析树，界面会继续显示 `1 INTRODUCTION` 后直接出现 `5 CONCLUSION`，并把印刷目录中的 `5 Conclusion` 当成第二个章节。用户必须先手动点击“重新整理本地阅读版面”才能看到新树，这使已保存的本地阅读版面看起来像每次都要重新加载。

## 决策

1. `GET /api/v1/papers/{paper_id}/reading-document` 和 `GET /api/v1/revisions/{revision_id}/sections` 在读取当前树前检查 `DocumentParse.parser_version`。当当前登记的解析版本不是 `structure-v2` 时，触发一次本地兼容升级；已有 `structure-v2` 时保持纯本地读取，不再次扫描 PDF。
2. 升级只接受数据库中已登记、路径允许且 SHA-256 与 `AttachmentRevision.sha256` 完全一致的 PDF。解析使用现有 `_scan_pdf`/`parse_structure`/`apply_structure`/`index_document`，不接受客户端路径，不调用 Provider，不创建模型任务或用量记录。
3. 升级在读取快照中完成文件读取和解析，在短写事务中再次核对论文版本和 SHA 后加性发布新的 `DocumentParse`、`Section` 和派生 FTS。旧解析、旧 Section、Chunk、EvidenceSpan、笔记、问答结果、个人状态和外部 PDF 保留；新章节通过精确的原始块定位复用已有 Span，不重写历史来源身份。
4. 发布前重新检查当前解析版本和来源。并发 GET 只能有一个请求发布 `structure-v2`；其余请求重新读取已提交的新树或返回本次读取得到的稳定旧树，不能覆盖较新的解析或删除旧数据。
5. 原始 PDF 不可用、字节变化、解析与已登记块无法逐一核对或数据库写入失败时，保留旧解析和本地存档，并返回明确的本地整理提示。普通读取不因升级失败删除历史数据；用户仍可稍后使用显式刷新重试。

## 结果

已有 Lite 用户打开论文即可获得当前章节树，不需要删除数据库、重新导入 Zotero 或先手动点击刷新。新版树应恢复正文主章、二/三级标题并排除印刷目录材料；阅读目录仍由前端按后端返回顺序和 `parent_id` 展示。结构升级只改变本地解析/章节派生数据，真实模型调用和 Token 为 0。

## 边界

PDF 本身缺少文字、扫描页、复杂版面、公式或表格语义时，自动升级不会添加 OCR 或科学解释；这些内容仍按现有结构解析边界保留原文和提示。若源 PDF 已被外部替换，系统不会把新字节静默绑定到旧 revision。该决策只处理旧结构版本兼容，不恢复完整 Knowledge Engine、Lint、Wiki、跨论文推理或 PDF 翻译功能。

## 验证要求

- 首次 GET 能从匿名旧 `structure-v1` 生成 `structure-v2`，章节顺序恢复，重复目录标题消失。
- 第二次 GET 不再读取或扫描 PDF；返回内容和投影哈希稳定。
- 原始 Chunk/Span、旧结构、历史结果和用量保持；源文件缺失或 SHA 变化时旧数据仍可读。
- 两个并发 GET 至多发布一个新结构，且不产生模型请求。
