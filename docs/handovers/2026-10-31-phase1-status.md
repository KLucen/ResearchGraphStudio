# ResearchGraph Studio 阶段总结与开发交接

核对时间：2026-10-31 19:46（Asia/Shanghai）。本次按用户要求整理现状与下一次开发入口，不继续扩展功能；保留现有未提交改动。

## 项目位置与约定

- 本地：`C:\Users\KLucen\Desktop\AI科研知识推理平台`。
- 远端：[KLucen/ResearchGraphStudio](https://github.com/KLucen/ResearchGraphStudio)，当前分支 main。
- Tauri 2 + React/TypeScript、Python/FastAPI Sidecar、SQLite/FTS5；React Flow 在后续图谱阶段接入。
- Python 使用 Anaconda 的 researchgraph-studio 环境；解释器 `C:\Users\KLucen\anaconda3\envs\researchgraph-studio\python.exe`，不向 base 安装，不另建 uv/.venv。
- 用户已授权每轮完成检查、更新日志后自动普通提交并推送 main，跟进 CI；不强推、不覆盖他人变更。
- G0 按用户 2026-10-29 决定放行，未执行的干净机/WebView2 场景不能写成实测通过。Zotero、私人论文库、个人笔记及模型服务尚未接入。

## 已推送并验收的基线

本次已核对远端 main 与本地 HEAD 均为 `a642d66de1f6bc17f1ceda3f596a69f16875720a`。这是上一轮来源检查验收文档提交；对应通过 CI 的代码提交为 `4410ef380633a603ec3b221f439259a4b879894b`。

已具备可安装桌面壳、引擎鉴权/生命周期、项目持久化、迁移备份、任务取消/重试，以及 PDF 引用/托管导入、内容去重、附件修订、页码原文块、来源可用性检查和同内容重新定位。历史原文不会因来源移动或变化被覆盖。

[CI 41024830613](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41024830613) 已完成且成功：32 项 Python、12 项 React、1 项 Rust 测试，以及 Windows 构建和另一 runner 的独立安装验收。此前 Windows 短路径导致 smoke 断言误判的问题已修复并复验。见 [Phase 1 记录](../phase1-verification.md)及 [CI 摘要](../environment/2026-10-30-phase1-sources-ci.json)。

已有本机验收包 `.local/phase1-sources-acceptance-kit.zip` 对应这份已验收代码，**不包含下述未提交的新功能**。

## 本机已实现、尚未交付的增量

2026-10-30 开发的以下改动仍在工作区，尚未提交或推送。核对时有 21 份已跟踪文件改动及 6 份新增源码/测试文件；本交接文档和日志不计入该数字。

| 功能 | 本机实现 |
| --- | --- |
| 临时文件回收 | workspaces.py：UUID 归属标记、子进程独占锁、启动回收、非递归白名单删除；活跃进程、未知内容、目录链接保留；权限失败可下次重试，清理失败不推翻已成功任务 |
| 任务阶段进度 | 迁移 0004 增加 Job.stage；显示启动、读取、解析、检查、保存等实际阶段，不估算百分比；重试清空旧阶段 |
| 项目任务分页 | 以创建时间和 UUID 为固定顺序，返回 items/next_cursor；同时间戳、新插入、旧任务重试及跨项目游标有测试 |
| 桌面界面 | 新 JobHistory 组件逐页加载和刷新，旧任务可重试；离线保留缓存并禁用操作；设置页显示启动回收统计 |
| 契约与宿主 | OpenAPI/TypeScript 已重新生成；Rust 白名单现支持 1–512 位 Base64URL 不透明游标；宿主/引擎/验收脚本期望 Schema 0004 |
| 分发验证 | smoke-engine.py 增加引擎强制终止后的暂存目录回收、历史分页和文件保留验证；PowerShell 验收增加对应重启检查 |

核心新增文件：

- [workspaces.py](../../services/engine/researchgraph/workspaces.py)
- [0004_job_progress.py](../../services/engine/researchgraph/migrations/versions/0004_job_progress.py)
- [JobHistory.tsx](../../apps/desktop/src/JobHistory.tsx)
- [test_workspaces.py](../../tests/engine/test_workspaces.py)、[test_job_history.py](../../tests/engine/test_job_history.py)、[JobHistory.test.tsx](../../apps/desktop/src/JobHistory.test.tsx)

回收仅涉及应用临时任务目录。托管附件、历史修订、原始 PDF、数据库、备份不在清理范围。旧版无归属标记的临时目录保留；零字节锁文件保留稳定身份，不把这种行为写成“清空所有缓存”。没有新增依赖。

## 已执行的本机验证

以下是 2026-10-31 复核后的实际结果：

- 45 项 Python 测试通过、1 项平台能力跳过，保留一条既有 Starlette/httpx 弃用提示；ruff、格式、mypy、pip check 通过。
- 16 项 React 测试、TypeScript、ESLint、Prettier、契约生成和生产 Web 构建通过。
- Rust fmt、clippy、1 项路由白名单测试通过，新增覆盖 Base64URL 游标的边界。
- 新打包引擎 smoke 通过任务分页/阶段、强制退出后的暂存文件回收、来源/托管附件保留、原文和来源重启持久化。
- Windows PowerShell 5.1 的引擎模式验收通过分页/阶段、临时文件回收及重启。它不是本轮新安装器的远端安装验收。

本机证据路径（被 Git 忽略）：`.local/phase1-jobs-check.log`、`.local/phase1-jobs-build.log`、`.local/phase1-jobs-smoke.log`、`.local/phase1-jobs-ps51/verification.json`。

此前独立原生数据已记录旧库升级、取消/重试、回收统计和原文重启读回；本轮发现旧桌面桥接错误地拒绝 Base64URL 任务游标并已修复。修复后的原生窗口复测在 Computer Use 阶段被用户按 Escape 停止，因此分页复测仍待执行。当前未发现 ResearchGraph 宿主或引擎残留进程。

交接文档与开发日志的 23 个本地链接、Markdown 结构及 git diff --check 通过。全仓库文档检查遇到新环境限制：source-register 中登记在桌面的四份补充材料当前均不在原路径，无法复核它们的链接和哈希。没有修改或重新生成原文；后续先依据仓库内既有需求基线与设计记录推进，原文核验恢复时再确认实际存放位置。

## 下一次开发的完成条件

1. 阅读 AGENTS.md、README、需求基线、本交接和开发日志；查看 git diff，基于现有未提交改动继续，保留已有代码与测试。
2. 复核临时回收的边界、子进程锁/迟启动竞争、权限失败、阶段更新和分页契约；有新修改时运行相关测试，必要时重建引擎。
3. 完成原生窗口验证。使用独立测试标识 `com.researchgraph.studio.phase1test` 和自造样本，验证旧 Schema 升级、超过一页任务的加载/重试、设置页回收统计和原文仍可查看；不迁移现有正式安装的数据来做实验。
4. 已新增 `docs/decisions/0006-job-history-workspace-recovery.md`并同步 README、`docs/api.md`、开发计划入口/v0.4 和 Phase 1 记录；当前要复核修复后的桌面分页桥接与远端安装 CI，不能把引擎分页测试单独当作原生窗口通过。
5. 将本轮实际报告写入 docs/environment，更新 DEVELOPMENT_LOG.md，检查链接、可用原材料哈希、敏感文件及远端更新；四份原文路径缺失须如实记录，不能写成已复核。不要提交 `.local`、运行数据库、二进制或私人物料。
6. 完成普通提交/推送 main，等待并修复 Windows CI；下载核对新安装器和报告，建立单独的新验收包，补记最终结果再推送文档。新 CI 尚未触发，不能沿用上一轮绿色结果证明本轮通过。

当前增量收尾后，下一功能阶段是 RG-007：Evidence/span 对象、跨页引用、归一化映射、原页面高亮和人工校正版本。真实 PDF 质量样本与 M1 安装版证据定位验收仍待完成；AI 抽取、主张/关系审核、图谱、Zotero/Obsidian 集成均未实现，不宣称整个 Phase 1 已结束。
