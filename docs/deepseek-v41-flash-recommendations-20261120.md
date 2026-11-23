# DeepSeek V4.1 Flash 配置核验与建议

2026-11-21实现跟进：新文字任务默认按正文或公开推理增量重置无活动计时，不再以固定总时限切断持续生成。下表180秒现在推荐配合“按生成活动等待”，表示首段/后续无活动等待；旧已冻结任务和显式legacy保留原有总时限。见[活动等待修复](text-activity-timeout-verification-20261121.md)。

核验日期：2026-11-20（Asia/Shanghai）。本报告针对本机当前使用的火山方舟 **Agent Plan**：OpenAI 兼容协议、`https://ark.cn-beijing.volces.com/api/plan/v3`、`deepseek-v4.1-flash`。只读取公开官方文档及脱敏配置元数据；本轮真实模型请求为 **0**，没有修改用户模型配置或运行数据库。公开文档能力、软件声明、历史请求成功和真实科学质量分别记录。

## 当前配置和预算故障

当前用途共用的配置为 `reasoning_effort=max`、普通文本等待90秒，模型上下文和输出能力未声明。知识任务冻结的软件策略是输入48000、输出6000 Token、每次分析最多2请求。失败发生于本地容量预检：`KNOWLEDGE_INPUT_BUDGET_EXCEEDED`，尚未发送请求，也没有模型响应可恢复。

完整输入包含已解析原文、引文结构、输出 Schema 和指令，不能只按论文字数判断。该失败输入的原规划估算约73905 Token、完整请求估算约79268 Token，均超过48000。修复后的文字估算按ASCII约3字符/Token、非ASCII约2 Token/字符处理；这是保守估算，不是供应商 tokenizer 的精确计数。可以把单次输入预算改为96000或“无上限”，保存后按新策略重新生成；旧失败记录及旧冻结配置保持。

“无上限”只取消对应的软件预算：输入仍须容纳于真实模型上下文，输出仍受真实端点输出和剩余上下文约束；每次分析请求数无上限也不取消累计请求额度、实际候选范围、持久发送账本及失败后显式继续规则。该选项不授权无限格式修复或自动重发。

## 官方接口和模型身份

| 服务 | 官方 OpenAI 兼容 Base URL | 对应模型标识 | 本项目建议 |
| --- | --- | --- | --- |
| 火山 Agent Plan | `https://ark.cn-beijing.volces.com/api/plan/v3` | `deepseek-v4.1-flash` | 当前配置属于此项，保留该地址与套餐专属 Key。[S1][S2] |
| 火山 Coding Plan | `https://ark.cn-beijing.volces.com/api/coding/v3` | `deepseek-v4.1-flash` | 与 Agent Plan 是不同套餐，不能据模型同名互换地址或 Key。[S3] |
| 火山常规按量 API | `https://ark.cn-beijing.volces.com/api/v3` | 当前推荐版本 `deepseek-v4-1-flash-261017` | 属于独立常规 API；不为修复预算故障切换到此地址。[S4] |
| DeepSeek 官方 API | `https://api.deepseek.com` | `deepseek-flash`，文档列为 DeepSeek-V4.1-Flash-1017 | 与火山的别名、计费及参数行为分开。软件已有“DeepSeek”预设中的 `deepseek-chat` 不能视为本配置。[S8] |

`/api/plan/v3` 是官方当前 Agent Plan 地址，不是已确认废弃路径。更换地址不是本次预算错误的修复条件。官方对套餐使用范围、额度和账单的说明以各自控制台及套餐文档为准。

## 容量、JSON 和输入能力

火山 Agent Plan 概览明确为 `deepseek-v4.1-flash` 列出 **1024K上下文、384K最大输出**，并注明原生多模态视觉理解。[S2] 常规方舟模型列表将 `deepseek-v4-1-flash-261017` 列入视觉理解和结构化输出能力；专题文档说明 Chat API 的 `max_tokens` 同时计算思维链和最终回答，默认131072，不能把全部输出额度都当成最终 JSON 的可用长度。[S4][S5]

