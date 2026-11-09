# Contract Test Checklist

1. schema_version 必须为 `paper_overview_graph.v1`。
2. PaperCard 必需字段完整；数组最大数量符合约束。
3. graph.nodes <= 12，graph.edges <= 16。
4. 节点 ID 唯一，边 ID 唯一。
5. 所有边端点必须存在，且 source != target。
6. 每个关系类型的 source/target 节点类型符合 02_schema_and_validation.md。
7. 同一 source + target + type 不重复。
8. LightGraph 模型输出禁止 evidence/citation/page/quote/source_span/confidence/x/y。
9. 相同缓存键二次请求必须命中缓存，模型调用数为 0。
10. 布局坐标仅保存在布局存储，不进入模型语义 JSON。
11. EXPLICIT 和 INFERRED 在 UI 中有不同标识。
12. 旧版图谱数据与轻量图谱版本隔离。
