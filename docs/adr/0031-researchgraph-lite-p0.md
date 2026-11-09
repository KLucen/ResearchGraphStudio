# ADR 0031：ResearchGraph Lite P0 模式开关与本地阅读基础

- 日期：2026-11-09
- 状态：已实现 P0，A/B/D 业务仍待后续阶段
- 适用分支：`refactor/researchgraph-lite-p0`

## 决策

ResearchGraph 从完整科研知识图谱的默认流程迁移为 Lite A+B+D 的渐进路线。P0 只改变默认入口和高成本任务触发边界：新项目使用 `experience_mode=lite`，选择 Zotero 论文后执行本地 PDF/章节/FTS5 处理，默认 0 次 LLM 调用。旧项目迁移后为 `legacy`，旧知识图谱、查询、Lint/Wiki 数据和 API 保留可读性。

P0 用新增的 `lite_token_usage`、`lite_cache_entries` 和只读用量接口建立统一观测与缓存基础。新增表不替代历史 ModelRun/Query/P5 账本；Provider usage、估算、未知和费用未知必须保持可区分。缓存命中不产生新调用，缓存内容按模型、Prompt、来源版本和小节身份形成版本化键并可标记 stale。

## 取舍

完整图谱抽取、跨论文推理、Lint/Wiki 后台和旧 Query 入口继续存在以保护历史数据与兼容性，但 Lite 模式默认不触发；Worker、抽取入口和后台维护任务共同执行保护，避免仅依赖前端隐藏。P0 不新增 B/A/D 生成接口，不把旧图谱显示当成 Lite 论文卡片、章节导读或局部问答的替代。

采用增量 Alembic 迁移 `0021`、`0022`，而不是重建数据库或删除旧表。迁移为旧项目设置 `legacy`，新项目 API 默认 `lite`，这样既能保存已有图谱，又能让新用户从低成本本地阅读开始。

## 验收边界

P0 的通过条件是本地解析和索引链路对匿名样例不调用模型，旧数据可读，Lite/legacy 模式不会导致应用启动异常，模式/用量/缓存回归通过。真实 Provider Token、价格、引用质量、B/A/D 功能和安装器原生体验不在本 ADR 的通过结论中；这些项目必须在对应阶段单独验收。

`unknown` 只表示信息或计量缺口。缺少实验条件、Provider usage 或价格时，程序保留 unknown/费用未知，不据此推断矛盾、补造条件或把未知费用写为零。

## 后续

Lite P1 先实现 B01 论文卡片：限制输入范围、六字段结构化输出、Span 引用校验、逐版本缓存和逐尝试用量记录。A01 章节导读和 D01 局部证据问答分别属于后续阶段；在此之前不恢复完整 P02/P12/P13 自动建图，也不把全量 Lint/Wiki 放回 Lite 默认路径。
