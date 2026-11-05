# 07 — 目标 API 与事件（设计 v3.3，与实现差异）

2026-11-04 当前：P4-Q01～Q07 已接入，Q08 安装反馈修复增加来源显示投影及保存内容批注/移除，Alembic head **0014**。边界见 [ADR0024](adr/0024-query-reading-cards-and-saved-lifecycle.md)，本轮状态见[反馈报告](p4-query-feedback-verification-20261104.md)，前次结果保留在[P4实际报告](p4-query-verification-20261104.md)。P5 Lint/Wiki 未启动。

已实现接口见 [api.md](api.md) 与生成 OpenAPI。自动构建、候选/选择/偏好、paper_backbone和P4-Q01～Q07已接入，数据库head0014；目标事件字段不保证与当前响应逐项同名。实际使用 expected_revision、selection_revision，项目投影 selections 按论文记录版本；未实现单独的 selection_revision 请求固定参数。Query生成/保存运行接口见本页对应章节，P5发布接口仍为目标。

## 自动构建

优先扩展现有 `POST /api/v1/knowledge/extract`，新增 pipeline=`paper-reading-v1`、density=`standard`，仍带 document_version_id 和 Idempotency-Key。Zotero/PDF 一键入口串接现有导入/解析任务，再启动此管线，无多余本地导入确认或人工审核步骤。

GET `/api/v1/jobs/{id}` 扩展阶段 indexing/extracting/integrating/selecting/publishing、阶段完成量、已保存候选数、已发布单元数、build_state、coverage_gaps、调用和未知费用。继续复用 retry/cancel；仅未提交阶段执行。模型、Prompt、证据或签名变动创建新构建版本，不能称旧任务续跑。

`retry`返回实际操作目标Job，旧任务独立续接可能返回已有后继，不能假定还是原id或queued。界面保留历史错误，但明确后继当前状态并可定位；已完成后继不重复排队/收费，失败后继需展示自己的原因，不能显示成无反馈。

新阅读任务由内部 reading_flow_policy=semantic-reading-1 选择新语义模板；不要求客户端或模型提供正式阶段 ID。模型快照冻结 output_policy，兼容接口 requested 能力不能显示为已实测 strict。调用/凭据管理接口沿用，真实 API Key 不进入快照正文或错误信息；运行 wire 与内部 DTO 区别见 [ADR0017](adr/0017-semantic-protocol-and-stage-recovery.md)。

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

候选/阶段检查点与事件同事务，选择快照与活跃指针同事务。上表为目标通知命名，不宣称已有完整outbox/SSE；当前以持久事件和轮询重建状态。Q01已分离KnowledgeStore.audit_event：query.prepared、NOTES_AUTHORIZED/NOTES_REVOKED/NOTES_SNAPSHOTTED和NOTE_USE_CHANGED等执行/文件操作记录before_revision=after_revision，不新建或递增GraphRevision。科学写入仍走原变更入口。

## 失败与权限

SOURCE_CHANGED、EVIDENCE_REF_INVALID、INTEGRATION_CONTEXT_STALE、UNRESOLVED_MEMBERSHIP、SELECTION_REVISION_CONFLICT、BLOCKED_CORE_REASON、MODEL_TIMEOUT 等分别给恢复方案；技术/来源失败不转为待人工审核。保留最后可用图和已提交知识。日志不得包含真实凭据或整篇私人文本。

模型记录终验失败使用 protocol/schema/context/evidence 分类与稳定 code，保留 raw_output 和 stage_validation 审计。模型回错根/版本等 response_invalid=true 才更新 status=validation_failed、error、finished_at；可信来源/候选/快照变化 response_invalid=false 时保留这三个历史字段，仅写本次复用诊断，停止并要求新构建，不能把它当网络重试。普通继续复用成功 P02/P12/P13 检查点和完整重验通过的旧响应，绝不无条件复用 received 的错误外壳。

所有接口回环鉴权、项目/文献隔离；新增桥接路径需明确方法和正文上限。不可通过任意路径读取PDF。当前Query只接受范围内的合法引用；后续Wiki生成同样须经过来源终验，文件导出授权独立，不属于科学审核。

## 当前Query准备API（P4-Q01～Q04）

以下是 Q01～Q04 引入、当前继续兼容的回环 API 与受限 Tauri 桥接。实现见[query_api.py](../services/engine/researchgraph/query_api.py)，基础决策及历史结果见[ADR0022](adr/0022-query-foundation-and-versioned-context.md)和[基础报告](p4-query-foundation-verification-20261104.md)。当前 Q06 问答页面已接入，下节说明回答与保存扩展。

