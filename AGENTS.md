# 项目协作约定

- 2026-11-07 Lint性能：新head0020仅增phase/timings与三索引，旧科学列/targets/input_hash/raw不改；catalog列投影/批量预取仍逐调用完整验源和逐link终验，无跨调用缓存。依赖边批量重建、CTE双向完整闭包先完成再当前权限过滤分页，隐藏中间节点不剪断传播。末批对象满数先提交rebuilding_dependencies，下一advance重验再建索引；桌面/自动幂等key含phase，GET不推进不记新计时。固定同字节harness本轮before/after为856.662931→469.026664秒、依赖重建13.185584→3.217814秒、反向P95 1.027968→0.030090秒、峰RSS300.695→247.469MiB；旧430秒不作本轮before，不宣称通用SLA。阶段计时不含所有事务/网络开销、不进P09冻结输入。实际全量回归/包及未测项以docs/p5-lint-performance-verification-20261107.md、progress和DEV-0062最新记录为准；unknown仍info/不补条件，真实调用0/正式库实验0，未Commit/Push。

- 2026-11-07 Lint处理方案：用户确认扫描可以继续，要求为诊断准备处理内容。26条规则按对象归属/生命周期派生只读repair_plan，SOURCE_UNCHECKED指向文献页“检查文件”，CONDITION_UNKNOWN保持info/unknown，有据时才受控重建，不直接改旧条件；外部材料只读新版本不走Wiki发布。模型需求false/true/null分开展示，方案不执行动作、不进入P09/P10/P11冻结输入/hash/问题指纹，无迁移。最终234后端专项/1符号链接权限跳过、159React、4Edge、冻结P5/旧smoke及PS5.1隔离5项通过；213运行源/312资源配对，新包7c08d3b8见docs/progress.md和DEV-0061。真实模型0、正式库实验0、未Commit/Push/替用户安装；新包原生及真实科学未验收，旧1124/430秒/17项不冒充本轮重跑。

- 2026-11-07 文档整理：当前状态统一读 docs/progress.md，docs/00–09维护当前设计；已结束阶段报告及完整旧进度见 docs/archive/reports/README.md。历史阶段限制与授权只适用于原轮次，当前仍P5/head0019、真实科学和新包原生待验，无新增收费/Commit/Push授权。重复docs/AGENTS.template.md与CHANGELOG_FROM_V2跳转页已移除，使用根规则及历史原文。

- 2026-11-05 P5扫描原生反馈：用户确认unknown信息已显示但进度停“正在处理”。新修复见docs/p5-scan-feedback-verification-20261105.md：活动报告只读刷新、旧响应不得回退终态/进度，准备/推进/待继续分清；桌面每批100（后端上限内、API默认25不改），逐调用验源不减。CONDITION_UNKNOWN仍info，保留unknown，不推断矛盾/补造条件。新包e432990a/213运行源/312资源，155React/31后端Lint专项/19Edge/冻结smoke/Host1/PS5.1隔离17通过；旧1124与430秒不冒充本轮重跑。schema0019、真实调用0、正式库实验写入0，未Commit/Push；新包原生及真实科学仍待验。

- 2026-11-05 本轮用户明确要求从中断现场继续 P5，覆盖历史“不进入P5”阶段限制。当前 head0019（0015诊断/依赖、0016 Wiki/发布、0017 P5工作流、0018独立外部文档、0019批注用途授权/最后显式导入索引），领域/入口/旧协议不变。新P5显式选择note/批注评论/外部版本，读取、模型用途和目录写入授权分开；外部来源不继承Wiki证据，批注评论不冒充作者原话。不得继承P4付费/上传授权，当前真实调用0、正式库实验写入0、不Commit/Push。实际功能/迁移/回归/包与剩余项见docs/p5-verification-20261105.md和ADR0029；真实P09/P10/P11科学质量及用户新包反馈仍待验收，不得记P5退出通过。

- 2026-11-05 11:33本轮交付完成：优化源码75061d2已普通推送main，独立run41959965368的windows/installed-app/实际安装VerifyDesktop全部成功。178运行源与封存23079790安装器按指纹匹配；最终只补文档不改运行源，CI自己的安装器与本机包分别记录。新包用户原生反馈仍待，科学16/3/0与预算结束限制不变。实际报告docs/archive/reports/p4-followup-verification-20261105.md；后续开发或付费调用不自动继承本轮上传/2请求授权，不进入P5。

