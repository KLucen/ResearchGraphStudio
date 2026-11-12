# 本地 Lite 研究引擎

researchgraph 实现 FastAPI 鉴权、Lite 项目/任务、SQLite 单写入者、Zotero 读取、PDF/章节解析、FTS5 索引、Provider 配置、统一用量、PaperCard + LightGraph、章节导读、证据问答与可选英文关键词辅助。选择论文、PDF 解析及索引均为本地处理，不调用模型。

开发使用 Conda 环境 `researchgraph-studio`。主 Sidecar 使用 PyInstaller onedir 打包；用户运行不依赖 Conda，不向 base 安装项目依赖。安装包不再携带翻译 Server、PDFMathTranslate/BabelDOC 运行时或其离线资源。

Lite 数据库为 `researchgraph-lite.sqlite3`，Alembic head 保持 `lite0008`。既有迁移及翻译表结构仅用于已有数据库兼容；本次撤下功能不降级或重建数据库，不删除论文、成果、布局、历史翻译行、用量、任务快照和生成文件。旧完整系统数据库仍与 Lite 库隔离，完整抽取、跨论文推理、Lint/Wiki 不属于活跃服务。

文献翻译已于 2026-11-12 按用户要求撤下，活跃引擎不再注册翻译路由，也不执行翻译 worker、模型代理或外部/随包运行时。旧任务不自动恢复，不允许通过通用重试重放；未完成任务停止为已取消，已有终态及 usage 保留，不将未知用量补成零。

撤下边界见 [ADR0040](../../docs/adr/0040-remove-pdf-translation.md) 与 [文献翻译撤下说明](../../docs/pdf-translation.md)。本轮测试、模型用量、构建和安装验证的实际结果以 [进度](../../docs/progress.md) 为准，不沿用历史翻译测试成绩。
