# ResearchGraph Lite P0：从 v3 完整工程的迁移评估

更新：2026-11-09（Asia/Shanghai）

本文记录 Lite A+B+D 重定位在当前工程上的实际映射与 P0 结果。它是迁移评估和验收边界，不是 A/B/D 功能已经完成的声明。完整目标设计仍以 [`docs/researchgraph_lite_ABD`](../researchgraph_lite_ABD/README.md) 及其 v1.0 规范为准。

## 范围和基线

本轮先完成可回退备份，再在独立分支实现 Lite P0。完整工程基线已经写入 [`docs/current_project_baseline.md`](../current_project_baseline.md)，并随提交 `7b45f0d` 推送到 `origin/backup/pre-lite-refactor`。当前开发分支为 `refactor/researchgraph-lite-p0`，本轮不把该分支推送到远端。

Lite P0 的目标是让“选择论文 → 本地解析 → 章节与文本索引”成为新项目的默认路径，并证明这条路径不调用模型。P0 不实现 B 论文卡片、A 章节导读或 D 证据问答，也不把旧图谱质量等同于 Lite 阅读体验。

设计包中“完整建图 30 万～80 万 Token/篇”和 Lite 显式任务 2.1 万～4.5 万 Token 是设计估算/预算目标，不是本工程当前逐篇实测值。本轮未调用真实 Provider，因此没有可报告的真实价格或模型 Token；价格未知时界面和接口保持 `cost_known=false` 或明确的未知状态。

## 当前架构和可复用资产

| 层 | v3 现有实现 | Lite P0 处理 |
| --- | --- | --- |
| 桌面宿主 | Tauri 2、Rust 路由白名单、Sidecar 生命周期和健康握手 | 复用；宿主新增 Lite 用量路由和 Schema `0022` 白名单 |
| 前端 | React/TypeScript、React Query、论文工作台、Zotero 选择与任务状态 | Lite 项目显示“文献与阅读”、本地解析/章节索引和用量摘要；legacy 项目保留原导航 |
| 引擎 | Python/FastAPI、SQLite/FTS5、Alembic、统一 Job/Store | 复用；增加模式判定、用量读模型和缓存基础 |
| 来源 | Paper、AttachmentRevision、Chunk/EvidenceSpan、结构 PDF、Zotero URI | 直接复用稳定来源身份，不复制 Lite 论文库，不上传或移动原 PDF |
| 模型 | Provider/ModelProfile、ModelRun、Query/P5 账本 | Lite 解析路径不创建模型任务；旧任务兼容入口由 Worker 和抽取入口阻断 |
| 知识图谱 | Claim、KnowledgeUnit、RelationAssertion、GraphProjection、Wiki/Lint | 不删除；legacy 历史数据仍可读取，Lite 默认隐藏高成本入口 |

## P0 的实际改动

### 模式和迁移

- `0021_lite_project_mode.py` 给 `projects` 增加 `experience_mode`。直接升级的旧项目回填为 `legacy`，新建项目 API 默认 `lite`，可显式创建 `legacy`。
- `0022_lite_usage_and_cache.py` 新增 `lite_token_usage` 与 `lite_cache_entries`，增加项目、论文、文献版本、小节和任务类型索引；不删除或重写旧表。
- `ProjectCreate`、`ProjectView`、ORM、OpenAPI、TypeScript 契约和 Tauri 白名单同步到 `0022`。

### 本地阅读路径和高成本流程开关

- Zotero/文件导入在 Lite 模式强制 `extract_after_parse=false`，即便旧客户端提交 `true` 也不会自动生成 P02/P12/P13 任务。
- Worker 在认领后再次检查 Lite 模式，阻止 `knowledge_extract`、`knowledge_reason`、`query_answer`、P5 工作流和翻译修复等完整模型任务调用 Provider；已排队的旧任务记录为本地阻断结果。
- 抽取入口和 Lint 后台维护任务也有 Lite 保护，避免绕过 Worker。
- PyMuPDF解析、跨页章节结构和Chunk/EvidenceSpan保持可用；Lite导入保存时物化FTS5本地来源索引，不依赖后续Query搜索才建立索引，也不遍历旧知识图谱。
- Lite 前端隐藏图谱、旧 Query、Lint、Wiki 和默认笔记来源入口；历史 `legacy` 项目继续使用原入口，旧知识和图谱不迁移、不清空。

### 用量和缓存基础

`GET /api/v1/projects/{project_id}/lite/usage?paper_id=...` 是只读汇总接口。汇总字段包含可确认调用次数、重试次数、缓存命中、输入/输出/总 Token、`provider/estimated/unknown` 来源计数、费用是否已知和按任务类型分组。`calls_known`、`unrecorded_runs`、`unattributed_runs` 明确披露缺失请求账本和无法独占归属的历史记录，不能把不完整的零计数当成零消费；论文级 Query/P5 用量以冻结来源为依据，不把项目全部调用摊给任意论文。GET 不推进任务、不写入用量或命中计数。

