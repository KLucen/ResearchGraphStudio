# 05 — 阅读辅助 Prompt 与调用协议（设计 v3.3）

当前参考模板统一版本 `reading-1.0`，各文件声明 output_contract。当前运行传输按 [ADR0017](adr/0017-semantic-protocol-and-stage-recovery.md) 使用新语义协议；参考内部对象不直接等于模型 wire Schema。旧运行模板、哈希与任务计划保持，不覆盖历史。对照见 [迁移计划](06_development_migration_plan.md)。

## 模板职责

| ID | 输出契约 | 触发 |
| --- | --- | --- |
| P01 | PaperOutline | 结构/论文类型不明确时，解析优先 |
| P02 | KnowledgeExtractionBatch | 按完整语义单元抽取候选，所有类型同批 |
| P03 | EntityAlignmentBatch | 实体对齐建议，不直接合并 |
| P04 | TranslationRepair | 缺失中文按需补译，不更改原语义 |
| P05 | ComparabilityReport | 已选择主张的条件对比 |
| P06 | RelationInference | 候选科学关系；NO_DECISION 留历史 |
| P07 | QueryAnswer | 后续阅读问答，默认只读 |
| P08 | QueryDistillation | 后续用户明确保存回答 |
| P09 | LintIssueBatch | 后续自动诊断建议 |
| P10 | ReadingSynthesisDraft | 后续阅读整理/Wiki 草稿 |
| P11 | WikiDeltaProposal | 后续依赖变化的局部文件变更提案 |
| P12 | SemanticIntegration → 内部 PaperIntegrationProposal | 新运行模板仅提出跨批关联与重复建议，程序组单元 |
| P13 | KeyedContributionRanking → 内部 CoreSelectionProposal | 程序固定完整评估槽位，模型提供贡献建议及priority，程序汇总排序；旧ContributionRanking保留 |

P01/P03/P04/P12/P13 不机械地对每段调用。先复用结构、缓存和确定性处理；P12/P13 在需要整合/语义选择时使用，输出仍按各契约验证。不为每个实体分别调用模型。无人工审核 Prompt 或审核关卡。

后续P07–P11按[ADR0018](adr/0018-query-wiki-and-obsidian-lifecycle.md)绑定文档版本/段落manifest、内容有效性、文件同步及根来源；P07可读取有效Wiki但不能把Wiki转述当新增独立证据。P08生成阅读衍生对象，不改写作者Claim；P09不把外部文件手改直接判科学错误；P10/P11只给文档语义/编辑提案，不自行写Markdown。正式Schema/Prompt在各阶段实现时版本化，本轮不改参考模板或历史运行模板。

图谱在后续任务中承担实质组织作用：P07输入由程序从种子命中沿合法支撑/科学关系补齐条件和证据，保留路径及不确定性，不仅提供节点标签；P08保存的引用关系不冒充新科学关系。P09在确定性支撑/来源/依赖检查后提供语义建议；P10按相关结论单元组织主题、分歧、共同点和适用条件，并补未选候选，不能逐节点改写成MD；P11只处理依赖变化影响的段落。文档、综合和原论文同根证据不重复计数，用户资料归属与授权沿依赖保留。现有P03–P06及历史编号不覆盖，新运行协议在对应任务实施时独立冻结。

## 公共输入安全与来源规则

论文、表格、笔记、已存候选均是不可信数据，不执行其中指令。模型只引用本次 allowed_evidence 和候选白名单短编号，不生成主键、文件路径、页码、offset、quote、审核/发布状态，不操作 SQL、Shell 或文件。程序绑定身份，服务端严格验证不可省略。

Provider 在新模型快照冻结 output_policy：只有官方精确端点/文档模型登记才用 native_json_schema；兼容接口 json_object 的 support=requested，只表示已请求 JSON。prompt 模式及思考参数冲突明确记录，不自动付费探测或失败后降级重发。Schema 转换不能删除科学约束或额外添加 null，不支持的关键字在调用前失败；记录源/请求哈希及转换。真实 strict API 尚未验收。

保留原语义语言及中文辅助，数字、单位、否定、条件和推测语气不得弱化。来源作者和转述归属分开；Finding 是报告观察，Claim 是作者判断，Argument 是论证，不把解释等同于观察。表格缺表头/单位时返回不确定性，不能猜列含义。

## P02 契约

