# ResearchGraph Lite 进度

更新：2026-11-20（Asia/Shanghai）。

## 2026-11-20 · 研究内容知识库K1–K3实施与验证（交付收尾中）

用户明确授权按方案完成前三阶段、闭环与回归并上传GitHub，覆盖上一条仅方案状态。已新增研究项目与任务记录之间的独立知识库，三视图为知识地图/论文知识/联系汇报；旧概览可零模型收藏，新paper-knowledge-1从本地或模型解析材料生成卡片与五类有引文知识，程序题名根与版本身份、逐项exact quote/occurrence终验。新lite0016–lite0018加性持久库/建模/关联及原子解析事件；可靠来源身份、多项目链接、专题/备注/归档/独立布局/导出与永久删除前备份、脱离应用论文保留快照已接。新模型用途knowledge_extract/knowledge_connect；默认自动策略关闭，明确范围/预算授权后，仅后续成功解析/新知识事件可自动建模及联系，旧无授权成果不回溯收费。累计预算同时包含建模/关联发送及预留/删除消费墓碑。

K3按保存知识双语词面召回冻结候选，从双侧科学节点/引文发布联系和带关系引用的结构化汇报；无候选零请求，部分批次保留partial与检查点，重启不重复已发槽。报告保存已读/置顶/个人备注、比较范围与旧版本标记；地图与报告双向定位及原文摘录/真实论文返回，浏览零模型。版本对可跨配置复用，只有显式重新分析才绕过复用且受预算限制。当前K2完整材料容量不足整体拒绝，未自动拆长文；来源合法不等于科学正确。

本分项实际：K1/K2/K3/usage后端专项**79 passed**（20.15秒），K1+app+自动授权事件专项**21 passed**；source匿名HTTP闭环2自动K2+1自动K3、首篇no_candidates/双侧引文/GET和重启0重发，usage为合成192 Token。知识库React/API **15 passed**、实际Edge新库 **3 passed**，最终前端TypeScript/ESLint通过；较早兼容子集64通过单列、不作最终全量。最终完整检查已通过：引擎819 passed/1权限跳过、React194/19文件、Edge37；mypy109、Ruff/格式/契约/依赖/前端生产构建及Rust fmt/clippy通过，Host16项和最终打包引擎连接/重启1项通过。暂存198文件私人路径/Gitleaks通过；新安装包160752786 bytes/SHA `b5c20fa89d4d9e075d08424cec8cd5e471737416ac2bf082fd85a19f4054f7ce`已完成PowerShell5.1隔离安装及安装版知识库闭环，Host17/0ignored通过，334资源逐项匹配；Git提交/PR/CI交付收尾中，见[本轮验证](knowledge-library-verification-20261120.md)、[ADR0060](adr/0060-durable-research-knowledge-library.md)和[实施方案](research-knowledge-base-plan-20261120.md)。真实模型0、正式用户库实验0，用户原生与科学验收另计；K4未启动。

## 2026-11-20 · 研究内容知识库方案（未实施）

按用户提出的长期维护方向完成当前源码只读评估及[实施讨论稿](research-knowledge-base-plan-20261120.md)：建议在研究项目和任务记录之间增加独立工作空间，以论文题名根组织问题/概念/方法/贡献/结果，新知识版本完成后在已设置范围/预算内增量发现跨论文联系并保存汇报。现有五类LightGraph、画布、任务/用量可复用；当前图无逐节点原文引用、节点ID按名称生成、论文删除会删概览，需先补独立快照/真实来源/版本与删除生命周期。推荐K1收藏与库基础、K2带来源知识、K3联系/报告形成首版闭环，再做K4规模及概念聚合。该稿为建议，不表示已增加入口/表/迁移/自动收费任务；当前head仍lite0015。无运行代码改动、正式库访问、真实模型请求或Commit/Push。

## 2026-11-20 · 根据反馈改为右侧直接分析与章末状态

用户指出重复原文卡无必要、分析被推到下方、章首阅读状态不便读完操作。本轮移除英文摘录卡，右侧直接显示一份实际整段分析，仅保留紧凑类型/编号定位；正文起点对齐、实际宽度至少560px保留双栏，更窄才按段堆叠。两种解析稿的阅读状态统一移到大章全部小节与可归属材料之后，原ID和目录续读/保存路径保持。正文尾追加图/公式按真实章节分组；旧共享section无法唯一消歧的材料独立可见，不误归最后章。已有合法笔记无需重生成，无迁移或模型请求。

最终TypeScript/ESLint、Prettier通过，React **179 passed/17文件（17.67秒）**，Edge **34 passed（28.7秒）**，Gitleaks与私人路径 **434文件通过**。末次全量在尾追加材料归属加固后执行；初次夹具断言和review发现保留记录，不沿用旧后端/Host成绩。实施见[ADR0059](adr/0059-reading-analysis-and-chapter-end-progress.md)及[本轮验证](reading-sidebar-footer-verification-20261120.md)。

新未签名安装器：[ResearchGraph-Studio-Reading-Sidebar-Footer-0.0.1-x64-setup.exe](../.local/releases/reading-sidebar-footer-20261120/ResearchGraph-Studio-Reading-Sidebar-Footer-0.0.1-x64-setup.exe)，**160,584,055 bytes**，SHA-256 `9f5833771a7f154eb109c0b31c2fb5e5a3b267481ccdcb4c3bf4c0ca79d2140e`。PowerShell5.1新隔离安装/sidecar烟测通过，schema lite0015、3段模型材料/进度、匿名本地PDF清理重建/删除与源文件保留，模型0。142项运行源/配置构建前后稳定，安装EXE及328内部资源与打包源逐项匹配，sidecar复用前次相同版本。正式库/私人PDF/凭据未读取，无真实模型、Commit/Push或日常目录安装；用户原生阅读体验待反馈。

## 2026-11-20 · 精读标记逐项对应与贴近布局

本地与模型精读共用组件增加每条高亮的段号.标记号、类型及精确原文摘录卡，原文/卡片双向定位、Enter/Space可操作。相邻同色、重叠标记及重复原文保留独立身份，原文DOM文字不增加编号内容。卡片按段内高亮首行相对位置显示，密集时顺延避让；整段说明明确标为“第N段·整段批注”，不伪造成逐片段独有解读。已有合法结果重新读取即可，不需要重新生成或模型调用。实际阅读宽度不足760px时段内单栏，字号、来源信息展开和窗口尺寸变化后重新排布；五色样式直接由共享组件加载。

最终TypeScript/ESLint、Prettier通过，React **177 passed/17文件（15.65秒）**，Edge **32 passed（22.7秒）**；首轮12px定位偏差及独立复核的尺寸观察/列标题问题已修正并补验，失败记录保留。私人路径规则与Gitleaks **431文件通过**、diff检查通过。仅前端变更，无迁移，head仍`lite0015`，本轮不重跑或借用历史后端全量/Host成绩。见[ADR0058](adr/0058-anchored-reading-annotations.md)及[本轮验证](reading-annotations-verification-20261120.md)。

新未签名安装器：[ResearchGraph-Studio-Reading-Annotations-0.0.1-x64-setup.exe](../.local/releases/reading-annotations-20261120/ResearchGraph-Studio-Reading-Annotations-0.0.1-x64-setup.exe)，**160,575,183 bytes**，SHA-256 `1d69670fb373705ac86ac4f9993a7f978530713505258927e421fd41b5d25720`。PowerShell5.1隔离安装和sidecar烟测通过，匿名PDF、3段模型材料/章节状态、清理/重建、删除/源文件保留、模型调用0；复用前次相同sidecar，安装EXE及328资源与打包源一致。141项运行源/配置在构建前后稳定。正式库/私人论文/凭据未读取，真实模型0，未Commit/Push或覆盖日常安装。密集标记会增加段落高度，用户原生GUI/真实阅读体验仍待反馈。

## 2026-11-19 · 精读标记显式本地部分恢复

续接用户指出“译文正常但精读标记失败”。对单条失败输出只读检查发现150条标记中11条写成不支持的`CLAIM`；映射到`THESIS`后另有2条引文与对应段落不匹配。两种任务彼此独立，翻译成功不证明精读合同通过；失败raw没有在报告输出。

新精读合同v4沿用v3固定slot和schema，只强化prompt中的规范类型枚举、THESIS含义和禁止CLAIM。旧任务及译文不变。用户明确点击后，后端严格重验raw与当前解析：只允许精确CLAIM→THESIS和隔离来源不匹配高亮；其它类型、字段、slot/段落覆盖或错误来源一律拒绝。结果以`partial`供精读使用，独立成功翻译继续单独显示。lite0015新增本地恢复表，保留原失败行、raw、错误及账本；GET重新由raw重算并核验来源版本。流程无Provider调用，不收费。正式库实验写入0、真实模型/HTTP调用0、未Commit/Push或覆盖日常安装。

全量引擎**728 passed /1 skipped /1 warning（220.68秒）**；读取回算加固后定向**84 passed /1 warning**。React **173 passed/16文件**，Playwright **25 passed**，Rust Host **15 passed/1 ignored**，另在已安装sidecar上运行被默认忽略的Host启动/重启集成测试并通过。Ruff、核心模块mypy、TypeScript/ESLint和Prettier通过。

新未签名安装器：[ResearchGraph-Studio-Reading-Recovery-0.0.1-x64-setup.exe](../.local/releases/reading-local-recovery-20261119/ResearchGraph-Studio-Reading-Recovery-0.0.1-x64-setup.exe)，**160,603,654 bytes**，SHA-256 `0caf84b9cb2317fd84d9e099aca929f494ece772bc1f55831f43efd8b600986d`。PowerShell 5.1隔离安装及产品sidecar smoke通过，schema为lite0015、模型调用0、源PDF保留；Host实际连接并重启已安装sidecar通过。验证材料在`.local/verify/reading-local-recovery-20261119/`。真实论文模型质量及用户日常目录安装/原生GUI仍由用户验收；正式库实验写入0、真实模型/外部HTTP请求0，未Commit/Push。详见[ADR0057](adr/0057-reading-output-and-workspace-recovery.md)及[补充验证](workspace-fixes-verification-20261119.md)。

## 2026-11-19 · 精读失败分类、论文回答读取与工作区四项修复

本轮继续中断现场，已完成代码、全量回归及新安装包。旧精读两次失败没有可校验正文，旧提示误归格式/来源错误；历史传输类型不能还原。新增安全分类区分超时、空响应、断流、截断、契约、来源和存储问题，有效raw及预算齐备才提供一次格式修复。新后处理合同v3用完整编号槽位减少重复输出，程序绑定段落ID/章节/原文后严格核对引文与来源，旧v1/v2和raw保持；长篇新精读/译文读取所选模型文档时限，仍不保证全文容量或语义准确。共享Provider补齐兼容空用量、未知结束状态、工具调用、空正文及失败回执处理，未自动重发。

WorldGraph仅只读诊断32页/65章/633块：全章节正文6.911秒、仅目录0.185秒，不能证明历史请求确实超时。论文回答改只读目录、单章原文按需加载，Host分开提示超时与断连。本地/模型来源均为“论文概览、论文精读、论文回答”；模型章节材料保留在精读内。圆形“论文解析操作”始终显示并展开四项操作，缺少来源显示禁用原因，切换不调用模型。模型稿的问答继续要求本地索引，不伪用证据身份。见[ADR0057](adr/0057-reading-output-and-workspace-recovery.md)和[验证报告](workspace-fixes-verification-20261119.md)。

最终引擎 **710 passed /1 skipped /1 warning（123.46秒）**，React **170 passed /16文件**，Edge **25 passed**，Rust Host **16 passed /0 ignored**。Ruff/151文件格式、mypy91、TypeScript/ESLint/Prettier和依赖检查通过。首轮Edge24通过/1失败因旧夹具和原文区断言未适配，修正后专项和全量通过，旧失败记录保留。源码/安装版各9个loopback综合请求、一次后处理/一次批次格式修复、历史保留及两次重启零重发通过；安装版32页匿名论文33章目录0.046549秒/按需1章、模型0。168项运行源/配置稳定，sidecar及326资源逐文件配对。

最终未签名安装器：[ResearchGraph-Studio-Workspace-Fixes-0.0.1-x64-setup.exe](../.local/releases/workspace-fixes-20261119/ResearchGraph-Studio-Workspace-Fixes-0.0.1-x64-setup.exe)，**160,575,660 bytes**，17:14:04构建，Windows PowerShell5.1隔离安装及实际安装引擎验证通过。当前head仍`lite0014`，正式库实验写入0，真实模型/外部HTTP请求0，未Commit/Push或替用户安装日常目录。真实Provider、长篇/科学/译文质量及用户原生GUI/干净机仍待验收；安装不自动重发旧失败精读。

## 2026-11-19 · 统一本地与模型论文概览/全文精读

正式库只读元数据确认最近成功模型解析保存74正文段、8个带LaTeX公式、1结构化表格、3图/3图注，数据库检查正常；旧概览仅通用摘要，冻结计划为overview=true/reading=false/translation=none。前端概览默认选中造成用户未额外选择也可能生成，已改概览/精读都默认不选，页面显示实际冻结选择。

两种来源仍分表保留真实身份，现共用PaperOverview的PaperCard+LightGraph及ReadingContent双栏精读、译文占位、五类论证高亮/批注和安全KaTeX。模型公式预览明确待核对；表格安全预览且保留原始材料。新精读/译文合同完整绑定segment ID、章节/原文/引文occurrence，旧摘要不伪造成图谱或批注。用户可在原材料上显式补生成概览、精读或仅译文，无需再次上传PDF；生成失败保留上次有效稿，编辑材料使旧输出stale。

新增报错后显式一次文本格式修复：批次失败raw本机私有保存、校验无损、只修失败响应；概览/精读/译文保留失败raw并可明确确认一次修复，不能递归链式收费。请求/来源/数据库错误不冒充格式问题，发送前后记持久账本，取消/重启保留已发槽。lite0014加性新增失败响应表及模型图谱布局表，升级前备份；旧PDF会话只读补真实论文关联，不改冻结计划。详情见[ADR0056](adr/0056-unified-reading-from-parser-sources.md)及[验证报告](unified-reading-verification-20261119.md)。

最终固定源码引擎 **664 passed /1 skipped /1 warning（215.12秒）**、React **167 passed /16 files**、Edge真实组件 **21 passed**，Ruff/mypy91与418文件安全扫描通过。首轮引擎4失败暴露JSON回执未持久化问题，已修并通过定向及最终全量。源码与安装版HTTP综合smoke均覆盖9个loopback请求、一次后处理/一次批次修复、仅发布恢复及两次重启0重发。Windows PowerShell5.1隔离安装通过，Host **15 passed /0 ignored（4.81秒）**；**168项**运行源/配置稳定，sidecar与**326项**资源逐文件配对。正式库只读诊断、实验写入0，真实模型/外部HTTP请求0；未Commit/Push或替用户安装日常目录。

