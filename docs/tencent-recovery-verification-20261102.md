# 腾讯云适配、超时与空图谱恢复验收

日期：2026-11-02（Asia/Shanghai）。R5 可靠性迭代，head 0010，无迁移，未进入 P4/P5。继承上一轮尚未提交的精确重复响应修复，不覆盖既有工作区。决策见 [ADR 0011](adr/0011-tencent-streaming-and-reading-recovery.md)。

## 实际故障

- 只读备份当前实际运行库，所有分析/试验在 `.local/timeout-empty-graph-20261102/` 隔离副本进行。正式软件和任务未被停止，正式库未用于试迁移。
- 两篇新阅读任务快照分别为 failed 6/12、cancelled 4/35；对应 206/190 条候选或历史知识，均 0 个结论单元/选择。主图只显示论文的原因是尚未进入 P12/P13 发布，不能解释为知识丢失。旧 unified-v3 的成功记录保持。
- 4500 字符根批、2137 字符/14 证据子批均在等待非流式响应 90 秒超时，发送约 0.08 秒；另一个成功小批 12136 completion Tokens 中 10303 为思考 Token。故障证据指向等待生成/默认高强度思考，不是 PDF 无法读取，也不能靠把输出上限改成 128K/256K 解决。

## 改动

- `model_adapters.py`、`providers.py`、`chat_stream.py`、模型设置：精确腾讯模型适配，1M 上下文/384K 输出能力；端点元数据优先，文档版本兜底。新抽取默认非思考 JSON，自动预算 32K；推理默认思考 64K预算；显式 effort 优先。SSE 流、无响应与总时限分开，安全部分输出保留，usage 不重复累计思考 Token。
- `reading_resume.py`、任务 API/DTO/原生白名单和任务历史：显式创建适配续接任务，复用旧计划/签名/操作账本，成功批次不再请求；原任务不可变，重复点击不创建重复续接。
- `reading_status.py`、投影/选择 API、GraphWorkspace/ReadingControls/JobHistory：显示已保存知识与真实模型活动；支持停止后明确执行部分建图，保留全文覆盖缺口，不引入人工审核。
- OpenAPI/TypeScript 契约、相关 Python/React/Rust 测试和使用文档同步。无新数据库表；Schema/Prompt 主契约、原证据、历史模型输出和知识 ID 保留。

## 真实服务与隔离恢复

真实验证只发起一次生成请求，使用已授权腾讯配置/OS 凭据；未重新跑整篇，未输出密钥或私人材料。

| 项目 | 实测 |
| --- | --- |
| 范围 | 原超时子批，2137 字符、14 EvidenceSpan |
| 首字节 / 完成 | 1.328 / 9.531 秒 |
| Schema / 来源 / Store | 通过；4 候选、2 关联，0 隔离关联 |
| 用量 | prompt 6249，completion 1292，total 7541；reasoning 0 |
| 有效请求 | thinking.disabled、JSON、SSE；自动预算 32768，能力上限 393216 |
| 数据保持 | 原 396 条 knowledge_nodes 全列逐行不变；副本新增 4 |
| 费用 | 供应商未提供；不推算为 0 |

随后把这份已收到的真实响应用于另一个干净快照的续接回放：实际旧计划 6/12→7/12，先跳过已提交批次，在下一批需新模型响应前停止。新增网络调用 0，原任务/签名/396 条原知识保持，新增 4 条；SQLite 完整性/外键检查通过。首次回放脚本误查询 `validated` 状态（实际为 `succeeded`）而未进入回放，修正后用新副本执行成功；未因此新增真实请求。

本机报告：`real-probe-report.json`、`resume-replay-report.json`，保存在上述忽略目录；不将原文、响应、运行库或服务凭据纳入源码。

## 自动化与安装包

- `scripts/check-phase0.ps1`：**214 Python passed / 2 skipped、45 React passed**；Ruff、format、mypy（63 source files）、pip check、OpenAPI/TypeScript 导出、前端类型/lint/生产构建通过。两项主机文件链接条件测试跳过，不计通过；Starlette 弃用与前端单包 >500 kB 为已存在非阻塞警告。
- `pnpm --dir apps/desktop test:browser`：**3 passed**，真实 React Flow 覆盖悬停/拖拽可见、固定/缩放/容器变化、共享支撑与布局保持。
- `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --locked`：**9 passed、1 ignored**；`cargo clippy ... -- -D warnings` 通过。打包后设置 `RGS_TEST_ENGINE_PATH`，另行运行 `cargo test ... packaged_engine_connects_through_native_host_and_restarts -- --ignored`：**1 passed**，其余9项未重复计数。
- `scripts/build-windows.ps1`：PyInstaller、Tauri、NSIS通过。`scripts/smoke-engine.py --executable ...` 冻结引擎检查通过，覆盖合成阅读/分层发布、来源保留、强退回收、重启持久化；合成模型不冒充腾讯真实调用。PowerShell5.1 `scripts/verify-windows-install.ps1 -EnginePath ...`：5项引擎检查通过，子进程PATH仅System32，不认证干净机安装。
- 新安装器：`.local/releases/tencent-streaming-recovery-20261102/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,552,219字节；SHA256 `c6febf559b1b0223d5bfd1234b9f7cff2f1c658fa47ed4bea18457fa00bfd723`。仍为0.0.1，以路径/哈希区分；没有替换用户运行中的软件或执行覆盖安装。
- `python scripts/check-sensitive.py --gitleaks .local/tools/gitleaks-8.30.1/gitleaks.exe`：474个候选文件的内容、私人路径规则和Gitleaks通过；`git diff --check`通过，暂存区为空。私人库/报告/安装器均留在忽略目录，未Commit/Push。
- 文档检查：134份Markdown、472个可用本地链接、88项当前资产字节/哈希清单通过；4个登记外部来源路径不可用，单独记录，不计为成功。最终检查未使用Computer Use，也没有操作用户的原生窗口。

## 用户安装后操作与剩余项

1. 待当前任务结束后退出旧版，安装本轮新包；不要删除论文、项目或知识。安装器不包含私人库和 API Key。
2. 全局模型继续选择原腾讯配置；Reasoning effort 留空使用角色默认。新任务自动应用适配；普通旧任务重试仍保留原策略。
3. 在旧失败/取消任务上使用“使用腾讯云适配继续”。它生成新的续接任务，只处理未完成批次；原任务记录保留。没有此按钮时不要直接删数据重抽，应核对是否还在运行、已进入整合、已有续接或曾显式设置思考强度。
4. 如先查看已抽内容，在图谱点击“查看已保存候选与建图选项”，任务停止后允许发送候选/必要证据，选择“基于已保存候选生成部分图谱”。只运行整合/选择，仍会产生模型用量；生成图须显示覆盖缺口，不能称全文完成。

真实单批通过不等于完整论文通过。两篇全文、真实 P12/P13 部分图、用户覆盖安装和科学质量仍待反馈；OpenAI直连、其他供应商和本地模型的 SSE 未实测。单次全文/自适应大批策略仍未实现。四份外部原文登记路径不可用的限制保留，未宣称已核验。下一步仍为 R5 全文与安装验证。
