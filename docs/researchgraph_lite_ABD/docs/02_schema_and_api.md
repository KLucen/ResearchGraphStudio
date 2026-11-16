# 02 精简 Schema、证据来源与 API 契约

> 这是基于现有 ResearchGraph v2/v3 的**Lite 设计参考**。设计包以 `lite0001` 作为空基线；当前工程通过 `lite0010` 加性迁移保存本地阅读投影与全文笔记，并保留范围精读、理解状态和已有迁移链，不加载或迁移 Graph/Claim/RelationAssertion 等旧业务表；历史工程通过 `backup/pre-lite-refactor` 回退。整篇 PDF 翻译已按 [ADR0040](../../adr/0040-remove-pdf-translation.md) 撤下，正文译文属于 [P2 精读](../../adr/0041-section-bilingual-close-reading.md) 与 [A04 全文精读](../../adr/0042-paper-reading-document-and-notes.md)。下面的参考 SQL 不直接升级用户数据库。

## 1. 模型分层

1. **Source（现有代码复用）**：Paper、DocumentVersion、Section、EvidenceSpan、Zotero attachment。负责 Lite 来源身份与定位；PDF正文来源仍由 Zotero 持有，旧完整图谱锚点不进入 Lite 数据库。
2. **Lite Artifacts（新增）**：PaperCard、ReadingGuide、QARecord。负责面向用户阅读的派生内容；不是科学论证图谱，不要求每字段实体建边。
3. **Operation Metadata（复用/扩展）**：ModelRun、TokenUsage、CacheEntry、TaskJob，记录预算、缓存、来源版本、错误与费用。

### 映射原则

现有 `papers`、`document_versions`、`sections`、`evidence_spans` 或等价模型**引用原表**，不复制一套Lite版论文库。新增的 Lite表必须引用现有稳定 `paper_id`、`document_version_id`、`section_id`、`span_id`。

### 来源定位 `EvidenceAnchor`

由**本地解析器**生成，不允许LLM编造：

```json
{
  "span_id": "sp-001",
  "document_version_id": "dv-001",
  "section_id": "sec-03",
  "page_start": 4,
  "page_end": 4,
  "char_start": 180,
  "char_end": 326,
  "source_text_sha256": "<hex sha256>"
}
```

说明：页面向用户显示1起始页码；若现有存储以0起始，适配层统一转换，**不重写既有存储约定**。`char_start/end` 均绑定确定的规范化文本版本和Section，必须满足 `0 <= start < end <= len(normalized_text)`。

## 2. B · PaperCard

由一份受限上下文产生一次短卡片（用户主动触发）。模型输出字段统一采用中文为主、引用 `span_id`：

```json
{
  "research_question": {"text_zh":"...","evidence_span_ids":["sp-1"],"status":"supported"},
  "motivation":       {"text_zh":"...","evidence_span_ids":["sp-2"],"status":"supported"},
  "method":           {"text_zh":"...","evidence_span_ids":["sp-3"],"status":"supported"},
  "contributions":   [{"text_zh":"...","evidence_span_ids":["sp-2"],"status":"supported"}],
  "results":         [{"text_zh":"...","evidence_span_ids":["sp-4"],"status":"supported"}],
  "limitations":     [{"text_zh":"...","evidence_span_ids":[],"status":"not_found"}],
  "overall_note": "概览只依据所提供的有限论文片段。"
}
```

其中 `status`：`supported`（有允许ID的片段支持）、`not_found`（输入范围内未找到）、`ambiguous`（有线索但无法确证）。当 status 非supported，`text_zh` 可以为空，不能伪造来源。`contributions/results/limitations` 至多各3条；单字段最长约250中文字符，细则见Pydantic。**不声称卡片覆盖论文全部内容**，以“所选片段的概览”方式呈现。

服务端另存：`id/paper_id/document_version_id/model_run_id/prompt_version/input_hash/created_at/state`。模型不得生成这些字段。

