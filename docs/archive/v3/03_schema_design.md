> 历史 v3 平铺图谱设计，已由当前 [阅读辅助设计](../../README.md)取代；不作为新实现要求。

# 03 — Knowledge Schema / Graph View Schema 统一设计

> 版本 `knowledge_schema=3.0`; `projection_schema=1.0`; `extraction_contract=1.0`。**这不是要求对既有P2/P3数据库执行破坏性替换**。先兼容映射，再执行可回滚迁移。

## 1. 三种模型明确分离

| 模型 | 生命周期 | 保存方式 | 核心目的 |
|---|---|---|---|
| Domain Knowledge Schema | 长期稳定、含科研语义 | SQLite和既有领域数据表 | 科研事实来源、主张与条件化关系 |
| Extraction Output Schema | 每次LLM调用的候选批次 | JSON/Pydantic校验、模型运行日志 | 合并章节级抽取并限制模型输出 |
| Graph View Schema | 可重新生成的前端投影 | API响应、布局缓存 | 短中文标签、可拖动、点选详情 |

**原则**：修改视觉节点外观，不改写知识数据；修改Prompt格式，不直接修改数据库表；所有知识入图由后端映射完成。

## 2. 领域知识核心实体

| 实体 | 强制核心字段 | 说明 |
|---|---|---|
| Project | id,title,revision | 知识空间及增量修订版本 |
| Paper | id,source_kind,title,zotero_server_id?,library_id?,item_key? | 文献元数据；不必复制PDF |
| DocumentVersion | id,paper_id,attachment_key?,file_sha256,parser_version,created_at | 绑定具体附件字节版本 |
| Section / Chunk | id,document_version_id,order,text_hash,paragraph_id列表 | 可重复抽取单元 |
| EvidenceSpan | id,document_version_id,paragraph_id,page_index,start_offset,end_offset,quote,source_text_hash | 可定位、可核验原文片段 |
| Concept | id,canonical_en,canonical_zh,aliases_en,aliases_zh,description | 领域概念；处理消歧与翻译一致性 |
| Method | id,name_en,name_zh,summary_en,summary_zh,attributes | 方法/技术机制 |
| Claim | id,paper_id,statement_en,translation_zh,short_label_zh,origin,modality,scope,source_evidence_ids | 作者主张**不等于科学事实** |
| ResearchQuestion | id,question_en,question_zh,origin,related_ids | 作者研究问题或用户研究问题须区分 |
| Experiment | id,paper_id,protocol,condition_refs | 以逻辑对象保存，不默认可见节点 |
| Condition | id,dimension,state,value,unit,source_evidence_ids | `known/unknown/not_applicable/conflicting` |
| Finding | id,experiment_id?,metric_ref?,effect_direction?,value?,baseline?,source_evidence_ids | 数字/实验结果独立保存，不能只写在Claim中 |
| RelationAssertion | id,source_claim_id,target_claim_id,decision,comparability_ref,evidence_ids,model_run_id,state | AI推断或用户确认的关系判断对象 |
| Annotation / Insight / Synthesis | id,kind,author,source_refs,summary | Zotero批注、用户理解与派生综合不得混为作者事实 |
| KnowledgeEvent | id,project_id,object_ref,event_type,previous_revision,next_revision | 事务事件和审计 |
| ModelRun | id,model_id,prompt_version,schema_version,task_input_hash,status,cost? | 重现调用配置；不得保存密钥 |

可在既有数据库中沿用实体表+JSON扩展字段；不必为了“短标签”把Experiment/Condition永久删除。

## 3. 最重要的业务状态

```text
source_status = anchored | needs_evidence | source_unavailable | invalid_anchor
review_status = unreviewed | accepted | edited | rejected | superseded
knowledge_origin = paper_author | citation_report | user | model
assertion_status = source_reported | model_inferred | user_hypothesis
relation_decision = SUPPORTS | CONTRADICTS | QUALIFIES | EXTENDS | RELATED | NO_DECISION
condition_state = known | unknown | not_applicable | conflicting
batch_state = queued | running | validated | committed | retryable_failed | terminal_failed | needs_repair
```

