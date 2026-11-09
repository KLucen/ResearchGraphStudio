# ResearchGraph 当前项目基线

更新日期：2026-11-09（Asia/Shanghai）
基线提交：`9ef8cde`（`main`，当前远端 `origin/main` 同步）
范围：重构前的 ResearchGraph Studio 现状审计。本文只描述当前仓库和已保存的验收证据，不把 Lite 设计包中的目标写成已实现功能。

## 1. 项目定位与技术架构

ResearchGraph Studio 当前是一个本地科研论文阅读与知识组织桌面应用。原设计目标是“论文 → 候选知识 → 论文级整合/选择 → 知识图谱 → Query/P5 文档工作流”；现有工程已经包含这一整条较重的链路。它采用以下技术栈：

- 桌面宿主：Tauri 2 + Rust。Rust 负责窗口、Sidecar 启动、会话令牌和受限 IPC，生产页面不能直接访问任意 HTTP 地址，也没有通用 Shell/文件权限。
- 前端：React 19、TypeScript、Vite 7、TanStack Query、React Flow、Lucide；测试使用 Vitest、Testing Library 和已安装 Edge 的 Playwright。
- 本地引擎：Python 3.12、FastAPI、SQLAlchemy 2、Alembic、SQLite（WAL、FTS5 和单写入者约束）、Pydantic v2、httpx。
- 文献处理：PyMuPDF 子进程解析 PDF；结构解析器为跨页章节、文本块、定位框和可恢复表格结构提供本地索引。当前无 OCR，也不保证复杂公式和复杂多级表格语义恢复。
- 模型访问：`ConfiguredProvider` 使用 OpenAI 兼容的 HTTP/SSE 协议，模型配置和 API Key 引用由设置模块管理；正常产品入口不提供 Mock，Mock 只用于显式测试和历史兼容。
- 打包与运行：Conda 环境 `researchgraph-studio`；PyInstaller 打包 Python 引擎，Tauri/NSIS 生成 Windows 安装器。契约由 Python/Pydantic 生成 OpenAPI，再生成 `packages/contracts/generated.ts`。

主要目录如下：

| 目录 | 当前职责 | 状态 |
| --- | --- | --- |
| `apps/desktop/src` | React 页面、项目/文献、图谱、Query、Lint/Wiki、设置和来源管理 | 已实现，正在作为旧产品壳运行 |
| `apps/desktop/src-tauri` | Rust 宿主、Sidecar 握手、IPC 和安装运行配置 | 已实现 |
| `services/engine/researchgraph` | FastAPI、SQLite 存储、PDF/结构解析、模型、阅读图谱、Query、Lint/Wiki、Zotero | 已实现，但模块范围较大 |
| `services/engine/researchgraph/migrations/versions` | Alembic `0001`–`0020` 加性迁移 | 已实现，当前 head 为 `0020` |
| `packages/contracts` | OpenAPI 与 TypeScript 契约 | 已实现，需和后端同步生成 |
| `scripts` | 开发、构建、契约导出、smoke、Windows 隔离验证和敏感扫描 | 已实现 |
| `tests/engine` | Python 后端、迁移、来源、阅读、Query、P5 和兼容回归 | 已实现 |
| `docs` | 当前设计、ADR、API、进度、验证报告和归档历史 | 已实现；部分旧文档仍需随 Lite 迁移更新 |
| `docs/researchgraph_lite_ABD` | 用户提供的 Lite A+B+D 设计包、参考契约、虚构样例和 P0–P4 迁移规范 | **仅设计包，尚未接入工程** |

`services/engine/README.md` 仍保留早期 Phase 0 的“PDF、模型、证据审核、Wiki 尚未实现”描述；该文件已落后于当前代码，不能作为当前功能状态依据。本基线以当前源码、迁移和最新验证报告为准。

## 2. 已完成、部分完成和仅设计的功能

### 已实现并有自动化验证的功能

