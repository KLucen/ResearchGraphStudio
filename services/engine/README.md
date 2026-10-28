# 本地研究引擎

Phase 0 的 researchgraph 包实现 FastAPI 鉴权、项目和诊断 Job、SQLite 单写入者、Alembic 迁移与事务事件。API 和启动协议见[接口文档](../../docs/api.md)。数据库只由引擎访问。

开发使用 Anaconda 环境 researchgraph-studio（Python 3.12），从仓库根目录执行 `pwsh -File scripts/check-phase0.ps1`。`scripts/build-engine.ps1` 使用 PyInstaller onedir 打包解释器和依赖；安装运行不调用用户的 Conda。

当前为最小结构，后续模块随业务增长再拆分 api/core/providers 等目录，不预建空实现。PDF、模型、证据审核、Wiki 均尚未实现；必须遵守[领域模型](../../docs/design/domain-model.md)的证据、归属、审核和恢复规则。
