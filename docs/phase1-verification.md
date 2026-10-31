# Phase 1 来源与证据开发记录

更新时间：2026-10-31（Asia/Shanghai）。G0 已按用户决定放行，依据 [ADR 0004](decisions/0004-g0-waiver-phase1.md)。RG-006 的 PDF 导入、来源检查、临时工作区回收、任务阶段和历史分页增量已完成引擎/自动化验收；桌面分页桥接修复后的原生复测仍待完成，M1 安装版证据定位和干净环境也未完成。

## 本轮范围

打开研究项目后，在“文献与原文”选择 PDF。默认引用原文件；选择“复制到项目存储”才保存托管副本。任务列表显示排队、解析、失败、取消和重试；已导入文献可查看附件修订、哈希、解析器版本、页码、原文块和块级坐标。

原生宿主打开文件选择器并提交所选路径，通用前端 HTTP 桥不允许直接调用文件导入路由。引擎 API 仍要求私有 Bearer 令牌。解析仅在本机执行，不调用模型，不读取 Zotero 或个人笔记。

- 迁移 0002：papers、paper_sources、attachment_revisions、chunks，Job 保存项目和导入参数。
- 文件名只用作暂定标题，不作为文献身份；不猜测 DOI 或作者。
- 同项目相同内容去重；不同路径保留映射；同一路径内容变化追加修订，旧块及哈希不覆盖。
- 原文按 PyMuPDF blocks 排序保存。字符定位目前是块内 Python Unicode 字符索引；文本不做归一化。块坐标不是精确字符框。
- 每份最多 50 MiB / 300 页 / 200 万字符，解析超时 120 秒，任务最多三次尝试；不执行 OCR。无文本页、损坏、加密、丢失文件均有实际状态提示。

### 任务恢复与历史分页增量（2026-10-31）

临时工作区只回收 `data/import-work/` 下应用自有的 UUID 平坦目录：必须有精确 `workspace.json` marker，内容只允许白名单文件。子进程用旁侧 `.lock` 文件持有独占租约；活动目录报告为 `busy`，目录链接、未知内容和权限失败保留 marker，下一次启动可重试。清理失败不会撤销已经提交的 PDF 结果，也不会删除原始 PDF、托管附件、历史修订、SQLite 或备份。健康接口和设置页提供 `removed`、`busy`、`retained`、`errors` 统计。

Job Schema 0004 增加实际阶段 `starting`、`reading`、`parsing`、`checking`、`saving`、`diagnostics`。阶段不估算百分比；取消/失败保留最后观察到的阶段，重试清空阶段。项目任务历史返回 `items`/不透明 `next_cursor`，以 `(created_at DESC, id DESC)` 排序，并在第一页固定 SQLite `rowid` 快照上界；即使迟到任务具有相同创建时间也不会混入后续页。状态变化和重试不改动分页顺序，跨项目或无效游标返回 `INVALID_CURSOR`。

本轮新增实现和约束见 [ADR 0006](decisions/0006-job-history-workspace-recovery.md)，API Schema 说明见 [接口文档](api.md)。

此前独立原生验收使用应用标识 `com.researchgraph.studio.phase1test`、数据目录 `C:\Users\KLucen\AppData\Local\com.researchgraph.studio.phase1test` 和仓库 `.local/native-phase1-synthetic.pdf`，操作前将旧测试目录备份到 `.local/native-phase1test-backup-20261031-195549`。验收报告记录了旧 Schema 0003 升级、取消/重试、来源检查、回收统计及重启后仍可查看的两页/四块原文。

本轮代码复核发现 Tauri `engine_request` 白名单仍将任务分页 `cursor` 当作 UUID 校验，而引擎实际返回 Base64URL 不透明游标。因此此前报告中的“加载更早任务后 13 条可见”无法通过当时的桌面桥接实现，该条已撤销，不作为通过证据。Rust 白名单已改为只允许 1–512 位 ASCII Base64URL 字符，并新增边界回归测试。修复后原生窗口复测未完成：Computer Use 两次在 `list_apps` 枚举阶段被物理 Escape 中止；最近一次没有触碰应用窗口。旧库升级、重试、回收统计和原文保留仅沿用此前独立数据记录，本轮不声称重新操作验证。

