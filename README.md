# ResearchGraph Studio Lite

ResearchGraph Studio Lite 是一个本地论文阅读辅助工具。它把 Zotero 或本地 PDF 转成可检索的章节和文本索引，再按需生成论文概览、章节导读和局部证据问答。论文选择、PDF 解析和全文索引都在本机完成；没有明确请求时不会调用模型。

当前工作区已经切换到 Lite 基础工程：

- **本地阅读**：连接 Zotero、选择论文、解析 PDF、识别跨页章节、建立 FTS5 文本索引。
- **论文概览**：PaperCard 与 LightGraph 使用一次联合模型调用生成；缓存命中不重复调用。图谱是单篇论文的概念组织，不是独立证据验证。
- **按需阅读辅助**：全文精读使用一次显式模型任务生成全部可读正文的中文译文、五色原文标注、论证批注与全文摘要；标题、正文和折叠图表材料分开展示。阅读整理层保留原始块、页码、坐标与哈希，保守组合跨页续文，支持本地重新整理。A01 小节导读、A03 主动理解检查和旧 A02 历史继续保留。个人状态本地保存，A01 可使用少量相关状态调整侧重点。论文问答先做本地检索，必要时明确启用英文关键词辅助。切换论文、章节或阅读板块不自动请求模型。
- **模型与用量**：设置与诊断中分开管理全局 Provider/Base URL/API Key 连接和模型参数配置；凭据保留在本机凭据存储中，统一记录输入/输出/总 Token、调用、重试、缓存命中和费用未知状态。
- **数据边界**：Lite 数据库从空库初始化，不迁移旧版完整图谱、Query、Lint、Wiki 或历史任务。旧工程回退点保存在 `backup/pre-lite-refactor`。

阅读工作区位于论文页面上方，论文信息收纳到下方默认折叠区域。整篇 PDF 翻译服务器和 PDF 导出流水线仍已撤下；精读译文属于阅读笔记。当前数据库迁移 head 为 `lite0011`：在保留旧阅读数据和本地解析流程的基础上，新增模型文档解析及概览、精读、逐段翻译的独立派生存档。论文工作区可编辑题名、模型章节材料和生成内容，也可逐篇清理旧本地解析/缓存或删除论文；清理与删除前均备份数据库，清理保留个人笔记、模型结果及源文件，删除只清除受控目录内的托管副本。详见 [ADR0040](docs/adr/0040-remove-pdf-translation.md)、[ADR0041](docs/adr/0041-section-bilingual-close-reading.md)、[ADR0042](docs/adr/0042-paper-reading-document-and-notes.md)、[ADR0047](docs/adr/0047-import-time-post-processing-plan.md) 和 [ADR0048](docs/adr/0048-paper-content-management-and-legacy-cleanup.md)。

论文精读与论文问答使用可展开/收起的文章目录侧栏。全文目录随滚动标记当前章节；问答目录同步实际选中章节，不由滚动改变检索范围。公式目前按 PDF 版面保守定位，支持同 SHA 来源的局部 PNG 原图预览；已接入可选的本地 Pix2Text MFR 识别流程，未配置权重时保留原图和 `latex_unavailable`，不会从线性文本猜补。问题定位与后续方案见 [公式解析评估](docs/formula-parsing-assessment.md)，可选运行时见 [公式 OCR 运行说明](docs/formula-ocr-setup.md)，导航边界见 [ADR0043](docs/adr/0043-reading-outline-and-formula-source-boundary.md)。

目录支持一级、二级、三级标题的独立展开与收起。新版解析修复小型大写标题漏检、退化表格误吞小节和印刷目录重复标题。已有论文可在全文精读中点击“重新整理本地阅读版面”，只读同 SHA 来源并增量保存新章节树；旧段落、历史结果与 Zotero PDF 保留，不触发模型。新旧边界与同块跨小节的范围限制见 [ADR0044](docs/adr/0044-versioned-pdf-chapter-tree.md)。

新导入可选择模型优先解析 PDF，按章节保存正文、公式和表格，再按用户选择生成论文概览或全文精读；全文精读可选逐段中文翻译。发送 PDF 前需明确联网授权。公式和表格始终尝试提取，多模态不可用时保留原文并标记降级；图片内容可以跳过。模型文档结果与旧本地 Chunk/Section 阅读数据分开保存。见 [ADR0047](docs/adr/0047-import-time-post-processing-plan.md) 和 [当前进度](docs/progress.md)。

## 文档

阅读内容整理后保存在本机。普通打开校验并读取本地存档，首次或旧存档升级只使用已存原文；只有“重新整理本地阅读版面”才再次读取 PDF。遇到读取错误可点击“重新读取本地存档”，不会触发模型生成。存档与并发读取边界见 [ADR0045](docs/adr/0045-persisted-reading-archive-and-read-transactions.md)。

- [Lite A+B+D 规范](docs/researchgraph_lite_ABD/README.md)
- [LightGraph 补充规范](docs/ResearchGraph_Lite_LightGraph_Addendum/README_ADDENDUM.md)
- [章节双栏精读规范](docs/researchgraph_lite_ABD/ResearchGraph_Lite_Section_CloseReading_Bilingual_Annotation.md)
- [当前项目基线](docs/current_project_baseline.md)
- [清理盘点与保留范围](docs/lite_cleanup_inventory.md)
- [开发进度](docs/progress.md)
- [模型配置](docs/model-configuration.md)
- [文献翻译撤下说明](docs/pdf-translation.md)
- [安全检查](docs/security-checks.md)

当前活跃迁移 head、已完成阶段和未完成范围以 [docs/progress.md](docs/progress.md) 为准。

## 开发环境

Windows 环境使用 Conda 环境 `researchgraph-studio`、Node 24、pnpm 12 和 Rust 工具链。依赖由 `environment.yml`、`conda-win-64.lock`、`requirements-win-64.lock`、`pnpm-lock.yaml` 和 `Cargo.lock` 固定。

```powershell
conda create --name researchgraph-studio --file .\conda-win-64.lock
conda run -n researchgraph-studio python -m pip install --require-hashes -r requirements-win-64.lock
pnpm install --frozen-lockfile
pwsh -File .\scripts\check-phase0.ps1
```

启动桌面开发环境：

```powershell
pwsh -File .\scripts\dev.ps1
```

应用数据写入用户本地的 Lite 数据目录。Zotero 原始附件和私人笔记仍由用户的本机应用管理，不进入 Git。

## 约束

`unknown` 表示信息缺口，不据此推断实验条件、矛盾或数字。模型只能返回受 Schema 约束的内容；正式 ID、来源定位、文件路径、数据库写入和缓存键由本地程序生成和校验。
