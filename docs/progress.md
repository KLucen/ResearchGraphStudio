# 实施进度

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
