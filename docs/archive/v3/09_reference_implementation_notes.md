> 历史 v3 平铺图谱设计，已由当前 [阅读辅助设计](../../README.md)取代；不作为新实现要求。

# 09 — 对Codex的实现注记

## 实际编程时的代码层建议

```text
engine/researchgraph/
  sources/                 # existing Zotero adapter + parser
  extraction/              # combined P02, chunk planner, background P03/P04
  validation/              # Schema, evidence allow-list, exact spans
  knowledge/               # existing KnowledgeStore, Review, GraphRevision
  graph/projection.py      # Domain -> short GraphProjection
  graph/layouts.py         # only visual node positions/pinning
  reasoning/               # existing Phase 3 comparator/relation, reused
  jobs/                    # resumable batch state machine + outbox
  api/                     # existing routes extended, not duplicated
apps/desktop/src/
  features/graph/          # Canvas, Filter, Search, NodeInspector, EdgeInspector
  features/zotero/         # collection + attachment selection
  features/tasks/          # batch progress/resume/errors
```

以上只是职责说明。已有代码命名不同也可沿用，不要求按目录重构。

## 自动入图的正确实施界限

- 从`P02`得到的`KnowledgeExtractionBatch`先程序校验，然后映射到既有Domain模型，不把LLM的`local_ref`直接持久化为主键。
- 如果整体批次有个别坏条目，尽可能隔离坏条目并保存其余有效条目，但必须在引用合法、事务完整的前提下；不可把依赖坏条目的link写成悬空边。
- 只对`source_status=anchored`的来源知识默认展示；未锚定但有用的候选放诊断筛选。
- `ModelRun`保留Prompt/Schema/输入哈希，重试失败不丢失旧ModelRun，已提交批次不重复调用。
- 后端GraphProjection不保存原始证据全量文本，减少前端内存/隐私暴露；详情接口按点击加载。

## 视觉性能

- 对大型工作区默认从研究问题、Paper或Concept局部展开，按节点深度/类型限量加载，支持渐进添加。
- 力模拟运行时间有上限或当系统稳定后停止；双击固定后不受力场移动，拖动时其他节点继续响应。
- 布局变化只持久化UI偏好，不触发实体向量重算和Wiki更新。

## 真实模型验收材料

测试用户现有Zotero论文时，禁止将PDF与私人批注混入ZIP或Git仓库；测试记录用文献ID/Hash、模型/Prompt版本、耗时、Token、通过情况和错误类型。真实模型调用应先征得用户同意其请求内容与费用，未配置Key时只执行Mock路径。
