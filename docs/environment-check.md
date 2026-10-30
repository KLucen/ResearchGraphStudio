# 开发环境检查报告

初次检查时间：2026-10-27 12:43（Asia/Shanghai）；同日根据用户补充更新 Conda、Zotero 和 GitHub 状态。机器可读证据：[最新快照](environment/2026-10-27-conda.json)、[初次快照](environment/2026-10-27.json)。

最新结论（2026-10-30）：**Phase 1 的 PDF 导入、来源检查与同内容重新定位已通过本机和 Windows CI 构建/安装验收；G0 按用户决定放行。** 项目使用固定版本 PyMuPDF 1.26.7 与已有 Conda/依赖锁，本轮未新增依赖。首次来源验收遇到 Windows 短路径断言误判，复现修复后完整 CI 成功（32 项 Python / 12 项 React / 1 项 Rust 测试）。当前范围及剩余工作见 [Phase 1 记录](phase1-verification.md)和 [最新 CI 摘要](environment/2026-10-30-phase1-sources-ci.json)，历史见 [Phase 0 记录](phase0-verification.md)。干净机测试未补做。下文历史快照不代表当前缺少工具；模型与 Zotero 接入尚未执行。

## 2026-10-28 Phase 0 环境增量

- 项目 Conda Python 3.12.16；业务与工具依赖在 requirements-win-64.lock 锁定并按哈希安装，未安装到 base。Node 24.20.0 / pnpm 12.5.1。
- 官方 rustup 安装 Rust 1.99.1 x86_64-pc-windows-msvc，版本固定于 rust-toolchain.toml；脚本只向当前进程 PATH 加入 Cargo，不修改系统 PATH。
- 官方签名 Build Tools 安装器补齐 Visual Studio 2022 17.14.37824.6、MSVC 14.44.35207、Windows SDK 10.0.26100.0。昨日安装中断，今日恢复，vswhere 显示 isComplete=true、无需重启。实际 cargo clippy、test 和 release 编译通过。
- WebView2 155.0.4283.62 已有，本机原生窗口实际启动。中文源码路径构建成功；独立 Sidecar 已验证中文/空格数据目录和无开发环境 PATH。
- GitHub Release 常规 URL 下载 NSIS 超时；历史代理 7892 当前未监听。通过官方 GitHub API 取得 Release 资源并下载（续传一次），校验 API 公布的 SHA-256 后放入 Tauri 工具缓存；没有使用第三方镜像或修改全局 Git/网络配置。
- NSIS 3.13 ZIP SHA-256：BA63DFFC4410EE89193E1CB5A41989991BD77C61068DA17E3156D136B7B0B3D8；nsis_tauri_utils 0.5.3 DLL：5BA143B5DB4A87D32D6E7802E033330AAE56CBCEABE0D1E3BA41948385AD4709。
- 干净 Windows G0、缺失 WebView2 的安装、模型运行和正式升级均尚未验证。开发机成功不等同于发布验收。

## 项目与系统

| 项目 | 实测结果 | 对开发的影响 |
| --- | --- | --- |
| 项目目录 | `C:\Users\KLucen\Desktop\AI科研知识推理平台` | 检查时原为空；已写入准备文件，目录可写 |
| Git | `2.55.0.windows.5`；已初始化 `main` 并关联 `origin` | 远端为 `KLucen/ResearchGraphStudio`，核查时为空；本地尚无提交或推送 |
| 操作系统 | Windows 11 家庭版中文版，`10.0.26200` | Windows 为首个构建和安装验证目标 |
| PowerShell | `7.6.5` | 环境检查脚本已在此版本执行 |
| CPU | Intel Core i9-14900HX，24 核/32 线程 | 有条件运行解析与小规模评估任务；实际吞吐未测 |
| 内存 | 15.7 GiB | 先控制文献解析、嵌入与模型并发，监测峰值占用 |
| GPU | RTX 5060 Laptop，8151 MiB 显存；驱动 `617.42` | 仅确认设备与驱动可见；未验证 CUDA/PyTorch/模型兼容性 |
| 磁盘 | C: 剩余约 136.5 GiB；D: 约 196.9 GiB | 足够开始源码与小规模样本开发；大模型和文献库另定数据位置 |
| WSL | Ubuntu，WSL 2，检查时处于停止状态 | 已注册；本轮没有启动或检查 Linux 内部依赖 |

