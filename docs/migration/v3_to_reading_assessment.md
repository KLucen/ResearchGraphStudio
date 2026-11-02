# v3 平铺图谱到阅读辅助分层图谱：工程映射

2026-11-02，设计 v3.3 / R0。本轮只读检查运行代码与既有测试记录，未启动用户库迁移或真实模型调用。

| 现有实现 | 可继承部分 | 缺口与下一步 |
| --- | --- | --- |
| [graph_projection.py](../../services/engine/researchgraph/graph_projection.py) | 类型过滤、分页、详情、布局上下文、来源/AI关系 | 每个 KnowledgeNode 补 REPORTS 线；新增基于选择版本和单元的投影，不在前端猜层级 |
| [unified_store.py](../../services/engine/researchgraph/unified_store.py) | 统一 Store、已有嵌套实验/条件/结果转领域对象、稳定 ID/依赖 | 复用已有对象，增加根/成员关系及质量/选择元数据；不复制候选内容 |
| [unified_contracts.py](../../services/engine/researchgraph/unified_contracts.py) | 当前严格 DTO、局部引用校验 | 新 reading union 与现有 unified-v3.1 独立适配，不能直接改旧响应消费者 |
| [unified_extraction.py](../../services/engine/researchgraph/unified_extraction.py) | 冻结计划、批次恢复、合法响应复用、超时拆分 | 添加整合/选择阶段检查点、候选快照签名和原子发布；旧任务原规则续跑 |
| [graph_models.py](../../services/engine/researchgraph/graph_models.py) | display、SourceAssertion、布局表 | 新增 unit versions/members、selection versions/entries/preferences 等；迁移号未决定 |
| [knowledge_store.py](../../services/engine/researchgraph/knowledge_store.py) | 事件、版本、幂等、来源保护 | 新操作仍统一入口；质量/成员/选择验证及状态变更同事务 |
| [ForceGraph.tsx](../../apps/desktop/src/ForceGraph.tsx) | 实时力导向、尺寸稳定、固定、相机 | 保留交互，增加展开单元/shared node 引用管理；无需重建渲染框架 |
| [KnowledgeReading.tsx](../../apps/desktop/src/KnowledgeReading.tsx) | 原文证据、模型记录、知识阅读 | 按问题/核心贡献/限制组织；新流程移除审核控件，旧记录仅历史 |

## 旧数据保护

Paper/AttachmentRevision/Chunk/EvidenceSpan 映射不变，知识 ID/既有原始输出/用户修改/历史审核记录保留。旧已接受语义不静默覆盖，旧驳回不被自动发布。旧布局按知识 ID 继承；隐藏和收起不删除位置。

已存在的条件/结果/实验不能再抽一遍建重复表。新 Argument/Limitation 或表格结构确实缺失时添加映射/记录；不能由旧文本自动宣称已精确重建。不存在单元的旧知识先保留检索，对足够来源内容再整合，不全量强制重抽。

## 版本迁移策略

建立新 pipeline 和 reference contract 的显式转换；运行 Prompt/DTO 版本冻结。R1 在独立备份测试，加性迁移并逐行比较旧列，保留恢复路径。R2–R4 分阶段接入，发布前旧有效视图可读；来源/用户显示偏好变化拒绝过期选择。

## 现阶段判断

P0–P2 继承；P3/v3 核心 M0–M5 已接入、M6 部分未验收。R0 是新的设计与参考契约交付，R1–R5 未实现。当前真实缩小批次仍超时，不能把新设计当成修复证明；真实跨论文科学关系边、干净机/安装执行等缺口仍保留。Query/Lint/Wiki 只预留接口。
