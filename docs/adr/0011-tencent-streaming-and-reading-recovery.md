# ADR 0011：腾讯云 DeepSeek 流式适配与阅读恢复

- 日期：2026-11-02（Asia/Shanghai）
- 状态：已实施；单个真实失败子批通过，全文与用户安装反馈待验收
- 范围：R5 响应可靠性；不进入 P4/P5，无数据库迁移，head 0010

后续修订：[ADR0012](0012-compact-extraction-and-model-output-ceiling.md)已替代下述32K/64K额外预算与供应商专属界面操作；当前使用模型最大能力和普通继续入口。本文件保留原决策及当轮实测。

## 问题与依据

用户使用腾讯云 Token Plan 企业版的 `deepseek-v4.1-flash`。隔离快照中的新阅读任务分别保存 6/12、4/35 批，尚无 ReadingUnit/GraphSelection，默认主图只有论文节点；两篇已有 206/190 条候选或历史知识，并未丢失。

失败请求约 0.08 秒完成发送，非流式响应等待 90 秒超时；2137 字符/14 证据的子批仍超时。另一个成功小批的 completion_tokens=12136，其中 reasoning_tokens=10303，说明缩小原文未消除默认思考的生成耗时。

2026-11-02 核对用户提供的[Token Plan](https://www.tencentcloud.com/zh/document/product/1300/81489)，以及腾讯云[模型规格](https://www.tencentcloud.com/zh/document/product/1300/78934)、[DeepSeek 指南](https://www.tencentcloud.com/zh/document/product/1300/80633)、[Chat 接口](https://www.tencentcloud.com/zh/document/product/1300/82345)：该模型上下文/最大输入为 1M，最大输出 384K；默认 thinking.enabled/high，不建议同时启用 thinking 和 JSON mode，推荐流式请求。DeepSeek [Chat 文档](https://api-docs.deepseek.com/api/create-chat-completion)明确 384K=393216。128K/256K 不能作为当前供应商该模型最大能力的二选一答案。

## 决策

1. **精确供应商适配**：仅对已登记腾讯云 TokenHub HTTPS 主机、`/plan/v3` 或 `/v1` 和两个精确模型 ID（基础名、`-1017`）生效。同名模型在其他服务不套用这些能力。`/models` 返回的有效字段优先，缺失字段才用版本化文档兜底；上下文按保守十进制 1,000,000 预留，输出上限 393216，记录能力来源。
2. **最大能力与任务预算分离**：不恢复手动最大输出框。新 Extraction 默认 `thinking.disabled` + JSON，自动预算 32768；Reasoning 默认 thinking.high，预算 65536，不同时发送 JSON response_format。显式 effort 优先，low/medium 对应 high、xhigh/max 对应 max；本地严格 JSON/Schema/证据验证不变。预算不超过端点有效上限及剩余上下文，不宣称每次调用都需使用 384K。
3. **流式传输**：发送 `stream=true` 与 include_usage，兼容供应商直接返回完整 JSON。增量 UTF-8/SSE 组装，区分 content 和 reasoning，仅记录思考字符计数。结束标记和 finish_reason 必须有效，半截 JSON 不入图；中途断流不自动重发，安全 partial 留在 ModelRun。传输最多 32 MB，保留正文最多 2 MB，避免每 Token 的 SSE 信封开销误占正文预算。
4. **有界等待**：连接最多 15 秒；无数据超时仍取设置值 5–180 秒；总时限为两倍、最多 300 秒，持续心跳不能无限延长。任务外层另留 5 秒收尾，连接测试原生桥最多 310 秒。响应超时仍只允许一次根批二分，子批再超时停止；不无限增大 timeout 或重试次数。数字型活动每约 2 秒更新，包含首/末字节、等待时间、内容/思考字符数；不把生成中显示为成功。
5. **显式续接旧任务**：普通重试仍冻结原配置。只有已停止、尚未进入 P12/P13、保存了签名/计划、原 effort 未指定且准确匹配腾讯适配的 reading 任务，提供“使用腾讯云适配继续”。创建确定 ID 的新续接 Job，保留原 Job、原模型快照、Prompt/Schema、签名、配置键和叶批账本，先校验签名/证据再应用独立 `resume_adapter`。已提交 KnowledgeOperation 直接复用，只有未完成批次采用新策略；每次 ModelRun 记录有效参数，续接任务独立统计调用用量。重复点击返回同一续接任务；同文献仍有活动任务则拒绝。不能借此更换模型、端点、原文或覆盖显式思考偏好。
6. **明确空图含义**：投影和选择接口返回已保存候选/历史知识数量、已发布单元、最新抽取进度/状态。无选择时主图解释尚未整合，并提供候选入口。任务停止后，用户可明确启动“基于已保存候选生成部分图谱”，仅执行 P12/P13，覆盖缺口包含 6/12 等实际进度，发布状态必须 partial。活动任务/无候选不能首次整合，不自动继续收费，也不将所有候选直接冒充核心结论。

## 数据与兼容

所有知识继续通过 KnowledgeStore，未删除、重置或迁移正式库，原始 PDF/证据/模型输出保留。旧成功批次不重复调用；原始模型结果与规范化审计分开。SSE 只接收文本，无 SQL/Shell/文件工具。密钥使用 OS 凭据，URL 不跟随跳转；不将模型原文、私人题名或密钥写入开发文档。

新接口字段向后兼容，原 retry/cancel 不变。普通旧任务可使用流式传输和能力发现，但不会静默注入新的 thinking 策略；显式续接具有独立任务身份和参数审计。未实现单次全文抽取，也未改变已保存分块计划。

## 验证与局限

真实腾讯请求仅一次，在隔离库成功抽取原失败子批：9.531 秒、4 候选/2 关联、7541 Tokens、reasoning_tokens=0；原 396 条知识逐行保持。该结果随后零网络回放到真实冻结任务的续接副本，6/12→7/12，验证已保存批次跳过与原签名保持。

SSE 边界、密钥跨分片、心跳总时限、能力混合、续接幂等/拒绝、部分图覆盖缺口及前端状态均有测试。完整结果与新安装器见[本轮报告](../tencent-recovery-verification-20261102.md)。真实 P12/P13 部分建图、两个完整论文以及用户原生安装尚未验证；不得用 Mock 或单批成绩替代全文科学质量验收。