## 工具链

| 工具 | 结果 | 建议 |
| --- | --- | --- |
| Node.js | `v24.20.0` | 先沿用，M1 验证所选框架与原生模块兼容性 |
| npm | `11.19.0` | 可用 |
| pnpm | `12.5.1` | 建骨架时明确 packageManager 并保存锁文件；尚未验证 Tauri/Vite 依赖组合 |
| 默认 Python | Anaconda `3.14.6` | 保留；项目依赖不装入 base |
| Conda | `26.7.2`，来自 `C:\Users\KLucen\anaconda3` | 用户指定的首选 Python 环境管理器；base 保持独立 |
| 项目 Python | Conda 环境 `researchgraph-studio`，`3.12.16` | 已创建，解释器和标准库验证通过 |
| 项目基础依赖 | pip `26.2.2`，OpenSSL `3.5.9`，SQLite `3.53.4` | 实际导入、SQLite 查询、`pip check` 均通过；尚无业务框架 |
| uv | `0.12.19`，原有 Python 3.12.14 仍保留 | 可用但非项目默认工具，不再要求创建 uv 环境或 `.venv` |
| Docker / Podman | PATH 未发现；常见 Docker Desktop CLI 路径也未发现 | 不视为本地桌面候选路线的前置条件；不是完整安装清单结论 |
| PostgreSQL / Redis | PATH 未发现对应命令；未发现匹配 Windows 服务 | 如后续改为服务型架构，需单独准备与验证 |
| Rust / Cargo / CMake / cl | PATH 未发现 | Tauri 或原生扩展构建可能需要额外工具；`cl` 不在普通终端 PATH 不能证明未安装 Build Tools |
| VS Code | 发现 `code.cmd` | 可用编辑入口，未更改编辑器设置 |
| Obsidian | 在 `%LOCALAPPDATA%\Programs\Obsidian\Obsidian.exe` 找到程序 | 未打开或检查个人 Vault |
| Zotero | `D:\Zotero\zotero.exe`，产品版本 `10.0.6`；观察到 `127.0.0.1:23119` 监听 | 安装位置已核实；端口监听不等于本地 API 数据调用已通过，未查询个人文献库 |

项目 Python 实际路径：

```text
C:\Users\KLucen\anaconda3\envs\researchgraph-studio\python.exe
```

## 端口与网络

初次检查上述开发/服务端口均无监听；用户补充路径后的复查已观察到 23119 的回环监听，见最新快照。端口状态只代表检查时刻，启动时仍要检测冲突；桌面引擎建议动态选择回环端口。

| 请求 | 结果 |
| --- | --- |
| npm registry ping，HTTP HEAD | 200 |
| PyPI simple index，HTTP HEAD | 200 |
| GitHub 首页，HTTP HEAD | 200 |
| GitHub 仓库 API | `KLucen/ResearchGraphStudio` 可访问，公开仓库，默认分支配置为 `main`；分支列表为空 |
| Git HTTPS `ls-remote origin` | 连接超时；首页可达不代表 Git 传输可达 |
| Git 官方 SSH 443 `ls-remote` / `fetch origin` | 均退出码 0，无 refs；主机密钥严格校验开启，使用已有身份验证 |
| Conda 官方 main channel | 实际创建完成：20 个包，Python 3.12.16；非仅网络入口探测 |
| 用户提供的 ChatGPT 分享链接 | 网页读取超时；本机 GET 返回 403；原设计正文未取得 |

前三项保留初次 HTTP 入口结果。新增 Conda 安装与 Git 读取有独立验证记录；未测试 Tauri 安装构建、真实 Git 推送或模型 API。分享链接失败是历史记录，设计内容已由 QA.md 与后续四份材料补充。

