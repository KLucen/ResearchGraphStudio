# 09 — 实施注记（设计 v3.3）

当前运行基线为 P5 — Lint / Wiki、Alembic `0020`。功能状态、最新修复包与未验收项统一见 [实施进度](progress.md)；P5 设计决策见 [ADR0029](adr/0029-lint-wiki-workflows-and-managed-publication.md)。本页维护设计与实现边界，历史验收按各轮报告保留。

## 工程原则

按职责重构，以设计合理性和可测试性决定范围。保留有效解析、证据、来源、任务、凭据和 Store，不复制一个新系统；不以“最小侵入”阻止必要的抽取/整合/选择拆分。不要为改目录名搬动全工程。

建议职责：Source/Evidence → CandidateExtractor → PaperIntegrator → CoreSelector → GraphProjection；全部知识变更经 KnowledgeStore。共享工作流、模型记录、依赖和状态，不允许 UI/模型直接 SQL。

## 当前实现顺序

R1–R4已接入，R5补验收在报告范围内通过；P4 Query已接入，当前按明确指令继续P5 Lint/Wiki，不重抽已有论文。结构解析→支撑展示→限定Schema适配成果保留：PyMuPDF产出pdf-structure-1，0011将解析产物保存在document_parses，既有原文块和证据不改。[ADR0017](adr/0017-semantic-protocol-and-stage-recovery.md)及[ADR0021](adr/0021-keyed-ranking-and-bounded-correction.md)的P02v4/reading-semantic-1、程序组单元/P13v3保持；完整章节、无固定字符目标、完整段落/表格组与旧冻结计划规则不变。

reading_transport处理严格语义外壳和程序身份绑定，reading_prompt_contract生成Schema对应Prompt规则；structured_output冻结Provider输出策略；reading_finish_wire/reading_finish_semantic拆分语义提案、程序form_units、贡献建议与失败预览；reading_stage_validation统一新响应及缓存终验。Store仍是唯一知识写入口，阅读领域仍1.0。0012增加Query/文档基础与派生索引，0013增加显式保存索引，0014加独立保存偏好，0015～0019加性引入Lint、Wiki发布、P5工作流、外部文档及批注权限/当前性；旧阅读模型记录/任务签名和保存manifest不改。

旧图谱 REPORTS 全连接只保留在旧视图兼容；新版投影基于 GraphSelection/KnowledgeUnit，不靠前端猜“哪个节点挂谁”。来源关系可检索，但不作为每个节点的默认可见边。

默认投影显示核心的有据方法、实验、条件、结果及其他非 Claim 支撑，可显式收起。旧快照漏列但存在合法有向关联的支撑可只读补全；不修改旧选择、不依共用证据猜边。Claim.kind_note_unused 只在精确 null 情形无损移除并审计，其他额外字段仍严格拒绝。相关版本和取舍见 [ADR0014](adr/0014-structured-pdf-and-support-graph.md)。

## 当前Query模块与可复用边界

[ADR0022](adr/0022-query-foundation-and-versioned-context.md)和[基础报告](archive/reports/p4-query-foundation-verification-20261104.md)说明Q01～Q04历史范围；当前回答/保存扩展见ADR0023及本轮P4报告。运行实现与docs/schemas参考契约分别维护，不能把参考SQL直接执行到用户库。

| 运行模块 | 职责 |
| --- | --- |
| query_contracts / query_models | 严格项目请求、分型依赖、项目级执行/回答版本审计和文档/授权结构，供已接入的准备/回答/保存入口使用 |
| query_documents | Store.query()内部登记适配；不可变文档/段落、逐段根依赖及可终止循环检查；授权用途穿透、内容/文件状态分离、安全文件hash读取 |
| query_retrieval | 当前来源资格、可重建派生索引、FTS5/BM25与确定性中英/术语融合；类型/范围/权限过滤先于排名；无模型改写或向量服务 |
| query_graph | 全部合法候选入口、完整支撑路径/共享成员根回查、种子相邻科学关系终验、条件四态比较；不读取GraphProjection分页、不造来源或单元 |
| query_context | query-context-1引用短编号、真实Chunk/EvidenceSpan/章节/必要表格组、根来源与修订manifest；组装后与读取缓存时重验，已知容量不足保留完整组并标不足 |
| query_api | search/index rebuild/prepare、运行历史/validate、generate/answer、documents、save/saved和derived-graph；prepare不读密钥/调用模型，generate入统一Job；受限桥接沿原鉴权边界接入 |
| query_answer_contracts / query_answer_wire / query_answers | P07同源Schema/Prompt、请求内引用与归属终验；发送前持久账本、raw恢复、取消和最多一次显式继续 |
| query_save / query_saved_models | Store.save_query、0013保存表、选段确定性复制、逐段根依赖与显式文档基线、幂等和独立DERIVED_FROM引用层 |
| query_presentation | 来源/用途终验后的本地只读显示；准确原文、题名/定位与已有中文要点，不进入snapshot/hash或模型请求 |
| query_saved_lifecycle / 0014保存偏好 | 个人批注、元数据并发与移除状态；排除保存段落副本及传递依赖，不改原Query/raw/文档或科学revision |
| QueryPanel / queryApi / QueryDerivedGraph | 项目问答、证据回查、历史及显式保存；绿色来源与紫色综合分层，非知识根不误跳KnowledgeNode详情 |