最终未签名安装包：[ResearchGraph-Studio-Unified-Reading-0.0.1-x64-setup.exe](../.local/releases/unified-reading-20261119/ResearchGraph-Studio-Unified-Reading-0.0.1-x64-setup.exe)，**160,566,627 bytes**，2026-11-19 11:17:16构建。安装后原论文可显式生成新版概览与全文精读，或在已有新版笔记上仅补中文译文，无需重传PDF；旧摘要不会自动升级，生成及一次修复可能产生模型费用。真实供应商兼容、论文科学质量、复杂公式表格与翻译准确性、用户原生GUI及干净机仍待实际验收，安装不会自动消耗该验收预算。

## 2026-11-19 · 已定位并修复章节发布外键写入顺序

用户再次仅发布失败后，读取正式库安全诊断确认 `SQLITE_CONSTRAINT_FOREIGNKEY (787)`、累计发布恢复2次；正文3/3、边界2/2检查点均通过，数据库 `quick_check=ok`、现存外键违规0。隔离启用生产外键检查后稳定复现：新概览 Job 尚未 INSERT，计划项就先 UPDATE 引用其 ID，导致发布事务回滚。现在先 flush 新 Job 再关联计划项，仍在同一事务中；之前批次测试没有启用外键，是漏检原因，已改用生产 `make_engine`。

对于旧版本已耗尽2次恢复、明确787外键失败且检查点完整的任务，增加一次修复版显式仅发布恢复，累计数保留并追加为3，写入版本和仅发布意图；失败/取消/中断后不再追加。授权后检查点改变直接停止，不能回落模型初始化或普通批次请求。论文页和任务记录均显示“仅重新发布章节（不重发批次）”，后续所选概览/精读可能另行调用模型。

实际源码验证：引擎 **586 passed / 1 skipped / 1 warning（147.95秒）**；专项 **50 passed（16.06秒，包含在全量内）**；桌面 **15 files / 155 passed**；Ruff、mypy86、TypeScript/ESLint通过。开发模式两条HTTP恢复入口通过，5个检查点/请求账本不变、1成功parse/1概览Job、GET只读、同幂等重放及重启不追加请求。安装版验证及本轮包记录见 [验证报告](document-fk-order-verification-20261119.md)，决策见 [ADR0055](adr/0055-document-postprocess-foreign-key-order.md)。正式库仅只读诊断，未替用户重试；本轮真实模型/外部HTTP请求与正式库实验写入0，未Commit/Push。下方旧“约束未知”是新增诊断前的历史结论，本条已由新记录定位为外键写入顺序问题。

最终安装包：[ResearchGraph-Studio-Publication-FK-Fix-0.0.1-x64-setup.exe](../.local/releases/document-fk-order-20261119/ResearchGraph-Studio-Publication-FK-Fix-0.0.1-x64-setup.exe)，**160,518,000 bytes**，2026-11-19 09:49:08构建。PowerShell5.1隔离安装烟测、安装版两条仅发布恢复入口及各自重启通过，新增模型请求0；Host **14 passed /0 ignored**。161项运行源/配置稳定，sidecar与324资源逐项配对一致。安装版覆盖与开发模式相同的5检查点/账本保留、旧count2兼容、无效Provider快照绕过和单次概览排队；概览在测试中禁网未生成，不冒称真实模型质量验收。用户可安装后打开原任务，点击“仅重新发布章节（不重发批次）”；无需重新导入或重新模型解析。

## 2026-11-18 · 模型章节发布 IntegrityError 恢复

用户最新模型论文任务的3/3正文批次和2/2边界检查点均已通过，失败发生在最终解析发布事务；早期任务只记录异常类型，无法反推出具体数据库约束。新增脱敏 SQLite 错误码/名称/约束类别记录，以及严格的“仅重新发布章节”恢复：仅在所有冻结检查点完整、源文件 stat 版本匹配且没有成功解析时开放，跳过 Provider 初始化和 PDF 上传，原模型批次不重发；每个任务最多2次显式发布恢复。所选概览/精读仍会作为独立任务继续，可能产生模型请求。见 [ADR0054](adr/0054-document-publication-integrity-recovery.md) 和[验证报告](document-integrity-verification-20261118.md)。

完整后端 **579 passed / 1 skipped / 1 warning（109.30秒）**；分批/导入重试专项 **34 passed**；桌面 **148 passed（14.51秒）**；Ruff、86文件 mypy、TypeScript/ESLint通过。Windows安装包已在PowerShell 5.1隔离安装并完成既有导入/模型文档/阅读状态/清理 smoke，模型调用为0；输出为 `lite0013`。包为 [Integrity Recovery](../.local/releases/document-integrity-recovery-20261118/ResearchGraph-Studio-Integrity-Recovery-0.0.1-x64-setup.exe)，**160,496,071 bytes**。新恢复事务由合成数据库唯一约束失败的引擎集成测试覆盖；未对用户失败任务重试，没有真实模型或外部HTTP请求、正式库写入、Commit/Push或替用户日常安装。旧任务因原版本诊断信息不足，具体 SQLite 约束仍未知。安装后可从原任务点击“仅重新发布章节（不重发批次）”；若 PDF 的 stat 版本已变化，任务会安全拒绝恢复。用户原选概览会随后独立执行。

## 2026-11-18 · 边界HTTP400与原任务恢复修复

只读任务元数据确认：新论文正文3批均已校验/HTTP200，失败发生于原第5–6页第一个边界复核，已尝试3次，最近约1.218秒返回400。边界提示遗漏JSON字样但启用json_object，兼容服务可复现拒绝；旧版未保留400服务正文，所以不声称看到供应商确切错误参数。已补明确JSON输出要求，并提供一次受控兼容恢复：安装新包后原任务明确确认，只续未完成边界，保留正文、页码、原3次账本和冻结模型，不必重新导入。修复请求发送前持久标记，崩溃或再次400也不能重复享受例外；发送前取消不耗该槽。全局/项目/详情只读显示恢复资格，UI分开正文与边界进度。见 [ADR0053](adr/0053-boundary-json-compatibility-recovery.md) 和 [验证](document-http400-verification-20261118.md)。

最终完整后端 **576 passed /1 skipped /1 warning（139.99秒）**，React **147 passed（16.72秒）**、Edge **19 passed（18.9秒）**，静态与契约检查通过。新包PowerShell5.1隔离安装、安装版4个旧边界恢复案例和普通两种分页路线通过：只发1次边界、extract零重发，修复仍400后两个retry入口409/零POST，重启零POST；Host **14 passed（3.68秒）**。**161项**源/配置保持一致，sidecar及**324项**资源配对。新包 [Boundary HTTP400 Fix](../.local/releases/document-boundary-http400-20261118/ResearchGraph-Studio-Boundary-HTTP400-Fix-0.0.1-x64-setup.exe)，**160,516,874 bytes**，21:46:26构建。

本轮正式库仅只读非敏感任务/参数元数据，未读正文、模型材料或凭据；没有修改用户正式任务/配置，没有真实模型或外部HTTP请求，没有Commit/Push或替用户日常安装。用户此前请求和费用保留事实；修复后真实服务兼容与论文科学质量仍待用户显式继续验证。

## 2026-11-18 · 可续接分页解析与一次格式修复

按用户7点方案完成新模型PDF分批流程：新任务默认每批最多5页（可选2–8、包含前1页共享），按实际模型/图片容量缩批并顺序执行；核心页以材料或明确缺页警告覆盖。新 document-batch-1 / document-boundary-1 与 lite0013 加性迁移保存成功检查点、冻结源元数据/快照/范围和请求账本，解析不以SHA-256为前置。失败只续未成功批次，已发未定请求须显式继续，可能再次收费。旧无分批计划的失败任务不会由“重试”自动升级，需在论文页“使用模型重新解析”创建新任务。

每批格式修复默认关闭、独立授权且最多一次，只发送失败响应文本/Schema/安全错误，不重传PDF；修后仍核对文字、公式、表格、页码和顺序，无法证明只改格式则拒绝。相邻批仅在末首续接标记要求时额外复核两页，模型只作决定，程序确定性合并；复杂表格/不确定关系保留片段和质量状态。界面显示批次、原始页、校验/边界进度、实际请求与预算，字段错误不回显正文。详见 [ADR0052](adr/0052-resumable-document-batches.md) 和 [本轮验证](document-batches-verification-20261118.md)。

最后质量状态修正后完整后端 **562 passed / 1 skipped / 1 warning（105.55秒）**，React **15 files / 133 passed（13.93秒）**，Edge **19 passed（13.1秒）**；Ruff、mypy85、TypeScript/ESLint及契约导出通过。Windows构建、PowerShell5.1隔离安装及安装版图片/PDF两条本机HTTP链路通过：匿名7页3批、5次模拟POST含一次纯文本修复及一次边界复核、重启零追加请求。Host **14 passed / 0 ignored（2.82秒）**；**160项**运行源/配置构建前后不变，sidecar与**324项**资源逐文件配对。

本轮未签名安装包：[Document Batches](../.local/releases/document-batches-20261118/ResearchGraph-Studio-Document-Batches-0.0.1-x64-setup.exe)，**160,485,540 bytes**，构建于20:28:56。真实模型/外部HTTP请求及正式库实验均为0，未读取私人论文或凭据，未Commit/Push，未替用户安装日常目录。真实供应商兼容、公式表格/跨页科学质量、用户原生GUI及干净机仍待验收；页码声明完整与结构校验不等于科学正确，600/1800秒为单次请求时限，不承诺整篇更快或更便宜。

## 2026-11-18 · 文档超时修复与页面图片传输

按用户继续解决故障的要求，新增文档独立等待/总时限600/1800秒及设置控件，旧任务快照不重写；增加显式PDF页面图片传输，仅本地144dpi渲染，不本地提取正文/公式/表格，由视觉模型识别。超时区分连接/上传/等待/接收/总时限，任务与论文页显示真实阶段/用时/页面准备数，安全诊断落Job.result白名单。火山/腾讯精确套餐地址提供显式推荐配置按钮，不自动改用户正式配置。

最终后端 **477 passed / 1 skipped / 1 warning（152.60秒）**、React **118 passed（17.33秒）**、Edge **17 passed（20.8秒）**，Ruff/mypy80/TypeScript/ESLint及契约通过。开发进程烟测发现并修复新阶段DTO遗漏，5项公开API阶段回归补齐，隔离两页图像端到端保存3种材料通过。首次中间构建不交付。ADR、输入上限与真实验证边界见 [ADR0051](adr/0051-document-timeouts-and-visual-pdf-input.md) 和 [本轮验证](document-timeout-fix-verification-20261118.md)。

最终 Windows 安装器已生成并通过 PowerShell 5.1 隔离安装、安装版两页图片解析链路（仅本机模拟Provider）、14项Host测试及322项资源配对；155项运行源/配置保持不变。安装包 [Document Timeout Fix](../.local/releases/document-timeout-fix-20261118/ResearchGraph-Studio-Document-Timeout-Fix-0.0.1-x64-setup.exe)，160,454,363 bytes。真实端点兼容与论文识别质量、原生GUI和干净机仍待验收；本轮未Commit/Push。

## 2026-11-18 · 模型文档超时调查（未改产品行为）

用户最新 PDF 模型导入从 17:57:06.956 到 17:58:37.148，创建到失败 **90.191 秒**；只读任务参数确认使用火山 `deepseek-v4.1-flash`、冻结 timeout=90 秒、reasoning_effort=max、PDF chat_file。失败已越过能力声明检查，直接落在 HTTP timeout 分支。整篇非流式请求与 90 秒读取/上传阈值高度吻合，等待响应是主要候选；当前没有保存 timeout 子类，不能断定一定是读取超时，也不能由此证明 PDF 支持或不支持。

合成 MockTransport **5 cases passed**，四类网络超时均显示同一文案，总时限显示另一文案；调查时两家端点 DNS/TCP/TLS 直连通过，无 HTTP/模型请求。按用户调查要求只读正式库的任务元数据和配置，不读正文/密钥；文件仅取大小，未读内容。未改产品、配置、任务状态，未重试收费请求、未构建新包或 Commit/Push。此前开发“正式库未访问/真实模型0”的边界只属于各自开发轮次，不用于否认此次只读诊断或用户已经执行的请求。完整证据与未确定项见 [超时调查](document-timeout-investigation-20261118.md)。

## 2026-11-18 · 本地/模型双解析与文档能力设置

按用户新要求，PDF/Zotero 导入默认本地解析建库，只有显式选择模型并授权才发送 PDF。修复保存 profile 时重置文件能力、编辑提供商覆盖参数的问题；新增每模型 PDF/文件传输声明和独立“论文解析模型”选择，不把联网勾选或文本连接成功当作 PDF 能力。论文页提供本地解析/重试、使用当前配置的模型重新解析和本地/模型材料查看切换，保留原论文身份、源文件、笔记和历史结果。新入口和规则见 [ADR0050](adr/0050-explicit-local-and-model-parsing.md)，覆盖旧“新导入仅模型优先”的界面限制；显式模型失败仍不自动回退。

最终引擎 **429 passed / 1 skipped / 1 warning（98.01 秒）**；桌面 **12 files / 109 passed（15.14 秒）**；Edge **16 passed（12.5 秒）**；mypy 79 files、Ruff、TypeScript/ESLint 和契约导出通过。新包 [Dual Parse](../.local/releases/dual-parse-20261118/ResearchGraph-Studio-Dual-Parse-0.0.1-x64-setup.exe) 为 **160,435,399 bytes**，153 项运行源/配置构建前后不变，sidecar 与 322 项安装资源配对一致。PowerShell 5.1 隔离安装实测清旧后本地重新解析、同 paper_id、不重复论文与再次清理通过；安装后 Host **14 passed / 0 ignored**。

schema 保持 `lite0012`，无新迁移。真实模型调用/费用 0、正式用户数据库未访问；截图端点的真实 PDF 兼容、论文科学质量、原生 GUI 和干净机仍待验收。修改模型配置后需“使用模型重新解析”采用当前配置，旧任务“重试”沿用原快照。未 Commit/Push。详见 [本轮验证](dual-parse-verification-20261118.md)。

## 2026-11-18 · 导入失败、管理授权与全文章节阅读状态

本轮修复用户安装反馈的四项问题：Host 现在放行精确 UUID 的论文重命名、删除和旧内容清理；模型解析在事务内冻结普通计划/授权值，修复关闭 Session 后读取 ORM 导致的 `DetachedInstanceError`；Zotero 选择保留真实题名并在模型解析前显示；全文精读整合大章节“未开始 / 阅读中 / 已读完”、目录完成标记与继续阅读，小节导读和独立理解状态入口已移除。

