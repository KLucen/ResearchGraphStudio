# 下一轮续接：P4 Query

2026-11-05 用户本轮授权已用于普通推送P4验收快照8d67ed1及后续优化75061d2；两者独立CI均全部成功，后者run41959965368包含实际安装VerifyDesktop，不继承旧成绩。最终仅补文档，运行源码仍75061d2。正式库实验写入0，私人验收资料和安装器不提交，不进入P5；实际交付结果见progress和开发日志最新记录，未来新工作不自动继承本次上传授权。

后续实现见[ADR0028](adr/0028-query-scientific-guidance-and-citation-closure.md)和[P4改进验收](p4-followup-verification-20261105.md)：新P07v3/冻结guidance/引用绑定审计与本调用表示优化已落地，旧v1/v2不改。934 Python/2权限跳过、124 React；178运行源与75061d2及新包匹配，最终串行原规格P95=1.583589秒，本机2秒目标达到，旧失败保留、不作通用SLA。两次新P07已全部用完预算，317171Token/19段独立16支持/3部分/0无支持，禁止自动追加请求或重复旧十题/抽取。科学3部分保留术语等同、比较范围及跨页引用不足，不能把补根引用写成语义证明。新包23079790原生反馈待确认，其它CI/安全/资源配对以报告最终记录为准。

2026-11-05 最新以 [P4 最终验收](p4-final-acceptance-20261105.md) 为准：用户确认旧锁修复安装版数据与功能正常；本轮真实十题保留原科学质量64支持/7部分/1数值错误，不得删除失败样本冒充全通过。新 P07 v2 冻结 numeric_layout，旧 v1 Prompt/hash/raw 保留；新写入保存也阻断已知危险数字。决策见 [ADR0027](adr/0027-query-layout-aware-numerical-grounding.md)。请求与单次补验均有私人持久账本，验收结束不自动追加付费调用。head0014，不新增迁移/正式库实验写入/Commit/Push，不进入P5；本轮新安装器的原生反馈不能直接继承旧包。

2026-11-04 最新状态：本轮[浏览与论文分组验收](p4-query-browsing-verification-20261104.md)已完成代码/自动化/打包，安装包在`.local/releases/p4-query-browsing-20261104/`，用户原生反馈待确认。各问答板块独立筛选论文、列表/引用10条分页、来源完整默认图谱标记、按真实冻结根分组和双层引用折叠已实现；跨页勾选保留。888 Python/122 React、首轮15 Edge及最后5 Query复测、15 Rust+打包Host1通过，详见报告，交叠不累加。head0014不变，无新真实调用/正式库实验/Commit/Push，不重复清理旧问答，不自动进入P5。

2026-11-04 当前：P4-Q01～Q07 已接入，Q08 正在修复安装后的来源显示、整组问答/导航和保存内容批注/移除反馈，Alembic head **0014**。决策见 [ADR0024](adr/0024-query-reading-cards-and-saved-lifecycle.md)，本轮状态见[反馈报告](p4-query-feedback-verification-20261104.md)；[ADR0023](adr/0023-grounded-query-and-explicit-saving.md)及[P4实际报告](p4-query-verification-20261104.md)保留前次结果。P5 Lint/Wiki 未启动，修复包原生确认另记。

更新：2026-11-04（Asia/Shanghai）。先阅读根 AGENTS、README、[文档导航](README.md)、[progress](progress.md)、开发日志最新条目及 docs/00～09；按实际代码和结果续接，不重建工程。

## 当前状态

R5 已推送 `main` 的 `80552d3`，[远端构建及独立安装 CI](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41778202007)均通过。随后 Query 改动尚未再次 Commit/Push，先前上传授权不自动延伸为新改动上传许可。

Q01～Q04 的决策与历史执行结果见 [ADR0022](adr/0022-query-foundation-and-versioned-context.md)及[Query 基础验收](p4-query-foundation-verification-20261104.md)；该阶段引入迁移 0012。Q05～Q07 新增有据回答、问答页面、显式保存和衍生图层，决策见 [ADR0023](adr/0023-grounded-query-and-explicit-saving.md)，迁移 0013 增加保存索引。领域 `reading-extraction-1.0`、入口 `paper-reading-v1` 及旧抽取任务协议保持。P5 Wiki 整理、发布与 Markdown 导出未开发。

当前接续安装后反馈修复，见[ADR0024](adr/0024-query-reading-cards-and-saved-lifecycle.md)和[反馈报告](p4-query-feedback-verification-20261104.md)。0014加独立保存偏好；query_presentation复用原文与已有中文要点，不改旧snapshot/hash或发请求。问答成组，原问答导航有可见状态；个人批注不进入科学上下文，移除穿透检索/衍生层/保存段落副本和依赖，原历史保留。修复包原生反馈不得以旧包的问题反馈替代。

主要运行模块为 `query_contracts/query_models/query_documents/query_retrieval/query_graph/query_context/query_api`，以及 `query_answer_contracts/query_answer_wire/query_answers/query_saved_models/query_save/query_saved_lifecycle/query_presentation`；前端为 `QueryPanel/queryApi/QueryDerivedGraph`：

