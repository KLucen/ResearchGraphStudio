# 实施进度

更新：2026-11-09（Asia/Shanghai）。本文维护当前状态和下一步；2026-11-05 及更早的完整实施记录移至[历史时间线](archive/reports/progress-through-20261105.md)。本页下半部分的 P5 成绩、包及未验项是重构前历史，不代表当前 Lite 开发范围。

## 当前阶段

**ResearchGraph Lite P0（A+B+D 路线）：本地阅读基础、模式开关、用量与缓存基础；完成 P0 后停止，尚未开发 P1。**

| 标识 | 当前值 |
| --- | --- |
| 应用版本 | `0.0.1` |
| Alembic head | `0022`：0021 项目模式、0022 用量/缓存 |
| 新项目默认 / 旧项目迁移 | `lite` / `legacy` |
| 重构前备份 | `origin/backup/pre-lite-refactor`，`7b45f0dce9168f8b547fca95f06a117e80404198`，已核实远端 |
| 当前分支 | `refactor/researchgraph-lite-p0`，从备份创建；工作区改动未提交、未推送 |
| 阅读领域 / 入口 | `reading-extraction-1.0` / `paper-reading-v1` |
| Query 上下文 / 回答传输 | `query-context-1` / `query-grounded-semantic-1` |
| P5 工作流传输 | `reading-workflows-1` |

重构前的架构、功能实际状态、Schema/API、Zotero/PDF/Provider/Knowledge Engine、Token 成本原因与可复用范围已记录在[当前项目基线](current_project_baseline.md)。旧 P5 工程已提交为 `9ef8cde`，基线文档随 `7b45f0d` 保存到独立备份分支。本轮仅向备份分支普通推送，未向 main 或 Lite 分支上传。

## Lite P0 已实现

- 新项目默认 Lite；0021 把既有项目回填为 legacy，保留全部旧论文、图谱、布局、ModelRun/Query/P5 raw 与历史版本。未重建工程或清空旧表。
- Lite Zotero 选择和 PDF 导入只做本地解析、章节结构、原文块/证据与 FTS5 索引。旧客户端提交 `extract_after_parse=true` 也被服务端规范化为本地处理，ingest 不创建抽取子任务。
- Worker 阻断 Lite 项目的完整抽取、跨论文推理、Query/P5/翻译模型任务；抽取入口再次保护；后台 Lint 维护跳过 Lite。前端 Lite 默认只显示文献与阅读，legacy 保留原导航和图谱访问。
- 统一只读用量接口 `GET /api/v1/projects/{project_id}/lite/usage?paper_id=...` 汇总旧账本与新 Lite 记录，区分已知调用、缺账本、usage/费用未知、估算、重试与缓存命中。
- `lite_token_usage` 与 `lite_cache_entries` 建立论文/文献版本/小节缓存基础；缓存命中计 0 新调用/0 新 Token，键绑定来源、Prompt/Schema、模型和安全配置指纹；旧版本可标记 stale，不自动重算。

用量写入服务与缓存是 P0 基础，尚未有 B/A/D 生成业务或自动 Provider 回调接入。legacy 账本只读聚合，不重写历史；缺失的调用次数、Token 或价格继续标未知。当前零调用的本地流程具有确切的零增量费用，不能将其当作已有历史账单的零费用。

## Lite P0 验证与边界

最终完整后端 **1208 passed / 3 skipped / 1 既有 TestClient 弃用警告**（456.23 秒）；P0/用量/模式专项 **18 passed**，Ruff/256 文件格式、mypy141运行源、Python依赖及生成契约通过。初次全量1194/3为中间结果，不与最终分母累加；旧Schema fixture的6个失败按旧列插入/保持修正，专项56通过。新测试另发现导入未物化FTS，已在Lite保存事务内建立本地来源索引，直接MATCH及重启保持通过；已有依赖cursor的Lite自动Lint维护也已阻断。