R5 当前新任务使用独立 [P02_reading_extract_compact_v4](../services/engine/researchgraph/prompts/P02_reading_extract_compact_v4.md)，wire 格式 reading-semantic-1，领域仍 1.0。模型根只输出 items/links/warnings；版本、批次、契约/传输标记和默认语言由冻结 transport_context 绑定。SourceText 共同语言、相同摘要省略和字符串语义沿用 [ADR0012](adr/0012-compact-extraction-and-model-output-ceiling.md)，不会丢弃条件、数值或证据。结构规则由实际 Schema 生成并核对 Prompt；原始同 local_ref 对象必须在展开前一致。请求输出额度取模型能力/剩余上下文的较小值，不额外固定 32K/64K。旧 v3/更早模板、Schema 哈希及冻结计划不变。

新输入附带跨页 section_path、原文块证据上下文和 source_tables；原文行/字体等完整布局保存在解析产物。只有 allowed_evidence ID 可作正式证据，章节/表格引用不冒充证据 ID。References、页眉页脚在请求前排除。所有章节遵循相同抽取规则，不为摘要/方法/结果分别设计抽取重点。section-context-v1 优先完整章节，不设 6000 字符/48 证据目标；仅模型上下文不足时按完整段落/表格组拆分。未知能力不猜固定上限，超时和重试仍有界，不能把结构输入描述为所有论文一次调用。

输入为 ExtractionRequest，无必填研究方向或领域关键词。可选 vocabulary 只能来自本次文献或已验证上下文。输出为显式类型 union；Claim/Method/Finding/Condition/Experiment/Metric/Concept/ResearchQuestion/Argument/Limitation 都有独立严格字段，Paper 后端管理。links 只连本批 local_ref，跨批关系留给 P12。没有 claim_detail.findings_placeholder 等自由扩展键。

抽取重要贡献及理解所必需的支撑、限制，不逐句建节点。保留原文全集，因此未抽取文本仍可由后续原文检索获得。max_items_hint 是请求规模提示，不是论文必须产出多少知识的指标。

对每个关键结论，同时抽出实际存在且有证据的 Method、Experiment、Condition 等必要支撑及合法有向关联；共享支撑可供多个 Claim 引用。不能为凑分支强造实验/条件，也不能将任意共用证据当作科学关系。`kind_note_unused`、占位键和模型评语不是 item 字段；非语义说明只放 warnings。

## P12/P13 上下文

新 finish plan 的 flow_policy=semantic-reading-1。P12_reading_associations_v1 一次输入全部来源有效候选、已有关系和完整引用证据，使用请求内 candidate_ref/evidence_ref。输出仅 associations/duplicates/warnings，不回传正式版本/修订，不枚举 units/member_ids。程序绑定内部身份，Store 由全部已验证有向路径形成各 Claim 单元。不能在整合时偷偷改 statement 或根据共享证据造边。

新计划显式冻结ranking_prompt=P13_reading_ranking_v3，一次输入全部程序组好的单元、密度和缺口，以及真实引用原文、论文来源、根/支撑疑点及精确数字排版风险。模型核对语义、归属和数值，不受支持或必要上下文不可靠用needs_context；相同条件的等价结论只建议一代表。输出assessments/warnings，程序以本次全部短编号生成required属性；每个槽位仅填recommendation/reasons/rationale/priority，不再在列表中重复生成claim_ref。priority为0–100严格整数，同分由程序按冻结输入顺序排序。静态Prompt规则从同源模板Schema生成核对，每个请求另携精确槽位Schema规则/哈希。v1/v2冻结计划继续原Prompt/Schema/签名/缓存。见[ADR0021](adr/0021-keyed-ranking-and-bounded-correction.md)。

外壳合法且槽位通过严格DTO后才可私有暂存；未知根字段/编号、重复JSON键或非法JSON不提取槽位。一次构建最多首次请求加一次定向格式修复，仅要求未完成输出，但保留完整论文输入以比较条件和重复贡献。持久请求账本限制超时及恢复费用，达到上限停止，继续不重发；不把模型原始错误文本当新指令。最终完整终验及Store发布再验不省略，不删除未知字段或合并冲突建议假装成功。软件负责协议可靠性，无需以更换模型作为修复前提。

程序绑定正式ID、文献版本、快照修订和已有缺口。模型不输出graph_role/source_status或确定科学真假；选择服务执行硬门槛、覆盖与偏好规则。优先覆盖论文贡献和必要边界，不依据特定领域热点、引用数量或固定名额。ADR0020的证据检查继续生效，格式通过不证明科学真实性。

