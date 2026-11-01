# v1 → v2 工程审计与最小迁移方案

日期：2026-11-01（Asia/Shanghai）。审计起点：`18b4598`；新版三份设计文档是主要依据，设计版本不等于已发布软件版本。本次范围截止新版 P2，不重做 P0，不实施 P3–P6。

## 审计证据

- 工作区：用户新增 `docs/01_product_design.md`、`02_development_plan.md`、`03_knowledge_schema_and_prompts.md`、参考 prompts/schemas/tests/examples；删除旧计划入口 `docs/development-plan.md`。保留这些变更，不初始化项目。
- 检查 `models.py`、`storage.py`、`app.py`、`ingest.py`、`source_files.py`、`workspaces.py`、0001–0004 迁移、React Papers/SourceFiles/JobHistory、Tauri 宿主白名单与打包/验收脚本。
- 实跑 `pwsh -File scripts/check-phase0.ps1`：45 Python passed、1 skipped，16 React passed；Ruff/格式/mypy/pip check/契约导出/TS/ESLint/Web build 通过。日志 `.local/v2-baseline-check.log`。保留既有 Starlette/httpx 弃用提示。
- 实跑 Conda 环境绝对解释器 `python -m pytest docs/tests -q`：5 passed。参考契约只是设计 DTO，不是运行中的服务。
- 正式应用数据目录以 SQLite `mode=ro` 读取结构/计数：Schema 0001，1 project、1 job，尚无 papers 表。未读取私人正文，未运行生产迁移；所有开发验证使用临时测试数据。
- 当前 shell 的 `cargo` 不在 PATH；通过既有环境脚本定位工具链后补测，不将命令不可用记作测试通过。

## 已实现且可复用

| 功能 | 代码/真实边界 |
| --- | --- |
| Tauri 2 + React/TS、鉴权 FastAPI Sidecar | 一次性 token、loopback、宿主路由白名单、启动/退出、PyInstaller、Windows CI；无须重做 P0 |
| SQLite/Alembic | 0001–0004、事务、外键、迁移前 SQLite backup；FTS5 能力探针，不等于已有全文检索 |
| PDF 引用/托管导入 | PyMuPDF 独立子进程、hash、内容去重、附件修订、来源检查/重新定位、旧文本保留 |
| 原文块 | Chunk UUID、版本 FK、零基页号、页标签、bbox、原始文本；不是语义段落/完整章节解析 |
| 任务管理 | 有界串行 worker、阶段、取消/重试/重启、稳定历史分页、安全暂存回收 |
| 事件/幂等 | knowledge_events 已保存项目/PDF/来源事件；idempotency_keys 可复用，不新建第二份事件库 |

## 已实现但需调整

- `Paper` → Paper，`AttachmentRevision` → DocumentVersion 兼容映射；不重复建文献/版本表。PaperSource 保留原路径语义，Zotero 身份新增单独映射。
- Chunk 文本保持原样；证据采用明确的 identity-v1 规范文本、Python Unicode 字符偏移和文本哈希，避免假称完成连字/断词映射。整块 bbox 只表示块位置。
- 新增保守的 Section 索引，标题无法判断时保留页级结构和 unresolved。模型 P01 只能分类已有 ID。
- 旧 `verified` 单轴设计已更新为来源验证与人工审核双轴；现库尚无旧 Claim，因此不把任务状态或来源检查状态迁成 accepted。
- 现有 Event 增加可空 actor/model/revision 字段，旧事件原样保留；KnowledgeStore 成为新知识对象/审核/证据的唯一事务入口，旧来源生命周期继续通过现有服务维护。
- 宿主白名单、Schema health、生成契约、打包资源和安装脚本同步更新；保留旧 endpoint 与字段。

## 新版要求但尚未实现（审计起点）

无 Zotero API/批注适配器、ObsidianReader、EvidenceSpan、章节语义、LLM Provider、ModelRun、知识对象/审核表、知识卡片、证据高亮。既有界面只有块文本显示；不能按旧计划勾选认定证据定位已完成。

## 数据与 API 增量

计划新增 0005：sections、evidence_spans、zotero_links、annotations、authorized_roots、note_snapshots、knowledge_nodes、node_evidence_links、knowledge_dependencies、graph_revisions、model_runs、review_decisions、knowledge_operations。Concept/Method/Experiment/Condition/Metric/Finding/Claim 共享带类型与可查询状态/条件列的节点表和经过 DTO 校验的 payload；不提前创建 Relation/Wiki 空表。

新增版本结构/证据读取、抽取 Job、知识列表/详情/历史、人工审核、模型配置/运行、Zotero只读浏览/批注导入、授权笔记扫描 API。沿用 `/api/v1` 与旧 PDF/来源/任务 API；精确契约以同步后的 OpenAPI 为准。

## 风险与保守处理

1. 生产旧库仍为 0001：先测试 0001/0004→新 head、迁移失败回滚和备份完整性；不直接升级用户数据库作实验。
2. PDF 更新保持旧版本与 Evidence 不变，新版本单独索引；不得改变已有知识引用。
3. LLM 输出不可信：限制证据白名单/局部引用、quote/offset/hash 校验、服务端 ID、事务原子写入、幂等与 revision 冲突；数值/归属疑点待审核。
4. 已接受内容不得被重抽取覆盖；模型原始结果、每次调用和人工修订历史分别保留。
5. Zotero 坐标不保证对应解析文本：只有唯一且可验证的匹配才落锚，其余 unresolved；不读取/写入 Zotero SQLite。
6. Obsidian 仅原生选择器授权目录，拒绝目录逃逸和 reparse/symlink；只读快照不自动进论文抽取上下文。
7. 真实模型未配置时默认明确标识 Mock；不能用离线 fixture 证明真实模型科学质量。未知真实 Zotero/真实模型/干净机环境记录待验收。
8. S1–S4 旧补充原文登记路径此前缺失，当前不作为恢复原文的假证明；以新设计与仓库历史记录推进。

## 实施顺序与验证

1. 审计、ADR、AGENTS/进度基线；保留用户设计包与现有源码。
2. 加性迁移、DocumentVersion 映射、Evidence/Section、只读 Zotero/Obsidian Adapter；旧 P1 回归。
3. 严格 DTO、统一 KnowledgeStore、证据/归属/数值校验、事件/revision/审核。
4. P01/P02、Mock 与明确配置的真实 Provider、调用日志、取消/失败/重试/幂等。
5. Paper & Reading 接真实 API，证据回查、卡片、修改/接受/驳回与历史；独立数据演示及重启持久化。
6. 全部格式/类型/单元/集成/契约/Rust/打包 smoke、可行的原生验证；检查敏感内容/文档链接/远端，普通提交推送并跟进 CI。实际结果记录 `docs/progress.md` 和开发日志；P2 后停止。