| 方法与路径 | 实际行为 |
| --- | --- |
| POST `/api/v1/projects/{project_id}/query/search` | 严格QueryRequest，本地检索及完整合法图扩展，返回status/hits/graph/terms/independent_sources/ranking_policy；不调用模型 |
| POST `/api/v1/projects/{project_id}/query/search/page` | 独立浏览请求包装QueryRequest，完整合法命中按展示论文过滤并每页10条；返回总数/总页/结果指纹及只读来源显示，不改变模型prepare范围 |
| POST `/api/v1/projects/{project_id}/query/index/rebuild` | 重建/同步可重建索引；默认不读取个人笔记，不改科学对象 |
| POST `/api/v1/projects/{project_id}/query/prepare` | 带Idempotency-Key，冻结QueryRun与多来源检索/证据上下文、可用Reasoning快照；返回query_id/status/input_hash/snapshot/error |
| GET `/api/v1/projects/{project_id}/query/runs/{query_id}` | 当前权限/来源完整重验后读取已准备记录；不直接信任历史缓存 |
| POST `/api/v1/projects/{project_id}/query/runs/{query_id}/validate` | 重新组装/终验，返回valid/input_hash/reference_count/status；不生成回答 |
| GET `/api/v1/projects/{project_id}/query/documents?include_personal=false` | 最小文档只读适配：已保存段落、内部版本、根依赖、内容有效性与文件同步状态；无文档时为空 |
| PUT `/api/v1/integrations/obsidian/{root_id}/query-permissions` | 带Idempotency-Key，allow_local/allow_model；模型外发默认false，仍需root处于授权状态 |

QueryRequest项目必须与路径一致；论文/版本限定必须属于项目且是当前可用范围，跨项目或旧版本请求拒绝。source_kinds支持paper/knowledge/chunk/wiki/synthesis/note，knowledge_kinds用于候选类型过滤；过滤在最终排名前执行。include_personal默认false，purpose=local/model分别校验用途；purpose=model在此仅准备可外发范围，实际发送仍须显式generate及发送前终验。limit为1–100，不能理解为支撑闭包节点上限。

search以FTS5/BM25、精确短语/术语、已有双语/别名融合；graph返回种子、完整合法支撑路径、经终验的科学关系及条件比较，独立来源按根论文版本/个人快照去重。References/页眉页脚不作科学回答证据，画布分页/折叠/隐藏不限制候选检索。

search/prepare/GET准备记录可返回顶层presentation，分别以entry_id和ref索引可读来源：title、original、summary_zh、summary_origin、paper_id、page_index、section_path。它在来源终验后生成，不进入冻结snapshot或input_hash，也不外发；原文取真实quote，中文要点仅复用已有extracted_translation，缺失时为null，不新增模型调用。

分页浏览的独立正文包含 `{request: QueryRequest, page: 1, page_size: 10, display_paper_ids: [], expected_result_hash?: string}`，`page` 从 1 开始，`page_size` 固定 10。`request.paper_ids` 是原问题的检索范围，`display_paper_ids` 只筛选该问题已命中的展示内容；请求项目及两种论文范围都需校验。全部命中不受旧QueryRequest.limit的展示截取影响，但模型prepare和旧冻结记录继续遵循原契约。每次翻页重新检查当前来源/用途，结果身份变化返回 `QUERY_RESULTS_CHANGED`，客户端需从第一页刷新，不能拼接失效页。

分页响应提供 `status/hits/presentation/total/page/page_size/total_pages/result_hash/graph_node_count/independent_sources` 及可选 `scope_coverage`。命中presentation增加 `graph_presence={state,representation,node_ids,graph_roles,graph_revision}`，其中state为 `in_graph/retrieval_only/not_applicable`，representation为 `node/evidence/null`。`in_graph+evidence` 表示原文被已有图谱节点引用，不是独立知识节点。旧响应缺字段时不推断“未入图”；核验错误也不伪装为否定状态。

图谱存在性是顶层来源presentation的当前只读信息，判断完整默认阅读投影，不能读取单页画布节点或Query临时扩展来推断。历史/保存列表新增只读论文根归属元数据供板块筛选，不写回旧snapshot、manifest或回答hash。完整边界见 [ADR0025](adr/0025-query-browsing-and-paper-grouped-answers.md)。

prepare.status为prepared/insufficient；prepared表示上下文已准备，不是LLM回答成功。snapshot包含request/retrieval/context/model/prompt/source_scope，prompt明确generation_enabled=false；context使用query-context-1，含S短编号→真实来源映射、章节/完整表格组、节点修订和内容/文件/授权状态。容量仅依据已知模型能力估算，不截掉必要支撑，不执行能力探测。

