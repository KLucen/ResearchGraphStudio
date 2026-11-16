# 本地 Lite 研究引擎

researchgraph 实现 FastAPI 鉴权、Lite 项目/任务、SQLite 单写入者、Zotero 读取、PDF/章节解析、FTS5 索引、Provider 配置、统一用量、PaperCard + LightGraph、章节导读、证据问答与可选英文关键词辅助。选择论文、PDF 解析及索引均为本地处理，不调用模型。

开发使用 Conda 环境 `researchgraph-studio`。主 Sidecar 使用 PyInstaller onedir 打包；用户运行不依赖 Conda，不向 base 安装项目依赖。安装包不再携带翻译 Server、PDFMathTranslate/BabelDOC 运行时或其离线资源。

Lite 数据库为 `researchgraph-lite.sqlite3`，Alembic head 为 `lite0010`，增加独立阅读投影与全文笔记表，保留此前精读、理解检查和个人状态，沿用升级前备份。既有迁移及翻译表结构用于兼容；不降级或重建数据库，不删除论文、成果、布局、历史翻译行、用量、任务快照和生成文件。旧完整系统数据库仍与 Lite 库隔离，完整抽取、跨论文推理、Lint/Wiki 不属于活跃服务。

本地阅读投影区分标题、组合正文及折叠材料，并保留所有来源块和哈希。A04 一次明确请求为整篇可读正文生成译文及论证笔记；容量不足提前拒绝，不自动拆批。旧 A02 协议/结果兼容，默认界面只读其历史。A03 仅提交复述时检查理解；个人自评与图谱语义分离。A01 可选择最多三项可靠状态调整导读。所有模型任务使用现有 Provider、Job 和统一用量账本；GET、状态更新、缓存和重启不自动发模型。见 [ADR0041](../../docs/adr/0041-section-bilingual-close-reading.md) 与 [ADR0042](../../docs/adr/0042-paper-reading-document-and-notes.md)。

文献翻译已于 2026-11-12 按用户要求撤下，活跃引擎不再注册翻译路由，也不执行翻译 worker、模型代理或外部/随包运行时。旧任务不自动恢复，不允许通过通用重试重放；未完成任务停止为已取消，已有终态及 usage 保留，不将未知用量补成零。

撤下边界见 [ADR0040](../../docs/adr/0040-remove-pdf-translation.md) 与 [文献翻译撤下说明](../../docs/pdf-translation.md)。本轮测试、模型用量、构建和安装验证的实际结果以 [进度](../../docs/progress.md) 为准，不沿用历史翻译测试成绩。
