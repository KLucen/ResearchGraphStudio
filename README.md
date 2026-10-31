# ResearchGraph Studio

AI 辅助科研桌面工作台：实验条件约束的证据推理、人工知识审核与增量知识演化。

当前进入 **Phase 1 来源与证据开发**，已加入 PDF 引用/托管导入、附件修订、页码原文块查看、来源检查和同内容文件重新定位；任务可取消/重试，并显示实际阶段、稳定项目任务历史和启动时临时工作区回收统计。当前 API Schema 为 0004，RG-006 已通过 [Windows 构建与安装 CI](docs/environment/2026-10-31-phase1-jobs-ci.json)；修复后的原生窗口分页复测、M1 安装版证据定位和干净环境验收仍待完成。采用 Tauri 2 + React/TypeScript、Python/FastAPI Sidecar、SQLite/FTS5。G0 于 2026-10-29 按用户决定放行；未补造干净机实测结果。当前范围和剩余工作见 [Phase 1 记录](docs/phase1-verification.md)，历史安装结果见 [Phase 0 记录](docs/phase0-verification.md)。AI、图谱和人工知识审核尚未实现。

开发目录：`C:\Users\KLucen\Desktop\AI科研知识推理平台`。开发远端：[KLucen/ResearchGraphStudio](https://github.com/KLucen/ResearchGraphStudio)，本地 origin 已关联。

## 开发与构建

Windows x64 需要 Node 24.20.0、pnpm 12.5.1、Rust（见 rust-toolchain.toml）、Visual Studio C++ Build Tools/Windows SDK 和 WebView2。Python 优先使用 Anaconda 的独立环境 `researchgraph-studio`，不向 base 安装依赖。

```powershell
# 在项目根目录；创建环境只需执行一次
conda create --name researchgraph-studio --file .\conda-win-64.lock
conda run -n researchgraph-studio python -m pip install --require-hashes -r requirements-win-64.lock
pnpm install --frozen-lockfile

# 静态检查、契约生成、测试及前端构建
pwsh -File .\scripts\check-phase0.ps1

# 构建 Sidecar 并启动原生开发窗口
pwsh -File .\scripts\dev.ps1

# 打包 Windows 当前用户 NSIS 安装器
pwsh -File .\scripts\build-windows.ps1
```

脚本自动定位指定 Conda 环境；Conda 未加入当前 shell 时可设置 `$env:RGS_PYTHON='C:\Users\KLucen\anaconda3\envs\researchgraph-studio\python.exe'`。根目录 `pnpm dev` 启动 Tauri，但要求已构建 Sidecar；`pnpm --dir apps/desktop dev` 只启动 Web UI。修改 Python 后重新运行开发脚本以重建引擎。

安装器输出在 `apps/desktop/src-tauri/target/release/bundle/nsis/`。随包携带 Python 解释器；当前 WebView2 缺失时需要联网安装。默认用户数据在 `%LOCALAPPDATA%\com.researchgraph.studio`，精确路径可在设置页查看。运行数据库、日志和个人材料不进入源码。

`environment.yml` 表达 Conda + pip 依赖意图；`conda-win-64.lock` 锁定基础解释器，`requirements-win-64.lock` 锁定 Python 包及哈希，`pnpm-lock.yaml`、Cargo.lock 和 rust-toolchain.toml 锁定前端与 Rust。优先用上面的两步方式复现 Python 环境。

## 设计与过程记录

- [完整开发计划 v0.4](docs/development-plan-v0.4.md)与[开发流程入口](docs/development-plan.md)
- [需求基线](docs/design/requirements-baseline.md)、[原文 QA](QA.md)、[补充材料登记](docs/design/source-register.md)
- [领域模型](docs/design/domain-model.md)、[Tauri 决策](docs/decisions/0002-tauri-evidence-workbench.md)、[工具/Wiki 决策](docs/decisions/0003-controlled-knowledge-evolution.md)、[来源检查决策](docs/decisions/0005-source-check-relocation.md)、[任务历史与临时工作区决策](docs/decisions/0006-job-history-workspace-recovery.md)
- [已实现 API](docs/api.md)、[Phase 0 验证与待验收项](docs/phase0-verification.md)、[环境报告](docs/environment-check.md)
- [开发日志](DEVELOPMENT_LOG.md)、[实验计划](experiments/README.md)

v0.1 先完成至少 5 篇论文的 PDF → 证据/主张/条件 → 关系推理 → 人工审核 → 图谱 → 保存/报告闭环。v1.0 增加 Zotero 只读入口、授权笔记回流、受控 Wiki、增量演化和系统化实验；工期与效果指标均为目标。

Zotero 安装程序为 `D:\Zotero\zotero.exe`，此目录不代表文献数据目录。Zotero 管原文题录，ResearchGraph 管证据/审核/知识版本，Obsidian 管个人笔记及授权 Wiki。MCP 不是前置依赖。

Git HTTPS 不通时，可使用已验证的官方 SSH 443 通道，保持 origin 和全局配置不变：

```powershell
git -c 'url.ssh://git@ssh.github.com:443/.insteadOf=https://github.com/' -c 'core.sshCommand=ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10' fetch origin
```

按用户 2026-10-28 的授权，每轮开发通过相关检查、记录日志后自动提交并普通推送到 `origin/main`。不强制覆盖远端；若 CI 失败，继续修复并推送。CI 在 Windows 构建后，使用另一个 runner 安装产物并运行无需开发工具的 PowerShell 验收；只修改 Markdown/docs 时由本地文档检查把关，不重复构建。
