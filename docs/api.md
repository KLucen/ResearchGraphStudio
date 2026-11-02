# 本地接口（P1–P3 与 v3.3 阅读图谱）

> 当前 v3.3 分层图谱/自动选择已接入，见本页末尾的阅读图谱接口与 [接口映射](07_api_and_events.md)。本页同时保留旧审核接口的兼容说明，新工作流不调用它们。

> 运行契约说明：本页对应保留的 v2 P1–P3 与本轮 v3 M0–M6 增量。[v3 API/事件](07_api_and_events.md)仍包含后续目标；实际差异见 [ADR 0004](adr/0004-v3-projection-and-unified-extraction.md)。

版本：0.0.1 开发增量；协议：1；数据库 Schema：0010；新任务 paper-reading-v1 / reading-extraction-1.0；既有领域契约 knowledge-v2.1 和统一抽取/补译 unified-v3.1 继续兼容。Pydantic 为单一来源，生成文件为 [OpenAPI](../packages/contracts/openapi.json) 与 [TypeScript](../packages/contracts/generated.ts)。本页只描述已实现接口。

## 连接和权限

Tauri 启动随安装包分发的 Python 引擎，通过私有 stdin 传入随机会话令牌。引擎绑定系统分配的 `127.0.0.1` 端口，迁移与 FTS5 检查成功后输出就绪信号；宿主核验协议和 Schema。令牌不进入前端、命令行或日志。React 只能通过 Rust `engine_request` 的方法/路径白名单调用 API；不存在通用 URL、shell 或文件访问命令。

所有 HTTP 请求（包括 OpenAPI）需要 `Authorization: Bearer <session-token>`；带 Origin 的请求拒绝，Host 受限。生产包 CSP 不允许前端直接访问任意 HTTP 地址。会话令牌不保护同一操作系统账号下能够读取进程内存的恶意程序。

## 接口

| 方法与路径 | 行为 |
| --- | --- |
| GET `/api/v1/health` | status、version、protocol_version、schema_version、database（ready）、fts5 |
| GET `/api/v1/projects?cursor=0&limit=50` | items、next_cursor；当前 cursor 是偏移量，limit 为 1–100 |
| POST `/api/v1/projects` | name（去空白后 1–120 字符）、description（最多 4000）；201 返回项目 |
| GET `/api/v1/jobs` | 最近 50 个任务 |
| GET `/api/v1/projects/{id}/jobs?limit=10&cursor=<opaque-token>` | 本项目任务历史；按 `(created_at DESC, id DESC)` 稳定快照 keyset 分页，返回 `items` 与不透明 `next_cursor`，`limit` 为 1–100 |
| POST `/api/v1/jobs` | 当前只接受 `{"kind":"diagnostics"}`；202 返回任务 |
| GET `/api/v1/jobs/{id}` | 获取任务；不存在返回 404 |
| POST `/api/v1/jobs/{id}/cancel` | 取消 queued/running 任务 |
| POST `/api/v1/projects/{id}/papers/import/pdf` | path、mode=reference/managed；202 返回持久化 PDF Job。仅原生 import_pdf_file 选择文件后提交，普通桥不开放此路径 |
| GET `/api/v1/projects/{id}/papers?cursor=0&limit=50` | 项目文献分页 |
| GET `/api/v1/papers/{id}` | 文献、全部已保存附件修订和来源路径；路径是登记记录，不保证当前可读取 |
| GET `/api/v1/revisions/{id}/chunks?cursor=0&limit=50` | 不可变文本块、0 起始页索引、page label、块索引与 bbox |
| POST `/api/v1/jobs/{id}/retry` | failed/interrupted/cancelled 重排队；最多执行 3 次 |
| POST `/api/v1/sources/{id}/check` | expected_generation；202 返回来源检查 Job，原文件与托管副本分别核对 |
| POST `/api/v1/sources/{id}/relocate` | expected_generation、path；仅原生 relocate_source_file 选择器提交；202 返回重定位 Job，普通桥禁止此路由 |

SourceView 包含 generation 与 last_check。last_check 为空表示尚未检查当前来源；否则包含 checked_at、original 和可选 managed，每项为 state 与 observed_sha256。状态为 available（内容一致）、changed、missing、unreadable、too_large 或 unstable；不是持续可用性承诺，也不是证据审核结果。重定位必须匹配来源绑定的修订哈希；排队后 generation 改变时任务失败且不应用结果。详见 [ADR 0005](decisions/0005-source-check-relocation.md)。

