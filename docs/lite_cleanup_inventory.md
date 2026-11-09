# ResearchGraph Lite 工程清理盘点

更新：2026-11-09（Asia/Shanghai）

本文记录 ResearchGraph Lite 清理前的目录、模块和数据分类。完整 v3/P4/P5 工程已保存在 `backup/pre-lite-refactor`（提交 `7b45f0d`），因此本轮可以从 Lite 目标重新整理活跃工作区。该分支的未提交 Lite P0 修改在清理前先保存为本地提交；本文件不包含私人论文、原始模型响应、数据库内容或密钥。

## 目录分类

| 分类 | 路径 | 处理 |
| --- | --- | --- |
| 保留 | `apps/desktop`, `services/engine/researchgraph`, `packages/contracts`, `scripts` | Tauri、React、FastAPI、SQLite/FTS5、Zotero、PDF/章节解析、Provider、用量、任务和安全工具 |
| 保留并精简 | `apps/desktop/src/ForceGraph.tsx`, `forceSimulation.ts`, `graphLayout.ts`, `graphAppearance.tsx` | 复用 React Flow/布局能力，改用 Lite 概览图 DTO |
| 保留 | `tests/fixtures/pdf`, 环境锁定文件、Cargo/PNPM 锁定文件、`.github/workflows` | 可分发测试样本、可复现构建和安全检查 |
| 保留 | `docs/researchgraph_lite_ABD`, `docs/ResearchGraph_Lite_LightGraph_Addendum`, `README.md`, `docs/README.md`, `docs/progress.md` | Lite 设计规范、当前说明和实际进度 |
| 归档到备份分支 | `docs/archive`, 历史 ADR/设计/报告、旧 Prompt/Schema/契约测试 | 旧工程仍可回退，活跃目录不再作为 Lite 运行说明 |
| 清理 | `.local`, `target`, `node_modules`, `dist/build`, Python/Rust/前端缓存 | 安装包、数据库、WAL/SHM、日志、实验响应和构建输出；均未被 Git 跟踪 |
| 清理 | 项目内字面目录 `%SystemDrive%` | 仅包含生成缓存，使用绝对路径删除，避免展开为系统盘变量 |
| 退役 | `query_*`, `p5_*`, `lint_*`, `wiki_*`, `external_document*`, `reasoning*`, `translation*`, 旧 `reading_*` 和完整 GraphRAG 页面/契约 | Lite 默认不再提供跨论文推理、Lint/Wiki 自动任务或完整抽取入口；旧版本由备份分支保留 |

## 运行边界

保留的 Lite 主链是：选择项目 → Zotero/PDF 来源 → 本地 PDF 解析 → 跨页章节和文本块 → FTS5 索引 → 可选的 PaperCard + LightGraph 概览。选择和索引阶段必须保持 0 次模型调用。主动生成概览使用 `PAPER_OVERVIEW_WITH_LIGHT_GRAPH_V1` 单次调用；缓存命中不产生新调用。

Lite 活跃数据只包含来源、解析、章节/文本索引、任务、模型配置、用量/缓存、PaperCard/LightGraph 结果和布局。旧图谱、跨论文 Query、Lint/Wiki、旧任务记录和旧抽取结果不迁移到新的 Lite 数据库。旧数据库只在备份分支和用户明确指定的历史目录中保留。

## 依赖解耦清单

清理前已核对以下耦合：

- `app.py` 的旧抽取、Query、P5、Lint、Wiki、推理和外部文档路由已从 Lite 入口移除；worker 不再空闲执行 Lint 维护。
- `ingest.py`、`document_structure.py` 和 Zotero 适配器只保留来源、解析和 FTS 写入，不再调用完整 KnowledgeStore/GraphRAG 抽取。
- `lite_usage.py` 使用独立 Lite 用量/缓存表，不能把旧 Query/P5/知识模型行摊给 Lite 论文。
- `Job.resume_adapter_available` 和旧 Provider Mock 不再导入 reading/Query/P5 协议。
- Tauri 白名单和前端路由只保留项目、论文、来源、任务、设置、Lite 用量、概览和布局接口。

## 删除前验证

清理前扫描结果：根目录 `node_modules` 约 6.1 GiB，Tauri `target` 约 5.1 GiB，`.local` 约 4.2 GiB；SQLite/WAL/SHM、安装包、日志和历史 PDF 均未被 Git 跟踪。Gitleaks 历史扫描覆盖 28 个提交，无泄露结果。项目外的 Zotero 数据、私人 PDF、批注、密钥和正式数据库不在本轮清理范围。

## 清理后验收

清理后必须通过：Python/前端/Rust 静态检查；新 Lite 数据库初始化；创建 Lite 项目；Zotero 连接或匿名适配器；PDF 导入、章节解析、FTS5 查询；选择论文和索引阶段 0 次模型调用；应用启动/停止/重启。未通过的旧 GraphRAG、P5、Lint/Wiki 兼容测试不再作为 Lite 验收项。
