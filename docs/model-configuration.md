# Lite 模型配置

更新：2026-11-12（Asia/Shanghai）。Lite 默认本地解析，不调用模型。模型只在用户主动生成 PaperCard + LightGraph、章节导读、证据问答或明确启用英文关键词辅助时使用。

模型配置位于“设置与诊断”的“模型”板块。页面按提供商卡片展示连接，添加时可以选择 DeepSeek、OpenAI、OpenRouter、SiliconFlow、智谱 AI、通义千问和本机 Ollama 等兼容预设，也可以打开“自定义模型 API”填写 Provider ID、显示名称、Base URL、协议、API Key 和多个模型。当前运行引擎只实现 OpenAI Chat Completions 兼容路径；原生 Anthropic 等协议不在界面中宣称已支持。

一个提供商下可以维护多个模型 ID/显示名称，保存后作为现有 model profile 供论文概览、章节精读和论文问答分别选择。模型配置请求不会重复提交 Base URL 或 API Key。Provider ID 目前只用于本地界面标识，未进入数据库 Schema；若需要跨设备同步，后续再增加字段和迁移。API Key 只写入操作系统凭据存储，数据库保存随机引用。连接测试使用固定非论文文本，不代表科学质量验收。

每次主动调用都记录 Provider、模型、Prompt/Schema 版本、输入/输出/总 Token、调用次数、重试次数、缓存命中和费用状态。供应商没有返回 usage 或价格配置时保留 `unknown`，不会把缺失值写成零。缓存键必须同时绑定论文、PDF 哈希、输入哈希、Schema、Prompt、Provider 和模型。

LightGraph 使用补充规范中的 `PAPER_OVERVIEW_WITH_LIGHT_GRAPH_V1`，PaperCard 与概念图只发起一次联合请求。模型不得生成正式 ID、文件路径、数据库语句、Evidence 节点或段落证据引用；本地程序负责 Schema 校验、稳定 ID、缓存和布局保存。

旧版完整抽取、跨论文推理、Lint/Wiki 和旧 Query 配置已从 Lite 活跃入口移除。旧项目只能从备份分支恢复。

文献翻译已于 2026-11-12 按用户要求撤下，设置中不再提供翻译运行环境或模型代理配置。已有模型连接、Profile、API Key 引用与其他阅读功能继续使用；历史翻译用量记录保留，供应商未返回的 usage 或费用仍为 `unknown`。保留 `lite0008` 迁移链以兼容已有数据库，不执行降级、数据删除或旧翻译任务重放。详见 [ADR0040](adr/0040-remove-pdf-translation.md) 与 [撤下说明](pdf-translation.md)。
