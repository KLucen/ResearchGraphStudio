# 空占位字段与抽取超时验收

日期：2026-11-02（Asia/Shanghai）。修复用户反馈的两次抽取失败，继承已有数据与 Phase，不新增阶段。详见 [ADR 0007](adr/0007-extraction-null-markers-and-timeout-adaptation.md)。

## 诊断

- 通过已确认的 UNC 路径对实际 SQLite 做一致性备份；本轮基线是 **156 条知识**。之前验收报告的 183 条是当时状态，不应恢复覆盖用户之后的操作。
- 四批任务首批成功；第二批 10445 原文字符/49 证据，返回 15 items，5 个 ClaimDetail 多出值为 null 的 findings_placeholder。总错误数为 5，旧任务摘要仅显示前 4 个，符合用户反馈。
- 十六批任务已有六批成功；第七批 8371 字符/75 证据，3 次约 90 秒 timeout、总耗时 274.391 秒，无完整响应或供应商用量。其他成功批次曾经超时后重发。旧日志没有网络阶段，无法确定供应商排队/生成或网络等待各占多少。
- 正常产品入口使用真实模型；私人诊断和备份只保存在 `.local/extraction-reliability-20261102/`。未改正式库、源 PDF 或 Zotero。

## 修改

- 已知路径的 null 占位字段可确定性移除并审计；不放宽领域 Schema，不丢弃非空或陌生字段。旧失败响应可复用，不重复付费抽取。
- 新任务采用独立 P02 3.2 模板与 8000 字符/64 证据目标；旧任务保留旧 Prompt/签名/计划，成功批次保持幂等。
- 增加连接/请求发送/响应头/响应体超时诊断。统一抽取响应超时仅拆未完成根批一次，按原文字数平衡，子批仍超时即停止；连接错误和限流仍有界重试，未增加 timeout。
- 阅读区显示空标记处理提示；任务批次显示“超时后缩小”。原响应、规范化路径、修复运行、来源与模型用量保留。

## 实际验证

**Schema 失败已在真实副本完整恢复；响应超时仍有未解决项。**

- 四批任务：复用原有成功批及包含 5 个 null 标记的失败响应，不重新抽取这两批；只发送剩余两批，最终 **4/4 成功**。两次用量分别 22,842 与 12,829 Token，共 **35,671 Token**。发送耗时 0.031/0.047 秒，等待响应头 88.609/45.204 秒；完整响应通过 Schema、证据与 Store。
- 十六批任务：保留前六批，旧失败根批按长度拆成两份，总数变为 17。第一个子批 **4185 字符/34 证据**仍在等待响应头时 90.047 秒超时，发送仅 0.032 秒、响应字节 0。已按边界停止，进度仍 **6/17**，没有继续重发该请求或执行其他待处理批。
- 同一子批另在独立副本尝试 P02 3.2，之后再减少候选提示并约束表格歧义；两次仍在等待响应头时达到 90 秒。上述三次超时均无供应商用量，不能当作零费用，也不声称新版模板已通过此真实批次。
- 无论文的短连接请求 **1.907 秒通过**（含能力探测），用量 **138 Token**。证据指向论文抽取响应明显慢于短请求；不能据此区分供应商排队、内部推理或返回链路。真实返回的已知用量合计 **35,809 Token**，另有三次未知用量的超时请求。
- 副本中原 **156 条知识全列逐行相同**，所有既有原始模型响应保持原样；SQLite integrity/foreign_key 检查通过。没有把实验结果写回正式库。

| 命令 / 场景 | 实际结果 |
| --- | --- |
| `pwsh -NoProfile -File scripts/check-phase0.ps1` | 全部通过：153 Python passed/2 skipped、37 React；Ruff/format、mypy 49 模块、依赖、契约、TS/eslint、前端构建通过 |
| 最后候选数量提示调整后的针对性回归 | `pytest test_extraction_reliability.py test_extraction_repair.py test_extraction_refinement.py test_graph_v3.py -q`：44 passed |
| PyInstaller/Tauri/NSIS 构建 | 通过；最终产物信息见下方交付记录 |
| 冻结引擎 smoke / PowerShell 5.1 EnginePath | 通过，独立数据与 System32-only 子进程 PATH；不是原生安装器执行验收 |
| 候选源码敏感内容与 Gitleaks / 文档与 diff | 347 个候选文件内容扫描通过，暂存区为空；92 份 Markdown/327 个本地链接、QA hash、环境 JSON、52 项设计资产及 diff 检查通过；4 份不可用外部原文明确排除 |

保留两项 Windows symlink 权限跳过、Starlette/httpx 弃用和前端 chunk 提示。图谱/Rust 源码本轮未改，没有重复其交互/单测；Tauri release 编译通过。

最终安装器保存在 `.local/releases/extraction-reliability-20261102/ResearchGraph Studio_0.0.1_x64-setup.exe`：**38,448,362 bytes**，SHA-256 `446A533B287C19E3FDEBCC088B15854B932D5A37FFAC45F46307CB19BB9B0AF5`。仍为开发版本 0.0.1、Schema 0009，无迁移；该目录内附 `verification.json`。没有替换当前运行窗口或安装版。

最终构建后的冻结 smoke 已重新通过；PowerShell 5.1 首次调用因主机脚本执行策略在运行前拒绝，随后使用仅当前子进程的 `-ExecutionPolicy Bypass` 和绝对 EnginePath 运行通过，未更改系统执行策略。日志分别为本机忽略目录下 `build-final.log`、`frozen-smoke-final.log`、`ps51-final.log` 与 `ps51-engine-final/verification.json`。这些检查使用独立数据，不能等同于安装器安装/卸载或干净 Windows 验收。

## 用户验收

退出旧窗口、安装本轮包，再在任务历史对 Schema 失败的任务点“继续未完成批次”，不必新建任务或重新导入 PDF；空占位响应会被复用。超时任务也保留继续入口和成功批次，但当前真实模型在缩小后的请求中仍超时，建议先避免反复点击造成未知费用；本轮不宣称此任务已恢复成功。调整模型配置不会回写已排队任务快照。

反馈新的错误文字和批次编号即可，不发送 API Key。遵循用户偏好，本轮不使用 Computer Use；安装执行和原生体验待用户反馈。四份登记补充原文仍不可用，历史来源/QA 保留；无 Commit/Push。
