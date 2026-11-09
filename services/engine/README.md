# 本地 Lite 研究引擎

researchgraph 包实现 FastAPI 鉴权、Lite 项目/任务、SQLite 单写入者、空库迁移、Zotero 读取、PDF/章节解析、FTS5 索引、Provider 配置、Token 用量和 PaperCard + LightGraph 概览。

开发使用 Anaconda 环境 `researchgraph-studio`（Python 3.12），从仓库根目录执行 `pwsh -File scripts/check-phase0.ps1`。`scripts/build-engine.ps1` 使用 PyInstaller onedir 打包解释器和依赖；安装运行不调用用户的 Conda。

Lite 数据库文件为 `researchgraph-lite.sqlite3`，只接受 `lite0001` 初始 Schema；检测到旧数据库时停止并提示使用新的 Lite 数据目录。完整图谱、跨论文推理、Lint/Wiki 和旧 Query 不在活跃服务中。
