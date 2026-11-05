# 实施进度

2026-11-05 最新：用户已明确授权提交推送当前P4成果，并尝试修复未达标项。先按内容/路径/历史/暂存扫描交付现有已验收快照，再在P4内处理检索P95与科学部分支持问题；不进入P5。下列“无Commit/Push授权”为此前验收轮次状态，新提交SHA/CI和优化实测将另记，不将计划记为完成。

2026-11-05（Asia/Shanghai）**P4-Q08 已完成本轮全量回归、两篇真实论文问答及修复补验；新包原生反馈待确认，不进入P5。** 用户确认旧`318f`锁修复安装版数据功能正常；本轮新性能/数值保护包另计。通过只读SQLite backup建立验收副本，正式库实验写入0，head0014无迁移/重抽论文。见[P4最终验收](p4-final-acceptance-20261105.md)与[ADR0027](adr/0027-query-layout-aware-numerical-grounding.md)。

本轮最终check-phase0退出0：914 Python passed/2符号链接权限跳过（443.17秒）、124 React，Ruff/194格式/mypy103源文件/依赖/契约/前端静态及生产构建通过；289 Query包含其中，15 Edge及19 Rust/fmt/clippy、打包Host1通过。176运行源指纹无漂移。最终PyInstaller/Tauri/NSIS、冻结smoke和PS5.1隔离17项通过；正常worker两启每轮7读200，0.109/0.078秒，竞争写503 DATABASE_BUSY、47来源表保持、0模型请求。

真实十题：9有据回答/1不足零调用、72段/396次引用，原质量64支持/7部分/1上标误读数值错误如实保留。新增冻结numeric_layout与P07v2、正文风险数值守卫及旧v1新保存门槛；唯一额外真实补验六段5支持/1部分，限制说明列举危险数字曾被误拦，改专用limitations确定性占位并留跨度/哈希审计，原正文/raw不改。同raw显式零调用恢复成功，原失败Job/审计保留，幂等保存/重启可读。总10次真实请求/1,623,354 Token，费用未知，验收结束不追加。普通Query不改科学数据；副本实际分页/保存/批注/移除/重启与44来源表、原任务/raw保持已验证。

最终包`.local/releases/p4-final-acceptance-20261105/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,832,356字节，SHA256 `19929c6990fb1ae0fa166450431a586025664d219a40b942c3d240755c38a6b8`。最终主源码万候选/两万块基准cold3.129851秒、warm P50=2.608713/P95=3.016278秒，未达到≤2秒目标，不能用隔离候选1.922秒替代，P4性能门槛仍有保留。测试合成幂等常量安全收尾后19专项通过；618源码候选内容/路径/Gitleaks、180 Markdown/806链接/88资产LF hash通过，4外部原文不可用单列，交付配对见报告。本轮未替用户安装、Commit或Push；部分科学措辞、复杂版面/表格、真实strict、跨模型/平台、干净机继续保留，不宣称全部P4门槛或科学质量通过。

2026-11-04 22:11（Asia/Shanghai）**P4-Q08 问答历史“无效响应”锁修复已完成回归/打包，用户新包原生反馈待确认**。实际宿主日志只读脱敏定位history/documents/saved在BEGIN IMMEDIATE报database is locked。WAL+受query_only保护只读快照供8个Query读路径与模型等待状态检查，原写路径仍IMMEDIATE；worker空轮询先只读、有任务再短事务重验认领，数据库等待移出事件循环。锁超时标准503 JSON、Rust保留非JSON HTTP状态，历史失败提供只重读、不生成的按钮。决策见[ADR0026](adr/0026-query-read-snapshots-and-worker-locks.md)，成绩/限制见[锁修复报告](query-history-lock-verification-20261104.md)。

最终check-phase0退出0：895 Python/2 skipped（460.69秒）、123 React，Ruff/191文件格式/mypy102源文件/依赖/契约/前端静态与生产构建通过；5 Query Edge、19 Rust/fmt/clippy及新打包Host1通过。新PyInstaller/Tauri/NSIS通过；正常worker冻结进程两启，在独立写锁及另一个写请求等锁时，7个读接口200，0.063/0.062秒；写争用明确503 DATABASE_BUSY JSON、47来源表保持、Query1/Model0/Answer0不变、模型请求0。冻结smoke含本地SSE1 POST及PS5.1隔离5项通过，均为合成协议，不宣称真实科学质量。

新包`.local/releases/query-history-lock-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe`，38823098字节，SHA256 `318f14db52341b6c865f48d0a8cdf9cc08916510c162bc780434cf1790d8f73a`，174源码/281资源指纹一致，无私人运行资料。613源码候选内容/路径/Gitleaks、177 Markdown/788本地链接/88规范资产LF hash、diff/空暂存区通过，四份登记外部原文仍不可用。head0014无迁移，未读写正式数据库作实验，仅读宿主日志异常类型/栈；真实调用0，未Computer Use/替用户安装/Commit/Push，不进入P5。下文保留历史浏览包与其失败反馈，不将旧成绩算作本轮通过。

2026-11-04 20:38（Asia/Shanghai）**P4-Q08 问答浏览增量已完成自动化与打包验收，用户原生反馈待确认**。来源预览、回答、保存列表/详情和历史独立选择一/多篇论文；所有列表及引用固定10条分页、总数/页码，跨页勾选不丢。新search/page浏览本问题全部合法词面命中；图谱标记取完整默认投影，区分已有节点、支撑原文及仅检索。回答按冻结根来源归单篇/跨篇/未归属，跨篇只显一次；引用两层默认折叠，外层不联动内层，另有全展开/收起。已修复答案先到时的临时错归属。见[ADR0025](adr/0025-query-browsing-and-paper-grouped-answers.md)及[本轮验收](p4-query-browsing-verification-20261104.md)。

完整流水线888 Python passed/2 skipped（394.70s）、122 React、Ruff/190文件格式/mypy102源文件、依赖/契约/前端静态与生产构建通过；首轮15 Edge后最终问答5项复测通过（交叠不累加），15 Rust及新打包Host1、fmt/clippy通过。新PyInstaller/Tauri/NSIS退出0；冻结合成问答→保存/批注/移除与两次重启通过（本地协议stub1 POST），独立browse29条10/10/9、筛选28/1、图谱标记/hash变化与两启通过，47张非Query表保持、模型请求0；PS5.1/System32-only PATH本轮5项通过。head0014不变，无新迁移/Prompt变化，不把浏览全量等同新增语义综述检索。

新包`.local/releases/p4-query-browsing-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe`，38805905字节，SHA256 `8ae2e658dcff4f45ad47a6139332315355cdfb831a14c2b77886ce0e75a6b5d8`；174源码/281资源指纹一致，无私人PDF/DB/密钥/日志。610源码候选内容/路径/Gitleaks、175 Markdown/768本地链接/88规范资产LF哈希、diff/空暂存区通过；4份外部登记原文仍不可用。真实调用0、正式库实验读写0、未Computer Use/替用户安装，旧清理维护不再重复。未Commit/Push、不进入P5；下文是历史轮次状态。

2026-11-04 19:17（Asia/Shanghai）用户明确要求直接删除旧问答记录以重新提问：已清理安装版中的1条旧Query/答案/专属模型记录、2条关联保存内容及其段落、检索索引、任务和幂等结果；不保留本次被删内容副本，不发起模型调用。先在内存副本演练，再事务执行；44张来源/论文图谱等表逐行哈希保持，4篇论文和429个知识节点不变，数据库完整性/外键通过。此为用户授权的数据清理，不是新增开发或科学质量验收；下文18:11及更早的“旧问答/raw保留”描述对应历史修复轮次，正常产品移除仍为软移除。请用户重新打开问答页、重新输入问题验证；未改源码/安装包、未Commit/Push、不进入P5。

更新：2026-11-04（Asia/Shanghai）。**P4-Q08 当前处理安装后的用户反馈，数据库 head 0014，不进入 P5。** 用户已安装前次 P4 包并报告来源摘要/裸 ID、原问答跳转、问答分组和保存后无批注/移除问题；本轮新增本地只读来源 presentation、整组问答与可见原问答导航，以及独立保存偏好表。来源显示不改冻结上下文/hash、不新增翻译调用；个人批注不改模型答案，移除穿透检索/衍生层和保存谱系，原问答/raw/文档/论文证据保留。决策见[ADR0024](adr/0024-query-reading-cards-and-saved-lifecycle.md)，实际执行及修复包状态见[反馈报告](p4-query-feedback-verification-20261104.md)。

本轮最终879 Python passed/2 skipped、114 React、14 Edge、15 Rust+打包Host1通过；Ruff/186文件格式/mypy100源文件、依赖/生成契约/生产构建通过。最终冻结HTTP/SSE协议stub的问答→保存→批注→重启→移除→重启通过（仅1次本地stub POST），PS5.1/System32-only PATH隔离17项通过；冻结0013→0014两次启动保留62张旧表列/行、旧manifest/raw及准确升级前备份。旧0013保存谱系只读恢复及损坏隔离已补；正式库实验写入0，真实请求0，不重抽论文。

最终修复包`.local/releases/p4-query-feedback-final-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe`，38793801字节，SHA256 `163a6cb9a1f68040d0482a11a0c989c85be781516d348175955b1c14bd575f9f`；171源指纹与281份资源（不含生成pycache）一致。603源码候选内容/路径/Gitleaks、173 Markdown/742本地链接/88资产LF哈希及空暂存区通过；四份登记外部原文仍不可用。未取得修复包用户原生反馈，不宣称已通过；没有使用Computer Use或替用户安装/卸载。前轮10次真实调用成绩保留历史，未Commit/Push、不进入P5。下面15:04/15:08及更早条目为对应历史交付状态，其中“原生确认待反馈”已由本轮问题反馈更新。

更新：2026-11-04 15:04（Asia/Shanghai）。**P4-Q05～Q07已实现，Q08本机验证和安装包已交付，原生确认待反馈，不进入P5。** 项目问答接入P07有据回答、逐段引用/归属/限制、发送前持久账本（每Query最多2槽、显式继续）、取消/失败恢复与历史；Store明确保存Synthesis/Insight及独立衍生图层。0013加性迁移只增保存表，旧论文/知识/raw保持，普通Query零科学改写，保存才新revision。见[ADR0023](adr/0023-grounded-query-and-explicit-saving.md)、[实际报告](p4-query-verification-20261104.md)。

本轮完整流水线先通过838 Python/2 skipped、108 React；最后多篇覆盖/性能补丁后全Query专项237通过，最终源码全量862 passed/2 skipped（332.31s）再通过；交叠专项不累加。13 Edge、14 Rust+1打包Host、clippy/fmt、静态/生成契约/依赖/前端生产构建、最终PyInstaller/Tauri/NSIS、冻结HTTP/SSE协议stub问答→保存→重启（1次stub请求）及PS5.1隔离17项通过。自动化合成资料、真实模型、用户原生分开，新增源码/测试未削减旧回归。

真实两篇/10题：9有据回答、1无证据零调用，实际10次/737701 Token（包含第4题坏JSON后的唯一第二槽，原失败/raw保留），供应商金额未知，调用已停止。原4篇来源/1921Chunk/1930Span/758知识/129旧ModelRun及18旧Job等逐行保持；显式保存2份综合后重启读取通过，正式库实验写入0。62段独立来源审读58支持/4部分支持、0完全无据/归属错；条件、架构限定与表头遗漏如实保留，不宣称全局科学正确。第9题原召回缺一篇，程序已补公平保位与missing零外发；相同真实题仅本地prepare已覆盖两篇，未付费重答，不改旧答案。

1万候选/2万块混合基准：冷1.985s、warm P50=1.736s/P95=1.986s（12样本nearest-rank=max），本机≤2s目标达到；峰值RSS279097344B，总库45961216B、FTS逻辑UTF8 3687347B。SQLite不支持dbstat，物理FTS页大小未知；合成共享来源分布不代表真实复杂表格/多论文全负载。旧冷192s瓶颈已定位并优化，来源和边证据终验保留。

新包`.local/releases/p4-query-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe`，38786476字节，SHA256 `861ef988c12ef5bfba8f70fa0d0e5b68348903cefa987698cc932273b6bbe97e`；165份打包源指纹一致，资源无私人PDF/DB/.env/日志。已请求用户新包问答/引用/保存/重启反馈，尚未反馈不算原生通过；干净机/真实strict/复杂版面无OCR、S1–S4四份外部补充原文不可用继续保留。安全/文档与交付配对结果见末次收尾。本轮未Commit/Push；HEAD/origin记录仍80552d3，R5远端CI不算本轮Query CI。

15:08收尾：最终862 Python/2 skipped、237 Query专项、108 React/13 Edge/14 Rust+Host1、PS5.1隔离17及冻结smoke通过；596源码候选实际内容/路径/Gitleaks、171 Markdown/704本地链接/88资产LF哈希、diff与空暂存区通过。四份外部原文不可用保留，用户新包原生反馈待确认；安装副本/165打包源指纹一致，真实请求保持10。未Commit/Push，P5未开始。


更新：2026-11-04（Asia/Shanghai）。**先推送 R5，随后完成 P4-Q01～Q04 后端基础。** `main` 已推送 `80552d3`，[该提交远端 CI](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41778202007) 的 Windows 回归、真实 Edge 图谱、冻结引擎/Rust/NSIS 及独立安装验收全部通过。下面的 Query 改动尚未再次 Commit/Push，R5 的远端成绩不冒充本轮 Query CI。

新增项目级 Query 契约/执行与文档版本、逐段依赖及内容/文件双状态；FTS5/精确术语与中文双字片段检索完整合法候选/原文/表格/有效文档及用途授权笔记；沿完整合法结论支撑与种子相邻科学关系补条件和根证据；query-context-1 冻结短引用、版本/hash/章节/表格/权限并重放。默认不读或外发私人笔记，撤权穿透文档/幂等缓存，原文没有 span 时只读引用 Chunk，不造科学知识。Query 索引/准备与笔记扫描使用独立审计，不推进 GraphRevision。Alembic **0012 加性迁移**、旧行与升级前备份在隔离库验证，正式库不作实验；领域/阅读协议不变。实现见[ADR0022](adr/0022-query-foundation-and-versioned-context.md)、[实际报告](p4-query-foundation-verification-20261104.md)。

完整检查 **734 Python passed/2 skipped、90 React passed**，Ruff/格式/mypy 91 源文件、依赖/生成契约/前端静态与生产构建通过。最终补齐宿主 Query/用途授权受限路由、本地路径拼接边界及模型容量冻结后，六个 Query 文件 **113 项**、Rust fmt/clippy 与 **11 项单测+1打包宿主**通过；交叠专项不累加成全量。已修复持久解析及表格引用/范围负例，保留完整必要支撑；容量不足标不足，不删表头或条件。最终 PyInstaller/Tauri/NSIS、冻结 smoke（含Query幂等/重验/重启/零科学写入）及 PS5.1 独立数据 **17项通过**。新包`.local/releases/p4-query-foundation-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,717,661字节，SHA256 `55fb899ea2c603cb4488a7b98c0cea4c6fe97bc0826f785df71adeea4ca406c2`；未替用户安装或运行正式库，新包原生/干净机不记通过。

