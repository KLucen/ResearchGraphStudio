# 本地接口（P1–P5、阅读图谱、问答与Lint/Wiki）

2026-11-07 当前 P5 工作区实现见 [ADR0029](adr/0029-lint-wiki-workflows-and-managed-publication.md)，Lint性能与阶段进度见[ADR0030](adr/0030-lint-performance-and-progress.md)，数据库 head0020。本页维护当前运行接口及明确标注的历史兼容路径；生成 OpenAPI 与 TypeScript 契约同步导出，最新验证、基准与未验收项见[本轮报告](p5-lint-performance-verification-20261107.md)及[实施进度](progress.md)，[续开发报告](p5-verification-20261105.md)保留前轮结果。

所有路径以 `/api/v1/projects/{project_id}` 为前缀，仍须回环 Bearer 鉴权和项目隔离。写入操作使用 `Idempotency-Key`（8～120 字符），新增原生目录授权使用独立 native token。模型任务同时要求 `allow_network: true`；准备和轮询不调用模型。

| 方法与路径 | 行为 |
| --- | --- |
| `GET /lint/documents` | page/page_size分页列出可诊断草稿、保存与失效文档metadata；个人文档须include_personal及当前读取授权，不返回正文 |
| `POST /lint/runs` | 冻结 paper_ids/document_ids/include_personal，创建确定性报告 |
| `GET /lint/runs`、`GET /lint/runs/{id}`、`GET /lint/runs/{id}/issues` | 读取历史/进度/分页问题；严重性/类别/论文/生命周期过滤，不自动推进扫描；问题附程序派生的只读 repair_plan |
| `POST /lint/runs/{id}/advance`、`POST /lint/runs/{id}/cancel` | 有界推进对象检查（max_items 1～100，默认25）或已持久阶段、取消；末批必要的依赖重建独立推进，重启保留已检查范围 |
| `POST /dependencies/rebuild`、`GET /dependencies` | 显式重建派生依赖索引，或按对象查询依赖/受影响闭包；`/lint/dependencies`为同义路径 |
| `POST /workflows/prepare` | kind为lint_semantic/wiki_synthesis/wiki_delta，Query须为model用途。新请求显式personal_sources指定note_ids/annotation_ids/external_version_ids；P09要求同范围lint_run_id，P11要求page/base_version/affected_section_ids |
| `GET /workflows`、`GET /workflows/{id}` | 冻结工作流、当前资格、请求槽、用量和结果；不暴露raw或凭据 |
| `POST /workflows/{id}/generate` | 显式排统一p5_workflow Job；continue_requested才可用下一槽，最多两槽，无隐式重发 |
| `POST /workflows/{id}/materialize` | 终验P10/P11原响应后幂等创建内部草稿并返回完整页；P09建议不能执行为编辑 |
| `GET /wiki/pages`、`GET /wiki/pages/{id}` | 默认每页10，offset/limit最大100；详情可指定version_id/include_personal/purpose并逐段重验 |
| `POST /wiki/pages/{id}/save` | version_id/expected_head_version_id/expected_content_hash匹配后建立不可变保存版本，不写文件 |
| `GET /wiki/roots`、`POST /wiki/roots`、`POST /wiki/roots/{id}/revoke` | 独立写入授权；新增授权必须由原生选择器经X-ResearchGraph-Native-Token完成 |
| `POST /wiki/pages/{id}/publish` | root_id/version/head/content/预期文件hash和幂等键核对后写受管文件，不接模型路径 |
| `GET /wiki/publications`、`POST /wiki/publications/{id}/recover` | 分页发布账本；恢复重验当前来源、授权、hash与文件身份 |
| `POST /wiki/pages/{id}/inspect-file` | 建立授权文件只读外改快照/diff，不作为新科学证据，不回写 |
| `GET /p5/personal-sources` | 分页读取当前允许本地查看的笔记、批注评论与外部文档版本，返回独立allow_model；列出不代表已选择或授权外发 |
| `POST /p5/annotations/{id}/grant` | allow_model/可选allow_local/expected_revision和幂等键独立变更用途授权，不自动选择；local字段省略保留当前值，高亮不是评论 |
| `POST /external-documents/preview` | include_personal=true，按已授权root_id/relative_path只读预览UTF-8 Markdown及hash，不接受任意绝对路径 |
| `POST /external-documents` | 显式expected_sha256/title/attribution登记独立快照；追加需document_id/base_version_id，不继承Wiki证据或写权限 |
| `GET /external-documents`、`GET /external-documents/{id}` | 独立外部来源及版本历史；当前include_personal/用途权限重验，保留source_verified=false及独立文件状态 |

### Lint 运行阶段、耗时与依赖查询

LintRunView的`phase`独立于`status`：`scanning`为对象检查，`rebuilding_dependencies`为待执行/执行中的依赖索引重建，`finished`表示已进入终态。首次成功的全范围扫描需要建立依赖索引时，末批先返回`status=running`、`processed=total`、`phase=rebuilding_dependencies`；下次`advance`重验完整来源后重建并结束。已有索引或指定范围等不需要本次初始化的扫描可直接结束。`progress`仍是对象比例，不能单凭1.0宣称整轮完成；客户端用run ID、processed、phase及input_hash区分推进幂等key。重放已处理key只读当前报告，不重复执行。