| 项目 | 已核验的文档结论 | 软件使用边界 |
| --- | --- | --- |
| 上下文 | 火山写1024K，也称1M。[S2][S5] | 本机容量数字尚未声明时，可在确认当前套餐模型后手填保守值1000000；这不是精确端点上限的实测值。 |
| 最大输出 | 火山写384K；DeepSeek官方参考明确384K为393216。[S2][S9] | 火山页面本次未给出对应精确整数。建议手填保守值384000；不能把DeepSeek官方精确值当成火山该端点已实测结果。 |
| JSON | 方舟当前模型列表列出结构化输出；通用文档定义 `json_object` 与 `json_schema` 两种模式。[S5][S6] | 本项目此配置使用JSON模式时仍标 `json_object/requested`，并执行本机完整格式和来源校验；不宣称火山原生 strict Schema 已接入或验收。 |
| 图片 | Agent Plan明确原生视觉；方舟模型专题明确 Chat API 的 `image_url` 图片输入。[S2][S4] | 页面转图片的 `chat_images` 对应图片输入。勾选image/multimodal是用户声明，不能替代传输核验。 |
| PDF文件 | 方舟常规Chat API参考明确PDF的 `file` 对象支持 `file_id`、`file_data`、`file_url` 三选一；内联Base64使用 `file_data` 时须带 `filename`。文档理解指南另提供Files API上传后以file_id引用的示例。[S7][S10] | 本软件 `chat_file` 使用Chat Completions内联 `file_data` 与 `filename`，属于该常规Chat规范定义的形式。当前Agent Plan端点的套餐兼容及PDF科学质量仍须独立验证；image+multimodal+chat_file声明或历史个案成功不证明全部PDF效果。 |

知识建模和联系分析发送的是已解析文字材料，不会因选择这两个用途而重新发送PDF。因此，先修复知识输入预算不需要同时变更PDF解析方式。PDF解析可以按端点已确认能力选择 `chat_file`，或另建图片输入、多模态与 `chat_images` 配置，再按原有显式授权与分批流程使用；不因文档核验自动变更当前传输或历史任务。

## 当前软件中的推荐值

建议维护两个独立profile：一个用于带来源知识提取，另一个用于联系分析，避免为联系分析选择更强思考时同时改变精读、翻译或PDF解析新任务。

| 设置项 | 论文知识建模 `knowledge_extract` | 论文联系分析 `knowledge_connect` | 原因 |
| --- | --- | --- | --- |
| Base URL / model | 当前Agent Plan地址 / `deepseek-v4.1-flash` | 同左 | 保持套餐和模型身份。 |
| 推理强度 | `none` | 先用 `high`；疑难对比再显式选择 `max` | 文本提取重在忠实引用与格式，先减少思考开销；复杂关系分析可增加思考。`max`不是日常必要条件。 |
| JSON输出 | 开启 | 开启 | 本机仍必须校验字段、引文与来源，不把合法JSON当成内容正确。 |
| temperature / top_p | 留空 | 留空 | 使用该端点默认行为；不为格式修复叠加采样参数。 |
| 普通文字等待 | 活动策略，180秒无活动等待 | 活动策略，180秒无活动等待 | 持续正文或公开推理增量会续期；服务端隐藏思考不可观察，纯心跳不续期。 |
| 文档等待 / 解析总时限 | 若另用PDF解析profile，600 / 1800秒 | 若另用PDF解析profile，600 / 1800秒 | 只影响文档HTTP请求，不延长知识建模等普通文字请求。 |
| 模型上下文声明 | 确认套餐后可填1000000 | 同左 | 保守容量声明，不从模型名称自动登记，不与真实usage混淆。 |
| 模型最大输出能力声明 | 确认套餐后可填384000 | 同左 | 描述端点能力；与下方当次任务软件预算分开。 |
| 单次输入Token预算 | 本次材料96000可用；长论文选“无上限” | 96000起；大范围比较按材料选择“无上限” | 48000不足以容纳已观察到的完整请求；“无上限”保留真实模型容量检查。 |
| 单次输出Token预算 | 先选16000；希望由端点决定时选“无上限” | 先选16000；`max`或长汇报可提高到32000或“无上限” | 6000对带引文结构及思考输出可能偏紧；这些是起始策略，未经真实质量验收。 |
| 每次分析最多请求数 | 该项约束联系分析；不扩展单次提取失败重发权限 | 建议“无上限”，或按本次候选版本对数设置明确值 | 多候选比较可能需要多个请求，原2请求会提早停止；已成功版本对继续复用。 |
| 累计请求预算 | 保留默认20，按预计工作量调整 | 与建模共用累计额度 | 三项“无上限”不取消累计额度；清理内容不返还已发请求。 |
| 候选论文上限 | 不适用 | 先保留默认8篇 | 先观察报告相关性，再扩大比较范围。 |

