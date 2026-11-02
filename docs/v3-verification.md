# v3 M0–M6 实际验收记录

后续更新：本报告保留 DEV-0025 的历史实测；DEV-0026 已完成自动能力、实时点图与 4 次真实恢复调用，见 [本轮优化验收](refinement-verification-20261102.md)。

日期：2026-11-02，Asia/Shanghai。当前为开发增量 0.0.1，Schema 0009。保留 v2 P0–P3，不进入 P4/P5；未 Commit/Push。核心实现已接入，真实新流程与干净机安装不能记为完成。

## 核心实现

| 任务 | 实现与证据 |
| --- | --- |
| M0 | 审计、305 文件工程快照、4 份 SQLite 一致性备份；修改前 104 Python / 28 React 通过 |
| M1 | 新投影 API 默认五类节点；旧知识无需重跑 LLM；按项目/类型/论文/搜索筛选、限深邻域与 revision 游标，完整领域仍由原 Store 保存 |
| M2 | React Flow 拖动固定、显式解除固定/重排、独立布局版本、自动保存/冲突、待保存本机恢复；按需 Inspector、英文回退、证据与 Zotero 入口 |
| M3 | unified-v3.1 章节 P02，嵌套实验/条件/结果/指标适配原领域；P04 仅显示补译，原始英文、原模型、accepted 状态保留；旧 P01/P02 可选 |
| M4 | 已提交批次跳过，已收到合法响应恢复；timeout/429 有界重试，JSON/来源错误不自动重发；批次状态、调用/用量/未知费用分开显示 |
| M5 | 复用旧 Comparator、P03/P04/P05 推理和审核历史，候选虚线、接受实线、失效隐藏；NO_DECISION 不建边，解释支持中英字段 |
| M6 | 本机回归、迁移副本、冻结引擎和原生复核执行；真实新流程受凭据阻塞，安装与远端 CI 的限制如下 |

## 实际测试命令与结果

Python 均用 Anaconda researchgraph-studio 绝对解释器，未另建环境。

- `scripts/check-phase0.ps1`：Python **123 passed、2 skipped**；Ruff/format/mypy、pip check、OpenAPI/TypeScript 生成通过。脚本随后因 3 份前端格式停下；已格式化并单独完成剩余检查，不把最初脚本记为全绿。
- `pnpm format:check`、`pnpm check`、`pnpm --dir apps/desktop test`、`pnpm build:web`：前端 **33 passed**，TS/ESLint/格式/生产构建通过。
- 详情与拖动修复后 `pytest tests/engine/test_graph_v3.py tests/engine/test_v3_compatibility.py -q`：**19 passed**；前端随后完成拖动修复与原地点击回归，最终 33 项通过。
- `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml`：**5 passed**，含图谱作用域与 Zotero URI 白名单。
- `pytest docs/tests -q`：**12 passed**；独立运行 `pytest docs/archive/v2/tests -q`：**5 passed**。
- `scripts/build-engine.ps1`：冻结 Sidecar 成功；`scripts/smoke-engine.py --executable ...`：在 System32-only PATH 下旧 P1/P2/P3、统一抽取、轻量投影、补译、布局、重启、EOF 退出全部通过。
- Windows PowerShell 5.1 `scripts/verify-windows-install.ps1 -EnginePath ... -PdfFixture tests/fixtures/pdf/two-pages.pdf -OutputRoot .local/v3-powershell-acceptance`：**passed**。此处使用 EnginePath 模式，不等同于安装器安装/卸载测试。

七批故障测试在第 2 批分别注入客户端失败、超时、429、非法 JSON、不存在的证据 ID。每种均保留首批，恢复完成 7 批，再提交相同输入不增加模型调用；超时/429 总调用为 10 次（首批 1、失败尝试 3、恢复 6），其余为 8 次。这些为 **Mock 故障注入**，不是供应商真实故障或科学质量验证。

2 项跳过是 Windows symlink 权限不足；保留 Starlette/httpx 弃用、PyInstaller tzdata 与约 527 KB 前端 chunk 提示。

## 数据与迁移

四份副本从 0004/0005/0008 升到 0009，按旧表旧列逐行比对一致，integrity/foreign_key 检查通过；P3 副本含 2 项目、5 论文、1508 知识节点。0009 只新增 knowledge_display、source_assertions、graph_layouts。旧表新增列来自此前既有 0005–0008 迁移，不应误判为旧字段丢失。证据和审核 ID、ModelRun 原始输出保留。

