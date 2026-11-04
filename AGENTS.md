# 项目协作约定

- 2026-11-04最新R5补验收见docs/r5-acceptance-verification-20261104.md：用户本轮授权实际检验，隔离副本用当前全局max配置两篇P13v3各1次成功（38/105槽位、7/20单元），新增P02/P12为0，再继续新增0；原16任务/127raw与参数/758节点逐行保持。32无支持+2上标误读均retrieval_only，5同义组各1核心，支撑路径/锚点0错误，有限证据/partial仍保留；不宣称全局科学准确率。新包17引擎/1打包Host/3旧schema升级及用户原项目/历史续接/重启三项反馈通过。2次真实276699Token、金额未知，验收已结束，不自动追加调用；正式库实验写入0、无迁移/Commit/Push，不进入P4/P5。4个附件PDF哈希匹配与S1–S4外部补充原文仍不可用是不同集合。此前“未新增付费/待复验”为对应历史轮次状态。

- 历史任务的继续接口可能幂等返回另一个已完成/失败/进行中的后继，不能假设原任务变为queued。JobHistory须显示返回结果与定位，分页外后继独立读取实际状态；原失败/raw保留，已成功后继不重排，ranking_status=pending不冒充完成。2026-11-04只读核验的Claim.kind_note_unused=null旧失败已有34/34成功后继，本轮仅修交互，不新增付费调用。

- 2026-11-04当前R5协议见ADR0021：用户要求软件修复连续冲突编号/额外字段，不以换模型为前提。新plan冻结P13_reading_ranking_v3/reading-ranking-keyed-1，程序把完整短编号集合固定为assessments required属性；模型只填建议/理由/说明/0–100整数priority，程序稳定降序，同分按冻结输入顺序。Schema与Prompt同源，旧v1/v2计划/签名/raw保持。合法外壳下有效槽位仅私有保留，缺失/非法槽位最多定向修复一次且保留完整上下文；不删未知字段、不合并冲突建议。发送前持久账本最多两个请求槽位含超时，继续不重发已发送槽位，上限后零调用。全槽位终验+Store再验才发布；旧selecting失败可独立v3续接并重验原P12谱系，零重复P02/P12。实际测试看progress，本轮无新增付费调用、迁移、Commit/Push，不进入P4/P5。

- R5证据感知选择见ADR0020：真实引文/根与支撑issues/数字排版风险继续传入v3；旧无ranking_prompt计划继续v1，显式v2保持v2。碎片依据Claim不能core/provisional，needs_context与insufficient_support标insufficient，member issues汇入caveats/limited。保留原文/候选/raw；前轮P02两篇6/6与15/15、v2各2次P13失败历史保持，本轮v3成功及32+2不入默认图另记，不改写旧记录。更换模型不是修复前置。

- R5支撑完整性见ADR0019：候选snapshot不覆盖关联，程序另冻reading-support-context-1；form_units缓存核对完整闭包，P13请求前/后核对冻结成员输入与当前合法路径，Store发布重载持久成员再验。关系变化SUPPORT_CONTEXT_CHANGED/response_invalid=false，保留历史状态/原图，不重复收费；旧无manifest保持指纹但须当前全路径重验。用户已反馈上一安装包三篇同显、悬停拖动、颜色图例、全屏Esc、重启知识布局五项全部通过，属于用户反馈；新包/科学质量/strict分开记录。

> 2026-11-04当前约定：R1–R4已接入，R5本轮三项补验收范围内通过，未进入P4/P5。head0011、领域reading-extraction-1.0、入口paper-reading-v1不变。新P02_reading_extract_compact_v4/reading-semantic-1仅输出items/links/warnings，程序绑定来源身份；P12仅语义关联/重复提案，程序沿全部已验证路径组单元，P13v3仅贡献评估槽位。首次失败预览必须provisional/pending/partial，旧图保留；统一终验决定缓存恢复资格。新旧协议边界见docs/adr/0017-semantic-protocol-and-stage-recovery.md与ADR0021，实测以docs/progress.md为准。

