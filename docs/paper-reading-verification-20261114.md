# PDF 阅读整理与一次全文精读验证 · 2026-11-14

## 范围与实际交付

按用户最新要求，在既有 Lite P2 上增量修改本地阅读整理、展示与生成入口。先处理跨页断段、双栏顺序和材料混入正文，再将默认入口改为“论文精读 → 全文精读”。用户一次明确操作后，A04 一次请求覆盖当前版本全部可读正文，联合生成中文译文、论证批注、五色精确高亮和全文论证摘要。英文原文始终来自本地。详见 [ADR0042](adr/0042-paper-reading-document-and-notes.md)。

保留 PaperCard + LightGraph、A01、A03、个人理解状态、D 问答及旧 A02 结果，不恢复完整 Knowledge Engine、Lint/Wiki、跨论文推理或已撤下的 PDF 翻译服务器。本轮完成后停止，没有 Commit/Push 或远端 CI。本轮真实模型调用、真实输入/输出 Token、真实重试和新增收费均为 **0**。

## 解析整理与界面

- 新增 `reading_projection.py` 及契约/模型/API，使用独立 `reading-document-1` 投影。原始 Chunk、Section、EvidenceSpan、DocumentParse 不重写；每个阅读单元保留源块/Span ID、原文精确跨度、页码、坐标和 SHA-256。
- 双栏按左栏完整阅读后进入右栏；跨栏标题分隔版面区域。字体、段落边界、栏内几何与续文信号共同支持时才组合相邻文字块。跨页和跨栏还要求真实页面尺寸、页末/页首位置及正文边界证据；不穿越标题或图表材料。不确定时保留断段，不让模型补写过渡文字。
- `pdf_structure.py` 增加页面尺寸、嵌入图像与疑似矢量区域元数据。图像只保存定位，不造文字、Evidence 或 Span。表格、图注、图像区域、疑似图内标签进入默认折叠材料区，显示原始换行、页码、分类依据和处理建议；无 OCR 或图表语义分析。
- `PaperCloseReading.tsx` 按标题/正文/材料分别渲染。正文为段落英文、常驻中文与对应中文批注，窄屏逐段堆叠；不再将标题、孤立数字和图内标签全部放入大型译文批注卡片。
- “重新整理本地阅读版面”是显式本地操作：只读登记的源 PDF，必须核对同一 SHA。缺失或改变时保留已有本地原文并提示无法完成的检查。普通 GET 不读取外部 PDF、不发模型；旧解析缺少真实尺寸时不猜测跨页合并。
- 旧 A02 结果、状态与 A03 保留在“理解状态与旧笔记”，默认界面隐藏旧逐范围生成和补调入口。A01 仍可按需单节导读，B/D 与图谱导航保留。

匿名双栏两页样本包括跨页续文、矢量图、`58.0`、`T3: Flights`、表格和图注；PDF 页图及前端桌面/材料/窄屏截图已检查。样本不来自私人论文。

## 数据、API、Prompt 与调用边界

`lite0009 → lite0010` 只新增 `lite_reading_documents` 与 `lite_paper_readings`，沿用升级前自动 SQLite 备份。迁移专项从真实旧结构创建隔离库，逐表验证既有行保持，含非空原文、旧 A02 raw、usage 与任务快照；备份保持旧 head。没有读取或升级用户正式数据库，没有删除外部 Zotero/PDF。

新增本地 API：

- `GET /api/v1/papers/{paper}/reading-document`
- `POST /api/v1/papers/{paper}/reading-document/refresh`
- `GET /api/v1/papers/{paper}/reading-notes`
- `POST /api/v1/papers/{paper}/reading-notes/generate`

运行任务为 `paper_reading_notes`，Prompt 为 `A04_paper_reading_notes_v1`，输出 Schema 为 `paper_reading_analysis.v1`；运行 Prompt 同步到 [模板](researchgraph_lite_ABD/prompts/A04_paper_reading_notes_v1.md)。新增 `paper_reading_api.py/contracts.py/models.py` 接入既有 Provider、worker、统一用量、缓存及启动恢复，Rust 路由白名单和 OpenAPI/TypeScript 契约同步更新。

模型接收完整可读正文、标题上下文及少量稳定材料缺口元数据，不接收材料原文作为正文，不重复输出英文。输出覆盖/顺序/归属、源映射/hash、高亮精确引用及图谱引用均受验证。独立有效段落可在截断或缺段时保留，但整体始终为 `INCOMPLETE`，不缓存为完整结果、不自动补调。

发送前按 ConfiguredProvider 实际构造逻辑检查有效容量，含准确端点限制与输入预留；不读 Key、不联网探测。已知不足时零请求拒绝；未知容量明确提示。一次请求不等于更少 Token，全文译文可能显著增加输出，旧小节预算不作为全文成本结论。

缓存绑定全文、来源、投影、模型配置及 Prompt/Schema 内容；重新整理仅产生临时源文件警告不单独使内容缓存失效。内容变化时旧稿保留并标 `STALE`。每次读取重新验证持久原文与映射，缓存不绕过来源终验。请求前占用持久唯一槽位并原子认领；GET、重复 worker、取消、重启和通用 retry 不自动重发。

