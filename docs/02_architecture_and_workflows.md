# 02 — 统一引擎与自动建图工作流（设计 v3.3）

## 职责与数据流

当前P13恢复按[ADR0021](adr/0021-keyed-ranking-and-bounded-correction.md)：合法外壳下独立有效槽位只作私有检查点，缺失/非法槽位最多定向修复一次，完整上下文保留。发送前持久预留账本，每构建至多两个请求槽位（超时计入）；继续重验已有raw，不重发已用槽位。全部槽位经终验和Store再验才发布。旧排序失败通过独立v3后继和P12原响应重验续接，保留谱系，不重新调用已成功P02/P12。

```mermaid
flowchart TD
  UI[Tauri / React] --> JOB[自动构建任务]
  JOB --> SRC[Source Adapter / Parser / Evidence Index]
  SRC --> EX[Candidate Extractor]
  EX --> VAL[Schema / Source Validator]
  VAL --> KS[KnowledgeStore]
  KS --> INT[Paper Integrator]
  INT --> SEL[Core Selector]
  SEL --> KS
  KS --> GP[Graph Projection]
  GP --> UI
  KS --> STRUCT[完整结论单元、合法支撑路径与科学关联]
  STRUCT --> QUERY[未来 Query：命中种子、路径扩展、条件比较]
  KS -->|候选、原文、表格与授权资料补充| QUERY
  QUERY --> ANSWER[有据回答：默认只读]
  ANSWER -->|明确保存并终验| SAVE[经 Store 新增阅读综合]
  SAVE --> DERIVED[独立衍生图层]
  SAVE --> QUERY
  STRUCT -->|明确整理时组织主题与支撑| WIKI[未来 Wiki：文档与逐段版本依赖]
  SAVE -->|明确整理或更新| WIKI
  WIKI -->|有效内容、状态及根来源| QUERY
  WIKI -->|明确授权导出| MD[受管 Markdown / Obsidian]
  LINT[未来 Lint：来源、支撑、依赖与文件诊断] -.-> STRUCT
  LINT -.-> WIKI
  LINT -.-> MD
```

所有模块使用一个 SQLite 知识底座。候选、结论单元、选择记录是不同职责的对象，不创建独立“图谱库/Query 库/Wiki 知识库”。LLM 只产生候选或提案，校验、幂等、事务与发布由代码控制。模块可重构，以可维护性为目标，不为减少修改量保留错误耦合，也不为目录好看重建工程。

图中 Query、保存综合、Wiki 与 Lint 是 P4/P5 待实现模块；当前仍处于 P3/R5。知识图谱组织结构复用 ReadingUnit/ReadingMember、SourceAssertion 及合法支撑闭包，GraphProjection 负责画布分页。后续消费直接读取完整结构，不从画布抓取数据，不为查询重新组一套来源或科学数据库。

## 来源与证据

Zotero Local API 只读；身份由 server/library/item/attachment 区分。PDF 读取前后核对 SHA-256，变动产生新 DocumentVersion，不在旧版本改 offset。原文段落、表格文本/表头/注释、定位及 ModelRun 原输出持久保留。表格不能可靠重建时标 partial/unresolved，保留可解析原始内容、附件定位和原因，不编造行列。

完整证据保留不等于长期复制 Zotero PDF；附件离线时旧索引与知识仍在，并标 source_unavailable。临时回收仅清理任务自有临时文件，不能顺带清理持久证据。直接 PDF 导入延续现有授权引用/托管模式。

解析器复用 PyMuPDF，不引入 MarkItDown。`pdf-structure-1` 包含跨页章节树、按原文保留的块及行/字体/坐标、阅读顺序、表格表头/行列/单元格与合并关系。章节不以换页切断；表格先于标题识别，防止单元格词语成为假章节。References、重复页眉页脚保留并标 excluded，不传入新 P02。无 OCR；章节/双栏及表格恢复是启发式，解析限制进入 warnings。

Alembic 0011 仅新增 `document_parses`，以 document_version_id/parser_version 唯一保存结构 JSON 和源 hash。新 PDF 证据使用完整原文块。既有 Chunk/EvidenceSpan 的文本、坐标、ID 和 offset 不修改；对旧版本补解析先核对源 hash 与全部原文块，不能准确匹配就拒绝写入结构并保留旧证据。解析版本与知识/选择/布局版本独立。

## 自动处理阶段