- 2026-11-05 11:08实际收尾：最终共享源934 Python/2权限跳过、124 React；178运行源稳定。串行原规格万候选/两万块基准warm P95=1.583589秒，本机≤2秒达标，旧3.016278及候选失败保留、不作通用SLA。仅新增2次真实P07v3/317171Token，19段16支持/3部分/0无支持，预算已结束不得继续自动收费；3部分为术语等同、比较范围扩大和跨页引用不足，不以引用补齐宣称语义正确。2份保存/幂等/两次重启、正式库实验写入0及旧记录保持已验。新包23079790待用户原生反馈，最终优化提交及CI另记，不进入P5。

- 2026-11-05 P4后续改进见ADR0028及docs/archive/reports/p4-followup-verification-20261105.md：已按本轮授权推送验收快照8d67ed1。新prepare冻结scientific_guidance并选P07v3，旧只有numeric_layout仍v2、无两字段仍v1，旧Prompt/hash/raw不改。wire DTO不变；仅补真实node/evidence/chunk根及检测表格组，补齐后再验归属，scientific_binding审计在GET/保存重算，背景可介绍但不冒充新贡献。未检表格/公式语义保持未知，不从扁平空格猜列；引用完整性不是语义证明。检索优化只减本调用ORM/遍历/UUID前缀/编码器准备，索引ID/字节和来源终验不变，不跨调用缓存。最终共享源SLA/两次有界P07补验/新CI与包以本轮报告为准，不沿用旧快成绩，不进入P5。

- 2026-11-05 最新用户授权“提交并推送至Github，并尝试解决未达标部分”：先将已验收P4快照通过实际内容/路径/历史及暂存Gitleaks检查后普通推送main，跟进该提交CI；再在P4内优化P95及科学partial，不进入P5。不把旧条目的无Commit/Push授权当成本轮阻塞；不上传私人验收库/raw/PDF/凭据或本地安装器。不自动重跑已结束10次模型验收；优先用冻结真实响应和匿名合成样例诊断，新增真实请求必须有清楚的验收预算/账本。

- 2026-11-05 P4数值补验已结束：总10次真实请求/1,623,354 Token，金额未知，不追加调用。原十题64支持/7部分/1数值错误保持；新v2六段5支持/1部分单列。专用limitations的8处危险token按原Unicode跨度确定性占位，带display_normalization审计，不改正文/raw或猜数字；正文危险数值仍拒绝。显式recovery-only冻结原runID/rawSHA/plan及现有槽预算，在provider/槽位前终验，不可复用即零网络失败，不退回新请求；实际恢复新增0槽/0调用、原失败Job及审计保留，保存幂等/重启通过。旧v1已知错数的新保存拒绝，原答案保持。最终回归/包指纹以本轮报告为准。

- 2026-11-05 P4最终回归/真实验收见docs/archive/reports/p4-final-acceptance-20261105.md、ADR0027。用户确认旧318f锁修复安装版数据功能正常；本轮新性能/数值保护包原生另计。10题原科学质量64支持/7部分/1数值错误，失败样本及raw保持；修复补验单列，不能抹去原错数。新prepare冻结numeric_layout/query-numeric-layout-1并按字段选择独立P07 v2，旧无字段context/v1 hash/Prompt/manifest/恢复不变。明确risk_pairs压平数字由程序终验拒绝QUERY_NUMERIC_LAYOUT_UNRESOLVED，保留raw、不自动继续；未知/partial不标安全。旧v1新保存只对所选段落作当前版式检查，含同/新键重放；不改旧答案或已有记录。只读presentation附警告。数值守卫保守、可能同值误拦，不是通用数学核验。检索按本调用批量载ModelRun/复用完整新鲜entries，仍逐候选/来源/授权/边/锚点终验，无跨调用cache/裁剪。head0014无迁移，不再调用已结束真实验收、不进入P5、不Commit/Push；实际最终命令/计数/包hash以新报告为准。