## 实际验证

| 范围 | 最终结果 |
| --- | --- |
| 后端全量 `python -m pytest -q` | **272 passed / 1 skipped / 1 warning，63.73 秒** |
| 全文精读后端专项 | **13 passed** |
| PDF 解析与阅读投影专项 | **31 passed** |
| Ruff / 格式 / mypy / pip check | 通过；**98 文件**格式、**64 源文件**类型检查 |
| TypeScript / ESLint / Prettier | 通过 |
| React 全量 | **8 files / 65 passed，8.80 秒** |
| 真实 Edge 浏览器全量 | **8 passed，7.9 秒**，含真实图谱组件、旧精读及全文入口、材料、授权、刷新与窄屏 |
| 前端生产构建 | 通过；现有单 JS 包 **577.65 KB** 提示保留 |
| Rust fmt / clippy | 通过 |
| 安装后 Rust Host 全量 | **11 passed / 0 ignored，2.77 秒**，含启动、重启、schema 与路由安全 |

唯一跳过为既有 Windows 符号链接权限；警告为既有 Starlette/httpx 弃用。较早一轮 271 passed 发生在新增图注回归之前，不作为最终全量成绩。独立审查发现正文 `Figure 1 shows…` / `Table 2 reports…` 可能被误当图注、材料原文换行丢失和普通来源区域文案不准，修复后完成上述回归。图注识别要求编号标点，或邻近图表区域且字体较小；正常图表指代句回归保留为正文。没有剩余已知 P1/P2 审查阻断。

源码与最终安装后 sidecar 分别通过合成 loopback HTTP/SSE 全文 smoke：本地导入、GET、刷新零调用，3 段正文一次 A04，缓存额外零调用，匿名 PDF SHA 不变。**每次独立 smoke 的模拟 usage 为 23 输入 / 41 输出 / 64 总 Token，重试 0，费用未知**；非 loopback 请求零次。这些固定夹具值不能当作真实全文成本。

安装后旧精读兼容 smoke 通过：4 段本地读取，合成 A02 一次、A03 一次、缓存额外零次，自评 `PARTIAL` 保持；模拟 **46/82/128** 单列，不与 A04 混作真实费用。普通引擎 smoke 验证本地解析/索引/阅读状态零模型。

## Windows 安装交付

PowerShell 7 执行 `scripts/build-windows.ps1`，使用项目 Conda Python 完成 PyInstaller、前端、Tauri 与 NSIS。打包前后 **101 个 Python/前端/宿主源文件哈希保持**。封存目录独立，没有覆盖较早章节精读包或日常安装。

- 安装器：`.local/releases/lite-paper-reading-20261114/ResearchGraph-Studio-Lite-Paper-Reading-0.0.1-x64-setup.exe`，**38,522,485 bytes（36.74 MiB）**。
- 安装器 SHA-256：`E0D4999005CF6CFE18ED3C4D7CCD57C49A7BB47B924CC42B5345A00013B87174`。
- 同目录完整 `researchgraph-engine/` 含 `_internal/`；引擎 EXE **15,202,470 bytes**，SHA-256 `B8F53E250DC98CD3580B3FA7BB8A2DC25FF513AF4B13DE91E391F03A0C2D2148`。不可只复制引擎 EXE。

PowerShell **5.1** 隔离静默安装通过；schema `lite0010`、本地 PDF 解析/索引 0 调用、0 输入输出 Token，旧翻译 API 404、没有 `translation-runtime`。安装后 **265 个 sidecar 文件**与封存逐一 SHA 匹配，桌面 EXE 存在。最终安装引擎已完成上述普通、旧精读及全文 smoke 和原生 Host 回归。

使用步骤：关闭旧程序，安装新包；选择已有论文 → 论文精读 → 全文精读。先点“重新整理本地阅读版面”，检查正文和折叠材料；需要全文译文与笔记时勾选本次发送授权并点击“生成全文精读笔记”。不需要删库或重导论文。

## 剩余问题与资料

复杂版面、特殊字体、扫描页、复杂公式和图表检测仍不能保证完整恢复；不确定分类明确标疑似，不确定断段保留。材料区提供页码和核对建议，不对图表作科学解释。真实论文的译文忠实度、论证质量、实际全文 Token/金额、正式 Zotero 库、用户原生 GUI 与干净机尚未验收。

构建、源清单、匿名样本、最终后端日志、安装/资源报告及安装后 smoke/Host 日志保存在忽略目录 `.local/verify/lite-paper-reading-20261114/`。这些本地资料和安装器不进入源码上传。本轮不自动追加真实模型请求或进入其他开发阶段。

最终源码内容/私人路径规则与 Gitleaks **306 文件**通过；本轮 **20 个改动文档 / 103 个本地链接**无缺失，`git diff --check` 通过，暂存为空。未 Commit/Push。
