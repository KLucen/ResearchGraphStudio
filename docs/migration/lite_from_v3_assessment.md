# ResearchGraph Lite 工程映射与清理结果

更新：2026-11-12（Asia/Shanghai）。

## 决策顺序与回退点

完整工程基线见 [current_project_baseline.md](../current_project_baseline.md)。先完成总结和安全检查，再将完整旧工程保存并推送为 backup/pre-lite-refactor，提交 7b45f0d；随后建立 refactor/researchgraph-lite-p0，本地 P0 快照为 29e4495。

用户后续明确要求清理旧业务及应用生成数据，并以新 Lite Schema 建立空数据库。因此早期独立空库方案覆盖原 Lite 设计包的旧业务可访问/增量迁移要求；旧完整系统通过备份分支回退，活跃 Lite 工程不提供旧 Query/Lint/Wiki/完整图谱入口。该清理阶段的提交与后续上传记录以 [实际进度](../progress.md) 为准；其空库初始化决定不适用于此后已有 Lite 用户数据的功能撤下。

## 模块映射

| 模块 | Lite 处理与当前状态 |
| --- | --- |
| Tauri 2/Rust 宿主 | 保留 Sidecar 生命周期、会话鉴权、受限 IPC、文件选择和健康握手；只放行现有 Lite 路由及参数 |
| React/TypeScript | 精简为研究项目、文献阅读、任务、设置与用量；移除旧业务页面与 API 客户端 |
| Zotero | 保留只读 Local API 连接、分类/附件选择、任务去重和导入；不直接操作 Zotero SQLite |
| PDF/来源 | 保留 PyMuPDF 子进程、版本/hash、文本块、跨页章节、原文定位及可恢复表格 |
| FTS5 | local_index.py 直接索引解析文本，支持论文/版本/章节范围检索；不依赖知识图谱 |
| Provider/设置 | 保留协议、能力、凭据引用、输出 Schema 和受控网络；本地解析不创建模型任务 |
| 用量/缓存 | 独立 Lite 账本记录每次请求/失败/缓存命中，未知 usage 或费用保持未知 |
| 图谱组件 | 复用 ForceGraph、forceSimulation、graphLayout 和 graphAppearance，以 Lite 概览 DTO 展示 |
| 完整旧知识业务 | 移除旧抽取、Query、Lint/Wiki、Reading/Reasoning、旧迁移和对应测试/Prompt/Schema |
| 文献翻译 | 2026-11-12 撤下界面、API、执行器和随包运行时；仅保留历史迁移及数据兼容，不删除已有译文、记录或用量 |
| 文档和产物 | 保留 Lite 规范、基线、当前说明、安全/构建脚本和匿名 fixture；旧报告/归档/安装包/运行数据清理 |

完整盘点和删除边界见 [lite_cleanup_inventory.md](../lite_cleanup_inventory.md)。

## 数据库与数据边界

Lite 文件名为 researchgraph-lite.sqlite3。设计包的 `lite0001` 是空基线；Alembic head 保持 `lite0008`，保留既有迁移链和翻译表结构以兼容已经使用的 Lite 数据库。2026-11-12 按用户要求撤下翻译能力，不执行数据库 downgrade、重新初始化或历史数据迁移；论文、章节、阅读成果、布局、历史翻译行、任务快照、用量与生成文件继续保留。翻译界面、业务 API、执行器和随包资源从活跃工程移除，旧任务不自动续发或重试。保留表结构不表示仍可运行翻译。完整旧系统的业务数据仍不迁移。详见 [ADR0040](../adr/0040-remove-pdf-translation.md)。

旧 0001–0022 迁移不再属于活跃 Lite 迁移链。程序不打开或升级旧 researchgraph.sqlite3；在 Lite 路径遇到旧结构时拒绝启动迁移。旧数据库、私人论文、Zotero 正式库和项目目录以外的用户文件未被处理。回退时须使用备份分支与用户保存的旧数据，Git 分支本身不包含私人数据。

## 当前工作流

1. 创建 Lite 项目并选择 Zotero 附件或本地 PDF。
2. 本地 PDF 子进程解析，保存版本/hash、章节、文本块和结构材料。
3. 同一导入事务建立 FTS5 索引；论文、章节和检索可立即使用。
4. 用户主动允许模型后生成一次联合论文概览，得到 PaperCard + LightGraph。
5. 程序校验结构、端点和数量上限，生成稳定节点/边 ID，记录用量与版本化缓存。
6. 图谱拖动/缩放/固定只更新独立布局和相机；缓存命中无新增模型请求，失败不自动重发。
7. 用户选定单一小节并显式选择 `quick`、`standard` 或 `deep` 后生成 A01 章节导读；结果按论文、文献版本、章节和深度缓存，源版本变化标记 `STALE`，模型只能引用本次允许的 Span，并支持复制导读。
8. 论文问答先对用户选定的 section/paper/selection 范围进行本地检索，再由用户明确生成 D01 回答；本地无命中时可单独授权 D02 关键词辅助，返回关键词后重新检索，不自动生成回答。

A 章节导读 A01 已实现：用户显式选择单节后可按 quick/standard/deep 生成，使用版本化缓存、STALE 识别、证据 Span 白名单和复制展示；GET、章节切换和本地解析不会调用模型。D01 局部证据问答已实现：默认 section、可选 paper/selection、FTS5 Top-K Span、显式授权、引用白名单、证据不足结果、缓存及失败/取消/重启记录；D02 关键词辅助已实现：服务端确认本地无命中后，用户明确授权才发送标题/章节标题/问题，返回 1–5 个关键词并重新执行本地检索。本轮没有真实模型质量、单篇论文真实 Token/费用或通用节省比例结论。

## 验证与剩余

当前实际结果以 [progress.md](../progress.md) 和 [开发日志](../../DEVELOPMENT_LOG.md) 为准；29e4495 中的 1208 后端/169 前端等属于清理前 P0 验证，不能当成本轮干净工程重跑成绩。新的测试范围验证 Lite 存活能力，不再要求退役完整知识业务通过。

仍需独立验收真实 Zotero 库、真实 Provider 的联合概览科学质量/usage、复杂表格/公式、扫描 PDF/OCR、跨平台、干净机和用户原生安装。未经实际测试不把这些项目标为通过。
