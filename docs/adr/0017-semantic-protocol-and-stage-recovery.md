# ADR 0017：语义输出协议、程序组图与阶段恢复资格

日期：2026-11-03（Asia/Shanghai）。状态：本轮实现设计；实测及交付状态以 [progress](../progress.md) 为准。仍在 P3/R5，不进入 Query/Lint/Wiki。

## 背景

旧阅读协议要求模型回传文献版本、批次、修订号和根集合等程序已知信息。合法科学内容可能因这些重复外壳字段失败；P12 同时承担关系判断和单元枚举，P13 失败又可能让首次建图只剩论文节点。此前缓存资格部分仅校验 DTO，文献版本或根集合不符的 received 响应可能被反复复用。

目标是把程序能确定的身份、编号和拓扑交回程序，保留模型对科学内容、语义关系和贡献的判断职责。减少协议错误不能依靠放松领域 Schema、删除原文或无界重调模型。

## 版本边界

- 数据库 head 仍为 0011，本轮不新增迁移；候选领域仍为 reading-extraction-1.0，产品入口仍为 paper-reading-v1。
- 新 P02 为 P02_reading_extract_compact_v4，输出传输格式 reading-semantic-1；不覆盖旧 reading-compact-1 模板和任务。
- 新 finish plan 记录 flow_policy=semantic-reading-1、context_policy=complete-context-v1，使用 P12_reading_associations_v1 / P13_reading_ranking_v1。
- 旧任务已有计划、Prompt、Schema、输入、签名和检查点保持旧路径；普通继续是否创建独立兼容续接仍按 ADR0013。不能在旧 Job 中静默切换协议。

## 1. 模型只输出语义，程序绑定身份

新 P02 输出根只允许 items、links、warnings，其中 items/links 必须显式存在。模型不回传 document_version_id、chunk_id、contract_version、wire_format 或默认 source_language。程序从冻结的 transport_context 绑定版本、批次和默认语言，再展开到原领域 DTO；模型可对个别 SourceText 显式声明不同语言。原始 JSON 保留。

输入证据及跨候选引用使用请求内短编号，程序保存其到正式 ID 的双向约束清单。短编号不能跨请求解释，也不能成为正式数据库 ID。任何白名单外引用均失败，不猜测、修复或创建正式 ID。

科学字段与原有条件规则不变。原始同 local_ref 对象在默认值展开前先比较；只有原始 JSON 完全相同的重复候选才可在完整验证后去重，不能因补默认值把不同响应合成同一对象。结构规则片段由实际输出 Schema 生成，并核对运行 Prompt，避免提示与契约各自维护后漂移。

## 2. 冻结可核实的 Provider 输出策略

新模型快照包含 output_policy：版本 structured-output-1、端点、模型、mode、support、依据和原因。mode 为 native_json_schema / json_object / prompt，support 为 documented / requested / disabled。端点或模型改变后不得沿用不匹配的冻结策略。

原生 strict 仅对代码登记的官方精确端点和文档明确模型启用；当前是 https://api.openai.com/v1 与 gpt-4o-mini、gpt-4o-mini-2024-07-18、gpt-4o-2024-08-06。兼容接口的 json_object 只表示已请求 JSON，不宣称支持严格 Schema。既有思考模式冲突使用明确记录的 prompt 策略。

严格 API Schema 可作可证明的互斥 union/const 等价转换；可选字段要求出现时不能额外添加 null 以放宽领域。转换和源/请求 Schema 哈希记录审计，不支持的关键词在请求前失败。拒绝、能力错误或严格模式失败不会自动改模式发起额外收费请求；没有付费探测或自动降级。真实 strict API 效果尚待单独验收，文档能力不等于实测。

## 3. 程序形成单元，模型判断关联和贡献

新 P12 仅输出 associations、duplicates、warnings，引用候选/证据短编号。程序绑定内部版本和修订号；P12 不能改写候选正文、枚举正式单元 ID 或决定成员表。关联仍须通过端点类型、证据和来源验证；重复提案不能物理删除或合并不同条件/归属的知识。

KnowledgeStore.reading().form_units 从每个当前有来源的 Claim 及全部已验证有向支撑路径形成 KnowledgeUnit/ReadingMember。支撑范围不取决于模型是否重复抄全 member_ids；共享支撑仍引用同一知识。没有合法路径就没有支撑节点，不能按共用证据猜边。

新 P13 输出 ranked_claims、warnings：对所有给定 claim_ref 返回唯一贡献建议、理由和解释。程序恢复正式根、文献版本及快照修订，再执行质量门槛、密度、偏好和原子发布。排序不是科学真实性证明，也不是用户审核步骤。

新语义发布显式传入 contribution_order，必须唯一覆盖全部输入单元的根；快照保存该顺序，根条目与已选单元保存从 1 开始的 contribution_rank，筛选后保留相对贡献顺序。这是展示与建议顺序，不是科学置信度或力导向坐标。旧路径不传该可选字段时沿用原顺序与指纹；默认 ranked 也不额外加入旧指纹，避免历史成功检查点失配。

