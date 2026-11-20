# ResearchGraph Studio Lite

ResearchGraph Studio Lite 是一个论文阅读辅助工具。导入默认在本机解析 Zotero 或 PDF，建立正文、章节和检索库；也可明确选择模型解析并授权发送 PDF，按章节保存正文、公式和表格，再按选择生成概览、全文精读及可选中文翻译。已有论文支持本地解析重试和后续模型重新解析；没有明确请求时不会调用模型。

当前工作区已经切换到 Lite 基础工程：

2026-11-20 研究内容知识库：新增独立“知识地图 / 论文知识 / 联系汇报”工作空间，位于研究项目和任务记录之间。已有概览可零模型收藏；新`paper-knowledge-1`按本地或模型解析材料生成带来源的五类知识，程序绑定论文题名根、身份和真实引文。配置`knowledge_extract`、`knowledge_connect`模型用途及范围/预算后，可对后续解析自动建模、分析联系并保存未读汇报。K1–K3运行代码与专项回归已落地，整体回归、安装交付和GitHub状态以[本轮验证](docs/knowledge-library-verification-20261120.md)为准；合成Provider结果不代表真实科学质量验收。实现边界见[ADR0060](docs/adr/0060-durable-research-knowledge-library.md)和[实施方案](docs/research-knowledge-base-plan-20261120.md)。

2026-11-20最新调整：精读去掉重复英文摘录卡，分析从原文右侧起点直接显示，紧凑类型/编号支持双向定位；本地与模型稿每章的阅读状态放到全部小节和材料后的章末。已有合法笔记无需重新生成。见[ADR0059](docs/adr/0059-reading-analysis-and-chapter-end-progress.md)和[验证报告](docs/reading-sidebar-footer-verification-20261120.md)。原摘录卡方案保留于[ADR0058](docs/adr/0058-anchored-reading-annotations.md)。

2026-11-19 后续修复：精读新任务使用固定编号槽位并区分传输、空响应与格式失败；论文回答先读目录、按需读取章节。两种来源统一“论文概览 / 论文精读 / 论文回答”，圆形“论文解析操作”展开四项解析/查看操作。精读标记可在用户明确操作后做无模型的部分恢复，head为`lite0015`，见[ADR0057](docs/adr/0057-reading-output-and-workspace-recovery.md)及[本轮验证](docs/workspace-fixes-verification-20261119.md)。

2026-11-19：本地与模型材料共用 PaperCard + LightGraph 概览及双栏精读组件，公式使用安全 KaTeX 预览，译文位置与论证批注保持一致。概览、精读默认不生成，须明确选择；已有模型提取稿可补生成或仅补译文。旧摘要保留，不能直接转成图谱或高亮。契约失败有本机响应材料时可显式授权一次格式修复，费用另计，不重传 PDF。该轮加性迁移 head 为 `lite0015`，见 [ADR0056](docs/adr/0056-unified-reading-from-parser-sources.md) 和[验证报告](docs/unified-reading-verification-20261119.md)。

- **论文导入**：连接 Zotero 或选择本地 PDF，默认本地解析并建立 FTS5 索引；可显式选择模型章节解析、配置独立论文解析模型及真实文件输入能力，显示实际阶段。已有论文可在本地和模型解析之间选择查看或重新生成。
- **论文概览**：PaperCard 与 LightGraph 使用一次联合模型调用生成；缓存命中不重复调用。图谱是单篇论文的概念组织，不是独立证据验证。
- **全文精读**：章节正文和公式表格结合已选精读/翻译结果显示；大章节下可标记“未开始 / 阅读中 / 已读完”，目录显示完成状态并提供继续阅读。小节导读与独立理解状态入口已移除，旧笔记、自评和问题保留。旧本地论文仍可读取全文笔记和使用局部证据问答。切换论文、章节或阅读板块不自动请求模型。
- **模型与用量**：设置与诊断中分开管理全局 Provider/Base URL/API Key 连接和模型参数配置；凭据保留在本机凭据存储中，统一记录输入/输出/总 Token、调用、重试、缓存命中和费用未知状态。
- **数据边界**：Lite 数据库从空库初始化，不迁移旧版完整图谱、Query、Lint、Wiki 或历史任务。旧工程回退点保存在 `backup/pre-lite-refactor`。
- **长期知识库**：收藏快照、带来源知识版本、专题、独立布局和双侧依据的联系汇报持久保存。归档不删除成果；从研究项目移除论文保留独立知识，永久移除知识需单独明确操作。浏览、筛选、拖动及打开报告不调用模型；生成与自动策略另有授权和累计预算。

