# ResearchGraph Studio Lite 独立软件质量审计

2026-11-23（Asia/Shanghai）

## 结论

**当前版适合作为单机受控试用版，尚未达到长期稳定运行的主力科研资料库或面向普通用户发布的成熟度。** 论文导入、本地阅读、带引文卡片、知识地图、跨论文汇报和归档等主流程已有真实实现。限制长期使用的是已复现的授权撤回、任务队列和列表可达性缺陷，以及缺少完整的工作区恢复。测试数量支持核心功能可用，也暴露出当前验收对积累数据、异常时序和发布环境的覆盖不足。

审计对象为 `codex/research-knowledge-library-k1-k3` 当前工作区，基准提交 `f80fd0ba6ae404bcd27a2a5e2a2b79270cbe57bd` 加审计开始时已有的改动。最新 Windows 包记录的 227 项构建输入全部匹配，数据库 head 为 `lite0019`。安装包 SHA-256 为 `29266e55f71f456147394834f4ba18831a662fba2618bf2602c3eecd8dd2fd92`。本次只读审查、在隔离库中执行合成验证和依赖元数据查询，没有修改产品代码、迁移、正式库或调用真实模型。

优先级按产品影响分为 P1 发布阻断、P2 重要缺口、P3 维护改进。证据区分隔离复现、源码确认和待验。未发现本轮实测中的不可恢复生产数据损坏，正式库完整性未纳入实验。

## 八项质量判断