当前只提供 search/index/prepare/read/validate 后端基础，没有问答 UI、P07/P08 调用、用户保存回答或 Wiki 发布。**本轮真实模型请求 0**；下一步 Q05 有据回答，Q06 页面、Q07 显式保存、Q08 24题/性能/真实链路仍待开发，不进入 P5。未重复运行无前端变更的浏览器回归，保留真实 strict/干净机/OCR复杂版面与 S1–S4 四份外部补充原文不可用限制；此前“P4未开始/head0011”是下列对应历史轮次状态。

13:58 收尾：571 源码候选路径/内容/Gitleaks、168 Markdown/662 本地链接/88 规范资产 LF 哈希、diff 与空暂存区通过；4份外部原文不可用如实保留。新包/冻结引擎与源码指纹、日志和delivery配对，本轮未再次Commit/Push。

更新：2026-11-04（Asia/Shanghai）。**R5实际剩余三项补验收已完成，范围内通过，未开始P4/P5。** 本轮获用户明确授权，用当前全局兼容模型/max配置在独立副本续接：两篇P13v3分别38/105槽位，各1次成功、发布7/20单元；P02/P12新增0、再次继续新增0，无编号冲突/额外字段/超时。原失败/raw/签名保留，旧16任务/127模型整行/758节点及来源证据解析逐行保持，正式库实验写入0。总计2真实请求/276,699总Token，供应商金额未提供；真实调用到此结束。

32条无支持候选与2条上标误读均为retrieval_only、核心/支撑0条；旧5同义组各1核心代表。36/232成员路径（5/138多跳）及可见/候选锚点错误0，343新P02候选全保留；6主要贡献均有图谱代表，15参照组仍可检索，选择性图谱不要求全部入图。有限证据核心2/1均有caveats；条件known/unknown如实保留，无真实conflicting/not_applicable样本。22/45条coverage_gaps使两图仍partial，排序complete不冒充全文无缺口；不外推全局科学准确率。

最新history-retry包安全解包/源码与289资源一致，**PS5.1隔离17项、打包Host1项、0008/0009/0010三旧库升级及重启通过**。用户明确反馈本包原项目与证据可读、原失败继续定位成功后继、退出重开知识/任务持久三项全部通过。101 Python专项/32 React任务历史本轮通过；无运行源码变更，不重复打包或冒充前轮全量回归。实际命令/数据/边界见[本轮R5验收](r5-acceptance-verification-20261104.md)。strict/干净机/复杂版面和4份外部补充原文不可用仍单列，4份运行附件PDF哈希匹配；未Commit/Push/远端CI。后续明确开发指令可从P4-Q01开始，本轮停止于R5验收。