- 项目创建、Job 历史、幂等键、任务状态和本地单写入者数据库。
- 本地 PDF 导入和 Zotero 入口；来源文件版本、SHA-256、页数、解析器版本和来源状态持久化。
- PDF 文本块、页码、坐标、跨页章节和结构化表格材料的本地解析与证据定位。
- 论文候选抽取、证据白名单、来源版本校验、KnowledgeStore 事务写入、原始模型响应保留和失败恢复。
- 阅读知识流程：P02 分段候选抽取，P12 语义关联/重复建议，程序组建阅读单元，P13 贡献排序和默认图谱选择。
- 图谱投影、论文/核心结论/支撑知识展示、候选检索、布局保存、拖动/固定/缩放等交互。
- Query 本地检索、完整合法支撑路径扩展、来源回查、P07 有据问答、回答历史和明确保存回答。保存回答是确定性写入，不额外生成 P08 模型内容。
- P5 确定性 Lint、依赖索引、影响闭包、问题生命周期和只读 `repair_plan`。普通扫描、依赖重建和处理方案展示本身不调用模型。
- P09/P10/P11 工作流接口、Wiki 草稿/版本/保存、受管 Markdown 发布、局部更新和文件状态诊断。
- OS 凭据引用、模型用途授权、个人来源选择、论文/用户/外部材料归属分离、敏感内容扫描和迁移/重启/幂等回归。

### 已实现但尚未完成真实产品验收的功能

- P02/P12/P13 的真实科学质量只在有限论文和有限调用中验证，不能推导为全文准确率或跨学科质量保证。
- P09/P10/P11 目前只有本地 HTTP/SSE 合成 Provider 回归；尚无真实模型 Token 和逐段科学质量验收。
- 真实 strict Schema API、跨模型/跨平台、干净机安装、复杂公式/多级表格、无 OCR 限制和四份登记外部原文仍未闭环。
- 最新安装器的用户原生升级、扫描、目录选择、发布和重启反馈仍需用户实际操作确认。
- 当前 `docs/progress.md` 和部分历史说明保留了开发阶段语境；重构前基线应作为 Lite 迁移的单一事实记录。

### 仅有设计或尚未接入的功能

- `docs/researchgraph_lite_ABD` 中的 ResearchGraph Lite A+B+D：A 章节式 AI 导读、B 极简论文卡片、D 限定范围证据问答，以及相应的精简契约、缓存和计量设计，当前均未接入现有应用。
- Lite 的默认零 LLM 解析模式、论文/章节级缓存、统一 Model Usage 页面和 Lite 模式开关，当前尚未实现。
- Lite 设计明确不把完整图谱、跨论文推理、全量 Lint/Wiki 作为单篇论文必经步骤；这是迁移目标，不代表旧功能已经删除或停用。

## 3. 核心模块、数据库 Schema、API 与主要流程

### 核心模块

- `app.py`：FastAPI 应用、生命周期、迁移、健康检查、项目/Job/论文/来源 API 注册。
- `storage.py`：SQLite 引擎、WAL/query-only 读会话、迁移入口、数据库路径和连接约束。
- `models.py`：项目、Job、事件、幂等、论文、附件版本、来源、Chunk 等基础 ORM。
- `knowledge_models.py`、`graph_models.py`、`reading_models.py`：知识节点/证据/关系、图谱投影、阅读单元/成员/选择。
- `ingest.py`、`pdf_structure.py`、`section_planner.py`：PDF 子进程解析、章节结构和抽取分批规划。
- `unified_extraction.py`、`unified_store.py`：P02 候选 DTO 校验、来源/证据终验和知识写入。
- `reading_finish_semantic.py`、`reading_ranking.py`、`reading_pipeline.py`：P12/P13 语义整合、贡献排序、阶段恢复和发布。
- `query_context.py`、`query_retrieval.py`、`query_answers.py`：Query 上下文冻结、检索、P07 请求和答案读取。
- `lint_service.py`、`lint_dependencies.py`、`p5_workflows.py`、`p5_execution.py`：确定性 Lint、依赖闭包、P09/P10/P11 工作流和执行槽位。
- `wiki_store.py`、`wiki_publish.py`：Wiki 文档版本、段落依赖、受管文件发布和恢复。
- `providers.py`、`model_settings.py`、`model_capabilities.py`：Provider、模型快照、能力和用量记录。
- `zotero_batch.py`、`integrations.py`：Zotero Local API、条目/附件/批注读取和个人来源边界。

