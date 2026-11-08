# ADR 0030：Lint 批量读取、依赖闭包与阶段进度

日期：2026-11-07（Asia/Shanghai）。状态：已实现；实际性能、回归和包的验证分别见 [本轮验证报告](../p5-lint-performance-verification-20261107.md)。延续 [ADR0029](0029-lint-wiki-workflows-and-managed-publication.md) 的科学与权限边界。

## 背景

用户要求优化依赖索引重建、反向影响查询、批量读取、数据库索引和阶段耗时，并分别展示扫描准备、推进、末批依赖重建的状态。此前每批完整 catalog 重验创建大量 ORM 对象，节点检查逐个加载证据与依赖；重建逐对象查询并构造 ORM 边，依赖查询则先加载整个项目的边。末批在同一事务内重建，界面只能看到上一批已提交状态。

## 决策

1. 保持完整输入终验。catalog 对 Chunk 和 KnowledgeNode 使用流式列投影，对来源记录、节点证据/依赖、单元成员批量读取；保留原参与 hash 的字段、排序与嵌套形状。每次 advance 及依赖重建仍读取当前来源、授权和文件观察，不建立跨调用缓存，不从画布或分页抽样。
2. 节点检查按当前批次预取节点、证据关联、依赖端点、文献版本、EvidenceSpan、Chunk 和 Section，保留本调用的强引用供原校验器读取。每条证据仍执行完整 `validate_evidence`，依赖端点与条件状态仍逐项校验；返回或异常时清空本批映射与引用，不复用上一调用的验证结论。
3. 依赖重建使用分块列读取和 Core executemany 插入，保留边的稳定 ID、角色、类别、expected 和 state，以及逐引用的当前来源终验。删除旧边、写新边、更新 cursor 和审计仍在同一事务内。增量对账继续沿旧/新边并集传播，防止删除一条边后丢失影响。
4. 正反向影响查询使用 SQLite 递归 CTE 的 `UNION` 去重闭包，支持循环及重复支撑路径，没有固定深度或节点上限。以已到达对象为外层，通过现有 `ix_dependency_reverse` / `ix_dependency_forward` 完整键探测；EXPLAIN 验证实际计划。先完成闭包，再按本次可见性终验、统计和分页，隐藏中间对象不能泄漏，也不能剪断合法公共后继。查询仅投影所需列，不实例化全项目依赖 ORM。
5. 新加性迁移 `0020` 为 LintRun 增加 `phase`、`timings`，并增加 `paper_sources(revision_id)`、`reading_members(node_id)`、`reading_units(root_claim_id, document_version_id)` 三个索引。旧活动报告默认 scanning，旧终态为 finished，旧耗时为 `{}`；不伪造历史计时。迁移沿用升级前 SQLite 备份，不改旧科学列值、targets/input_hash、operation 响应、原 raw 或 GraphRevision。
6. `phase` 为 scanning、rebuilding_dependencies、finished。准备请求尚未返回时由桌面显示“准备范围”，总数未定不显示虚假百分比。首次全范围扫描的最后一批对象完成后，先提交仍 active 的 rebuilding_dependencies；下一次 advance 重新验源后才重建并结束。对象 100% 与整轮完成分开。该阶段可重启续接、取消；来源变化则 input_stale。无重建需求和规则异常 partial 维持原结束语义。
7. 桌面与后台续接幂等 key 包含 phase 和 processed，防止最后对象批和重建批共用序号而循环命中旧操作。只读 GET 不推进、不重建、不记新耗时；终态/进度/阶段均防迟到响应回退。旧响应缺新字段仍可读取，旧耗时显示“未记录”。API 默认 25、上限 100，桌面批次 100 保持。
8. `timings` 使用单调时钟，累计 `prepare_seconds`、`validate_seconds`、`check_seconds`、`dependency_rebuild_seconds`、`finalize_seconds`；`elapsed_seconds` 为已记录阶段之和，`last_advance_seconds` 为最近实际推进调用耗时，`advance_calls` 计非重放的活动推进次数。计时不含等待用户继续、网络往返或事务提交后的时间，不是端到端 SLA；失败回滚不伪装成功计时。计时和 phase 不进入 P09/P10/P11 的冻结科学快照、wire/hash 或稳定问题指纹。
9. 提供固定规模离线脚本：10,000 候选、20,000 块、2 Wiki、30,011 目标、每批 100；保留多数候选共用一合法 span、19,999 独立新增 raw chunks 的分布。比较同字节 harness 和冻结前后运行源，记录每批 wall/SQL/phase、各阶段耗时、完整正反向闭包、单块影响、OS RSS/进程峰值。使用全新合成库，拒绝既有输出目录，不调用真实模型、不打开正式库。

## 不变的语义与验证边界

`CONDITION_UNKNOWN` 保持 info，表示信息缺口；保留 unknown，不推断矛盾或补造条件。处理方案仍为只读派生展示。普通 Lint 与依赖索引不推进科学图修订，不写论文或私人文件，不重发模型，不继承已结束的模型预算。

性能基准、协议回归、冻结包和用户原生反馈分别记录。新迁移的隔离测试不能冒充用户数据库升级反馈；合成 P09/P10/P11 不能冒充真实科学质量。历史 430.284749 秒及 P4 检索指标不作本轮实测或通用目标。