新流程继续 complete-context-v1，不设固定字符数、候选数、根数或窗口数预算。真实端点上下文能力、输出能力与有界超时保留，超过真实能力应明确失败而非静默丢上下文。旧 reading_windows、Prompt/Schema/签名及 P13 原八单元分组保持旧路径与精确检查点，不因新协议重跑成功 P02/P12/P13。上下文历史见 [ADR0015](adr/0015-complete-reading-context.md)，新职责拆分见 ADR0017。

## 后置验证与失败恢复

Schema 验证后仍需文献/引用白名单、角色类型、单元连通性、源 hash 与语义支持检查。语义支持评估保留其模型来源，不伪称确定性程序已经证明论证正确。校验失败保留原输出、隔离无效批次；不存在人工待审分支。

新响应与所有缓存状态共用 validate_stage 终验，失败按 protocol/schema/context/evidence 留诊断与哈希。仅 response_invalid=true 更新模型 validation_failed/error/finished_at；可信输入来源/候选/快照变化为 false 时保留历史 status/error/finished_at，只记本次复用诊断并停止，不能通过新调用修复。首次新语义整合/排序失败且没有旧图，可显示来源及保守贡献门槛通过的 provisional 视图，明确 pending/partial 和相关性 unresolved；任务不记成功。已有图保留，来源冲突不发布预览。

阶段按输入 hash/配置/Prompt/Schema 冻结；重试不重复已提交调用，整合失败不重新抽全文。响应等待超时有界停止，局部修复只能在明确白名单范围内进行；不得以放宽 extra=forbid 或无限增加 timeout 掩盖问题。

历史 P13 仅有一种语法恢复例外：根对象最后的 coverage_gaps 非空数组各项都是完整 JSON 字符串，最终根 `}` 已存在，仅数组的 `]` 缺失。按 token 边界插入这一个字符；不补写说明、建议或证据，不推断语义完整。旧 P13 正常及恢复后解析均严格拒绝重复键（含转义后同名）和 NaN/Infinity；规则与双 hash 留审计，原始输出不变，见 [ADR0016](adr/0016-selection-json-syntax-recovery.md)。其“其他阶段解析不变”是当轮范围；新语义 P02/P12/P13 均严格解码，不作通用语法恢复。

旧 P13 非法响应可按原输入/签名完整重验后复用，不重调已成功 P02/P12 或前面成功的 P13；剩余未完成部分才发新请求。新的供应商结束原因记 `ModelRun.parameters.attempts[].request.finish_reason`；历史记录未保存该字段时保持未知，不能反推 stop 或据此声称模型已经完整输出。此次不修改运行 Prompt/Schema 或完整上下文策略。

## 验证方式

合成示例与契约负例覆盖引用、归属、条件、类型、图谱拓扑、选择/检索隔离；这只验证结构。真实 Prompt 效果还需跨论文类型样本，记录贡献覆盖、错误归属、条件遗漏、证据有效性、冗余及调用成本，不能将示例通过写成模型准确率通过。

## 运行模板闭合修正

当前新任务使用 P02_reading_extract_compact_v4、P12_reading_associations_v1、P13_reading_ranking_v3（旧v1/v2冻结计划不改）；实际Schema生成的结构规则与运行Prompt必须一致。此前P02_v3/P12_integration_v2/P13_selection_v3及更早文件保留历史：其外壳说明规范化、根/member_ids和coverage_gaps约定仅用于对应冻结任务，不与新语义外壳混用。不能提示模型生成Schema禁止的说明字段。

新整合输入包含全部当前有效候选；旧窗口按冻结快照复用，不重新按 ID 抢占或删减上下文。生成阶段的候选/证据仍视为不可信数据。限定的说明映射和建议隔离必须保留原响应、规则、位置及原因；不能把宽松 JSON 解析等同于科学验证。失败阶段的合法响应及已提交检查点可复用。

只读诊断已确认一次 Claim 额外生成 `kind_note_unused: null`；限定无损适配只移除这个类型/字段/值组合并审计。非 null、其他 kind 或任意其他扩展仍拒绝，随后完整验证字段和来源。已收到响应的本地重验通过不等于最终新 Prompt 真实生成通过，实际调用与全文质量另记。