`timings`字段的单位和意义：

| 键 | 记录内容 |
| --- | --- |
| `prepare_seconds` | 准备检查范围等准备阶段累计秒数 |
| `validate_seconds` | 每次推进对完整冻结输入复验的累计秒数 |
| `check_seconds` | 对象检查及本批读取的累计秒数 |
| `dependency_rebuild_seconds` | 依赖索引重建累计秒数 |
| `finalize_seconds` | 完成归档和报告差异处理累计秒数 |
| `elapsed_seconds` | 上述五阶段记录值之和，不包含用户等待、停机或全部HTTP往返时间 |
| `last_advance_seconds` | 最近一次已持久化推进的处理秒数 |
| `advance_calls` | 已持久化推进次数，幂等重放不累加，单位为次 |

0020迁移后的旧报告`timings={}`；未记录阶段保持缺省，客户端显示“未记录”，不能补成实测零。新增phase/timings不进入P09/P10/P11冻结snapshot、模型输入、hash或问题指纹。GET报告仅读取，准备请求未返回时客户端总数待定；完成对象检查后的依赖重建使用独立进度提示。

`GET /dependencies`使用`object_type`和`object_id`成对指定根，`direction=dependents/dependencies`选择反向影响或正向依赖；省略根时浏览当前项目登记边。指定根的查询通过递归CTE计算完整闭包并去重终止，再按当前权限筛选、计数与分页，不设固定跳数/节点截断。不可见中间对象不会截断后续合法影响，也不返回其身份；响应保留generation/event_sequence/pending_events。重建使用批量读取及同事务派生边写入，catalog指纹和逐调用来源/授权校验不省略。

P5模型任务取消/继续复用 `/api/v1/jobs/{id}/cancel`、`/retry`，GET使用统一JobView合法阶段。Wiki更新使用wiki_delta工作流，仅处理显式段落；开发计划中旧拟定的 `/syntheses` 和 `/wiki/pages/{id}/updates` 未作为运行入口。

新界面总是发送 `personal_sources={"version":"p5-personal-sources-1","note_ids":[],"annotation_ids":[],"external_version_ids":[]}`，只填用户实际勾选的快照/版本。该字段在历史请求缺省时不补默认值，旧P4请求与hash不改。笔记/外部来源沿已有Obsidian根的query-permissions独立控制local/model用途；批注评论默认不允许model，当前性只代表最后显式导入。外部来源`external_source`归属不改为用户作者或论文证据。

P5/Wiki/Lint的CHANGED/STALE/CONFLICT/REVOKED错误返回409，不存在404，Schema/范围/无证据422，SQLite BUSY/LOCKED沿用503标准JSON。来源/权限/基线变化停止并保留历史，幂等重放仍检查当前资格。


> 兼容接口说明：本页保留旧审核、v2 P1–P3 和 unified-v3 路由，供旧任务与历史数据读取；新自动阅读流程不调用人工审核接口。P4 Query 与 P5 路由已实现，设计目标与运行差异见[接口映射](07_api_and_events.md)。

版本：0.0.1 开发增量；协议：1；数据库 Schema：0020；阅读任务 paper-reading-v1 / reading-extraction-1.0保持；既有领域契约 knowledge-v2.1 和统一抽取/补译 unified-v3.1继续兼容。Pydantic为运行契约来源，生成文件为[OpenAPI](../packages/contracts/openapi.json)与[TypeScript](../packages/contracts/generated.ts)。带日期的小节保留当轮兼容背景；当前P5接口见页首，Query增量见文末。

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
| POST `/api/v1/jobs/{id}/retry` | 普通failed/interrupted/cancelled任务重排队，最多执行3次；旧协议兼容续接可返回独立后继Job，包括已存在的queued/running/succeeded/failed后继，不保证返回原id或queued |
| POST `/api/v1/sources/{id}/check` | expected_generation；202 返回来源检查 Job，原文件与托管副本分别核对 |
| POST `/api/v1/sources/{id}/relocate` | expected_generation、path；仅原生 relocate_source_file 选择器提交；202 返回重定位 Job，普通桥禁止此路由 |

SourceView 包含 generation 与 last_check。last_check 为空表示尚未检查当前来源；否则包含 checked_at、original 和可选 managed，每项为 state 与 observed_sha256。状态为 available（内容一致）、changed、missing、unreadable、too_large 或 unstable；不是持续可用性承诺，也不是证据审核结果。重定位必须匹配来源绑定的修订哈希；排队后 generation 改变时任务失败且不应用结果。详见 [ADR 0005](decisions/0005-source-check-relocation.md)。

项目/任务创建、知识抽取与审核等幂等写接口必须带 8–120 字符的 `Idempotency-Key`。相同操作/标识/内容返回首次保存的响应，不重复写入；同标识不同内容返回 409。任务响应可能是首次提交时的状态，应再次查询取得最新状态。项目任务历史使用 `(created_at DESC, id DESC)` 固定顺序，并以 SQLite 插入序号记录第一页快照；继续请求时只传递上页返回的 `next_cursor`，不要解析或自行构造游标。无效游标、跨项目游标或越界 `limit` 返回 422 `INVALID_CURSOR` 或校验错误。游标发出后，新任务（包括创建时间相同的任务）、状态更新和重试都不会改变该分页快照。