项目/任务创建、知识抽取与审核等幂等写接口必须带 8–120 字符的 `Idempotency-Key`。相同操作/标识/内容返回首次保存的响应，不重复写入；同标识不同内容返回 409。任务响应可能是首次提交时的状态，应再次查询取得最新状态。项目任务历史使用 `(created_at DESC, id DESC)` 固定顺序，并以 SQLite 插入序号记录第一页快照；继续请求时只传递上页返回的 `next_cursor`，不要解析或自行构造游标。无效游标、跨项目游标或越界 `limit` 返回 422 `INVALID_CURSOR` 或校验错误。游标发出后，新任务（包括创建时间相同的任务）、状态更新和重试都不会改变该分页快照。

`JobView.stage` 只表示引擎已经观察到的阶段：`starting`、`reading`、`parsing`、`outlining`、`extracting`、`resolving`、`comparing`、`reasoning`、`checking`、`saving` 或 `diagnostics`。阶段不代表百分比；排队时为 `null`，取消/失败保留最后阶段和已保存批次进度，重试重新排队并清空阶段。清理暂存目录失败不会把已经提交的任务改为失败。

输入校验、业务冲突和鉴权失败返回 `error: {code, message, retryable, request_id}`。未知底层异常可能返回通用 500，由宿主转为连接/无效响应错误；不把数据库堆栈或原始输入作为用户提示。

## 持久化和恢复

Windows 默认数据位置为 `%LOCALAPPDATA%\com.researchgraph.studio`，以设置页实际显示路径为准。`researchgraph.sqlite3` 保存 projects、jobs、events、idempotency、papers、paper_sources、attachment_revisions、chunks 和 Alembic 版本；项目创建、PROJECT_CREATED 事件和幂等记录在一个事务中提交。PDF 结果、来源、文本块、PDF_IMPORTED 事件和任务成功状态也在一个事务中提交。0005 新增知识节点、证据、章节、模型调用、审核、依赖、graph revision、操作幂等和只读来源快照；旧 knowledge_events 加可空元数据。ReviewDecision 保留人工修改前后快照，不能用运行任务状态替代。Paper/AttachmentRevision/Chunk 分别兼容 Paper/DocumentVersion/paragraph。

仅引擎写数据库，文件锁防止多个引擎同时打开同一工作区。SQLite 启用外键、5 秒 busy timeout 与显式事务。迁移既有数据库前使用 SQLite backup API 留存快照；失败迁移回滚，禁止自动降级。恢复备份应先退出应用，并同时保留故障文件；用户恢复界面将在后续阶段实现。

启动时会回收 `data/import-work/` 中应用自有的平坦临时工作目录。目录必须包含精确的 `workspace.json` marker，并且所有内容都属于白名单；活动子进程持有同名旁侧 `.lock` 时报告 `busy`，目录链接、未知内容和权限失败报告 `retained`/`errors`，保留 marker 供下次启动重试。该回收不触碰原始 PDF、`attachments/`、历史修订、数据库或备份。`GET /api/v1/health` 的 `temporary_files` 和设置页显示本次启动的四项统计。

诊断任务实际执行 quick_check、外键检查和 FTS5 临时表检索。单 worker 串行执行；取消阻止结果回写，但不能抢占已开始的短时 SQLite 检查。启动将上次 running 改为 interrupted，queued 恢复执行。PDF Job 使用单独子进程，取消/正常退出终止解析；50 MiB、300 页、200 万字符、120 秒上限。Job payload 保存重试参数，JobView 仅暴露 project_id 和任务结果。重试需人工触发。模型任务使用相同 worker，阶段为 outlining/extracting/checking/saving；调用超时按模型设置，默认 90 秒，任务层另加 5 秒。取消阻止知识写入，但已发出的远端请求不保证立即终止。

关闭宿主 stdin 会通知引擎退出，宿主正常退出最多等待 5 秒再终止子进程；宿主崩溃时管道 EOF 同样触发引擎退出。启动日志位于数据目录的 engine-startup.log，令牌不写入该文件。

