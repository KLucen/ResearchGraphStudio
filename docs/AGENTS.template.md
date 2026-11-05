# 工程协作规则附录：阅读辅助知识图谱与 Query

2026-11-04 最新增量：[ADR0025](adr/0025-query-browsing-and-paper-grouped-answers.md)和[浏览验收](p4-query-browsing-verification-20261104.md)落实各Query板块独立论文筛选、10条分页、完整默认图谱标记和按冻结来源分组/双层引用折叠。search/page是只读本地全量命中浏览，不改旧prepare/hash/模型输入；跨页选择保留，历史/保存归属只派生真实根来源。head0014不变，零新真实请求，安装包用户原生反馈待确认；停在P4，无Commit/Push授权。

2026-11-04 当前：P4-Q01～Q07 已接入，Q08 正在修复安装后的来源显示、整组问答/导航和保存内容批注/移除反馈，Alembic head **0014**。决策见 [ADR0024](adr/0024-query-reading-cards-and-saved-lifecycle.md)，本轮状态见[反馈报告](p4-query-feedback-verification-20261104.md)；[ADR0023](adr/0023-grounded-query-and-explicit-saving.md)及[P4实际报告](p4-query-verification-20261104.md)保留前次结果。P5 Lint/Wiki 未启动，修复包原生确认另记。

更新：2026-11-04（Asia/Shanghai）。现有根 AGENTS 及用户本轮明确指令优先，本附录不整体替换根规则，也不授予开发或上传权限。

Query 基础由 [ADR0022](adr/0022-query-foundation-and-versioned-context.md)和迁移 0012 引入；[基础验收报告](p4-query-foundation-verification-20261104.md)保留该阶段历史结果。0013增加显式保存索引，当前0014增加独立保存偏好；领域 `reading-extraction-1.0`、入口 `paper-reading-v1` 保持。先前 R5 成果已推送 `80552d3` 且[远端 CI](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41778202007)通过，Query 新增量没有再次 Commit/Push。

## 共享底座与来源

- 产品辅助科研论文阅读，不预设研究方向，统一称知识图谱。继承工程，不重建第二套知识库。
- Ingest、Query、Lint 共享 Knowledge Engine/Knowledge Store。保留原文、表格、证据坐标、候选和模型 raw；未选候选仍可检索。
- 一键建图没有人工审核/待审/接受驳回。旧人工状态及修改仅作兼容保留，不能静默覆盖。
- 默认 Paper→核心 Claim→有据非 Claim 支撑，允许共享成员与显式收起；来源归属不全部画线，不因共享证据或布局相邻猜科学边。
- 原语言权威、中文辅助；作者主张、转述、个人观点和模型综合分别归属。条件保留 known/unknown/not_applicable/conflicting，不猜数值或统一不同单位。
- Zotero 原文/数据库与 Obsidian 私人笔记只读；路径、快照、用途授权与根依赖必须可核验。密钥只在 OS 凭据存储，不入数据库、日志或源码。

## Query 执行、保存与后续边界

- `query_runs/query_model_runs` 属于项目级执行审计，不随意绑定首篇论文。旧 ModelRun、任务签名及 raw 不重建、不改写。
- 普通查询、索引重建、笔记授权/扫描和文件检查不推进科学 GraphRevision；使用 `KnowledgeStore.audit_event`，不能把通用诊断写入科学变更入口。
- Q01 最小 registry 保存不可变文档版本/段落及根依赖；内容 valid/stale/invalid/unverified 与文件 not_exported/in_sync/modified/missing/conflict/unavailable 独立。磁盘缺失/外改不使有效内部版本自动失效，外部文本不继承旧 manifest。
- 默认文献查询不读私人材料；笔记 local/model 用途分别授权，模型外发默认关闭。撤权沿 Wiki/综合/缓存依赖穿透，保留历史不代表继续允许使用。
- Q02 索引是可重建派生产物，检索资格须实时核对项目、论文/版本、候选有效性和授权。隔离/旧驳回/superseded/Mock 默认排除；References/页眉页脚不作科学证据。
- Q03 从命中种子沿完整合法支撑补方法、实验、条件、结果、指标和限制；独立于画布分页/折叠/隐藏。科学关系必须重验，导航线和 NO_DECISION 不作证据；不沿整个 RELATED 连通图无限扩展。
- Q04 `query-context-1` 绑定精确版本、hash、坐标、章节/表格、路径、文档状态、权限及短编号。没有正式 span 时只读引用 Chunk，不为查询造知识或假证据。缓存和重放也要终验，不能只信旧成功状态。
- 不套用旧 Comparator 3跳/100节点/48K限制，不裁断必要条件或表头。已知模型能力不足时保留完整组并标不足，估算不冒充真实 tokenizer 或 API 成绩。
- Q05 `P07_query_grounded_v1/query-grounded-semantic-1` 只生成语义段落和请求内引用；程序绑定正式身份。模型执行使用持久请求账本：发送前占用槽位，最多两个请求且第二次须明确继续；已有完整响应先重新终验，超时槽位不重发。来源或授权变化停止复用，不能靠再次收费修复。
- Q06 项目问答页提供本地预览、明确生成、手动继续、回答历史、逐条证据和真实用量展示。预览不调用模型；私人资料的本地读取与模型用途分别授权，每次提问还须明确同意发送，问题或范围变化后重新确认。
- Q07 显式选择已验证回答段落，通过 KnowledgeStore 幂等保存 Synthesis/Insight、不可变文档版本及逐段根依赖；保存采用确定性复制和校验，不再调用模型，不重写论文 Claim。可选内部文档目标追加新版本，独立衍生图层不冒充科学关系；这不是 P5 的主题整理、Wiki 发布或 Markdown 导出。
- 来源presentation仅为终验后的本地显示，不修改冻结snapshot/hash；原文权威，已有中文摘要辅助，缺失明确提示，不自动调用模型补译。问题、来源、答案与保存成组，原问答导航须提供实际定位/加载/错误。
- 0014个人批注与移除使用独立metadata_revision/expected_revision和幂等键，经Store只记审计、不改科学GraphRevision。批注不进入模型上下文；移除穿透检索/衍生层/段落副本及依赖，原Query/raw/文档/证据保留。include_personal控制来源私人资料用途，不将个人批注自动隐藏或授权外发。
- 当前后续为 Q08 用户反馈修复、最终验证、报告、修复包及用户原生确认。实际结果以当前报告为准，不以旧包反馈、协议桩、Mock 或 R5 排序替代，不自动重复付费调用，不自动进入 P5。
- 默认 Query 只读，用户保存是独立明确动作；Wiki 整理/更新与 Markdown 导出仍需后续单独实现和授权。生命周期边界见 [ADR0018](adr/0018-query-wiki-and-obsidian-lifecycle.md)和[开发计划](06_development_migration_plan.md)。

