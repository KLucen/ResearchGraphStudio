# 03 — 阅读辅助知识图谱 Schema（设计 v3.3）

2026-11-04 当前：P4-Q01～Q07 已接入，Q08 安装反馈修复加入只读来源显示与保存生命周期，Alembic head **0014**。新边界见 [ADR0024](adr/0024-query-reading-cards-and-saved-lifecycle.md)和[反馈报告](p4-query-feedback-verification-20261104.md)；[ADR0023](adr/0023-grounded-query-and-explicit-saving.md)与[P4实际报告](p4-query-verification-20261104.md)保留前次结果。P5 Lint/Wiki 未启动。

R5当前传输见[ADR0021](adr/0021-keyed-ranking-and-bounded-correction.md)：新finish计划冻结P13_reading_ranking_v3/reading-ranking-keyed-1，程序固定完整assessments槽位并稳定排序，有界修复不放宽领域约束。v1/v2原计划与响应保留。此前[ADR0020](adr/0020-evidence-aware-core-selection.md)的真实原文/疑点/数字排版上下文、碎片核心门槛及成员caveats继续生效；它们不是科学正确性保证，实际结果见[progress](progress.md)。

参考 Pydantic：[contracts.py](schemas/contracts.py)，生成 JSON：[generated](schemas/generated/)。参考契约版本 reading-extraction-1.0 / reading-integration-1.0 / reading-selection-1.0 / reading-projection-2.0。**当前 Alembic head 0014，阅读任务仍使用 paper-reading-v1；Query加性表不改变阅读领域/传输协议。** 阅读服务使用独立 reading_contracts.py；本轮Query运行契约为[query_contracts.py](../services/engine/researchgraph/query_contracts.py)，与参考契约的区别见下节及[API](07_api_and_events.md)。旧DTO/任务签名仍可读取历史。

[ADR0017](adr/0017-semantic-protocol-and-stage-recovery.md) 引入 reading-semantic-1 传输和 semantic-reading-1 阶段协议，不改阅读领域。参考 PaperIntegrationProposal/CoreSelectionProposal 仍描述程序绑定后的对象，不能直接视为新模型输出 Schema。Q01～Q04新增结构按[ADR0022](adr/0022-query-foundation-and-versioned-context.md)，不改R5协议。

## 分层与身份

| 对象 | 职责 | 谁产生正式 ID |
| --- | --- | --- |
| Paper / DocumentVersion | 来源身份、PDF hash、解析版本 | 现有来源模块 |
| EvidenceSpan / SourceTable | 原文、定位、表格与未解析状态 | 解析器/证据服务 |
| KnowledgeExtractionBatch | 本批候选及局部关联 | 模型只产生 local_ref |
| CandidateRecord | 正式知识及验证/质量元数据 | KnowledgeStore |
| PaperIntegrationProposal | 程序绑定后的跨批关联/重复/历史单元提案 | 新 P12 仅语义短编号提案；正式身份由程序绑定 |
| KnowledgeUnit / UnitMembership | 结论与支撑的多对多集合 | KnowledgeStore |
| CoreSelectionProposal | 关键性和覆盖建议 | 模型不决定发布 |
| GraphSelection / SelectionPreference | 自动选择快照及可选显示偏好 | 选择服务经 Store |
| GraphProjection | Paper→核心 Claim→支撑的视图 | 投影服务 |
| GroundedPassage | Query/Wiki 的逐段出处与依赖 | 程序在回答绑定/保存时分配；Wiki整理留待P5 |

Paper/DocumentVersion 映射现有 Paper/AttachmentRevision，不能再建平行来源库。知识单元是集合，不是新增一份 Claim；local_ref 只在原批/输入上下文内解释。

### 结构文档与旧证据兼容

运行表 `document_parses` 保存 id、document_version_id、parser_version、source_sha256、data、created_at，文献版本/解析器版本唯一。data.schema_version=`pdf-structure-1`，包含 blocks（原文、bbox、lines、阅读 ordinal、section_ref、excluded）、sections（parent_id、level、跨页范围、role）、tables（header、rows、带行列/跨度/bbox/原文块引用的 cells、structure_status）及 warnings。