解析任务与论文面板显示真实阶段：读取 Zotero 附件、准备模型、等待模型解析、校验结果、保存章节。当前是单次非流式请求，等待阶段没有逐章百分比。Job、计划项、解析和导入会话的失败/取消/重试同步；升级时把旧终态 Job 遗留的“解析中”计划对齐为终态，不自动重发。联网已授权的失败解析可由用户显式点击“重试模型解析”；原计划未授权联网时提示重新导入。

`lite0012` 加性增加模型章节阅读状态，按 `parse_id + chapter_ref` 保存，大章取模型章节的最小层级。新解析不继承旧已读标记，旧记录保留；模型章节状态的读取与标记均不调用模型。旧 Section 的进度通过窄范围 PATCH 更新，保留自评、问题、失去关联的概念和来源基线。清理旧本地解析保留模型章节状态；整篇删除仅移除对应论文状态，其他论文与源文件边界保持。升级前仍自动备份。

最终后端全量 **419 passed / 1 skipped / 1 warning（83.96 秒）**；最终桌面 Vitest **11 files / 106 passed（13.62 秒）**，Edge 真实 React 渲染回归 **15 passed（12.1 秒）**。全 Ruff lint、全引擎 mypy（78 files）、compileall、TypeScript/ESLint、Prettier、OpenAPI/TS 契约导出通过；全局 Python format 仍有此前无关文件格式欠账，本轮修改文件格式检查通过。浏览器覆盖已读状态、重新打开后的续读、620px/390px 下标题避开固定工具栏及无横向溢出。

取消守卫覆盖附件路径读取、PDF 异步读取和 HTTP 客户端准备：真正 POST 前重新检查 Job，终态任务不发送请求；已发出的供应商请求无法撤回，但取消后不会发布解析输出。合成 MockTransport 覆盖这两个边界，没有真实外发。

最终安装包为 [Import Reading Fix](../.local/releases/import-reading-fix-final-20261118/ResearchGraph-Studio-Import-Reading-Fix-0.0.1-x64-setup.exe)，**160,413,261 bytes**。构建前后 151 项运行源/配置不变，安装前后 sidecar 与 322 项资源配对一致；PowerShell 5.1 隔离安装通过，schema `lite0012`，已读状态保存/清旧保留/整篇删除，以及引用 PDF 保留均实测通过。安装后 sidecar 的 Rust Host **14 passed / 0 ignored**，含实际启动与重启。不交付前两次已被后续修复替代的构建，失败与中间证据保留。

真实 Provider/模型调用与费用为 0，正式用户库和私人论文未用作开发实验；真实论文质量、用户原生 GUI 和干净机兼容性仍待验收。未 Commit/Push。完整结果见 [本轮验证](import-reading-fix-verification-20261118.md) 与 [ADR0049](adr/0049-import-recovery-and-chapter-reading-progress.md)。

本轮会话终止原因已从 Codex session JSONL 还原：最近一次失败前最后的工具调用是 `write_stdin(session_id=60020)`，其返回 `Unknown process id`；随后 Codex 向 CC Switch 发起下一轮 `/responses` 工具请求，TokenX 上游返回 HTTP 400，原因是该账户只支持 Chat Completions。该错误与项目业务 tool call、pytest、Ruff 或 PDF 请求参数无关；同一配置在更早失败中也出现在 `exec`、`collaboration.send_message`、`list_agents`、`wait_agent` 之后。需调整 CC Switch/TokenX 的 Responses 能力或切换支持 Chat Completions 工具调用的 Codex 模型。

模型优先导入已继续实现并完成隔离安装验证：`lite0011` 新增独立 `llm_document_outputs` 派生层；解析成功后仅将用户勾选的概览、全文精读、逐段翻译排入专用后处理任务，直接消费模型章节数据，不进入旧本地 Chunk/Section worker。后端专项 **18 passed / 1 warning**，引擎全量 **371 passed / 1 skipped / 1 warning**，桌面两组回归 **50 passed**；PowerShell 5.1 隔离安装与安装后 smoke 通过。真实 Provider、论文科学质量和桌面 GUI 原生体验仍未验收。

2026-11-18 增量：Tauri PDF 选择句柄已随模型优先计划转发；PDF/Zotero 会话记录 `paper_id`，桌面论文工作区可以读取 `llm_document_parse` 的章节、公式、表格和独立后处理输出。后处理严格校验章节归属、翻译原文引用和非空概览/精读结果；Provider 配置异常与失败状态会同步收敛。安装包使用最终打包引擎路径运行 Rust Host **11 passed / 1 ignored**，安装后 Host 测试 **1 passed**；前序验证包含引擎全量 **371 passed / 1 skipped / 1 warning**、模型导入专项 **18 passed / 1 warning**、桌面回归 **50 passed**，以及 TypeScript/ESLint、Ruff、compileall 和 `git diff --check`。本轮没有真实模型调用。

## 2026-11-18 · 模型优先导入实现与 Windows 安装验证

模型优先导入已完成当前实现并生成未签名 Windows 安装包。`lite0011` 保存导入计划、模型章节解析及独立概览/精读/翻译输出；解析结果进入论文工作区展示。只有明确授权联网才发送 PDF；公式和表格始终请求提取，多模态图像内容可以跳过。该数据层不覆盖旧本地阅读的 Chunk/Section 和历史笔记。

安装器构建前后核对了 **131 个**引擎、桌面、宿主和脚本源文件，内容指纹一致。PowerShell 5.1 隔离静默安装通过，健康检查 schema 为 `lite0011`；使用匿名合成材料保存并读回 3 个章节/材料段，包含公式与表格，Provider 调用数为 0。安装后 sidecar 的章节精读、全文精读和阅读存档三组 smoke 通过。合成 SSE 的 Token 仅为测试夹具数据，不代表真实模型用量。

Rust Host 测试为 **11 passed / 1 ignored**，针对安装后 sidecar 的宿主启动/重启测试 **1 passed**。安装包为 [ResearchGraph-Studio-Model-First-Import-0.0.1-x64-setup.exe](../.local/releases/model-first-import-20261118/ResearchGraph-Studio-Model-First-Import-0.0.1-x64-setup.exe)，**160,407,722 bytes**，SHA-256 `A73CFF57B44ABC51031CB0D55186D3504E37A229FAF7327292956B21B8884B0C`；隔离验证记录在同目录 `verification.json`。安装器与验证数据位于 `.local` 忽略目录，不进入 Git。

本轮真实 Provider/模型调用、Token/费用、真实论文提取质量和桌面 GUI 原生操作均未验收；安装 smoke 只证明隔离安装和合成协议链路。实现尚未 Commit/Push。

## 当前状态

本轮新增论文列表同步修复：左侧个人研究空间与当前项目论文区现在同时监听 PDF/Zotero 导入任务状态变化，并在 worker 将 `Paper` 行提交后失效两条列表缓存；侧栏查询仍保留定时刷新和挂载时强制读取，避免首次失效早于数据库提交时停留在旧列表。前端回归覆盖“worker 提交第二篇论文后侧栏出现新标题”，TypeScript/ESLint 和桌面端 Vitest 通过。该改动包含在本轮综合安装快照中；隔离安装与 sidecar smoke 已通过，用户桌面 GUI 原生操作反馈仍待验收。

本地阅读的写锁竞争和旧章节树升级已修复：已保存的阅读版面校验后直接读取，论文/任务/笔记等纯 GET 使用受保护的只读快照。首次或旧存档从本地原文整理后短事务归档，写锁忙时仍返回正文；检测到旧 `structure-v1` 时，全文阅读和章节目录首次打开会从已登记且 SHA 一致的 PDF 自动生成一次 `structure-v2`，之后不再扫描。界面新增“重新读取本地存档”，不会重新解析或调用模型。这些本地阅读能力沿用此前 `lite0010` 表结构；当前 `lite0011` 在其上加性增加模型导入层，不删除旧数据。实际结果见 [存档验证](reading-cache-verification-20261116.md)、[结构自动升级验证](structure-auto-upgrade-verification-20261116.md) 与 [ADR0046](adr/0046-auto-upgrade-legacy-pdf-structure.md)。

针对 `1 INTRODUCTION` 后跳到 `5 CONCLUSION` 的后续修复已加入：结构解析会读取已标记的印刷目录行作为保守标题提示，只在正文页中精确匹配标题时恢复漏识别的一级/二级/三级章节；目录行仍保持材料区，不会再次成为章节。全文本地阅读投影完成后会刷新章节目录查询，避免旧结构升级和目录请求并发时把旧树留在界面缓存中。此次修改不读取模型、不新增 Token、不修改旧 Section/Span/笔记或外部 PDF；定向后端 `48 passed / 1 warning`，前端 PaperCloseReading/ReadingOutline `19 passed`，TypeScript/ESLint 通过。更新安装包为 [Lite Structure Outline Repair](../.local/releases/lite-structure-outline-repair-20261116/ResearchGraph-Studio-Lite-Structure-Outline-Repair-0.0.1-x64-setup.exe)（SHA-256 `854B436EEB2C50D987A4D416F03AD4F0359EB25691570F9016CF956A3E4F9CA6`），PowerShell 隔离安装、Lite 健康、匿名 PDF 解析和 0 模型调用通过。

本地工作区在既有 Lite A+B+D 和 P2 状态基础上，增加本地阅读整理层与一次全文精读任务：正文按段落、标题按标题，图表/图注/疑似图内标签折叠；保守组合可靠的跨块、跨栏和跨页续文，保留原始块、Span、页码、坐标与哈希。默认入口改为“论文精读 → 全文精读”，A04 一次模型请求生成当前论文全部可读正文的常驻中文译文、五色精确高亮、中文批注及全文摘要。保留 A01、A03、个人状态、旧 A02 历史与 LightGraph。2026-11-14 阶段的 `lite0010` 仅加表并沿用升级前备份；当前 `lite0011` 在其基础上继续加性迁移，不重建或删除数据。最新边界见 [ADR0042](adr/0042-paper-reading-document-and-notes.md)。

精读与问答共用可展开/收起的文章目录侧栏。最新修复使用 `structure-v2` 恢复漏识别标题，分离印刷目录并限制退化/局部表格误吞正文；目录按父子关系支持一级、二级、三级独立折叠。显式本地刷新逐块核对同 SHA 来源，增量添加新章节树，原 Span/旧结果不改；`reading-document-2` 按精确标题字符范围整理，旧全文笔记可能显示过期且不自动生成。段中/问答内部阅读锚点继续保留，无新增数据库迁移或真实模型调用。最新边界见 [ADR0044](adr/0044-versioned-pdf-chapter-tree.md) 与 [本轮验证](reading-tree-verification-20261116.md)。公式目前已做保守候选定位、同 SHA 局部 PNG 原图预览、可选本地 Pix2Text MFR 识别、版本化结果缓存和识别后精读投影自动刷新；默认未配置 OCR 时仍保留原图和 `latex_unavailable`，原始线性文本不会被猜补。边界见 [ADR0043](adr/0043-reading-outline-and-formula-source-boundary.md) 与 [公式 OCR 运行说明](formula-ocr-setup.md)。

论文导入后的模型处理方案见 [ADR0047](adr/0047-import-time-post-processing-plan.md)：选择模型优先导入后直接把 PDF 文件引用交给大模型，按章节导出正文、公式和表格，再按用户选择生成论文概览或全文精读；精读下可选逐段中文翻译。图片/图内内容在无多模态时允许跳过，公式和表格尽量提取并明确降级状态。新流程不以本地 PDF 解析、`reading-document-2`、FTS5 或 SHA-256 作为前置条件。设计基线已推送至 GitHub `main`（`0dbd5d2`）；本轮实现与隔离安装现已完成，但尚未推送。真实模型调用和正式用户数据库仍未使用。

整篇 PDF 翻译服务器和 PDF 导出流水线仍已撤下，旧任务不恢复或重发。阅读译文只在用户明确生成全文精读笔记时产生；打开论文、本地整理和切换章节不会自动调用模型。全文超出模型有效容量时发送前拒绝，不静默截断、不隐藏分批。下方范围 A02 和整篇 PDF 翻译的生成入口属于历史阶段，当前边界读 ADR0042；翻译撤下边界仍见 [ADR0040](adr/0040-remove-pdf-translation.md)。

上一轮按用户 2026-11-16 的 Push 授权，将 P2、全文精读及最初的目录侧栏以源码提交 **`29d598e3f470c2c1b5740f73b79c37260d91fe2a`** 普通推送 GitHub `main`，官方远端 SHA 已核对一致；315 文件内容、91 文件暂存及完整历史扫描通过，安装器/运行数据未上传。HTTPS 失败后使用官方 SSH 443，未改 origin/全局网络或 force push；GitHub API 限流 403，CI 未核实。本轮缺章与三级目录修复暂无新的上传授权，未 Commit/Push，不继承上一轮授权。

| 能力                                               | 实际状态                                                                                                                                                                         |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tauri 2 + React/TypeScript + FastAPI + SQLite/FTS5 | 保留并已精简，静态检查通过                                                                                                                                                       |
| Zotero 连接、论文选择、PDF/章节解析、文本索引      | 本地解析/索引仍为 0 模型调用；另提供用户授权后运行的模型优先导入，详见 `lite0011` 和下方安装验证                                                                                  |
| Lite 模式、`lite0012`、用量与缓存基础              | 保留旧阅读投影/全文笔记及模型文档；新增按解析版本绑定的大章节阅读进度，采用加性迁移 |
| PaperCard + LightGraph                             | P1 联合抽取、缓存、任务、布局 API 与交互已实现；由一次模型调用生成                                                                                                               |
| 图谱交互                                           | 已支持节点拖动、缩放、点击详情、关系详情、布局/相机持久化和重置                                                                                                                  |
| A01 章节导读                                       | 正常入口已移除；旧接口、缓存和历史兼容保留，正常精读直接进入全文 |
| 本地阅读整理                                       | `reading-document-2` 正文/标题/材料分离、双栏顺序、保守连续段组合；同 SHA 本地刷新增量修复当前章节，原始来源和旧结果保留；图片/矢量只定位，公式支持受限原图预览和可选本地识别 |
| 公式定位与显示                                     | 同 SHA PDF 的保守候选、revision-bound `formula_id`、PNG/JSON base64 原图预览、版本化识别缓存、Pix2Text 可选适配器和 KaTeX 可信结果渲染已接入；默认安装包不带 OCR 权重 |
| A04 全文精读 / A02 历史                            | A04 一次完整正文请求，译文/高亮/批注/全文摘要联合生成，完整/部分/过期分开；保留 A02 历史读取，默认界面不再逐范围生成 |
| 文章目录侧栏                                       | 精读/问答共用，可逐级折叠一级/二级/三级标题，定位当前项展开祖先；保留段中锚点，刷新清除失效选择，晚到响应按原请求范围归档；操作零模型 |
| 章节进度与旧个人理解状态                           | 大章节下直接标记未开始/阅读中/已读完，目录显示已读并支持续读；独立理解状态入口已移除，旧自评、疑问、概念笔记与 A03 历史保持 |
| D 证据问答                                         | P3 D01 已实现最小闭环：section/paper/selection 契约、FTS5 Top-K Span、显式授权、严格引用校验、缓存、失败/取消/重启记录和桌面问答区；D02 已实现为本地无命中后的可选英文关键词辅助 |
| 完整图谱抽取、跨论文推理、Lint/Wiki                | 已从活跃 Lite 工程移除；历史工程只保留在备份分支                                                                                                                                 |
| 设置与阅读信息架构                                 | Lite 用量在设置按全部项目查看；模型连接单独保存 Base URL/API Key；论文工作区为论文概览、论文精读、论文问答，阅读进度融合于全文和目录 |
| 文献翻译                                           | 已按用户要求撤下界面、业务 API、执行器、模型代理、服务启停和打包资源；历史记录只读，未完成任务停止为已取消，不删除旧文件 |