原生验收报告见 [2026-10-31 RG-006 窗口报告](environment/2026-10-31-phase1-jobs-native.json)。它是开发机调试构建和自造 PDF 结果，不替代修复后桌面分页复测、远端新安装包、干净 Windows、缺失 WebView2 或真实论文质量验收。

交付前复核再次通过 45 项 Python（1 项平台能力跳过）、16 项 React、1 项 Rust、静态/格式/契约/生产构建、冻结引擎重建与 smoke。PowerShell 5.1 引擎模式报告为通过，证据在本机忽略目录 `.local/phase1-jobs-ps51-final-010d4454e00545d4b916df0912f72621/verification.json`；报告仍将干净 Windows 标为未认证。原生分页和新安装器验收单独待完成，不能由这些引擎检查替代。

## 验证与样本

### 来源检查与重新定位增量（2026-10-30）

文献详情新增“检查文件”和“重新定位…”：原文件与托管副本分别显示内容一致、变化、丢失、无法读取、超限或检查时变化，并保存时间。重新定位只接受相同哈希且未冲突的 PDF；来源 ID、附件修订、历史文本保持不变。检查结果不代表证据审核通过；当前来源与所选历史修订不同时有明确提示。

迁移 0003 增加 generation 与 last_check，来源更改后拒绝旧任务结果。检查/重定位在可取消的子进程内执行，沿用幂等、重试及原子事件记录；项目任务现在独立查询，不再被其他项目的任务挤出。规则见 [ADR 0005](decisions/0005-source-check-relocation.md)。

本机 32 项 Python、12 项 React、1 项 Rust 测试与静态/格式检查、生产构建通过；新打包引擎和 [PowerShell 5.1 验收](environment/2026-10-30-phase1-sources-powershell.json)通过来源丢失/托管副本可用、同内容重新定位与重启读回。Windows PowerShell 本机首次因执行策略拒绝启动脚本；随后用仅对该次进程生效的参数执行成功，未修改全局策略。

原生调试窗口在独立测试数据目录中完成升级读回、点击检查、显示内容一致及时间、通过原生选择器重定位到同内容自造副本；文献仍为一篇，附件哈希与两页原文保持不变。