备份及审计在 `.local/v3-m0/`、`.local/v3-migration-report.json`，真实材料和凭据不在报告源码中。Zotero Local API 只读实测 TEST 分类 5 篇论文、6 个可读 PDF；5 个已有登记来源的 SHA-256 与数据库一致，未改原 PDF 或 Zotero 数据。

原生工具首次按 exe 路径启动时误选了同名已安装版本，该版本正常启动把正式旧库从 **0005 升到 0008**，没有升级到本轮 0009。已关闭，未在其中执行抽取或编辑；随后只读审计确认旧表旧列逐行一致，既有自动迁移备份和本轮 M0 快照都保留。未擅自覆盖/回滚正式数据库。后续改用返回的精确 process 路径及独立 `com.researchgraph.studio.v3test` 标识。

## 原生复核

独立窗口 `ResearchGraph Studio - v3 acceptance` 读取旧 P3 副本：旧项目/论文/任务历史可读；无终端窗口；旧知识直接投影，节点详情显示英文主张与来源状态、第 5 页原文证据；“在 Zotero 中打开”成功启动 Zotero。

原生发现并修复两处自动化单测未覆盖的问题：文献无限分页缓存与图谱筛选缓存键冲突导致白屏；拖动状态与快速指针事件的起始阈值导致移动未生效。已补缓存跨页面用例、统一位置状态并改为按下即可拖动；原地点击不会固定或保存布局。详情关联遍历收窄，防止经共享方法展开不相关主张；相关实验折叠，证据直接可见。

最终原生复核通过拖动、解除/重新固定、缩放和侧栏折叠。数据库确认节点坐标实际变化，布局版本升至 8；关闭再打开后整份布局（位置、固定、缩放与平移）相同，侧栏保持折叠，1508 个知识节点仍可读。正常退出后 ResearchGraph GUI/Sidecar 进程均为 0，无 PowerShell 窗口。记录在本机忽略目录 `.local/v3-native-persistence.json`、`v3-native-exit.json`。

## 安装器与安全检查

本轮 `pnpm --dir apps/desktop tauri build` 正式 NSIS 构建成功，保存在 `.local/releases/v3-m0-m6-20261102/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,441,992 bytes；SHA-256 `A4A9B710DBDEF02508134302653227056775042C33737C8435002978B6ED3253`。仍为开发版本 0.0.1，包含 Schema 0009；安装器未安装或卸载验收。此目录及构建日志均被 Git 忽略。

候选内容/敏感路径及 Gitleaks 扫描 324 文件通过；未 Commit/Push，未触发远端 CI。设计清单 52 项重新计算并逐项校验通过；84 份 Markdown、285 个本地链接、QA 原件 hash 与环境 JSON 通过，四个不可用外部原文单列。最终原生副本的 33 个旧表（排除运行任务与迁移版本表）与 M0 备份逐行相同。

## 真实模型与未完成项

- 旧库保有 compatible 模型配置，但 Windows Credential Manager 对应凭据无法读取。已请用户在独立验收窗口重新保存，密钥不应发到聊天。当前**未调用真实新 P02/P04、未验证真实七批故障恢复、未记录新供应商 Token/费用**；0 次调用不等于费用测量为零。
- 旧 v2 三篇真实论文和三组 NO_DECISION 的记录仍保留，不当作本轮统一抽取成绩。真实关系审核仍须条件可比、双方证据充分的样本，不放宽门槛制造关系。
- 当前已有正式安装与用户库，安装验证脚本主动拒绝覆盖；本轮保留构建安装器与独立原生/EnginePath 验证。新安装器的安装/卸载、干净 Windows、缺失 WebView2、远端 CI **未测**。
- 当前页最多 60 节点、详情相关对象最多 128，完整对象仍在领域 API；大项目全图性能、术语跨论文一致性、真实翻译科学准确率未验收。没有 OCR/逐字框/向量召回/物理实体合并。
- 四份外部补充原文登记路径仍不可用，无法核验原文及哈希；QA 原件和历史登记保留。

后续先补本轮真实 API 和安装验收，之后再单独评估 P4；本轮不进入下一 Phase。