- 允许**已自动展示而未人工审核**：`source_status=anchored`, `review_status=unreviewed`。
- `anchored`只指PDF原文证据可回查；科学结论不因此成立。
- `citation_report`表示论文**引用了别人**，不得写为本文作者自己实验发现。
- `NO_DECISION`保存推理日志，不生成科学关系边。
- `model_inferred`关系在视图中用虚线与候选标识，即使证据ID有效也不能直接当“科学已证实”。

## 4. 可见节点五类 + 详情映射

| Graph node.kind | 可见label | `detail_ref`加载的信息 |
|---|---|---|
| Paper | 论文短名（不采用超长标题） | DOI、作者、Zotero item/attachment、版本、关联知识 |
| Concept | 规范中文术语 | 英文名称、别名、定义、证据、关联方法 |
| Method | 简短中文方法名 | 机制、中英摘要、关联实验、条件与来源 |
| Claim | 简短“对象+结果/动作” | 完整原文主张、中文译文、限定范围、Finding/Condition、Evidence |
| ResearchQuestion | 简短问题 | 完整问题、来源身份、关联主张与开放问题 |

默认不生成“条件=3”“第4页证据”等视觉节点；它们在域模型中仍然可查询。高级“实验结构视图”可以按需展开Experiment、Finding、Condition。

## 5. ExtractionBatch输入/输出契约

**输入由后端提供**：`project_id`、`paper_id`、`document_version_id`、`chunk_id`、`allowed_evidence[]`（每项含ID与原文文本）、`source_context`、`domain_vocabulary`、`prompt_version`。仅`allowed_evidence_ids`可被LLM引用。

**输出由模型提供**：`document_version_id`、`chunk_id`、`items[]`、`links[]`、`warnings[]`。`items`的`kind`限定为五类；科研细节位于`ClaimDetail / MethodDetail`等类型化属性中。LLM仅允许生成本批次`local_ref`，正式主键由后端分配。

建议一个节点：

```json
{
  "local_ref":"claim-1",
  "kind":"Claim",
  "label_zh":"共享记忆提升合作率",
  "label_en":"Memory improves cooperation",
  "summary_zh":"在所报告的合作任务条件下，作者称共享记忆提高任务成功率。",
  "summary_en":"The authors report improved task success with shared memory in their cooperative setting.",
  "evidence_ids":["ev-001"],
  "origin":"paper_author",
  "claim_detail":{
    "statement_en":"Shared memory improves task success in the reported cooperative task.",
    "statement_zh":"共享记忆在所报告的合作任务中提高了任务成功率。",
    "modality":"asserted",
    "conditions":[{"dimension":"task_type","state":"known","value_en":"cooperative","value_zh":"合作","unit":null,"evidence_ids":["ev-001"]}],
    "findings":[]
  }
}
```

此为**虚构结构样例**，非真实论文证据。真实ExtractionBatch示例见`examples/extraction_batch.json`。

### 5.1 LLM不可以决定的字段

正式数据库`id`、`graph_revision`、`review_status`、`source_status`、`page_index`、`PDF path`、`file_sha256`、`created_at`、`is_scientifically_true`。这些都由解析器、验证器、KnowledgeStore或用户操作决定。

### 5.2 自动校验门槛

1. JSON Schema有效，局部引用唯一，允许`kind`和属性相匹配。
2. `evidence_ids`必须是该任务允许的证据集合；正文Claim/Method的主张应有至少一条有效EvidenceSpan。上下文不足时放入诊断队列。
3. EvidenceSpan映射到`DocumentVersion`且`quote`等于规范化原文对齐片段；页索引源自解析器，内部零基。
4. Condition已知值需要源证据；未知与不适用不能被擅自填为“相同”或0。
5. 在`knowledge_store.apply`事务中处理重复、来源状态、事件及增量通知。
6. 中文翻译不能改变数字、否定、强度或适用范围；译文不当可以标记`translation_needs_review`但不必拦截可靠的英文知识入图，使用英文回退标签。