首轮 [CI 40995909703](https://github.com/KLucen/ResearchGraphStudio/actions/runs/40995909703) 的 Python/React 与静态检查通过，打包 smoke 因 Windows 短路径与 API 规范化路径直接比较而失败，未进入安装验收。本机以 8.3 短路径复现后，修正验收脚本并核对实际文件身份，复测通过；PowerShell 5.1 的短路径验收原样通过。见[路径回归记录](environment/2026-10-30-phase1-sources-paths.json)。

修复提交 `4410ef380633a603ec3b221f439259a4b879894b` 的 [CI 41024830613](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41024830613) 已全部成功：32 项 Python / 12 项 React / 1 项 Rust 测试、静态/契约/生产构建、打包引擎和 NSIS 构建通过；另一 runner 完成安装、PDF 导入、原文件丢失/托管副本可用、同内容重新定位、来源/原文重启持久化、鉴权、诊断、桌面启动/单实例/正常退出/崩溃清理及卸载。详见 [CI 摘要](environment/2026-10-30-phase1-sources-ci.json)和[原始安装报告](environment/2026-10-30-phase1-sources-installed.json)。

本轮安装器 37,623,738 字节，SHA-256 `7F6CF7463FCB0C4F39DFBD492A5EF83CDED330D95D0297D9924ED2D0F8DE6B17`；两个下载 artifact 的官方 ZIP 哈希均匹配，安装器哈希与安装报告一致。开发机 `.local/phase1-sources-acceptance-kit.zip` 保存本轮安装器、脚本、CC0 样本、校验清单、说明及原始报告，六个条目和文件字节已核对，未覆盖既有安装。CI 成功不代表未执行的干净 Windows / 缺 WebView2 场景已测试。

### PDF 导入首轮（历史验收）

`tests/fixtures/pdf/` 为项目自造 CC0 样本；生成脚本为 tests/fixtures/make_pdf_samples.py。包括两页文本、图片页、加密文件和故意损坏文件，不含用户文献。

本机已通过：20 项 Python 测试（含从 0001 升级与备份、故障回滚、跨页块定位、去重、历史修订、项目隔离、失败不留半成品、取消后重试、运行中取消/退出终止子进程）、7 项 React 测试、1 项 Rust 路由测试及 fmt/clippy；冻结引擎在仅系统 PATH 下完成托管导入和重启文本读回，[Windows PowerShell 5.1 报告](environment/2026-10-29-phase1-powershell.json)亦通过 PDF 导入/重启和 EOF 退出。

2026-10-30 原生窗口复核：使用独立标识 `com.researchgraph.studio.phase1test` 启动调试构建，读回此前保存的验收项目和样本。通过原生文件选择器再次导入 two-pages.pdf 后，两次任务均完成，项目仍只有一篇文献；详情显示一致的 SHA-256、两页原文、S-1/S-2 页标签及 72%/81% 样本数值。此结果来自开发机，不代替干净 Windows 验收。

[CI 40930522934](https://github.com/KLucen/ResearchGraphStudio/actions/runs/40930522934) 已全部通过，对应实现提交 `9b7a306be1e73e0392e81b6a576706d3aa712042`：Windows runner 重建依赖并通过 20 项 Python、7 项 React、1 项 Rust 测试、静态检查、契约和打包引擎验证，生成 NSIS；另一 runner 通过安装、PDF 导入、项目/原文重启读回、鉴权、诊断、宿主启动/单实例/正常退出/崩溃清理及卸载。见 [CI 摘要](environment/2026-10-30-phase1-ci.json)和[原始安装报告](environment/2026-10-30-phase1-installed.json)。

CI 安装器 37,606,027 字节，SHA-256 `DBE45D7678F387D3B28AAC1D762BC86BEF9A2ED5BF64A13760682FE45B87FC89`；已下载并核对官方 artifact ZIP 摘要与安装报告。开发机 `.local/phase1-acceptance-kit.zip` 保存该安装器、样本、脚本和说明，未提交二进制；未覆盖原有本机安装。

解析实现依据 [PyMuPDF 官方文本抽取文档](https://pymupdf.readthedocs.io/en/latest/recipes-text.html)，版本固定为 1.26.7；原文块阅读顺序可能受 PDF 排版影响，不能视为语义阅读顺序已验证。

## 剩余工作

1. RG-006 桌面收尾：在可继续使用 Computer Use 的原生窗口重新加载第 2 页任务历史，确认 Base64URL 游标可经 Tauri 白名单到达引擎；当前修复后的窗口复测因物理 Escape 中止而未执行。
2. RG-007：Evidence/span 对象、跨页引用、断词及归一化映射、原页面高亮、人工校正的新版本和原因记录。
3. M1：完整安装版导入与证据定位验收；G0 未执行的干净 Windows 和缺 WebView2 实测留在发布检查中。
4. 使用更多真实、可分发的 PDF 做版式质量验收；自造样本只证明工程边界，不代表科学语料效果。

当前原文块可回看，但尚不能创建或接受 Claim/Relation；不能把“导入完成”理解为证据审核通过。

### RG-006 已实现的边界（2026-10-31）

- `import-work` 崩溃残留已按应用 marker 和独占锁回收；迟启动子进程在再次校验后失败，目录链接或 Windows junction 不会触及外部位置。清理失败保留 marker 并在下次启动重试，不让已完成的导入退回失败。
- 托管附件单独处理：当前 PaperSource 不再指向某个文件，不代表历史 AttachmentRevision 不再需要它。历史版本、共享内容哈希、原文件、数据库及备份必须保留；不能直接对 attachments 执行“当前来源未引用即删除”。回收规则及恢复方案确定后再实现。
- 任务进度只显示真实阶段（等待、读取/检查、解析、保存），不猜测百分比。分页历史保留项目隔离、确定顺序和取消/重试入口；重复请求与任务状态变化不应使列表遗漏，已由 keyset 游标和测试覆盖。
- 验证包括异常终止后重启、文件占用/拒绝访问、重复回收、外部目录链接、旧附件与共享附件保留、取消后重试，以及开发机原生窗口的同一流程。安装版的本轮新验收尚待远端 CI；更多真实论文的版式质量验收另行记录，自造样本不代表真实语料效果。
