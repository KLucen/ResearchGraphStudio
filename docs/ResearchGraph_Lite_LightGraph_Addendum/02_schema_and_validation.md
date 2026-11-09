# 02. Schema 与校验规范

## 设计原则
- 一次概览响应同时返回 PaperCard 和 LightGraph。
- 不生成证据溯源字段。
- 图谱按单篇论文隔离，不做跨论文合并。
- 模型只返回语义数据，不返回坐标。
- 中文为主要展示语言，英文原词保留在节点标签中。

## 顶层结构
`paper_overview_graph.v1`：
- `schema_version`
- `paper_card`
- `graph`

`paper_id`、PDF 哈希、模型标识、Token 用量、生成时间由后端写入，不让模型生成。

## PaperCard
| 字段 | 类型 | 限制 |
|---|---|---|
| research_question | string | 1项，建议≤100个中文字符 |
| motivation | string | 1项，建议≤100个中文字符 |
| method_summary | string | 1项，建议≤120个中文字符 |
| contributions | string[] | 最多3项，每项建议≤60字 |
| main_findings | string[] | 最多3项，每项建议≤60字 |
| limitations | string[] | 最多2项，每项建议≤60字 |

信息不足时数组返回空数组，不得编造。

## Graph Node
| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 当前响应内唯一 ID，例如 n1 |
| type | enum | RESEARCH_QUESTION / CONCEPT / METHOD / CONTRIBUTION / FINDING |
| label_zh | string | 简短中文标签，建议2–16字 |
| label_en | string/null | 原文英文术语；无对应术语时 null |
| description_zh | string | 中文说明，建议15–60字 |
| basis | enum | EXPLICIT / INFERRED |

不设置 confidence、evidence、citations、quotes、page、source_span 等字段。

## Graph Edge
| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 当前响应内唯一 ID，例如 e1 |
| source | string | 必须引用存在的 node.id |
| target | string | 必须引用存在的 node.id |
| type | enum | INVESTIGATES / USES / ANALYZES / YIELDS / CONTRIBUTES_TO / RELATED_TO |
| basis | enum | EXPLICIT / INFERRED |

## 数量约束
- nodes：0–12；推荐6–12，但允许更少。
- edges：0–16。
- 不得有空标签、重复节点、自环或重复边。
- 图谱应稀疏、可读，不追求最大连通度。
- 输入材料不足时允许空图，由后端计算 `graph_status=NOT_ENOUGH_INFO`。

## 关系端点约束
- INVESTIGATES：RESEARCH_QUESTION → CONCEPT。
- USES：RESEARCH_QUESTION → METHOD。
- ANALYZES：METHOD → CONCEPT。
- YIELDS：METHOD → FINDING。
- CONTRIBUTES_TO：FINDING → CONTRIBUTION。
- RELATED_TO：允许任意不同类型节点，仅在无更具体关系时使用。

## Basis 语义
- EXPLICIT：论文输入文本明确陈述该概念/关系。
- INFERRED：模型为组织知识而归纳的关系或表述。
这不是置信度评分；EXPLICIT 不代表科研结论已独立验证。

## ID 与持久化
LLM 返回局部 ID（n1、n2、e1）。后端校验后，根据 `paper_id + node.type + 规范化 label` 生成稳定节点 ID（例如 UUID5），再映射边端点。局部 ID 不作为跨版本稳定 ID。

## 禁止字段
LightGraph 节点或边不得包含：
evidence_id、evidence_refs、citation、citations、quote、quoted_text、page、page_number、source_span、start_offset、end_offset、confidence、confidence_score、x、y、position。
模型额外输出未知字段时拒绝或丢弃并记录 schema error，不调用 LLM 修复。