### 主要数据库表和迁移

当前 Alembic 迁移为 `0001`–`0020`，遵循加性迁移，不覆盖旧数据。基础表包括：

- `projects`、`jobs`、`knowledge_events`、`idempotency_keys`：项目、异步任务、审计事件和幂等响应。
- `papers`、`attachment_revisions`、`paper_sources`、`chunks`：论文、PDF 字节版本、来源路径/模式和原文块。
- `evidence_spans`、`sections`、`document_parses`、表格结构表：证据偏移、章节、解析器版本和结构化材料。
- `knowledge_nodes`、`node_evidence`、`source_assertions`、`knowledge_operations`、`graph_revisions`、`graph_layouts`：候选/发布知识、证据关联、科学/导航关系、幂等操作和图谱投影。
- `model_runs`、模型配置/能力快照和任务阶段表：模型请求、原始输出、参数、输入/Prompt/Schema 哈希、usage、失败与恢复。
- `reading_units`、`reading_members`、选择/偏好表：论文级整合单元、成员、默认图谱选择和显示偏好。
- Query 表：冻结上下文、检索/执行记录、答案、保存回答、注释、移除状态和衍生引用。
- P5/Wiki 表：`lint_runs`、诊断、依赖边、文档版本/段落、Wiki 根授权、发布操作和外部文件检查。

迁移 `0020` 只为 Lint 阶段/耗时和三组查询索引增加列/索引，不改旧科学列、targets、input hash 或 raw。Lite 迁移应继续采用加性策略，不能删除或重写这些旧表。

### 主要 API

- 基础：`/api/v1/health`、项目、Job、论文、来源导入/检查/定位。
- Zotero：`/api/v1/integrations/zotero/browse`、批量导入和项目导入历史。
- 阅读/图谱：论文选择、知识单元、候选、重建和显示偏好。
- Query：`/query/search`、`search/page`、`index/rebuild`、`prepare`、执行/校验、答案、保存/注释/移除和衍生图。
- Lint/依赖：文献范围、扫描、报告、issues、推进/取消、依赖重建和正反向依赖查询。
- Wiki/P5：页面、根授权、保存、发布/恢复/文件检查；P5 prepare、history、generate 和 materialize。
- 原生桌面接口：Rust 宿主只代理受限引擎通信，前端使用生成契约和 Tauri IPC。

### 主要工作流程

1. **导入论文**：本地 PDF 或 Zotero 条目 → 读取路径/附件/批注元数据 → 子进程解析 → SHA-256 与 `AttachmentRevision` → `Chunk`/章节/表格结构 → `EvidenceSpan`/FTS 索引。
2. **旧版完整建图**：P02 按章节/批次抽取候选 → 严格 DTO、来源和证据校验 → P12 读取整篇候选与引用证据提出关联/重复 → 程序形成阅读单元 → P13 读取全部单元与证据做贡献建议 → KnowledgeStore 发布图谱选择。
3. **Query**：本地检索/完整支撑路径扩展 → 冻结 manifest、来源和权限 → P07 生成有据答案 → 程序校验引用/条件/布局风险 → 用户明确保存时确定性写入衍生知识。
4. **P5**：确定性 Lint 生成报告 → 依赖重建和影响闭包 → 用户显式准备 P09/P10/P11 → 单独模型槽生成建议/主题/段落变更 → 程序校验并 materialize Wiki → 单独授权发布 Markdown。

## 4. Zotero、PDF、Provider 与 Knowledge Engine

### Zotero

`zotero_batch.py` 和 `integrations.py` 使用 Zotero Local API 读取 collection、条目、附件位置及高亮/文字批注；不直接读写 Zotero SQLite。Zotero 附件是只读权威来源，ResearchGraph 记录来源和版本，不默认复制完整 PDF。无法唯一匹配批注锚点时会显式标记，不能把批注当作者原话。

### PDF 与章节解析