最终完整前端 **169 passed / 17 文件**（17.82 秒），TypeScript/ESLint、Prettier、生产构建通过；Rust **20 passed / 1 ignored**，格式检查通过。最终源码重建PyInstaller引擎后，显式原生Host健康握手/停止/重启 **1 passed**（3.41 秒）；Windows PowerShell5.1/System32-only PATH隔离 **17项**通过。源引擎及最终冻结引擎smoke的认证、导入、旧图谱/Query、强退恢复及重启持久化分别通过；每轮旧Query兼容smoke各有 **1 次本地P07协议stub**，不是Lite本地流程或真实模型请求。旧冻结引擎head0020的首次Host失败保留，重建为0022后通过；本轮没有重建NSIS安装器或安装用户应用，未将旧安装器当Lite验收。前端652.72KB chunk及PyInstaller可选模块提示保留。

Lite 本地测试使用至少两份不同的合成 PDF，模型入口设调用哨兵；正常导入/章节索引、重启读取与五类旧排队模型任务均要求调用数为 0。Zotero 测试使用本地匿名 adapter fixture，并非直接操作用户 Zotero 或私人 PDF。

真实模型调用 **0**、正式库实验写入 **0**、私人论文/批注/凭据读取 **0**。实际用户旧库未升级或安装测试；旧数据保持以隔离的已填充历史 Schema 升级和重启回归证明，不能表述为用户所有正式数据已经实际验收。真实 B/A/D 质量、价格、strict、复杂表格/公式、无 OCR、跨平台/干净机和用户安装反馈仍待相应阶段验证。

Lite本地两份PDF的实际增量：输入0 Token、输出0 Token、调用0、重试0、费用0；零值由Provider调用哨兵和空账本共同验证。源码候选内容/私人路径/Gitleaks与全历史扫描、文档链接及清单复核的最终结果见DEV-0063；Lite改动保留在本地工作区，未Commit/Push。

最终冻结引擎独立Lite探针也通过：默认Lite项目、合成PDF导入、4个文本块和用量接口calls/input/output/total均为0，正常EOF退出。首次临时探针使用过短会话令牌未启动，已清理后以合法令牌重跑，不计失败尝试为通过。

## 下一阶段（尚未开始）

Lite P1 仅做 **B01 六字段论文卡片**：受限源段落选择、Span 白名单、版本化结果和缓存、显式“生成/重新生成”与费用提示、逐请求 Provider usage/失败重试记账，验证二次打开缓存零新增调用。A 章节导读、D 局部问答和完整预算设置在后续阶段。本轮不提前实现这些业务，也不追加真实模型调用。

迁移/复用映射见[Lite迁移评估](migration/lite_from_v3_assessment.md)，决策见[ADR0031](adr/0031-researchgraph-lite-p0.md)，目标设计见[Lite A+B+D](researchgraph_lite_ABD/README.md)。

## 重构前 P5 状态（截至 2026-11-07）

**以下是 backup/pre-lite-refactor 所含完整模式的历史状态；P5 的真实科学质量与用户原生退出验收尚未闭环，不作为 Lite P0 的未完成开发任务自动续做。**

已接入确定性 Lint、稳定问题指纹/生命周期、反向依赖与影响闭包、P09/P10/P11 独立任务、Wiki 草稿/不可变保存/历史、受管 Markdown 发布/恢复和局部更新。笔记快照、批注评论和外部 Markdown 版本按来源选择；local/model 用途与目录写入授权分别校验。实现边界见[ADR0029](adr/0029-lint-wiki-workflows-and-managed-publication.md)与[P5 实施报告](p5-verification-20261105.md)。

## 最新功能修复与验证

2026-11-05 16:00 的扫描反馈修复增加活动报告只读刷新、终态/进度防回退和明确的准备/推进/待继续/完成状态。桌面每批推进 100 项，后端默认 25、上限 100 和逐调用验源不变。`CONDITION_UNKNOWN` 保持 info，表示信息缺口，不推断矛盾或补造条件；`SOURCE_UNCHECKED` 表示没有原文件可用性检查记录，不等于文件丢失或科学错误。