## 3. A · ReadingGuide

一次产出对应一个 `section_id` + `depth` + `input_fingerprint`，**不是整篇论文摘要**：

```json
{
  "section_id": "sec-03",
  "overview_zh":"本节介绍用于社会推理的建模方式与输入输出。",
  "key_points":["关注表示方式","关注推理流程","关注限制条件"],
  "reading_questions":["该方法依赖哪些输入？","作者如何验证模块作用？"],
  "difficult_terms":[{"term_en":"theory of mind","hint_zh":"心智理论，在本节中关注其他主体状态推测"}],
  "evidence_span_ids":["sp-03","sp-04"],
  "needs_more_context":false,
  "caveats":[]
}
```

`depth = quick|standard|deep` 由用户输入决定，不由模型自选。`section_id`必须是本次允许集合中的单一小节。结果须与源章节版本绑定，默认只读缓存；修改正文后标记 stale 而不静默更新。

## 4. D · PaperQA

模型只看到用户问题、作用域、至多3–5个引用片段及可选卡片/小节标题摘要，不可访问整个项目的旧完整图谱（用户选用高级模式除外）。

```json
{
  "answer_zh":"在提供的第3节原文中，该词指……",
  "evidence_citations":[{"span_id":"sp-21","reason_zh":"提供了术语定义"}],
  "insufficient_evidence":false,
  "uncertainty_zh":"",
  "suggest_expand_scope":false
}
```

如果不足：`insufficient_evidence = true`，回答应明确指出无法由当前证据确定，可以建议扩展 `section → paper`；不得引用未提供的ID，不得假造论文页码。`qa_records` 保存 `scope`, `question_text`, `answer`, `citations`, `retrieval_run_id`, `model_run_id`, `created_at`，不自动更新Graph知识实体。

## 5. RetrievalHit 与索引

**本地索引**使用现有 SQLite FTS5（或等价已实现检索）。记录 `span_id/section_id/document_version_id/text_hash/page_start` 和可检索 `text`。归属必须与用户当前授权论文一致，默认只检索当前章节；若整篇范围，先FTS排序再挑有限Top-K并限制每片长度。

- 选中文本/片段优先于全文搜索。
- 引用片段必须来自本次检索结果；检索结果得分低时显示不确定性。
- 中文问题和英文索引不匹配时，利用本地卡片/标题的双语词汇表补充关键词；**仅当用户允许**且初检索不足时调用可选的小Prompt关键词转换。
- 问题涉及数学公式、表格或图像，而本地解析无法可靠获得内容时，提示模型证据受限，允许用户手动提供图表内容，不编造数值。

## 6. 缓存与失效（Token节省的关键）

缓存键必须由确定性输入生成：

```text
sha256(canonical_json({
  task_kind, paper_id, document_version_id, section_id?,
  scope?, question_normalized_hash?, retrieval_hit_ids_and_hashes?,
  input_span_ids_and_hashes, prompt_version, schema_version,
  provider, model_id, decoding_params, language, depth?
}))
```

`question_normalized_hash` 至少做 trim/空白标准化；不要为语义不同但表面相似的问题共享答案。Base URL如果会改变模型行为，应纳入安全的配置指纹（不要纳入API Key明文）。源PDF、解析版本、Prompt、模型、参数或检索结果改变，都要形成新缓存键；旧结果保留 `stale` 状态供用户查看。

- 查缓存命中后立即返回，**不调用模型**；`force_regenerate=true`才绕过。
- 同一任务重复点击应合并进行中的请求（single-flight），避免并发双重计费。
- 超时和可重试错误采用有限指数退避；每次尝试都有独立 `ModelRunAttempt`，保存已成功结果，不重复覆盖。

## 7. TokenBudgetPolicy 与用量记账

预算目标（每次输入+输出总Token）：

