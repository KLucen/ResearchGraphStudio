# Lite 模型配置

更新：2026-11-09（Asia/Shanghai）。Lite 默认本地解析，不调用模型。模型只在用户主动生成 PaperCard + LightGraph、章节导读或证据问答时使用。

模型配置位于“设置与诊断”。Provider 支持 OpenAI、兼容 HTTPS API 和 loopback 本地模型；API Key 只写入操作系统凭据存储，数据库保存随机引用。连接测试使用固定非论文文本，不代表科学质量验收。

每次主动调用都记录 Provider、模型、Prompt/Schema 版本、输入/输出/总 Token、调用次数、重试次数、缓存命中和费用状态。供应商没有返回 usage 或价格配置时保留 `unknown`，不会把缺失值写成零。缓存键必须同时绑定论文、PDF 哈希、输入哈希、Schema、Prompt、Provider 和模型。

LightGraph 使用补充规范中的 `PAPER_OVERVIEW_WITH_LIGHT_GRAPH_V1`，PaperCard 与概念图只发起一次联合请求。模型不得生成正式 ID、文件路径、数据库语句、Evidence 节点或段落证据引用；本地程序负责 Schema 校验、稳定 ID、缓存和布局保存。

旧版完整抽取、跨论文推理、Lint/Wiki 和旧 Query 配置已从 Lite 活跃入口移除。旧项目只能从备份分支恢复。