`ingest.py` 在子进程中调用 PyMuPDF，当前限制为本地可读 PDF、最多 300 页、50 MiB、提取文本最多 200 万字符；保存输入字节 SHA-256、页/块坐标和解析警告。`pdf_structure.py` 记录跨页章节树、行/块定位、表头/行列/单元格及合并关系。References 和页眉页脚保留但不进入默认抽取；无 OCR，扫描 PDF、复杂表格、公式语义需人工回查原文。

### LLM Provider

`ConfiguredProvider` 通过 OpenAI 兼容 HTTP/SSE 发送 system Prompt、结构化用户 JSON 和生成 Schema，支持 documented/requested/disabled output policy、JSON object/native JSON schema、模型能力/上下文窗口/输出上限和有界超时。每次请求保存 `prompt_tokens`、`completion_tokens`、`total_tokens` 和供应商提供的 `reasoning_tokens`；reasoning 已包含在 completion/total 时不能重复相加。失败 raw、请求参数、finish reason、输入/Prompt/Schema 哈希和恢复槽位保留。

### Knowledge Engine

KnowledgeStore 是统一写入边界。P02、推理、阅读图谱、Query 保存、Lint、Wiki 和来源事件都通过 Store 或其专用 mutation 进入同一事务；证据写入前执行版本、偏移、quote、文本哈希、坐标和章节归属校验。科学图修订和 Query/P5 审计事件分开，后者不推进科学图版本。稳定 ID、幂等键、源快照和事件审计用于恢复；旧 ModelRun/raw/知识行不因新协议静默覆盖。

## 5. 当前已知问题、未完成任务与技术债务

### 产品和验收未闭环

- P09/P10/P11 没有真实模型 Token 和逐段科学质量实测；P5 软件流程接入不等于真实科学验收完成。
- 新包用户原生升级、扫描、授权目录、发布和重启反馈尚未确认；strict API、跨模型/平台和干净机验收未完成。
- 复杂多级表头、公式、图示和扫描 PDF 仍受无 OCR/启发式结构恢复限制；四份登记的外部原文仍不可用。
- 当前完整图谱协议输入量大，旧任务需要多阶段上下文和较高模型能力；对普通研究生阅读任务偏重。

### 工程债务

- 旧 P0–P5、R5、Query、Wiki 和兼容协议共存，模块、契约、迁移和前端状态复杂；`services/engine/README.md` 等早期说明已过时。
- 生成 OpenAPI/TypeScript 契约、运行 Prompt、Schema 和历史兼容 DTO 需要同步，容易出现版本漂移。
- SQLite 单写入者、WAL/query-only 读会话和长批处理需要持续验证锁竞争与恢复；完整 catalog 扫描仍是 Lint 主要耗时。
- Provider 能力和费用由供应商决定；目前记录 Token，但没有通用费用估算或跨供应商统一价格模型。
- 现有自动化测试大量覆盖协议与合成 Provider，不能替代真实科学质量、不同论文类型和真实用户工作流。
- 当前主分支已推送重构前的 P5 版本，但 Lite 设计目录仍是未接入的设计包；后续必须在新分支增量迁移，不能重建工程或删除旧数据。

## 6. 当前 LLM 调用流程与 Token 消耗原因

### 当前调用链

- **P02**：按完整跨页章节/段落或表格组分批发送原文块、表格结构、Prompt、Schema；每批输出多种候选类型和证据引用。章节越多，调用次数越多。
- **P12**：一次发送该论文全部有效候选、候选 payload、完整引用证据和已有关联，模型只提出语义关系/重复建议，但输入是全篇级别。
- **P13**：一次发送全部程序形成的结论单元、支撑内容、论文上下文、根/支撑疑点和数字排版上下文；共享支撑会在不同结构中再次出现。
- **P07**：问题上下文由程序沿完整合法支撑路径、候选、原文和表格证据扩展后发送；默认不是只发送屏幕上显示的几个节点。
- **P09/P10/P11**：按所选范围收集全部合法材料；P11 即使只更新一段，也会带完整来源上下文和目标段落基线。

### 主要原因