## 6. GraphProjection v1 — 轻量前端接口

```json
{
  "project_id":"project-demo",
  "graph_revision":12,
  "filter":{"scope":"paper","id":"paper-demo","depth":2},
  "nodes":[{
    "id":"claim-001","kind":"Claim","label_zh":"共享记忆提升合作率","label_en":"Memory improves cooperation",
    "detail_ref":"claim:claim-001","source_status":"anchored","review_status":"unreviewed","knowledge_origin":"paper_author",
    "badges":["原文有据"],"size":1
  }],
  "edges":[{
    "id":"edge-001","source":"paper-demo","target":"claim-001","relation":"PROPOSES",
    "epistemic_status":"source_reported","review_status":"unreviewed","is_dashed":false,"detail_ref":"link:edge-001"
  }],
  "has_more":false,
  "next_cursor":null
}
```

### 图谱label策略

- 中文优先，并有英文回退；`label_zh`建议4–18个汉字左右；概念名称可略长，前端负责截断、tooltip和视觉处理。
- Claim短标签只概括“对象+作用”，不能替代`statement_en`、`statement_zh`和证据；不因显示简短就断言适用于所有条件。
- `detail_ref`只有一个精确对应的对象，不应将任意文件系统路径传给前端。
- `GraphProjection`可按筛选/语言/当前局部视图重新生成，不改变领域知识图谱。

### 布局数据不属于科学知识

```
graph_layouts(project_id, view_id, node_id, x, y, pinned, updated_at, layout_version)
graph_viewports(project_id, view_id, zoom, pan_x, pan_y)
```

拖动节点更新布局表，不应产生`KnowledgeEvent`或触发Query/Lint/Wiki重算。

## 7. 关系类型

**源关系（无须LLM科学推理）**：`PAPER_HAS_CLAIM`, `PAPER_HAS_METHOD`, `PAPER_STUDIES_CONCEPT`, `QUESTION_INVOLVES_CONCEPT`, `CLAIM_ABOUT_METHOD`, `CLAIM_REPORTED_IN_PAPER`等，应由经证据验证的抽取结构映射生成。

**AI候选科学关系**：`SUPPORTS`, `CONTRADICTS`, `QUALIFIES`, `EXTENDS`, `RELATED`。对应RelationAssertion，存Comparability、Reason、Evidence、ModelRun、审核状态。

**特殊判断**：`NO_DECISION`保存为InferenceRun，不生成实体间科学关系边。

## 8. 数据库迁移建议

1. 审计现有P2/P3表、关联及前端数据读取；不要按v3创建第二套重复表。
2. 只增缺失的字段：`short_label_zh`, `label_en`, `translation_zh`, `source_status`, `knowledge_origin`, `graph_revision`, `schema_version`等；可用旁路`display_metadata`与独立翻译表承载，避免大表锁。
3. 创建或扩展`graph_layouts`、`extraction_batches`、`knowledge_events`、`graph_outbox`；`GraphProjection`可以纯API计算，无需物化到新表。
4. 旧图谱节点ID/边ID不变；对旧数据用按需补全双语标签和详情引用；解析历史保持。
5. 迁移必须可逆或可备份恢复，先测试旧数据库样例再迁移用户库；不丢失已经存在的用户审阅状态。
6. 旧的手工审核API可保留为高级选项，但主建图路径不能依赖它。

## 9. Schema版本控制

`domain_schema_version=3.0`、`extraction_schema_version=1.0`、`projection_schema_version=1.0`按独立语义版本演化。Schema变化必须更新Pydantic/JSON Schema、Prompt版本、迁移与测试；模型跑出来的旧数据保留输入配置及来源，可选择升级重抽但不可静默覆盖。

## 10. 接口代码参考

`schemas/contracts.py`包含主要Pydantic实体、跨论文比较、推理及可视图谱契约；`schemas/generated/`包含由其生成的JSON Schema。正式工程中的Provider Structured Output可能不支持所有JSON Schema关键字，适配器需转为厂商支持子集，但服务端完整校验不可省略。