P0 缓存已经校验项目、论文、文献版本和可选小节的真实归属，并核对保存的来源 hash；读写身份纳入版本化键，已保存响应不可在原键覆盖，重复写入仅允许相同响应。缓存以 `stale` 标记保留旧结果；该校验针对保存来源版本，不代表磁盘原文件持续可用或当前科学语义正确。后续业务仍需将范围、证据与模型输入参数形成确定性输入指纹。

这些表和服务是未来 B/A/D 的基础，不代表 P0 已接入三类生成业务，也不代表所有旧 ModelRun 都有可复原的真实 token 账本。缺少 Provider usage 或价格时保留 unknown/estimated 语义，不能把未知费用写成零。缓存命中不产生新的模型调用和新 Token。

## 功能状态区分

| 功能 | 状态 | 事实边界 |
| --- | --- | --- |
| Zotero 连接、论文选择、PDF 本地解析 | 已实现并保留 | 使用现有读取/解析链路，P0 定向测试通过 |
| 章节结构、文本块、FTS5 索引 | 已实现并保留 | Lite 选择论文后可直接读取，不触发模型 |
| Lite/legacy 项目模式 | 已实现 | 新项目默认 Lite，旧项目迁移为 legacy |
| 完整 P02/P12/P13、跨论文推理、Lint/Wiki 自动任务 | Lite 默认停用 | 旧实现和数据保留；Lite 旧入口被阻断或隐藏 |
| 统一用量汇总和版本缓存基础 | P0 已实现基础 | 未来业务仍需在实际 Provider 调用点写入逐尝试记录 |
| B 论文卡片 | 仅设计 | P1 开发内容，P0 没有生成入口 |
| A 章节导读 | 仅设计 | P2 开发内容 |
| D 局部证据问答 | 仅设计 | P3 开发内容 |
| 每篇论文真实 Token/费用下降比例 | 未测 | 本轮真实模型调用为 0，不能宣称质量或通用节省比例 |

## 实际验证

- 最终完整后端回归：`1208 passed, 3 skipped, 1 warning`（456.23秒）；跳过项是既有平台权限/能力限制，TestClient弃用提示保留。P0/用量/模式专项18通过；Ruff/256格式、mypy141运行源及依赖检查通过。
- 最终前端：`17 files / 169 tests passed`（17.82秒），TypeScript/ESLint/Prettier、契约生成与生产构建通过；652.72KB chunk提示保留。
- Rust：`20 passed, 1 ignored`及格式检查通过；最终冻结引擎路径显式运行原生Host启动/连接/停止/重启，独立`1 passed`（3.41秒）。Windows PowerShell5.1的System32-only PATH引擎隔离17项通过。未实际安装用户应用，不能写成安装器或干净机验收。
- Lite定向测试覆盖新项目默认模式、旧项目legacy回填、匿名Zotero adapter、两份不同合成PDF本地解析、章节/Chunk读取、直接FTS MATCH与重启保持、零模型调用、五类旧排队任务阻断、已有cursor自动Lint停用、用量未知/重试/缓存和完整缓存身份/stale。
- 源引擎与最终冻结引擎smoke分别完成健康握手、认证、PDF导入、重启和历史兼容检查；每轮旧Query各使用离线P07协议stub 1次，与Lite解析零调用分开，真实模型调用为0。
- Lite两份PDF本地测试的输入/输出Token、调用次数、重试次数和增量费用均为0，Provider哨兵确认无请求。历史缺账本和未知费用仍明确披露，不能用这组零值替代旧账单。
- 正式用户数据库、私人 PDF/批注、真实 API Key 和真实 Provider 均未读取或调用；正式库实验写入为 0。

## 风险和未完成项

P0 仍保留旧 Query/P5/抽取 API 以支持历史兼容，因此“调用旧入口”可能先创建一个被 Lite Worker 阻断的任务，界面应把它显示为本地停用，而不是普通模型失败。缓存项目/来源版本/章节身份和不可变响应约束已在 P0 实施；未来 P1 必须把每次真实 Provider 尝试写入统一账本，并处理无 usage、超时是否已计费、重试和并发 single-flight，不能仅凭旧行数量推算真实请求。

P1 计划只做 B：受限输入选择、六字段 `PaperCardDraft`、证据 Span 白名单、版本化缓存和真实 Provider usage 接入；之后再评估 A 和 D。P0 不做整篇总结、不生成知识图谱节点、不自动更新 Wiki/Lint、不推送 Lite 分支。

## 回退原则

回退使用已推送的 `backup/pre-lite-refactor` 分支和提交 `7b45f0d`。Lite 迁移是加性的；不得删除 `projects` 旧字段、旧图谱表、用户论文或历史 raw。任何后续迁移都必须先在隔离数据库备份和升级/回退演练，真实模型和正式库实验需要另行授权。