更新：2026-11-04（Asia/Shanghai）。**修复历史抽取任务点击继续无反馈，仍P3/R5。** 只读核验用户报告的 `items.1.Claim.kind_note_unused (extra_forbidden)`：旧P02v2任务停在31/34、字段为Claim上的null，其独立P02v3后继已于11月3日34/34成功发布。后端正确幂等返回成功后继；原界面丢弃返回Job，历史失败行保持，造成无响应。限定null兼容已存在，无需放宽Schema或重抽。

JobHistory现在反馈提交中及实际返回状态、关联历史与“查看续接结果”；分页外后继单独显示/轮询，终态停定时，刷新失败保留结果。更新操作结果前取消在途单任务GET，防止旧running覆盖cancelled；旧queued缓存不覆盖返回成功，ranking_status=pending不称完成。原失败/raw/知识保持，未改后端运行代码、Schema/迁移、来源PDF或私人材料，无新增真实模型请求或正式库写入。详细证据与本轮包见[历史续接验收](history-retry-verification-20261104.md)。

本轮`check-phase0.ps1`退出0：**625 Python passed/2 skipped、初轮88 React**；最后两项前端竞争/文案补丁后重新完成format/check/test/build，**最终90 React通过（任务历史32项）**。Ruff/154文件格式/mypy83源文件、依赖/契约/TS/ESLint/Prettier及生产构建通过；专项旧响应兼容/幂等17项另通过。PyInstaller/Tauri/NSIS、最终冻结smoke及PS5.1隔离17项通过。已有httpx弃用/大chunk提示及本机权限跳过保留；没有因本轮交互修复重复运行图谱浏览器或Rust测试，不把上一轮结果当本轮。

新包`.local/releases/history-retry-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,710,564字节，SHA256 `d5320ac80159fca0ead50da3298c5f7e52352f226cc733126a62aba2bbbad34c`；引擎hash与上轮相同。退出软件后安装，原历史任务可直接查看成功后继，无需删除知识/重抽；本包原生待用户反馈。554源码候选路径/内容与Gitleaks、165 Markdown/637本地链接/88资产LF哈希核验通过，四份外部原文不可用单列；diff通过、暂存区为空，包/日志/交付清单本机配对。R5科学质量/真实P13/strict、干净机仍有验收限制。不进入P4/P5，未Commit/Push。

更新：2026-11-04 10:31（Asia/Shanghai）。**按用户纠正修复软件的P13协议可靠性，不以更换模型为前提。** 新P13v3/reading-ranking-keyed-1由程序固定完整编号槽位，模型只写贡献判断与整数priority；同源Schema/Prompt，程序稳定排序，完整原文/疑点/排版上下文不减。合法外壳下有效槽位仅作私有检查点，缺失/非法槽位定向修复一次；持久账本每构建最多2请求，含超时，继续不重发已发送槽位，不删字段或合并冲突。见[ADR0021](adr/0021-keyed-ranking-and-bounded-correction.md)及[实际验收与安装](ranking-protocol-verification-20261104.md)。

旧v1/v2计划/签名/raw及历史ModelRun参数保留。原排序失败通过“继续未完成批次”创建独立v3后继，重验真实P12及显式adoption链，零重复P02/P12；上轮两篇隔离真实失败任务只读核验均可采用可信P12，冻结输入一致、session无改动。未知谱系/来源或支撑变化明确停止，不追加付费P12。本轮真实API请求0、正式库写入0，无迁移/head变化，无人工审核，不进入P4/P5。

最终**623 Python passed/2 skipped、80 React、10真实Edge/React Flow、9 Rust单测+1打包宿主通过**，最终恢复/旧任务47项另复验。Ruff/格式/mypy83源文件/依赖/契约/前端静态/生产构建通过；PyInstaller/Tauri/NSIS、冻结smoke新版键控评估、PowerShell5.1隔离17项通过。首轮旧投影fixture不识别新title及首次PS调用测试PDF路径错误均修复并重跑，保留日志；httpx弃用和大chunk提示、两项符号链接权限跳过如实记录。

新包`.local/releases/r5-protocol-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,708,292字节，SHA256 `a10e7b14dbb9d8f283d3e973ce79fab92980cc974ae89cc6f1e158405f53b37c`。退出旧应用后安装，保持当前模型，在原失败任务继续即可，无需删除知识/重抽。当前仍P3/R5：本包原生和真实P13/科学质量未验收，之前32条语义无支持与2条上标误读仍待核对；strict/干净机/四份不可用外部原文限制保留。10:33收尾：553文件最终敏感内容/路径扫描、164 Markdown/632本地链接/88资产LF哈希、diff及空暂存区通过；最终包与源/交付清单hash一致，日志配对保存。未Commit/Push/远端CI。

更新：2026-11-03 23:42（Asia/Shanghai）。**R5本轮代码/回归/安装包完成，真实科学质量验收未通过；用户选择先交付，稍后更换模型。** 仍P3/R5，不进入P4/P5。新增[ADR0019](adr/0019-support-path-revalidation.md)支撑路径manifest/缓存与发布再验，以及[ADR0020](adr/0020-evidence-aware-core-selection.md)P13v2真实原文/疑点/数字排版上下文、碎片核心门槛和成员caveats。旧v1 Prompt、冻结计划/签名/raw、head0011/领域1.0不改，安全诊断显示路径而不反射输入或未知key。

最终**547 Python passed/2 skipped、76 React、10真实Edge/React Flow、9 Rust单测+1打包宿主通过**；静态/依赖/契约/生产构建、最终冻结smoke、PS5.1 16项与PyInstaller/Tauri/NSIS通过。用户已反馈上一包三篇同显、悬停拖动、颜色图例、全屏Esc、重启知识布局五项全部通过；本轮新包尚无原生反馈。详见[实际验收与安装器](r5-final-verification-20261103.md)。

隔离真实P02两篇6/6与15/15：87/256新候选的186/426证据链接机械锚定0错误，但第二篇确认32条不受引文语义支持及2条上标误读。新排版helper命中真实风险；P13v2两篇各2次均因重复/冲突编号或额外字段未通过，没有新选择发布、旧图保留，不能把修复接入或Schema通过当科学质量通过。第一篇旧v1部分结果路径80条闭合，但有同义根/疑点支撑边界。

主验收32次真实请求、已返回1,329,531 Tokens；另并行误调度2次P12已停（用量/费用未知），共34次已知发出，供应商金额未提供。原415知识/95原raw保持、4源hash匹配、SQLite完整性通过，正式库写入0。原配置不改；独立新配置续接明确新签名/提交谱系，没有重调已保存批次。用户选择后停止所有模型调用。