这是来源解析产物，不创建第二套 Paper 或正式知识 ID。新 PDF 以完整文本块建立 EvidenceSpan；既有 Chunk/EvidenceSpan 完全保留，补解析必须逐块核对精确文本及坐标。References 与页眉页脚仍在原始结构中，extraction 输入排除它们。表格结构只描述可恢复布局，不证明单位或数值语义正确。

## 候选抽取：显式类型，禁止占位键

items 为按 kind 区分的严格 union；每类都有 local_ref、label、summary、origin、evidence_ids、uncertainties。label/summary 使用 SourceText(original,language,zh?)。英文源保留英文权威值；中文可空并原文回退。标签不是 quote。

| kind | 特有字段 | 说明 |
| --- | --- | --- |
| Claim | statement, contribution_type, modality, scope? | 实验/方法/理论/综述/限制/背景主张 |
| Method | method_role | proposed/adapted/used/compared/unknown |
| Finding | result, reported_value?, unit?, baseline? | 实际报告结果，保留数值原字符串 |
| Condition | dimension,state,value?,unit?,alternatives | 开放维度，不写死学科 |
| Experiment | protocol | 真正出现的实验，不强造 |
| Metric | unit? | 指标含义在 summary，不能无单位强换算 |
| Argument | argument_type | derivation/proof/literature_comparison/explanation |
| Limitation | limitation_type | scope/uncertainty/negative_result/open_question |
| Concept | aliases | 名称相同不足以证明同一实体 |
| ResearchQuestion | 通用字段 | 论文自身提出的问题 |

不输出 Paper、正式 ID、page/offset/quote、source_status、审核或科学真实性字段。extra=forbid 保持；不在领域契约中添加 findings_placeholder 或任意说明键。运行适配仅允许有明确无损规则的已知说明规范化，见末节；不能因此容纳其他未知字段。

links 指本批已存在 local_ref，关系枚举为 SUPPORTED_BY、ASSOCIATED_METHOD、HAS_CONDITION、REPORTS_FINDING、MEASURED_WITH、ABOUT_CONCEPT、ADDRESSES、LIMITED_BY；端点类型和证据均验证。跨批关联由 P12 在持久候选上建议，不猜跨批 ID。

## 条件与证据

### 当前运行传输 reading-semantic-1

新 [reading_transport.py](../services/engine/researchgraph/reading_transport.py) 从领域及既有紧凑字段派生 P02_reading_extract_compact_v4 输出 Schema：根只允许 items、links、warnings，items/links 显式必填。document_version_id、chunk_id、contract_version、wire_format 和默认 source_language 由冻结 transport_context 绑定，模型不能输出或覆盖。证据使用请求内短编号，绑定后再执行严格领域、白名单、原文锚点和 Store 验证。

SourceText 字符串、共同语言省略和完全相同摘要省略沿用既有精确规则；原始相同 local_ref 候选须在展开前一致，不能由补默认值制造可合并性。Prompt 的结构规则由实际输出 Schema 生成并校验，避免独立手写字段约束漂移。raw_output 原样保存，reading_wire 审计记录格式、程序绑定及展开规则。

新 P12 的 SemanticIntegration 仅含 associations/duplicates/warnings，关联引用 source_ref/target_ref/evidence_refs，重复提案引用 candidate_refs/representative_ref。新 P13 KeyedContributionRanking 仅含 assessments/warnings；assessments的精确短编号集合由请求Schema固定，全部required且禁止额外属性。每槽位复用SelectionHint的recommendation/reasons/rationale约束，并加严格整数priority（0–100）；模型不重复生成claim_ref。程序按priority降序、同分按冻结输入顺序形成内部CoreSelectionProposal，绑定正式ID、文献版本、修订和coverage_gaps。旧ContributionRanking/ranked_claims仅供v1/v2冻结任务；不新增正式知识类型、表或迁移。