| 验证范围 | 实际结果 | 对应轮次 |
| --- | --- | --- |
| 反馈修复前端 | 155 React / 17 文件，19 Edge 通过 | 2026-11-05 扫描反馈修复 |
| 后端专项 | 31 Lint/文档专项通过 | 同上；Python 运行源未改 |
| 打包链路 | PyInstaller/Tauri/NSIS、冻结 P5/旧 smoke、Host 1、PS5.1 隔离 17 项通过；213 运行源/312 资源匹配 | 同上；不是用户实际安装反馈 |
| 完整后端基线 | 1124 Python passed / 3 权限跳过、148 React、19 Edge、Rust 20 及静态/契约检查通过 | 更早的 P5/head0019 功能完成轮；未因反馈修复重新全量运行 |
| Lint 规模基线 | 10,000 候选 / 20,000 原文块 / 30,011 目标，完整扫描 430.284749 秒 | 更早的串行基准，未因反馈修复重跑；不是通用 SLA |

上述为带日期的历史成绩。本轮性能优化已完成同字节脚本的串行前后基准：完整推进 856.662931→469.026664 秒，依赖重建 13.185584→3.217814 秒，反向查询 P95 1.027968→0.030090 秒，峰值 RSS 300.695→247.469 MiB。完整 catalog 仍逐调用重验且占主要耗时，不能宣称所有项目即时完成，也不继承 P4 的两秒检索目标。具体实现、SQL/阶段计时及失败尝试见[本轮性能报告](p5-lint-performance-verification-20261107.md)与[ADR0030](adr/0030-lint-performance-and-progress.md)。

## 重构前历史交付包

最新性能与阶段反馈包为 `.local/releases/p5-lint-performance-20261107/ResearchGraph Studio_0.0.1_x64-setup.exe`，39,054,979 字节，SHA256：

`afd062f6f700f9081db2f756d37e6b8fa38b5206f06c1f25d7d4488fd4d12198`

退出旧应用后安装此包，首次启动按既有机制先备份再升级到0020；原论文、报告、旧科学输入与版本保持。打开“Lint / Wiki”中的原报告并“重新读取报告”，未完成则显式继续；新推进记录阶段耗时，历史未记录耗时不会补造。新全范围扫描可观察对象检查满数后仍进行的依赖重建阶段，不需重抽论文。旧 `p5-lint-repair-20261107`、`p5-scan-status-20261105` 和 `p5-lint-wiki-complete-20261105` 包保留。用户确认旧扫描可以继续；本性能包的用户原生升级/扫描、目录选择、发布和重启反馈仍需分别确认。

## P5 历史未验项

- 扫描可以继续已收到用户确认；性能/阶段反馈新版及原生目录选择、发布/重启反馈仍待确认。
- 真实 P09/P10/P11 逐段科学验收尚未执行，当前没有新增付费预算，不继承已结束的 P4/R5 调用授权。
- Lint 本轮已优化并新跑同规格基准，完整 catalog 复验仍是主要耗时；用户原生效果另验，历史文档整理没有重跑性能。
- 真实 strict、跨模型/平台、干净机、复杂表格/公式和无 OCR 限制，以及 S1–S4 四份不可用补充原文单列保留。
- 截至11月7日当轮P5未提交、未推送；该快照现已包含在11月9日的重构前备份，不能将历史授权状态作为当前分支状态。

本次 P5 开发及反馈修复真实模型调用 0、正式库实验写入 0；未替用户安装、未使用 Computer Use。合成协议通过不代表科学语义和 P5 全部退出门槛通过。

## 2026-11-07 文档整理

已将当前设计、运行说明、进度/续接与历史证据分开：清理 00–09 和导航中的重复旧状态，历史报告归档到 [archive/reports](archive/reports/README.md)，完整旧进度移入历史时间线，移除重复协作模板和旧版跳转页。文档整理的实际检查结果记录于[开发日志](../DEVELOPMENT_LOG.md)最新 DEV-0060；没有借本轮文档变更追加应用回归或模型验收成绩。

实际检查：189 份 Markdown、804 个本地链接目标、86 项当前规范资产及 52 项归档资产的 LF 清单/哈希通过；30 份报告和完整旧进度除链接外保持正文，366 个非文档文件对照整理前无变化。四份已登记外部原文仍不可用，未计为通过。差异空白和预期删除范围检查通过，暂存区为空。

## 2026-11-07 Lint 问题处理方案