## v2 统一 Knowledge Engine 增量

| 方法与路径 | 行为 |
| --- | --- |
| GET `/api/v1/revisions/{id}/structure` | 持久化章节与 EvidenceSpan，保守解析，不伪造语义结构 |
| GET `/api/v1/evidence/{id}` | 再校验版本、paragraph、原文 hash、offset、quote 后返回 |
| GET `/api/v1/evidence/{id}/preview` | 校验可用 PDF SHA-256，内存生成 PNG data URL；块级高亮，不改 PDF |
| GET `/api/v1/revisions/{id}/knowledge` | 知识卡片和项目 graph_revision |
| GET `/api/v1/knowledge/nodes/{id}` | node、evidence、原始 model_run、reviews、graph_revision |
| POST `/api/v1/knowledge/extract` | document_version_id、provider 默认 project、allow_network、pipeline 默认 unified-v3；mock/configured/legacy-v2 仅显式测试或历史兼容；project 冻结当前全局 Extraction 模型配置与安全凭据引用；202 Job |
| POST `/api/v1/knowledge/reviews` | node_id、expected_revision、expected_graph_revision、action=revise/accept/reject、reason、可选 payload |
| GET `/api/v1/revisions/{id}/runs` | Prompt/输入 hash、模型、参数、原始输出、状态、错误 |
| GET `/api/v1/providers` | Mock/真实模型配置状态，不返回密钥 |
| GET `/api/v1/integrations/zotero/status` | 本机 Local API 只读连通性 |
| GET `/api/v1/integrations/zotero/{items\|collections}` | library 与 start 的受限读取，50 条/页 |
| POST `/api/v1/integrations/zotero/annotations` | document_version_id、library、item_key、attachment_key；校验已授权 PDF 路径/hash |
| GET `/api/v1/revisions/{id}/annotations` | 批注 ID、源 Key、评论、原始位置、block_matched/unresolved |
| POST `/api/v1/integrations/obsidian/roots` | project_id、path；仅原生 authorize_notes_directory 目录选择器可经宿主提交 |
| GET `/api/v1/projects/{id}/note-roots` | 当前项目授权目录及状态 |
| POST `/api/v1/integrations/obsidian/{id}/{scan\|revoke}` | 只读扫描或撤销，不删除/修改笔记 |
| GET `/api/v1/integrations/obsidian/{id}/notes` | 当前有效授权下的 Markdown 来源、hash、快照版本 |

新知识统一由 KnowledgeStore 事务入口处理；LLM DTO 不接受正式 ID、审核状态、SQL 或文件指令。已验证来源的作者主张以 unreviewed 入图；归属、数值或条件疑点为 needs_review。source_verified 只确认引文与保存原文吻合，不证明科学语义。人工审核使用乐观 revision，冲突 409；非法 DTO 为 422。重抽取复用精确相同对象，不覆盖人工版本；ModelRun 原始输出永久保留。

证据为 identity-v1 的 Python Unicode 字符偏移，end 为排他边界；bbox 为完整文本块。不同页用多个 span；本轮不做逐字框、跨页单一 span 或归一化纠错。新 PDF 修订保留旧知识/证据并加来源更新提示。人工修订暂不重接证据/依赖；Condition 独立卡片为当前状态，Claim payload 内 conditions 保留抽取时快照。

旧抽取每批最多 10000 原文字符，P01/P02 模板随包分发，运行契约在 knowledge_contracts.py。成功 P02 批次已提交，后续批失败不会回滚成功批；重试以 KnowledgeOperation 为持久化进度，跳过已成功批次并复用相同输入的已成功 P01 响应，不重复消耗模型调用。真实 Provider 参数见 README，Mock 不用于科学质量结论。批注无法唯一匹配时不生成正式文本偏移；私人笔记只读、禁链接逃逸，不参与论文抽取。

## 全局模型设置与 Zotero 批量导入（0006/0007）

