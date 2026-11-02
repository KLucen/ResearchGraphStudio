# ADR 0008：面向论文阅读的自动选择与结论分层知识图谱

日期：2026-11-02（Asia/Shanghai）。状态：**设计采用，运行实现待 R1–R5**。本次用户要求重设计 Schema/Prompt/文档，并追加“流程不需要人工审核”。继承 [ADR 0007](0007-extraction-null-markers-and-timeout-adaptation.md)的数据保留与恢复边界，替代 ADR 0004 中“通过基础校验即全部进入默认投影”的目标规则。

## 问题与决策依据

当前 graph_projection.py 为每个可见 KnowledgeNode 生成 Paper→节点的 REPORTS 边，主要反映来源归属。统一抽取已经保存实验/条件/结果，但缺少论文级核心选择和结论单元，因此图谱容易平铺且无法表达贡献与依据的层次。

用户明确产品是通用科研论文阅读辅助工具，称“知识图谱”，无需预设具体研究方向。仍保留选择论文直接生成图谱的操作流程，不要求用户先审核候选。

## 采用的设计

1. 来源/证据、结构化候选、默认图谱三种职责共用 KnowledgeStore。原文段落/表格材料/定位/模型原始输出保留；完整原文不等于逐句建节点。
2. 自动管线为 indexing → extracting → integrating → selecting → publishing，候选经过来源、相关性、证据完整性和重复检查后才选入默认图。无人工审核、待审队列或接受/驳回步骤。
3. KnowledgeUnit 以一个 Claim 为根，关联多个支撑对象；成员可共享，正式内容仍只有一份。默认 Paper→核心 Claim；展开后 Claim→支撑。来源归属仍可查但不全部画线。导航边不是科学论证边。
4. 论文类型采用 empirical/methodological/theoretical/review/mixed/unknown，条件维度开放。核心 Claim 可表达实验结果、方法贡献、理论结论、综述综合或重要限制，不强造实验。
5. 核心选择是“质量门槛 + 贡献相关性 + 覆盖/重复检查”；P12 负责关联/去重建议，P13 负责关键性建议，程序验证与发布。未选择内容继续检索，错误/缺证据响应隔离诊断，不无条件作为回答依据。
6. 新状态分 validation_status、source_status、graph_role；legacy_review_status 仅保存旧数据。历史用户修改/接受/驳回记录不可覆盖；新流程不生成审核任务。SelectionPreference 只控制显示，不能绕过来源门槛。
7. knowledge/selection/layout revision 独立。候选、整合与选择各有检查点；失败保留成功阶段和旧有效图；选择快照完整验证后原子切换。更换密度或显示偏好通常不重抽论文。
8. Query 未来检索完整 Store/证据，Wiki 未来使用逐段版本依赖和来源引用；主图未选不等于不能检索，核心不等于事实认证。查询保存和文件导出是授权写入，不是科学审核。

## 契约与成本

设计版本 v3.3；参考 DTO reading-extraction-1.0、reading-integration-1.0、reading-selection-1.0、reading-projection-2.0。运行 DTO unified-v3.1、P02 3.2、Alembic 0009 不改。旧 Prompt/签名和原输出保留，新版本经明确适配接入。

新候选采用显式 discriminated union，Finding/Condition 等不再靠自由字段嵌套；SourceText 保留原语言及可空中文。JSON Schema 的体积/厂商支持需真实模型验证，不能认为参考结构会自动降低 Token 或超时。P12/P13 使用已保存候选和必要证据、有界调用与缓存，不机械增加每批调用。

## 迁移与取舍

允许按职责重构，工程目标为合理、实用、可测，不以修改行数最少为约束。仍保留现有有效工程与用户数据，不重建知识库。旧来源/节点/依赖/模型/审核记录映射保留；单元和选择作为新增关系，缺失关联保守留检索，不能假造或自动全量重抽。

风险：选择可能遗漏贡献，整合可能错配条件，论文类型识别可能不准，共享节点布局复杂，模型调用成本可能增加。对策为覆盖缺口、可解释选择、完整候选检索、严格版本/来源/路径验证、自动失败保留及跨论文类型真实评价。本次参考测试不能替代应用或模型验收。

阶段与交付见 [迁移计划](../06_development_migration_plan.md)及[本轮规范验证](../reading-design-verification-20261102.md)。不进入 P4/P5。