## 2026-11-17 · 公式候选定位与原图预览增量

针对公式被普通文本解析破坏上下标、分数和积分上下限的问题，本轮先完成保真回退链路：PDF 导入/本地阅读整理会按版面符号、短块、居中位置、字体线索和公式编号保守标记疑似独立公式；候选保留页码、bbox、原始文本、文本哈希、稳定 `formula_id` 和 `latex_unavailable` 状态。刷新扫描传入文献版本 ID，使结构、阅读投影和公式 API 使用同一 revision-bound ID；旧结构缓存缺少 ID 时由当前 revision、页码、bbox 和原文重新计算，避免预览路由失配。

新增只读接口 `GET /api/v1/revisions/{revision_id}/formulas`、`.../formulas/{formula_id}/preview` 和兼容的 PNG `/image` 路由。来源必须是已登记且 SHA-256 与 revision 一致的 PDF，预览裁剪、页码和面积有界；JSON 预览返回 base64 PNG，供 Tauri bridge 安全传递。桌面宿主白名单只接受 UUID revision、受限 `formula-` 32 位十六进制 ID 和 `page/limit` 查询。前端仅在明确有可信 LaTeX 时使用 KaTeX；未识别时显示原始文本及原图入口，不从损坏的线性文本猜补公式。

测试覆盖合成 PDF 候选检测、结构中的 revision-bound `formula_id`、同 SHA 来源校验、PNG 二进制和 JSON base64 预览、非法宿主路由与旧结构 ID 兼容。定向后端 `73 passed / 1 warning`，Ruff 和相关 mypy 通过，契约已重新导出。真实模型调用、Token、OCR 权重和私人 PDF 读取均为 0。专用公式 OCR/图像转 LaTeX 识别器仍未接入；下一步需单独评估权重、许可、安装包体积、CPU 能力、缓存失效和结构级准确率，不能把 KaTeX 渲染成功当成公式识别正确。

## 2026-11-17 · 公式识别流程与精读投影自动刷新

在前一轮保守候选和原图预览基础上，补齐了本地公式识别的增量链路。`formula_api.py` 新增 `POST /api/v1/revisions/{revision_id}/formulas/recognize`，支持整篇候选或指定 `formula_ids`，默认不重复处理已识别项；识别器返回结果经过控制字符、长度和括号平衡检查，非法 LaTeX 转为 `needs_review`，失败保留原图和原始文本。接口明确返回 `model_calls=0`，不创建 LLM 用量记录。

识别结果保存到当前版本化 `DocumentParse.data.formulas` 的派生字段，绑定 PDF SHA、revision、页码、bbox、原文哈希、识别器版本和配置哈希；重启后从结构存档读取，源 SHA、原文或区域变化时旧结果不暴露为可渲染 LaTeX。识别成功后在同一短事务重组阅读投影，桌面端自动重新读取 `reading-document`；前端新增“自动识别公式并刷新”按钮，`recognized` 才进入 KaTeX，`needs_review`/`failed`/`latex_unavailable` 均显示原图入口。

新增可选 `formula_ocr.py` Pix2Text MFR-1.5 ONNX CPU 适配器，只有设置 `RESEARCHGRAPH_FORMULA_OCR=pix2text` 且提供本地模型目录时才启用，应用启动不会下载权重。当前 `researchgraph-studio` 主环境没有安装 OCR 依赖或权重，因此实际运行返回 `FORMULA_RECOGNIZER_UNAVAILABLE`，没有真实模型调用、Token、OCR 权重下载或费用；这不是公式科学准确率验收。相关部署边界见 [公式 OCR 运行说明](formula-ocr-setup.md)。

专项验证：公式/解析/投影/识别 API **61 passed / 1 warning**；阅读投影/存档回归 **60 passed / 1 warning**；Ruff、相关 mypy、TypeScript、ESLint、Prettier 和 OpenAPI/TS 契约导出通过。Tauri 白名单新增识别 POST 路由，前端 PaperCloseReading 识别后重读测试通过。未读取正式用户数据库、私人 PDF、Zotero 正式库或 API Key；无 Commit/Push 授权，本轮不推送。

默认 Windows 安装包仍不携带 Pix2Text/Torch/模型权重，避免把约 200MB 级模型和重型依赖强行放进 Lite 主安装包。完成最终全量回归和安装包构建后，以实际包路径、SHA 和验证结果为准；用户配置专用 OCR 权重后的符号/结构准确率仍需独立验收。

## 2026-11-17 · 公式识别自动刷新与安装验收

公式识别链路已完成自动刷新闭环：点击论文精读中的“自动识别公式并刷新”后，后端只处理已由本地 PDF 版面定位的公式候选；识别结果绑定 PDF SHA、revision、页码、bbox、原文哈希、识别器版本和配置哈希，并在版本化结构存档中保存。识别完成后同一短事务重组 `reading-document-2` 投影，桌面端自动重新读取论文精读内容，因此不会继续展示识别前的旧解析结果。只对通过校验且状态为 `recognized` 的 LaTeX 使用 KaTeX；`needs_review`、`failed` 和 `latex_unavailable` 继续保留原始文本和原图入口。

当前主环境没有 Pix2Text、Torch、ONNX Runtime 或本地模型权重。默认安装包因此返回 `FORMULA_RECOGNIZER_UNAVAILABLE`，不会根据损坏的线性文本猜补 LaTeX，也不产生 LLM Token。已接入可选 Pix2Text MFR-1.5 ONNX CPU 适配器，只有显式设置 `RESEARCHGRAPH_FORMULA_OCR` 与本地模型目录后才加载；普通启动、PDF 解析和阅读刷新均不会联网下载权重。真实公式符号和二维结构准确率仍需在用户配置专用权重后用可分发样本单独验收。

本轮专项后端测试 `75 passed / 1 warning`，前端阅读测试 `3 files / 59 passed`，Rust 安装后 Host `11 passed / 0 ignored`；隔离安装 schema 为 `lite0010`，匿名 PDF 解析及模型调用为 `0`。新的未签名 Windows 安装包为 [Formula Auto Recognition](../.local/releases/formula-auto-recognition-20261117/ResearchGraph-Studio-Formula-Auto-Recognition-0.0.1-x64-setup.exe)，SHA-256 `F14EB914F6ED0D3FCFCDD6035B0B99C76F5E737B187596ED3621A9AEF4970D77`；完整 sidecar 引擎 SHA-256 `4D95B0E6BCB2BF40243786503171AF4DB9E674BBF5809FB7DCFE01480FC8F8BB`。本轮 Gitleaks/敏感路径扫描 `330 files` 通过，未 Commit/Push。

继续隔离安装验收后，新的交付包为 [Formula Resume](../.local/releases/formula-resume-20261117/ResearchGraph-Studio-Formula-Resume-0.0.1-x64-setup.exe)，大小 `160,345,366` bytes，SHA-256 `5038AA4B3100E7B47C27E285772639F20A7A3A5019303A0A9192C08BB91ADA5F`；安装后 sidecar 引擎大小 `17,357,643` bytes，SHA-256 `B622E1FF2AB211017A597D1484C42381ED29CB8DAC61BB0B78746F3B21852DE3`，与交付目录一致。PowerShell 5.1 静默安装、`lite0010` 健康握手、匿名 PDF 导入/本地解析、FTS5 和 0 模型调用通过；翻译接口仍为 `404`，旧 `translation-runtime` 未打包。安装后使用匿名合成公式 PDF 验证到 1 个候选：未设置 `RESEARCHGRAPH_FORMULA_OCR` 时返回 `FORMULA_RECOGNIZER_UNAVAILABLE`，保留原图和原始文本，未自动加载离线资源，`model_calls=0`。验证材料位于 `.local/verify/formula-resume-20261117/`；这证明安装与安全回退行为，不代表公式科学准确率通过。未 Commit/Push。

## 2026-11-16 · 旧章节结构首次读取自动升级

本轮确认截图中的 `1 INTRODUCTION` 后跳到 `5 CONCLUSION`，并出现重复 `5 Conclusion`，原因是正式 Lite 数据库仍在复用早期 `structure-v1`：印刷目录条目曾被持久化成章节，正文标题也没有完整识别。前端目录只是按后端顺序显示，问题不是折叠或排序，也不是 PDF 缺页。

新增 `services/engine/researchgraph/structure_upgrade.py`。`GET /api/v1/papers/{paper_id}/reading-document`、`GET /api/v1/revisions/{revision_id}/sections` 和结构读取入口在返回内容前检查解析版本；只有旧版本才读取已登记且 SHA-256 一致的 PDF，用现有 `structure-v2` 扫描器加性发布新 `DocumentParse`、Section 和 FTS。旧 Section、Span、Chunk、笔记、问答、个人状态、用量和外部 PDF 全部保留；没有模型任务、Provider 请求或 Token。并发请求会二次核对版本，数据库忙、源缺失或哈希变化时保留旧树并在下次读取重试。章节投影同时过滤旧树中可确定的印刷目录条目，避免兼容路径继续把目录当正文章节。

实际验证：后端全量 **348 passed / 1 skipped / 1 warning，95.31 秒**；结构自动升级专项 **22 passed / 1 warning**，阅读存档/并发组合 **38 passed / 1 warning**；Ruff、Ruff format、mypy 65 个源文件、pip check、TypeScript/ESLint/Prettier 和 React **9 files / 86 passed** 通过。前端生产构建通过，Vite 保留现有约 592.08KB 单 chunk 提示。真实模型调用、真实 Token、重试及新增费用均 **0**，隔离测试使用匿名 PDF/合成数据。

Windows 未签名安装包：`.local/releases/lite-structure-auto-upgrade-20261116/ResearchGraph-Studio-Lite-Structure-Auto-Upgrade-0.0.1-x64-setup.exe`，**38,575,252 bytes**，SHA-256 `18523C9D4EF784EB310B8CC6F6F24194322710C7E8910AD30BE23C82D175A147`。同目录 `researchgraph-engine/` 含完整 `_internal`，引擎 EXE **15,232,181 bytes**，SHA-256 `A93FC736474AA785C5B3C4D361C0AAEC4085B1459027A1B91B26B6896C995DCA`，不能单独复制 EXE。PowerShell 5.1 隔离静默安装、lite0010 健康检查、匿名 PDF 导入和本地索引通过，模型调用为 0。构建与验证目录均在 `.local` 忽略路径；本轮未 Commit/Push，也未读取或修改正式用户数据库。

旧源 PDF 不可用时不会删除旧解析；当前安装包首次进入已有论文的全文精读或章节目录即可自动尝试升级，无需删库或重新导入 Zotero。复杂版面、扫描页 OCR、公式恢复和表格语义仍按现有边界处理。详细边界见 [结构自动升级验证](structure-auto-upgrade-verification-20261116.md)。

## 2026-11-16 · 本地存档与并发读取修复

截图提示为数据库锁冲突，不代表需要重新解析或确定有任务仍在运行。已确认旧GET本身申请写锁并重组阅读投影；本轮复用持久存档并拆开只读准备/短事务发布。原文、Span及坐标、章节树、布局和视图哈希仍每次核验，旧缓存自动补校验元数据；其他请求刚发布新存档时拒绝旧准备结果覆盖。已完成笔记和个人状态保留，读取重试不生成新任务。静态关键词路由优先，避免被问答ID路由误匹配。

后端全量342 passed/1 skipped/1 warning，66.68秒；React9 files/86 passed，11.94秒；Edge13 passed，11.2秒；TypeScript/ESLint/Prettier、Ruff、94文件格式、mypy64源与pip check通过。真实文件WAL并发和暖缓存无组装/无写入、冷缓存忙时仍可读、旧缓存升级、源/坐标校验及显式刷新边界均有回归。

完整Windows构建和PS5.1隔离安装通过，114个运行源/配置保持、265个sidecar文件匹配。安装后普通/A02+A03/A04 smoke与存档专用实际重启测试通过：持写锁可读，脚本自造PDF删除后仍能重启读取同存档，0模型；原生Host11 passed/0 ignored，2.84秒。未签名安装包`.local/releases/lite-reading-cache-20261116/ResearchGraph-Studio-Lite-Reading-Cache-0.0.1-x64-setup.exe`，38,569,335字节/36.78MiB，SHA256 `D7576F3C24DA07830C9BB3A1C8F42659F178897AEE168CF7473C3F00285E2EDC`。真实模型/Token/重试/新增费用0，无Commit/Push，详细结果及合成用量读[本轮报告](reading-cache-verification-20261116.md)。

## 2026-11-16 · 缺章修复与三级目录树

确认用户反馈由小型大写标题漏检、退化网格误吞正文、印刷目录重复标题及原侧栏平面展示共同造成。新版解析与投影逐个验证标题字符范围/级别/引用，支持同块多个标题、References 后的附录恢复。Section/Span 原身份保留；当前树映射通过经核验原始块读取旧 Span，块跨多小节则明确上下文较宽，混合排除章节不用于新导读/问答。FTS 每块一行，不复制来源。旧已完成问答读冻结来源，输入变化的未完成任务不外发。

实际来源只读诊断与隔离副本刷新恢复主章 **1–5**、**4.1–4.5**、三级层级，65 个当前章节、63 个可见标题，61 个印刷目录材料，重复第五章消失。原业务行/用量保持，重复刷新投影一致，正式库逻辑快照和 Zotero PDF SHA 前后相同；没有在正式库实验。一个残余检测网格对长正文仅局部相交，已改为部分范围提示，不再整体吞正文，不宣称网格语义已验证。

最终后端 **326 passed / 1 skipped / 1 warning，65.14 秒**；Ruff/99文件格式/mypy64源/pip check通过。最终前端 TypeScript/ESLint/Prettier、React **9 files / 83 passed，12.20 秒**通过；Edge **13 passed，11.9 秒**，四张截图已检。Rust fmt/clippy、API/TS契约导出通过。解析25、投影44、兼容16专项包含在对应最终验证范围；早期8项投影错误已修，重复测试的日志占用尝试不计通过。

