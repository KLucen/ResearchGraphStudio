# ADR0047：论文导入时的大模型章节解析与后处理计划（仅设计）

日期：2026-11-17（Asia/Shanghai）

状态：提案；本轮只更新设计，不实施、不迁移、不新增模型调用。

## 背景

当前本地 PDF 解析对复杂双栏、公式和表格的恢复效果不稳定。用户希望选择论文后直接使用大模型，按论文章节结构导出正文、公式和表格内容，再根据选择生成论文概览或全文精读；中文翻译只在选择全文精读时单独决定。图片和图内内容可以在模型没有多模态能力时跳过，但公式和表格必须作为解析结果的一部分尽量提取。

本方案不再把本地 PDF 解析、`reading-document-2`、FTS5 或 SHA-256 作为大模型调用的前置条件。旧版本中的本地解析结果和 SHA 字段继续兼容读取，新导入计划不把 SHA-256 作为 UI 授权条件、发送门槛或缓存命中条件。

## 决策

采用“模型优先的导入解析”：用户选择论文后先创建导入会话和来源快照，再将原始 PDF 文件引用直接交给文档解析模型。模型先输出章节树和按章节组织的材料，再由程序物化模型文档层、章节文本、公式和表格。概览、全文精读和中文翻译依赖这次模型解析结果。

### 1. 模型优先的分阶段导入

1. **选择来源并创建导入会话**

   - Native picker 返回短期 opaque `selection_id`、文件名、页数（若宿主可直接读取）和只读来源元数据。
   - 程序创建 `Paper`、`ImportSession` 和 `source_snapshot`；新模型文档不要求先生成本地 `AttachmentRevision`、Chunk、Section 或 FTS5。
   - Web 层不把任意路径传给 sidecar；模型任务只使用该会话绑定的来源引用。

2. **直接提交文档解析模型**

   - `llm_document_parse` 直接接收 PDF 文件或提供方的文件引用。
   - 首批请求生成章节树、章节顺序和页范围提示；随后按章节或页批次提取正文段落、公式、表格及可选图像材料。
   - 每个批次保存原始响应、模型能力、发送范围、顺序、状态和警告。容量不足时按章节/页批次拆分，不能静默截断。

3. **物化模型解析结果**

   - 程序校验 JSON/DTO、章节顺序、页码范围、bbox 格式、段落归属、表格行列结构和公式状态。
   - 校验通过后生成模型文档层的正式章节、段落、表格和公式 ID，并生成章节文本导出、阅读投影和可选 FTS5 索引。
   - 模型结果属于“模型派生转录”，不能覆盖原始 PDF、历史本地解析、作者原文或已保存知识事实；原始 PDF 和模型 raw 始终保留用于核对。

4. **执行用户选择的后处理**

   - 概览和全文精读是两个独立选项，可以同时选择；两者都未选择时只完成章节解析与材料投影。
   - `paper_overview`：生成 PaperCard + LightGraph。
   - `paper_reading`：生成全文精读分析、论证角色、重点标注、中文批注和摘要。
   - `translation_mode=full|none`：仅在全文精读下决定是否逐段生成 `translation_zh`。
   - 公式和表格提取属于 `llm_document_parse` 的必需材料；图像/图内标签属于可选材料，不单独阻塞正文解析。

解析、概览、精读和翻译分别保存状态。某个后处理失败不会删除论文或其他已成功章节；缺失批次和失败项可单独重试。

### 2. 导入界面

导入流程在提交模型前显示“导入后生成”卡片：

| 选项 | 结果 |
| --- | --- |
| 模型解析并生成论文概览 | 先生成章节正文、公式和表格，再生成 PaperCard + LightGraph |
| 模型解析并生成全文精读 | 先生成章节正文、公式和表格，再生成全文精读 |
| 精读中的中文翻译 | 仅在全文精读下显示；选择 `full` 或 `none` |
| 图片/图内内容 | 多模态模型可选择提取；无多模态时跳过图片并提示需打开 PDF |
| 公式和表格 | 始终尝试提取；多模态不可用时保留线性/原始内容并标记退化，不阻塞正文段落导出 |

提交前显示文件名、页数、章节批次、Provider/模型、文本或视觉能力、预计请求数、Token/费用未知或估算值、发送范围和联网授权。界面不显示 SHA-256，也不要求用户为模型解析确认 SHA。

### 3. 章节与材料解析契约

`llm_document_parse` 可以直接返回模型观察到的结构化材料。程序在校验后生成正式 ID，模型不能生成正式数据库 ID、修改 PDF 或把推测内容写回原始 Chunk。

允许的模型字段包括：

