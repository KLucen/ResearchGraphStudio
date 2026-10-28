# Tauri 桌面工作台

Phase 0 实现项目列表/创建/详情与设置诊断页。React 调用受限 Tauri IPC，Rust 持有会话令牌并管理 Python Sidecar。生产页面不直接请求任意 HTTP 地址，也没有通用 shell/文件权限。

从仓库根目录运行 `pwsh -File scripts/dev.ps1`；生产安装构建为 `pwsh -File scripts/build-windows.ps1`。在本目录单独执行 pnpm dev 只启动 Web UI，不具备原生宿主能力。

后续 PDF/证据查看、条件比较、审核、React Flow 图谱、Wiki 等按[计划](../../docs/development-plan-v0.4.md)逐阶段接通。已执行检查与 G0 限制见[验证记录](../../docs/phase0-verification.md)。