| 任务 | 默认预算目标 | 关键限制 |
|---|---:|---|
| 本地PDF索引 | 0 | 不触发LLM |
| B 卡片 | 6k–12k | 控制源段落、最多6栏和各3个子项 |
| A 单节导读 | 3k–6k | 只传Section范围；默认简短输出 |
| D 单次问题 | 2k–5k | Top-K=3–5；上下文上限；最多一次扩展需再次确认 |

预算按Provider返回的输入/输出token分项记录；若Provider无usage，保存估算及 `usage_source=estimated`，不得伪装成实测。**估算上限是软性预检**：无可靠tokenizer时不能保证实际精确限额，必须通过输入字符/字节上限、模型max_output_tokens和请求阻断形成保守保护。

用户可设置单请求、单篇累计、单日模型消耗上限；超出需用户明确确认。重试Token计入总消耗；缓存读取计入0新消耗，提供已节省估算值但不假报供应商优惠。

## 8. API 建议（可适配旧路由）

| 动作 | 接口建议 | 说明 |
|---|---|---|
| 章节树 | `GET /papers/{paper_id}/sections` | 复用既有API |
| 卡片详情 | `GET /lite/papers/{paper_id}/card` | 包含cache/stale/generation状态 |
| 生成卡片 | `POST /lite/papers/{paper_id}/card/generate` | 幂等键，模型请求需要显式用户操作 |
| 小节导读 | `GET /lite/sections/{section_id}/guide?depth=standard` | 查询缓存 |
| 生成导读 | `POST /lite/sections/{section_id}/guide/generate` | section专属 |
| 问答 | `POST /lite/qa` | paper_id, scope, section_id?, question, requested_top_k? |
| 英文关键词辅助 | `POST /api/v1/papers/{paper_id}/qa/keywords` | 仅本地检索无命中且用户明确授权；只发送标题、章节标题和问题，返回可轮询的 KeywordView |
| 英文关键词状态 | `GET /api/v1/papers/{paper_id}/qa/keywords/{keyword_id}` | 读取生成状态；完成后关键词只用于重新执行本地 FTS5，不自动生成回答 |
| 来源证据 | `GET /sources/spans/{span_id}` | 有权限的短片段与Zotero定位，不暴露任意文件路径 |
| Token统计 | `GET /lite/usage?paper_id=...` | 含retry、cache hit、实测/估算 |
| Lite任务 | `GET /jobs/{id}` | 尽量复用已有任务系统 |

接口安全：Sidecar仅监听loopback并校验本机会话令牌；项目授权限制论文范围；禁止随意文件路径与SSRF；GET不得触发模型调用。流式输出可选，不是Lite首版必需项。

## 9. 持久化草案与数据兼容

新增 `lite_paper_cards`, `lite_section_guides`, `lite_qa_records`, `lite_cache_entries`, `lite_token_usage`（详见 `schemas/sqlite_reference.sql`）。正式迁移应基于现有Alembic历史实现，只新增字段/表和索引。

Lite 干净工程不包含 `claims / evidence / graph_nodes / relation_assertions / wiki_*` 等旧业务表，也不提供旧 API 入口；运行时使用独立 Lite Schema（head 为 `lite0010`，包括章节导读、D01 局部问答、D02 英文关键词、全局模型连接、范围精读、个人理解状态、本地阅读投影、全文笔记及历史翻译兼容结构），不读取或迁移旧图谱。旧用户需要访问历史数据时，使用 `backup/pre-lite-refactor` 和原工程数据目录回退，不把旧历史混入 Lite 数据库。

2026-11-12 撤下翻译时不执行数据库 downgrade、重新初始化或数据删除。既有翻译表、配置、任务快照、用量及生成文件保留，历史实际或未知用量不回写；前端设置、翻译 API、worker、代理和随包资源移除，旧任务不能恢复或重试。`lite0008` 只表达迁移兼容边界，不表示翻译功能仍然启用。

## 10. 安全与权限不变量