| 维度 | 已核实的能力 | 影响成熟度的缺口 |
| --- | --- | --- |
| 功能完整性 | 本地导入、阅读来源、概览与精读、知识图谱、任务与归档在真实组件或引擎夹具中有可用路径 | 项目论文与全局任务到第 51 条失去常规浏览入口。知识历史恢复也只取第一页运行信息。见 [A04](#a04)。 |
| 潜在 Bug | 已有幂等、状态重启修复和旧批次续接回归 | 写锁异常可停止唯一执行器。取消任务未释放当前执行槽。见 [A02](#a02)、[A03](#a03)。 |
| 软件架构 | Tauri、React 与 FastAPI Sidecar 权限和职责基本清晰。SQLite 写入和模型发布有明确边界 | 单队列同时承担本地、网络及诊断任务。大模块混合 API、队列、校验和发布，IPC 路由与后端接口需要同步维护。见 [A02](#a02)、[A12](#a12)。 |
| 数据与存储 | WAL、外键、迁移备份与事务回滚、归档续清均有回归 | 单库快照无法完整恢复受管文件。论文清除改变历史用量，备份保留边界不清。见 [A05](#a05)、[A06](#a06)。 |
| API 与模型调用 | TLS、来源验证、显式发送、持久请求槽、预算、缓存重验和受控续接已有实现 | 自动联系缺少生效中的授权撤回。取消与供应商冷却反馈不足。引文精确匹配无法判断总结是否受引文支持。见 [A01](#a01)、[A03](#a03)、[A10](#a10)、[A11](#a11)。 |
| UI/UX | 实际工作区通过浅深色、来源切换、报告定位、阅读高亮、归档确认和键盘焦点回归 | 活动状态可能失真。搜索范围与提示不一致。图谱跨标签页可恢复到过时布局，WebView 存储不可用时首页无降级。见 [A02](#a02)、[A04](#a04)、[A09](#a09)、[A16](#a16)、[A17](#a17)。 |
| 性能与资源 | 小库启动已量测。阅读正文具备本地存档和按需读取路径 | 轮询重复扫描汇报和原始模型输出。大图谱计算和每次保存的全量历史对响应和存储造成压力。见 [A07](#a07)、[A08](#a08)、[A15](#a15)。 |
| 安全性与稳定性 | 回环会话、IPC 路由白名单、CSP、系统凭据、源文件选择授权和敏感信息扫描均已核查 | 已排队自动联网仍可发送。PDF 预览路径有资源上限缺口。依赖告警和发布签名缺少闭环。见 [A01](#a01)、[A13](#a13)、[A14](#a14)。 |

## P1 发布阻断

### A01

**自动联系任务入队后关闭联网权限，未发送的请求仍可能发出。** 隔离库用两篇匿名论文实际排入自动分析任务，随后关闭自动联系和允许联网，再执行等待中的任务。测试 Provider 收到 1 次调用，任务保存了汇报。真实网络和费用均为 0。自动入口检查授权，但落盘只保留 `allow_network=True`。执行主要复查冻结授权和预算。同类自动知识提取在发送前另查当前权限。界面已经说明策略只作用于后续事件，所以此项是**授权撤回能力缺口和两条自动路径行为不一致**，不归因于已发请求无法收回。成熟版验收需覆盖已排队任务和多批任务中下一次尚未发送的请求，以及可辨识的撤回提示。 [联系入队](../services/engine/researchgraph/knowledge_connections.py#L1044) · [联系执行](../services/engine/researchgraph/knowledge_connections.py#L885) · [自动提取复查](../services/engine/researchgraph/knowledge_tasks.py#L740) · [授权设置](../apps/desktop/src/ResearchKnowledgeBase.tsx#L1657)

### A02

**队列执行器可因一次数据库写入超时退出，而应用继续报告引擎就绪。** 通过测试同步点把真实 SQLite 写锁放在诊断任务最终持久化前。超时后当前任务停在 `running`，释放锁后下一任务仍停在 `queued`，`/health` 继续返回就绪。重启后前者标为中断，后者成功执行。部分错误发生在单任务异常保护外，启动只创建一个协程且没有运行中监督。应能在不重放已发送模型请求的前提下恢复队列，并在健康诊断中区分 HTTP 服务存活和任务处理可用。 [工作循环](../services/engine/researchgraph/app.py#L236) · [最终写入](../services/engine/researchgraph/app.py#L354) · [执行器生命周期](../services/engine/researchgraph/app.py#L419) · [健康接口](../services/engine/researchgraph/app.py#L563)

### A03

**点取消后，本地任务仍可能等待模型请求结束。** 隔离试验让 Provider 替身保持等待，经正式任务 API 取消，返回 `cancelled`。随后入队的纯本机诊断仍为 `queued`，直到替身返回后才成功。当前只更新任务持久状态，单执行器仍在等待请求。文字活动模式允许有持续进展的请求超过旧总时限，队尾的影响可持续很久。现有保护会抑制被取消结果的发布。验收需区分本机停止等待、供应商可能仍计费和已收到用量的记录，并验证长模型任务不会阻塞本机操作。 [队列调度](../services/engine/researchgraph/app.py#L267) · [取消入口](../services/engine/researchgraph/app.py#L902) · [模型等待](../services/engine/researchgraph/knowledge_tasks.py#L805) · [文字活动时限](../services/engine/researchgraph/providers.py#L442)

### A04

**论文和任务在第 51 条失去浏览入口，活动状态也可能失真。** 匿名库实际保存 51 篇论文及 51 项任务。项目论文 API 首屏返回 50 项和 `next_cursor=50`，第二页可读取较早论文。实际 Edge 工作区的项目树只显示 50 篇，没有加载后续页的操作。任务接口固定取最近 50 项，旧任务的独立接口仍返回 `running`，实际任务页却显示「当前没有进行中的任务」。旧失败任务的本机恢复、归档入口随列表消失。验收需分别验证项目树翻页、全局任务分页与独立的活动统计，并覆盖知识运行恢复信息的第 51 条。 [项目论文 API](../services/engine/researchgraph/app.py#L1085) · [项目树取数](../apps/desktop/src/App.tsx#L510) · [论文工作区](../apps/desktop/src/Papers.tsx#L54) · [全局任务 API](../services/engine/researchgraph/app.py#L610) · [活动统计](../apps/desktop/src/App.tsx#L117) · [任务历史](../apps/desktop/src/JobHistory.tsx#L144)

### A05

**可验证的数据库备份无法恢复完整工作区。** 在隔离库中彻底清除一篇受管论文。生成的备份通过 `integrity_check`，数据库中可读出受管 PDF 路径，但对应应用副本已删除。外部原件若已不可用，数据库恢复只找回路径与库中材料。迁移备份同样只复制 SQLite。未发现统一备份覆盖受管 PDF 与源链接、凭据重绑、隔离校验后恢复的完整入口或演练。长期使用应能从独立快照在另一目录或干净用户环境恢复代表性论文、卡片、引文、图谱及设置，明确外部 Zotero 源缺失和凭据重绑的表现。 [迁移备份](../services/engine/researchgraph/storage.py#L68) · [清除前备份](../services/engine/researchgraph/paper_management_api.py#L193) · [受管文件清理](../services/engine/researchgraph/paper_management_api.py#L447)

## P2 重要缺口

### A06

**论文清除改变既往用量，旧 SQLite 备份仍保留清除前数据。** 匿名回执清除前进入全局 1 次请求、46 Token，清除后这条记录消失。论文清除会级联处理部分 `LiteTokenUsage`、批次和模型输出。任务记录单独清除和知识库匿名账本有独立保留逻辑，不能据此推断所有计量都丢失。备份整库带旧正文和模型响应，归档清除界面未解释备份保留或替应用决定其生命周期。历史计费汇总应能脱离内容保存，备份应有可验证的保留、导出和到期处置策略。 [论文级清理](../services/engine/researchgraph/paper_management_api.py#L330) · [全局统计](../services/engine/researchgraph/lite_usage.py#L131) · [匿名用量模型](../services/engine/researchgraph/knowledge_connection_models.py#L98) · [确认文案](../apps/desktop/src/ArchiveWorkspace.tsx#L14)

### A07

**统计与汇报列表读取成本随正文和历史规模增长。** 汇报后端先取全量再切片，每页回读原始响应和依赖。前端请求全部页，任务活动时轮询，侧栏只需未读数也复用完整数据。2,000 份极简匿名汇报，一次取齐需 10 次 GET、4,010 次 SQL SELECT，相应暖态中位数 1.56 秒，合计约 659 KiB 响应。结果不含浏览器渲染。常规 `/lite/usage` 在 64 份合成输出下，仅增加原始及结构化文本体积就使暖态中位数从 13.53 ms 增到 125.47 ms，Python 跟踪分配峰值从 0.40 MiB 增到 96.36 MiB。知识用量也读完整报告请求和提取运行，200 条和 20 条样本的独立对照为 182.2 ms 与 22.3 ms，跟踪峰值 112.9 与 11.3 MiB。孤立的汇报完整性错误也会连带拒绝正常记录。隔离库内一份汇报缺失运行引用后，列表返回 422，另一份正常汇报的单条接口维持 200。项目树另外对折叠项目每三秒轮询第一页。统计、摘要和证据详读需要各自的查询边界及规模回归。 [汇报查询](../services/engine/researchgraph/knowledge_workflow_api.py#L200) · [汇报轮询](../apps/desktop/src/ResearchKnowledgeBase.tsx#L1898) · [汇报整页获取](../apps/desktop/src/knowledgeApi.ts#L315) · [用量全文查询](../services/engine/researchgraph/lite_usage.py#L415) · [知识用量查询](../services/engine/researchgraph/lite_usage.py#L304) · [项目轮询](../apps/desktop/src/App.tsx#L510)

### A08

**图谱页数上限不能限制节点数，减少动态效果路径仍会长时间占用界面线程。** 当前默认可展开本页 12 篇论文，力计算每步对可见节点两两计算。开启减少动态效果时，一帧同步执行最多 160 个物理步。同机 Node 纯计算暖态微基准，240、600、1,200 节点中位数约 122、737、4,258 ms，七次计算取中位数，无边与 DOM 开销。它证明算法增长和同步路径风险，实际整窗掉帧未测。需要用有边、标签和布局的大图验证拖动、键盘与首帧响应。 [力计算](../apps/desktop/src/forceSimulation.ts#L48) · [减少动态效果分支](../apps/desktop/src/ForceGraph.tsx#L136) · [当前页展开](../apps/desktop/src/ResearchKnowledgeBase.tsx#L416)

### A09

**搜索提示超出实际范围，列表出错容易被误读为空。** 知识库占位提示承诺搜索论文、研究问题与概念，后端该入口只匹配论文题名和备注，单独出现在节点中的术语不会命中。项目侧栏无单独分支表达论文查询失败，失败可能呈现为「暂无论文」。知识条目来源有效时会显示「返回论文阅读」，但来源的所属项目若尚未被项目分页载入，处理函数会静默返回。三项均可从源码确定，影响日常查找和错误自助诊断。 [搜索提示](../apps/desktop/src/ResearchKnowledgeBase.tsx#L2167) · [实际过滤](../services/engine/researchgraph/knowledge_library_api.py#L191) · [项目树状态](../apps/desktop/src/App.tsx#L598) · [阅读跳转处理函数](../apps/desktop/src/App.tsx#L402)

### A10

**有精确引文的关系总结仍可能给出无据结论。** 在匿名测试中保持两侧引文合法，在比较和摘要加入来源中不存在的「提升 900%」与全任务一致性判断。合同接受了这些字段。已显示 AI 分析标记且保留原始材料，精确定位真实有效。该测试表明结构与定位门槛没有验证比较语句的科学支持度。适合阅读线索使用，核心结论仍需双侧证据、数值核对和可重复的真实样本验收。 [对照字段校验](../services/engine/researchgraph/knowledge_connections.py#L255) · [汇报重验](../services/engine/researchgraph/knowledge_connections.py#L644)

### A11

**Provider 限流信息未形成明确的等待反馈。** 文本请求对 HTTP 429 识别数字形式的 `Retry-After`，置入异常字段，没有找到业务层读取后将冷却提示写入任务状态的路径。用户可以显式重试，但缺少稳定的何时可重试和本次是否可能计费的反馈。应验证限流、连接超时、响应中断和供应商未知用量在各类任务中的一致处理，同时保留显式授权与发送账本。 [限流解析](../services/engine/researchgraph/providers.py#L536) · [异常字段](../services/engine/researchgraph/providers.py#L49)

### A13

**公式原图路径先读取全部文件，之后才检查大小与 SHA。** 本地 PDF 导入已采用上限读取和可结束子进程。公式预览 `_registered_pdf` 对登记路径使用 `read_bytes()` 后再应用 50 MiB 约束，若登记文件已被换成大文件，读取和内存分配发生在拒绝之前。公式候选检查和裁图在 Sidecar 进程内调用 PDF 库。裁图区的面积有上限，降低输出放大。此项是源码确认的可用性和隔离强度缺口，未构造恶意 PDF 或进行资源耗尽探测。 [公式读取与校验](../services/engine/researchgraph/formula_api.py#L471) · [裁图限制](../services/engine/researchgraph/formula_api.py#L515) · [导入子进程](../services/engine/researchgraph/ingest.py#L265)

### A14

**依赖处置和发布身份尚未形成闭环。** OSV 查询覆盖锁文件中 59 个 PyPI、395 个 npm、479 个 crates.io 包版本，分别有 2、4、7 个包版本匹配至少一条公告。计数包括构建、测试及非 Windows 的可选依赖，未将公告匹配当作应用可利用性。发布包包含 Pillow 12.0.0 和 OpenTelemetry API 1.45.1，锁文件版本与公告范围匹配。Pillow 当前使用路径为本机裁出的公式图，未证实公告的特定图像格式通路。未发现应用主动使用 OpenTelemetry 入站追踪解析的调用。Windows Rust 正常依赖保留 `url` 2.5.8，未证实公告路径可达。npm 匹配项未出现在桌面生产依赖树中。CI 有 Windows 构建、安装及隔离数据验收，但未发现产物 SBOM、公告门禁和签名校验。当前安装器与旧包仍共用 `0.0.1`，本机 Authenticode 状态为 `NotSigned`。建议将公告按产物和调用面判定，建立唯一制品版本及签名升级验收。 [依赖锁](../requirements-win-64.lock#L621) · [Windows CI](../.github/workflows/phase0.yml#L22) · [Pillow 公告](https://github.com/advisories/GHSA-22hg-r758-rrw9) · [OpenTelemetry 公告](https://github.com/advisories/GHSA-mf5v-w3w3-f6cg) · [RustSec 公告](https://osv.dev/vulnerability/RUSTSEC-2026-0592) · [OSV 查询合同](https://github.com/google/osv.dev/blob/master/docs/api/post-v1-querybatch.md) · [Microsoft 发布签名说明](https://learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation)

### A15

**普通图谱保存会累计整份坐标的幂等响应。** 保存层使用新幂等键，并同时保存当前图谱布局与完整历史响应。隔离测试以 2,000 个坐标变更视口 50 次，产生 1 行当前布局和 50 行幂等记录，后者仅 JSON 就占 8,862,090 bytes。该数字未计入索引和 WAL。未找到适用于这类高频布局响应的独立淘汰策略。长期验收需验证回放语义，并量化同一知识库日常拖动后的数据增长。 [桌面保存请求](../apps/desktop/src/knowledgeApi.ts#L378) · [地图保存路由](../services/engine/researchgraph/knowledge_library_api.py#L397) · [通用幂等记录](../services/engine/researchgraph/knowledge_library_api.py#L70)

### A16

**图谱布局存在桌面载荷边界不一致和标签页缓存回退。** 后端接受至多 2,000 个坐标，Rust 将通用 IPC 请求体限制在 64 KiB。以 36 字符版本 ID 和小数坐标组成的普通 600 点夹具，紧凑 JSON 为 76,549 bytes。引擎对 2,000 点的隔离保存实测成功。由宿主上限可判断上述载荷会被拒绝，未通过原生宿主发送该大载荷。保存失败有画布下方提示，但内存位置会在确认前改变。另在真实 Edge 组件中，取消固定并缩放已经保存，从联系汇报切回地图仍显示旧位置与固定状态，重载页面后才显示当前结果。原回归只覆盖重载。验收需同时走原生大载荷保存、标签页往返和查询缓存更新。 [前端布局保存](../apps/desktop/src/ResearchKnowledgeBase.tsx#L349) · [失败提示](../apps/desktop/src/ResearchKnowledgeBase.tsx#L732) · [坐标合同](../services/engine/researchgraph/knowledge_library_contracts.py#L124) · [宿主大小限制](../apps/desktop/src-tauri/src/main.rs#L729) · [图谱初始化](../apps/desktop/src/ForceGraph.tsx#L93)

### A17

**WebView 本机存储异常时，应用壳可能无法挂载。** 浏览器测试模拟 `localStorage` 访问抛出 `SecurityError`，实际应用入口出现未处理异常，根节点为空。外观偏好有读取失败回退，主应用的首次侧栏偏好读取仍可阻断启动。此项是隔离异常条件复现，日常 WebView 未出现该故障。成熟版应在偏好不可用时仍显示应用与诊断入口。 [初次读取](../apps/desktop/src/App.tsx#L49) · [应用挂载](../apps/desktop/src/main.tsx#L10) · [外观初始回退](../apps/desktop/public/appearance-init.js#L2)

## P3 架构与维护

### A12

**功能边界清楚，运行与展示内部仍有大范围耦合。** `model_document_api.py` 约 2,776 行，聚合请求、批次账本、验证、发布和路由。`ResearchKnowledgeBase.tsx` 约 2,634 行，包含地图、筛选、报告、配置和轮询。Rust 的手工 IPC 路由允许列表有实际安全价值，同时给 OpenAPI、客户端与宿主带来同步责任。迁移、旧协议、授权和发布状态相互依赖，适合先建立跨版本契约验证再拆职责。发布说明也需单一来源，根 README 的新版卡片说明与下方旧 LightGraph 条目仍同时存在。 [模型文档 API](../services/engine/researchgraph/model_document_api.py) · [知识库页面](../apps/desktop/src/ResearchKnowledgeBase.tsx) · [宿主路由限制](../apps/desktop/src-tauri/src/main.rs#L260) · [产品说明](../README.md)

## 防护与验证证据

### 功能和数据回归

- 本轮重跑 pytest **1,019 通过、1 跳过**。跳过原因为本机无法创建文件符号链接，另有一条 Starlette 使用 `httpx` 的弃用提示。React **256 通过**。Edge 首轮 **60 通过、1 项图谱夹具加载超时**，完整重跑 **61 通过**。Ruff、mypy（120 个源码）、前端类型、ESLint、Prettier 通过。现行 OpenAPI 的 111 条路由和独立生成的 TypeScript 均与仓库快照一致。Rust Host **19 通过**，含包内引擎连接与重启。
- 现有发布包解出的引擎通过本机导入、归档、标题、阅读与清理烟测。独立 WebView2 测试宿主实测外观重启记忆、系统媒体模拟、深色弹窗和键盘焦点。两个路径分别使用隔离数据和独立应用 ID，未运行日常安装器覆盖安装。
- 有效防护包括 SQLite WAL、外键、受限只读会话、事务与迁移备份，持久请求槽与缓存重验，以及原始响应和引用分开存储。请求认证使用回环、每次启动的令牌和 Origin 拒绝。宿主校验允许的路由与载荷约束，PDF 入口有原生选择授权。Windows Credential Manager 保存密钥，正常入口只用 HTTPS 或显式回环，供应商请求禁止跟随重定向。CSP 已配置。 [存储初始化](../services/engine/researchgraph/storage.py#L17) · [认证](../services/engine/researchgraph/app.py#L441) · [文件选择](../apps/desktop/src-tauri/src/main.rs#L552) · [凭据实现](../services/engine/researchgraph/credentials.py#L25) · [模型传输](../services/engine/researchgraph/providers.py#L511) · [CSP 配置](../apps/desktop/src-tauri/tauri.conf.json#L14) · [Tauri CSP 指南](https://v2.tauri.app/security/csp/)

### 性能与安全核查

- 同一台 Windows 主机，包内引擎进程启动至完成认证的 HTTP 健康响应，四组初建空库和对应重启中位数分别为 **1.67 秒**与 **1.57 秒**。采样时父引擎工作集约 **136–138 MiB**，未覆盖宿主、WebView、子进程或重度任务。汇报、用量和图谱数据为隔离合成规模样本，详见 A07–A08。
- Gitleaks 扫描 **564 个工作区文件**与 **55 个本地历史提交**，没有发现匹配泄漏。范围不含正式库、凭据管理器内容和运行时日志。数据库、备份和原始模型输出存放在本机文件系统，其机密性仍依赖 Windows 用户权限、磁盘及备份介质保护。
- 未验收干净机安装、常规覆盖升级、整库备份恢复、长时间满负载、显存和整机峰值内存，以及跨供应商费用和语义质量。依赖公告、程序集签名和运行路径已核查到上述范围，未进行入侵或漏洞复现。测试结果不包含产品当前付费或真实论文科学准确率。

## 成熟度验收门槛

1. **授权与队列**：关闭联网后未发送的自动请求为零。取消立即结束本机等待。一次锁冲突或意外任务异常后，后续本机任务仍能完成，真实执行器状态可诊断。重启和补救不自动重发已出网请求。
2. **可达与恢复**：论文、任务、运行历史随规模增长可完整访问。将备份恢复到隔离的新目录，核对受管 PDF 指纹、卡片、笔记、图谱、任务和用量。包括磁盘不足、原件移除、升级中断与回滚。
3. **大库与科学质量**：围绕实际目标库规模记录启动、查询、轮询、首屏、内存和长会话指标。对代表性合成和真实论文分别检查结构、引文、数值、适用条件和比较语义。真实调用需要单独预算与授权。
4. **可维护发布**：签名及版本可辨识，保留依赖物料与处置记录，覆盖干净机、上版覆盖、回滚、托盘和原生弹窗。README、接口、安装包和验收记录指向同一发行版本。

本报告记录问题与验收条件。本轮没有实施修复、安装、提交或推送。