output_policy 是冻结模型参数中的 structured-output-1 对象，明确 mode、support、端点/模型及依据；ModelRun 记录源/请求 Schema 哈希和严格模式转换审计。native_json_schema 仅匹配代码中的官方精确能力登记；json_object/requested 不等于 strict 已验证。不支持的约束在发请求前失败，不能静默删除约束或自动降级重发。

### 历史运行传输 reading-compact-1

旧冻结任务继续使用独立 `P02_reading_extract_compact_v3` 或更早模板与[reading_wire.py](../services/engine/researchgraph/reading_wire.py)生成的 wire Schema，领域 reading-extraction-1.0 不变。顶层 wire_format/source_language 声明格式与共同原语言；SourceText 可省略相同 language，或用非空原文字符串表示无翻译文本。仅声明字段可无损展开，不能转换任意数值/额外键。Claim/Finding/Experiment 可省略与 statement/result/protocol 完全重复的 summary，程序精确复制；有额外语义仍显式输出摘要，其他类型 summary 必填。

原raw_output保留，展开路径/规则写reading_wire审计；之后执行原有字段、来源、条件及Store验证。旧模板/Schema/冻结签名继续原规则，不能通过新格式放宽旧任务。完整决策见[ADR0012](adr/0012-compact-extraction-and-model-output-ceiling.md)。下列领域条件规则不变。

### 领域条件与证据约束

- known 必须有一个原文支持的值；unknown/not_applicable 不允许值、单位或冲突列表。
- conflicting 保留至少两个有证据的 alternatives，不选择其中一个冒充确定值。
- EvidenceSpan.text_sha256 明确为完整规范化段落 UTF-8 SHA-256；offset 是该不可变段落的字符范围，end 不含。quote 必须精确相等，doc version/归属另验。
- SourceTable 保存 raw_text、headers、rows、caption、notes、structure_status；partial/unresolved 必须说明原因。既有无结构表格仅以原始材料回填，不假造网格。
- EvidenceInput.context_group/context_complete 用来维持表头、表行、注释上下文；不完整表格不支持自动猜数值/列含义。

## 状态与自动选择

新模型没有人工审核状态机。CandidateRecord.validation_status = valid/quarantined/superseded；source_status = anchored/needs_evidence/source_unavailable/invalid_anchor；QualityAssessment 记录 relevance、evidence_completeness、duplicate_status、blocking_issues、caveats、rationale、assessed_by、policy_version。

GraphSelection 独立保存 core/supporting/retrieval_only 和 automatic/user_preference；“未选”不等于非法或删除。自动核心必须是当前论文作者的 Claim、主贡献相关、证据充分或有限且明示限制、重复已解决、没有阻断问题。支撑节点必须有单元成员关系。人工显示偏好不能绕过来源/有效性门槛。

legacy_review_status 可空，只供历史迁移保存；新抽取不生成该字段的非空值，不出现审核 API/队列。旧 accepted/edited 内容不静默改写，旧 rejected/superseded 默认不重新发布。现有 review 表原样保留。

## 单元、选择与版本

KnowledgeUnit(root_claim_id, revision, memberships[]) 引用稳定知识。member 的 association_ids 必须在同版本输入中存在，组合成从根到成员的有效路径。共享成员可属于多个单元，不能用一个 parent_claim_id 限制所有归属。

GraphSelection 对完整输入候选快照逐个记录角色，避免未选对象无解释地消失；每个核心恰有一个选择中的单元，全部 supporting 被至少一个单元引用。版本包括 knowledge_revision、selection_revision、policy_version、density、build_state、coverage_gaps。快照不可原地覆盖；活跃指针事务切换。

新语义发布可选 contribution_order，必须唯一覆盖全部输入单元根。快照保存该顺序，根条目和已选单元保存从 1 开始的 contribution_rank；筛选不改变其相对贡献顺序。这些值是贡献建议，不代表科学置信度或布局坐标。旧路径不传时保持原顺序和原指纹；默认 ranked 不改变历史指纹，不能为补排序而使旧成功检查点失效。