用户确认扫描可以继续；这项反馈不替代目录选择、Wiki 发布、重启或真实科学质量验收。Lint 问题卡片现在提供程序生成的“修复 / 处理方案”。`SOURCE_UNCHECKED` 引导到文献页检查文件、记录可用性并重新运行 Lint；`CONDITION_UNKNOWN` 引导回查正文/表格/图注，有明确证据时才准备受控重建或新版本，原文未说明时继续保留 `unknown`。不直接编辑旧条件，不据此推断矛盾或补造实验条件。

方案按规则及问题生命周期区分来源、支撑、依赖、私人快照和受管文件的处理路径。后端通过 `repair_plan` DTO 提供方案，旧报告读取时即可派生；旧响应没有该字段时桌面提供安全回退。方案是只读提示，展示不调用模型或自动修改任何内容；后续步骤明确区分“此步骤不调用模型”“需要模型（需单独授权）”和“由后续受控流程决定”。展示字段不进入 P09/P10/P11 冻结快照、模型输入或 hash，不新增迁移。

最终冻结源码的定向回归：10 个后端文件 **234 passed / 1 符号链接权限跳过**（80.09 秒），完整前端 **159 passed / 17 文件**（18.04 秒）；Edge P5 渲染专项 4 项通过，mypy 134 源文件及 Ruff/格式/TypeScript/ESLint/生成契约通过。后端跳过项、既有 TestClient 弃用警告和首次格式检查失败均保留在 DEV-0061；未重跑旧 1124 后端全量或 430 秒规模基准，不沿用为新成绩。

该处理方案轮的 PyInstaller/Tauri/NSIS、冻结 P5 和旧 smoke 通过，P09/P10/P11 均为本地合成 HTTP/SSE，不是真实科学验收。该轮 Windows PowerShell 5.1 的 System32-only PATH 引擎隔离 **5 项**通过（未传 PDF fixture，不套用旧 17 项成绩），未安装应用或运行 Host 测试。213 运行源及 312 打包资源配对，安装器为 `p5-lint-repair-20261107` / `7c08d3b8`；当轮无新增迁移、Commit 或 Push。以下性能轮有独立新包和验证分母。

## 2026-11-07 Lint 性能与阶段反馈

完成 [ADR0030](adr/0030-lint-performance-and-progress.md) 的批量 catalog/节点预读、依赖边批量重建、索引递归完整闭包、0020加性迁移及准备/扫描/末批重建进度。scope/target/hash 与逐调用来源/用途终验保持；30,011 个 ordered targets 在相同 query_only 快照前后逐项完全相同，六类依赖场景的全部边与72次查询响应等价。unknown 保持 info，处理方案不执行修复，phase/timings 不进入冻结科学快照/hash。

最终实际验证：完整后端 **1185 passed / 3 权限相关跳过**（469.05秒），完整 React **164 / 17 文件**（18.93秒），P5 Edge **5**、Rust **20**及打包 Host **1**通过；mypy136源文件、Ruff/249格式（含基准脚本）、Python依赖、TypeScript/ESLint/Prettier、OpenAPI/TypeScript生成通过。PyInstaller/Tauri/NSIS、冻结 P5/旧 smoke、PS5.1/System32-only PATH **17项**（本轮实际传入双页合成PDF）通过；无实际安装或用户原生操作。

固定同字节基准的完整推进469.026664秒（本轮before856.662931）、显式重建3.217814秒、反向完整闭包P95=0.030090秒、峰RSS247.469MiB；完整目录复验仍占433.712787秒，大规模扫描仍需等待。301批对象检查后先提交running/rebuilding_dependencies，再由第302批终验/重建后完成。SQL、wall、阶段累计441.972498秒、12样本口径、脚本等价格式修正及失败尝试见[本轮报告](p5-lint-performance-verification-20261107.md)和DEV-0062，不套用旧430秒或P4目标。

215运行源在冻结/最终回归/构建前后指纹稳定，基准自身165后端文件实测前后也保持；314引擎资源与Tauri副本匹配；新包见上方当前交付，旧包保留。真实模型0、正式库实验0、未Computer Use/替用户安装/Commit/Push；真实科学、用户原生反馈和P5完整退出门槛仍待验收。