1. indexing：解析、章节/表格上下文、证据版本；P01 仅结构不足时使用。
2. extracting：P02 对完整语义单元选择性抽取贡献、必要支撑和限制，不逐句实体化。新任务使用 P02_reading_extract_compact_v4 / reading-semantic-1 / section-context-v1；模型只输出 items/links/warnings，程序绑定冻结版本、批次、默认语言和证据短编号。按跨页章节组织，所有章节用相同规则，不设置 6000 字符/48 证据目标。已知上下文不足才按完整段落/表格上下文组拆分；不可容纳的单组明确失败，不截断或丢弃。每批校验后经 Store 保存候选和原输出。
3. integrating：新 finish plan 的 flow_policy=semantic-reading-1。P12_reading_associations_v1 一次读取全部来源有效候选和完整引用证据，仅提出 associations/duplicates/warnings。程序校验端点与来源后，由 Store.form_units 沿全部已验证有向支撑路径形成各 Claim 单元，不依赖模型抄写 member_ids。不重写主张、不物理合并科学语义。
4. selecting：新plan冻结P13_reading_ranking_v3，读取全部程序单元、真实引用原文、疑点与数字排版风险。程序将本次结论短编号固定为assessments对象的required属性；模型只填贡献建议、理由、说明与0–100整数priority，程序稳定排序，同分按冻结输入顺序。旧v1/v2计划保持原协议。原文不支持或必要支撑不可靠时needs_context；程序再执行质量门槛、相关性、重复、覆盖及显示偏好，碎片依据不能成为核心，成员疑点汇总单元。见[ADR0020](adr/0020-evidence-aware-core-selection.md)与[ADR0021](adr/0021-keyed-ranking-and-bounded-correction.md)。
5. publishing：校验单元连通性及选择快照后原子发布。无人工审核节点；失败不会转为待审。

## 硬门槛与语义评估

Schema、证据 ID/版本、精确 offset/hash、局部引用、端点类型和依赖闭合由程序检查。语义支持程度不能只靠 ID 存在来证明，需保留模型辅助评估及不确定性，并用真实论文评价。critical blocking issue、错误归属、证据不足、未解重复不会自动进入核心。有限缺口不影响原意时可展示 caveats；不能把未知条件等同于相同或不同。

所有合法候选持久化；格式/来源失败的响应只存原始 ModelRun 与诊断，不能混入可引用候选。未选候选仍可被检索，严重失效/旧历史驳回对象默认不作为答案依据但保留诊断历史。

## 结论单元

KnowledgeUnit 是 root Claim 与支撑对象的版本化关联，不复制 Claim 文本。UnitMembership 的 association_ids 必须形成同一文献版本内从根到成员的已验证路径，可跨 Experiment→Finding→Metric。视图可以将这些细节平铺在结论分支下，但导航边不冒充直接科学因果关系。跨单元共享方法/条件允许，多论文实体合并仍走独立候选对齐，不自动覆盖旧语义。

## 任务与原子发布

每阶段保存输入快照、Prompt/Schema 哈希、模型配置、原输出、已提交操作键及用量。batch checkpoint 与候选写入同事务；整合/选择失败只重做未完成阶段。已收到合法响应复用；不能把切换密度做成重新抽取。

统一终验 validate_stage 同时用于新响应和 received/succeeded/validation_failed 缓存：传输绑定后检查 JSON/DTO、版本/批次/修订、白名单、原文锚点和当前候选快照，Store 写入时再验。失败分类 protocol/schema/context/evidence，raw 不改，诊断写 stage_validation。仅响应本身不合格才更新 validation_failed/error/finished_at；可信来源或快照变化 response_invalid=false，保留历史 status/error/finished_at，只记本次复用诊断并停止。固定坏响应不能反复命中，也不能为来源冲突重新收费。详见 [ADR0017](adr/0017-semantic-protocol-and-stage-recovery.md)。

新模型快照显式冻结 output_policy。只有官方精确端点/文档模型登记才用 native_json_schema；兼容 API 的 json_object 是 requested，不保证严格 Schema。能力冲突/拒绝不触发额外收费探测或自动降级。源/请求 Schema 哈希及转换审计保留；真实 strict 调用尚未验收。

新 `reading_finish_plan.context_policy=complete-context-v1` 去除 P12 的 26000 字符候选/24000 字符证据、60 候选/8 根/20 窗口及 P13 的 48000 字符/8 单元软件预算，不截断证据或因这些常量拒绝选择。真实端点容量与有界请求时限仍生效，不承诺任意长度论文都能成功单次整合。ADR0015 的上下文改动不改旧 Prompt；本轮独立新语义模板按 ADR0017 接入，领域 Schema 不变。

旧 `reading_windows` 必须在构造新窗口前读取并原样复用；不得为了新策略重跑已成功 P02/P12。旧 finish plan 的 P13 维持原 8 单元分组、输入与检查点键，只移除 48000 字符的调用前阻塞；新计划才采用全部单元一次。来源/候选快照变化仍按版本冲突处理，不静默覆盖旧任务。见 [ADR0015](adr/0015-complete-reading-context.md)。

首次构建可发布通过相同门槛的部分单元，标 partial 和 coverage_gaps；未完成批次不伪称全文图谱。更新期间继续提供上一有效选择版本，构建完成用 expected revision + 活跃指针事务切换。用户修改展示偏好或源变动使输入过期时拒绝旧发布并重新基于最新状态计算。

