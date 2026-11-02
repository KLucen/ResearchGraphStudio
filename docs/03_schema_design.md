# 03 — 阅读辅助知识图谱 Schema（设计 v3.3）

参考 Pydantic：[contracts.py](schemas/contracts.py)，生成 JSON：[generated](schemas/generated/)。参考契约版本 reading-extraction-1.0 / reading-integration-1.0 / reading-selection-1.0 / reading-projection-2.0。**运行库仍 0009，运行抽取仍 unified-v3.1，不能直接替换旧 DTO。**

## 分层与身份

| 对象 | 职责 | 谁产生正式 ID |
| --- | --- | --- |
| Paper / DocumentVersion | 来源身份、PDF hash、解析版本 | 现有来源模块 |
| EvidenceSpan / SourceTable | 原文、定位、表格与未解析状态 | 解析器/证据服务 |
| KnowledgeExtractionBatch | 本批候选及局部关联 | 模型只产生 local_ref |
| CandidateRecord | 正式知识及验证/质量元数据 | KnowledgeStore |
| PaperIntegrationProposal | 跨批关联/重复/单元提案 | 仅复用输入 ID，单元用 local_ref |
| KnowledgeUnit / UnitMembership | 结论与支撑的多对多集合 | KnowledgeStore |
| CoreSelectionProposal | 关键性和覆盖建议 | 模型不决定发布 |
| GraphSelection / SelectionPreference | 自动选择快照及可选显示偏好 | 选择服务经 Store |
| GraphProjection | Paper→核心 Claim→支撑的视图 | 投影服务 |
| GroundedPassage | Query/Wiki 的逐段出处与依赖 | 后续工作流验证后分配 |

Paper/DocumentVersion 映射现有 Paper/AttachmentRevision，不能再建平行来源库。知识单元是集合，不是新增一份 Claim；local_ref 只在原批/输入上下文内解释。

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

不输出 Paper、正式 ID、page/offset/quote、source_status、审核或科学真实性字段。未知额外字段一律拒绝；不在新契约中容纳 findings_placeholder。旧任务的明确 null 兼容仅属于旧运行适配。

links 指本批已存在 local_ref，关系枚举为 SUPPORTED_BY、ASSOCIATED_METHOD、HAS_CONDITION、REPORTS_FINDING、MEASURED_WITH、ABOUT_CONCEPT、ADDRESSES、LIMITED_BY；端点类型和证据均验证。跨批关联由 P12 在持久候选上建议，不猜跨批 ID。

## 条件与证据

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

SelectionPreference 只接受 include_core/exclude_core/reset_automatic，带 expected_selection_revision。它不是接受/驳回知识。失效来源无法被强制提升，返回原因；恢复自动规则也不会删除历史。

include_core 只适用于已有 Claim；Method/Condition 等通过已验证的结论成员关系展开。不能为了“提升”而临时改写候选类型、编造一个 Claim 或手工猜归属。

## 投影与未来消费

GraphProjection 默认只允许 Paper→核心 Claim 的 HAS_CORE_CLAIM；展开时 UNIT_MEMBER/SOURCE_EVIDENCE 从该 Claim 指向支撑/证据。这些线 epistemic_status=navigation，详情解释真实关联路径。SCIENCE_RELATION 需 assertion_id；模型推断虚线，NO_DECISION 不形成边。默认投影不包含 retrieval_only；搜索结果可另展示并临时定位，不写回选择。

每个单论文投影含 paper_id、document_version_id、knowledge_revision、selection_revision、build_state、expanded_unit_ids。项目视图组合多个单论文投影及经验证关系，去重共享 ID；分页保持根上下文和端点闭合。

RetrievalHit 不因图谱角色排除候选；来源/有效性门槛独立。QueryAnswer/GroundedPassage 为每段提供 attribution、带 revision/document_version 的论文依赖、证据及限制；个人观点另用 source_kind=note 与 snapshot_id，不能冒充论文证据；不能把图谱导航线作为科学证据。ReadingSynthesisDraft/WikiDeltaProposal 同样逐段引用，文件发布授权和冲突检查独立于知识自动处理。

## 迁移边界

参考 SQL 只描述建议新增关系，不可直接运行到用户库。正式迁移先备份、审计旧表、建立旧 ID 映射，再以 Alembic 加性迁移实现。旧嵌套条件/结果/实验与依赖已经存在时复用；原 ModelRun 和已完成任务签名保持。完整计划见 [06](06_development_migration_plan.md)。