历史任务续接时，客户端必须读取返回Job的id/status/result并展示实际响应，不能只刷新原历史行。原错误记录保留，不因后继成功而覆盖；已成功后继不重新排队或调用模型。续接结果可能不在当前分页快照中，应显示其实际状态并提供定位入口；若后继失败，定位实际失败任务及原因，不能宣称已开始执行。

`JobView.stage` 只表示引擎已经观察到的阶段：`starting`、`reading`、`parsing`、`outlining`、`extracting`、`resolving`、`comparing`、`reasoning`、`checking`、`saving` 或 `diagnostics`。阶段不代表百分比；排队时为 `null`，取消/失败保留最后阶段和已保存批次进度，重试重新排队并清空阶段。清理暂存目录失败不会把已经提交的任务改为失败。

输入校验、业务冲突和鉴权失败返回 `error: {code, message, retryable, request_id}`。SQLite BUSY/LOCKED通过driver错误码识别，数据库OperationalError统一返回该JSON外壳：锁冲突为HTTP503 `DATABASE_BUSY`，其他为HTTP500 `DATABASE_ERROR`，不回显SQL、绑定参数、driver原文、路径或私人内容。宿主保留服务的结构化错误；遇到非JSON失败则提供HTTP状态和通用提示，不回显body。HTTP200的坏JSON也作为无效响应处理。其他未分类底层异常仍可能返回通用500，不能将其视为模型协议失败或自动恢复模型请求。

## 持久化和恢复

Windows 默认数据位置为 `%LOCALAPPDATA%\com.researchgraph.studio`，以设置页实际显示路径为准。`researchgraph.sqlite3` 保存 projects、jobs、events、idempotency、papers、paper_sources、attachment_revisions、chunks 和 Alembic 版本；项目创建、PROJECT_CREATED 事件和幂等记录在一个事务中提交。PDF 结果、来源、文本块、PDF_IMPORTED 事件和任务成功状态也在一个事务中提交。0005 新增知识节点、证据、章节、模型调用、审核、依赖、graph revision、操作幂等和只读来源快照；旧 knowledge_events 加可空元数据。ReviewDecision 保留人工修改前后快照，不能用运行任务状态替代。Paper/AttachmentRevision/Chunk 分别兼容 Paper/DocumentVersion/paragraph。

仅引擎写数据库，文件锁防止多个引擎同时打开同一工作区。SQLite启用WAL、外键、5秒busy timeout与显式事务，保留默认FULL同步耐久策略；WAL不允许多个并发写入者，也不保证无锁冲突。已审计的Query纯读取使用受query_only保护的deferred快照，实际写路径仍为BEGIN IMMEDIATE。迁移既有数据库前使用SQLite backup API留存一致性快照，不能只复制活动WAL数据库的主文件；失败迁移回滚，禁止自动降级。恢复备份应先退出应用，并同时保留故障文件；用户恢复界面将在后续阶段实现。具体读写与认领边界见[ADR0026](adr/0026-query-read-snapshots-and-worker-locks.md)。

启动时会回收 `data/import-work/` 中应用自有的平坦临时工作目录。目录必须包含精确的 `workspace.json` marker，并且所有内容都属于白名单；活动子进程持有同名旁侧 `.lock` 时报告 `busy`，目录链接、未知内容和权限失败报告 `retained`/`errors`，保留 marker 供下次启动重试。该回收不触碰原始 PDF、`attachments/`、历史修订、数据库或备份。`GET /api/v1/health` 的 `temporary_files` 和设置页显示本次启动的四项统计。

诊断任务实际执行 quick_check、外键检查和 FTS5 临时表检索。单 worker 串行执行；取消阻止结果回写，但不能抢占已开始的短时 SQLite 检查。启动将上次 running 改为 interrupted，queued 恢复执行。PDF Job 使用单独子进程，取消/正常退出终止解析；50 MiB、300 页、200 万字符、120 秒上限。Job payload 保存重试参数，JobView 仅暴露 project_id 和任务结果。重试需人工触发。模型任务使用相同 worker，阶段为 outlining/extracting/checking/saving；调用超时按模型设置，默认 90 秒，任务层另加 5 秒。取消阻止知识写入，但已发出的远端请求不保证立即终止。

关闭宿主 stdin 会通知引擎退出，宿主正常退出最多等待 5 秒再终止子进程；宿主崩溃时管道 EOF 同样触发引擎退出。启动日志位于数据目录的 engine-startup.log，令牌不写入该文件。

## v2 统一 Knowledge Engine 增量

| 方法与路径 | 行为 |
| --- | --- |
| GET `/api/v1/revisions/{id}/structure` | 章节与 EvidenceSpan；新增可空 structured_document（pdf-structure-1），含跨页章节、原文行/块与可恢复表格结构 |
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