新语义流程首次整合/排序失败且无旧图时，可发布保守 provisional 视图，ranking_status=pending、build_state=partial、质量相关性 unresolved。仅来源有效、明确论文作者归属、非背景/unknown/speculative、无未解 issues 且非重复代表的 Claim 可显示，支撑仍需合法路径。任务保持失败及继续入口，不冒充核心贡献排序完成；已有图或来源/快照冲突时不发布临时替代。

现有超时保护继续：配置时限内有界请求，区分连接/发送/等待响应/读取；P02 响应超时仅一次拆分未完成根批，子批失败停止。结构计划拆分不破坏完整段落或表格组，无法安全拆分时停止并说明原因。成功批次不重发。按章节组织不保证供应商永不超时；P12/P13 保留真实端点容量与有界停止，不重新引入软件字符或窗口数预算。

## 版本与缓存

- knowledge_revision：语义对象、证据关联及有效性变动。
- selection_revision：核心集合、支撑成员、密度/展示偏好与选择依据。
- layout_revision：坐标、固定和视口；不改变知识或触发 Wiki 内容重算。
- 构建签名：来源/解析器版本、各阶段输入 hash、Prompt/Schema、模型与参数；结构计划额外冻结 parse_artifact_id。原任务计划和成功操作不重排，普通继续需要升级时按 ADR0013 建独立续接；不把新结构计划写回旧 Job。
- 投影/分页缓存绑定上述知识与选择快照、展开单元、过滤条件；游标跨版本拒绝，页内补齐论文/根上下文，不补全部来源线。

## 后续消费与部署

Query 读完整 Store 和 Evidence，不以 GraphProjection 作为检索全集。Wiki 每段跟踪知识 revision、文献版本及证据；选择变化只提示组织可能变化，证据失效才令依赖内容失效。Query 保存与 Wiki 文件导出需明确动作，不加入科学审核流程。

Query 的路径是文本/术语/文档命中种子→合法单元与科学关系扩展→补全方法/实验/条件/结果/限制→根证据终验。导航线只帮助找内容，NO_DECISION、布局相邻和共享证据不能作为推理依据；没有合法关联时回到原文检索，不能猜边。遍历去重并记录所经路径及修订，只扩展问题相关单元，必要支撑不裁断；真实模型容量不足时明确覆盖范围或停止，不直接继承旧 Comparator 的3跳/100节点/48K字符或画布60/120节点限制。旧 Comparator 保留原兼容路径。

Wiki 使用这些结论单元组织主题、共同点、分歧与条件，补充未选候选和原文，不逐节点机械转成Markdown。Lint分开检查科学支撑图、来源/文档依赖图和文件同步；循环自证禁止，普通文档导航可以双向。执行审计、文件扫描和诊断不推进科学图版本；实施时须拆解当前Store.event（包括Obsidian扫描）的递增耦合。

按 [ADR0018](adr/0018-query-wiki-and-obsidian-lifecycle.md) 澄清：当前图谱是结构化论文知识的视图，Wiki 是带逐段依赖的阅读文档，两者不等同。已保存阅读综合（Synthesis/Insight）、Wiki文档/版本及结构化来源共用一个Store；Obsidian Markdown是授权文件载体，私人笔记仍是独立只读来源。完整Wiki运行能力尚未实现。

P4先建立最小文档登记、段落manifest、状态和只读适配，Query同时检索有效Wiki/阅读综合与底层知识/证据；P5再完成文档生成、可靠导出和增量更新。不存在Wiki时不阻塞问答。引用Wiki必须携带文档版本和根来源，不能把综合/文档/原论文三次转述算成三个独立证据；来源依赖不允许循环，普通文档导航链接不受此限制。

内容依赖有效性、草稿/已保存版本、授权用途和文件同步状态分别保存。磁盘缺失不自动令内部有效文档失效；外部手改不继承旧manifest。Query可明确引用仍有效的内部旧快照并提示文件差异，不能声称读到磁盘最新内容；过期科学段落默认不作为当前依据，其他有效段落可用。Query读取时重验当前状态，不依赖上次Lint的报告结论。

Query显式保存新增阅读衍生对象，不改写论文Claim或自动调整论文核心；可选独立衍生图层展示。另行指定“整理/更新Wiki”才创建文档版本，另行“导出/更新文件”才执行授权写入。受管Markdown外部编辑只读快照并记录差异/冲突，不静默回写科学图谱；私人Markdown无受管身份时只能按外部/个人资料使用和检查。Lint覆盖知识、段落依赖、受管文件hash/链接与授权，诊断、修复索引、更新文档和发布文件分开。

保持 Tauri Sidecar 生命周期、回环鉴权、凭据安全、源文件只读。所有新记录与通知经 Store 事务；事件或轮询实现按现有工程演进，本文不宣称已有 outbox/SSE。
