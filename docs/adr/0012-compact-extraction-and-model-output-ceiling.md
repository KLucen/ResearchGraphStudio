# ADR 0012：按模型输出能力请求与紧凑抽取格式

- 日期：2026-11-02（Asia/Shanghai）
- 状态：已实施；局部真实响应验证，全文待验收
- 范围：R5，不进入 P4/P5；领域 reading-extraction-1.0 / 数据库 0010 不变
- 后续决策：[ADR 0011](0011-tencent-streaming-and-reading-recovery.md) 的32K/64K额外预算和供应商专属续接按钮被本决策替代；原执行记录保留

## 问题

用户要求模型最大输出能力用于减少知识抽取失败，不需要“使用腾讯云适配继续”这一产品操作。上一轮虽然识别384K，仍额外设置32K/64K，未充分使用可用能力。旧Schema又让Claim/Finding/Experiment重复输出summary与statement/result/protocol，每个SourceText重复language；这些重复会增加生成量，但不增加证据。

本轮真实请求确认腾讯端点接受max_tokens=393216、thinking.disabled和SSE，完整返回而非截断。另发现Finding.baseline返回了纯文本，原对象形式校验失败；这属于结构表达差异，不能继续显示成Token不足。

## 决策

1. 删除第二层32K/64K固定限额。请求使用可信输出能力与扣除输入安全预留后上下文的较小值；当前端点的384K能力对应393216。更低端点元数据优先；未知能力仍使用供应商默认。最大值是允许额度，不要求模型用满，供应商计费以实际返回用量为准。保留连接/无响应/总时限、正文/传输大小及有限拆分边界。
2. 正常界面只有“继续未完成批次”。retry服务端在适用时创建原设计的独立续接任务，保留原Job、签名、成功操作键和调用历史；不让用户选择供应商修复策略。内部resume-adapted旧接口留兼容，前端不调用、不展示。明确设置的思考偏好仍不擅自覆盖。
3. 新任务采用独立Prompt `P02_reading_extract_compact` 和传输格式 `reading-compact-1`。领域contract_version仍为reading-extraction-1.0。传输Schema从领域Schema生成，只应用明确定义的格式变化；服务端展开后继续原有严格领域/证据/Store验证。
4. 顶层source_language表示共同原语言；SourceText省略language时精确继承该值，异种语言显式覆盖。SourceText可用非空字符串表示“该原语言的原文语义、无翻译”；仅Schema声明的SourceText字段允许这种转换，数字、额外字段或其他任意类型不转换。节点标签/主张仍优先生成有zh的对象，不额外调用翻译模型。
5. Claim/Finding/Experiment在summary与statement/result/protocol相同时可省略summary，由程序精确复制已有字段。不同摘要仍可显式保存；其他类型summary仍必填。不得删除条件、数值、否定、不确定性和证据来压缩响应。Prompt要求短标签、重要贡献及必要支撑，不填满配额或逐句建节点。
6. 不放宽extra=forbid或来源门槛。适配只处理上述确定性表示，记录字段路径和规则，不改原始ModelRun响应；重复检查继续比较原始wire对象，不能把不同原响应强行判为完全重复。非法关联沿用隔离规则，不能猜测修正科学关系。
7. 冻结计划选择自己的Prompt/Schema。已启动的旧P02保持原文件/哈希/领域验证；新紧凑模板和wire Schema加入构建签名、ModelRun schema_hash与reading_wire审计。旧任务不会为升级格式重复已提交批次；新/旧输出格式不能混用。普通续接可享受模型能力上限，但保留旧抽取格式。

## 边界与验证

finish_reason=length在Provider层明确归类output_limit，不能把半截JSON交给Schema后报泛化错误。若服务实际仍截断，沿用只拆未完成叶批、最多三层的恢复，不无限重发；更高上限不能保证网络不超时或模型永不输出错误字段。

真实2137字符/14证据小批请求输出额度393216、约27秒完整收到、10445 Tokens。第一次因baseline字符串校验失败，完善显式传输规则后用同响应零网络回放，12候选/10有效关联入Store，2关联隔离，396条旧知识逐行保持。原响应14968字节，领域展开19672字节，该样本减少约24%；不能宣称通用压缩率或全文质量通过。最终Prompt增加字符串格式说明后未再收费重跑；真实证据来自该已接收响应的最终校验。

自动化覆盖更高输出额度、较小端点/上下文优先、截断分类、语言/字符串/条件规则、未知字段拒绝、原响应审计、旧模板/重复恢复、普通续接UI和完整Store链路。详见[本轮验收](../archive/reports/compact-output-verification-20261102.md)。
