# ADR 0031：ResearchGraph Lite P0 本地阅读基础

- 日期：2026-11-09
- 状态：P0 已实现；数据策略已由用户后续清理要求和 ADR0032更新
- 原始 P0 快照：29e4495

## P0 决策

ResearchGraph 转向 Lite A+B+D。选择 Zotero 论文或本地 PDF 后只进行本地解析、章节识别与 FTS5 索引，默认不调用模型。用量与论文/章节缓存建立独立基础，Provider usage、估算、未知及费用未知必须区分；缓存命中不产生新模型调用或 Token。

原始 P0 采用 0021/0022 加性迁移和 legacy 可访问策略。用户随后要求全面清理并建立新空 Lite 数据库；当前活跃工程改用 lite0001、researchgraph-lite.sqlite3，不迁移旧业务数据，旧系统只通过 backup/pre-lite-refactor 回退。当前决策见 [ADR0032](0032-lite-clean-engine-and-paper-overview.md)。

## 验收口径

P0 的核心条件是匿名 PDF/Zotero 本地处理、章节/FTS5、任务重启和零模型调用通过。旧正式数据库和真实 Zotero 库没有作为实验对象；原 P0 的旧数据兼容测试属于29e4495的历史验证，不能表述为清理后的 Lite 仍能打开旧图谱。

## 后续范围

P1 联合实现 B 的 PaperCard + LightGraph，一次调用且无 Evidence 节点；A 章节导读和 D 证据问答仍待后续阶段。unknown只表示信息/计量缺口，不能补造条件或推断未知费用为零。