新包`.local/releases/r5-final-20261103/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,674,011字节，SHA256 `dc5a1ab1c8961947dc51a5a4acf31fc812a6f4c22f244a82ce62579b4d84d6bc`。退出旧应用后安装，无需删除原知识。真实strict/干净机/新包原生未验收，四份外部补充原文不可用；未Commit/Push或远端CI。2026-11-03 23:45（Asia/Shanghai）收尾：161 Markdown/613本地链接/88资产LF哈希通过，四份登记外部原文仍不可用；544源码候选内容/路径及Gitleaks通过，git diff --check通过、暂存区为空。最终安装器副本与构建源长度/hash一致，离线日志与匿名结果封存；未Commit/Push，真实P13未过且用户选择稍后换模型，不进入下一Phase。

更新：2026-11-03 21:32（Asia/Shanghai）。**按图谱驱动的完整阅读生命周期重写开发计划并同步项目介绍；仅文档，不启动P4/P5。** 知识图谱明确承担结论组织、合法支撑路径与条件比较结构，Query从完整Store命中后沿图扩展并补原文/未选候选/有效Wiki/授权资料；明确保存才新增Synthesis/Insight等衍生对象，并可在独立图层回溯来源。Wiki按结论单元组织主题/分歧与条件，Markdown为授权导出表达；Lint检查来源、图结构、逐段依赖和文件同步。

[开发计划](06_development_migration_plan.md)改为当前基线→完整流程→R5剩余验收→P4-Q01–Q08→P5-L01–L04/W01–W05，保留17项实施/验收任务并补图谱作用对照测试。只读代码核对确认旧Comparator仍有3跳/100节点/48K限制、FTS仅knowledge_nodes.text、ModelRun单文献绑定及Store.event/Obsidian扫描推进GraphRevision；均列为新Query契约/适配任务，不改旧兼容路径。P4先有最小Wiki登记/状态/只读适配，P5扩展生成发布；保存回答、整理Wiki与导出MD分开。

同步根README、docs导航/00–08、ADR0018、协作与下一轮模板；当前仍P3/R5，head0011/运行Schema/Prompt/用户库/安装器不变。无真实模型调用、迁移、应用回归、打包或Git上传；上一轮460 Python/76 React/8浏览器等结果仅作历史基线，不记本轮重跑。最后文档/敏感核验结果收尾补记，四份已登记外部原文不可用限制保留。

21:44收尾：17项任务/流程边界、157 Markdown/591本地链接/88资产LF哈希、538候选文件Gitleaks/路径检查通过；284个非文档文件保持，暂存区为空且diff检查通过。独立复核补清无单元原文/候选和Zotero评论可用，外部MD登记不继承证据/写权。仅文档与Mermaid源文本基本检查，未做渲染器或应用回归，不记P4/P5功能通过；四份外部原文仍不可用。

更新：2026-11-03 17:38（Asia/Shanghai）。**补清Query/Wiki/图谱/Obsidian数据边界，仅设计未实施。** [ADR0018](adr/0018-query-wiki-and-obsidian-lifecycle.md)明确Wiki是带逐段依赖的阅读文档，不是当前图谱；Query兼读有效Wiki/已保存综合和底层知识/证据，并检查版本、权限、内容有效性及文件同步。P4前置最小文档登记/状态/只读适配，P5扩展生成发布，避免此前“P5以后才读Wiki”的缺口。

保存问答默认新增有据Synthesis/Insight等衍生对象，不覆盖作者Claim/原选择；整理/更新Wiki与导出MD分别明确动作。外部手改MD不继承旧manifest或自动回写图谱，内容过期和磁盘不同步分开；Lint区分受管MD和授权私人笔记，核验根证据/依赖/hash/链接，缺元数据不直接判科学错误。同步00–03/05–08、导航/协作约定和17项开发任务及验收；当前仍P3/R5，head0011/运行代码/Schema/Prompt/用户库及安装器不变，无模型调用/Commit/Push。文档核验收尾另记；四份外部原文不可用限制保持。

17:39 收尾：17项规划编号/顺序及P4先读Wiki的约束通过；157 Markdown/573本地链接/88资产LF哈希通过，四份登记外部原文仍不可用；538源码候选路径/内容及Gitleaks通过。独立审阅补清Q07仅登记已验段落文档版本，P10/P11与渲染/发布留在P5；本轮未运行应用回归，文档变更不记功能验收。

更新：2026-11-03 17:16（Asia/Shanghai）。**完成P4 Query / P5 Lint-Wiki详细规划，尚未开始这两个Phase的实现。** [开发计划](06_development_migration_plan.md)现包含P4-Q01–Q08、P5-L01–L04与W01–W05共17项任务，每项列出实现方法/交付物/验收，另有契约缺口、拟定接口、依赖顺序、自动化/真实模型/原生交付门槛和安全边界。当前实际工程仍为P3/R5；此前3篇真实安装反馈与图谱回归结果保持原记录。

本轮代码核对确认knowledge_fts只索引知识节点，正文/表格/中文/笔记统一检索需新增；ModelRun绑定单篇及Store.event递增GraphRevision需在Q01解决，不能让普通问答日志改变知识图谱。P4默认只读、显式保存；P5先规则Lint与逐段依赖，再P09语义建议、P10整理、授权受管导出及P11增量diff，不增加人工审核。参考Schema/Prompt尚不是运行实现；保留旧库、原文/私人笔记、旧任务签名及现有未提交成果。

本轮只改开发计划、入口/API说明和进度/日志，不改运行代码、Schema/Prompt或数据库，不调用真实API、不构建新包、不Commit/Push。文档编号/链接/清单核验结果收尾补记；四份登记外部原文不可用限制保留。后续开发顺序由计划明确，不因本轮写计划自动启动。

17:17 收尾：17个唯一有序任务编号与待开发/验收目标状态核对通过；156 Markdown/561本地链接/88项资产LF哈希通过，四份外部原文不可用单列；537源码候选路径/内容及Gitleaks通过。当前运行Schema/head0011和安装器保持，暂存区为空。

更新：2026-11-03 16:53（Asia/Shanghai）。**用户报告已真实安装并跑通3篇论文，本轮完成图谱工作区修复与新包构建。** 补全11类节点颜色/未知回退及上方横向图例；修复第一篇占满60节点导致其余论文不显示，按论文轮换、结论/支撑交替分页，游标绑定图版本；切范围新响应后适应视口，支持手动适应及失效游标回首页。全屏保持同一画布、固定位置和焦点恢复。搜索筛选美化后置顶，图谱紧随，全部论文的候选/建图选项移至页末且独立展开；重复任务记录移除，仅文献与阅读保留。见[实际验收与安装器](graph-workspace-verification-20261103.md)。

**460 Python passed/2 skipped、76 React、8真实React Flow、9 Rust单测+1打包宿主通过**。Ruff/格式/mypy79源文件/依赖/契约/前端静态及构建通过；PyInstaller/Tauri/NSIS、冻结smoke、PowerShell5.1 EnginePath五项通过。首轮前端lint发现新增memo依赖声明问题，修复后完整前端检查重跑；浏览器发现全屏竖排图例占高，改横排后8项最终通过。三篇各70主节点后端分页及三篇合成前端独立验证，不读取用户库或论文，不新调用模型。

新安装器 `.local/releases/graph-workspace-20261103/ResearchGraph Studio_0.0.1_x64-setup.exe`，38659968字节，SHA256 `d75462a2df3d19ff76ca1a2d2212fd34808a7e1243d42533b3cbfc3ed08f534f`。退出后安装即可使用原知识，无需重抽；当前包原生交互待用户反馈。用户3篇反馈不等于独立科学质量/strict验收。仍在R5，head0011/领域/数据不变，不进入P4/P5；未Computer Use、未替用户安装/卸载、未Commit/Push。四份原文路径不可用限制保留。最终敏感内容/文档核验另补记。

16:54 收尾：537 个源码候选内容/路径及 Gitleaks 通过；156 Markdown/554 本地链接/88 清单资产及 LF 哈希通过，四份外部原文不可用单列。git diff --check通过，暂存区为空，最终安装器/交付信息/验证日志与合成截图配对保存；未上传运行或私人材料。

更新：2026-11-03 16:10（Asia/Shanghai）。**四项语义协议与恢复可靠性改造已接入并完成本地回归/新包构建。** 新 P02v4/reading-semantic-1 减少身份外壳，Prompt 规则从实际 Schema 生成核对；Provider 新快照冻结 strict/兼容 JSON/提示路径，不自动降级收费。新 P12 仅补语义关联，程序沿合法路径组单元，P13 仅贡献建议并保存名次；首次失败明确 provisional/pending/partial，已有图保留。所有阶段的新响应与缓存共用终验，可信来源/快照变化停止而不改写历史模型成功状态。见[ADR0017](adr/0017-semantic-protocol-and-stage-recovery.md)和[本轮验收及安装](semantic-reliability-verification-20261103.md)。

最终 **457 Python passed/2 skipped、59 React、3 真实图谱渲染、9 Rust单测+1打包宿主集成通过**；Ruff/格式/mypy79源文件/pip/契约/前端检查与构建、PyInstaller/Tauri/NSIS、冻结smoke、PowerShell5.1 EnginePath五项通过。真实备份隔离副本复用旧P12与P13检查点、第五组零调用恢复，第六组调用边界停止；新语义失败副本首次显示51个来源有效候选根，已有图保留原21根，均明确未排序完成。原始响应、知识、证据及冻结计划保持。正式库写入及真实模型请求均0；真实 strict、两篇新模板全文和用户原生安装仍待验收。

新安装器位于 `.local/releases/semantic-reliability-20261103/`，长度/哈希见报告。旧任务维持旧协议及成功检查点，新任务使用新语义流水线；不需删除知识或重建工程。head0011/内部领域1.0/入口不变，仍在R5，未进入P4/P5。本轮未使用Computer Use，未替用户安装/卸载、未Commit/Push；四份登记原文不可用限制保留。最终安全及文档核验另补记。

16:14收尾：525个源码候选内容/路径及Gitleaks通过；155 Markdown/549本地链接/88清单资产核验通过，四份登记外部原文不可用单列。git diff --check通过，暂存区为空；新安装器长度/哈希与delivery及构建源一致。最终安全、文档报告已配对保存在本机release目录；真实新模板全文和用户安装反馈仍待验收。

更新：2026-11-03 13:55（Asia/Shanghai）。**P13 JSON 末尾数组缺括号已修复并完成新包构建。** 实际失败任务已完成34/34抽取、10/10整合与前4组选择，第5组4359字符响应的末字段 coverage_gaps 漏一个 `]`，不是PDF抽取失败。仅该完整字符串数组且根 `}` 已存在的形态可补一个字符，原 raw/科学字段不改，完整 Schema/来源/版本白名单仍验；P13正常和恢复路径同时严格拒绝重复键及NaN/Infinity，防止静默覆盖。成功恢复同时清空旧error。见[ADR0016](adr/0016-selection-json-syntax-recovery.md)与[实际验收/安装](selection-json-verification-20261103.md)。

最终 **317 Python passed/2 skipped、47 React、9 Rust单测+1打包宿主集成通过**；Ruff/格式/mypy73源文件/pip/契约/前端检查、PyInstaller/Tauri/NSIS、冻结smoke、PowerShell5.1五项通过。只读备份隔离恢复精确复用10个P12和4个P13检查点，第5组零API重验并保存新检查点，error已清空，原raw/用量/冻结计划/其他数据保持；在第6组无网络Probe边界主动停止，真实调用0。后续真实选择与用户安装反馈仍待验收。没有新增上下文预算、改Prompt/领域或迁移，仍在R5；未修改正式库、未Commit/Push。

13:59收尾：509源码候选内容/路径及Gitleaks通过；150 Markdown/522本地链接/88清单资产核验通过，四份外部原文路径不可用。git diff --check通过、暂存区为空；安装器与delivery哈希一致。最终严格解析隔离恢复再次通过，未新增真实请求。

更新：2026-11-03 12:56（Asia/Shanghai）。**移除整合/选择阶段的固定上下文预算，修复 P13 在模型调用前超过 48000 字符便失败。** 新 complete-context-v1 用完整候选/引用证据执行一次 P12、全部单元执行一次 P13；旧窗口优先读取，旧签名/P13 分组与已成功检查点复用，不重复全文抽取或成功整合。实际两任务抽取已为15/15、34/34，P12检查点4/4、10/10可复用；副本零网络探测直接到达超48K的P13调用边界，旧知识/来源/模型结果及冻结计划保持。不是实际模型选择成功。

最终 **287 Python passed/2 skipped、47 React、9 Rust单测+1打包宿主集成通过**；Ruff/格式/mypy72文件/pip/前端检查、NSIS构建、冻结引擎smoke、PowerShell5.1五项通过。新安装器及步骤见[本轮实际验收](complete-context-verification-20261103.md)，设计见[ADR0015](adr/0015-complete-reading-context.md)。安装后继续原失败任务即可，无需重抽；真实选择/用户安装反馈仍待验收。0011及领域/Prompt不变，仍在R5，未进入下一Phase，未Commit/Push。

更新：2026-11-03 11:08（Asia/Shanghai）。**结构解析、默认结论支撑和 null 占位 Schema 恢复已完成，本地安装包已构建。** 仍处于 R5，未进入 P4/P5。0011 仅增加版本化结构解析旁表，保留旧原文块和证据；新 P02_compact_v3 按包含子节的跨页章节输入，排除 References，无 6000 字符/48 证据目标。默认图谱展示核心结论下有明确来源关联的方法、实验、条件等，显式收起且共享节点去重。

最终 **283 Python passed/2 skipped、47 React、3 真实 React Flow、9 Rust 单测+1 打包宿主集成通过**；Ruff/mypy72文件/依赖/契约/前端构建、冻结引擎 smoke 和 PowerShell5.1 EnginePath 五项通过。两篇真实 PDF 隔离解析为35/14章节，离线容量规划为11/6窗口（最大18270/18895字符），不冒充真实模型成功。真实失败 `kind_note_unused:null` 零调用恢复4候选/0关联，262旧知识/47旧ModelRun及原响应保持。现有真实投影38节点54边，含方法/实验/条件；收起后10节点。正式库未改。新包、哈希及原生操作步骤见[本轮实际验收](structured-reading-verification-20261103.md)。新Prompt真实全文生成及用户安装反馈待验收；四份外部原文路径不可用。本轮未Commit/Push。

更新：2026-11-03 00:08（Asia/Shanghai）。**本轮代码已推送，远端构建与安装验收全部通过。** 功能提交`1c28137`、验收配对修复`a4cd365`，均为普通推送main。[CI 41474458777](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41474458777)的windows与installed-app成功；安装报告20项通过，包含桌面宿主握手、退出/崩溃清理、来源/知识保留及卸载。CI合成离线测试不代替真实模型质量或用户本机反馈。仍处于R5，下一步为用户安装续接反馈及全文支撑/表格覆盖；P4/P5未开始。详细提交、安全扫描与安装包见[本轮报告](schema-scope-verification-20261102.md#最终交付)。

更新：2026-11-02 23:36（Asia/Shanghai）。本轮已安全提交并普通推送main：`1c28137`。首次远端CI在冻结引擎验收读取关系详情时404，安装任务未运行；发现合成样本按列表首行配对会选到不相关Claim，正常NO_DECISION没有proposal_id。控制样本顺序复现相同404后，验收脚本改为按双方明确的共同原文配对，并在读取详情前断言候选存在。修复后本机冻结引擎连续两次通过；产品源码及已有安装包未改变。远端复跑结果待补记。

更新：2026-11-02 22:59（Asia/Shanghai）。**R5新版候选范围与抽取续接已修复，全文质量仍需完善。** 当前默认仅使用reading-extraction-1.0来源/DTO，旧unified知识保留历史；新P02_compact_v2/P12_v2/P13_v3闭合模板与候选/说明校验已接入。旧失败任务通过普通继续创建独立新版续接，成功操作和可重验响应复用。

真实隔离副本9/12→12/12并发布22核心单元；重开后23默认节点、28展开节点/29边，全部为新版且边闭合，422原知识/48原模型记录/9原任务及原文逐行不变。实际结果partial：仅5个支撑节点，表格/公式及支撑质量未全面通过。另一个最终P13窗口8根通过。累计15次真实调用/213503 Tokens，金额未提供。243 Python/2跳过、46 React、3真实图谱渲染测试通过，详见[本轮实际验收与安装](schema-scope-verification-20261102.md)、[ADR0013](adr/0013-current-schema-and-bounded-recovery.md)。未操作正式库或Push；下一步仅R5安装反馈与论文支撑覆盖，不进入P4/P5。

更新：2026-11-02 21:27（Asia/Shanghai）。**R5输出能力与Schema精简完成，全文仍待验收。** 按用户纠正移除供应商专属按钮，统一“继续未完成批次”；不再额外限制32K/64K，按模型最大输出及剩余上下文请求。新P02_reading_extract_compact / reading-compact-1省略可无损还原的摘要/语言重复，并明确SourceText原文字符串形式；旧领域1.0/数据库0010/旧Prompt与成功批次保持。

真实端点接受393216额度，约27秒完整响应；首次Finding.baseline纯文本导致结构校验失败，完善新wire规则后同响应零调用重验，12候选/10有效关联保存、2无效关联隔离，396旧知识逐行不变。本样本紧凑响应比展开少约24%字节；不是全文或通用质量成绩。最终 **229 Python passed/2 skipped、45 React passed**，静态/依赖/契约/构建通过；新安装器、冻结引擎smoke、PowerShell5.1 EnginePath及1项原生宿主集成通过。未替用户安装、未Commit/Push。详见[最新验收与包](compact-output-verification-20261102.md)、[ADR0012](adr/0012-compact-extraction-and-model-output-ceiling.md)。下一步限于R5全文与安装反馈，P4/P5未开始。

更新：2026-11-02 20:52（Asia/Shanghai）。**R5 腾讯云流式适配与空图谱恢复已实现，全文验收仍未完成。** 腾讯 Token Plan `deepseek-v4.1-flash` 文档能力为1M上下文/384K最大输出；新抽取默认非思考JSON、SSE与有界总时限。旧失败任务可显式新建续接，冻结签名/成功批次与原记录保留；未发布图显示候选数，支持停止后基于候选生成明确partial图谱。原始证据/知识保留，head0010无迁移。

原超时子批真实一次请求9.531秒通过：4候选/2关联、7541 Tokens、reasoning=0；隔离库396原知识逐行不变。同响应零网络回放到真实旧计划6/12→7/12，成功批次未重调，原任务/签名不变。不是两篇全文成功。完整回归 **214 Python passed/2 skipped、45 React、3真实React Flow、9 Rust单测+1打包宿主集成通过**，lint/type/依赖/契约/构建与冻结引擎smoke/PowerShell5.1通过。新包保存于本机，未替换运行软件，未Commit/Push。详见[实际结果与安装包](tencent-recovery-verification-20261102.md)和[ADR0011](adr/0011-tencent-streaming-and-reading-recovery.md)。下一步仍为R5两篇全文、真实部分建图和用户安装反馈，未进入P4/P5。

更新：2026-11-02 19:31（Asia/Shanghai）。R5 修复新阅读任务的 `batch(value_error)`：真实输出 28 候选中 8 个完全重复，严格字段/来源检查后可确定性合并并记录审计；同编号不同内容仍拒绝。原失败响应与成功批次可复用，Prompt/Schema/冻结计划/head 0010 不变。隔离真实副本新增 20 候选、保留 24 关联，307 条原知识逐行不变，新增模型调用和 Token 均为 0；不是全文成功。界面子批改为“已保存（超时拆分后）”。

本轮整体检查 **189 Python passed / 2 skipped、40 React passed**，Ruff/mypy/依赖/契约/前端构建通过；PyInstaller/Tauri/NSIS、冻结引擎 smoke、PowerShell 5.1 EnginePath、1 项原生宿主打包握手与重启测试通过。安装器已保存在本机，未替换运行中的软件；没有 Commit/Push。详见[验收报告及安装包](reading-response-verification-20261102.md)和 [ADR 0010](adr/0010-reading-response-deduplication.md)。

仍处于 R5。下一步验证用户新流程全文结果、核心贡献/条件/限制质量及安装反馈；预算自适应单批/多批尚未实现，不进入 P4/P5。旧 unified-v3 两条任务在本次快照已为 5/5、17/17，以下 6/17 等状态仅为历史。

更新：2026-11-02 19:03（Asia/Shanghai）。修复用户安装后的“引擎或数据库版本不匹配”：Rust 宿主仍要求0009，Python已为0010。宿主改为0010并验证数据库ready/FTS5，新增跨语言版本一致性和真实打包引擎的宿主握手/重启回归。旧CI只检查子进程401，存在误判；现安装检查必须匹配宿主握手记录与父子进程ID。9项Rust单测及另行运行的1项打包集成测试、clippy和PowerShell5.1的6项检查逻辑场景通过。修复包及后续结果见[验收补记](reading-implementation-verification-20261102.md#安装后版本不匹配修复)。未修改正式库或进入下一Phase。

以下保留此前实现及验收记录；上一轮CI成功不代表旧安装包的宿主版本握手已经通过。

更新：2026-11-02 17:30（Asia/Shanghai）。**R1–R4 已实现，R5 自动化及两篇真实论文局部链路通过，全文/安装体验仍未全部验收。** Alembic head 0010，新入口 paper-reading-v1；旧任务维持旧协议。未进入 P4/P5。实测范围、失败与操作步骤见[本轮验收](reading-implementation-verification-20261102.md)和[ADR 0009](adr/0009-reading-pipeline-implementation.md)。

- 先完成 306 文件既有成果安全提交并推送 `8d3ba1d`，远端 CI 41415123193 全部成功。
- 候选/单元/选择与原知识共用 Store；默认论文→核心结论→展开支撑，候选搜索、显示偏好、密度和阶段恢复接入。正常界面没有人工审核动作，旧记录/API兼容保留。
- 当前正式库275条知识在只读备份的迁移副本逐表保持；正式库没有用于升级试验。两篇真实局部输出21候选、2/3核心单元，明确 partial；已知71,260 Tokens，另一次超时未知。
- 下一步继续 R5 全文响应可靠性、贡献/条件/限制质量与安装反馈；不提前开发 Query/Wiki。安装器和私人验收材料仅本机保存。

以下为 R0 与前轮实际历史，不把历史状态当当前状态。

更新：2026-11-02 16:25（Asia/Shanghai）。**本轮完成 v3.3 阅读辅助知识图谱的 R0 设计与参考契约，尚未接入运行软件。** 工程仍在 P3/v3 自动建图质量迭代：M0–M5 核心已接入，M6 有未验收项；下一步 R1 存储/迁移适配，随后 R2–R5。运行 Schema 0009 / DTO unified-v3.1 / P02 3.2 不变，未进入 P4/P5。详见[设计导航](README.md)、[阶段计划](06_development_migration_plan.md)、[本轮规范验证](reading-design-verification-20261102.md)。

## 2026-11-02 阅读辅助知识图谱设计（R0）

- 产品定位为通用科研论文阅读辅助，统一称知识图谱，无特定研究方向前置。一键流程自动完成候选抽取、论文整合、核心选择和发布；按用户追加要求移除人工审核/待审队列/接受驳回步骤，历史审核数据仅作兼容保留。
- 重写 00–09 细则，明确原文/表格材料/定位/模型原输出保留，未选候选仍检索；默认 Paper→核心 Claim→支撑，多对多共享成员、导航线与科学关系分离。实验/方法/理论/综述使用共同结构，不强造实验。
- 重新设计 Pydantic/29 份生成 JSON Schema、目标 SQL、25 个合成示例；13 份参考 Prompt（新增 P12 整合、P13 选择）。保留源状态/有效性/角色/版本边界，未来 Query/Wiki 逐段依赖，非人工审核流程。
- 新 [ADR 0008](adr/0008-reading-knowledge-graph.md)、[代码兼容映射](migration/v3_to_reading_assessment.md)、[变化摘要](CHANGELOG_FROM_V3.md)，更新根 AGENTS/README、文档导航/下一轮模板/API 目标边界。原 v3 的 52 项规范资产归档至 archive/v3，历史报告原样保留。
- Conda 环境执行：本版参考测试 **78 passed**，归档 v3 **12 passed**、v2 **5 passed**；Ruff/format 与生成 Schema/示例/Prompt 对应、内存 SQLite 参考关系检查通过。这些不是应用回归或真实模型质量结果。
- 收尾核对：201 个非文档文件哈希保持；88 项当前/52 项归档资产、125 份 Markdown/420 本地链接与 QA/环境 JSON 通过；440 个候选文件敏感内容/Gitleaks 和 diff 检查通过，暂存区为空。
- 本轮未修改运行源码、运行 Prompt、API 生成文件、安装版或用户库，未调用真实模型、未执行迁移/安装/Computer Use。最后一次应用回归仍为前轮 153 Python passed/2 skipped、37 React，不能算本轮重跑。

## 下一开发内容

R1 先审计并备份旧数据，以 Alembic 实现候选质量元数据、结论单元/成员、选择快照/偏好和阶段检查点，统一 Store 验证/写入，建立旧 DTO/ID/审核历史映射并验证旧库可读。之后接新抽取、P12/P13 自动整合选择、分层交互与真实验收。详见 06 的 R1–R5 完成条件。

现有真实响应超时任务仍 **6/17**；另一 Schema 任务副本 4/4 成功是前轮结果。新版模型质量、完整超时论文、真实科学关系边、安装/干净机未验收；四份外部原文登记路径仍不可用。未 Commit/Push。

以下为原执行历史，不将其反向改写为新设计验收。

更新：2026-11-02 14:28（Asia/Shanghai）。本轮处理空占位字段导致的 Schema 失败和抽取响应超时；Schema 任务已在真实库副本上恢复 **4/4**，超时任务仍停在 **6/17**，未宣称彻底解决。Schema head 0009，无迁移，未进入下一 Phase、未 Commit/Push。详见[本轮验收](extraction-reliability-verification-20261102.md)和 [ADR 0007](adr/0007-extraction-null-markers-and-timeout-adaptation.md)。

## 2026-11-02 空占位字段与抽取可靠性

- 确认失败响应的 5 个 ClaimDetail 含 `findings_placeholder:null`。仅该准确路径和值允许确定性移除并记录审计，原响应完整保留；其他陌生/非空字段仍严格拒绝。旧失败结果可复用，继续走来源、证据和统一 Store。
- 新 P02 3.2 明确字段、完整证据和表格歧义约束，新计划以 8000 字符/64 证据为目标，候选数量按字数提示；旧 Prompt/签名/计划保持兼容，已提交批次不重调。响应超时仅二分未完成根批一次，子批再超时即停止；连接/限流等仍有界重试。
- 真实副本的 Schema 任务复用首批和原失败响应，仅为剩余两批发送请求，完成 4/4；原 156 条知识全列逐行不变，原模型响应保留、SQLite 完整性通过。未写正式库。
- 超时根批缩小后 4185 字符/34 证据仍等待响应头超时；两个新版 Prompt 变体同样超过 90 秒。短请求 1.907 秒成功，不能将其当作论文抽取通过。已知真实用量合计 35,809 Token，另三次超时用量/费用未知；停止继续试调用。
- `scripts/check-phase0.ps1`：153 Python passed/2 skipped、37 React，静态/契约/依赖/前端构建通过。最终小调整后针对性 44 passed；最终 PyInstaller/Tauri/NSIS、冻结 smoke、PowerShell 5.1 EnginePath 验证通过。图谱/Rust 本轮未改，未重复原生交互与 Rust 单测。
- 新包位于 `.local/releases/extraction-reliability-20261102/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,448,362 bytes；版本仍 0.0.1，未替换用户当前安装。用户安装后可继续 Schema 失败任务；超时任务仍需确认模型生成耗时/服务表现，不能建议反复盲目重试。未使用 Computer Use，安装执行待用户反馈。四份外部原文不可用限制保留。