| 方法与路径 | 行为 |
| --- | --- |
| GET `/api/v1/settings/models` | 所有项目共用的配置、默认角色与 has_api_key；不返回密钥或凭据引用 |
| POST `/api/v1/settings/models` | 新建配置，参数白名单；密钥写 OS 凭据管理器 |
| POST `/api/v1/settings/models/{profile_id}/update` | 更新配置；更换端点/类型清空当前密钥引用，旧引用保留给排队任务 |
| POST `/api/v1/settings/models/{profile_id}/delete` | 停用配置、清理凭据及角色；保留既有知识和模型记录 |
| POST `/api/v1/settings/models/{profile_id}/test` | 固定非论文文本调用，分别报告连通、JSON 校验和 Mock 标识 |
| POST `/api/v1/settings/model-roles` | 设置 extraction/reasoning，作为所有项目共用的默认角色 |
| POST `/api/v1/integrations/zotero/browse` | library/collection_key/search/start，10 篇/页，返回本地 PDF 可用状态和 next_start |
| POST `/api/v1/projects/{id}/zotero-imports` | library/collection_key/selections[{item_key,attachment_key}]/mode；每批最多 50 附件，每附件独立 Job；202 |
| GET `/api/v1/projects/{id}/zotero-imports` | 最近 100 个导入任务；更早历史通过项目 jobs 分页读取 |

原 projects/{id}/models 与 model-roles 路由保留为兼容别名，读取/修改全局配置；仍检查项目存在。0007 升级保留配置 ID、凭据引用与旧角色记录；旧角色一致时迁入全局默认，有分歧则留空等待选择。

模型设置及只读 browse 不采用持久化 Idempotency-Key 响应缓存，避免将含密钥请求写入幂等表；模型设置页面会禁用正在提交的按钮。Zotero 批量提交使用 Idempotency-Key 和在途任务去重，导入内容通过 SHA-256 去重；同条目不同 PDF 保存版本。客户端只提交来源 ID，服务端核验所属条目和分类后定位 PDF，不接受任意路径。

配置参数含可选 temperature/top_p/reasoning_effort、JSON 模式和 5–180 秒调用超时。max_output_tokens 仅兼容旧值，保存时清空；请求上限使用可信模型能力或服务默认。capabilities 只由服务器探测并写入，客户端不能注入。抽取任务层遵循配置并限制在至多 180 秒，额外保留 5 秒收尾时间；旧环境配置默认 30 秒。连接测试原生桥超时 190 秒。取消任务会阻止后续知识写入，不能保证服务端立即停止生成。Windows 凭据不在 SQLite 备份中，换用户或机器需重新录入。


## P3 条件化推理与图谱（0008）

| 方法与路径 | 行为 |
| --- | --- |
| POST `/api/v1/knowledge/candidates` | source_id/query/top_k（1–30）；同项目、其他论文、同节点类型的 FTS5/BM25 召回；只读 |
| GET `/api/v1/knowledge/nodes/{id}/context` | 当前主张/实体、依赖、条件与已验证证据，最多 100 个依赖节点 |
| POST `/api/v1/knowledge/{relations\|alignments}/infer` | source_id/target_id/provider=mock或project/allow_network；排队时冻结全局 Reasoning 配置；202 Job |
| GET `/api/v1/projects/{id}/reasoning` | 最近 50 次尝试及对应关系/对齐候选，包括 NO_DECISION |
| GET `/api/v1/knowledge/nodes/{id}/reasoning` | 节点关联的最近 50 次尝试 |
| GET `/api/v1/knowledge/{relations\|alignments}/{id}` | 候选、冻结比较/来源快照、模型原始输出和审核历史 |
| POST `/api/v1/knowledge/semantic-reviews` | proposal_id/kind=relation或alignment/expected_revision/action=accept或reject/reason；冲突 409 |
| GET `/api/v1/graph/subgraph` | project_id/kind=claim或concept或method/status=all或proposed或accepted或rejected/cursor/limit/focus_id |

图查询按 UUID keyset 排序，limit 1–120，最多返回 300 条两端均可见的科学关系；UI 每页 24 节点。status 筛选关系审核状态，不要求端点 Claim 已接受。该游标是有界浏览，不提供任务历史那样的插入快照；并发新入图节点可在后续页面出现。焦点范围最多 120 条关联关系。P03 对齐判断显示在审核列表，不伪装为科学关系或执行物理实体合并。

P04 必须覆盖当前条件维度，unknown/conflicting 不能当作 same/different；确定比较需要证据，单位不同不能直接相同。P05 必须引用双方主张的直接证据；CONTRADICTS 还要求整体可比、主题同一、任务/指标已知且值与单位一致。其他关系仍需人工判断科学含义。NO_DECISION 只保存 reasoning_attempts。所有候选及审核通过 KnowledgeStore 记录 KnowledgeEvent 与 GraphRevision。