0012新增Query审计和文档表、query_index_entries/query_fts；旧ModelRun单篇非空约束和原raw保持，跨篇执行用query_runs/query_model_runs，不伪挂首篇。索引重建与普通prepare可写派生/执行记录，不改变知识/科学关系/选择/布局。KnowledgeStore.audit_event与原科学event分开；Obsidian授权/用途/扫描不再推进GraphRevision。

registry可读取已登记的saved文档；新draft不替换已保存头。文件in_sync只证明字节匹配登记基线，不代表Markdown语义渲染认证。外改正文不导入旧版本；外改只读diff、Wiki主题/局部生成、发布与故障恢复已由独立P5流程接入。内部文档登记与用户选段save入口分开，后者必须重验回答版本、根依赖和当前权限。

Q05～Q07的调用/恢复、页面和保存已接入；Q08实际验收分别记录离线HTTP/SSE协议、合成检索/性能、真实论文模型回答和用户原生反馈，不互相替代。P5已在上述基础接入Wiki受管发布；没有外部搜索、新向量数据库、队列服务或产品多Agent框架。

## 当前P5模块与复用边界

Lint通过lint_service/lint_maintenance管理确定性报告、反向依赖和变更游标；p5_sources/p5_personal组装所选完整合法来源及逐份个人选择；p5_workflows/p5_execution/p5_transport管理P09/P10/P11快照、严格输出、持久请求槽及恢复。wiki_store/wiki_publish复用文档registry，维护不可变页面、独立写根和受管发布账本；external_documents登记独立外部Markdown版本，不写原文件或继承Wiki证据。P5Workspace及原生桥接提供项目入口；范围与操作以运行API为准。

## 自动化边界

新流程不含人工审核服务/队列/状态迁移。语义风险自动隔离或带限制展示；用户显示偏好独立。旧审核与用户修改保留不可覆盖，不在新界面强制出现。JSON shape、白名单、类型、版本、引用闭合和事务属于代码；重要性/语义支持可模型辅助，但必须记录不确定性与实测质量。

## 成本与失败

已有合法模型输出复用；整合/选择按候选和版本缓存；仅必要证据片段外发。模型超时有界停止，未收到用量标未知。暂时无法整合的候选保留并可检索；不无限分裂批次或把不完整结果包装成全文成功。

received/succeeded/validation_failed 缓存同样完成 JSON/DTO、版本/根、白名单、证据和快照终验。固定坏响应记分类诊断后不可无条件重复复用；仅 response_invalid=true 更新 validation_failed/error/finished_at，可信来源或快照变化为 false 时保留历史 status/error/finished_at，只记本次复用诊断并停止，不通过再次收费解决。Provider strict 仅精确登记能力启用，兼容 JSON 为 requested，未知约束/能力冲突不自动降级重发。实际 strict 尚待真实调用验收。

新语义发布保存完整 contribution_order 及 1 起始 contribution_rank；旧路径未传时保持原指纹与顺序。任务统计从持久化 ModelRun.attempts/供应商 usage 汇总，失败阶段不漏计；缺请求明细单列未知，缓存不造调用，费用不推算为零。

## 数据与发布

源段落/表格材料/定位/ModelRun 不属于临时回收范围。结构解析只是恢复可确认布局，无 OCR，也不保证所有复杂表格/公式/双栏均正确；失败保留原材料并报告限制。选择快照以 expected revision 发布，源或用户偏好变化时拒绝过期提交；上一有效图保留。布局独立，详情按需加载，不把全部原文塞入图谱 API。

首次语义整合/排序失败时，没有旧图才允许保守 provisional 视图，明确 pending/partial 及相关性 unresolved；仅有效来源、明确作者归属、非背景/unknown/speculative、无 issues 且非重复代表的结论和合法支撑可展示。来源/快照冲突不发布预览，已有图不覆盖。任务仍保留失败与未完成阶段，不能把预览成功当核心贡献排序或全文生成通过。

## 验收与交付

Conda researchgraph-studio；单元/契约/加性迁移/打包引擎/真实渲染与真实模型分别记录。优先自动化，按用户偏好提供操作步骤，由用户反馈原生体验；不频繁Computer Use。未经执行的安装/调用不记通过；迁移与故障只用隔离数据，正式库不作实验，不自动追加真实模型调用。最终命令、调用用量和未知费用统一写本轮验收报告，干净机/跨平台及新包用户反馈未测项单列。内部选段保存、P5主题草稿/保存与授权文件发布分别验证；P5运行实现不等于真实科学或用户原生退出验收通过。