- 项目级 QueryRun/QueryModelRun 和不可变回答版本记录真实执行，不把跨论文查询挂到第一篇论文。普通执行/文件审计不推进科学 GraphRevision，旧单篇 ModelRun/raw 保留。
- 最小文档 registry 保存不可变版本、逐段依赖及独立文件登记；内容有效性与文件同步分开，实时递归校验根来源/用途授权。Query 不把外部编辑拼接到旧 manifest。
- 可重建 FTS5/精确召回覆盖题名、合法候选双语/别名、原文/表格、有效文档及授权笔记；默认文献查询不读私人资料，模型用途默认关闭。
- 从种子沿完整合法支撑闭包和重验科学关系扩展，保留共享成员、四态条件及归属。画布分页/折叠/隐藏不影响结果；不继承旧 Comparator 的 3 跳/100 节点/48K 限制。
- `query-context-1` 冻结版本/hash、证据或只读 Chunk 引用、章节/完整表格组、路径、权限及短编号。prepare、缓存读取和 validate 重新组装终验；来源变化不能靠重复模型调用修复。

- P07 用 `query-grounded-semantic-1` 生成语义段落和短引用，发送前/返回后/重放前终验；持久账本最多两个请求，第二次仅明确继续触发，超时槽位不重发，来源变化不再收费重试。
- 显式保存通过 KnowledgeStore 幂等新增 Synthesis/Insight、不可变文档版本及逐段根依赖；只复制已选择的有效回答段落，不额外调用模型或覆盖论文 Claim。内部文档目标追加新版本，衍生图层与原科学图分开。
- 项目问答页提供本地证据预览、明确生成与继续、历史和逐条引用、选择保存、保存阅读库及衍生图层。默认不读私人材料；本地/model 授权和单次发送确认分别校验，失败或撤权时不继续展示私人缓存。

API 已接入 search、index/rebuild、prepare、runs/answers 读取与终验、generate/continue、save/saved/derived、saved annotation/remove、documents，以及 Obsidian query-permissions；Tauri 代理白名单和运行合同同步。prepare 只绑定 Reasoning 快照，不读取密钥或调用模型；真实调用仅由明确生成/继续进入执行路径。具体路径与状态见[运行 API](api.md)。

## 下一步范围

当前续接范围为 **P4-Q08 最终交付与新包原生反馈**：先看[P4最终验收](p4-final-acceptance-20261105.md)；本轮真实请求总计10次/1,623,354 Token，验收结束，不自动追加。原十题64支持/7部分/1数值错误与修复补验5支持/1部分分别保留；专用限制字段带审计占位后，同raw显式零调用恢复/保存/重启已通过。用户“数据功能正常”指旧锁修复安装包，本轮新性能/数值保护包反馈另计。任务、实现方法和验收要求见[开发计划](06_development_migration_plan.md)。不自动进入 P5 Lint/Wiki，后续开发须另有明确指令。

核验时保留实际发送前和响应后的 context 终验；模型只输出严格语义与请求内引用，程序绑定正式身份。科学段落保留归属、条件和限制，个人资料授权必须穿透 Wiki/综合。参考模板不直接替代运行契约，不能用“连接成功”代替结构化协议或真实回答质量验收。

查询默认不写科学知识；Q07 显式保存才新增衍生综合，不覆盖作者 Claim。当前可追加内部文档版本，后续 Wiki 整理/发布与导出 Markdown 分别明确。Query/Wiki/Lint 的职责沿用 [ADR0018](adr/0018-query-wiki-and-obsidian-lifecycle.md)。

## 继续前检查

1. 检查 git status/diff 和最新提交，保留已有未提交 Query 改动。阅读当前实际报告，避免重复已完成的 R5 付费验收或重抽论文。
2. 以 Conda `researchgraph-studio` 运行回归。迁移/撤权/文件故障只用隔离合成数据；不要把正式用户库升级作实验。
3. 依据[P4当前实际报告](p4-query-verification-20261104.md)确认未测项和已有真实调用账本，不重复已完成的付费请求。离线协议桩只验证链路，完整真实基准、规模性能、strict 与干净机结果分开记录；R5 的排序成绩不能替代 Query。
4. 任何 Commit/Push 前运行内容/路径及 Gitleaks 检查并核对暂存文件；私人资料、raw、数据库、日志、密钥和安装产物不入源码。未获新授权不 Push。

## 继承的 R5 基线

[R5 补验收](r5-acceptance-verification-20261104.md)记录两篇 P13v3 各一次成功、再继续零调用，32+2 已知错误不入默认图、5 组同义各一代表及安装反馈。有限证据和 partial 保留；真实 strict、复杂版面、跨平台/干净机及 S1～S4 补充原文不可用仍未认证。历史失败报告保持原结果。

抽取兼容与恢复以 [ADR0017](adr/0017-semantic-protocol-and-stage-recovery.md)、[ADR0020](adr/0020-evidence-aware-core-selection.md)、[ADR0021](adr/0021-keyed-ranking-and-bounded-correction.md)为准。旧 Job/签名/raw/模型记录不改，成功批次不重调；历史续接须展示接口返回的实际后继状态，不能假设原失败行变 queued，也不能把 ranking pending 冒充完整完成。详见[历史续接验收](history-retry-verification-20261104.md)。