- 2026-11-04 历史“无效响应”锁修复见ADR0026及docs/archive/reports/query-history-lock-verification-20261104.md：WAL+受query_only保护read_session供已审计8个Query读/校验路由及P07等待状态检查；writer仍IMMEDIATE，索引/prepare/生成入队/Store写不改只读。池归还恢复query_only，普通写可复用。worker空轮询只读、有queued再短事务重验认领，claim/诊断完成DB等待to_thread，锁冲突未认领不发模型，取消先等claim线程完成。BUSY/LOCKED标准503 DATABASE_BUSY JSON、其它OperationalError脱敏500 DATABASE_ERROR；Rust非JSON保留HTTP状态不回显body。历史失败提供手动重读，不能自动generate/模型重发。head0014无迁移/正式库实验/付费调用/Commit/Push/P5；新包原生待反馈。此前888等为浏览包历史成绩，本轮实际成绩以新报告为准。

- 2026-11-04 P4浏览增量见ADR0025及docs/archive/reports/p4-query-browsing-verification-20261104.md：问答各板块独立论文多选，列表及引用每页10条。search/page单独浏览全部合法词面命中，不改旧QueryRequest/prepare/snapshot/manifest/hash/模型输入；每页重验，结果hash变化须刷新。来源图谱标记取完整默认reading backbone一次收集，不取画布分页或Query临时图；原文支撑标evidence而非独立节点。回答按冻结根来源分组，跨论文段只显一次；两层引用默认折叠，外层展开不展开内层，显式全展开跨引用页有效；跨页保存选择保留。历史/保存paper_ids是只读派生元数据，不按整问题scope编造归属；冻结refs未到不能提前显示答案。head0014不变，无新增真实请求/正式库实验写入/Commit/Push，不进入P5；最终包与用户反馈分开记录。

- 2026-11-04 P4安装反馈修复：来源顶层presentation只读展示已验证原文与已有中文摘要，不进入冻结snapshot/manifest/hash或触发翻译请求；缺中文明确提示，答案要点标AI综合。问题/来源/答案/保存成组，查看原问答须实际读取并可见定位/加载/错误。0014只增query_saved_preferences：个人annotation及独立metadata_revision/removed_at，经Store幂等+expected_revision，审计不推进科学GraphRevision。移除排除保存列表/检索/衍生图及其段落复制/依赖谱系；旧Query/raw/答案/文档/论文证据保留，重复保存已移除指纹明确拒绝，不返回不可见成功。修复包实际状态见docs/archive/reports/p4-query-feedback-verification-20261104.md；旧0013包已收到问题反馈，不算修复包原生通过；不新增模型调用、不进入P5、无Commit/Push授权。

- P4新增scope_coverage只用于新显式多论文/版本查询：按篇公平保留真实命中，题名不算科学覆盖；context按实际根证据重算，缺篇insufficient且零外发/不保存。旧无字段manifest/hash/回答保持。普通retrieve仅同步局部复用来源核验，后续调用重验，边证据不省略；撤权孤儿FTS也清理。新保存node根冻结可选payload_sha256，旧无字段兼容，源码稳定后包指纹必须复核。

- 2026-11-04 最新范围：用户要求完成 P4 剩余 Q05～Q08，覆盖此前仅 Q01～Q04 的限制。本轮新增 P07/query-grounded-semantic-1、回答持久槽位（每查询最多2次、失败不自动重发）、问答UI、KnowledgeStore.save_query和0013 query_saved_knowledge。Q05回答原始输出、来源及用途在发送/收到/GET/保存终验，科学知识只在明确保存时变更；不重写论文Claim/选择/布局，不进入P5。实际回归/真实/安装状态以docs/progress.md和docs/archive/reports/p4-query-verification-20261104.md为准。本轮无新的Commit/Push授权；旧“不进入P4/无问答/head0012”均为历史条目。

- 2026-11-04 最新：用户明确授权“先 Push 本轮 R5，再开发 P4-Q01～Q04”。R5 已提交推送为 80552d3，远端 CI 全部通过；授权已用于该次交付，不自动再次 Push 新增 Query 改动。当前 Q01～Q04 已实现，head0012，领域 reading-extraction-1.0/入口 paper-reading-v1 不变；后续从 Q05 开始，不进入 P5。见 docs/adr/0022-query-foundation-and-versioned-context.md、docs/archive/reports/p4-query-foundation-verification-20261104.md 与 progress。下文“不进入P4/head0011/无迁移”指对应历史轮次，不再作为本轮限制。
- Query 当前仅本地 search/prepare/validate 与项目级执行记录，无 P07/P08 调用、问答 UI 或用户保存回答入口。0012 只加 Query/文档/授权/派生索引表，旧 ModelRun 和知识行不重建。KnowledgeStore.audit_event 不推进 GraphRevision；科学知识写入仍走 Store。query-context-1 冻结完整合法支撑路径/条件/表格及根证据，缓存和幂等重放均重新验证来源与当前用途权限；笔记默认不读、不外发，撤销穿透 Wiki/缓存。内容有效性与文件字节基线分开，in_sync 不宣称 MD 语义等价。无固定48K/3跳/100节点限制，容量不足保留完整组并标不足；无新增真实模型调用，正式库不作实验。