以下保留前轮历史记录。

更新：2026-11-02 13:32（Asia/Shanghai）。本轮修复用户反馈的图谱闪动/拖动消失、第二篇 Schema 失败，并整理文献工作区。未进入下一 Phase，Schema 0009 不变。实际结果见[稳定性验收](stability-verification-20261102.md)和 [ADR 0006](adr/0006-graph-stability-and-local-reference-repair.md)。未 Commit/Push。

## 2026-11-02 图谱与文献工作区稳定性

- 真实 React Flow 浏览器测试复现节点更新丢失尺寸导致隐藏；显式稳定点尺寸、过滤无效坐标、修正 RAF 清理、边文字不截获指针。新增 headless Edge 真实组件回归，未使用 Computer Use。
- 实际失败响应为批内关系引用不存在的 local_ref，未发现混入另一篇论文。新增精确诊断和独立 P02_local_link_repair，一份错误响应最多一次端点修复记录，正文/证据/合法端点不可改写；保留原始模型结果、修复来源和已完成批次。旧任务签名实测兼容。
- 在真实库的隔离副本上调用真实模型 1 次，使用 1,725 Token，修复后通过 Schema、证据与 Store，保存 14 个领域节点；183 个原节点全列逐行不变。未对正式库写入，未重跑剩余全文。
- 文献与阅读分成导入论文、任务记录、项目文献三个可折叠板块；PDF/Zotero 同级，笔记来源独立，折叠保留选择并记忆展开状态。
- 最终 `scripts/check-phase0.ps1` 全部通过：139 Python passed/2 skipped、37 React；Ruff、mypy、依赖、契约、TS/eslint、格式、前端构建通过。`pnpm --dir apps/desktop test:browser` 2 passed；v3/v2 参考契约 12/5 passed。冻结引擎和 PowerShell 5.1 EnginePath 验证通过。
- 已构建并保存 `.local/releases/stability-20261102/ResearchGraph Studio_0.0.1_x64-setup.exe`，供用户安装反馈。版本仍 0.0.1；未替换当前运行软件，原生/安装执行与第二篇剩余全文验收待反馈。安全扫描通过，四份外部原文不可用限制保留。