SelectionPreference 只接受 include_core/exclude_core/reset_automatic，带 expected_selection_revision。它不是接受/驳回知识。失效来源无法被强制提升，返回原因；恢复自动规则也不会删除历史。

首次语义整合/排序失败且无旧图时，运行快照可额外标 selection_mode=provisional、ranking_status=pending、build_state=partial；其 quality.relevance 为 unresolved、assessed_by 为 rules。它是保守阅读预览，不能标为已完成贡献排序；来源/归属、非背景、非 unknown/speculative、无 issues 等门槛仍执行。已有图或来源快照变化时不发布临时替代，内部复用角色不改变外部“排序待完成”含义。

投影将临时根明确映射为 graph_role=provisional、Paper→根 HAS_CANDIDATE_CLAIM；完成选择使用 core / HAS_CORE_CLAIM。支撑仍为 supporting / UNIT_MEMBER，都是导航边。paper_builds.ranking_status 与 selection_mode 的契约兼容默认是 unknown / ranked；已有有效历史选择缺少标记时按 complete / ranked 解释。本次任务失败状态与保留旧图状态分别保存。

include_core 只适用于已有 Claim；Method/Condition 等通过已验证的结论成员关系展开。不能为了“提升”而临时改写候选类型、编造一个 Claim 或手工猜归属。

## 投影与未来消费

GraphProjection 的 HAS_CORE_CLAIM 仅连接 Paper→核心 Claim；默认同时显示有合法有向关联的非 Claim 支撑，包括 Method/Experiment/Condition/Finding/Metric，以 UNIT_MEMBER 连接相应结论，可显式收起。证据在详情按需查看。导航线 epistemic_status=navigation，详情解释真实关联路径。SCIENCE_RELATION 需 assertion_id；模型推断虚线，NO_DECISION 不形成边。未选候选不因共享证据进入主图；旧快照漏列但存在合法根到成员路径的支撑可只读补全，搜索临时查看不写回选择。

每个单论文投影含 paper_id、document_version_id、knowledge_revision、selection_revision、build_state、expanded_unit_ids。项目视图组合多个单论文投影及经验证关系，去重共享 ID；分页保持根上下文和端点闭合。

RetrievalHit 不因图谱角色排除候选；来源/有效性门槛独立。QueryAnswer/GroundedPassage 为每段提供 attribution、带 revision/document_version 的论文依赖、证据及限制；个人观点另用 source_kind=note 与 snapshot_id，不能冒充论文证据；不能把图谱导航线作为科学证据。ReadingSynthesisDraft/WikiDeltaProposal 同样逐段引用，文件发布授权和冲突检查独立于知识自动处理。

[ADR0018](adr/0018-query-wiki-and-obsidian-lifecycle.md) 的最小文档registry、不可变段落版本、根依赖及文件登记已由Q01实现，Q07已加入明确保存阅读综合；完整Wiki生成发布仍待P5。保存综合不是修改作者Claim，Wiki不是GraphProjection，也不以任意Markdown代替结构化知识。

运行契约分别表达内容valid/stale/invalid/unverified、draft/saved版本状态和文件not_exported/in_sync/modified/missing/conflict/unavailable。文件缺失不等于内部内容证据失效，外部新文本不自动继承旧段落证据。当前依赖支持chunk/evidence/node/note/passage并逐层解析到根来源；note授权穿透文档转述，不能借wiki标签绕过权限。Annotation的独立Query引用尚未接入，不能把其历史导入能力记成当前检索来源。检索同时命中不同表达层时按根来源去重，不增加独立支持数。参考Schema继续保留，不用它替代新运行协议。

