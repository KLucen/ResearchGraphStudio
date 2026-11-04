# 09 — 实施注记（设计 v3.3）

## 工程原则

按职责重构，以设计合理性和可测试性决定范围。保留有效解析、证据、来源、任务、凭据和 Store，不复制一个新系统；不以“最小侵入”阻止必要的抽取/整合/选择拆分。不要为改目录名搬动全工程。

建议职责：Source/Evidence → CandidateExtractor → PaperIntegrator → CoreSelector → GraphProjection；全部知识变更经 KnowledgeStore。共享工作流、模型记录、依赖和状态，不允许 UI/模型直接 SQL。

## 当前实现顺序

R1–R4 已接入，不重复实现。结构解析→支撑展示→限定 Schema 适配的前轮成果保留：PyMuPDF 产出 pdf-structure-1，0011 将解析产物保存在 document_parses，既有原文块和证据不改。本轮 [ADR0017](adr/0017-semantic-protocol-and-stage-recovery.md) 继续 R5：新 P02_compact_v4 / reading-semantic-1 按跨页章节输入，所有章节相同抽取规则，不采用 6000 字符/48 证据目标。容量或故障需要拆分时保持段落/表格组完整，旧冻结计划不重排。

reading_transport 处理严格语义外壳和程序身份绑定，reading_prompt_contract 生成 Schema 对应 Prompt 结构规则；structured_output 冻结 Provider 输出策略及可证明的请求 Schema 转换；reading_finish_wire/reading_finish_semantic 拆分语义提案、程序 form_units、贡献建议与失败预览；reading_stage_validation 统一新响应及缓存的只读终验。Store 仍是唯一知识写入口，领域仍1.0/head0011，无本轮迁移。

旧图谱 REPORTS 全连接只保留在旧视图兼容；新版投影基于 GraphSelection/KnowledgeUnit，不靠前端猜“哪个节点挂谁”。来源关系可检索，但不作为每个节点的默认可见边。

默认投影显示核心的有据方法、实验、条件、结果及其他非 Claim 支撑，可显式收起。旧快照漏列但存在合法有向关联的支撑可只读补全；不修改旧选择、不依共用证据猜边。Claim.kind_note_unused 只在精确 null 情形无损移除并审计，其他额外字段仍严格拒绝。相关版本和取舍见 [ADR0014](adr/0014-structured-pdf-and-support-graph.md)。

## 自动化边界

新流程不含人工审核服务/队列/状态迁移。语义风险自动隔离或带限制展示；用户显示偏好独立。旧审核与用户修改保留不可覆盖，不在新界面强制出现。JSON shape、白名单、类型、版本、引用闭合和事务属于代码；重要性/语义支持可模型辅助，但必须记录不确定性与实测质量。

## 成本与失败

已有合法模型输出复用；整合/选择按候选和版本缓存；仅必要证据片段外发。模型超时有界停止，未收到用量标未知。暂时无法整合的候选保留并可检索；不无限分裂批次或把不完整结果包装成全文成功。

received/succeeded/validation_failed 缓存同样完成 JSON/DTO、版本/根、白名单、证据和快照终验。固定坏响应记分类诊断后不可无条件重复复用；仅 response_invalid=true 更新 validation_failed/error/finished_at，可信来源或快照变化为 false 时保留历史 status/error/finished_at，只记本次复用诊断并停止，不通过再次收费解决。Provider strict 仅精确登记能力启用，兼容 JSON 为 requested，未知约束/能力冲突不自动降级重发。实际 strict 尚待真实调用验收。

新语义发布保存完整 contribution_order 及 1 起始 contribution_rank；旧路径未传时保持原指纹与顺序。任务统计从持久化 ModelRun.attempts/供应商 usage 汇总，失败阶段不漏计；缺请求明细单列未知，缓存不造调用，费用不推算为零。

## 数据与发布

源段落/表格材料/定位/ModelRun 不属于临时回收范围。结构解析只是恢复可确认布局，无 OCR，也不保证所有复杂表格/公式/双栏均正确；失败保留原材料并报告限制。选择快照以 expected revision 发布，源或用户偏好变化时拒绝过期提交；上一有效图保留。布局独立，详情按需加载，不把全部原文塞入图谱 API。

首次语义整合/排序失败时，没有旧图才允许保守 provisional 视图，明确 pending/partial 及相关性 unresolved；仅有效来源、明确作者归属、非背景/unknown/speculative、无 issues 且非重复代表的结论和合法支撑可展示。来源/快照冲突不发布预览，已有图不覆盖。任务仍保留失败与未完成阶段，不能把预览成功当核心贡献排序或全文生成通过。

## 验收与交付

Conda researchgraph-studio；单元/契约/数据库迁移/真实渲染与真实模型分别记录。优先自动化，按用户偏好提供操作步骤和安装包，由用户反馈原生体验；不频繁 Computer Use。未经执行的安装/调用不记通过；无需为本轮文档设计调用私人模型或改用户库。