以下保留前轮历史记录。

更新：2026-11-02（Asia/Shanghai）。当前完成 v3 核心增量后的抽取/图谱优化，未进入下一 Phase，Schema 0009 不变。真实库副本上的 4 次真实调用与恢复已通过；全文剩余批次、真实关系审核和安装器安装仍未验收。详见 [本轮优化验收](refinement-verification-20261102.md)及 [ADR 0005](adr/0005-model-capabilities-resume-force-graph.md)。未 Commit/Push。

## 2026-11-02 抽取截断与实时图谱优化

- 找到 Windows 应用文件虚拟化下的实际用户库：48 批旧任务冻结 8192，设置页后改 65536 不回写任务。移除手工上限，自动读取模型能力；未知时使用供应商默认，不猜别名。
- 相邻段落合并、新计划 48→16 / 11→4；旧任务保留原幂等计划和成功结果。失败批次有界拆分，签名校验、截断原文/失败用量留审计，任务长列表折叠。
- 点与低饱和半透明边、实时力导向拖动、邻居高亮、双击固定、独立聚焦。布局冷却保存与冲突重载，宿主布局请求容量与 2000 位置契约匹配。
- 正常界面移除旧抽取基线与 Mock。历史测试知识不删除，未经人工改动的 Mock 节点默认不混入图谱/阅读/比较候选；人工知识继续保留。
- 完整回归：131 Python passed/2 skipped、35 React、6 Rust；v3/v2 参考分别 12/5。静态、契约、冻结引擎及 PowerShell 5.1 EnginePath 验证通过。
- 真实副本恢复 4 次调用全部成功，405 原节点逐行不变、新增 55；保存进度 1→5/49（拆分后）。仅四次实际调用用量 41,374 Token，推理用量包含其中；费用未知，剩余 44 批未执行。正式库未写入实验结果。
- 原生复核、最终安装器与安全扫描结果见验收报告。四份外部补充原文登记路径仍不可用。