- 模型只能引用传入的 span IDs；LLM不能自己生成PDF页码、Zotero路径、正式主键。
- SQLite保存原文索引和用户提问等敏感研究数据时须留在本地，不提交GitHub；提供清除缓存选项。
- 更新本地版本采用事务；遇到PDF文件变化不在旧证据上进行覆盖式重提取。
- `.gitignore`、Secret Scanner、日志脱敏、系统安全密钥存储继续沿用旧工程规范。

## 11. P2 双栏精读兼容契约（2026-11-14 较早阶段）

`lite0009` 增加 `lite_section_close_readings`、`lite_understanding_checks`、`lite_reading_states` 和 `lite_concept_understanding`，不修改旧成果或外部文件。完整模型 DTO 见 [补充规范](../ResearchGraph_Lite_Section_CloseReading_Bilingual_Annotation.md)，运行 API/响应外壳以 `packages/contracts/openapi.json` 为准。

| 路由（均在 `/api/v1` 下） | 作用 |
| --- | --- |
| `GET /papers/{paper}/sections/{section}/paragraphs` | 本地读取稳定段落 ID、原文、页码、hash、Span IDs |
| `GET /papers/{paper}/sections/{section}/close-reading` | 按版本、段落范围或 result_id 读取已生成结果；不发模型 |
| `POST /papers/{paper}/sections/{section}/close-reading/generate` | 显式一次 A02；缺段重试传 retry_missing_of |
| `GET/PUT /papers/{paper}/sections/{section}/reading-state` | 本地进度、自评、疑问和未解概念 |
| `GET/POST /papers/{paper}/sections/{section}/understanding-check` | 读取结果或主动提交 A03；POST 也兼容 `/generate` |
| `GET /papers/{paper}/concept-understanding` | 当前及待重新关联的个人概念状态 |
| `PUT /papers/{paper}/concept-understanding/{node}` | 本地修改自评和个人笔记，不改图谱语义 |

英文由 Chunk/Span 一致性校验后读取，输出不包含英文全文。A02 `COMPLETED` 与 `INCOMPLETE` 明确分开；重试后原范围可从合法后继恢复已缺段译文，但不把子范围摘要提升为整节摘要。高亮原文不匹配和外来图谱 ID 单独移除。A03 只更新可靠关联节点的 last_check_result，自评不被模型覆盖。A01 可显式传 adaptive，并最多加入三项可靠相关状态；理解状态更改不改变 A02 缓存。

## 12. 当前阅读整理与全文笔记

`lite0010` 增加 `lite_reading_documents` 与 `lite_paper_readings`。阅读单元通过 sources/regions 保存原始 Chunk、Span、原文跨度/哈希、页码和坐标；阅读投影不覆盖源表。正文、标题、折叠材料分别为 paragraph、heading、material。已有 A02/A03 和个人状态表保留。

| 路由（均在 `/api/v1` 下） | 作用 |
| --- | --- |
| `GET /papers/{paper}/reading-document` | 从本地已索引原文建立/读取阅读投影；不读外部 PDF、不发模型 |
| `POST /papers/{paper}/reading-document/refresh` | 明确本地重新整理，可从登记且哈希相符的 PDF 补充图像/版面信息；零模型 |
| `GET /papers/{paper}/reading-notes` | 读取当前或指定 result_id 的全文笔记；不自动生成 |
| `POST /papers/{paper}/reading-notes/generate` | 用户显式授权，一次全文模型请求；有效容量不足时零请求拒绝 |

阅读投影版本及内容、原始来源、Prompt/Schema 内容与模型参数共同决定新缓存身份。原文或投影变化只将旧笔记派生为 STALE，旧 raw 和成果保留。旧小节 A02 API 继续兼容，但默认界面不提供逐段范围生成。完整运行 DTO 以导出 OpenAPI 为准。[ADR0042](../../adr/0042-paper-reading-document-and-notes.md) 说明范围覆盖关系。