1. 同一原文/证据在 P02、P12、P13 及后续 Query/P5 中重复作为输入。
2. 全篇候选、支撑、问题、表格和布局被一次性纳入完整上下文，缺少按需最小化上下文。
3. 每次请求都携带系统 Prompt、输出 Schema、协议规则和结构化 JSON 包装。
4. P02→P12→P13 是多阶段模型链路，失败、格式修复和有限重试会增加调用量；成功批次虽然可复用，但首次构建成本仍高。
5. 结构化输出和中英文语义字段增加输出量；高推理配置会让 completion 中的 reasoning 比例上升。

已有真实账本只能作为量级证据，不能当作当前全链路单篇固定值：

- P13v3 两篇一次成功分别为 87,907 和 188,792 Token，合计 276,699。
- P07v3 两次合计 317,171 Token，平均约 158,586/次。
- P02/P12/P13 的旧研发账本混有失败、旧协议和未知用量；没有一份干净的“当前单篇完整建图”总账，因此不能简单除以论文数。
- P09/P10/P11 目前只有本地合成 HTTP/SSE 验证，没有真实 Token 实测。

## 7. Lite 版本的复用、停用和迁移边界

### 可直接复用

- Tauri/Rust 宿主、React 页面壳、项目和论文选择、Tauri IPC、Sidecar 启动与安全握手。
- Zotero Local API 适配、附件路径读取、批注元数据导入和来源授权边界。
- PyMuPDF 子进程解析、PDF SHA-256、`AttachmentRevision`、`Chunk`、章节结构、表格结构、`EvidenceSpan`、FTS5 和本地索引。
- SQLite/Alembic/WAL、单写入者、Job/事件/幂等/源版本/文件状态和 KnowledgeStore 事务边界。
- Provider 设置、OS 凭据引用、模型能力快照、实际 usage 采集和 `ModelRun` 审计结构。
- Query 的局部检索、证据引用白名单、来源定位、回答保存和原文/AI/个人观点归属规则。
- 现有测试、契约生成、构建脚本、敏感内容扫描和旧数据只读访问。

### Lite 默认停用或移出必经流程

- 默认关闭 P02 全量候选抽取、P12 全篇语义关联、P13 全单元贡献排序。
- 默认关闭跨论文推理、全量语义 Lint、P09/P10/P11 和 Wiki 自动生成/局部维护。
- 不删除旧图谱、旧 ModelRun、旧 Query、旧 Wiki 或旧迁移；旧数据保持可读，只有显式进入旧功能时才使用旧链路。

### Lite 目标流程的初步映射

| Lite 能力 | 旧工程复用 | 新增/改造 |
| --- | --- | --- |
| A 章节式 AI 导读 | Section、Chunk、EvidenceSpan、Provider、ModelRun、Job | 新的最小章节上下文和导读缓存 |
| B 极简论文卡片 | Paper、Revision、Section、证据定位、Provider | `PaperCard` 结果与论文级缓存 |
| D 按需证据问答 | 局部 Query 检索、来源回查、回答保存、Provider usage | 限定范围上下文、最小 QA 契约和按需扩大范围 |
| 本地默认零调用 | PDF/章节解析、FTS、Job、缓存 | Lite 模式开关和禁止自动调模型的入口保护 |
| Token/费用统计 | ModelRun/provider usage | 统一论文/章节/动作级 Model Usage 视图 |

Lite 迁移的首要原则是：选择论文后先完成本地解析和章节索引，默认 LLM 调用次数为 0；用户明确点击生成卡片、章节导读或证据问答后才产生模型调用。`unknown`、来源定位、作者/AI/个人归属和失败账本继续保留。

## 8. 基线结论

当前工程不是空白项目，而是一个功能完整、协议和历史兼容边界较多的 P5 版本。直接在 `main` 上删减会增加旧数据和回退风险。建议后续严格采用：

1. 将本文件和当前完整工程作为备份分支的基线。
2. 从备份分支创建独立 `refactor/researchgraph-lite-p0`。
3. 先增加 Lite 模式和本地零调用路径，再逐步停用高成本默认流程。
4. 继续让旧图谱和旧 API 可读，不做破坏性删除或数据库重建。
5. Lite P0 完成后只验证本地解析、章节索引、0 次 LLM 调用、旧数据可读和桌面启动；不提前实现 P1–P4。
