# Tauri 桌面工作台

桌面工作台提供项目、文献与阅读、图谱与比较、独立笔记来源和全局设置。React 调用受限 Tauri IPC，Rust 持有会话令牌并管理 Python Sidecar。生产页面不直接请求任意 HTTP 地址，也没有通用 shell/文件权限。

从仓库根目录运行 `pwsh -File scripts/dev.ps1`；生产安装构建为 `pwsh -File scripts/build-windows.ps1`。在本目录单独执行 pnpm dev 只启动 Web UI，不具备原生宿主能力。

当前实现与限制见[进度](../../docs/progress.md)及[稳定性验收](../../docs/stability-verification-20261102.md)，后续工作遵循 [v3 迁移计划](../../docs/06_development_migration_plan.md)，不自动进入 Query/Wiki Phase。

单元测试运行 `pnpm test`。真实 React Flow 的浏览器回归运行 `pnpm test:browser`，使用已安装的 Microsoft Edge（headless），独立 Vite 1427 端口及合成图，不连接用户数据库或正式后端；未安装 Edge 的环境需先提供对应 Playwright 浏览器。fixture 不进入生产构建。原生安装与交互结果由用户按验收报告反馈。