完整 PyInstaller/Tauri/NSIS 构建通过，114个源码/配置SHA保持；PS5.1隔离安装通过、265个sidecar文件逐一匹配。安装后匿名五页文献实测五主章/三级parent/投影/小节检索/重复刷新保持，调用0；普通/A02+A03/A04 smoke通过，合成用量46/82/128与23/41/64分列，不是真实成本。安装后原生Host **11 passed / 0 ignored，2.88秒**，含启动/重启；Vite现有591.34KB单包提示保留。

未签名安装包 `.local/releases/lite-reading-tree-20261116/ResearchGraph-Studio-Lite-Reading-Tree-0.0.1-x64-setup.exe`，**38,560,200 bytes / 36.77 MiB**，SHA256 `57C2D1821F01199C737F80D282C18860C8A599A7FC573C92B8901056D87B24D2`；同目录完整引擎EXE SHA `CA590F7D1C4167637EB371978ED4D140036155ACEE6B679D7880A18C8EF94E0D`。未覆盖日常安装，用户GUI与干净机待反馈。

真实模型调用、真实 Token、真实重试与新增费用均 **0**。已有论文安装后在全文精读点击“重新整理本地阅读版面”更新当前树，无需删库重导；旧全文笔记可能过期，保留但不自动再生。特殊字体/复杂版面/扫描页和同块跨小节仍有边界，公式 OCR 不在本轮范围。源码内容/私人路径规则与 Gitleaks318文件、7个改动文档/91个本地链接及diff检查通过，暂存为空，未Commit/Push。详见 [验证报告](reading-tree-verification-20261116.md)。

## 2026-11-16 · 较早的阅读目录侧栏与公式问题诊断

新增 `ReadingOutline.tsx` / CSS / React 与真实 Edge 测试，集成到全文精读、A01/旧笔记和论文问答。桌面左侧目录可收起，实际阅读区域小于 880px 时改为浮层；支持 Escape、外点、当前项可访问语义和焦点恢复。全文目录跟随实际滚动，短末节到底保持当前；问答只由显式选章改变章节，不改变已选提问范围。宽度重排前记录当前原文字符，恢复外层及问答原文框内位置，连续切换不逐行漂移。公式原图定位与 OCR 尚未实现，诊断及推荐顺序见 [评估](formula-parsing-assessment.md)。

最终 TypeScript/ESLint/Prettier 通过，React **69/9 files，8.68 秒**，修正夹具后 Edge 全套 **12 passed，10.5 秒**。首轮 9 通过/3 失败及后续段中漂移、内部滚动和夹具调整如实保留。四张截图已查看；段首/段中及内部原文同一字符在切换后误差 <2px。65 个后端/宿主源码与前次保持，本轮没有重跑旧 272 后端全量，不冒用旧成绩。

Windows 构建通过，**114 个源码/配置文件**打包前后 SHA 保持；安装包 **38,533,805 bytes**，路径 `.local/releases/lite-reading-sidebar-20261116/ResearchGraph-Studio-Lite-Reading-Sidebar-0.0.1-x64-setup.exe`，SHA-256 **`82758295011D3CDC48AD5A3207C0059344268C88C3A3E941B56D712457A11C5A`**。PS5.1 隔离安装通过，265 个 sidecar 文件与封存匹配，桌面 EXE 存在。安装后的本地解析、A02/A03 与 A04 合成 HTTP/SSE smoke 通过；原生 Host **11 passed / 0 ignored，2.87 秒**，含启动/重启。包未签名，正式库/用户 GUI 和干净机未冒充通过。

真实模型调用、真实 Token、真实重试及新增费用均 **0**。A04 的模拟 23/41/64 与 A02+A03 的模拟 46/82/128 只是账本验证；真实论文质量及成本待明确预算后验收。详细结果、使用步骤及剩余项见 [本轮报告](reading-sidebar-verification-20261116.md)。

## 2026-11-14 · 阅读整理与一次全文精读交付

新增独立 `reading-document-1` 本地投影，保守组合可靠的跨块/跨栏/跨页正文，双栏保持左栏后右栏；原始块、Span、定位和哈希保留。标题单列，表格/图片区域/图注/疑似图内标签进入默认折叠材料区，显示原文换行、页码、依据及建议，无 OCR/图表语义分析。旧论文可显式“重新整理本地阅读版面”，核对登记源 SHA 后只读补充信息，不删库重导。默认“论文精读 → 全文精读”，A04 一次完整正文请求联合生成译文、高亮、批注与全文摘要，不静默裁剪/拆批/补调。原 A01、A03、个人状态与 A02 历史保留。

`lite0010` 只新增 `lite_reading_documents`、`lite_paper_readings`，升级前备份；隔离迁移逐表确认旧行保持，正式用户库未操作。容量预检使用实际 Provider 的有效限制，已知不足零请求拒绝；缺段/截断保留有效部分但始终 `INCOMPLETE`。缓存绑定完整内容/投影/来源/模型/Prompt/Schema，旧稿过期独立保留；持久请求槽、原子认领、来源前后终验阻止重复发送。详见 [本轮验证](paper-reading-verification-20261114.md) 与 [ADR0042](adr/0042-paper-reading-document-and-notes.md)。

最终后端 **272 passed / 1 skipped / 1 warning，63.73 秒**；全文专项13、解析/投影专项31通过。Ruff/98文件格式、mypy64源、pip check通过。React **8 files / 65 passed，8.80 秒**；真实 Edge **8 passed，7.9 秒**；TypeScript/ESLint/Prettier、Rust fmt/clippy、契约导出与生产构建通过，现有577.65KB单包提示保留。审查发现的正文图表指代句误判、材料原文换行和区域文案均已修复，匿名两页PDF及真实渲染截图已查看。

PowerShell7完整打包、PowerShell5.1隔离静默安装通过；101个Python/前端/宿主源打包前后hash保持，安装后265个sidecar文件与封存逐一匹配。安装后本地解析/索引/阅读状态零调用，旧精读兼容及全文HTTP/SSE smoke通过；全文3段一次合成请求，缓存新增0，PDF字节保持。每次独立全文smoke模拟 **23输入/41输出/64总Token**、重试0、费用未知；旧A02/A03兼容的模拟46/82/128单列。最终安装引擎Rust Host **11 passed / 0 ignored，2.77 秒**，含启动/重启。真实模型调用、真实Token与新增费用均 **0**。

新未签名安装包：`.local/releases/lite-paper-reading-20261114/ResearchGraph-Studio-Lite-Paper-Reading-0.0.1-x64-setup.exe`，**38,522,485 bytes / 36.74 MiB**，SHA-256 `E0D4999005CF6CFE18ED3C4D7CCD57C49A7BB47B924CC42B5345A00013B87174`；完整sidecar同目录，引擎SHA `B8F53E250DC98CD3580B3FA7BB8A2DC25FF513AF4B13DE91E391F03A0C2D2148`。旧包与日常安装未覆盖；关闭旧程序安装后，从已有论文进入全文精读即可，不需删库或重导。

最终源码内容/私人路径规则及Gitleaks **306文件**通过；本轮20个改动文档/103个本地链接无缺失，diff检查通过，暂存为空。真实文献译文/批注质量、全文Token/费用、复杂版面、正式Zotero库、用户原生GUI和干净机仍待验收；不把合成用量、Host测试或匿名样例当作这些验收。没有Commit/Push，不追加收费或提前开发其他阶段。

## 2026-11-14 · 较早阶段：P2 双栏精读与个人理解状态

按本轮附件完成 P2-a/b/c 增量，不重建 A+B+D。入口为论文阅读工作区 → 章节精读 → 选小节 → 双栏精读。默认先读取本地英文；显式授权后 A02 对所选范围一次生成常驻中文译文、五色原文高亮、逐段中文批注和范围论证摘要。长小节手动缩小段落范围，缺段保留并支持仅重试缺失段，不自动预生成整篇或追加图谱抽取。A01 小节导读继续保留；个人状态点击零模型，A03 仅主动复述提交，建议不覆盖自评。LightGraph 用独立阅读圈层显示主观状态，节点语义不改。

`lite0009` 加性创建四表并沿用升级备份；兼容测试验证旧项目/数据保持，旧图谱版本不可靠的概念状态保留为待重新关联。缓存绑定源文/范围、Schema/Prompt 内容、模型与配置，旧结果过期独立展示；状态点击不使译文重生成。发送前持久请求槽，GET、取消和重启不自动重发。详细修改、Prompt、API 和验证边界见 [本轮报告](section-close-reading-verification-20261114.md) 与 [ADR0041](adr/0041-section-bilingual-close-reading.md)。

本轮实际验证：后端 **242 passed / 1 skipped / 1 warning，77.39 秒**；Ruff/86文件格式、mypy56源与pip check通过。前端 **59 passed**，真实 Edge 浏览器 **6 passed**，TypeScript/ESLint/Prettier和生产构建通过，现有562.66KB单包提示保留。OpenAPI/TS契约已导出。首轮旧测试head断言失败及smoke格式修正保留于报告，没有把尝试记为通过。

PowerShell7完整构建、PowerShell5.1隔离静默安装通过；56个Python源打包前后hash保持、安装后263个sidecar文件与封存逐一匹配。安装后本地四段读取/状态保存零模型；实际HTTP/SSE合成A02一次、A03一次、缓存新增零次，自评和PDF字节保持。安装后引擎的Rust Host全量 **10 passed / 0 ignored**，含启动/重启。真实模型调用、真实Token、重试及新增费用均 **0**；每次独立smoke的模拟46输入/82输出/128总Token仅用于账本验证，费用未知，不是真实论文成本。

未签名 Windows 安装包：`.local/releases/lite-section-reading-20261114/ResearchGraph-Studio-Lite-Section-Reading-0.0.1-x64-setup.exe`，**38,480,943 bytes / 36.70 MiB**，SHA-256 `3E27C040FBF893AEF21B1C1F4C91B36DD0E44F685A5FD0EF934B3DD914C96DB5`。同目录完整sidecar含`_internal`，引擎EXE SHA-256 `CCC3CAB1057C2F732B314EBD6F65BA8E8A65CC5A478664A91D738C55EF16E2A3`。安装验证只用独立目录，未替换日常安装。无需手动删库或重新导入已有论文。

最终源码内容/私人路径规则与Gitleaks **284文件**通过；**17个改动文档 / 83个本地链接**无缺失，diff检查通过，暂存为空。真实论文译文/论证/A03质量和真实成本尚未标定；正式Zotero库、正式库GUI和干净机仍待验收。没有读写正式用户数据，不Commit/Push，不进入其他阶段。

## 2026-11-12 · 撤回版本 GitHub 交付

用户在本地交付后明确要求“push到github”。提交前核对 `main`、官方 origin 和 60 个显式路径；当前全部 260 个源码文件的内容/私人路径规则及 Gitleaks 通过，提交前全部 Git 历史 37 个提交扫描通过。暂存区的 39 个新增/修改文件内容扫描通过，另 21 个删除路径已核对；`git diff --cached --check` 通过。没有上传凭据、私人论文、数据库、日志、翻译资源或安装器。

默认 HTTPS 连接失败，按 github-transfer 技能使用已验证主机密钥的官方 SSH443，认证、远端基线与 fetch 核对通过，先 dry-run 后普通 push；没有 force push，也没有改变 origin、全局 Git 或网络设置。源码提交 `a2ed78f9db31f7d61dcc79a707bdfaea0d4a210b` 已成功推送，官方远端 refs 返回同一 SHA。

GitHub Actions `Windows build and acceptance`，run `43151333334`，head SHA 为上述源码提交；11:56 查询为 `in_progress`、conclusion 为 null，尚不宣称远端 CI 通过。本次只提交/上传已验收源码并补交付记录，没有重新运行完整开发测试或真实模型。本机安装包 SHA 仍为 `B01F56AF08D2CBB0C2D0E2591D12038430FDC2D2BD3B82D19EAC630E2C652835`，运行源和安装内容未变；其后仅补本文档和开发日志。

## 2026-11-12 · 撤下文献翻译并交付轻量安装包

用户反馈 `TRANSLATION_PROVIDER_TRUNCATED` 后明确要求退回没有翻译功能的版本。本轮定向移除翻译功能，没有整体回退同时包含阅读/导航/模型配置改进的提交。保留论文概览（PaperCard + LightGraph）、章节精读、论文问答、Zotero、本地解析/索引、英文关键词辅助、项目树、模型连接、统一用量和底部折叠信息卡。

前端翻译板块、设置、DTO/API 和样式已删除；后端翻译路由、执行器、代理、外部服务与随包 CLI 已删除；Rust 宿主删除翻译文件操作并拒绝旧路由；构建和 CI 不再下载、准备或分发翻译运行环境。OpenAPI 与 TypeScript 契约已重新导出，不含翻译 API/DTO。旧本地资源、安装包和生成文件没有被主动清除。

Alembic head 保持 `lite0008`，既有迁移和表映射仅作兼容，不降级、不重建数据库。启动/领取时将旧 queued/running 翻译停止为已取消；retry 在幂等重放之前拒绝，GET 不推进。旧完成/失败等终态、快照、实际/未知 usage 和文件保持；历史特殊阶段只在 DTO 展示时映射，避免历史详情/列表报错，不改终态原始行。兼容验证使用隔离合成数据，没有读取或修改正式用户库。

实际验证：

- 后端 `python -m pytest -q`：**204 passed / 1 skipped / 1 warning，73.63 秒**；回退与迁移专项 **19 passed，7.22 秒**。覆盖历史库逐表保持、旧任务不发网络/不启动子进程、幂等重放阻断、CLI 参数拒绝及旧阶段展示。跳过为本机符号链接权限，警告为既有 Starlette/httpx 弃用。Ruff、71 文件格式、mypy 49 源文件通过，另 4 个 Python 脚本 Ruff/格式和 `pip check` 通过。
- 前端 TypeScript/ESLint、Prettier、**6 files / 51 passed（10.41 秒）**及生产构建通过。浏览器真实图谱 **2 passed（7.5 秒）**，含拖动、固定、缩放、选择、轮询和重载布局。初次加载超时及中间代理假设保留；构建结束后的串行对照中，原 Vite 监听仍有 1 失败/1 通过，仅排除 `src-tauri/**` 监听后两项通过。最终未改变 Edge 代理、断言或超时，仅调整开发服务器监听；最终生成的前端文件与安装包构建时逐字节一致。既有 531.42KB chunk 提示仍在。
- Rust fmt/clippy 通过；`RGS_TEST_ENGINE_PATH` 指向最终安装后的引擎，`cargo test --locked -- --include-ignored`：**9 passed / 0 ignored**，含原生宿主启动、重启和翻译路由拒绝。
- `scripts/build-windows.ps1` 使用项目 Conda Python 和 PowerShell 7 完成 PyInstaller、Tauri、NSIS。构建后 **49 个 Python 源文件哈希保持**。Windows PowerShell 5.1 隔离静默安装通过，安装后引擎 SHA 与封存一致；schema `lite0008`，匿名 PDF 解析/索引 **0 模型调用、0 输入/输出 Token**，翻译 API 404，安装目录无 `translation-runtime`。首次安装验证在默认 fixture 参数求值时退出，尚未安装；将路径默认值移至参数绑定后，使用默认 fixture 重跑通过。
- 内容/私人路径规则与 Gitleaks **260 文件**通过；改动涉及的 **18 个文档 / 93 个本地链接**均存在，最终 `git diff --check` 通过。暂存区为空，未 Commit/Push，未启动远端 CI。