query-source-graph-1记录种子、完整合法关联/逐成员路径、补回的方法/实验/条件/结果/限制、各自修订与根证据。GraphSelection角色只提供组织线索，不能充当科学真实性；GraphProjection分页和显示偏好不限制检索。已保存Synthesis/Insight使用独立类型/归属、source_query_id及多源依赖；衍生图层不复制或覆盖原主张。科学关系、单元导航、衍生引用和文档依赖分别处理。

### Query基础运行对象与实际表

迁移0012新增下表，0013另加显式保存索引，0014加入独立保存偏好；均不重建旧ModelRun或改写科学数据。旧ModelRun仍要求单文献版本；项目级Query执行不伪挂第一篇论文。

| 对象/表 | 当前职责 |
| --- | --- |
| QueryRun / query_runs | 项目、严格请求、冻结检索/上下文/模型配置、input_hash、准备状态及时间；跨来源执行记录 |
| QueryModelRun / query_model_runs | 项目级模型调用审计，含query_run、manifest、Prompt/模型/参数/raw/错误及发送前请求槽位；用于P07执行和恢复 |
| QueryAnswerVersion / query_answer_versions | 回答不可变版本，关联QueryRun和QueryModelRun；无证据的确定性不足回答可无模型调用 |
| QueryDocument / query_documents | wiki/synthesis稳定文档身份及当前已保存版本指针 |
| QueryDocumentVersion / query_document_versions | 不可变revision、draft/saved、hash；新草稿不替换现有已保存头 |
| QueryPassage / query_passages | 有序local_ref、text/hash、attribution、dependencies和caveats；不是论文Claim |
| QueryFileBinding / query_file_bindings | 授权root/相对路径、登记文档版本与文件hash、冲突状态；不授予发布权限 |
| NoteUseGrant / note_use_grants | 复用AuthorizedRoot，区分local/model用途及授权revision；模型外发默认关闭 |
| QueryOperation / query_operations | 准备/文档登记的幂等键、请求hash和结果定位 |
| query_index_entries / query_fts | 可重建的本地检索派生数据；无科学知识写入口 |
| QuerySavedKnowledge / query_saved_knowledge（0013） | 显式保存的Synthesis/Insight、来源答案/文档版本、逐段manifest与幂等指纹 |
| QuerySavedPreference / query_saved_preferences（0014） | saved_id、个人annotation、独立revision、removed_at与updated_at；不改保存正文或原manifest |

QueryDependency以type/id区分：chunk绑定完整块hash与start/end/quote；evidence复用原chunk hash及现有坐标；node绑定revision并重验当前合法候选和根证据；note绑定不可变快照hash及用途授权；passage绑定段落hash并递归核验。跨项目/循环、失效或Mock候选、假引用和未保存草稿拒绝；原始笔记字节及快照解码文本同时核对。

QueryRequest含project_id/question、paper_ids/document_version_ids、source_kinds/knowledge_kinds、include_personal、purpose和limit。query-context-1以请求内S短编号映射到真实来源及上述根依赖，保存章节路径、完整表格组、图谱路径、内容/文件状态、模型快照hash和覆盖缺口；上下文重新组装与hash终验决定缓存能否读取。

2026-11-05 新准备额外冻结 `numeric_layout`（`query-numeric-layout-1`）：按实际来源/Chunk/证据映射保留字号位移风险、压平数字和未知/部分覆盖。它属于版本化输入而非模型输出或科学知识改写；有字段时重建并终验，无字段的历史清单仍逐字保持旧 hash。新 P07 v2 与旧 v1 的 Prompt/计划分别选择，Schema `query-grounded-semantic-1` 和 head0014 不变，见 [ADR0027](adr/0027-query-layout-aware-numerical-grounding.md)。

后续新准备冻结 `scientific_guidance/query-scientific-grounding-1`：实际来源角色、原文根链接及已检测表格组；未检出结构为未知，不猜列或公式。存在此字段使用独立P07v3，旧仅numeric_layout仍v2、两者均无仍v1，输出DTO及head0014不变。绑定只补已存在合法根/表格引用，`scientific_binding`审计原/绑定引用与raw/guidance/结果哈希，GET/保存重算；不改原文/raw或把引用完整性说成语义证明，见[ADR0028](adr/0028-query-scientific-guidance-and-citation-closure.md)。

