# 工程协作规则附录：阅读辅助知识图谱

2026-11-04最新R5三项补验收见[实际报告](r5-acceptance-verification-20261104.md)：当前模型两篇P13v3各1次成功，零重复P02/P12，再继续零调用；32无支持+2上标误读不进默认图、5重复组各1代表，新包隔离与用户三项反馈通过。partial/有限证据及strict/干净机/S1–S4限制保留，不自动追加付费调用。下方待复验为对应旧实现轮状态，当前以progress为准；P4/P5未开始。

当前R5协议见[ADR0021](adr/0021-keyed-ranking-and-bounded-correction.md)：新finish计划冻结P13_reading_ranking_v3/reading-ranking-keyed-1，程序固定assessments完整required短编号；模型仅填建议/理由/说明/0–100整数priority，程序降序，同分按冻结输入顺序。Schema/Prompt同源；合法外壳下有效槽位仅私有保留，定向修复未完成输出但保留完整上下文，最多两个持久请求槽位含超时，继续不重发。旧v1/v2计划/raw保持，旧排序失败独立续接并重验原P12谱系，零重复P02/P12。软件负责协议可靠性，不以换模型为前提，本轮无新增付费调用。

[ADR0020](adr/0020-evidence-aware-core-selection.md)的原文/疑点/数字排版风险、碎片核心门槛和成员caveats继续生效。32条语义无支持及2条上标误读本轮真实复验均不进默认图；这只是已知缺陷范围，不代表全局科学准确率。未新增审核、迁移或P4/P5，结果见[progress](progress.md)，历史[R5失败验收](r5-final-verification-20261103.md)不改写。

当前（2026-11-04）：R1–R4已接入，R5三项补验收范围内通过；head0011、领域reading-extraction-1.0、入口paper-reading-v1不变。结构解析与默认支撑展示见[ADR0014](adr/0014-structured-pdf-and-support-graph.md)，实测以[progress](progress.md)为准，未进入P4/P5。

本轮当前协议见 [ADR0017](adr/0017-semantic-protocol-and-stage-recovery.md)：新 P02v4 / reading-semantic-1 仅 items/links/warnings，程序绑定版本、批次、默认语言和短编号；semantic-reading-1 的 P12 仅语义边/重复提案，程序 form_units 取全部已验证路径，P13 仅贡献建议。旧冻结计划保持原协议与检查点，领域/head不变。本段覆盖下文历史协议描述的默认入口含义。

P12/P13 已按 [ADR0015](adr/0015-complete-reading-context.md) 去除软件字符/候选/窗口预算；新 complete-context-v1 全量整合与选择，旧窗口/签名/P13分组及成功检查点继续复用。真实端点能力、有界超时和严格来源校验保留，整合/选择失败不重抽全文。

现有根 AGENTS 优先，不整体替换。产品面向科研论文阅读，统一称知识图谱，无特定研究方向前置。

完整流程与后续任务见[开发计划](06_development_migration_plan.md)和[ADR0018](adr/0018-query-wiki-and-obsidian-lifecycle.md)：图谱组织结论/支撑路径，Query沿完整结构扩展并补原文/候选/有效Wiki/授权资料；明确保存新增衍生综合，可在独立图层显示，整理Wiki与导出MD分别明确。Wiki是版本化文档，私人Obsidian默认只读。Lint查来源/支撑/依赖/文件状态。画布分页/折叠不限制检索，旧Comparator固定限制不直接继承，普通执行/文件诊断不推进科学图修订。当前仍P3/R5；这些P4/P5任务未实现，模板不能视作启动授权。

- 一键自动构建：来源→候选→论文整合→核心选择→分层投影。无人工审核、待审队列、接受/驳回步骤。
- 完整保留原文/表格材料/证据定位/模型原输出；未选候选仍检索。Candidate/Unit/Selection 共用 KnowledgeStore。
- Paper 只直接连接核心 Claim，默认显示其有据方法/实验/条件/结果等非 Claim 支撑，可显式收起；来源关系不全部画线，共享节点不复制，不依共享证据猜边。
- 跨页章节树和表格表头/行列/单元格关系保存在 pdf-structure-1，References 保留但不抽取。所有章节用相同抽取规则，不强造实验；质量/归属/条件/限制必须明确。
- 新 validation/source/graph_role 分离；legacy_review_status 只保留旧数据，不新增审核流程；已有人工作品/状态不覆盖。
- 用户显示偏好不是科学审核，不能绕过来源门槛；Query/Wiki 是未来契约，保存/导出授权单独处理。
- 运行 0011/paper-reading-v1；0011 仅加 document_parses，原 Chunk/EvidenceSpan 不重写，旧库补解析需精确校验。新 P02_reading_extract_compact_v4 按完整章节及模型上下文容量规划，不设 6000 字符/48 证据目标；完整段落/表格组不可裁断。结构规则从实际输出 Schema 生成并核对 Prompt，身份由程序绑定，未知外壳字段拒绝。旧 v3/reading-compact-1 及更早签名/计划保留，独立升级遵循ADR0013，成功批次及可重验响应复用。
- Provider 新快照冻结 output_policy；strict 仅精确官方能力登记，兼容 JSON 是 requested，不自动收费探测或降级重发，未知 Schema 约束调用前拒绝。真实 strict API 未测须明示，文档支持不等于实测。
- 新响应与 received/succeeded/validation_failed 缓存共享完整终验；失败分类 protocol/schema/context/evidence，raw和审计保持。仅 response_invalid=true 更新 validation_failed/error/finished_at；可信来源/候选/快照变化为 false 时保留历史 status/error/finished_at，只记复用诊断并停止，不靠新调用修复。固定坏响应不能重复命中，Store 写入仍重验。
- 首次整合/排序失败且没有旧图时仅保守 provisional/pending/partial 视图，质量相关性 unresolved，不冒充完成核心排序；仅有效来源、明确作者归属、非背景/unknown/speculative、无issues且非重复代表的结论和合法支撑。已有图保留，来源/快照冲突不预览；无人工审核。
- 仅 Claim.kind_note_unused=null 可无损移除并审计，非 null/其他 kind/其他未知字段仍拒绝。原始模型输出不改，字段/来源验证和统一 Store 不省略。
- 历史 [ADR0016](adr/0016-selection-json-syntax-recovery.md) 仅在旧 P13 根末 coverage_gaps 是完整非空字符串列表、已有根 `}`、仅缺数组 `]` 时插入一个字符；正常及恢复都严格拒绝重复键/NaN/Infinity，不扩展为通用修复。其“其他阶段不变”为当轮范围，新语义P02/P12/P13同样严格解码但无此恢复。保留raw及规则/0起始字符位置/双hash，旧合法响应完整重验才复用，成功阶段不重调。新finish_reason记实际返回，历史未知不推断stop。
- 可按职责重构，不受最少改行限制；不重建工程/第二套知识库，不删除来源或私有材料。
- Conda researchgraph-studio；使用隔离数据做迁移和验收，参考测试不代替真实 API。按用户偏好减少 Computer Use。
- 每轮更新 progress/开发日志，记录实际命令/结果/未测；Commit/Push 前内容扫描，未获新授权不 Push。