以下保留前轮历史进度。此前凭据阻塞本轮已通过定位正确数据库解决，不将旧报告静默改成通过。

更新：2026-11-02（Asia/Shanghai）。已按用户要求实施 v3 M0–M6 核心增量，继承 v2 P0–P3；Schema 0009。**代码与离线路径已实现，真实新流程受安全凭据不可读取阻塞，M6 不是全部验收通过**。详见 [v3 实际验收](v3-verification.md)、[迁移评估](migration/v2_to_v3_assessment.md)、[ADR 0004](adr/0004-v3-projection-and-unified-extraction.md)。未进入 P4/P5，未 Commit/Push。

## 2026-11-02 v3 核心开发

- 轻量 GraphProjection、五类可见节点、按需 Inspector、有界搜索/筛选/焦点图、候选边线型；布局与知识 revision 分离，拖动固定/重排/自动保存/重启恢复。
- 统一章节 P02 保留完整实验/条件/结果/指标，旧 P01/P02 显式对照；P04 只补译显示，保护原始英文/accepted 状态/模型历史。Zotero 默认引用，选择附件后可直接解析并排队抽取。
- 断点恢复覆盖 7 批第 2 批超时、429、JSON/证据/客户端失败；保留成功批次及已收到结果，重复任务不新增模型调用。
- 回归 123 Python passed/2 skipped、33 React、5 Rust；v3 参考 12、归档 v2 参考 5。详情修复后新增针对性 19 passed。静态/契约/前端构建、冻结引擎、PowerShell 5.1 EnginePath 验证通过；完整脚本前端格式阻塞已单独修复复验。
- 4 份隔离旧库迁移逐行保持原列，含 1508 节点 P3 副本；TEST 分类实读 5 篇/6 PDF，5 个登记来源哈希一致。
- 原生复核修复缓存键冲突白屏、拖动状态与起始阈值；节点拖动/固定、布局与缩放重启保存、侧栏折叠、无终端启动与 Sidecar 随窗退出通过；Zotero 打开成功。工具曾误开正式旧安装版，引发既有 0005→0008 自动升级，旧列逐行审计一致；后续用独立 v3 标识，未覆盖/回滚用户库。
- Windows 安全凭据不可读取，已请求用户重新录入；本轮真实模型、真实七批恢复、真实关系审核及干净机安装未宣称通过。安装包/最终原生结果见验收报告。


## 2026-11-02 文档目录调整

- 按用户追加要求将 v3 的 10 份设计章节直接放到 `docs/`；Schema、Prompt、示例和测试分别位于 `docs/schemas/`、`docs/prompts/`、`docs/examples/`、`docs/tests/`。旧独立规范包目录已移出 docs。
- 搬移 53 份文件，原包 README 的核心决议、所有权、环境及参考资料合并到文档导航；同步全部当前路径引用，按新布局重建 52 项 SHA-256 与文件清单。旧 v2 仍在 `docs/archive/v2/`。
- 新路径实测：`python -m pytest docs/tests -q` 为 12 passed，归档 v2 为 5 passed；52 项哈希、16 份生成 Schema、一致性和文档链接检查通过。26 份 Schema/SQL/示例/测试文件与搬移前字节一致，运行代码和 QA 原件不变。
- 候选内容/路径及 Gitleaks 扫描 305 文件通过，`git diff --check` 通过；未执行应用回归、真实模型、安装或数据库迁移，未 Commit/Push。原始输入、已合并 README 和生成缓存留在 `.local/docs-flatten-20261102/` 忽略备份。

## 2026-11-02 首轮文档整理（DEV-0023）

- 重建 [docs 导航](README.md)，将 29 个旧 v2 设计、Prompt、Schema、示例和测试文件整体归档至 `archive/v2/`；从当前入口移除重复设计，保留历史内容与包内结构。
- 合并 v3 适用规则到根 AGENTS；更新 README、运行说明和历史标记，新增[文档整理映射](migration/v3-documentation-map.md)与 [ADR 0003](adr/0003-v3-documentation-baseline.md)。记录 Prompt 新旧编号、参考契约差异及版本边界。
- 参考契约实跑：v3 **12 passed**、归档 v2 **5 passed**；v3 清单 52 项 SHA-256 与 16 份 Pydantic/JSON Schema 一致。Markdown 本地链接、QA 原件哈希与环境 JSON 检查通过，四份不可用外部原文单独记录。
- 首轮归档时，运行代码、既有未提交实现、运行 Prompt、生成 API 和 v3 原包保持不变；随后目录调整见上节。候选内容/路径及 Gitleaks 扫描 306 文件通过，`git diff --check` 通过。
- 文档整理不执行应用回归、真实 LLM、数据库迁移或安装验收；下方软件结果均来自 2026-11-01，不能当作 v3 新功能验证。

