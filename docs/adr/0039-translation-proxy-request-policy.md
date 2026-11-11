# ADR0039：翻译文本请求策略与可区分的代理错误

日期：2026-11-11（Asia/Shanghai）

状态：已采纳；真实模型调用为 0，实际回归、安装包与原生反馈以 [开发进度](../progress.md) 为准。

## 背景

用户开始翻译后看到“模型代理预算或请求校验失败，后续请求已阻断”。本次可确认的历史错误码为 `TRANSLATION_PROVIDER_FAILED`。旧实现将预算、请求协议、来源和上游模型失败合并为同一条提示，且供应商 HTTP 失败、截断、非法响应等都可能归入一般错误；现存历史信息不足以还原这次请求的准确 HTTP 或响应原因，不能把参数兼容性假设写为已证明的 HTTP 400 根因。

另一个可由代码确认的兼容风险是：随包 CLI 已关闭温度和思考参数，但本机代理会重新加入阅读 Profile 中的 `temperature`、`top_p`、`reasoning_effort` 及模型适配字段。翻译任务不需要这些阅读参数，部分兼容接口可能拒绝它们。修复需要同时收窄新任务的上游字段并提高失败可诊断性，保留旧任务冻结语义。

## 决策

### 新随包任务冻结独立请求策略

新建 `bundled` 任务在 `model_snapshot` 中冻结 `translation_request_policy=text-chat-minimal-1`。执行器只依据快照决定 `forward_parameters`，不会根据当前全局设置反向改变已排队任务。该策略复用冻结连接、模型、凭据引用、超时与已知输出能力，上游仅发送文本 `model/messages` 和程序控制的输出上限。阅读配置中的采样参数、思考强度及模型适配器附加字段不加入这些请求，原 Profile 和冻结参数原文仍保留。

输出上限保持最多 8192 Token，已知能力更低时取更低值。该上限与累计 UTF-8 输入字节估算、请求数守卫共同约束调用；它们不是供应商费用硬上限。预检、缓存命中、历史读取与本地 PDF 解析仍为零模型调用。

### 旧身份与缓存版本边界

仅当快照已含 `translation_request_policy` 时，`_identity` 才把同名字段加入身份 payload。新策略结果与旧参数行为的结果使用不同缓存键。已有无该字段的任务保持原快照、参数转发及原身份算法，不补字段、不重算或重写历史缓存键；`manual/managed` 新任务仍使用其原参数策略。此变更无数据库迁移，Alembic head 继续为 `lite0008`。

### 受控 SDK 兼容与字段审计

入站仍要求冻结模型和纯文本 `system/user/assistant` 消息。对 SDK 可能发送的 `max_tokens`、`max_completion_tokens`、`temperature`、`top_p`、`reasoning_effort`、`stream=false`、空或 null `extra_body` 进行类型和值域校验，再按冻结策略重建上游请求；入站值不能覆盖模型、冻结参数或输出上限。流式、结构化输出、工具、图像、非空 `extra_body` 及未知字段继续拒绝。非法请求撤销票据，SDK 不能通过后续重试触发新的收费调用。

代理在内存中只记录入站顶层字段名；用量账本的 `extra.request_fields` 保存实际上游请求字段名，并保留既有请求哈希、输入字节估算和估算策略。正文、请求头、真实 Key、临时票据、供应商错误正文及隐藏推理不进入这些诊断材料。字段名审计用于观察请求形状，不声称能够补回旧失败的供应商错误详情。

### 根据可观测结果分类失败

| 条件                                         | 错误码                                  |
| -------------------------------------------- | --------------------------------------- |
| 请求数或输入估算超限                         | `TRANSLATION_BUDGET_EXCEEDED`           |
| 入站文本请求协议不合法                       | `TRANSLATION_TEXT_ONLY`                 |
| 上游 HTTP 401/403                            | `TRANSLATION_PROVIDER_AUTH_FAILED`      |
| 上游 HTTP 429                                | `TRANSLATION_PROVIDER_RATE_LIMITED`     |
| 其他上游 HTTP 4xx                            | `TRANSLATION_PROVIDER_REQUEST_REJECTED` |
| `finish_reason=length`                       | `TRANSLATION_PROVIDER_TRUNCATED`        |
| 非法 JSON、choices、非文本内容或未知结束状态 | `TRANSLATION_PROVIDER_RESPONSE_INVALID` |
| 网络、服务端及其他未细分失败                 | `TRANSLATION_PROVIDER_FAILED`           |

响应仍要求恰有一个 choice、明确 `finish_reason=stop` 和非空文本，工具响应拒绝；缺失、null 或未知结束状态不会补成 `stop`。截断与非法响应不发布译文。失败或取消撤销任务票据、阻断后续请求，不自动降级或重新收费；已经收到的合法 usage 保留，没有 usage 继续记未知。界面与任务记录按具体代码显示提示，不再统一误称预算或请求校验失败。

## 验证边界

自动化使用匿名合成 PDF、loopback 代理和合成 Provider，覆盖新旧身份及参数策略、SDK 兼容字段、预算/HTTP/截断/非法响应、脱敏、用量保留、失败不发布和重复执行不重发。真实模型调用与真实输入/输出 Token 为 **0**。合成用量仅为夹具，不代表供应商计量或真实翻译质量；准确测试数量、实际随包 CLI 和隔离安装结果由 [开发进度](../progress.md) 记录。

本决策增量补充 [ADR0038](0038-bundled-translation-and-reading-layout.md)，不改变默认随包运行时、输出格式、本机 PDF 处理或原文保留边界。使用及错误处理见 [文献翻译](../pdf-translation.md)。