输入使用本批 ev0001 等短证据编号。P02–P05 的 ModelRun.parameters.input_manifest 保存短编号到正式 EvidenceSpan 的冻结映射；只有 Schema 声明的证据字段可以解析，缩写/陌生 ID 直接拒绝，不猜测补全。原始输出保持原样。P01 每批最多 8 节、每节有界代表段落；P02 按所有证据区间分批抽取，不因此丢弃其他段落。

推理操作身份包含模型/端点/参数、Prompt hash、输入契约和完整来源快照。同配置同上下文重复运行复用候选，不覆盖审核。写入前及审核时重算依赖快照 hash；推理期间变化拒绝保存，已有候选标 stale 且不能接受。原候选、审核与模型结果仍保留。失效判断在读取时计算，完整后台依赖重算属后续阶段。


## v3 投影、布局和统一抽取（0009）

| 方法与路径 | 行为 |
| --- | --- |
| POST `/api/v1/projects/{id}/graph/projection` | 只读 body：kinds、search、paper_id、focus_id、depth 0–3、include_ai_candidates、diagnostics、limit 1–120、cursor；返回短标签、来源/审核状态、两端可见的边和 graph_revision，不含原文大段 payload |
| GET `/api/v1/projects/{id}/graph/nodes/{node_id}` | 完整 NodeView、显示翻译、最多 128 个相关领域对象与 80 个证据、论文版本和校验过的 Zotero 链接 |
| GET/POST `/api/v1/projects/{id}/graph/layout` | 布局 version、positions(node_id/x/y/pinned)、zoom/pan_x/pan_y；写入携带 expected_version，部分位置合并，最多 2000 节点，冲突 409；不增加 GraphRevision |
| POST `/api/v1/projects/{id}/graph/translate` | node_ids 1–30、provider=mock/project、allow_network；有 Idempotency-Key；冻结原文及显示版本，P04 仅补译显示，统一 Store 写 DISPLAY_TRANSLATED 事件，保留前后内容与 ModelRun |

投影默认 Paper/Concept/Method/Claim/ResearchQuestion，未人工审核但 source_verified 的节点可见；rejected/superseded 默认隐藏。来源结构边实线，AI proposed 边虚线，接受后实线，stale 或 NO_DECISION 无边。分页游标绑定筛选和 graph_revision，修订变化返回 409，客户端需回第一页；焦点 BFS 有限深与节点上限，has_more 表示截断。不会对旧数据自动调用模型。

新统一 P02 3.2 合并相邻段落，内部目标 8000 字符/64 个完整证据，已知模型输出能力较小时缩小；不因页号/章节 ID 改变就强制拆批，也不裁掉完整证据。旧任务按保存的 12000 字符计划或最早 6000 字符/章节规则恢复，包含 Concept/Method/Claim/ResearchQuestion、嵌套 Experiment/Condition/Finding/Metric 与来源结构边。运行 DTO 在 unified_contracts.py；其完整实验字段扩展了参考规范。证据只允许冻结本批 aliases，映射后检查真实 ID、quote/offset/hash 和来源；整批事务拒绝坏输出，避免悬空关系。英文回退与中文机器翻译不等于人工接受。

同版本、输入、模型/端点/参数、Prompt 和 Schema 下通过 KnowledgeOperation 跳过成功批次；收到但未提交的合法 ModelRun 可在同任务重试复用。连接阶段 timeout/network/rate_limit/server 最多三次尝试，退避上限 8 秒；统一抽取等待/读取响应及总时限 timeout 不原样重发，只允许未拆根批二分一次，子批仍超时即失败。output_limit/context_limit 最多三层拆分；单证据或达到上限明确失败。其余不可重试错误不自动重发。Job.payload.unified_plan 保存 prompt_name、计划、配置签名和证据哈希；旧无 prompt_name 的计划使用原模板。拆分 KnowledgeOperation 可跨重复任务复用。Prompt/来源/Schema 签名变化拒绝继续旧计划。Job.result 包含 batches、completed_batches/total_batches、knowledge_count、usage、model_calls、cost=null 与 cost_status。ModelRun.parameters 保存 attempts、duration_seconds、usage（含供应商返回的失败/推理用量）、有效请求限制及来源映射；每次请求记录 input_bytes/source_characters/evidence_count、发送/响应头/总耗时、response_bytes 和 timeout_phase，原始响应保留审计。未返回用量的超时请求可能收费，不能推算为零。

