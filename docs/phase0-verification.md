# Phase 0 交付与验证

更新时间：2026-10-28（Asia/Shanghai）。产品探针版本 0.0.1。完整范围以[计划 v0.4](development-plan-v0.4.md)为准。

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
| 干净 Windows G0 | 未执行，仍为发布关卡 |
| GitHub Actions | main 首次推送 d1a39fa 已触发运行；远端依赖、业务测试、契约和打包引擎已通过，安装构建进行中，最终结果见后续验收记录 |

本机 Windows 11 已有开发环境及 WebView2。移除子进程 PATH 中的 Python/Node/Conda 能验证随包解释器，但不能证明一台没有系统运行库的电脑也可安装。不得据此关闭 G0。

测试使用自造项目“Phase 0 安装验证”，未读取个人文献或笔记。引擎异常后曾观察到设置页保留缓存的 FTS5 可用提示，已修正为等待检查；该修复不改变引擎、数据库或 IPC 契约。Starlette TestClient 有一条 httpx 弃用提示，测试仍通过，后续随框架兼容升级处理。

## 任务状态

| 任务 | 状态与剩余工作 |
| --- | --- |
| RG-001 构建环境与锁定 | 已实现并在本机编译验证；第二台机器重建未验证 |
| RG-002 桌面最小界面 | 已实现并通过真实窗口操作 |
| RG-003 Sidecar 与 Job | 已实现；鉴权/版本/任务/重连/退出已验证 |
| RG-004 存储与契约 | 已实现；幂等/并发/持久化/失败迁移备份已验证 |
| RG-005 安装与 CI | 安装器和 CI 工作流已实现；本机安装通过，干净 Windows G0 与远端 CI 待执行 |

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

本次最终安装器：`ResearchGraph Studio_0.0.1_x64-setup.exe`，约 22.89 MiB；SHA-256：`E36DB25CA2614643956C07C759EEAF00E339D852114ACDBD83D894669A4E5C59`。本机测试安装目录为项目下 `.local/安装验证 ResearchGraph`，安装的应用及自造项目保留供查看。复核摘要见[机器可读记录](environment/2026-10-28-phase0.json)。

## G0 待执行清单

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

G0 通过前 RG-005 保持“待独立环境验收”。后续可准备 Phase 1 fixtures 与来源模型，但不能宣称已通过最终用户安装门槛。