本轮最终未签名 Windows 安装包：`.local/releases/lite-no-translation-20261112/ResearchGraph-Studio-Lite-No-Translation-0.0.1-x64-setup.exe`，**38,407,246 bytes（36.63 MiB）**，SHA-256 `B01F56AF08D2CBB0C2D0E2591D12038430FDC2D2BD3B82D19EAC630E2C652835`。同目录完整 `researchgraph-engine/` 包含 `_internal/`；引擎 EXE **15,081,736 bytes**，SHA-256 `33CCF7DE718E8AC9218D2889E749159F607445A06011834348723C9A38571461`，不能只复制引擎 EXE。安装验证位于 `.local/verify/lite-no-translation-20261112/`，构建/静态/安全资料位于 `.local/pdf2zh-audit/rollback-*`；图谱失败与串行对照位于 `.local/verify/translation-rollback-20261112/frontend-browser/`，均被忽略。

本轮真实模型调用、真实输入/输出 Token、真实重试和新增费用均为 **0**。没有覆盖用户日常安装、清空正式数据或读取正式 Key/私人论文/Zotero 库。隔离安装与原生宿主验证不等于干净机或用户正式库 GUI 验收；新版用户界面反馈仍待。退出旧版后可安装此包，无需手工删库或重新导入已有论文。

## 2026-11-11 · GitHub 交付记录

用户在本轮验证完成后明确要求 push。已将此前未上传的 Lite 清理/P0 提交及当前经验证的阅读、模型配置、导航、随包翻译和代理修复一并普通推送至 `KLucen/ResearchGraphStudio` 的 `main`。运行源码提交为 `e399357b36f70881a2eca1f701939bbc43d3454f`，推送后通过官方远端 refs 核对同一 SHA。默认 HTTPS 连接失败，使用已验证主机密钥的 GitHub 官方 SSH443，先 dry-run 后普通 push；origin 的 HTTPS 配置、全局 Git/网络设置均未修改，没有 force push。

提交前逐项核对98个源码/迁移/测试/契约/文档/脚本路径，源码内容扫描278文件、暂存内容98文件及全历史Gitleaks均通过；无私人论文、数据库、Key、运行日志、安装器或随包二进制。两处个人Skill安装路径改为环境变量示例，ADR日期行尾空格在暂存差异检查发现后已修正，最终暂存差异检查通过。

GitHub Actions `Windows build and acceptance` 已启动，run `43049353054`，源码 SHA 为上述提交；记录时状态 `in_progress`，**不宣称远端CI通过**。本机最终安装包与验证结果仍以下方记录为准；后续仅补交付文档，不改变运行源码或本机包。

## 2026-11-11 · 翻译代理兼容与错误分类

用户反馈的历史错误码是 `TRANSLATION_PROVIDER_FAILED`。旧后端将模型服务失败、预算及协议问题统一显示为“模型代理预算或请求校验失败”；这个码不足以还原该次失败的 HTTP 或响应原因，不能认定用户一定发生参数错误或 HTTP 400。

已修复可由代码确认的参数兼容缺陷：新建随包任务冻结 `text-chat-minimal-1`，复用模型连接、ID、凭据引用、超时和已知输出能力，但不重新注入阅读 Profile 的 temperature/top_p/reasoning_effort 或适配器附加字段。策略进入预检和缓存身份；旧无字段任务的快照、参数策略、缓存键及旧译文访问保持。Schema 仍为 `lite0008`，没有数据库迁移。

代理校验 SDK 的有限兼容字段后重建冻结请求，仍拒绝流式、工具、结构化输出和未知字段。上游鉴权、限流、其他 4xx、截断及响应格式错误分别显示具体代码和中文提示；未知结束状态不推定为 stop。失败后撤销临时票据，SDK、worker 和 GET 不得触发自动收费重发；已返回 usage 保留，缺失仍未知。用量审计只增加实际上游字段名，不记录正文、凭据、票据或上游错误正文。详见 [ADR0039](adr/0039-translation-proxy-request-policy.md)。

实际验证：

- 代理/API 专项 **81 passed / 1 warning，9.09 秒**；最终后端全量 **355 passed / 1 skipped / 1 warning，65.18 秒**。跳过为本机符号链接权限，警告为既有 Starlette/httpx 弃用。Ruff、格式 **91 files** 和 mypy **54 source files** 通过。前端未因本修复改动；本轮早先 TypeScript/ESLint/Prettier 与 **7 files / 61 passed** 通过，最终生产构建再次通过，保留既有 549.60KB chunk 提示。
- `scripts/build-windows.ps1` 使用项目 Conda Python 完成资源复核、PyInstaller、Tauri 与 NSIS；最终引擎封存后 **54 个 Python 源文件哈希未变化**。PowerShell 7 执行完整构建，本轮不将其冒充为整个构建脚本的 PowerShell 5.1 验证。
- 最终安装器隔离静默安装通过，schema `lite0008`、bundled 默认和资源检查正常；匿名 PDF 解析/章节索引 **0 模型调用**。安装后引擎 SHA 与封存副本一致。`RGS_TEST_ENGINE_PATH` 指向该安装后引擎，`cargo test -- --include-ignored`：**9 passed / 0 ignored**，含原生 Host 启动与重启。
- **安装后实际随包 CLI 增强 smoke 通过**：mono **42.922 秒 / 175,012 bytes / 2页**，dual **47.969 秒 / 177,747 bytes / 2页**，中文文本、双语页宽及各自整篇缓存命中均通过。所选 Profile 显式配置 temperature/top_p/reasoning_effort，合成 Provider 若收到这些字段即拒绝；实测出站字段只有 `max_tokens/messages/model`。
- 该独立安装 smoke 合成 Provider **27 次**：mono13、dual13、HTTP400负向1。负向约 **7.828秒**进入 FAILED，显示 `TRANSLATION_PROVIDER_REQUEST_REJECTED` 及具体中文，重试0、无产物、不回显上游模拟私密正文；再次GET不调用模型。两个成功格式的模拟 usage 合计442输入/182输出/624总 Token，HTTP失败无usage仍未知。这些都是固定夹具，不能作为真实 Token、真实质量或费用成绩。源码增强 smoke 另行通过，数据与安装版本分开记录。
- 封存最终 sidecar 的 manual/managed 合成协议 smoke 分别通过；各1次合成 Provider、17/7/24模拟 Token、2次缓存命中，managed完成前确认端口释放。首次 managed 命令漏传必填 `--runtime-python`，解析参数即退出、未执行验证；补齐参数后通过，不把首次记成测试通过。
- 源码内容/私人路径规则与 Gitleaks **278文件**通过；29个本地文档链接及 `git diff --check` 通过。暂存区为空，未提交或上传。

最终 Windows 安装包：`.local/releases/translation-proxy-fix-final-20261111/ResearchGraph-Studio-Translation-Proxy-Fix-0.0.1-x64-setup.exe`，**754,646,101 bytes（719.69MiB）**，SHA-256 `11D9F2ADAFC639DC334D9FE15AB383864C5875AC1173C4CF99F2ACB8C6FE944F`。同目录完整 `researchgraph-engine/` 保留 `_internal/` 与 `translation-runtime/`，EXE **15,174,112 bytes**，SHA-256 `1B71C55505DD4A849776F212AEF6E9D3E61377381E6D5CAE02196CE02C5BAB31`，不能只复制该EXE。未签名；本轮中间包与旧包保留，不作为最终交付。资料位于忽略目录 `.local/pdf2zh-audit/proxy-final-*`、`.local/verify/translation-proxy-fix-final-20261111/`。

本轮真实模型调用、真实输入/输出 Token、真实重试及增量费用均为 **0**；未读取正式 Key、用户运行库、私人 PDF 或 Zotero 正式库，未 Commit/Push。用户原任务的准确上游原因仍未知，旧失败及其实际/未知用量保留；修复版本的用户 Provider、真实译文科学质量、复杂版式、干净机与用户原生界面体验仍待反馈。使用新包后重新预检并显式提交新任务，不自动续发失败任务。

## 2026-11-11 · 内置翻译运行时与阅读布局

按用户最新要求，Windows 安装器提供完整翻译核心及运行环境，默认 enabled/bundled。只在用户明确授权的非缓存翻译任务中无窗口启动；翻译结束、失败、取消或退出时回收本应用的进程树。无需另装 Zotero XPI、Server 或 Python，也无需配置解释器和脚本路径。高级外部 managed/manual 继续可用。来源 PDF 不覆盖，模型只接收翻译文本与提示，真实 Key 继续留在本机模型代理中。

新界面默认生成左右双语 PDF，可选择仅中文 PDF。`output_mode` 进入预检指纹、任务与缓存键；切换格式须重新预检，只有所选文件通过校验才发布。API 缺字段及旧历史保持 both；`lite0008` 加性升级保留原论文、章节、用量、旧译文、外部路径及任务快照，缺快照的旧任务仍按 manual 解释。升级前自动备份，不重新初始化数据库。

阅读工作区和四个功能入口置顶。完整标题、分类、Zotero 打开、修订、解析警告、来源检查及原文移到页面末尾的独立“论文信息”卡，默认折叠；解析原文进一步按需加载，切论文恢复折叠。

实际验证：

- 后端全量 `python -m pytest tests/engine -v`：**330 passed / 1 skipped / 1 warning，95.16 秒**。跳过是本机符号链接权限，警告为既有 Starlette/httpx 弃用提示。包含输出模式/缓存、lite0006/0007 升级保留、内置 adapter 的固定参数/鉴权/路径/产物、无启动预检、进程归属及失败/取消清理。
- TypeScript、ESLint、Prettier 通过；前端 **7 files / 61 passed**，其中翻译 16、阅读 24。覆盖首屏顺序、默认折叠、原文按需读取、dual/mono、切格式预检失效及高级外部模式。生产构建通过，保留既有 **549.60KB** JS chunk 提示。
- Ruff 与 Python 格式 **88 files**、mypy **54 source files** 通过；Rust fmt/clippy 通过。Rust 含打包原生 Host **9 passed / 0 ignored**；安装后的引擎 Host 启动/重启另跑 **1 passed**。
- 源码及封存 sidecar 使用**实际随包 CLI**连接本地合成 Provider，匿名两页正文样例 mono/dual 均完成且各自整篇缓存命中不再调用。每个独立双模式 smoke 合成 Provider **26 次**（每格式13），模拟 usage 合计输入 **442** / 输出 **182** / 总 **624**；这些固定合成数字不是真实 Token。封存 sidecar 还验证实际中文文字和左右双语页面宽度。最初极稀疏 fixture 被上游判为扫描件，应用正确拒绝发布；该失败保留，不改成通过。
- Windows PowerShell 5.1 资源准备、重复校验及坏缓存拒绝通过；固定官方下载校验后，完整保留 Python、依赖、字体/模型/分词/CMap 资源和原始许可证，并提供匹配版本的第三方源码资料。运行资源共 **25,263 文件 / 1,457,616,856 bytes**，其中来源材料 **221,829,005 bytes**。构建脚本与 CI 均接入资源准备，资源和源码压缩包不进入 Git；本轮没有上传或运行远端 CI。
- `scripts/build-windows.ps1` 完整 PyInstaller/Tauri NSIS 构建通过。最终安装器隔离静默安装成功，schema lite0008，默认 bundled 已启用，安装资源校验通过，匿名 PDF 解析/章节索引 **0 次模型调用**，安装后引擎 SHA 与封存副本一致。**安装后实际 CLI 双模式 smoke 通过**：mono **44.500 秒 / 175,012 bytes / 2页**，dual **38.281 秒 / 177,747 bytes / 2页**；中文文字、双语宽度与两种整篇缓存复用均检查通过。该独立 smoke 合成26次、模拟442/182/624 Token，与源码/封存引擎测试分开记录，真实模型仍0。
- 封存引擎的旧 manual/managed 合成 HTTP smoke 分别通过，各为 **1** 次合成 Provider、**17/7/24** 模拟 Token及 **2** 次缓存命中；managed 完成前确认端口释放。
- 内容/路径及 Gitleaks 扫描 **277 文件**通过；`git diff --check` 通过，无暂存、Commit 或 Push。

可启动 Windows 安装包：`.local/releases/bundled-translation-20261111/ResearchGraph-Studio-Bundled-Translation-0.0.1-x64-setup.exe`，**753,899,166 bytes（718.97 MiB）**，SHA-256 `EAD2191E9E3F95494A935D32FDC472FEDB0658D63D292AC7D9E5C4422CBA1C06`。完整 sidecar 位于同目录 `researchgraph-engine/`，包含 `_internal/` 与 `translation-runtime/`，EXE **15,171,417 bytes**，SHA-256 `D98728D461E61A2646BB89B48AB8D30E4F24CC45B540B1596A538FE9D9AAF9E8`；不要单独复制其 EXE。未签名，隔离验收资料在 `.local/verify/bundled-translation-20261111/`，构建/测试报告在 `.local/pdf2zh-audit/`，均被 Git 忽略。

本轮真实模型调用、真实输入/输出 Token、真实重试和增量费用均为 **0**。未读取正式 Key、数据库、私人 PDF 或 Zotero 正式库。实际引擎合成联调只验证运行与产物，不代表真实论文翻译准确性、复杂公式/表格或干净机器兼容性；用户原生桌面体验仍待反馈。没有执行两个随包 VC++ 安装器或更改系统全局依赖，不能将本机隔离安装当成干净机验收。说明见 [文献翻译](pdf-translation.md) 和 [ADR0038](adr/0038-bundled-translation-and-reading-layout.md)。

## 2026-11-11 · 翻译服务按需自动启停

设置增加“按需自动启停（推荐）”和“手动连接服务”，支持浏览选择 Python 解释器与专用 `server.py`。首次仍需在工程之外安装完整 Server 4.1.8 / pdf2zh_next 环境；之后无需手动打开或关闭命令窗口。新安装无设置行时推荐 managed；`lite0006 → lite0007` 加性迁移将已有设置保持为 manual，并保留原有论文、解析、用量和译文，升级前自动备份。

配置检查和预检只读验证本机路径、脚本版本与端口，不执行 Python 或启动服务，也不证明排版依赖完整。只有非缓存、明确授权的翻译任务才启动服务；创建时冻结 `runtime_snapshot`，后续设置变化不会改写已排队任务。健康检查、提交、每次轮询及其历史回退、下载前重验自建进程与监听端口归属，失去归属时停止并保留诊断，不接管替代服务。

