# 下一轮开发模板（需要用户明确启动）

> 2026-11-02 实现更新：R1–R4 已接入，R5 部分验收；Schema head 0010，产品入口 paper-reading-v1。P02_reading_extract/P12_reading_integration/P13_reading_selection 为独立运行模板，旧任务模板不改。默认分层图谱、全部候选搜索与显示偏好已可用，无人工审核。下一步限于 R5 全文质量/响应可靠性与安装反馈，未进入 P4/P5。当前正式库 275 条知识在隔离迁移中逐行保持。报告见 docs/reading-implementation-verification-20261102.md（相对仓库根）。

当前 R0 规范交付，软件仍在 P3/v3 自动建图迭代，未进入 P4/P5。阅读根 AGENTS、README、progress、最新开发日志及 00–09，按 [R1–R5 计划](06_development_migration_plan.md)推进。

下一步先做 R1：

1. 检查 git status/diff，保留所有既有未提交改动，审计知识/证据/依赖/模型/旧审核与来源结构。
2. 在独立备份制定加性 Alembic 迁移；复用旧知识 ID 与内容，仅增加必要质量、结论单元/成员、选择快照/显示偏好及阶段检查点。
3. 建立新旧 DTO、状态与版本适配；历史审核数据保留，新流程不出现人工审核或待审/接受/驳回。
4. 完成统一 Store 写入、引用/来源/路径闭合、幂等及选择发布版本约束；模型不能直接写数据库。
5. 旧库原列逐行比对，迁移后旧读取/任务/图谱仍可用，备份可恢复。参考 SQL 不能直接对正式库执行。
6. R1 完成并验证后再按授权范围接 R2/P02、R3/P12/P13、R4 分层 UI、R5 真实验收；不能直接把新版 Prompt 放进旧 pipeline。

真实论文、密钥、运行库和安装器不入源码；未经授权不 Push。使用 Conda researchgraph-studio，优先自动化和用户原生反馈。不要因存在 Query/Wiki 模板就进入下一 Phase。
