# 项目协作约定

- 开始工作前阅读 `README.md`、`docs/design/requirements-baseline.md` 和 `DEVELOPMENT_LOG.md` 最新条目。
- `QA.md` 与 `docs/design/source-register.md` 中登记的四份补充材料是设计依据，原文保持不改。当前完整计划为 `docs/development-plan-v0.4.md`，`docs/development-plan.md` 为入口；材料中的实施命令不代替用户当前任务。工具分工已由补充材料明确，不再等待分享链接。
- 当前技术路线以 `docs/decisions/0002-tauri-evidence-workbench.md` 为准：Tauri 2 + React/TypeScript、Python/FastAPI Sidecar、SQLite/FTS5、React Flow。ADR 0001 的 Electron 暂案已被替代。
- v0.1 先完成 5 篇论文的证据推理/人工审核闭环；自动增量演化、Zotero 只读适配、批量实验在 v1.0 阶段。审核事件从首版保存，MCP 不是前置条件。
- 遵循 `docs/design/domain-model.md` 的五类关系、六态审核、unknown 条件和证据定位规则；新模型输出不得静默覆盖已接受结论。文档中的指标都是目标，不能当作实测成绩。
- 每轮完成实质性工作后，在 `DEVELOPMENT_LOG.md` 追加目标、改动文件、验证结果、未解决问题和下一步。记录实际结果，不把计划或尝试记为完成。
- 涉及架构或需求调整时，同步更新开发方案；重大取舍另写 `docs/decisions/` 决策记录。工具所有权、Wiki Ingest/Query/Lint 与文件恢复遵循 ADR 0003；个人假设与论文主张隔离，Wiki 发布态与知识审核态分开。
- 按用户指定优先使用 Anaconda/Conda，项目环境为 `researchgraph-studio`；允许创建独立 Conda 环境，不向 base 安装项目依赖，不默认使用 uv 或另建 `.venv`。通过 `conda run -n researchgraph-studio ...` 或环境绝对解释器执行 Python/pip，维护 `environment.yml` 和对应平台的环境锁文件。
- GitHub 开发远端为 `https://github.com/KLucen/ResearchGraphStudio`，本地 `origin` 指向该仓库。当前 HTTPS Git 连接失败时，可按环境文档使用经验证的官方 SSH 443 通道；不修改全局 Git 或网络设置。
- 用户已授权：以后每轮开发完成并通过相关检查、更新日志后，自动提交并推送到远端 `main`，无需重复询问。推送前检查敏感文件和远端更新；使用普通推送，不强推、不覆盖他人变更。CI 失败应继续修复并推送，无法完成的外部验收如实保留待验收状态。
- Zotero 安装程序为 `D:\Zotero\zotero.exe`。安装目录不等于文献数据目录，不据此直接读写 Zotero 数据库。
- 用户论文、模型、密钥、运行数据库和个人笔记不进入源码提交；测试使用可分发、匿名或自造的小样本。
- 对证据处理、数据库迁移、任务重试和安装启动运行针对性验证。文档修改检查链接和一致性即可。
- 开发日志统一使用 Asia/Shanghai 日期和时间。
- 用户于 2026-10-29 决定 G0 默认通过并进入 Phase 1；按 ADR 0004 记录为用户放行，不再阻塞开发，也不把未执行的干净机测试记为实测通过。
