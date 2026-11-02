# 阅读抽取重复响应与批次状态验收

日期：2026-11-02（Asia/Shanghai）。范围：R5 响应可靠性，未进入 P4/P5。工作区从 3d8b4ed 继续，未变更数据库 head 0010、运行 Prompt/Schema 或冻结任务计划。

## 实际故障

- 用户报告的“batch(value_error)”来自 27 页论文的新阅读任务首批：28 个候选中 8 个完整 JSON 重复，20 个唯一候选，24 个关联。错误实际为 duplicate references，不是 PDF 不可读或本批 Token 截断。
- 该批响应 22,434 字符；供应商返回 prompt_tokens=8,404、completion_tokens=12,916、total_tokens=21,320，其中 reasoning_tokens=6,919 已含在 completion_tokens 中。不重复累计思考用量，不推断供应商未报告的费用。
- 另一篇 9 页论文快照时已保存 3/10 子批。原先 8 批，两个根批等待响应超时（90 秒）后各二分，成功子批显示“完成（超时后缩小）”。这是快照状态，不能作为任务当前进度；分裂保留全部证据，未截掉后半内容。
- 两篇保存的原文约 42,733 / 161,379 字符、159 / 775 个 EvidenceSpan。当前 6000 字符/48 证据策略会产生较多批次；模型能力探测未得到可信 context_window 或 max_output_tokens，使用供应商默认。

## 修复与保护边界

具体规则见 [ADR 0010](adr/0010-reading-response-deduplication.md)。完整结构及证据校验后仅合并同编号且完整对象完全相同的重复；不同内容、未知字段、越界证据仍拒绝。原始响应保留，审计记录索引和规则。失败响应重新校验后继续经过统一 Store，成功批次不重复调用。

前端用“已保存（超时拆分后）”区别子批和全文完成；模型历史显示精确去重信息。未更改分块目标或擅自增大 timeout；自适应单次全文方案仍为待实现评估，不是本轮交付功能。

## 真实响应隔离回放

对当前实际运行库制作一致性副本后，只在 `.local/reading-failures-20261102/replay-data/` 执行。未升级、覆盖、恢复或写入正式库；未读取密钥或新发真实 API 请求。私人原文/响应/库不进入仓库。

- 复用原失败响应，去掉 8 个完全重复对象，20 候选和 24 关联通过 Schema、证据和 KnowledgeStore。
- 冻结 Prompt/Schema/计划签名兼容；副本进度由 0/34 到 1/34，到下一项需模型调用时立即停止。
- 副本原有 307 条 knowledge_nodes 全列逐行不变，新保存 20 条。所有原 ModelRun.raw_output 保持；第二次续跑无重复入库。
- 新模型调用 0、新增 Token 0；SQLite integrity_check 与 foreign_key_check 通过。
- 这是用户真实响应的离线回放，不是 Mock 质量测试，也不是全文成功。剩余 33 批及 P12/P13 本轮未调用。
- 快照中的旧 unified-v3 两条历史任务为 5/5、17/17 成功；此前报告的 6/17 是当时状态，保留历史记录，不作为当前阻塞。

本机明细：`.local/reading-failures-20261102/replay-report.json`。报告仅写结构、数量和检查结果，不含论文题名、正文、服务端点或凭据。

## 自动化与交付

- Conda researchgraph-studio 执行针对性回归：39 passed，涵盖精确重复、冲突、来源、额外字段、列表上限、真实调度下旧失败响应复用及成功批次保留。
- React 当前测试 40 passed，新增子批保存不等于全文完成的状态测试。
- `scripts/check-phase0.ps1`：189 Python passed / 2 skipped，40 React passed；Ruff、format、mypy、pip check、OpenAPI/TypeScript 契约、前端类型/lint/构建通过。两项文件链接场景因主机权限/文件系统条件跳过，未当作通过。Starlette 弃用及前端单包超过 500 kB 提示为已存在的非阻塞警告。
- `scripts/build-windows.ps1`：PyInstaller、Tauri、NSIS 成功。`scripts/smoke-engine.py --executable ...` 覆盖合成阅读管线、分层发布和重启持久化通过；PowerShell 5.1 `verify-windows-install.ps1 -EnginePath ...` 通过。
- 设置 `RGS_TEST_ENGINE_PATH` 后运行 `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --locked packaged_engine_connects_through_native_host_and_restarts -- --ignored`：1 passed，9 unrelated tests filtered out。无 Rust 源码更改，没有将未重跑的 9 项计入本轮通过数。
- 安装器：`.local/releases/reading-response-recovery-20261102/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,527,857 字节。SHA256 `073ae8dd5559e5b23383f0ebda476e4a489bf95dc27bc5d308c8f51d54fb1498`。版本仍 0.0.1，以路径和哈希区分交付包。
- 安全内容扫描：`python scripts/check-sensitive.py --gitleaks .local/tools/gitleaks-8.30.1/gitleaks.exe`，465 个候选文件及路径规则通过。`git diff --check` 通过，暂存区为空。未执行 Commit/Push，私人库、响应和安装器仅在忽略目录。
- 文档核对：132 份 Markdown、457 个可用本地链接、88 项当前资产哈希/字节清单通过；4 个登记外部来源路径不可用，单独列为限制，未计为链接成功。
- 未执行安装器覆盖安装、Computer Use、真实服务全文新请求或 GitHub 上传；用户原生操作与反馈待完成。

## 未通过及下一步

全文新任务和新安装器的用户原生反馈仍待验证。本轮保留当前正在运行的软件和任务，不主动安装/中断，不发起额外真实调用。用户安装修复包后应在原失败任务使用“继续未完成批次”；不要删除论文/知识或创建重复抽取来绕过该错误。后续未完成批次仍会产生实际模型调用费用，不能将本批零调用恢复理解为全任务免费。

下一步限于 R5：检查两篇新流程全文完成、核心贡献与证据质量、响应耗时；评估预算自适应单批/多批与整合规模。四份外部补充原文登记路径不可用的限制保持，未宣称完成其核验。
