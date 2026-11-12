# 文献翻译撤下说明

更新：2026-11-12（Asia/Shanghai）。

用户在遇到 `TRANSLATION_PROVIDER_TRUNCATED` 后明确要求退回没有文献翻译功能的版本。当前应用已撤下翻译板块、翻译设置、相关业务 API 和执行器；安装包不再携带翻译 Server、PDFMathTranslate/BabelDOC 运行时或离线排版资源。撤下决策见 [ADR0040](adr/0040-remove-pdf-translation.md)。

论文阅读工作区继续提供论文概览（PaperCard + LightGraph）、章节精读和论文问答。Zotero 连接、本地 PDF/章节解析、文本索引、模型配置和统一用量保留；阅读工作区仍置顶，论文信息在页面底部默认折叠。

本次不降级或重建数据库，不删除已有论文、成果、布局、历史翻译行、任务快照、用量或生成文件。Alembic head 保持 `lite0008` 是为了已有数据库的迁移兼容，不表示翻译功能仍然可用。仍在排队或运行的旧翻译任务会停止为已取消并说明功能已移除，已完成、失败等终态记录保留；旧任务不自动恢复、重试或重放，不产生新的翻译模型请求。历史实际或未知用量保持原有含义。

[ADR0036](adr/0036-optional-pdf-translation-bridge.md)、[ADR0037](adr/0037-managed-translation-server.md)、[ADR0038](adr/0038-bundled-translation-and-reading-layout.md) 和 [ADR0039](adr/0039-translation-proxy-request-policy.md) 仅记录翻译方案的历史演进，不再作为当前安装、设置或使用步骤。ADR0038 中关于阅读布局的决定继续适用。

本次测试、零模型调用验证、Windows 安装包及隔离启动的实际结果见 [开发进度](progress.md) 和 [开发日志](../DEVELOPMENT_LOG.md)。历史翻译测试与旧安装包不代表本次回退的验证结果。
