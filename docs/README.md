# 文档导航

更新：2026-11-12（Asia/Shanghai）。活跃文档维护 ResearchGraph Lite 的产品规范、运行边界、迁移评估、清理盘点、进度和安全说明。当前保留 PaperCard + LightGraph、A01 章节导读、D01 局部证据问答、D02 英文关键词辅助和全局模型连接配置。按用户要求撤下文献翻译界面、业务 API 和运行时；保留阅读工作区置顶、论文信息默认折叠的布局。Alembic head 继续为 `lite0008`，仅保留历史迁移与数据兼容，不再表示提供翻译功能。完整 v3/P4/P5 文档已从活跃目录清理，旧工程仍可从 `backup/pre-lite-refactor` 回退。

## 先读

- [根 README](../README.md)
- [Lite A+B+D 规范](researchgraph_lite_ABD/README.md)
- [LightGraph 补充规范](ResearchGraph_Lite_LightGraph_Addendum/README_ADDENDUM.md)
- [当前项目基线](current_project_baseline.md)
- [Lite 迁移评估](migration/lite_from_v3_assessment.md)
- [清理盘点](lite_cleanup_inventory.md)
- [实际进度](progress.md)
- [模型配置](model-configuration.md)
- [撤下文献翻译的决策](adr/0040-remove-pdf-translation.md)
- [文献翻译撤下说明](pdf-translation.md)
- [安全检查](security-checks.md)
- [Lite P0 决策](adr/0031-researchgraph-lite-p0.md)
- [Lite 清理与联合论文概览决策](adr/0032-lite-clean-engine-and-paper-overview.md)

翻译实现的演进历史保留在 [ADR0036](adr/0036-optional-pdf-translation-bridge.md)、[ADR0037](adr/0037-managed-translation-server.md)、[ADR0038](adr/0038-bundled-translation-and-reading-layout.md) 和 [ADR0039](adr/0039-translation-proxy-request-policy.md)。其翻译相关决策已由 ADR0040 覆盖，不作为当前配置或运行指南；ADR0038 的阅读布局继续保留。

## 文档规则

Lite 文档只描述当前活跃工程和可复现实验。历史完整图谱、跨论文 Query、Lint/Wiki、旧安装包、数据库、日志和原始模型响应不进入活跃目录。真实模型调用、价格和科学质量必须按实际账本记录；没有可用实验条件时继续保留 `unknown`。

设计 Schema、Prompt 和契约测试以 `docs/researchgraph_lite_ABD` 与 `docs/ResearchGraph_Lite_LightGraph_Addendum` 为准。`docs/researchgraph_lite_ABD/schemas/sqlite_reference.sql` 之类参考文件不直接执行，运行数据库由代码初始化和版本检查负责。
