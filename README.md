# ResearchGraph Studio

AI 辅助科研桌面工作台：实验条件约束的证据推理、人工知识审核与增量知识演化。

当前完成 **Graph-Centric v2 P1 兼容补全与 P2 最小知识闭环**：继承 PDF 引用/托管导入、来源版本、任务恢复与稳定分页；增加只读 Zotero 批注、授权 Markdown 快照、论文结构、证据锚点、结构化抽取、知识卡片和人工审核历史。统一 KnowledgeStore 校验来源并写入 SQLite，API Schema 为 0005。离线 Mock 已用于流程验收；真实模型科学质量、真实 Zotero 批注和干净 Windows 仍待外部验收。实际结果见[实施进度](docs/progress.md)与[迁移评估](docs/migration/v1_to_v2_assessment.md)。

技术栈继续使用 Tauri 2 + React/TypeScript、Python/FastAPI Sidecar、SQLite/FTS5；未重做 P0，未进入 P3 跨论文推理。G0 保留用户放行记录，不等同于干净机实测。历史结果见 [Phase 1](docs/phase1-verification.md)和 [Phase 0](docs/phase0-verification.md)。

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

## 论文阅读与抽取

打开项目，通过原生选择器导入 PDF，展开“论文结构与知识”。默认 Mock 只摘录原文以验证流程；点击知识卡片回查证据与 PDF 块高亮。修改内容后填写理由并保存修订，再接受或驳回当前版本。来源验证与人工审核分开；作者主张和人工接受均不等于已证明的科学事实。缺失条件保留 unknown。

真实模型使用兼容 OpenAI Chat Completions 的文本接口，在启动桌面程序的环境中配置 `RGS_MODEL_BASE_URL`（例如本地服务的 `http://127.0.0.1:8000/v1`）、`RGS_MODEL_NAME` 和可选 `RGS_MODEL_API_KEY`。远端必须 HTTPS；不跟随重定向，不使用系统代理。随后在阅读区选择“已配置模型”并明确同意发送当前论文片段。密钥不写数据库、日志或 Git；私人笔记不进入抽取输入。每次调用保存模型、Prompt 哈希、输入哈希、参数、原始结果和状态。失败/取消可在任务历史重试；已成功的 P02 批次复用，失败批次不写知识。

Zotero 仅使用本机 Local API 读取条目、附件位置与高亮/文字批注，不读写 Zotero SQLite。PDF 仍需原生选择器授权，关联批注前校验路径和 SHA-256；无法唯一匹配的批注显示“锚点未解析”。“只读来源接入”可授权笔记目录并扫描 Markdown，保存来源、哈希和版本快照，不修改原笔记，不实现 Wiki 发布。

0005 是加性迁移，启动升级前自动备份旧库。原 Paper/附件修订/文本块及 API 保留；原文使用 identity-v1 字符映射，黄色只表示解析块范围。暂不包含 OCR、精确逐字定位、跨页单一 span、完整章节语义、关系推理和 Wiki。

## 设计与过程记录

- [产品设计 v2](docs/01_product_design.md)、[开发计划 v2](docs/02_development_plan.md)、[知识契约与 Prompt](docs/03_knowledge_schema_and_prompts.md)
- [迁移评估](docs/migration/v1_to_v2_assessment.md)、[统一引擎 ADR](docs/adr/0001-unified-knowledge-engine.md)、[实际进度](docs/progress.md)；[旧开发计划 v0.4](docs/development-plan-v0.4.md)仅保留历史
- [需求基线](docs/design/requirements-baseline.md)、[原文 QA](QA.md)、[补充材料登记](docs/design/source-register.md)
- [领域模型](docs/design/domain-model.md)、[Tauri 决策](docs/decisions/0002-tauri-evidence-workbench.md)、[工具/Wiki 决策](docs/decisions/0003-controlled-knowledge-evolution.md)、[来源检查决策](docs/decisions/0005-source-check-relocation.md)、[任务历史与临时工作区决策](docs/decisions/0006-job-history-workspace-recovery.md)
- [已实现 API](docs/api.md)、[Phase 0 验证与待验收项](docs/phase0-verification.md)、[环境报告](docs/environment-check.md)
- [开发日志](DEVELOPMENT_LOG.md)、[实验计划](experiments/README.md)

新版后续 P3 入口为跨论文条件化推理与图谱探索；Query、Lint、Wiki、增量演化按后续阶段推进，本轮停止于 P2。设计 v2 不代表软件发布版本已达到 2.0，工期与效果指标均为目标。

Zotero 安装程序为 `D:\Zotero\zotero.exe`，此目录不代表文献数据目录。Zotero 管原文题录，ResearchGraph 管证据/审核/知识版本，Obsidian 管个人笔记及授权 Wiki。MCP 不是前置依赖。

Git HTTPS 不通时，可使用已验证的官方 SSH 443 通道，保持 origin 和全局配置不变：

```powershell
git -c 'url.ssh://git@ssh.github.com:443/.insteadOf=https://github.com/' -c 'core.sshCommand=ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10' fetch origin
```

按用户 2026-10-28 的授权，每轮开发通过相关检查、记录日志后自动提交并普通推送到 `origin/main`。不强制覆盖远端；若 CI 失败，继续修复并推送。CI 在 Windows 构建后，使用另一个 runner 安装产物并运行无需开发工具的 PowerShell 验收；只修改 Markdown/docs 时由本地文档检查把关，不重复构建。