- 2026-11-04最新R5补验收见docs/archive/reports/r5-acceptance-verification-20261104.md：用户本轮授权实际检验，隔离副本用当前全局max配置两篇P13v3各1次成功（38/105槽位、7/20单元），新增P02/P12为0，再继续新增0；原16任务/127raw与参数/758节点逐行保持。32无支持+2上标误读均retrieval_only，5同义组各1核心，支撑路径/锚点0错误，有限证据/partial仍保留；不宣称全局科学准确率。新包17引擎/1打包Host/3旧schema升级及用户原项目/历史续接/重启三项反馈通过。2次真实276699Token、金额未知，验收已结束，不自动追加调用；正式库实验写入0、无迁移/Commit/Push，不进入P4/P5。4个附件PDF哈希匹配与S1–S4外部补充原文仍不可用是不同集合。此前“未新增付费/待复验”为对应历史轮次状态。

- 历史任务的继续接口可能幂等返回另一个已完成/失败/进行中的后继，不能假设原任务变为queued。JobHistory须显示返回结果与定位，分页外后继独立读取实际状态；原失败/raw保留，已成功后继不重排，ranking_status=pending不冒充完成。2026-11-04只读核验的Claim.kind_note_unused=null旧失败已有34/34成功后继，本轮仅修交互，不新增付费调用。

- 2026-11-04当前R5协议见ADR0021：用户要求软件修复连续冲突编号/额外字段，不以换模型为前提。新plan冻结P13_reading_ranking_v3/reading-ranking-keyed-1，程序把完整短编号集合固定为assessments required属性；模型只填建议/理由/说明/0–100整数priority，程序稳定降序，同分按冻结输入顺序。Schema与Prompt同源，旧v1/v2计划/签名/raw保持。合法外壳下有效槽位仅私有保留，缺失/非法槽位最多定向修复一次且保留完整上下文；不删未知字段、不合并冲突建议。发送前持久账本最多两个请求槽位含超时，继续不重发已发送槽位，上限后零调用。全槽位终验+Store再验才发布；旧selecting失败可独立v3续接并重验原P12谱系，零重复P02/P12。实际测试看progress，本轮无新增付费调用、迁移、Commit/Push，不进入P4/P5。

- R5证据感知选择见ADR0020：真实引文/根与支撑issues/数字排版风险继续传入v3；旧无ranking_prompt计划继续v1，显式v2保持v2。碎片依据Claim不能core/provisional，needs_context与insufficient_support标insufficient，member issues汇入caveats/limited。保留原文/候选/raw；前轮P02两篇6/6与15/15、v2各2次P13失败历史保持，本轮v3成功及32+2不入默认图另记，不改写旧记录。更换模型不是修复前置。

- R5支撑完整性见ADR0019：候选snapshot不覆盖关联，程序另冻reading-support-context-1；form_units缓存核对完整闭包，P13请求前/后核对冻结成员输入与当前合法路径，Store发布重载持久成员再验。关系变化SUPPORT_CONTEXT_CHANGED/response_invalid=false，保留历史状态/原图，不重复收费；旧无manifest保持指纹但须当前全路径重验。用户已反馈上一安装包三篇同显、悬停拖动、颜色图例、全屏Esc、重启知识布局五项全部通过，属于用户反馈；新包/科学质量/strict分开记录。

> 2026-11-04 阅读协议继续保持：R1–R5 本轮验收范围已交付；当前已进入 P4-Q01～Q04，head0012，领域 reading-extraction-1.0、入口 paper-reading-v1 不变。新P02_reading_extract_compact_v4/reading-semantic-1仅输出items/links/warnings，程序绑定来源身份；P12仅语义关联/重复提案，程序沿全部已验证路径组单元，P13v3仅贡献评估槽位。首次失败预览必须provisional/pending/partial，旧图保留；统一终验决定缓存恢复资格。新旧协议边界见docs/adr/0017-semantic-protocol-and-stage-recovery.md与ADR0021，实测以docs/progress.md为准。

