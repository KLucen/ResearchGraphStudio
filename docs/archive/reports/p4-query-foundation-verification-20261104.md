# P4-Q01～Q04 实施与验收 — 2026-11-04

本轮先按授权将 R5 源码、测试及实际验收提交并推送至 main：`80552d3`，随后开发 Query 四项基础任务。Query 增量尚未再次 Commit/Push。没有调用真实模型或升级正式用户数据库；全部迁移、权限故障和解析篡改使用独立合成数据。

R5 的[远端 CI](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41778202007) 全部成功，包括 Windows 回归/真实 Edge 图谱/打包和独立安装验收。公开状态与 artifact 元数据已留存本机；匿名日志返回 403，未声称下载远端日志或安装 artifact。以下本轮 Query 成绩与该次 R5 CI 区分。

## 已实现

| 任务 | 实际实现 |
| --- | --- |
| Q01 契约/存储 | 项目级 QueryRun/QueryModelRun/回答版本预留；严格请求与保存命令；最小文档版本/段落/依赖/文件登记；审计不推进科学图版本；Alembic 0012 加性迁移 |
| Q02 索引 | 当前合法候选、双语/别名、题名、原文/表格、有效文档和用途授权笔记；可重建 FTS5 与精确召回；来源/类型先过滤；默认不读私人笔记 |
| Q03 图谱召回 | 文本/Wiki根种子→完整合法结论支撑；共享成员与科学跨篇关系重验；四态条件与保守比较；独立于画布分页/隐藏/核心选择 |
| Q04 上下文 | 版本/坐标/hash/章节/表格与根依赖 manifest、请求短编号、完整组容量检查及重放；原文没有正式 span 时只读引用 Chunk，不造知识 |

实现决策见 [ADR0022](../../adr/0022-query-foundation-and-versioned-context.md)。本轮没有新增问答页面、模型回答或保存回答功能；这些仍为 Q05～Q07。

实际代码文件集中在 `services/engine/researchgraph/`：新增 `query_contracts.py`、`query_models.py`、`query_documents.py`、`query_retrieval.py`、`query_graph.py`、`query_context.py`、`query_api.py` 和 `migrations/versions/0012_query_foundation.py`；调整 `app.py`、`integrations.py`、`knowledge_api.py`、`knowledge_store.py`、`storage.py`。宿主修改 `apps/desktop/src-tauri/src/main.rs`，契约同步 `packages/contracts/openapi.json` 和 `generated.ts`；`scripts/smoke-engine.py`/`verify-windows-install.ps1` 补冻结检查/当前 head。新增六个 `tests/engine/test_query_*.py`，四个既有兼容测试仅同步当前 head 断言；README/AGENTS、docs 00–03/05–09/API/导航/续接/计划/进度、ADR0022、开发日志和规范清单同步。

## 接口

- `POST /api/v1/projects/{project_id}/query/search`：本地召回、理由、图谱路径与条件。
- `POST /api/v1/projects/{project_id}/query/index/rebuild`：重建派生索引。
- `POST /api/v1/projects/{project_id}/query/prepare`：幂等冻结来源/检索/上下文，需 Idempotency-Key。
- `GET /api/v1/projects/{project_id}/query/runs/{query_id}` 及 `POST .../validate`：权限和来源实时终验后读取/重放。
- `GET /api/v1/projects/{project_id}/query/documents`：只读内部文档与逐段状态。
- `PUT /api/v1/integrations/obsidian/{root_id}/query-permissions`：独立授权本地/模型用途；后者默认关闭。

项目必须与路径一致。body 包含 question、paper_ids/document_version_ids、source_kinds/knowledge_kinds、include_personal、purpose 和 limit；正常产品没有 Mock 选择器。OpenAPI 与生成 TS 同步，原 P0～P3 API 保持。

## 数据、安全与已修复缺口

0011→0012 在合成旧库比较全部旧表列/行、来源、raw、任务签名；升级前一致性备份与二次启动单备份检查。旧 ModelRun 单篇约束不重建，新增项目级执行记录避免跨篇任务错误归属。Query/笔记授权扫描仅审计，不改变科学知识、关系、选择、布局或 GraphRevision。

独立复核先复现解析 hash/schema/原文/坐标/缺失表头引用 5 类负例，以及 cell 引用/负索引/行列/跨度越界 7 类负例；修复后统一拒绝或标不足。只命中单行也补完整表头与全部单元格，没有为查询新建 EvidenceSpan。Wiki-only 命中能回到根结论和条件，原文/Wiki/综合同根不增加独立来源数。

文档测试覆盖一段失效其余保留、内部有效但文件缺失/外改、草稿不召回、循环/跨项目拒绝、撤权穿透缓存与 Wiki、模型用途默认关闭、BOM/还原历史笔记及默认不打开私人文件。内容状态与文件基线状态分开；当前没有 P5 渲染或可靠发布，in_sync 不代表 Markdown 与内部正文已作语义等价验证。

最终复核补齐 Tauri Query/用途授权的精确白名单、方法/UUID/参数与 Unicode 请求大小检查；宿主统一拒绝非单斜杠本地路径，堵住 URL 拼接成为外部 authority/userinfo 的风险。prepare 新快照冻结同 Provider 的已登记有效容量，精确端点/模型才适用，未知保持未知，端点更低上限保留；配置与历史快照不变，没有额外能力探测。

