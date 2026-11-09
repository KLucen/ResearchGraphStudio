# ResearchGraph Lite：轻量知识图谱补充规范（A+B+D Addendum）

本包只补充“论文概览中的轻量知识图谱”，不重复 ResearchGraph Lite 原有 A+B+D 产品设计、章节导读和按需问答规范。

## 适用范围
在既定 ResearchGraph Lite 中保留：
- A：章节级 AI 阅读导读
- B：论文知识卡片
- D：按需检索式论文问答

本补充将 B 扩展为：**论文概览 = 论文知识卡片 + 单篇论文轻量知识图谱**。

轻量图谱必须与论文卡片共用一次概览生成调用，不得再运行旧版完整 Knowledge Extraction / Knowledge Evolution 流水线。

## 文件
- `CODEX_LIGHT_GRAPH_ADDENDUM.md`：交给 Codex 的执行指令。
- `01_light_graph_product_spec.md`：功能边界和交互规格。
- `02_schema_and_validation.md`：数据结构、字段约束和校验规则。
- `03_prompt_design.md`：论文卡片与轻量图谱联合生成 Prompt。
- `04_storage_api_and_cache.md`：存储、接口、缓存和版本策略。
- `05_token_and_acceptance.md`：Token控制、测试和验收标准。
- `schemas/paper_overview_graph.schema.json`：JSON Schema。
- `examples/paper_overview_graph.example.json`：虚构示例数据。

## 与原 Lite 规范的关系
原 A+B+D 规范仍然是主规范。本包只覆盖轻量图谱，以及 B（论文概览）与图谱的联合输出。若两份规范有冲突，以以下原则为准：
1. 选择论文和本地解析阶段默认 0 LLM 调用。
2. 用户主动生成论文概览时，一次调用同时生成 PaperCard 和 LightGraph。
3. 不生成证据节点、段落引用、页码定位或 Evidence Trace。
4. 不进行跨论文实体融合、条件化推理、冲突判断、Lint 或 Wiki 自动演化。
5. 保留 AI 生成状态，不能把概念关系图包装成经验证的科研证据网络。
