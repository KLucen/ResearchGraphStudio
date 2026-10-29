# Phase 0 交付与验证

更新时间：2026-10-29（Asia/Shanghai）。产品探针版本 0.0.1。完整范围以[计划 v0.4](development-plan-v0.4.md)为准。

**流程状态：用户于 2026-10-29 明确决定 G0 默认通过，已放行 Phase 1。** 依据 [ADR 0004](decisions/0004-g0-waiver-phase1.md)。下文“未执行”描述真实测试覆盖，不再作为阻塞开发的关卡。

## 当前实现

- 项目空态、创建、列表、搜索已加载项目、分页、项目详情和运行设置页。
- Tauri 私有令牌/回环 HTTP 桥接、版本握手、单实例、引擎重启与退出管理。
- SQLite 项目/任务/事件/幂等存储、Alembic 初始迁移、迁移前备份和失败回滚。
- 实际存储诊断任务、取消、最多三次执行、重启中断恢复。
- PyInstaller onedir 引擎，NSIS 当前用户安装配置，Windows CI 工作流。

本阶段没有 PDF 导入、模型调用、关系推理、图谱审核、Zotero 或 Wiki 发布。界面没有用演示论文或模型响应冒充功能。

## 验证记录

| 检查 | 当前结果 |
| --- | --- |
| Python 引擎测试 | 11 个通过；覆盖鉴权、输入、并发幂等、持久化、分页、任务、单写锁、失败迁移 |
| React 测试 | 3 个通过；创建、失败重试幂等、离线禁用 |
| Python/TypeScript 静态检查、生产 Web 构建 | 锁定依赖安装后全套通过；UI 断连提示修复后再次通过相关检查 |
| Rust fmt / clippy / test | 通过，1 个路径白名单测试通过，release 编译成功 |
| 打包引擎独立进程 | 已通过：中文/空格临时路径、无开发工具 PATH、鉴权、创建/重放、诊断、退出/重启读回 |
| 安装包、原生窗口操作 | NSIS 构建成功；本机静默安装退出 0，中文/空格安装路径成功，移除开发工具 PATH 后原生窗口连接成功并读回项目 |
| 故障与生命周期 | 重复启动只有一个实例；引擎异常终止后 UI 报错并可重连；强制终止宿主后子引擎在 15 秒等待窗口内退出；正常关闭后无残留进程 |
| 本机卸载/重装 | 静默卸载退出 0，程序移除、数据库保留；最终安装包重装退出 0，原项目仍可读回 |
| 干净 Windows G0 | 用户决定放行；独立干净机实测未执行，后续发布补测 |
| GitHub Actions | [运行 40809339440](https://github.com/KLucen/ResearchGraphStudio/actions/runs/40809339440) 全部通过，代码提交 8df4e1e；构建与独立 runner 安装验证均成功 |
| 独立 runner 安装生命周期 | Windows Server 2022 / PowerShell 5.1：安装、鉴权、诊断、幂等/重启读回、EOF 退出、桌面 Sidecar、单实例、正常/崩溃退出及卸载后保留数据全部通过 |

本机 Windows 11 已有开发环境及 WebView2。移除子进程 PATH 中的 Python/Node/Conda 能验证随包解释器，但不能证明一台没有系统运行库的电脑也可安装。不得据此关闭 G0。

测试使用自造项目“Phase 0 安装验证”，未读取个人文献或笔记。引擎异常后曾观察到设置页保留缓存的 FTS5 可用提示，已修正为等待检查；该修复不改变引擎、数据库或 IPC 契约。Starlette TestClient 有一条 httpx 弃用提示，测试仍通过，后续随框架兼容升级处理。

## 任务状态

| 任务 | 状态与剩余工作 |
| --- | --- |
| RG-001 构建环境与锁定 | 已实现；本机及 GitHub windows-2022 runner 按锁文件重建、检查和构建通过 |
| RG-002 桌面最小界面 | 已实现并通过真实窗口操作 |
| RG-003 Sidecar 与 Job | 已实现；鉴权/版本/任务/重连/退出已验证 |
| RG-004 存储与契约 | 已实现；幂等/并发/持久化/失败迁移备份已验证 |
| RG-005 安装与 CI | 本机及 CI 已通过；G0 按用户决定放行，未测环境项目保留 |

## 复现命令

在项目根目录运行，Python 必须来自 researchgraph-studio Conda 环境：

```powershell
pwsh -File scripts/check-phase0.ps1
pwsh -File scripts/build-engine.ps1
conda run -n researchgraph-studio python scripts/smoke-engine.py --executable apps/desktop/src-tauri/binaries/researchgraph-engine-x86_64-pc-windows-msvc.exe
cargo fmt --manifest-path apps/desktop/src-tauri/Cargo.toml --check
cargo clippy --manifest-path apps/desktop/src-tauri/Cargo.toml --locked --all-targets -- -D warnings
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --locked
pwsh -File scripts/build-windows.ps1
```

构建输出：`apps/desktop/src-tauri/target/release/bundle/nsis/`。默认安装仅当前用户，安装器没有代码签名。若目标机缺少 WebView2，当前配置联网下载其官方 bootstrapper，不能视为完全离线安装包。

2026-10-29 CI 验收安装器：`ResearchGraph Studio_0.0.1_x64-setup.exe`，23,976,140 字节；SHA-256：`9EC242A883044079E02DFDEF5BF3E25D730EC93C7E1146AA9CFD4B0FF4B4E437`。从上方 Actions 运行的 `researchgraph-phase0-windows` artifact 下载。本机 `.local/phase0-acceptance-kit.zip` 包含该安装器、修复后的脚本和使用说明，未提交二进制到源码仓库。

完整通过结果见 [CI 摘要](environment/2026-10-29-phase0-ci.json)和[安装验收原始报告](environment/2026-10-29-phase0-installed.json)。下载后的两个 artifact ZIP 均按 GitHub 公布的 SHA-256 校验，安装器再次匹配验收报告中的哈希。

本机日常查看用的 `.local/安装验证 ResearchGraph` 仍保留 2026-10-28 安装的应用及自造项目，未覆盖更新；对应旧安装器 SHA-256 为 `E36DB25CA2614643956C07C759EEAF00E339D852114ACDBD83D894669A4E5C59`，历史验证见[机器可读记录](environment/2026-10-28-phase0.json)。

## G0 待执行清单

首次 CI 运行 40686890045 的构建成功，安装后引擎就绪检查失败。2026-10-29 修复验收脚本的管道编码：Windows PowerShell 5.1 在 UTF-8 控制台下会在创建 stdin writer 时输出 BOM，导致引擎无法解析启动 JSON。本机使用同一 CI 安装产物复现，修复后在 UTF-8 和默认控制台编码下均通过，另验证调用方编码恢复（[回归记录](environment/2026-10-29-phase0-encoding.json)）。脚本只在创建管道期间设置无 BOM UTF-8 并恢复编码；失败报告包含退出码和 stderr，CI 同时保留 engine-stderr.txt。应用协议、数据库和用户安装均未改动。修复后的完整 CI 已通过。

2026-10-28 20:17 新增 `scripts/verify-windows-install.ps1`，兼容 Windows 自带 PowerShell 5.1。只复制安装器和该脚本即可在独立机器运行，脚本不调用 Python/Node/Conda；子进程 PATH 限为 System32。已有安装、运行窗口或用户数据时拒绝桌面安装测试，避免影响日常工作区。以下 ExecutionPolicy 仅对当前测试进程生效，不修改系统策略：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\verify-windows-install.ps1 -Installer '.\ResearchGraph Studio_0.0.1_x64-setup.exe' -VerifyDesktop -OutputRoot 'C:\rgs-acceptance-001'
```

OutputRoot 必须是新目录，报告保存为 verification.json。脚本检查安装、鉴权、中文/空格路径、项目幂等/持久化、诊断、EOF 退出；`-VerifyDesktop` 再检查原生宿主启动 Sidecar、单实例、正常/异常退出和卸载后数据保留。脚本不自动认证整套 G0：UI 人工操作、独立机器无开发环境及缺 WebView2 安装仍需记录。CI 的第二个 windows-2022 runner 与构建工作区隔离，但系统预装工具，不能等同干净 Windows。

本机已有安装，因此本轮只使用 `-EnginePath` 模式做 PowerShell 5.1 验证（[实际通过记录](environment/2026-10-28-phase0-powershell.json)），不覆盖已安装应用。另以已有安装做拒绝测试，确认脚本在启动安装器前停止并记录失败。完整安装模式交由新 CI runner 执行。本机 Windows 11 Home / CoreCountrySpecific 25H2，没有 WindowsSandbox.exe，也未发现现成 VM 控制工具；本轮未安装或启用虚拟化组件。

在独立 Windows 10/11 x64 虚拟机或测试机（没有 Python/Node/Conda/Rust）记录系统版本、安装器 SHA-256 和 WebView2 初始状态：

1. 普通用户安装到含空格/中文的目录；缺 WebView2 时确认 bootstrapper 安装路径。
2. 启动、创建自造中文项目、执行存储诊断；退出后确认无引擎残留。
3. 重启读回项目；第二次启动聚焦已有窗口；异常终止宿主后确认子进程退出。
4. 断网后再次打开和创建项目；验证未调用云端模型。
5. 卸载后检查程序文件移除、用户数据保留规则；重装读回。正式升级、备份恢复和代码签名另按发布阶段验证。

G0 已按用户决定放行，Phase 1 正式开始；上述未测项不改写成实测通过，后续发布时补齐。