Zotero 批量导入新增 extract_after_parse（旧 API 默认 false）、provider 和 allow_network；开启后，在解析成功的同一事务创建确定身份的统一抽取子任务，父任务结果返回 extraction_job_id。默认 reference；旧参数默认值不改变旧幂等请求身份。Tauri 仅放行项目作用域图谱路由，open_zotero 只接受 library/groups 的有效条目 URI，不执行命令 Shell。

新运行 P02/P04 分别为统一抽取/显示补译；旧 P3 的 P03/P04/P05 文件名为兼容而保留，语义对应 v3 P03/P05/P06。比较和关系 DTO 新增可选 rationale_zh/reason_zh，英文与原始结果保留。完整 P4 Query/P5 Lint/Wiki 未实现。

正常产品入口只选真实全局模型。投影 `include_test_data` 默认 false，阅读/subgraph/candidates 为旧 API 兼容默认 true，当前 UI 显式 false：排除未经人工修改的 Mock 生成节点，人工接受或 revision>1 的记录仍保留。详情和历史可读，数据库不删除。投影 `include_paper_context=true` 可附加至多 24 个父论文与真实 REPORTS 来源边；`context_node_ids` 标识辅助节点，不改变主分页游标。新建任务不会静默回退 Mock。

Tauri 宿主对已授权 graph/layout POST 提供 512 KiB 有界请求预算，与最多 2000 个位置的服务端契约匹配；其他桥接请求仍为 16 KiB。

统一抽取的缺失局部引用错误提供 links[index].source_local_ref/target_local_ref 路径。`P02_local_link_repair` 辅助运行只返回端点补丁；每份错误响应一次修复记录，`ModelRun.parameters.input_manifest.repair_of_run_id` 指向原始运行。重试可复用旧 invalid 响应和已收到的修复结果，但不重复修复已失败记录；其他非法 JSON/证据输出仍可重抽未完成批次。源错误、已合法端点和科学内容不能被补丁改写，修复后仍经 Store 完整验证。不改变 API DTO 或数据库 Schema 0009。


## 2026-11-02：reading pipeline / 0010

- POST `/api/v1/knowledge/extract` 新增显式 `pipeline=paper-reading-v1`、density、paper_type。保留 legacy-v2/unified-v3 旧任务与默认 API 兼容，正常前端和 Zotero 子任务显式选 reading。
- 阶段增加 indexing/integrating/selecting/publishing；result 保留批次、整合窗口、已发布单元、coverage_gaps、build_state、全部模型用量。
- GET `/api/v1/papers/{id}/candidates?search=&cursor=&limit=40`：全部候选/来源有效性/选择原因；签名光标在候选或选择变化后拒绝继续。
- GET `/api/v1/papers/{id}/graph-selection` / `knowledge-units`：当前快照与引用成员，无选择时 revision=0。
- POST `/api/v1/papers/{id}/graph-selection/rebuild`：document_version_id、density、expected_revision、allow_network。已有有效选择不调模型；首次整合只排已有候选阶段，不抽 PDF。
- POST `/api/v1/papers/{id}/graph-selection/preferences`：candidate_id、expected_revision、action=include_core/exclude_core/reset_automatic、reason；不写 review，不绕过来源门槛。
- POST `/api/v1/projects/{id}/graph/projection`：view=paper_backbone、expanded_unit_ids、原筛选/分页字段；响应 reading-projection-2.0、selections、build_state、coverage_gaps，节点 graph_role/unit_ids，边 navigation 明确区别科学推断。view=legacy 留旧客户端兼容。
- 原详情、布局、模型历史、retry/cancel 接口继续使用。新增桌面桥接仅允许明确路径/方法/查询参数，鉴权和正文上限沿用原实现。
- 设计 `GraphSelection` 与运行快照的少量内部字段不同，不能直接调用 docs 参考模型替代 OpenAPI；历史审核路由保留但正常界面不再调用。