Windows 通过 CreateProcess 的 Job List 原子绑定专属 kill-on-close Job，隐藏窗口并仅继承 NUL 标准句柄；回收只针对自建树，不按进程名称杀 Python 或 Zotero。正常成功先下载、验证和保存译文，再确认 Job 活动进程数归零，最后发布 COMPLETED；失败、取消和正常退出也回收自建树，硬崩溃由 Job 句柄关闭清理。停止无法确认时不发布成功。任务界面增加启动与关闭阶段；取消后的最终清理警告可能在重新进入页面后显示，当前提示只表示请求关闭。

实际验证：

- 后端全量 `python -m pytest tests/engine -v`：**258 passed / 1 skipped / 1 warning，67.27 秒**；跳过为本机符号链接权限条件，警告为既有 TestClient/httpx 弃用提示。取消清理提示最终修补后，API 专项再次 **19 passed**。首次 `-q` 运行以退出码 1 提前结束、没有完整报告，不作为通过成绩；随后上述全量与专项成功。
- Runtime 专项包含真实合成 Server/子/孙三层进程、占用端口不接管、运行期端口被替代、启动超时/早退/版本错误、取消及 owner 被强制终止后的 Job 回收。Bridge 专项验证每个 HTTP 请求前检查，包括 history 回退；服务停止未确认不得发布成功。
- `pnpm --dir apps/desktop check`、`pnpm format:check` 通过；Vitest **7 files / 54 passed**。Ruff、Python 格式检查 **83 files**、mypy **52 source files**、Rust fmt 通过。
- `cargo test -- --include-ignored`：**9 passed / 0 ignored**，含最终打包引擎的 Host 启动与重启；安装后的最终引擎另跑 Host **1 passed**。
- `scripts/build-windows.ps1` 通过 PyInstaller 与 Tauri NSIS 构建。前端产物仍有约 **546.51KB** JS chunk 提示，不影响构建。
- 源码和最终打包引擎的自动/手动合成翻译 smoke 均通过；安装后引擎的自动模式 smoke 再次通过。自动模式实际创建后台合成服务进程，COMPLETED 时端口已释放，整篇缓存不再启动。每个独立 smoke 为合成 Provider **1** 次、**17 输入 / 7 输出 / 24 总 Token**、**2** 次缓存命中；模拟产物为匿名原 PDF，不能作为真实翻译或真实 Token 成绩。
- `verify-windows-install.ps1` 隔离静默安装通过：schema `lite0007`、默认翻译关闭、匿名 PDF 解析/章节索引、本地处理 **0** 次模型调用；安装后引擎 SHA 与封存 sidecar 一致。
- `scripts/check-sensitive.py --gitleaks .local/tools/gitleaks-8.24.3/gitleaks.exe`：**267 文件**内容/路径及 Gitleaks 扫描通过；`git diff --check` 通过。没有暂存、Commit 或 Push。

本轮可启动安装包：`.local/releases/managed-translation-20261111/ResearchGraph-Studio-Managed-Translation-0.0.1-x64-setup.exe`，**38,482,111 bytes**，SHA-256 `8BFB67708455E45BB87CE6202AE5763E5818A92A9A773175ED48A19AD24E598C`。完整 sidecar 位于同目录 `researchgraph-engine/`；EXE **15,149,511 bytes**，SHA-256 `F4C9806BFFBC60BF135AAD429A7966C6DEE7E22834AA3EEC05A114A3C794BA66`，须保留 `_internal/`。安装器未签名，隔离验收材料在 `.local/verify/managed-translation-20261111/`，均不进入 Git。

本轮真实模型调用、真实输入/输出 Token、真实重试和增量费用均为 **0**。没有读取正式 API Key、数据库、私人 PDF 或 Zotero 正式库；独立外部 Server/排版引擎仍未实际安装运行，真实译文、复杂版式、公式/表格、OCR/字体和用户桌面原生体验仍待验收。外部启动已关闭环境创建与源码更新，但通知检查和首次资源下载仍可能联网，不能宣称完全离线。使用说明见 [文献翻译](pdf-translation.md)，决策见 [ADR0037](adr/0037-managed-translation-server.md)。

## 2026-11-11 · 可选版式文献翻译

论文阅读工作区增加独立“文献翻译”板块，设置与诊断增加默认关闭的本机翻译服务配置。复用已保存的模型 Profile 和连接，不需要重复输入 API Key。本轮适配 `zotero-pdf2zh@e783bb9ffd5cf3caf0efbb2cfd4d19f8d9f8a09e` 自报 Server **4.1.8** 的 `pdf2zh_next / OpenAI` 协议；不捆绑外部源码、Server 或排版引擎，用户须独立安装专用本机服务。只支持全文英文到简体中文，同时请求中文与左右双语 PDF。

预检不调用模型，并用 `prepare_fingerprint` / `expected_fingerprint` 绑定来源字节、模型/连接/凭据引用、服务与版本、输出选项及预算；变更后重新预检。非缓存任务须显式确认模型外发和专用服务/留存副本。每个任务启动一次性 loopback 模型代理，外部服务只得到短期票据；真实密钥保留在系统凭据存储，模型响应若回显密钥会被拒绝，已产生用量仍保留。代理执行请求数和累计 UTF-8 输入字节估算限额，单请求输出最多 8192 Token（已知能力更低时取低值）；这些限制不是费用硬上限。

原 PDF 不覆盖，来源读取时校验实际字节 SHA-256。译文保存到受管的 `translations/<translation_id>/{mono,dual}.pdf`，下载与打开检查文件名、路径、大小、PDF 页结构和哈希；不进入作者原文 Span、FTS5 证据或 LightGraph，不自动回写 Zotero。整篇缓存和任务内相同成功请求可复用，外部缓存关闭。发布前要求有成功模型账本且无失败/在途请求；只显示“引擎已生成，全文质量尚未验证”。取消撤销票据、阻断新请求并尽力关闭本机在途连接；外部服务没有停止子进程 API，排版可能继续。重启不自动续发，任务中心禁止通用重试。

实际验证：

- `python -m pytest tests/engine -q`：**230 passed / 1 skipped / 1 warning，61.17 秒**；包含翻译 API、Bridge、代理、迁移与既有阅读功能。最后凭据回显保护后的代理专项 **24 passed**。
- `pnpm --dir apps/desktop check`、`pnpm format:check`：通过；Vitest **7 files / 49 passed**，覆盖最终预检指纹、授权、预算失效、版本隔离、打开、取消和缓存。生产构建通过，保留既有约 542.53KB JS chunk 提示。
- Ruff、mypy **50 source files**、Rust fmt：通过。`cargo test -- --include-ignored` **9 passed / 0 ignored**，包含最终打包引擎的原生 Host 启动和两次握手/停止；安装后的引擎另跑 Host 测试 **1 passed**。
- `lite0005 → lite0006` 迁移测试通过：升级前自动备份，来源、历史用量、外键/数据库完整性和 FTS5 保留；没有对正式库升级作实验。
- `scripts/build-windows.ps1` 完成 PyInstaller 与 Tauri NSIS 构建；最终侧载引擎和隔离安装后的引擎均通过 `scripts/smoke-translation.py --executable ...`。协议测试走实际 HTTP → Bridge → 临时代理 → 合成 Provider → 受管 PDF 下载；每个独立 smoke 中合成调用 **1**，输入 **17** / 输出 **7** / 总 **24** Token，缓存命中 **2**。匿名 PDF 被作为模拟产物返回，**不是实际翻译，也不是本轮真实 Token 用量**。
- `scripts/verify-windows-install.ps1 -Installer ... -ExpectedSha256 ...`：隔离静默安装、schema `lite0006`、默认翻译关闭、匿名 PDF 本地解析通过，导入阶段模型调用 **0**。安装后引擎 SHA 与封存 sidecar 一致。
- `scripts/check-sensitive.py --gitleaks .local/tools/gitleaks-8.24.3/gitleaks.exe`：**262 文件内容/路径扫描通过**；`git diff --check` 通过。本轮不 Commit/Push。

最新可启动安装包：`.local/releases/pdf-translation-20261111/ResearchGraph-Studio-PDF-Translation-0.0.1-x64-setup.exe`，**38,452,244 bytes**，SHA-256 `25983BFC1F5BC182B02CE71A0AAA3A7897652BF25974A3879FEE96BF0B5084A1`。完整 sidecar 在同目录 `researchgraph-engine/`，EXE **15,126,340 bytes**，SHA-256 `D7321D2DA5096260BC9D25634A03B03789936453F1B41004143871BCBEC61365`；必须携带 `_internal/`，不要单独复制 EXE。包未签名，构建与隔离验收材料在忽略目录，不进入 Git。

本轮真实模型调用、真实输入/输出 Token、真实重试与增量费用均为 **0**。没有读取正式 API Key、正式数据库、Zotero 正式库或私人 PDF。**独立外部 Server/引擎尚未实际安装运行**，复杂版面、公式/表格、OCR、字体、实际译文质量、真实 Provider 费用和用户桌面原生体验均未验收；源码与合成协议通过不能替代这些项目。使用步骤见 [文献翻译](pdf-translation.md)，决策见 [ADR0036](adr/0036-optional-pdf-translation-bridge.md)。

## 2026-11-10 · 模型提供商设置重排

设置页的模型配置已按提供商卡片重排：常见的 DeepSeek、OpenAI、OpenRouter、SiliconFlow、智谱 AI、通义千问和本机 Ollama 作为可编辑的兼容接口预设；“自定义模型 API”提供 Provider ID、显示名称、API 地址、当前支持的 OpenAI Chat Completions 协议、API Key 和本地模型目录。一个提供商可以维护多个模型，模型目录保存为现有的 Lite model profile，并可在论文概览模型、章节精读与问答模型中分别选择。

API Key 仍只写入系统凭据存储，模型目录不会自动调用供应商 `/models` 接口；原生 Anthropic 等未接入的协议不在界面中伪装成已支持。Provider ID 当前用于配置表单中的本地标识，连接持久化仍由现有连接名称/Base URL/兼容 provider 字段承担，后续若需要跨设备同步再增加数据库字段。

本轮修改：`apps/desktop/src/ModelSettings.tsx`、`apps/desktop/src/ModelSettings.test.tsx`、`apps/desktop/src/style.css`。前端测试 **6 files / 42 passed**，TypeScript、ESLint 通过；真实 Provider、真实 Token/费用和正式数据库仍未使用。

最终可启动包：`.local/releases/model-provider-settings-20261110/ResearchGraph-Studio-Model-Providers-0.0.1-x64-setup.exe`，SHA-256 `6A09DAA7AE992F02F5278BD7B91F08249B9E562E08FE56F8A456643635F553DB`；完整 sidecar 位于同目录 `researchgraph-engine/`，EXE SHA-256 `1A460FB53316C22817EFCACC93CEA921EC6993EE7A6B9C13D42CFEACAFC72A3D`。sidecar smoke 和最终静默安装隔离验证通过，schema `lite0005`、匿名 PDF 导入成功、`model_calls=0`。

## 2026-11-10 · Lite 信息架构重排

本轮按 ADR0035 将项目页面从“导入论文 / 任务记录 / 项目文献”三段式工作台改为三层结构：左侧项目树负责项目和论文定位；一级导航增加与研究项目并列的“任务记录”；右侧只显示当前论文的论文概览、章节精读和论文问答。项目文献列表不再在右侧重复渲染。

导入论文保留在左侧当前项目操作和项目空状态，继续支持本地 PDF 与 Zotero。论文阅读标题区保留本地分类偏好。全局任务中心读取所有项目任务并显示项目名称、状态、阶段和取消/重试动作；本地解析、模型授权、Token 用量和 `unknown` 语义均未改变。

实际修改包括 `apps/desktop/src/App.tsx`、`Papers.tsx`、`JobHistory.tsx`、`style.css` 与前端测试。前端 Vitest **6 files / 41 passed**，TypeScript、ESLint、生产构建通过。最终 Windows 安装包为 `.local/releases/lite-navigation-layout-20261110/ResearchGraph-Studio-Lite-Navigation-0.0.1-x64-setup.exe`，38,380,988 bytes，SHA-256 `55719fb81c48eaa6c1c4776d293f2667fed8e1b16b6416ce901606191482905d`；sidecar 为同目录 `researchgraph-engine.exe`，15,076,947 bytes，SHA-256 `1a460fb53316c22817efcacc93cea921ec6993ee7a6b9c13d42cfeacafc72a3d`，须与 `_internal/` 同目录。静默安装、sidecar smoke、匿名 PDF 解析均通过，schema `lite0005`，模型调用为 0。当前未 Commit/Push，尚未完成用户原生桌面验收。

## 力导向图谱设计固化

新增 `apps/desktop/src/ForceGraph.design.test.tsx` 作为 LightGraph 力导向引擎设计契约（6 项断言），验证稳定节点 ID 布局恢复、确定性种子、有限坐标、局部力学、固定/拖动/冷却、双语标签、关系语义、相机保存、持久化回调以及不读取证据字段或模型坐标。该测试总结的是实际保留的 `ForceGraph`、`ForceSimulation`、`graphLayout` 与 `graphAppearance` 行为，不代表恢复旧版完整图谱业务。

已建立可复用 Skill：`C:\Users\KLucen\.codex\skills\researchgraph-force-graph`，入口为 `SKILL.md`，详细参数与边界见 `references/engine-design.md`。Skill 明确单篇 PaperCard + LightGraph 的边界：一次联合模型调用、布局与语义分离、同论文同版本才恢复布局、不生成 Evidence/证据字段或模型坐标、不恢复 Query/Lint/Wiki/跨论文推理。

## 清理结果

已完成全项目分类和清理：删除旧安装包、构建输出、数据库/WAL/SHM、日志、实验响应、Python/Node/Rust 缓存、旧 v2/v3 文档归档、旧 Prompt/Schema、完整图谱/Query/Lint/Wiki/Reading/Reasoning 业务代码、旧迁移和对应测试。根目录旧选题说明 `QA.md` 也已移除；必要的 Lite 规范、当前基线、迁移评估、安全说明和匿名 PDF fixture 保留。

活跃工程只保留本地阅读基础、Zotero、PDF/章节/FTS5、Provider/模型配置、任务、用量/缓存和可复用 React Flow 图组件。运行代码和契约中没有指向已删除旧业务的路由或导入；历史完整实现仍可从备份分支恢复。

## Lite 数据边界

新数据库使用 `researchgraph-lite.sqlite3`，当前 Alembic head 为 `lite0010`：保留 Lite 既有迁移链及已撤下翻译的兼容表，新增精读/理解状态、阅读整理和全文笔记。完整旧版图谱、Query、Lint、Wiki、任务与缓存不迁移到 Lite；已有 Lite 数据升级前自动备份，通过加性迁移保留，不重新初始化。检测到完整旧系统数据库结构时会停止并提示使用新的 Lite 数据目录。本轮目录侧栏不增加迁移。