## 继承的解析、抽取与恢复

- `pdf-structure-1` 保留跨页章节和可恢复的表头/行列/单元格；References 保留不抽取。原 Chunk/EvidenceSpan 不重写，旧库补解析逐块精确校验；无 OCR，复杂表格不能保证。
- [ADR0017](adr/0017-semantic-protocol-and-stage-recovery.md)：新 P02v4/reading-semantic-1 仅语义，程序绑定来源；P12 仅关联/重复提案，程序沿验证路径组单元；P13v3 仅贡献评估。旧冻结计划/签名/检查点保持原协议。
- [ADR0021](adr/0021-keyed-ranking-and-bounded-correction.md)：程序固定完整评估槽位与 Schema，同源 Prompt；合法外壳下有效槽位只私有保留，最多一次定向修复、两个持久请求槽位含超时，继续不重发已用槽位。全槽位终验及 Store 再验后才发布，不删未知字段或合并冲突建议。
- [ADR0020](adr/0020-evidence-aware-core-selection.md)的原文/疑点/数字排版风险及支撑 caveats 保留；来源锚定不等于科学正确。首次失败仅保守 provisional/pending/partial，旧图保留，不伪称排序完成。
- 新响应与 received/succeeded/validation_failed 缓存同终验；protocol/schema/context/evidence 留稳定诊断。仅 response_invalid=true 改模型失败状态；可信来源/候选/快照变化保留历史并停止，不能靠再次收费修复。
- Provider 冻结 output_policy，strict 只用精确官方能力登记；兼容 JSON 不冒称 strict，不收费探测或自动降级重发。未知 Schema 约束发送前拒绝。
- 已知 `Claim.kind_note_unused=null` 仅精确无损移除并审计，其他未知/非空值仍拒绝。旧 P13 单字符恢复仅按 [ADR0016](adr/0016-selection-json-syntax-recovery.md)限定规则，不能扩成通用 JSON 修补。
- 历史继续接口可返回已完成/失败/运行中的后继；必须显示实际返回结果，分页外后继独立读取，原失败/raw保留，ranking pending 不冒充完成。

## 验证与交付

[R5 历史补验收](r5-acceptance-verification-20261104.md)已在明确范围内通过：两篇 P13v3、已知 32+2 缺陷过滤、同义代表及用户安装反馈；有限证据/partial 保留，不宣称全论文准确率。该成绩不能替代新 Query 验收。

- 每轮先检查 git status/diff，保留未提交成果；按 [progress](progress.md)及实际报告区分实现、离线测试、真实模型和用户反馈。
- Conda 环境为 `researchgraph-studio`；迁移先备份，权限/文件/来源故障用隔离合成数据，正式库不作试验对象。测试与安装不得修改原 PDF、Zotero 或私人笔记。
- 每轮更新 progress 和开发日志，使用 Asia/Shanghai 时间记录实际命令、结果、未测与下一步。参考契约不是运行 API，文档指标不是实测成绩。
- 减少 Computer Use，优先自动化及用户原生反馈。真实 strict、完整 Query 基准/性能、复杂版面、跨平台/干净机及 S1～S4 不可用原文分别登记限制。
- 任何 Commit/Push 前检查实际内容/路径、暂存区及 Gitleaks；私人论文/批注、数据库、模型 raw、日志、密钥和安装器不入源码。未获新授权不 Push。
