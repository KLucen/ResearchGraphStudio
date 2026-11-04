# 07 — 目标 API 与事件（设计 v3.3，与实现差异）

已实现接口见 [api.md](api.md) 与生成 OpenAPI。自动构建、候选/选择/偏好和 paper_backbone 已接入；下文目标字段不保证与当前响应逐项同名。实际使用 expected_revision、selection_revision，项目投影 selections 按论文记录版本；未实现单独的 selection_revision 请求固定参数。

## 自动构建

优先扩展现有 `POST /api/v1/knowledge/extract`，新增 pipeline=`paper-reading-v1`、density=`standard`，仍带 document_version_id 和 Idempotency-Key。Zotero/PDF 一键入口串接现有导入/解析任务，再启动此管线，无多余本地导入确认或人工审核步骤。

GET `/api/v1/jobs/{id}` 扩展阶段 indexing/extracting/integrating/selecting/publishing、阶段完成量、已保存候选数、已发布单元数、build_state、coverage_gaps、调用和未知费用。继续复用 retry/cancel；仅未提交阶段执行。模型、Prompt、证据或签名变动创建新构建版本，不能称旧任务续跑。

`retry`返回实际操作目标Job，旧任务独立续接可能返回已有后继，不能假定还是原id或queued。界面保留历史错误，但明确后继当前状态并可定位；已完成后继不重复排队/收费，失败后继需展示自己的原因，不能显示成无反馈。

本轮新任务由内部 reading_flow_policy=semantic-reading-1 选择新语义模板；不要求客户端或模型提供正式阶段 ID。模型快照冻结 output_policy，兼容接口 requested 能力不能显示为已实测 strict。调用/凭据管理接口沿用，真实 API Key 不进入快照正文或错误信息；运行 wire 与内部 DTO 区别见 [ADR0017](adr/0017-semantic-protocol-and-stage-recovery.md)。

阶段结果可携带 ranking_status=pending/complete/not_applicable、stage_failure 的 stage/category/code/next_action、previous_graph_retained 及 preview_selection_revision。首次失败预览明确 selection_mode=provisional、build_state=partial，任务仍保留失败和继续入口；这些不是人工审核状态。GraphProjection.paper_builds 新增 ranking_status/selection_mode，契约兼容默认 unknown/ranked；已有有效历史选择缺字段时按 complete/ranked 解释。它表示当前视图，不能用保留旧图的完成状态解释新任务成功。

graph-selection 快照可选 contribution_order，根条目和已选单元可选 contribution_rank（从 1 开始）。仅新语义发布传入完整唯一的根顺序；旧字段缺失保持原顺序与指纹，旧响应继续有效。投影临时根 graph_role=provisional、Paper→根 HAS_CANDIDATE_CLAIM；完成选择为 core/HAS_CORE_CLAIM，支撑 supporting/UNIT_MEMBER 均为导航。

新语义阶段在成功与失败结果中从本 Job 的 ModelRun 汇总实际 attempts 与供应商 usage，涵盖 P12/P13 失败调用。model_calls 仅计已记录请求，model_calls_unrecorded_runs 记录缺少 attempts 的历史运行数；存在缺失时 model_calls_status=known_attempts_only，否则 recorded。usage 只累计供应商提供的非负整数 Token，cost=null/cost_status=provider_not_reported；未知明细不推定一次调用或零费用，缓存复用不虚构新调用。

GET `/api/v1/revisions/{id}/structure` 保留 sections/evidence 兼容字段，并返回可空 structured_document（pdf-structure-1）。结构产物包含跨页章节、块/行位置、阅读顺序、表格表头/行列/单元格、excluded 和 warnings；查询不触发模型或重写旧证据。新任务冻结 parse_artifact_id 与 section-context-v1 计划，References 不进入抽取。

## 候选与选择

| 目标接口 | 语义 |
| --- | --- |
| GET `/api/v1/papers/{id}/candidates` | 分页/搜索全部候选，含角色、选择原因和来源状态 |
| GET `/api/v1/papers/{id}/knowledge-units` | 固定版本结论及成员引用，不复制内容 |
| GET `/api/v1/papers/{id}/graph-selection` | 活跃 GraphSelection 及完整度 |
| POST `/api/v1/papers/{id}/graph-selection/rebuild` | 基于已保存候选重算密度/策略，不自动重抽 PDF |
| POST `/api/v1/papers/{id}/graph-selection/preferences` | SelectionPreference + expected revision，设置显示偏好 |

不存在新的 review/approve/reject 路由。现有旧 review API 只为历史客户端兼容保留，不在新工作流/UI 中调用。展示偏好既不写审核记录，也不能绕过来源门槛；无效核心提升返回 BLOCKED_CORE_REASON。

## 图谱与详情

扩展现有 `POST /api/v1/projects/{id}/graph/projection`，使用 view=`paper_backbone`、paper_id、expanded_unit_ids、collapsed_unit_ids、limit/cursor。selection_revision 是目标快照语义，当前按响应 selections 读取，不作为独立固定请求参数。新响应以 reading-projection-2.0 区分。默认核心及其已验证的非 Claim 支撑可见，collapsed_unit_ids 显式收起，expanded_unit_ids 优先于收起；所有边端点闭合。