方舟 Chat API明确 `reasoning_effort` 使用顶层字段，支持 `none/low/high/max`，其中 `none` 关闭思考；`minimal`映射low、`medium/xhigh`映射high。[S4] 此语义不能套用代码中另行登记的Tencent请求变换。当前火山profile已保存的 `max` 是显式值，不因本报告自动覆盖；保存推荐值仅作用于后续新任务，旧失败/raw/历史快照保持。

本轮没有为火山新增厂商专用运行适配器，没有自动改用户profile、密钥或输入能力。旧固定策略中，普通等待设180秒时整个文字请求总时限为300秒；2026-11-21新增的活动策略不使用此固定总时限，仍保留连接和无活动保护。两种文字策略均与文档解析600/1800秒设置独立。更大输出/更强思考之间仍可能有取舍；没有新增真实请求预算时，不以公开文档代替兼容性、延迟或科学质量实测。

## 官方来源

- [S1 Agent Plan接入其他工具](https://docs.volcengine.com/docs/ark/agent-plan-personal-other-tools?lang=zh)：`/api/plan/v3`、OpenAI兼容协议与套餐专属Key。
- [S2 Agent Plan套餐概览](https://docs.volcengine.com/docs/ark/agent-plan-personal-plan-overview?lang=zh)：模型别名、1024K/384K、视觉与套餐范围。
- [S3 Coding Plan接入其他工具](https://docs.volcengine.com/docs/ark/coding-plan-personal-ai-other-tools?lang=zh)：`/api/coding/v3`，与常规按量地址区别。
- [S4 方舟DeepSeek-V4.1-Flash（升级1017）](https://docs.volcengine.com/docs/ark/deepseek-v4-1-flash?lang=zh)：当前版本、图片输入、思考参数映射、输出含思维链及默认131072。
- [S5 方舟模型列表](https://docs.volcengine.com/docs/ark/model-list?lang=zh)：视觉理解、结构化输出能力和文档容量。
- [S6 方舟结构化输出(beta)](https://docs.volcengine.com/docs/ark/structured-output-beta?lang=zh)：JSON模式、输入必须包含JSON、模式与严格约束区别。
- [S7 方舟文档理解](https://docs.volcengine.com/docs/ark/document-understanding?lang=zh)：PDF输入、Chat的file_id与Responses的Base64示例。
- [S8 DeepSeek官方模型与价格](https://api-docs.deepseek.com/quick_start/pricing)：`deepseek-flash`当前版本及官方API身份。
- [S9 DeepSeek官方Chat Completion参考](https://api-docs.deepseek.com/api/create-chat-completion)：384K=393216、JSON模式和默认输出值；此处精确数字不作为火山端点实测。
- [S10 方舟Chat API参考](https://ark.volcengine.com/region:cn-beijing/docs/chat-api)：常规Chat的PDF文件对象支持file_id/file_data/file_url；使用file_data时filename必填。

所有来源为本轮可访问的公开页面。供应商可变更模型别名、容量和价格，实际以调用时端点及控制台为准；本报告不将文档声明记为本机验收通过。