配置参数含可选 temperature/top_p/reasoning_effort、JSON 模式和 5–180 秒无响应超时。max_output_tokens 仅兼容旧值，保存时清空；capabilities 由服务器探测或准确供应商/模型文档兜底，客户端不能注入能力。流式请求总时限为无响应超时两倍、最多 300 秒，任务外层另留 5 秒收尾；旧环境配置默认无响应 30 秒。连接测试原生桥最多 310 秒。取消任务阻止后续知识写入，不能保证供应商立即停止生成。Windows 凭据不在 SQLite 备份中，换用户或机器需重新录入。腾讯适配的角色策略与任务预算见[模型设置](model-configuration.md)。


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

该历史增量的 P02/P04 分别为统一抽取/显示补译；旧 P3 的 P03/P04/P05 文件名为兼容而保留，语义对应 v3 P03/P05/P06。比较和关系 DTO 新增可选 rationale_zh/reason_zh，英文与原始结果保留。P4当前运行接口另见文末；P5 Lint/Wiki未实现。

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

paper_backbone 的当前主节点排序为 paper-round-robin-1：论文之间轮换、单篇中心优先并交替结论与支撑。默认 60/最大 120 主节点，上下文另补；首篇不能占满多论文首屏。cursor 绑定排序版本与 graph_revision，旧光标或知识变化返回 422 CURSOR_STALE，可“返回第一页”重新分页；前文旧 legacy 的409/至多24父论文条款不适用于此模式。has_more 为分页状态，与 build_state/coverage_gaps 独立；paper_builds/selections 覆盖当前筛选的全部论文。前端取全论文列表分页供筛选和末尾选项，不一次无界返回全部图节点。详见[图谱接口](07_api_and_events.md#图谱与详情)。
- 原详情、布局、模型历史、retry/cancel 接口继续使用。新增桌面桥接仅允许明确路径/方法/查询参数，鉴权和正文上限沿用原实现。
- 设计 `GraphSelection` 与运行快照的少量内部字段不同，不能直接调用 docs 参考模型替代 OpenAPI；历史审核路由保留但正常界面不再调用。

## 2026-11-02：腾讯云流式适配与部分构建状态

后续用户交互修正：[ADR0012](adr/0012-compact-extraction-and-model-output-ceiling.md)将前端统一为原POST `/api/v1/jobs/{id}/retry`；适用时后端选择兼容续接，resume-adapted仅保留旧接口。输出额度按能力/剩余上下文，不再额外32K/64K限制。新P02运行使用reading-compact-1 wire Schema，展开后进入原领域DTO；ModelRun.parameters.reading_wire记录格式和expanded_fields（路径/规则，无新增正文日志）。旧计划继续原Prompt/Schema。

- JobView 新增 `resume_adapter_available`。POST `/api/v1/jobs/{id}/resume-adapted` 使用原 Idempotency-Key 规则，返回独立续接 Job；确定 ID 进一步防止不同请求键的重复点击。仅限准确匹配腾讯模型、未指定 effort、尚未进入整合且已停止的 reading 任务；同文献活动任务拒绝。旧 Job 不变，原 unified_plan/config/signature/批次账本保留，payload 独立记录 resume_adapter/resumed_from。校验原签名/证据后仅对未完成调用应用新策略。原 retry/cancel 行为不变，原生桥仅放行该准确 POST 路径。
- ModelRun.parameters.attempts[].request 记录 transport、effective_thinking、request_output_budget、能力来源、首/末字节、生成/思考字符数和总时限。Job.result.model_activity 每约 2 秒更新数字活动，结束清除。流结束异常记 incomplete_stream，不自动重发；安全 partial 留 ModelRun，不写知识。
- GraphProjection.paper_builds、graph-selection.build 返回 candidate_count（含该版本历史知识）、published_units、最新抽取任务/状态、completed_batches/total_batches、extraction_incomplete、active。不把候选数当已发布核心数。
- graph-selection/rebuild 首次/候选快照变化时拒绝活动任务或空候选；只使用已有候选执行 P12/P13。未完整抽取时携带 extraction_coverage_gaps，发布 partial；已有有效选择改密度仍不调用模型，原缺口保留。
- 未增加表或迁移，head 0010。详见 [ADR 0011](adr/0011-tencent-streaming-and-reading-recovery.md)。

## 当前阅读范围与续接（2026-11-02）

- GET /api/v1/revisions/{id}/knowledge新增current_schema_only布尔参数，默认false以兼容历史调用；正常阅读界面发送true。节点详情/原始模型记录仍可回查历史。
- /papers/{id}/candidates、paper_backbone和P12/P13默认只处理当前阅读候选。旧选择快照不作为现行主图发布，但revision继续递增，不删除ReadingHead/历史选择。
- POST /jobs/{id}/retry遇到旧阅读模板时返回独立续接Job；result.schema_upgrade/resumed_from表明新Schema续接。成功批次引用旧KnowledgeOperation，已收到且可重验响应复制到新ModelRun并记录response_reused_from，新增调用和Token计数为0；原始Job/ModelRun不改。
- 旧unified生产任务按新版重新抽取，不将旧图谱静默转换为新版候选。显式Mock/旧测试API保留兼容。无额外供应商操作入口。

主张比较器的GET /graph/subgraph及POST /knowledge/candidates也支持current_schema_only（兼容默认false）；正常界面发送true。筛选在分页/召回中生效，旧候选作为比较源会明确拒绝；历史详情保持可读。

## 当前结构解析与支撑图谱（2026-11-03 / 0011）

- 0011 仅新增 document_parses，文献版本/解析器版本唯一；不改既有 Chunk/EvidenceSpan/知识/ModelRun。GET `/api/v1/revisions/{id}/structure` 保留 sections/evidence，并附 structured_document 或 null。结构 schema_version=pdf-structure-1，包含 parser_version、blocks（原文、bbox、lines、ordinal、section_ref、excluded）、sections（parent_id、level、start/end_page、role）、tables（header、rows、cells 的行列/跨度/bbox/块引用、structure_status）和 warnings。查询本身不发模型请求。
- 新导入 PDF 用完整原文块建立 span。旧来源补解析需源 SHA-256 与每个原文块的精确文本/坐标匹配；不匹配返回 PARSE_SOURCE_MISMATCH/PARSE_ANCHOR_MISMATCH，旧记录保留。References 和页眉页脚保留在结构中，但排除新抽取输入；无 OCR，不保证复杂表格或公式语义恢复。
- 新任务冻结 P02_reading_extract_compact_v3、reading-compact-1、section-context-v1 及 parse_artifact_id，领域仍 reading-extraction-1.0。按跨页章节输入，各章节同规则，无 6000 字符/48 证据目标。只有模型上下文容量不足才按完整段落/表格组拆分，不截断原文；完整单组无法容纳明确失败。输入 allowed_evidence 带 section_path/context_group/context_complete，可附 source_tables；表格/章节 ref 不能充当 EvidenceSpan ID。旧冻结任务计划和成功操作不重排，超时/重试仍有界。
- POST `/api/v1/projects/{id}/graph/projection` 的 paper_backbone 新增 collapsed_unit_ids（默认空，最多 120）；expanded_unit_ids 保留且优先。默认显示核心 Claim 的已验证非 Claim 支撑，包括方法、实验、条件、结果、指标；显式收起隐藏相应分支。旧选择漏列但存在合法有向关联的支撑可只读补全，不改快照、不依共享证据猜边。Paper 只连核心，UNIT_MEMBER 仅作导航，端点闭合和共享 ID 保持。
- 对已观察的 Claim.kind_note_unused=null 仅执行精确无损规范化，紧凑响应审计记 ModelRun.parameters.reading_wire.expanded_fields，其他响应记 ModelRun.parameters.reading_envelope_normalization；raw_output 不变。非 null、其他 kind/未知字段仍拒绝；之后仍经过完整领域/来源/Store 校验。已收到失败响应完整重验通过，可零调用复用；具体结果见 progress，不把本地回放当成新 Prompt 真实生成或全文验收。

详见[ADR0014](adr/0014-structured-pdf-and-support-graph.md)。该历史增量没有增加人工审核或实现P4/P5；当前P4-Q01～Q07接口见文末。

## 阅读语义协议与阶段恢复（2026-11-03 / 当轮head0011）

上述带日期段落保留其历史范围；新任务按 [ADR0017](adr/0017-semantic-protocol-and-stage-recovery.md) 使用 P02_reading_extract_compact_v4 / reading-semantic-1，以及 semantic-reading-1 的 P12_reading_associations_v1 / P13_reading_ranking_v1。入口仍为 paper-reading-v1，领域仍为 reading-extraction-1.0；没有新表、迁移或人工审核接口。

- P02 模型根仅 items/links/warnings，版本/批次/默认语言由冻结 transport_context 绑定，展开后执行完整领域与来源校验。章节输入、References 排除、完整段落/表格组及有界重试规则保持；不新增固定字符/证据目标。
- P12 仅提出语义关联和重复建议，KnowledgeStore 沿全部已验证有向路径组单元；P13 完整且唯一覆盖请求内 claim_ref，仅给贡献建议。正式身份及发布由程序负责，旧冻结计划、签名与成功检查点继续原路径。
- 新 Provider 快照冻结 output_policy（structured-output-1）：仅代码登记的精确官方能力启用 native_json_schema；兼容 json_object 为 requested，不宣称 strict 已验证。能力冲突不自动降级重发，真实 strict API 尚待验收。

现有路由增加的可选响应信息如下，生成契约见 packages/contracts，旧客户端和旧快照仍可读取：

| 位置/字段 | 行为与兼容 |
| --- | --- |
| GraphProjection.paper_builds[].ranking_status | 当前可展示选择的排序状态；契约默认 unknown，首次临时视图 pending，有效历史选择缺标记按 complete 解释 |
| GraphProjection.paper_builds[].selection_mode | ranked/provisional，兼容默认 ranked；状态对应当前图，新任务失败可与保留旧图并存 |
| graph-selection 快照 contribution_order | 可选完整唯一根顺序，仅新语义发布传入；旧路径缺省不改变旧顺序及幂等指纹 |
| 根 entries / 已选 units 的 contribution_rank | 可选、从 1 开始，表示贡献建议顺序；不表示科学置信度，不规定力导向坐标 |
| Job.result.ranking_status | pending/complete/not_applicable；保留 stage_failure、previous_graph_retained、preview_selection_revision 等诊断，失败任务仍可继续未完成阶段 |
| Job.result.model_calls / model_calls_status / model_calls_unrecorded_runs | 从本 Job 的持久化 ModelRun.attempts 计实际记录请求；缺少明细的历史运行单列，状态 known_attempts_only，否则 recorded |
| Job.result.usage / cost / cost_status | 汇总供应商提供的非负整数 prompt/completion/total/reasoning Tokens，包含失败阶段；cost=null、provider_not_reported 表示未知费用 |

首次语义整合/排序失败且没有旧图时，只能发布通过保守来源/归属门槛的 provisional/pending/partial 视图。投影临时根 graph_role=provisional，Paper→根为 HAS_CANDIDATE_CLAIM（排序未完成）；完成选择的根为 core/HAS_CORE_CLAIM。根→有据支撑为 UNIT_MEMBER，支撑角色仍为 supporting。这些都是导航边，不是科学关系。已有有效图时失败保留旧图；来源或候选快照变化不发布临时替代。

新响应与 received/succeeded/validation_failed 缓存共用 validate_stage 完整终验，不能仅凭状态复用。response_invalid=true 才把模型记录更新为 validation_failed 并更新 error/finished_at；可信来源、候选或冻结快照变化 response_invalid=false 时保留历史 status/error/finished_at，只在 parameters.stage_validation 写本次分类/code/input/raw 哈希等复用诊断并停止。raw_output、历史供应商用量及结束原因不改，不为来源冲突发起新收费请求。

新语义阶段的调用统计在成功和失败路径均刷新；缓存复用不新增调用，缺少 attempts 不推定为一次请求，超时未返回用量不能推定零费用。三阶段严格拒绝重复键/NaN/Infinity/未知外壳；ADR0016 的限定单字符语法恢复只留在旧 P13 路径。来源与 Store 验证不省略；实际测试和未验证项以 [progress](progress.md) 为准。

## Query本地准备（0012引入，当前继续兼容）

[ADR0022](adr/0022-query-foundation-and-versioned-context.md)实现P4-Q01～Q04：本地召回、合法图谱支撑扩展、最小文档读取与版本化上下文。本节prepare仍不调用模型，prepared不表示已回答；Q05/Q07的generate、answer和save独立路由见下节，Q06已提供项目问答页面。

| 方法与路径 | 请求及返回 |
| --- | --- |
| POST `/api/v1/projects/{project_id}/query/search` | QueryRequest；返回status=empty/matched/no_evidence、hits、graph、terms、independent_sources、ranking_policy=lexical-graph-1 |
| POST `/api/v1/projects/{project_id}/query/search/page` | QueryBrowseRequest；当前全部合法词面命中按展示论文范围过滤并每页10条；返回总数/页数、结果hash及只读图谱标记，不创建QueryRun或调用模型 |
| POST `/api/v1/projects/{project_id}/query/index/rebuild` | 重建/同步项目query_index_entries/query_fts；默认不读取个人笔记；不需要幂等键 |
| POST `/api/v1/projects/{project_id}/query/prepare` | QueryRequest及Idempotency-Key；返回query_id/status/input_hash/snapshot/error，保存项目级准备记录 |
| GET `/api/v1/projects/{project_id}/query/runs/{query_id}` | 重新检查来源/权限/上下文后返回准备记录；跨项目不返回记录 |
| POST `/api/v1/projects/{project_id}/query/runs/{query_id}/validate` | 终验已有快照；返回valid、input_hash、reference_count与context状态，不调用模型 |
| GET `/api/v1/projects/{project_id}/query/documents?include_personal=false` | items为当前已保存文档段落及内部版本/根依赖/内容状态/文件状态；默认排除个人来源 |
| PUT `/api/v1/integrations/obsidian/{root_id}/query-permissions` | Idempotency-Key，allow_local默认true、allow_model默认false；返回root_id/用途及revision |

检索与准备请求示例：

```json
{
  "project_id": "project-id",
  "question": "主要方法在什么实验条件下有效？",
  "paper_ids": [],
  "document_version_ids": [],
  "source_kinds": [],
  "knowledge_kinds": [],
  "include_personal": false,
  "purpose": "local",
  "limit": 20
}
```

project_id与路径必须一致。paper_ids/document_version_ids为空表示项目当前来源范围；显式范围不得跨项目或使用已过期版本。source_kinds可选paper/knowledge/chunk/wiki/synthesis/note，knowledge_kinds为claim/method/finding/condition/experiment/metric/concept/research_question/argument/limitation。列表须无重复；limit为1–100，只限制种子命中数量，不截断必要支撑闭包。空白问题被严格请求拒绝；来源无命中正常返回不足，不发起外部搜索。

hits保留匹配原因、片段和来源数据；graph含实际种子、完整合法关联/成员路径、节点修订、条件四态及确定性比较。检索不受主图分页/折叠/隐藏影响，非法锚点、隔离/Mock/旧驳回/旧版本候选默认排除。Wiki/综合/原文同根命中不增加独立证据数。

search/prepare/GET准备记录增加顶层presentation：hits按entry_id、references按上下文ref索引SourceDisplay，包含title/original/summary_zh/summary_origin/paper_id/paper_ids/page_index/section_path。paper_ids由实际根来源派生，支持跨论文来源，不借用问题的整个请求范围。original使用真实来源片段，知识命中优先展示关联证据quote；summary_zh只复用已有辅助译文，summary_origin=extracted_translation或null。缺失不生成译文；presentation不进入snapshot、manifest、input_hash或模型请求，旧冻结契约不变。

### 完整来源浏览（2026-11-04 / head0014）

`POST /api/v1/projects/{project_id}/query/search/page` 的请求为：

```json
{
  "request": {
    "project_id": "project-id",
    "question": "主要方法在什么实验条件下有效？",
    "paper_ids": [],
    "include_personal": false,
    "purpose": "local",
    "limit": 20
  },
  "page": 1,
  "page_size": 10,
  "display_paper_ids": [],
  "expected_result_hash": null
}
```

`request`沿用QueryRequest；其中来源范围决定可检索内容，`display_paper_ids`只决定本板块展示范围，多来源条目命中任一所选论文即保留。空展示范围表示全部论文，重复、空白或跨项目论文ID被拒绝。此路由遍历本问题的全部合法词面命中，不以request.limit截断浏览；原search/prepare的命中额度和冻结模型上下文不变。“全部命中”不等于把数据库全部知识视为匹配，也不保证识别自动逐篇总结等语义意图。

响应含`status/hits/presentation/total/page/page_size/total_pages/result_hash/graph_node_count/independent_sources`及可选`scope_coverage`。page从1开始，page_size固定10，超出有效页返回`QUERY_PAGE_INVALID`；无命中时total=0、total_pages=1。后续页携带上次result_hash；每次重验来源、用途权限与当前图谱，结果变化返回`QUERY_RESULTS_CHANGED`，客户端显示刷新入口并从第一页重新读取，不混合旧页。graph_node_count/independent_sources描述整个问题的来源范围，不随展示论文筛选重算。

各命中`presentation.graph_presence`含`state`（in_graph/retrieval_only/not_applicable）、`representation`（node/evidence/null）、node_ids、graph_roles及graph_revision。其依据是分页前一次收集的完整默认阅读投影，不能用画布前60/120节点或Query临时扩展结果代替。原文支撑已展示知识时为in_graph/evidence，界面标“图谱已有知识引用的原文”，不把原文片段当独立节点；文档/笔记另标不适用。计算失败明确报错，缺字段不能当作未入图。浏览不生成跨论文所有Claim的两两条件比较；普通search/prepare的合法图扩展与确定性比较保持。

历史回答的来源预览按原问题重新检索当前内容，原答案仍只依赖冻结引用，新增命中不会回写旧snapshot/manifest/hash。前端来源、回答段落、保存内容/详情与历史独立筛选和每页10条；跨论文答案段落只展示一次并标涉及论文。每段引用外层与逐条内层默认折叠，打开外层不连带打开内层，显式“展开所有引用”才全部展开；引用超过10条同样分页。展示筛选和分页不丢失跨页已选保存段落，不新增模型调用。

prepare.status=prepared表示本地上下文ready；无证据、表格不完整或已知容量不足返回insufficient。snapshot冻结request/retrieval/context、可空model快照、prompt和source_scope；prompt.generation_enabled=false。context.policy=query-context-1，其references使用S短编号，记录真实Chunk区间/证据、节点、章节、完整表格组、文档版本和授权。PDF当前字节未检查时为not_checked，不能据此宣称当前附件已核验。

容量估算仅使用已登记的context_window/max_output_tokens，无任意字符/3跳/100节点预算；不足时保留完整上下文，不切掉必要条件或表头。不配置Reasoning模型也能做本地准备；已有配置只冻结安全配置/凭据引用，不读取API Key，也不调用模型。

同幂等键重复prepare、GET历史及validate均复核当前来源、知识、解析、授权和文档状态。QUERY_MANIFEST_INVALID表示清单hash被改；QUERY_CONTEXT_CHANGED表示可信输入已变化，停止复用但保留原QueryRun。QUERY_SCOPE_MISMATCH/QUERY_SCOPE_INVALID、QUERY_SEED_INVALID、QUERY_SOURCE_INVALID等返回具体拒绝原因，不能据此盲目重发模型。

文档content_state与file_state分开；内部有效段落可在未导出、文件缺失或外改时继续读取并明确状态。外部新文本不继承旧manifest，失效段落不给出可作回答的正文。NoteUseGrant区分本地与模型用途，include_personal=false时不读取笔记；purpose=model须allow_model，准备成功不代替生成前的用途终验。撤销root同时撤销外发许可，重新目录授权不静默恢复；缓存和经Wiki转述均不能绕过。

0012为加性迁移，保留旧来源/证据/任务/ModelRun，新增query_runs/query_model_runs/query_answer_versions、文档/段落/依赖登记、文件绑定、用途授权和派生索引。普通检索仅写派生索引，prepare另写执行记录与audit_event，均不改变科学图revision、论文知识、选择或布局。Store.query()仍为内部文档登记；用户回答保存走下节KnowledgeStore.save_query入口，Markdown发布留在P5。基础验证见[Q01～Q04历史报告](archive/reports/p4-query-foundation-verification-20261104.md)，当前结果见[P4报告](archive/reports/p4-query-verification-20261104.md)。

## P4 回答、历史与保存接口（2026-11-04 / head0014）

所有路径均位于 `/api/v1/projects/{project_id}/query`，跨项目拒绝，沿用本地Bearer认证和Tauri方法/UUID/参数白名单。

| 方法与路径 | 实际行为 |
| --- | --- |
| `GET /runs?limit=&cursor=` | 按created_at/id稳定分页；默认20、最大50，状态读取实际Job；顶层paper_ids取完成回答实际引用根，尚未回答时取准备上下文 |
| `POST /runs/{id}/generate` | Idempotency-Key必填；body=`{allow_network:true,continue_requested:false}`；202返回实际Job，显式继续才开第二槽 |
| `GET /runs/{id}/answer` | QueryAnswerView：执行状态、答案、模型用量/耗时/错误、可继续及请求计数；读取重验当前来源/用途 |
| `POST /runs/{id}/save` | QuerySaveCommand经KnowledgeStore.save_query显式保存；选段/hash/来源/权限终验；不改作者Claim |
| `GET /saved?include_personal=false` | 返回 `{items:[...]}`，只展示本用途仍获授权内容，过期段落标状态；各对象及其段落的顶层paper_ids由实际根来源派生供展示筛选 |
| `GET /saved/{id}?include_personal=false` | 保存综合、原回答/文档版本/逐段依赖与状态；paper_ids仅只读展示元数据，不修改冻结保存manifest |
| `PUT /saved/{id}/annotation?include_personal=false` | Idempotency-Key必填；`{annotation,expected_revision}`，个人批注最多12000字符，经Store写独立元数据 |
| `POST /saved/{id}/remove?include_personal=false` | Idempotency-Key必填；`{expected_revision}`，移出已保存库和后续检索/衍生层，保留历史与证据 |
| `GET /derived-graph?include_personal=false` | 独立衍生节点及DERIVED_FROM引用，非科学关系 |

统一 `/api/v1/jobs/{id}/cancel` 和 `/retry` 支持query_answer；后者幂等返回真实后继状态，不将旧queued缓存冒充成功。每Query最多2个持久发送槽位，收到raw未发布可零调用恢复；失败不自动重试，达到上限零调用。GET不暴露raw；无证据/容量不足零调用并明确insufficient。普通检索/生成只有执行审计，明确save才新增科学revision/event。这些 Query 路由不执行 Wiki 生成、Markdown 导出或 Lint；对应操作使用本页顶部列出的独立 P5 工作流、Lint 与 Wiki 发布路由。

0014保存偏好不改0013保存manifest。保存对象响应增加annotation/metadata_revision/removed_at，旧无偏好行兼容为空字符串/0/null；更新需匹配metadata_revision。annotation可本地查看但不进入read_passages/检索/模型上下文/科学根；include_personal仍只控制来源私人资料用途，false不单独隐藏批注。移除直接读取返回QUERY_SAVED_REMOVED，相同已移除指纹不能再次返回不可见成功。移除排除保存段落的后续副本并重验依赖谱系，不相关追加段落仍可读。批注不改模型正文或作者主张，两类操作只写审计、不推进科学GraphRevision；Query/raw/答案/不可变文档与论文根证据保留。

## Query只读快照与历史故障恢复（2026-11-04 / head0014）

GET准备记录、POST validate、GET documents、GET runs历史、GET answer、GET saved、GET saved详情及GET derived-graph共八个已审计路径使用`read_session`：关闭autoflush，连接执行`query_only=ON`及deferred `BEGIN`，归还连接时恢复可写模式。它们读取已提交快照，不争IMMEDIATE写锁，仍逐次校验来源/依赖/当前授权；意外写入被数据库保护拒绝。search/search/page及索引同步仍写派生索引，prepare/入队/save/批注/移除仍写持久状态，不能套用只读会话或取消原幂等/事务检查。没有新增接口或Schema迁移。

工作器空轮询只读探测queued，有候选后才以新的短IMMEDIATE事务重验并认领。认领及诊断数据库处理通过线程执行，锁等待不占用异步事件循环；未认领成功时保持queued、不发模型请求。关闭时等待已提交给线程的认领完成再清理running任务。历史页的“重新读取问答历史”只重读GET runs及其分页，不执行generate/retry、不新增任务或收费请求。503 `DATABASE_BUSY`可提示稍后刷新，500 `DATABASE_ERROR`提示设置与诊断；两者都不意味着应重发模型。实际回归、包与原生状态见[锁修复报告](archive/reports/query-history-lock-verification-20261104.md)。
