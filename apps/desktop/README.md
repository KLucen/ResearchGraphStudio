# Tauri 桌面工作台

桌面工作台提供项目、文献与阅读、图谱与比较、问答、Lint/Wiki、独立笔记来源和全局设置。React 调用受限 Tauri IPC，Rust 持有会话令牌并管理 Python Sidecar。生产页面不直接请求任意 HTTP 地址，也没有通用 shell/文件权限。

从仓库根目录运行 `pwsh -File scripts/dev.ps1`；生产安装构建为 `pwsh -File scripts/build-windows.ps1`。在本目录单独执行 pnpm dev 只启动 Web UI，不具备原生宿主能力。

当前已接入 Query 与 P5 Lint/Wiki，数据库 head 为 `0020`。Lint分别展示总数待定的准备、按对象推进和末批依赖重建；对象数达到总数时仍须按实际阶段等待完成，恢复活动报告只读刷新，显式继续才推进。阶段耗时按秒显示，推进请求按次显示，旧报告没有记录时保留“未记录”。实际验证与未完成退出项见[进度](../../docs/progress.md)、[Lint 性能与进度报告](../../docs/p5-lint-performance-verification-20261107.md)、[P5 报告](../../docs/p5-verification-20261105.md)和[扫描反馈修复](../../docs/p5-scan-feedback-verification-20261105.md)；开发要求见[实施计划](../../docs/06_development_migration_plan.md)。

单元测试运行 `pnpm test`。真实 React Flow 的浏览器回归运行 `pnpm test:browser`，使用已安装的 Microsoft Edge（headless），独立 Vite 1427 端口及合成图，不连接用户数据库或正式后端；未安装 Edge 的环境需先提供对应 Playwright 浏览器。fixture 不进入生产构建。原生安装与交互结果由用户按验收报告反馈。