- 开始工作前阅读 `README.md`、`docs/README.md`、`docs/progress.md`、`DEVELOPMENT_LOG.md` 最新条目，以及 `docs/00_decisions_and_scope.md`、`01_product_design.md`、`02_architecture_and_workflows.md`、`03_schema_design.md`、`06_development_migration_plan.md`；按任务补读交互、Prompt、API 和验证章节。
- 当前以 docs/00–09 的 v3.3 阅读辅助知识图谱设计及 ADR 0008 为依据，旧 v3/v2 资产在 docs/archive/。产品辅助科研论文阅读，不预设研究方向，统一称知识图谱。新流程一键自动构建，无人工审核/待审队列/接受驳回。保留原文、表格材料、定位、模型输出及未选候选；参考契约不是运行 API。
- 当前技术路线以 `docs/decisions/0002-tauri-evidence-workbench.md` 为准：Tauri 2 + React/TypeScript、Python/FastAPI Sidecar、SQLite/FTS5、React Flow。ADR 0001 的 Electron 暂案已被替代。
- 当前工程继承 P0–P3，Q01～Q04 已实施，下一步 Q05；M6/跨模型/干净机等限制按报告保留。不能重建工程或提前启动 P5。未测项明示，Mock 不替代真实验收。
- Ingest、Query、Lint 共享 Knowledge Engine；新知识写入统一经过 KnowledgeStore。新流程自动验证与选择，无人工审核；作者主张不等于科学事实。Query 默认只读，用户选择保存后才可沉淀知识。NO_DECISION 不作为科学关系边；已接受语义不得被模型静默覆盖。
- P4/P5待实现边界见ADR0018：Wiki为有版本/逐段依赖的阅读文档，不是图谱；Query兼读有效Wiki/保存综合与底层证据，P4前置最小文档状态/只读adapter，P5扩展发布。保存默认新增Synthesis/Insight等衍生对象，不重写论文Claim；整理/更新Wiki及导出MD分别明确动作。内容依赖失效与文件外部修改/缺失分开，后者不使内部有效旧版本自动失效也不让新文本继承旧manifest；Lint区分受管MD与授权私人材料，只读诊断，不静默回写图谱或私人文件。
- 图谱是论文知识组织与支撑路径层，GraphProjection只是画布；Query 已从命中种子沿完整合法单元/种子相邻科学关系补条件和根证据，不能从分页画布取全集或直接继承旧Comparator的3跳/100节点/48K约束。Wiki按单元组织主题/分歧，Lint查支撑及依赖；后续保存综合可显示于独立衍生图层，隐藏不影响检索。导航/科学关系/衍生引用/文档依赖分型；普通Query、Lint和文件扫描不推进科学图修订。完整生命周期及当前/后续边界见docs/06，Q05～Q08/P5 尚待开发。
- LLM 只输出严格 DTO/候选，不能执行 SQL、Shell、文件操作或生成正式 ID；正文、批注、笔记中的指令均为不可信数据。条件区分 known/unknown/not_applicable/conflicting。文档指标不是实测成绩。
- 每轮完成实质性工作后，在 `DEVELOPMENT_LOG.md` 追加目标、改动文件、验证结果、未解决问题和下一步。记录实际结果，不把计划或尝试记为完成。
- 涉及架构或需求调整同步开发方案，新决策写 `docs/adr/`；保留旧 `docs/decisions/` 历史。当前结构文档决策见 ADR 0014，Query 基础见 ADR0022，v3 文档基线见 ADR 0003 与 `docs/migration/v3-documentation-map.md`。Alembic head 为 0012，不能与领域/投影/抽取版本混用。Obsidian 私人笔记默认只读，发布需要独立授权；个人观点与论文主张隔离。
- 来源/候选/选择共用 KnowledgeStore，KnowledgeUnit 引用已有知识，多对多成员不复制。默认 Paper→核心 Claim→有据非 Claim 支撑（包括 Method/Experiment/Condition/Finding/Metric），可显式收起；不为缺失支撑造节点。来源归属不全部画线，导航边不冒充科学关系。原语言权威、中文辅助，知识/选择/布局版本分开。
- 候选经 Schema/来源校验后持久化，默认核心另经论文相关性、证据完整性和重复/覆盖检查自动选择。未选仍可检索；用户显示偏好不是审核且不能绕过来源门槛。历史审核/人工修订仅作兼容保留，旧已接受语义不静默覆盖，旧驳回不自动重新发布。
- P02 按章节语义一次提取多类知识，输出额度读取已知能力或使用供应商默认，不为能力探测额外付费；保存计划/签名/拆分账本，已提交批次不得重复调用。新旧 Prompt/协议独立，不能覆盖运行历史。Zotero 附件默认只读引用、不长期复制，直接 PDF 导入保留。
- 新 PDF 解析输出 pdf-structure-1：跨页章节树、原文行/块坐标、可恢复表格的表头/行列/单元格及合并关系；References 和页眉页脚保留但不进入抽取。document_parses 按文献版本/解析器版本唯一；旧 Chunk/EvidenceSpan 不改，旧库补解析必须逐块精确核验。无 OCR，复杂版面与表格恢复不能保证。
- 新任务使用 P02_reading_extract_compact_v4/reading-semantic-1；模型仅 items/links/warnings，版本/批次/默认语言由冻结 transport_context 绑定，证据引用请求内短编号。展开后仍走 reading-extraction-1.0 严格领域/来源验证，Prompt 结构规则由实际输出 Schema 生成并核对。section-context-v1 优先完整跨页章节，各章节相同规则，References 排除；只有模型容量不足才按完整段落/表格组拆分，无固定字符数/证据数目标，超时重试有界。旧 v3/reading-compact-1 及更早 Prompt/Schema/签名/计划不改；独立续接遵循 ADR0013，成功操作及可重验响应复用。
- 新 finish plan 使用 flow_policy=semantic-reading-1/context_policy=complete-context-v1：P12_reading_associations_v1 仅提出语义边/重复，程序 form_units 从所有已验证路径形成单元；新plan显式冻结P13_reading_ranking_v3对程序固定槽位给贡献建议并核对原文，旧无ranking_prompt计划保持v1、显式v2保持v2。新任务无旧26K/24K/48K、60候选/8根/20窗口预算，真实端点能力和有界时限保留。旧finish plan/reading_windows原签名/P13分组与成功检查点不变；见ADR0015/0017/0020/0021。
- 新模型快照显式冻结 output_policy（strict/json_object/prompt 与 documented/requested/disabled）。原生 strict 只用于代码登记的官方精确端点/模型，兼容 JSON 不宣称严格 Schema；不付费探测、不自动降级重发。Schema 转换不能删除约束或额外加 null，未知关键字调用前失败，记录源/请求哈希及转换。真实 strict API 未测须明确，不能把文档能力当成绩。
- validate_stage 对新响应与 received/succeeded/validation_failed 缓存均做 JSON/DTO、context/白名单/证据/快照终验，Store 写入仍再验。坏响应分类 protocol/schema/context/evidence，stage_validation 记录稳定 code 与 input/raw 哈希，raw_output 不改；固定坏响应不能循环复用。仅 response_invalid=true 更新 validation_failed/error/finished_at；可信来源/候选/快照变化为 false，保留历史 status/error/finished_at，只记本次复用诊断，停止并要求新构建，不能靠再次收费修复。
- 首次语义整合/排序失败且没有旧图时可保守 provisional 展示有来源/明确作者归属、非背景/unknown/speculative、无 issues 且非重复代表的 Claim 和合法支撑，ranking_status=pending/build_state=partial、质量相关性 unresolved；任务仍失败，不冒充完成核心排序。已有图保留，来源或快照冲突不得预览；无人工审核。
- 历史 ADR0016 只允许旧 P13 根末 coverage_gaps 完整非空字符串列表、已有根 `}`、仅缺数组 `]` 的单字符恢复；正常及恢复后都拒绝重复键/NaN/Infinity，拒绝其他损坏。其“其他阶段不变”是当轮范围，新语义 P02/P12/P13 也严格解码但不作此恢复。审计 integration_normalization 记录 rule/0起始Unicode字符offset/双SHA-256，raw不改，完整Schema/ID/来源/Store不省略；旧合法/可精确恢复响应仍重验复用，成功阶段不重调。finish_reason仅记实际返回，历史未知不推断stop；head0011不变。
- 阅读响应只在完整字段/证据校验后合并同 local_ref 且原始 JSON 完全相同的重复项，去重记录 reading_normalization 并保留 raw_output；同编号不同内容仍拒绝。仅已观察到的 Claim.kind_note_unused 且值恰为 null 可无损移除，紧凑响应审计记 ModelRun.parameters.reading_wire.expanded_fields，其他响应记 reading_envelope_normalization；非空值/其他类型/其他未知字段仍拒绝。旧失败响应完整重验后可零调用续用，Store 来源验证不省略，见 ADR0010/0014。不把按章节输入写成所有论文一次请求成功。
- 每轮更新 `docs/progress.md` 和开发日志，记录实际命令/结果/跳过/风险；迁移先备份，测试使用隔离数据，不直接升级或覆盖用户数据库作实验。参考 SQL 不能直接替代 Alembic 迁移。
- 按用户指定优先使用 Anaconda/Conda，项目环境为 `researchgraph-studio`；允许创建独立 Conda 环境，不向 base 安装项目依赖，不默认使用 uv 或另建 `.venv`。通过 `conda run -n researchgraph-studio ...` 或环境绝对解释器执行 Python/pip，维护 `environment.yml` 和对应平台的环境锁文件。
- GitHub 开发远端为 `https://github.com/KLucen/ResearchGraphStudio`，本地 `origin` 指向该仓库。当前 HTTPS Git 连接失败时，可按环境文档使用经验证的官方 SSH 443 通道；不修改全局 Git 或网络设置。
- 用户 2026-11-01 P3 指令覆盖此前自动推送授权：未经新的明确授权不得 Push。任何 Commit/Push 前必须运行 Gitleaks 等内容扫描并核对暂存文件，检查真实 API Key/Token、.env、数据库、私人论文/批注/日志，不能仅依赖 .gitignore；发现泄露风险停止提交和上传。密钥存入 OS 凭据存储，不明文进入数据库或日志。
- Zotero 安装程序为 `D:\Zotero\zotero.exe`。安装目录不等于文献数据目录，不据此直接读写 Zotero 数据库。
- 用户论文、模型、密钥、运行数据库和个人笔记不进入源码提交；测试使用可分发、匿名或自造的小样本。
- 对证据处理、数据库迁移、任务重试和安装启动运行针对性验证。文档修改检查链接和一致性即可。
- 用户 2026-11-02 要求减少 Computer Use：优先自动化回归（图谱需覆盖真实渲染组件），通过后提供安装包和明确操作步骤，请用户反馈原生结果；未由用户反馈或实际执行的项目不得记为验收通过。
- 开发日志统一使用 Asia/Shanghai 日期和时间。
- 2026-11-02 R5模型适配见ADR0011/0012：准确端点/模型才用1M/384K文档能力；移除额外32K/64K限额，保留输入预留/端点更低上限/总时限。界面只有“继续未完成批次”，retry后端按需创建独立兼容续接，原签名/成功批次不变，不出现供应商专属操作。部分图须标全文缺口。真实单子批不代表全文；不要重复运行本机真实probe产生额外费用。
- 用户于 2026-10-29 决定 G0 默认通过并进入 Phase 1；按 ADR 0004 记录为用户放行，不再阻塞开发，也不把未执行的干净机测试记为实测通过。

- 正常产品入口只使用真实全局模型，移除旧基线/Mock选择器；Mock仅显式测试和历史兼容，历史测试数据默认不混入图谱，人工修改/接受数据保留。图谱使用点与边、实时力导向拖动、双击固定和独立聚焦按钮；布局冷却/松手保存，不能逐帧写入。

- 图谱类型颜色/中文标签/图例由 graphAppearance 共用，全部11类及未知回退不能露白。paper_backbone 按 paper-round-robin-1 均衡论文分页（默认60/最大120主节点，上下文补齐），cursor绑定graph_revision，失效可直接回第一页。图谱界面按搜索筛选→画布/图例/详情→末尾各论文候选选项排列；选项独立于论文filter，任务记录仅文献与阅读。全屏不重挂载/重排；首次尊重保存相机，切范围新结果后才fit，轮询/resize不fit。用户报告已安装跑通3篇，属于用户反馈，不替代独立科学质量/strict验收。

- 上一轮“这一轮提交并推送Github”授权已用于该轮交付，不延伸到本轮；本轮未经新的明确授权不 Push。