选择 Zotero 论文或导入本地 PDF 后，解析、章节识别、文本块保存和 FTS5 建索引均在本机完成；不会自动排队 PaperCard、A、D 或任何完整知识图谱任务。生成概览必须由用户明确允许一次模型调用；PaperCard 和 LightGraph 共用同一请求，缓存命中不产生新调用。`unknown` 只表示信息或计量缺口，不据此补造实验条件、推断矛盾或把未知费用写成零。

## 前次阅读功能验证记录（2026-11-10）

- 后端：D01 专项 **8 passed**，D02 合约/API 专项 **5 passed**；完整后端回归 **185 passed / 1 skipped / 1 warning**。Ruff、mypy、compileall 和 OpenAPI/TypeScript 契约导出通过。
- 前端：TypeScript、ESLint、Vitest **41 passed / 6 files**，覆盖项目侧栏、论文分类偏好、任务中心、D02 显式授权/关键词展示和本地重检索；生产构建仍保留既有 >500KB chunk 提示。
- Rust/Tauri：已加入 D02 三条白名单路由、模型连接/设置入口和 schema `lite0005` 校验；修复关键词列表路由被通用 QA 详情路由提前匹配的问题，并补齐 `scope=selection|section|paper` 查询校验。`cargo fmt --check` 通过，Rust 单元测试 **7 passed / 1 ignored**（本轮未重复运行缺少 cargo 的环境）。
- Lite 专项：匿名 PDF 两份、章节结构、Chunk/EvidenceSpan、FTS5 正文检索、重启读取和 Provider 哨兵均通过；解析阶段实际调用数、输入 Token、输出 Token、总 Token、重试和增量费用均为 0。
- Windows 交付：当次导航布局安装包为 `.local/releases/lite-navigation-layout-20261110/ResearchGraph-Studio-Lite-Navigation-0.0.1-x64-setup.exe`（38,380,988 bytes，SHA-256 `55719fb81c48eaa6c1c4776d293f2667fed8e1b16b6416ce901606191482905d`）；sidecar 完整目录为同目录 `researchgraph-engine.exe` 与 `_internal/`（EXE 15,076,947 bytes，SHA-256 `1a460fb53316c22817efcacc93cea921ec6993ee7a6b9c13d42cfeacafc72a3d`）。sidecar smoke、直接 sidecar 隔离验证和静默安装隔离验证均通过：schema `lite0005`、匿名 PDF 导入成功、`model_calls=0`。构建产物不进入 Git。
- 论文功能入口修复：选中论文但解析版本尚未写入时，详情页会明确显示本地解析/章节索引等待状态，并每 1.5 秒刷新论文详情；解析版本出现后自动显示章节导读、局部证据问答、PaperCard 和 LightGraph，不再出现“选中论文但页面空白”的状态。
- 本轮未读取正式用户数据库、Zotero 正式库、私人 PDF/批注或真实 API Key，未调用真实 Provider；真实输入/输出 Token、重试和增量费用均为 0。安装包和构建目录位于被忽略的 `.local`/`target`，不进入提交。工作区安全检查与 `git diff --check` 通过；本轮仍未 Commit/Push。

## 下一步

优先建议建设公式原图定位：同 SHA 的登记来源、页码/bbox 与本地受限预览，先保证读到原式；精确公式检测、预览 API 与界面均尚未实现。需要可复制公式时再评估按需局部 OCR → LaTeX 的部署、许可、缓存与不确定性，不恢复整篇 PDF 翻译服务器。方案见 [公式评估](formula-parsing-assessment.md)。

Lite P4 仍需完成真实 Provider/论文质量与费用标定、全部 A/B/D 的统一预算守卫，以及正式 Zotero、用户原生 GUI、干净机和跨平台验证；当前显式段落提问已可传入 selection，复杂 Span 选择体验可继续完善。本地任务与模拟 usage 不代替真实验收。真实调用需另行明确样本与预算，不能自动追加。后续开发以用户下一轮范围为准。

## 2026-11-10 · 设置与阅读工作区调整

- 用量入口已从项目文献页移到设置与诊断，设置页显示全部 Lite 项目的统一账本；原有 unknown 用量仍按未知显示，不按 0 估计。
- 新增 lite0005_model_connections 加性迁移。连接单独保存 Provider、Base URL 和凭据引用；模型 profile 通过 connection_id 复用连接，只保存 Model ID 和思考/采样/超时/JSON 参数。旧 profile 请求仍可兼容，历史任务快照继续冻结完整连接信息。
- 论文选中后显示独立的论文阅读工作区：论文概览（知识卡片 + 轻量图谱）、章节精读、论文问答。概览内继续使用一次联合 PaperCard + LightGraph 请求，布局和图谱交互保持。
- 实际验证：后端 tests/engine 185 passed / 1 skipped / 1 warning；前端 Vitest 39 passed / 6 files，TypeScript 与 ESLint 通过。真实 Provider、真实 Token/费用、正式数据库和桌面原生窗口本轮均未验证；安装包已重建并完成 sidecar/静默安装隔离验证。

## 2026-11-10 · 可交付包修复与最终验证

- 独立 sidecar 必须携带 PyInstaller 生成的 `_internal/` 目录；先前只复制 EXE 会出现 Python DLL 找不到的弹窗。已将完整 sidecar 目录补齐到 `.local/releases/lite-settings-20261110/`，并重新通过 smoke 和直接 sidecar 隔离验证。
- 安装包 `ResearchGraph-Studio-Lite-Settings-0.0.1-x64-setup.exe`：38,396,216 bytes，SHA-256 `0f353b850e94291e1f46272c158b01300d02322df7619f3183d932467d9185cd`。
- sidecar `researchgraph-engine.exe`：15,076,836 bytes，SHA-256 `8d5b4648fb724f55f99d1f79c7e776da8a29d20e4cc48af37c5e7182997e68db`；与 `_internal/` 同目录使用。
- smoke、直接 sidecar 验证和静默安装验证均返回 `result=passed`，health schema 为 `lite0005`，匿名 PDF 导入成功，模型调用为 0。
- Gitleaks 未安装；已完成工作区敏感模式扫描、暂存范围检查和 `git diff --check`。当前仍未 Commit/Push，未读取真实 API Key、正式数据库、私人论文或批注。

## 2026-11-17 · 公式保真预览与安全 LaTeX 显示

本轮针对 PDF 公式被线性化、空方框和上下标丢失的问题完成 Lite 增量闭环。PDF 文本层已经丢失二维结构时，系统不会让通用模型猜公式；解析阶段只生成保守的疑似独立公式候选，保留页码、bbox、原始文本和来源哈希。公式候选 ID 绑定当前 revision、页码、bbox 与原文哈希；旧结构存档在投影时按当前 revision 重算，避免 `unbound` ID 造成预览失配。

新增 `services/engine/researchgraph/formula_api.py` 的候选列表和同 SHA 原始 PDF 校验；`/api/v1/revisions/{revision_id}/formulas/{formula_id}/preview` 返回受限 PNG Base64，兼容 `/image` 路由复用同一页码、bbox、面积和来源校验。Tauri Host 仅放行合法 revision 与 `formula-` + 32 位十六进制 ID。前端 `FormulaDisplay` 使用 KaTeX 渲染明确标记为 `recognized` 的 LaTeX，提供复制 LaTeX、查看公式原图、页码说明和失败提示；`latex_unavailable`、不确定或渲染失败时始终显示原始文本和原图入口。

实际修改涉及 `formula_api.py`、`pdf_structure.py`、`reading_projection.py`、`reading_projection_contracts.py`、Tauri `main.rs`、`PaperCloseReading.tsx`、`api.ts`、公式样式/测试、OpenAPI/TypeScript 契约和公式边界文档。没有安装 OCR 权重，没有把公式识别结果写回原始 Span、知识图谱或论文事实。

验证结果：后端全量 **352 passed / 1 skipped / 1 warning**；公式/解析/投影专项 **73 passed / 1 warning**；前端 **9 files / 87 passed**；TypeScript/ESLint/Prettier、Ruff、mypy、Python compileall 均通过。额外补回归：孤立 `a = b` 正文不再生成公式候选。Rust Host **11 passed / 0 failed / 0 ignored**（使用最终打包引擎路径）；OpenAPI/TS 契约重新导出；`git diff --check` 和 Gitleaks/路径敏感扫描 **328 files passed**。隔离静默安装验证通过，schema `lite0010`、匿名 PDF 本地解析模型调用 **0**。

新的未签名 Windows 安装包：[ResearchGraph-Studio-Formula-Preview-0.0.1-x64-setup.exe](../.local/releases/formula-preview-20261117-final/ResearchGraph-Studio-Formula-Preview-0.0.1-x64-setup.exe)，39,552,322 bytes，SHA-256 `184142B709E0146123CFD7F74D4F741D43C29F5435343B1BAAD75188317A1756`。完整 sidecar 位于同目录 `researchgraph-engine/`，包含 `_internal/`；引擎 15,246,198 bytes，SHA-256 `3BF0E5A26F846D40810CBDB988148188615E15D9C23C96AD42788EE2A3886408`。安装器和运行数据均在 `.local` 忽略目录，不进入 Git。

剩余边界：当前生产解析仍不会自动生成 LaTeX；KaTeX 显示成功只代表语法可渲染。下一阶段需单独评估用户明确点击后的专用图像转 LaTeX OCR、模型权重/许可/CPU 成本、识别缓存失效和分数/根号/矩阵/积分上下限的结构准确率，不增加全文默认模型调用。

## 2026-11-17 · 模型优先导入实现起步

在 ADR0047 设计提交 `0dbd5d2` 推送后，开始实现模型优先导入的增量基础。新增 `ImportSession`、`ImportPlanItem`、`LlmDocumentParse` 和 `LlmDocumentSegment` 的持久层与 `document-parse` API；模型输出经过严格 DTO、章节顺序、公式/表格材料校验后由程序生成正式 ID，旧 `Chunk`/`Section`/`EvidenceSpan` 不被覆盖。PDF/model-first Job 不再进入旧本地解析分支；Provider 只有显式声明 PDF/图像输入和 `chat_file` 传输时才发送文件，能力不足会明确失败，不静默回退本地解析。

补充修复了文档结果桥接接口的 FastAPI `Key` 前向引用、Provider 元数据刷新时丢失文档能力、导入计划项与 Job 的状态绑定。导入卡片新增显式联网授权字段，默认不发送 PDF；公式和表格请求保持强制开启。匿名 fixture/合成响应验证通过，真实 Provider、Token/费用、OCR 权重和用户数据库仍为 0。实际测试见 `DEVELOPMENT_LOG.md` 的 DEV-0103；当前代码改动尚未 Commit/Push。

## 2026-11-18 · 论文管理、旧解析清理与安装验收

导入和新建项目对话框改为视口内模态窗口，内容较长时在窗口内滚动。PDF/Zotero 导入任务状态变化会同步刷新当前项目论文区和左侧个人研究空间，修复论文数量不同步。论文工作区可编辑题名、模型章节正文/公式/表格及成功的概览、精读和翻译结果。

用户可逐篇清理旧本地 Chunk、FTS、EvidenceSpan、DocumentParse、阅读投影和缓存；保留个人笔记/理解状态、已生成内容、模型章节文档、论文记录和源文件。操作前创建并校验 SQLite 在线备份。清理后普通阅读不会重建旧解析；有关联的排队本地任务时拒绝清理，防止旧 worker 再写回。整篇论文删除同样先备份，只删除应用 `attachments` 根目录内经路径核验的托管 PDF，不删除引用 PDF、Zotero 原件或目录链接指向的外部文件，也不删除整个研究项目。用户数据库未被开发或安装测试批量改写；旧数据由用户在应用中逐篇显式清理。

验证：后端全量 **376 passed / 1 skipped / 1 warning**；论文管理 API **5 passed**；桌面 Vitest **10 files / 98 passed**。TypeScript/ESLint、Prettier、OpenAPI/TypeScript 契约导出、mypy **75 files**、Ruff、compileall、PowerShell 5.1 脚本解析与 `git diff --check` 通过。Rust Host 使用隔离安装 sidecar **12 passed / 0 failed / 0 ignored**。新 NSIS 安装器静默安装和 smoke 通过：schema `lite0011`、旧 Chunk 移除 **4**、模型章节材料清理后仍为 **3**、旧阅读存档没有自动重建、论文删除成功、引用源文件保留、模型调用 **0**。

安装包：[ResearchGraph-Studio-Paper-Management-0.0.1-x64-setup.exe](../.local/releases/paper-management-20261118/ResearchGraph-Studio-Paper-Management-0.0.1-x64-setup.exe)，**160,425,045 bytes**，SHA-256 `AB6F20489F884FFEB0DF8F3CA5C76C7655D6551819A39A16623FCB90F931F161`；隔离安装数据位于 `.local/verify/paper-management-20261118-retry1/`，不进入 Git。本轮未使用真实 Provider/模型、正式用户数据库、私人论文或 API Key。真实论文质量与用户桌面 GUI 原生反馈仍待验收。

## 2026-11-19 · IntegrityError 发布状态投影修正

继续复核 2026-11-18 的仅发布恢复后，发现任务仍可能从最后一次边界步骤继承 `current_kind=boundary`，导致最终数据库发布失败被显示为“边界复核失败”。只读投影现会优先呈现可恢复的章节发布阶段；前端显示发布失败/等待/进行中状态，并隐藏不再相关的边界页范围。有效边界兼容恢复仍显示边界阶段，正文批次和边界已通过计数继续保留。新增后端 API 与前端回归。

最终验证：引擎 **579 passed / 1 skipped / 1 warning**；桌面 **15 files / 151 passed**；TypeScript、ESLint、Prettier 通过。PowerShell 7 完整重建安装器；PowerShell 5.1 隔离安装烟测通过，schema `lite0013`、匿名 PDF、模型章节材料/进度、旧内容清理与源文件保留均通过，模型调用 **0**。

最新未签名安装包：[ResearchGraph-Studio-Integrity-Recovery-0.0.1-x64-setup.exe](../.local/releases/document-integrity-recovery-20261119-final/ResearchGraph-Studio-Integrity-Recovery-0.0.1-x64-setup.exe)，**160,512,380 bytes**，SHA-256 `DEE14B90B8911661CCD45C4C91C5BC601DC1137C32E1A9B0085A3EB2A1A8B16D`。隔离安装证据位于 `.local/verify/document-integrity-recovery-20261119/install-smoke/`。历史 IntegrityError 的具体 SQLite 约束仍无法由旧任务追溯；未访问正式用户数据库、未发真实模型请求，未 Commit/Push。真实供应商质量、原生 GUI 与干净机仍待验收。