QueryRetrieval / QueryPreparation 顶层可带 `presentation={hits,references}`。每个显示项包含title/original/summary_zh/summary_origin/paper_id/page_index/section_path；summary_origin仅在复用已有抽取译文时为extracted_translation。它是终验后的本地显示投影，不进入snapshot/manifest/input_hash，不改变历史检索或模型输入。中文缺失不是证据缺失，不由程序编造译文。

GroundedQueryPassage、QueryAnswer、QuerySaveCommand用于Q05/Q07运行入口：段落引用唯一、个人归属与knowledge_status一致、不足必须说明；保存命令绑定source_query_id、answer_version_id、selected_passage_refs、expected_input_hash及显式文档基线。传输/身份/锚点终验不等于语义支持评价，真实回答质量和协议测试分别记录。

## 迁移边界

参考 SQL 只描述建议新增关系，不可直接运行到用户库。正式迁移先备份、审计旧表、建立旧 ID 映射，再以 Alembic 加性迁移实现。旧嵌套条件/结果/实验与依赖已经存在时复用；原 ModelRun 和已完成任务签名保持。完整计划见 [06](06_development_migration_plan.md)。

## 阅读运行范围与严格校验（2026-11-03基线）

该轮数据库为head0011；当前0014不改变以下阅读协议。领域DTO仍为reading-extraction-1.0，新P02v4传输reading-semantic-1，旧reading-compact-1保持冻结。items/links必须显式存在，字段缺失不能解释为成功抽取零候选；字段级extra=forbid及来源检查不取消。新语义阶段职责和Provider输出策略见ADR0017，旧模板及冻结计划保留。

新版阅读与图谱只纳入具有reading-1.0/P02_reading来源、且候选payload通过当前DTO校验的知识；旧unified知识、旧选择快照仅作历史。选择写入candidate_scope=reading-candidates-only-v1；快照包含该范围标记。没有删除、覆盖或重新编号旧知识。相同领域Schema的已成功阅读候选可复用，不因传输字段简化而重抽。新响应与所有可复用状态共用 validate_stage 完整终验；protocol/schema/context/evidence 诊断与 input/raw 哈希保存在 stage_validation，原始响应不改。response_invalid=true 才更新 ModelRun.status=validation_failed、error、finished_at；可信来源/候选/快照变化为 false，保留这三个历史字段，只记录本次复用诊断并停止，不转为新模型请求。

历史协议仅对明确、无损的模型外层说明进行规范化：旧P02顶层waiver字符串保留为warnings并审计；旧P12 limitations字符串数组映射warnings；旧P13 warnings/limitations映射coverage_gaps，已知冗余版本标记只作审计。对象型未知扩展、科学字段、原文ID、数值和条件仍严格拒绝。旧P12根自成员去除并留痕，不能将根视为自身支撑。新语义外壳仅允许自身 Schema 字段，不继承这些外壳说明别名。

本轮实际失败还包含 `items.1.Claim.kind_note_unused (extra_forbidden)`，只读原响应确认该值恰为 JSON null。限定适配只移除 Claim 上这个精确字段的 null：紧凑响应审计记 `ModelRun.parameters.reading_wire.expanded_fields`，其他响应记 `ModelRun.parameters.reading_envelope_normalization`，raw_output 保持原样。非 null、其他 kind、其他未知字段仍拒绝，不得借此删除科学内容或跳过证据验证。已收到响应的本地完整重验通过，不等于新 Prompt 真实生成或全文验收通过，具体结果见实际报告。

### P13 单字符语法恢复