相同幂等请求、GET历史及validate均重新检查上下文。假manifest为QUERY_MANIFEST_INVALID，来源/知识/权限/文档变化为QUERY_CONTEXT_CHANGED，跨范围/假种子等另返回明确QUERY_*诊断；错误不触发收费重试，原执行记录保留。旧单篇ModelRun保持，query_model_runs/query_answer_versions已由Q05用于项目级生成审计和不可变回答版本。

2026-11-05 新 prepare 在 context 冻结 numeric_layout，并使用独立 P07 v2；旧无字段 context/v1 仍保持 hash 与请求槽。`QUERY_NUMERIC_LAYOUT_UNRESOLVED` 表示正文使用明确版式风险数字，保留 raw、不自动继续；版式来源变化按上下文变化拒绝。专用limitations仅作带跨度/哈希审计的危险token占位，不改正文/raw；完整已收响应可用时，显式恢复冻结原runID/rawSHA/plan及现有预算，provider/新槽前重验，不可复用零网络失败。只读 presentation 可显示 layout_warnings，不回写历史答案。没有新增 HTTP 操作、迁移或模型 DTO 字段，见 [ADR0027](adr/0027-query-layout-aware-numerical-grounding.md)。

后续新prepare增加版本化scientific_guidance并选择P07v3；旧无字段清单保持原计划。`QUERY_SCIENTIFIC_GUIDANCE_INVALID`表示真实角色/引用组与来源清单不一致，属于上下文问题，不能通过额外收费重发解决。答案绑定只补清单已有原文根及检测表格组，scientific_binding审计随GET/保存/恢复终验；不新增HTTP操作、审核流程或模型输出字段。见[ADR0028](adr/0028-query-scientific-guidance-and-citation-closure.md)。

本地prepare和Store内部文档登记不等于回答生成或保存。P07需显式generate入统一Job，Q07经save入口再验后新增衍生对象；指定内部文档目标/基线与P5文件publish是不同动作。已实现的回答、历史、保存和衍生图接口见下节及[运行API](api.md)，后续任务与验收见[开发计划](06_development_migration_plan.md)。

## P4 回答、历史与保存接口（2026-11-04 / head0014）

所有路径均位于 `/api/v1/projects/{project_id}/query`，跨项目拒绝，沿用本地Bearer认证和Tauri方法/UUID/参数白名单。

| 方法与路径 | 实际行为 |
| --- | --- |
| `GET /runs?limit=&cursor=` | 按created_at/id稳定分页；默认20、最大50，状态读取实际Job |
| `POST /runs/{id}/generate` | Idempotency-Key必填；body=`{allow_network:true,continue_requested:false}`；202返回实际Job，显式继续才开第二槽 |
| `GET /runs/{id}/answer` | QueryAnswerView：执行状态、答案、模型用量/耗时/错误、可继续及请求计数；读取重验当前来源/用途 |
| `POST /runs/{id}/save` | QuerySaveCommand经KnowledgeStore.save_query显式保存；选段/hash/来源/权限终验；不改作者Claim |
| `GET /saved?include_personal=false` | 返回 `{items:[...]}`，只展示本用途仍获授权内容，过期段落标状态 |
| `GET /saved/{id}?include_personal=false` | 保存综合、原回答/文档版本/逐段依赖与状态 |
| `PUT /saved/{id}/annotation?include_personal=false` | Idempotency-Key必填；`{annotation,expected_revision}`更新独立个人批注，不改答案或科学revision |
| `POST /saved/{id}/remove?include_personal=false` | Idempotency-Key必填；`{expected_revision}`移出保存库/检索/衍生层，保留原始历史与证据 |
| `GET /derived-graph?include_personal=false` | 独立衍生节点及DERIVED_FROM引用，非科学关系 |

统一 `/api/v1/jobs/{id}/cancel` 和 `/retry` 支持query_answer；后者幂等返回真实后继状态，不将旧queued缓存冒充成功。每Query最多2个持久发送槽位，收到raw未发布可零调用恢复；失败不自动重试，达到上限零调用。GET不暴露raw；无证据/容量不足零调用并明确insufficient。普通检索/生成只有执行审计，明确save才新增科学revision/event。暂不提供Wiki生成、MD导出、Lint执行路由。

保存对象增加annotation、metadata_revision及removed_at；无旧偏好行时分别为空字符串、0、null。批注上限12000字符，metadata_revision用于expected_revision并发检查，不能拿GraphRevision替代。annotation仅本地个人元数据，不进入read_passages/检索/模型上下文；include_personal只控制来源私人材料用途，false不单独隐藏批注。移除直接读取返回QUERY_SAVED_REMOVED，已移除指纹再次保存明确拒绝；保存段落的后续副本及依赖谱系重验，不能从其它文档重新暴露。批注与移除只记审计事件，不删除Query/raw/答案/不可变文档或论文根，不推进科学图revision。