`origin` 为 `https://github.com/KLucen/ResearchGraphStudio.git`。本轮保留 HTTPS 地址，SSH 443 通过单次 URL 覆盖访问同一官方仓库；可复用命令见[项目入口](../README.md)。未修改全局 Git、代理或 Conda channel 配置。

## Conda 环境管理

用户已明确优先使用 Anaconda，并允许创建独立环境。本轮实际创建命令为：

```powershell
conda create --name researchgraph-studio --override-channels --channel https://repo.anaconda.com/pkgs/main --strict-channel-priority python=3.12 pip --yes
conda run -n researchgraph-studio python --version
conda run -n researchgraph-studio python -m pip check
```

初次环境文件含 `nodefaults`，当前 Conda 26.7.2 在实际解析中将其视为 channel 并返回 404。已移除该项，实际创建使用显式官方源和 `--override-channels`，没有改动全局配置或关闭 TLS 校验。

[环境规格](../environment.yml)保存直接依赖意图；[Windows 精确锁文件](../conda-win-64.lock)包含 20 个包及 SHA-256，可用 `conda create -n researchgraph-studio --file .\conda-win-64.lock` 在新机器重建。锁文件由本机已安装环境导出，未声称已在第二台机器完成重建。以后加入 pip-only 包时需单独维护其锁定记录。

## 下一步环境工作

1. 按 QA 的 Tauri 路线确认/补齐 Rust MSVC、C++ Build Tools/Windows SDK；在 `researchgraph-studio` 中增加最小业务依赖，建立 Tauri/React 工程与锁文件。
2. 安装最小依赖，验证中文目录下构建；出现真实兼容问题再选择版本或工具替代方案。
3. 做 Python 引擎打包与桌面启动探针，验证依赖收集、进程退出和数据库写入位置。
4. 使用干净 Windows 测试环境验证安装包，不以开发机成功代替最终用户验证。
5. 选择模型方式和实验样本后再测内存、GPU 和推理性能；Zotero 安装位置已确认，接入阶段验证 API 能力及文献来源映射。

## QA 对齐后的 Tauri 前置检查

2026-10-27 只读检查见[专项记录](environment/2026-10-27-tauri.json)。本轮未安装构建工具或改变系统配置。

| 项目 | 结果 | 后续动作 |
| --- | --- | --- |
| Rust/rustup/cargo | PATH 未发现；常见 `.cargo/bin/rustup.exe`、`cargo.exe` 不存在 | 新计划 Phase 0 准备 MSVC 目标工具链并记录精确版本 |
| C++ Build Tools/SDK | 常见 Visual Studio Installer 路径中未发现 vswhere | 尚不能确认可用，进一步检查或安装 C++ 桌面开发组件后实际编译验证 |
| WebView2 | 注册表检测到 Runtime 155.0.4283.62 | 骨架阶段实际启动窗口；安装包另测试缺失 Runtime 的目标机 |

[Tauri 官方前置说明](https://v2.tauri.app/start/prerequisites/)要求 Windows 的 C++ Build Tools、WebView2 和 Rust/MSVC。Python 环境就绪不能替代这些条件。[安装文档](https://v2.tauri.app/distribute/windows-installer/)区分联网与离线 WebView2 分发，首轮打包须明确选择并验证。

## 复查命令

```powershell
Set-Location -LiteralPath 'C:\Users\KLucen\Desktop\AI科研知识推理平台'
pwsh -File .\scripts\check-environment.ps1
# 需要网络检查和保存快照时，给出新的日期文件名：
pwsh -File .\scripts\check-environment.ps1 -CheckNetwork -OutputPath .\docs\environment\YYYY-MM-DD.json
```

脚本检查命令版本、系统资源、指定端口和常见路径；不安装依赖、不启动 WSL、不修改系统配置。指定 `OutputPath` 会写入或更新该报告文件，历史快照应使用不同文件名。