P13v3的部分槽位及修复账本属于任务私有状态，不是GraphSelection或新的正式知识对象。程序保存根输入、请求/Schema/manifest哈希、序号与槽位ModelRun/raw哈希谱系，恢复逐次严格解码；不信任历史成功标记。额外字段、重复JSON键、非法JSON与未知编号仍拒绝，不通过去字段或冲突合并取得成功。全部槽位聚合后继续原领域/来源/完整支撑终验和Store原子发布，见[ADR0021](adr/0021-keyed-ranking-and-bounded-correction.md)。

旧 P13 的 `validate_selection` 可应用 [ADR0016](adr/0016-selection-json-syntax-recovery.md)：根对象最后字段 coverage_gaps 是非空、每项均为完整 JSON 字符串的数组，最终根 `}` 已存在，且仅数组闭合 `]` 缺失时，在该根闭合前插入一个 `]`。使用 token 解码识别位置，不改任何字符串、键、数值、ID 或建议；不补 EOF、不平衡通用括号、不推断模型是否表达完所有语义。新 P02/P12/P13 语义传输均严格拒绝重复键和 NaN/Infinity，不作该语法恢复。

旧 P13 正常及恢复后均严格拒绝重复键（含转义后同名）和 NaN/Infinity；恢复另拒绝尾逗号、未闭合字符串、额外/嵌套结构及其他损坏。ADR0016 的“其他阶段不变”是历史范围，后续新语义路径按 ADR0017 同样严格解码，不放宽领域 Schema。恢复后完整 Schema、白名单、ID/来源与 Store 校验仍执行。审计存 `ModelRun.parameters.integration_normalization`：rule=`close-final-selection-gaps-array-v1`、path、inserted、offset（0 起始 Unicode 字符索引，以字符串记录）、raw_sha256、normalized_sha256；raw_output 原样保留，旧 Prompt/领域/数据库及上下文策略不改。

P12属于组织建议：窗口外成员/关联/重复建议隔离，非法方向不写边，不同条件或归属不折叠。缺少整合结果的已验证根仅保留直接证据单元并标缺口，不虚构支撑；原始响应不修改。Store对实际写入的所有候选、证据、类型及闭合路径再次检查。见[ADR0013](adr/0013-current-schema-and-bounded-recovery.md)。

## P4 回答与显式保存运行契约

运行 AnswerWire/AnswerPassageWire 位于 query_answer_contracts.py，模型根仅 passages/limitations；每段只输出 text/attribution/source_refs/limitations。程序绑定 QueryAnswerVersion、A编号、输入hash、状态及原运行谱系；科学段落必须具备本次上下文中的论文根，个人观点必须具有授权note根，跨篇综合不得标为单篇作者主张。严格 JSON 拒绝重复键、NaN/Infinity、额外字段和未知引用，不猜补破损响应。

QueryModelRun 记录实际模型、Prompt/hash、参数/冻结策略、发送账本、raw、实际usage/finish_reason/耗时、稳定错误及未知费用。query_answer Job 复用统一工作器/取消/继续，QueryRun仍保留原 prepared/insufficient准备状态，前端执行状态读 Job/QueryAnswerView。

0013 加性新增 query_saved_knowledge，关联 source_query_id/answer_version_id、Synthesis或Insight、文档版本、选段ID和逐段多源manifest，不改旧0012/阅读表。QuerySaveCommand显式绑定预期input hash和所选段，指定文档更新需提供base_version_id。保存采用已验证段落复制（P08确定性路径），不为复制强制额外模型调用；个人来源权限沿根依赖穿透。历史回答/raw保留，未保存执行记录不自动进入知识检索。

0014 加性新增 query_saved_preferences。批注及移除命令绑定expected_revision与幂等键，响应以metadata_revision区分科学revision；旧无偏好行按版本0/空批注/未移除解释。移除排除对象及其保存段落的后续副本、依赖谱系，不删除不可变文档或原Query/raw；后续不相关追加内容不受连带删除。批注可本地查看但不进入read_passages/检索/模型上下文/科学根；include_personal仍只控制来源私人资料用途。两类操作只记审计、不推进GraphRevision。完整规则见[ADR0024](adr/0024-query-reading-cards-and-saved-lifecycle.md)。