阅读工作区位于论文页面上方，论文信息收纳到下方默认折叠区域。整篇 PDF 翻译服务器和 PDF 导出流水线仍已撤下；精读译文属于阅读笔记。当前数据库迁移 head 为 `lite0018`：`lite0016`–`lite0018`加性增加独立知识库、来源建模、关联请求槽及持久汇报，保留旧阅读数据、模型文档、生成内容与大章节阅读进度，升级前自动备份。论文工作区可编辑题名、模型章节材料和生成内容，也可逐篇清理旧本地解析/缓存或删除论文；清理与删除前均备份数据库，清理保留个人笔记、模型结果及源文件，删除只清除受控目录内的托管副本。详见 [ADR0040](docs/adr/0040-remove-pdf-translation.md)、[ADR0041](docs/adr/0041-section-bilingual-close-reading.md)、[ADR0042](docs/adr/0042-paper-reading-document-and-notes.md)、[ADR0047](docs/adr/0047-import-time-post-processing-plan.md) 和 [ADR0048](docs/adr/0048-paper-content-management-and-legacy-cleanup.md) 和 [ADR0049](docs/adr/0049-import-recovery-and-chapter-reading-progress.md)。

论文精读与论文问答使用可展开/收起的文章目录侧栏。全文目录随滚动标记当前章节；问答目录同步实际选中章节，不由滚动改变检索范围。公式目前按 PDF 版面保守定位，支持同 SHA 来源的局部 PNG 原图预览；已接入可选的本地 Pix2Text MFR 识别流程，未配置权重时保留原图和 `latex_unavailable`，不会从线性文本猜补。问题定位与后续方案见 [公式解析评估](docs/formula-parsing-assessment.md)，可选运行时见 [公式 OCR 运行说明](docs/formula-ocr-setup.md)，导航边界见 [ADR0043](docs/adr/0043-reading-outline-and-formula-source-boundary.md)。

目录支持一级、二级、三级标题的独立展开与收起。新版解析修复小型大写标题漏检、退化表格误吞小节和印刷目录重复标题。已有论文可在全文精读中点击“重新整理本地阅读版面”，只读同 SHA 来源并增量保存新章节树；旧段落、历史结果与 Zotero PDF 保留，不触发模型。新旧边界与同块跨小节的范围限制见 [ADR0044](docs/adr/0044-versioned-pdf-chapter-tree.md)。

新模型解析默认按页顺序分批，每批最多5页（可选2–8页，含相邻前1页共享），根据已知容量只缩小范围；保存原始页码和已校验检查点，失败后明确继续仅处理未成功批次。支持直接PDF文件或页面转图片，两者都需要明确联网授权和端点实际能力。格式修复默认关闭，单独授权后每失败抽取批次最多额外1次文本请求，不重传PDF；边界按需最多B−1次检查，无法确认或复杂表格保留needs_review，不宣称全文无缝。预算是B次抽取＋授权边界最多B−1次＋授权修复最多B次，显式重试可能再次收费；概览/精读/翻译另计。默认600/1800秒均为单请求时限，不是整篇SLA。公式表格始终请求提取，无法识别页显式保留缺口，模型结果不混写旧本地Chunk/Section。旧任务未开批次沿用原路径。见 [ADR0052](docs/adr/0052-resumable-document-batches.md)、[本轮验证](docs/document-batches-verification-20261118.md)、[模型配置](docs/model-configuration.md) 和 [当前进度](docs/progress.md)。

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
