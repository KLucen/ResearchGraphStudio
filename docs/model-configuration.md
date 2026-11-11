# Lite 模型配置

更新：2026-11-11（Asia/Shanghai）。Lite 默认本地解析，不调用模型。模型只在用户主动生成 PaperCard + LightGraph、章节导读、证据问答或可选文献翻译时使用。

模型配置位于“设置与诊断”的“模型”板块。页面按提供商卡片展示连接，添加时可以选择 DeepSeek、OpenAI、OpenRouter、SiliconFlow、智谱 AI、通义千问和本机 Ollama 等兼容预设，也可以打开“自定义模型 API”填写 Provider ID、显示名称、Base URL、协议、API Key 和多个模型。当前运行引擎只实现 OpenAI Chat Completions 兼容路径；原生 Anthropic 等协议不在界面中宣称已支持。

一个提供商下可以维护多个模型 ID/显示名称，保存后作为现有 model profile 供论文概览、章节精读和论文问答分别选择。模型配置请求不会重复提交 Base URL 或 API Key。Provider ID 目前只用于本地界面标识，未进入数据库 Schema；若需要跨设备同步，后续再增加字段和迁移。API Key 只写入操作系统凭据存储，数据库保存随机引用。连接测试使用固定非论文文本，不代表科学质量验收。

每次主动调用都记录 Provider、模型、Prompt/Schema 版本、输入/输出/总 Token、调用次数、重试次数、缓存命中和费用状态。供应商没有返回 usage 或价格配置时保留 `unknown`，不会把缺失值写成零。缓存键必须同时绑定论文、PDF 哈希、输入哈希、Schema、Prompt、Provider 和模型。

LightGraph 使用补充规范中的 `PAPER_OVERVIEW_WITH_LIGHT_GRAPH_V1`，PaperCard 与概念图只发起一次联合请求。模型不得生成正式 ID、文件路径、数据库语句、Evidence 节点或段落证据引用；本地程序负责 Schema 校验、稳定 ID、缓存和布局保存。

旧版完整抽取、跨论文推理、Lint/Wiki 和旧 Query 配置已从 Lite 活跃入口移除。旧项目只能从备份分支恢复。

文献翻译直接选择上述已有 Profile，真实 Key 不交给外部排版服务。每个任务使用一次性本机模型代理，转发到冻结的兼容接口，并逐请求记录实际 usage。新建随包任务冻结 `translation_request_policy=text-chat-minimal-1`：复用连接、模型 ID、凭据引用、超时与已知输出能力，上游仅发送文本 `model/messages` 和受控输出上限，不转发阅读配置中的采样、思考参数或模型适配器附加字段，不修改所选 Profile。旧任务未记录该策略时，原参数行为及缓存身份保持；新策略进入缓存键，避免混用旧结果。

翻译不用结构化 JSON 输出、流式或工具调用。每请求最多 8192 输出 Token（已知能力更低时取低值），截断或上游失败会停止新请求，不静默重发。新版区分接口拒绝、鉴权失败、限流、响应截断与格式不兼容；缺失或未知结束状态不推断为成功。历史 `TRANSLATION_PROVIDER_FAILED` 不能反推出某个具体 HTTP 原因。审计仅保存请求字段名、哈希与输入字节估算，不保存正文、凭据或供应商错误正文。输入估算和请求数限制不等于供应商费用硬上限。具体使用方法及错误码见 [文献翻译](pdf-translation.md)，版本边界见 [ADR0039](adr/0039-translation-proxy-request-policy.md)。

翻译默认使用软件自带引擎，安装包包含 PDFMathTranslate-next 2.10.2、BabelDOC 0.7.1、独立 Python 和离线排版资源，无需再次配置 Server 或解释器路径。PDF 在本机处理，只有翻译文本和提示发送到所选模型 API。输出可选双语、中文或两种，新界面默认双语；输出格式参与缓存身份，旧未提供格式的记录继续按两种处理。

高级区域仍可使用独立外部环境的自动启停或手动服务。`lite0008` 升级前自动备份，未来任务默认使用随包引擎，旧外部路径和历史任务快照保留；无快照的旧任务按手动模式解释。预检、检查配置和缓存不启动引擎或发模型。随包资源和生命周期依据见 [ADR0038](adr/0038-bundled-translation-and-reading-layout.md)。本轮真实模型调用为 0；实际引擎合成联调、安装及真实翻译质量按进度分开记录。