- `chapter_ref`、`title`、`level`、`order`、可选 `page_start/page_end`；
- `kind=paragraph|table|formula|figure|caption`；
- 段落转录、段落作用、原文定位提示和 `confidence`；
- `source_mode=multimodal|text_layer|model_derived`，以及模型能力和输入材料摘要；
- 公式的 `latex` 或 `mathml`、线性原文、`latex_status` 和警告；
- 表格的列、行、合并单元格、脚注、原始表格文本和 `table_status`；
- 图片/图注的定位、原文和 `figure_status`；
- 批次级 `warnings`、缺失页或未解析材料。

程序只做结构和边界校验，不声称模型转录已经证明了科学语义。页码和 bbox 只在模型提供且格式有效时保存；无法确认时保留模型原文并标记 `needs_review`，不凭空补坐标。

### 4. 多模态和无多模态模型的降级

- 有多模态能力时，优先发送原始 PDF 的页图或局部图，尽量恢复上下标、分数、根号、矩阵、积分/求和上下限和表格单元格；公式同时要求 LaTeX/MathML 与可读原文，表格同时要求结构化单元格和脚注。
- 无多模态但支持 PDF/文档文件输入时，发送文件引用和按页/章节的文本要求，`source_mode=text_layer`。公式保留线性原文、页码和 `latex_status=unavailable|needs_review`；不得猜测二维公式。
- 无多模态且只有普通文本输入时，`source_mode=model_derived`。表格可以按文本分隔符尝试恢复；无法确认行列时只保留 `raw_table_text`、页码和 `table_status=degraded|needs_review`，不得把猜测列值写入结构化表格。
- 扫描 PDF 或图像页在无多模态时，不伪造正文、LaTeX、单元格或图内标签；保留原页入口、已获得的图注/定位提示，并把对应材料标记 `unavailable`。正文章节任务仍可完成，公式/表格增强作为可重试的独立子任务。
- 用户可以显式选择“必须使用多模态，否则暂停”。只有这个选项被选中且能力检查失败时才暂停；默认策略是按上述规则降级并继续导出正文。

### 5. 概览、精读和翻译契约

概览输入绑定 `llm_document_parse_id`、`parse_version`、`chapter_projection_id` 和冻结模型快照，继续使用 `paper_overview_graph.v1`。

全文精读使用新的 `paper_reading_analysis.v2`，保留旧 v1 历史记录。请求和缓存身份显式包含：

```text
translation_mode = full | none
```

`full` 要求正文段落生成 `translation_zh`；`none` 保留英文原文、中文论证批注和摘要，但不生成逐段译文。中文翻译属于阅读笔记，不恢复整篇 PDF 翻译服务，也不覆盖作者原文。

正式实施前必须冻结模型角色映射和 Profile 快照，避免任务排队期间全局设置变化。旧本地解析结果可以继续读取，但不会被静默转换成新的模型解析结果。

### 6. 任务、缓存和恢复

建议使用新的加性计划审计层（候选 `lite0011`）：

- `import_sessions`：项目、来源选择、授权、计划快照和整体状态；
- `llm_document_parses`：模型快照、能力、章节/页批次、原始响应、校验状态和降级标记；
- `llm_document_segments`：章节、段落、公式、表格、图注和物化投影；
- `import_plan_items`：解析、概览、精读、翻译和补偿任务的状态、用量、缓存身份、Job 和错误。

新流程使用 `source_snapshot_id + import_session_id + llm_document_parse_id + parse_version + prompt/schema + model_snapshot + translation_mode` 作为缓存和恢复关联，不以 SHA-256 作为必要字段。用户重新选择来源或明确点击“重新解析”时创建新的会话和解析运行。

建议增加：

- `GET /api/v1/import-sessions/{session_id}`：读取导入会话、章节批次和后处理状态；
- `POST /api/v1/import-sessions/{session_id}/items/{item_kind}/retry`：只重试指定失败项或缺失批次；
- 现有 PDF/Zotero 导入请求中的 `post_import_plan` 快照字段。

每个模型子项发送前独立冻结 Provider、模型、参数、Prompt/Schema 和容量预算。沿用 `allow_network`、用量记录和费用 `unknown` 语义；重启时运行中的任务标记为 `interrupted`，不自动重发。任一批次失败只标记该批次缺失，其他批次、原始 PDF 和已生成章节仍可读。

## 不在本轮实施

本轮只根据用户最新要求更新设计文档，不新增模型调用、不修改当前导入 API、不新增数据库迁移、不改变现有本地解析运行逻辑，也不实现 `llm_document_parse`、`paper_reading_analysis.v2` 或导入向导。

正式实施前必须完成：模型文件/多模态能力探测、章节批次与合并协议、公式/表格降级文案、Provider/预算确认、opaque 文件选择句柄、匿名 PDF + 合成 Provider 回归，以及真实论文的成本和科学质量验收。