新任务继续使用完整候选/证据及全部单元上下文，没有固定软件字符数、候选数、窗口数或根数预算。实际端点容量、输出能力和有界请求时限保留；不能承诺所有论文一次请求完成。

## 4. 首次失败的保守临时视图

若新语义整合或排序失败且从未有可用图，可用已持久化且来源有效的候选及合法路径形成 provisional 阅读视图。只展示归属明确的论文作者 Claim，排除背景、unknown/speculative、已有重复代表或任何未解 issues；质量相关性仍为 unresolved，不把规则筛选标成完成贡献排序。没有符合门槛的结论时允许空视图并说明原因，不强造节点。

快照明确标 selection_mode=provisional、ranking_status=pending、build_state=partial，界面说明贡献排序未完成；失败任务仍可继续未完成阶段，不能显示全文建图成功。临时视图不是人工待审队列。已有可用图时失败保留旧图，不用临时视图覆盖；来源/候选快照过期时不得发布临时视图。后续成功发布使用 expected revision 保护显示偏好与版本。

投影中临时根的 graph_role=provisional，Paper→根使用 HAS_CANDIDATE_CLAIM（结论候选，排序未完成）；完成选择的根使用 core / HAS_CORE_CLAIM。根→支撑仍为 UNIT_MEMBER，支撑 graph_role=supporting。这些边均为导航，不是科学关系。GraphProjection.paper_builds 新增 ranking_status 与 selection_mode，契约兼容默认分别 unknown / ranked；已有有效历史选择缺少标记时按 complete / ranked 解释。失败任务的 pending 与保留旧图的完成状态分别呈现，不能由旧图推断新任务成功。

## 5. 新响应和缓存共用终验

reading_stage_validation.validate_stage 是无知识写入的终验入口。完成传输绑定后，统一检查 JSON/DTO、版本/批次/修订、候选及根白名单、原文锚点和当前快照；Store 实际写入时仍再次验证来源和引用。旧 P12 越界候选建议保留既有隔离规则，证据错误不能因隔离而伪装成功。

received、succeeded、validation_failed 缓存均不能仅凭状态复用。匹配输入、配置、Prompt/Schema 和清单后仍做终验。模型响应本身不合格（response_invalid=true）才更新 status=validation_failed、error 与 finished_at；stage_validation 审计记录 policy、protocol/schema/context/evidence 分类、code、response_invalid 及 input/raw 哈希，原始响应不改。无效固定响应不能无条件反复命中；可继续寻找更旧的合法响应或执行必要的新请求。

模型自己回错版本/根/证据属于 response_invalid=true；可信来源、候选或冻结快照变化属于 false。后者保留历史 ModelRun 的 status/error/finished_at，只追加或更新本次 stage_validation 复用诊断，停止并要求新构建；不能把原成功响应追记为坏响应，也不能靠再次收费解决。新旧合法响应及 ADR0016 限定的旧 P13 精确语法恢复仍可完整重验后零调用复用；成功 P02/P12/P13 检查点不重跑。

新语义协议严格拒绝重复键、NaN/Infinity 和未知外壳字段。ADR0016 的单字符 coverage_gaps 恢复仅保留在旧 P13 路径，不能扩成新协议的通用 JSON 修复。原 ModelRun、usage、供应商结束原因和恢复审计分别保留；没有历史 finish_reason 就保持未知。

## 6. 用持久化模型记录核算任务

新语义整合/排序阶段在成功与失败路径都从本 Job 的持久化 ModelRun 汇总实际记录。model_calls 只计 parameters.attempts 中的请求条目，usage 只汇总供应商提供的非负整数 prompt_tokens/completion_tokens/total_tokens/reasoning_tokens；失败阶段也纳入。缓存复用不虚构新请求或 Token。

历史或导入记录若缺少 attempts，计入 model_calls_unrecorded_runs，model_calls_status=known_attempts_only；全部有记录才为 recorded。缺失请求明细既不推定为一次调用，也不能证明零费用。cost=null、cost_status=provider_not_reported 继续表示供应商未提供费用；请求超时且无用量仍可能收费，不以图谱节点数或成功批次数估算费用。

## 影响与待验收

实现涉及 reading_transport、reading_prompt_contract、structured_output、reading_finish_wire、reading_finish_semantic、reading_stage_validation 及统一 Store/Provider/任务接入。没有新增数据库、人工审核或平行知识库，原始 PDF、Zotero 和个人笔记均只读。

必须分别验证协议/Schema 漂移、短编号绑定、来源冲突停止、全部已验证路径组单元、首次 provisional 与旧图保留、失败缓存重验及完整续接。合成测试、零网络响应回放、真实 API、科学质量、安装交互分别记录；本 ADR 不声明这些项目已通过。真实 strict、两篇全文新模板生成质量及用户安装反馈见实际进度和本轮报告。