对旧选择快照漏列、但已有合法有向关联可从核心到达的支撑，投影可只读补全；不修改知识或旧快照，不仅凭共享证据猜关系。Paper 仅连核心 Claim，结论分支的 UNIT_MEMBER 是导航关系。共享支撑保留一个 ID。

项目级视图组合多论文投影与候选科学关系，响应须标每篇选择版本，不能让一个 selection_revision 代表不同论文。paper_builds/selections 覆盖当前筛选的论文范围，不受当前节点页限制。光标固定输入、选择和过滤快照，过期/跨项目光标返回 422 CURSOR_STALE，前端可直接“返回第一页”重新分页。

当前 reading-projection-2.0 使用 paper-round-robin-1 确定性排序：按论文轮换、每篇先中心再交替结论和支撑，默认 60/最大 120 个主节点，父论文及结论上下文另补并标 context_node_ids。cursor 同时绑定排序版本、筛选、选择、节点成员与 graph_revision；旧排序游标及图谱变动返回冲突，需回第一页。has_more 只表示尚有分页节点，不据此把完整构建标为 partial。该变动只读，不修改候选、选择或历史布局。

继续沿用节点详情/布局接口。布局保存只改 layout revision；搜索命中未选候选可加载独立详情，临时查看不隐式提升为核心。

## 事务事件

| 事件 | 内容与约束 |
| --- | --- |
| candidate.batch_committed | batch、候选 ID、knowledge revision；不是全部主图发布 |
| paper.integration_committed | 输入 revision、单元及关联变化 |
| graph.selection_published | paper/version、knowledge/selection revision、partial/complete、策略及差异 |
| graph.preference_changed | 展示偏好及选择 revision，不表示科学审核 |
| knowledge.source_invalidated | 来源版本和受影响对象，保留旧记录 |
| graph.layout_changed | 仅 UI 状态，不触发知识/Wiki 语义失效 |

候选/阶段检查点与事件同事务，选择快照与活跃指针同事务。事件方案待实现；轮询必须能够完整重建状态，断线不能丢进度。

## 失败与权限

SOURCE_CHANGED、EVIDENCE_REF_INVALID、INTEGRATION_CONTEXT_STALE、UNRESOLVED_MEMBERSHIP、SELECTION_REVISION_CONFLICT、BLOCKED_CORE_REASON、MODEL_TIMEOUT 等分别给恢复方案；技术/来源失败不转为待人工审核。保留最后可用图和已提交知识。日志不得包含真实凭据或整篇私人文本。

模型记录终验失败使用 protocol/schema/context/evidence 分类与稳定 code，保留 raw_output 和 stage_validation 审计。模型回错根/版本等 response_invalid=true 才更新 status=validation_failed、error、finished_at；可信来源/候选/快照变化 response_invalid=false 时保留这三个历史字段，仅写本次复用诊断，停止并要求新构建，不能把它当网络重试。普通继续复用成功 P02/P12/P13 检查点和完整重验通过的旧响应，绝不无条件复用 received 的错误外壳。

所有接口回环鉴权、项目/文献隔离；新增桥接路径需明确方法和正文上限。不可通过任意路径读取 PDF。Query/Wiki 后续仅接收白名单引用；文件导出授权独立，不属于科学审核。

P4 Query / P5 Lint-Wiki 的拟定操作、执行审计与科学版本边界、来源/授权及发布冲突验收集中在[开发计划](06_development_migration_plan.md)。这些路由尚未实现或写入运行OpenAPI；跨论文ModelRun作用域、诊断元数据及受管文件发布账本需先完成各阶段契约任务，不能直接复用会递增GraphRevision的知识事件入口记普通日志。

按[ADR0018](adr/0018-query-wiki-and-obsidian-lifecycle.md)，拟定query sources响应还须说明内部文档/段落版本、根证据、内容有效性、授权与文件同步状态。save默认新增阅读衍生对象；明确的Wiki目标/文档更新与publish文件操作分别绑定预期版本/哈希。P4先建最小registry/只读适配，P5扩展生成发布。Lint分别检查受管Markdown及授权私人资料，不能将外部编辑自动作为已验证论文知识或把文件同步冲突误当全部科学内容失效。本轮不新增实际接口。

图谱驱动Query的拟定检索/sources结果还须包含种子命中、扩展理由、KnowledgeUnit及合法关联路径、节点/关系修订、补充条件和根证据；来源于当前画布之外的内容可回查，不受其分页游标限制。save返回衍生对象/版本与来源引用，供独立衍生图层显示，不能直接返回“已更新论文核心”。Lint返回受影响单元/段落及规则诊断，不执行模型生成的修复动作。Query执行、Lint与文件状态审计和科学变更修订分开，普通查询不使现有graph cursor失效。上述均为计划要求，运行OpenAPI尚未新增这些路由。
