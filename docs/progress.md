# ResearchGraph Lite 进度

更新：2026-11-09 21:35（Asia/Shanghai）。

## 当前状态

本地工作区已完成 Lite 工程清理、Lite P0 和 B（PaperCard + LightGraph）联合概览基础实现。完整旧工程可从 `backup/pre-lite-refactor` 回退；清理提交 `e3354b2` 已通过 `679f480` 合并到本地 `main`，文档边界修订为 `f9b53cc`，未推送远端。

| 能力 | 实际状态 |
| --- | --- |
| Tauri 2 + React/TypeScript + FastAPI + SQLite/FTS5 | 保留并已精简，静态检查通过 |
| Zotero 连接、论文选择、PDF/章节解析、文本索引 | 已实现；选择和本地解析阶段 0 次模型调用 |
| Lite 模式、空库 `lite0001`、用量与缓存基础 | P0 已实现并通过专项与重启验证 |
| PaperCard + LightGraph | P1 联合抽取、缓存、任务、布局 API 与交互已实现；由一次模型调用生成 |
| 图谱交互 | 已支持节点拖动、缩放、点击详情、关系详情、布局/相机持久化和重置 |
| A 章节导读 | 尚未开发 |
| D 证据问答 | 尚未开发 |
| 完整图谱抽取、跨论文推理、Lint/Wiki | 已从活跃 Lite 工程移除；历史工程只保留在备份分支 |

## 清理结果

已完成全项目分类和清理：删除旧安装包、构建输出、数据库/WAL/SHM、日志、实验响应、Python/Node/Rust 缓存、旧 v2/v3 文档归档、旧 Prompt/Schema、完整图谱/Query/Lint/Wiki/Reading/Reasoning 业务代码、旧迁移和对应测试。根目录旧选题说明 `QA.md` 也已移除；必要的 Lite 规范、当前基线、迁移评估、安全说明和匿名 PDF fixture 保留。

活跃工程只保留本地阅读基础、Zotero、PDF/章节/FTS5、Provider/模型配置、任务、用量/缓存和可复用 React Flow 图组件。运行代码和契约中没有指向已删除旧业务的路由或导入；历史完整实现仍可从备份分支恢复。

## Lite 数据边界

新数据库使用 `researchgraph-lite.sqlite3` 和独立初始 Schema `lite0001`，只创建 Lite 表与本地 FTS5 索引，不迁移旧图谱、Query、Lint、Wiki、任务记录、缓存或抽取结果。检测到旧数据库结构时会停止并提示使用新的 Lite 数据目录。旧数据库不会被覆盖或删除。

选择 Zotero 论文或导入本地 PDF 后，解析、章节识别、文本块保存和 FTS5 建索引均在本机完成；不会自动排队 PaperCard、A、D 或任何完整知识图谱任务。生成概览必须由用户明确允许一次模型调用；PaperCard 和 LightGraph 共用同一请求，缓存命中不产生新调用。`unknown` 只表示信息或计量缺口，不据此补造实验条件、推断矛盾或把未知费用写成零。

## 验证结果

- 后端：最终 `pytest -q` 为 **143 passed / 1 skipped / 1 既有 warning**；Ruff、mypy、compileall 和依赖检查通过。
- 前端：TypeScript、ESLint、Prettier、Vitest（5 个文件、30 个测试）和生产构建通过；真实浏览器 LightGraph 测试 2 项通过。
- Rust/Tauri：`cargo test` 为 **7 passed / 1 ignored**，格式检查通过；源引擎和打包引擎 Lite smoke 均通过。白名单已覆盖项目、论文、Zotero、PDF、用量、概览和布局接口。
- Lite 专项：匿名 PDF 两份、章节结构、Chunk/EvidenceSpan、FTS5 正文检索、重启读取和 Provider 哨兵均通过；解析阶段实际调用数、输入 Token、输出 Token、总 Token、重试和增量费用均为 0。
- 本轮未读取正式用户数据库、Zotero 正式库、私人 PDF/批注或真实 API Key，未调用真实 Provider，未执行安装器安装验收。提交前使用项目外的 Gitleaks 8.24.3（官方发布压缩包 SHA-256 已核对）扫描暂存内容和工作区源码；最终再次扫描当前工作区及 **32 个 Git 历史提交**，均通过，同时完成路径规则和 `git diff --cached --check`。

## 下一步

本轮清理、提交、合并和合并后 Lite 专项回归已完成。下一阶段进入 Lite P2 的 A 章节导读设计与实现；D 证据问答另行排期。真实 Provider Token/费用、复杂表格/公式、OCR、跨平台和用户原生安装体验仍需独立验收。
