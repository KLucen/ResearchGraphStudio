# 图谱、Schema 失败恢复与文献工作区验收

日期：2026-11-02（Asia/Shanghai）。承接 DEV-0026，修复用户实际反馈，不进入下一 Phase。所有私人输出、数据库备份和安装包只在 `.local/`；没有 Commit/Push。

## 实际原因与实现

- **图谱闪动/消失**：受控节点重建时未携带测量尺寸，React Flow 将节点暂时隐藏并重新测量。真实渲染测试在旧实现拖动期间检测到 visibility:hidden；显式稳定点尺寸后通过持续悬停、逐帧可见性、连续/快速拖动、邻居响应、固定/解除、缩放和容器变化检查。边标签不截获指针，非有限坐标拒绝进入模拟。
- **第二篇 Schema 错误**：合法 JSON，11 items、8 links，某条关系引用了不存在的 local_ref。文献版本与本任务匹配，未发现两篇任务混写。新版报告精确路径，新增一次受限端点修复；保留原始结果、修复记录、来源验证和幂等边界。详见 [ADR 0006](../../adr/0006-graph-stability-and-local-reference-repair.md)。
- **文献工作区**：导入论文（同级 PDF/Zotero）、任务记录（阶段/批次/错误/继续/分页）、项目文献（列表/知识/证据/模型记录）均可折叠并按项目记忆。Obsidian 私人笔记进入独立“笔记来源”，不属于论文导入。折叠不卸载内容，不丢失当前选择。

## 真实响应复核

- 对已存在的一致性备份再复制至 `.local/stability-20261102/real-repair/`；不对正式数据库排队或写入。
- 复用第二篇失败批次的原始响应，经已配置真实模型进行 **1 次**引用修复，之后通过 Schema、证据校验与 KnowledgeStore，产生 14 个领域节点标识。原有 **183 条知识**不变，原始错误响应完整保留；SQLite integrity/foreign_key 检查通过。
- 实际供应商用量：prompt_tokens 1621、completion_tokens 104、total_tokens **1725**；reasoning_tokens 62 已包含在 completion 中。供应商未返回费用，不能记为零。
- 只验证该失败批次，未重新执行剩余 15 批。私人诊断和复核结果位于 `.local/stability-20261102/`，不写进源码。

## 回归与交付

| 命令 / 场景 | 实际结果 |
| --- | --- |
| `pwsh -NoProfile -File scripts/check-phase0.ps1`（Anaconda researchgraph-studio） | 最终完整通过：139 Python passed / 2 skipped，37 React；Ruff/format、mypy 48 模块、pip check、契约导出、TS/eslint、前端格式和构建通过 |
| `pnpm --dir apps/desktop test:browser` | 2 passed；安装在本机的 Edge headless，真实 React Flow + 合成图，无用户桌面控制 |
| `python -m pytest docs/tests -q` / 独立进程 `docs/archive/v2/tests` | 12 passed / 5 passed |
| 真实失败响应副本复核 | 1 次真实调用成功；183 个旧节点全列逐行相同，旧任务 signature 与当前代码精确匹配 |
| `pwsh -NoProfile -File scripts/build-windows.ps1` | PyInstaller Sidecar + Tauri release + NSIS 成功，新修复 Prompt 已包含在资源中 |
| `python scripts/smoke-engine.py --executable apps/desktop/src-tauri/binaries/researchgraph-engine-x86_64-pc-windows-msvc.exe` | 通过：隔离数据、P0–P3 路径、抽取/审核/来源/图谱/布局/重启、stdin EOF 退出；测试 Provider，不冒充真实模型验收 |
| PowerShell 5.1 `scripts/verify-windows-install.ps1 -EnginePath ...` | passed；System32-only 子进程 PATH、独立数据目录；不是安装器执行验收 |
| `python scripts/check-sensitive.py --gitleaks .local/tools/gitleaks-8.30.1/gitleaks.exe` | 候选源码内容及路径检查通过；暂存区为空 |
| 文档链接、QA hash、环境 JSON、设计资产 SHA-256 / `git diff --check` | 通过；四份不可用外部原文明确排除 |

首次全量运行发现非法 JSON/证据失败不能重抽的兼容回归，已将 invalid 缓存限制为局部引用错误并完整重跑通过。新文献页测试的按钮选择器错误也已修正。没有把失败运行记为通过。

安装器：`.local/releases/stability-20261102/ResearchGraph Studio_0.0.1_x64-setup.exe`，**38,442,557 bytes**，SHA-256 `9BD990ED8B434E27A151C1F668282B6929181928F6CB1B713905D603D1569B62`。开发版本仍为 0.0.1；本轮未替换用户安装版。完整命令日志位于 `.local/stability-20261102/`。

两项 symlink 权限测试跳过、Starlette/httpx 弃用与前端单 chunk 大于 500 KiB 提示保留。Rust 源码本轮未改，未重复单跑其测试；Tauri release 编译通过。

## 用户原生验收步骤

1. 退出正在运行的 ResearchGraph Studio，安装本轮安装包后重新打开现有项目；无需卸载或删除数据目录。
2. 图谱节点上停留 5 秒，拖动一个节点并快速松开；确认节点及邻居持续可见。再检查缩放、双击固定和重启后位置。
3. 在“文献与阅读”展开/收起三个板块，切换 PDF/Zotero；确认导入入口并列、选择不丢失，笔记只在“笔记来源”。
4. 在失败的第二篇任务上点击“继续未完成批次”。确认旧错误响应经过引用修复后继续；在论文的“模型调用与原始结果”查看独立修复运行及来源。该操作会调用真实模型完成剩余批次并产生供应商费用。
5. 如仍失败，请反馈批次编号和错误文字；不发送密钥。原生结果在用户反馈后登记。

## 未验收和限制

本轮遵循用户要求不频繁使用 Computer Use。Windows 安装执行、原生交互、第二篇全文完成及科学内容正确性待用户反馈；headless 浏览器和单批真实修复不替代这些项目。干净 Windows/WebView2 缺失场景与远端 CI 未测。四份外部补充原文登记路径仍不可用，历史来源登记与 QA 原件保持。没有新增 Phase 功能。
