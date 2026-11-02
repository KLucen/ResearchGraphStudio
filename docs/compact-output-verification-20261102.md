# 输出额度、Schema精简与统一续接验收

日期：2026-11-02（Asia/Shanghai）。R5；保留当前未提交的全部既有成果，无迁移，正式库/来源PDF未修改。最新规则见 [ADR 0012](adr/0012-compact-extraction-and-model-output-ceiling.md)。

## 实际修改

- `model_adapters.py`：移除32K/64K第二层限制，使用Provider已核算的模型最大输出与上下文余量。当前腾讯模型可请求393216；低能力端点仍按其实际值，不普遍给所有模型套384K。
- `JobHistory.tsx` / `api.ts` / `app.py`：删除供应商专属按钮，统一“继续未完成批次”；后端选择兼容续接，原Job/签名/成功批次保留。旧resume-adapted路径仍是兼容接口。
- 新 `reading_wire.py` / `P02_reading_extract_compact.md`：新传输格式reading-compact-1，原领域reading-extraction-1.0不变。共同语言、可省略的相同摘要和明确的SourceText字符串形式减少重复；保留原语言、中文、条件、数值、归属和证据ID。旧Prompt/Schema不覆盖。
- `unified_extraction.py` / `reading_validation.py` / `extraction.py` / `providers.py`：按冻结计划选择新旧格式，展开后严格校验，通过同一KnowledgeStore保存；原输出不改、展开路径/规则单独审计，失败响应可重校验复用。正常产品入口仍没有Mock。
- 新 `test_reading_wire.py`，调整模型上限、普通续接和旧响应兼容测试；技术文档、进度和日志同步。未改图谱布局算法或知识数据库结构。

## 真实调用与失败后的零调用恢复

在已有一致性备份的独立副本进行，仅一次新生成请求，不重跑全文。使用原授权OS凭据，不在聊天/文档记录密钥或论文正文。

| 项目 | 实际结果 |
| --- | --- |
| 输入 | 原失败子批，2137字符、14证据 |
| 请求额度 | max_tokens=393216，端点接受；thinking.disabled、JSON、SSE |
| 首字节 / 响应完成 | 1.000秒 / 26.984秒 |
| 用量 | prompt5747、completion4698、total10445、reasoning0 |
| 初次结果 | 完整响应未截断；items.5.Finding.baseline为字符串，原对象验证报model_type |
| 最终校验 | 定义SourceText字符串简写后，原响应离线重验；新增网络调用0 |
| 候选与关联 | 12候选、10有效关联保存，2无效端点关联隔离；没有猜修关系 |
| 数据保留 | 396条原knowledge_nodes全列逐行不变，原ModelRun输出保留；SQLite完整性/外键通过 |
| 大小 | 紧凑响应14968字节，展开19672字节；该响应节省约24% |
| 请求Schema | 10419字节，原领域Schema11734字节；均为紧凑JSON字节，不冒充Token计数 |

费用供应商未返回，不记为0。最终Prompt增加字符串简写说明后未再调用真实服务，验证使用上述真实响应的本地重验；不能描述为最终Prompt重新生成成功，更不能当作两篇全文成功。私人副本/响应/报告只保存在 `.local/compact-output-20261102/`。

## 自动化与交付

- 专项回归首次50项通过；新增字符串/条件规则后 `test_reading_wire.py` 15项通过。包含旧P02冻结模板、已提交批次不重调、输出大于64K模拟、截断不进入Schema、来源/字段拒绝、审计与普通续接入口。
- 最终 `scripts/check-phase0.ps1`：**229 Python passed / 2 skipped、45 React passed**，Ruff/format/mypy（64文件）、pip check、OpenAPI/TypeScript导出、前端类型/lint/生产构建通过。两项文件链接主机条件跳过不计通过；既有Starlette弃用/前端单包体积警告保留。期间一次lint因说明字符串超过行宽未通过，已修正并完整重跑。
- 旧 `reading_contracts.py` 和 `P02_reading_extract.md` 无diff，未修改数据库迁移或Rust源码；本轮不将上一轮9项Rust单测和3项浏览器图谱测试冒充重跑。
- `scripts/build-windows.ps1`：PyInstaller/Tauri/NSIS通过；冻结引擎 `scripts/smoke-engine.py --executable ...` 的新紧凑合成阅读/Store/发布与重启回归通过。PowerShell5.1 `verify-windows-install.ps1 -EnginePath ...` 的5项引擎检查通过；设置RGS_TEST_ENGINE_PATH后 `cargo test ... packaged_engine_connects_through_native_host_and_restarts -- --ignored`：1 passed。
- 新安装器 `.local/releases/compact-extraction-20261102/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,557,759字节，SHA256 `b23c132f7c4833354ecb3141be3dd2ed513bf9746ff82907598f8e159b8bc109`。版本仍0.0.1，按路径/哈希区分。未覆盖安装或中断用户软件。
- `python scripts/check-sensitive.py --gitleaks .local/tools/gitleaks-8.30.1/gitleaks.exe`：479个源码候选文件的内容/私人路径/Gitleaks通过；diff检查通过，暂存区为空。私人库/响应/安装器均在忽略目录。
- 文档137份Markdown、491个可用本地链接、88项当前资产字节/哈希清单通过；4个登记外部来源不可用，单列为限制，未算通过。
- 未Commit/Push，未覆盖安装或用Computer Use操作用户窗口。

## 使用与未验收项

安装本轮包后，原任务使用普通“继续未完成批次”；已保存部分不重抽。新发起的抽取使用紧凑格式，已启动旧任务仍保留旧模板/签名，无需为此删除已有知识。新格式不自动改写原模型输出。

更大输出额度消除了应用额外32K/64K限制，但不能保证服务永不超时、截断或输出错误。两篇全文、最终Prompt的再次真实生成、完整图谱科学质量与用户安装反馈仍待验收；下一步继续R5，不进入P4/P5。四份外部原文登记路径不可用限制保持。
