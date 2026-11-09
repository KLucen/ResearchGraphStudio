# 04. 存储、API 与缓存

## 存储原则
轻量图谱与旧版完整科研知识图谱隔离。不要覆盖旧版节点表或关系表。

### paper_overview_results
建议字段：
- id
- paper_id
- pdf_hash
- input_hash
- schema_version
- prompt_version
- provider_id
- model_id
- paper_card_json
- graph_json
- usage_json
- status（PENDING / COMPLETED / FAILED）
- created_at
- updated_at

### paper_graph_layouts
建议字段：
- id
- overview_result_id
- node_id
- x
- y
- pinned
- updated_at

布局表与模型语义结果分离。重新生成图谱时，稳定 node_id 仍存在则恢复位置。

## 缓存键
`hash(paper_id + pdf_hash + input_hash + schema_version + prompt_version + provider_id + model_id)`

缓存命中时直接返回 PaperCard + LightGraph，不调用模型。PDF内容、输入摘录、Prompt/Schema版本或模型标识变化时创建新结果版本，不覆盖旧版本。

## 后端接口建议
- `POST /papers/{paper_id}/overview/generate`：检查缓存；未命中时执行一次联合概览调用。
- `GET /papers/{paper_id}/overview`：返回最新卡片和图谱。
- `GET /papers/{paper_id}/overview/graph`：返回图谱节点和边。
- `PUT /papers/{paper_id}/overview/graph/layout`：保存拖动位置。
- `POST /papers/{paper_id}/overview/graph/layout/reset`：清除布局并重新计算。

实际路由应遵循现有工程风格，不要求机械照搬。

## 后端职责
1. 本地抽取概览输入片段。
2. 计算 input_hash 与 cache_key。
3. 命中缓存时不调用模型。
4. 未命中时只调用一次 `PAPER_OVERVIEW_WITH_LIGHT_GRAPH_V1`。
5. 校验 JSON Schema、数量限制、节点 ID、边端点和关系端点类型。
6. 确定性生成稳定节点 ID。
7. 保存 PaperCard、Graph 和 Token usage。
8. 前端布局单独持久化。

后端返回元数据：paper_id、overview_result_id、schema_version、prompt_version、generated_at、cache_hit、usage（input_tokens、output_tokens、total_tokens、cost 若 Provider 可得）。这些字段由后端生成，不让模型生成。