## 实际执行

统一使用 Conda `researchgraph-studio` 解释器。

```powershell
pwsh -NoProfile -File scripts/check-phase0.ps1
& C:/Users/KLucen/anaconda3/envs/researchgraph-studio/python.exe -m pytest tests/engine/test_query_documents.py tests/engine/test_query_migration.py tests/engine/test_query_graph.py tests/engine/test_query_retrieval.py tests/engine/test_query_security.py tests/engine/test_query_tables.py -q
pwsh -NoProfile -File scripts/build-windows.ps1
& C:/Users/KLucen/anaconda3/envs/researchgraph-studio/python.exe scripts/smoke-engine.py --executable apps/desktop/src-tauri/binaries/researchgraph-engine-x86_64-pc-windows-msvc.exe
$env:RGS_TEST_ENGINE_PATH = (Resolve-Path apps/desktop/src-tauri/binaries/researchgraph-engine-x86_64-pc-windows-msvc.exe).Path
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml packaged_engine_connects_through_native_host_and_restarts -- --ignored
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/verify-windows-install.ps1 -EnginePath apps/desktop/src-tauri/binaries/researchgraph-engine-x86_64-pc-windows-msvc.exe -PdfFixture tests/fixtures/pdf/two-pages.pdf -OutputRoot .local/p4-q01-q04-20261104/powershell-verified
```

`scripts/check-phase0.ps1` 退出 0：**734 Python passed、2 skipped，90 React passed**；Ruff/168 文件格式/mypy 91 源文件、依赖、OpenAPI/TS 契约、前端静态检查及生产构建通过。随后新增有效容量冻结与原生路由补丁，最终六个 Query 文件 **113 项通过**（其中检索 36 项，含 4 项新配置用例），Ruff/mypy 通过；Rust fmt/clippy `-D warnings`、**11 项单测及 1 项冻结宿主测试通过**。没有将交叠专项累加冒充全量数量。第一次检查因来源筛选的 list 型变错误停止，改为只读 Sequence 后通过。已有 Starlette/httpx 弃用、大 chunk 提示与本机符号链接权限两项跳过保留。

最终 PyInstaller/Tauri/NSIS 构建退出 0；冻结引擎 smoke 验证 Query 幂等 prepare、终验、零科学写入及重启读取，并回归旧导入/抽取/选择/图谱/任务。生产 Host 两次握手启动/停止通过。Windows PowerShell 5.1 的 EnginePath 模式以 System32-only 子进程 PATH、自造 two-pages.pdf 与全新隔离目录验证 **17 项通过**。首次命令被本机脚本执行策略拒绝，未运行脚本；改用仅该进程的 `-ExecutionPolicy Bypass` 后通过，未改变系统策略。不执行安装器、不启动正式桌面库，不冒充干净机安装或用户反馈。前端运行代码未变，本轮不重复真实浏览器回归，80552d3 的远端 R5 结果另列。

Q03 固定 6 题对照文本种子与图扩展，覆盖条件、结果/指标、多跳、限制、共享支撑、转述归属；121 节点的完整合法闭包不被旧 100 节点/3跳限制截断。Q04 大于 48K 原文保留、已知容量不足保留完整组并标不足、双篇证据及变更/假引用负例通过。以上为确定性本地成绩，不是模型回答的科学准确率。

## 安装包与留存

最新安装器：`.local/releases/p4-query-foundation-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe`，**38,717,661 字节**，SHA256 `55fb899ea2c603cb4488a7b98c0cea4c6fe97bc0826f785df71adeea4ca406c2`。冻结引擎 SHA256 `7cbe885e3e11b09131fa7d74a4f363ce1f6c59ca890abe6eeace1074b6bc8c2a`。副本与构建源逐字节 hash 一致，源码指纹、delivery.json、最终回归/构建/冻结/宿主/PS5.1 日志存忽略目录，不进源码。

这是带 head0012 和 Query 基础接口的开发交付包，没有新增问答页面；用户当前 R5 已验收安装版与本包区分，本包原生界面及正式库升级没有替用户执行或记为通过。

最终安全与文档核验：571 个源码候选的路径/内容及 Gitleaks 通过；168 Markdown、662 本地链接、88 项规范资产 LF 哈希通过。S1–S4 四份外部补充原文登记路径仍不可用，不计作链接回归或原文核验通过。git diff --check 通过、暂存区为空，HEAD 与 origin/main 都是 80552d3；Query 新增量仍在工作区。实验目录、运行库、模型快照和安装器忽略边界已核对，没有进入源码上传。

## 限制与下一步

P07/P08 未执行，真实 Query 模型质量、完整 24 题 P4 基准及1万候选/2万正文性能仍在 Q05～Q08 计划内；不以 R5 两次真实排序验收代替 Query 验收。无向量检索、外网补证据、问答 UI、用户保存综合或 Wiki 发布。

PDF OCR/复杂版面、真实 strict、跨平台/干净机以及 S1–S4 四份外部补充原文仍未核验。用户正式数据库、原 PDF、Zotero 和私人笔记未被实验改写。后续从 Q05 开始，本轮止于 Q04。