## 2026-11-01 启动与抽取恢复增量

- 抽取恢复现在以 `KnowledgeOperation` 的成功记录作为持久化进度：任务失败后只调用未完成批次，已提交批次的节点计数会在重试结束时恢复；相同任务、输入、模型和参数下已收到且可校验的 P01 大纲也会复用，避免重复请求。批次上限为 10000 原文字符，文档 API 已同步。
- 针对 7 批次中途失败场景新增离线回归：首批知识保留，恢复后完成计数与幂等操作节点数一致，首批和 P01 不重复调用。该测试使用独立自造 PDF，不代表真实 Zotero/模型验收。
- DEV-0020/0021 当时未复测原生窗口或真实七批次失败恢复，且 shell 未发现 Cargo。随后 DEV-0022 使用本机 Rust 工具链完成安装器构建；构建成功不替代安装或真实模型验收。
- 本轮将正式 Sidecar 的 Windows 子进程创建保持为 `CREATE_NO_WINDOW`，并将 debug Tauri 入口也设置为 Windows GUI 子系统；后端 stderr 继续写入 `engine-startup.log`，开发调试仍可查看日志。
- Provider 生产请求改用可取消的异步 `httpx` 流式响应，限制响应体 2 MiB，区分超时/网络/429/5xx/客户端/重定向/输出截断；保留旧 `_request` 兼容入口供现有测试与集成使用。Zotero 批量导入成功项现在直接提供“解析并抽取知识”入口，仍需用户显式授权后发送解析片段。
- 首页空状态口号、项目卡片占位宣传语、页脚宣传内容和来源重复说明已删除；论文入口改为知识概览/证据/抽取状态导向。双语字段继续保留英文权威值，图谱与阅读卡片优先显示已有 `*_zh` 辅助字段。

## 现有 v2 P3 实现（2026-11-01）

- 全局“设置与诊断”统一管理 OpenAI、兼容 API、本地模型和 Mock，以及 Extraction/Reasoning 默认角色。用户原配置和凭据引用经 0007 迁移保留；API Key 存 Windows Credential Manager，数据库与 API 响应不含明文。
- Zotero Local API 只读 Collection 选择、搜索分页、论文/PDF 勾选、全选本页、批量导入、进度、失败重试、来源关联和 SHA-256 去重。TEST 实际读到 5 篇论文、6 个 PDF；导入其中三篇，未修改原文或 Zotero 数据。
- P2 真实模型使用批次短证据 ID，并在 ModelRun 冻结映射；严禁猜测补全错误 UUID。P01 输入有界，P02 仍覆盖所有证据，成功批次与进度持久化。
- P03 实体对齐候选；FTS5/BM25 候选召回；P04 当前条件对照；P05 关系推理。0008 加性迁移新增推理、关系、对齐、审核及 FTS5 索引，回填旧知识。统一 KnowledgeStore 处理证据/Schema 验证、幂等、事务、事件、图 revision 和审核；NO_DECISION 不建科学关系边。
- React Flow 图谱支持节点/边交互、有界分页、焦点范围、关系审核筛选；Comparator 展示双方条件、证据/PDF 高亮、模型结果与审核历史。来源或条件变更后候选 stale，禁止接受；P03 不物理合并实体。
- 导航折叠为图标并提供提示，换页及重启保留；画布尺寸变化后自动 fit。原生发现并修复展开侧栏后右侧节点裁切，以及已接受关系筛选误隐藏未审核端点的问题。

架构依据：[迁移评估](migration/v1_to_v2_assessment.md)、[统一引擎 ADR](adr/0001-unified-knowledge-engine.md)、[P3 ADR](adr/0002-phase3-models-and-reasoning.md)、[运行 API](api.md)。详细实际验收见[Phase 3 本机验收记录](phase3-verification.md)。

## 既有软件验证结果（2026-11-01）

| 检查 | 结果 |
| --- | --- |
| Conda 全回归、静态检查、契约生成、前端构建 | 104 Python passed、2 skipped；完整脚本时 27 React passed |
| 图谱尺寸修复后 TS/ESLint、React、原生重建 | 28 React passed，构建通过 |
| Rust fmt/clippy/test | 4 passed |
| v2 设计参考契约 | 5 passed；本轮归档后另行复跑通过 |
| 冻结 Sidecar smoke | P1/P2、全局角色、P03–P05、图谱/审核/重启/stale 通过，使用 Mock |
| Windows PowerShell 5.1 引擎验收 | 通过；不是本轮安装器或干净机验收 |
| 真实全文抽取 | 三篇分别完成 3/3、11/11、11/11 批，顶层输出计数 116、321、484 |
| 真实来源完整性 | 1683 个 EvidenceSpan 的页/版本/quote/offset/hash 均有效；4 份原 PDF hash 未变；SQLite/外键检查通过 |
| 真实 P03 | same_as 对齐候选；原生双侧 PDF 高亮、驳回及审核历史通过。验收代操作，不代表用户科学确认 |
| 真实 P04/P05 | 三组 Claim、四次成功尝试均 NO_DECISION；一次额外字段导致严格 Schema 拒绝后重试成功。真实科学关系审核闭环未通过 |
| DEV-0021 回归 | 104 Python passed、2 skipped；28 React passed；前端 TypeScript/Vite 构建通过；Provider Ruff check/format 通过；敏感扫描 248 文件通过 |
| 独立自造 Mock 原生项目 | RELATED 候选→接受→绿色关系边→筛选→退出重启读回通过；原始模型输出、事件保留 |
| 导航与原生布局 | 折叠/展开不裁切；跨页和重启保持折叠；任务历史 10→15 项 |

两项 Python skip 是 Windows 文件 symlink 权限，junction 验证仍通过。实测兼容模型由用户在设置页录入，密钥未通过聊天传递。计数不是科学正确率；1683 个证据是三篇真实论文的结果，不含随后建立的两个自造 Mock PDF。不同配置的历史输出仍保留，数据库节点总量不能当作本次新增量。

## 安装器状态

本轮 `pnpm --dir apps/desktop tauri build` 正式 NSIS 构建成功，保存在 `.local/releases/v3-m0-m6-20261102/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,441,992 bytes；SHA-256 `A4A9B710DBDEF02508134302653227056775042C33737C8435002978B6ED3253`。仍为开发版本 0.0.1，包含 Schema 0009；安装器未安装或卸载验收。此目录及构建日志均被 Git 忽略。

此前 DEV-0022 的安装器仍是历史构建结果；本轮没有卸载或覆盖正式用户安装。

## 数据、安全与历史

- 未重做 P0–P2；原 Paper/附件版本/证据/历史仍可读。迁移前自动 SQLite 备份，0007 保留旧模型引用，0008 回填旧节点。未删除用户数据库、附件、知识或笔记。
- DEV-0018 如实记录了自动化工具误开正式安装版，使正式库 0001→0005；升级前备份存在，旧四表旧列逐行一致。该轮后续使用独立验收目录。
- `.gitignore` 加强；提交前扫描实际候选/暂存内容，审查私人材料和真实凭据。敏感日志、数据库、论文、验收脚本与安装产物留在本机忽略目录，详见[安全检查](security-checks.md)。本轮不 Push，不将上一轮 CI 冒充本轮结果。
- P2 历史代码提交 `e67854d` 的[CI 41271020398](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41271020398)与安装验收继续保留；旧计划两份文件的用户删除保持，历史链接使用 Git permalink。
- S1–S4 四份外部补充原文登记路径均不可用，无法复核原文/哈希；QA 原件和历史登记保留。G0 用户放行不等于干净机实测。

## 剩余问题与下一步

1. P3 仍需一组有明确双方证据且条件可比的真实关系，完成用户领域审核和原生图谱验收。当前三组 NO_DECISION 应保留，不能调低验证门槛或用 Mock 代替。
2. 只实测一个兼容供应商；OpenAI 直连、其他兼容服务、本地真实模型、私人 Zotero 批注和复杂图表/公式抽取未实测。来源校验不判断模型科学含义。
3. 原文为 identity-v1 字符映射和块级高亮，不包含 OCR、精确逐字框、跨页单一 span。P3 仅 FTS5 召回、对齐判断和读取时失效检测，没有向量召回、物理实体合并或完整后台依赖重算。
4. 已构建安装器但未安装验收，未 Push 或运行新远端 CI；干净 Windows、缺失 WebView2、其他平台仍待验收。保留 Starlette/httpx、PyInstaller tzdata 与约 512 KB 前端 chunk 提示。

v3 M0–M6 核心实施已见顶部条目。下一步先恢复安全凭据、使用真实模型补齐统一抽取及恢复验收，再在独立 Windows 账户/虚拟机验证安装。P4 Query、P5 Lint/Wiki 未开始。