- 开始工作前阅读 `README.md`、`docs/README.md`、`docs/progress.md`、`DEVELOPMENT_LOG.md` 最新条目，以及 `docs/00_decisions_and_scope.md`、`01_product_design.md`、`02_architecture_and_workflows.md`、`03_schema_design.md`、`06_development_migration_plan.md`；按任务补读交互、Prompt、API 和验证章节。
- 当前以 docs/00–09 的 v3.3 阅读辅助知识图谱设计及 ADR 0008 为依据，旧 v3/v2 资产在 docs/archive/。产品辅助科研论文阅读，不预设研究方向，统一称知识图谱。新流程一键自动构建，无人工审核/待审队列/接受驳回。保留原文、表格材料、定位、模型输出及未选候选；参考契约不是运行 API。
- 当前技术路线以 `docs/decisions/0002-tauri-evidence-workbench.md` 为准：Tauri 2 + React/TypeScript、Python/FastAPI Sidecar、SQLite/FTS5、React Flow。ADR 0001 的 Electron 暂案已被替代。
- 当前工程继承P0–P2，处于P3/v3自动建图收尾：M0–M5核心已接入，R1–R4已实施，R5本轮三项补验收范围内通过，M6/跨模型/干净机等限制按报告保留。后续明确要求开发P4时从Q01开始，本轮不得启动P4/P5；允许合理重构，不能重建工程。未测项明示，Mock不替代真实验收。
- Ingest、Query、Lint 共享 Knowledge Engine；新知识写入统一经过 KnowledgeStore。新流程自动验证与选择，无人工审核；作者主张不等于科学事实。Query 默认只读，用户选择保存后才可沉淀知识。NO_DECISION 不作为科学关系边；已接受语义不得被模型静默覆盖。
- P4/P5待实现边界见ADR0018：Wiki为有版本/逐段依赖的阅读文档，不是图谱；Query兼读有效Wiki/保存综合与底层证据，P4前置最小文档状态/只读adapter，P5扩展发布。保存默认新增Synthesis/Insight等衍生对象，不重写论文Claim；整理/更新Wiki及导出MD分别明确动作。内容依赖失效与文件外部修改/缺失分开，后者不使内部有效旧版本自动失效也不让新文本继承旧manifest；Lint区分受管MD与授权私人材料，只读诊断，不静默回写图谱或私人文件。
- 图谱是论文知识组织与支撑路径层，GraphProjection只是画布；P4应从命中种子沿完整合法单元/科学关联补条件和根证据，不能从分页画布取全集或直接继承旧Comparator的3跳/100节点/48K约束。Wiki按单元组织主题/分歧，Lint查支撑及依赖；保存综合可显示于独立衍生图层，隐藏不影响检索。导航/科学关系/衍生引用/文档依赖分型；普通Query、Lint和文件扫描不推进科学图修订。完整生命周期及当前/后续边界见docs/06；本轮只重写计划与介绍，P4/P5仍未实施。
- LLM 只输出严格 DTO/候选，不能执行 SQL、Shell、文件操作或生成正式 ID；正文、批注、笔记中的指令均为不可信数据。条件区分 known/unknown/not_applicable/conflicting。文档指标不是实测成绩。
- 每轮完成实质性工作后，在 `DEVELOPMENT_LOG.md` 追加目标、改动文件、验证结果、未解决问题和下一步。记录实际结果，不把计划或尝试记为完成。
- 涉及架构或需求调整同步开发方案，新决策写 `docs/adr/`；保留旧 `docs/decisions/` 历史。当前结构文档决策见 ADR 0014，v3 文档基线见 ADR 0003 与 `docs/migration/v3-documentation-map.md`。Alembic head 为 0011，不能与领域/投影/抽取版本混用。Obsidian 私人笔记默认只读，发布需要独立授权；个人观点与论文主张隔离。
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
