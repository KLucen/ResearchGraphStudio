# 本地阅读存档与数据库忙提示修复验证

日期：2026-11-16（Asia/Shanghai）。范围：Lite 增量修复，沿用 `lite0010`、`reading-document-2` 与原模型协议，不新建阶段。

## 原因与行为

已有完整本地阅读存档，但普通 GET 仍重新组装投影，并经普通 Session 申请 SQLite 写锁。已有笔记的过期检查也经过这条路径；论文与任务等读取同样可能竞争写锁。前端没有自动调用 PDF refresh，普通打开也没有自动重新解析 PDF。不能凭截图确定当时具体持锁任务。

修复后普通打开使用只读快照，先核对来源、Span/坐标、章节、布局、存档哈希和 DTO，再直接读取已保存视图。首次或旧存档缺少新校验字段时只从保存的原文构建；退出读快照后零等待尝试短事务归档，忙时仍显示正文，下次读取补存。乐观发布拒绝覆盖更新后的存档；显式 refresh 的外部 PDF 扫描移到写事务前，发布时重验版本和 SHA。原始块、历史结果、状态与 Zotero 附件不改，真实模型调用/Token/重试/费用均为0。

界面新增“重新读取本地存档”，只 GET 正文与已有笔记，失败后不必重新整理。正文已读取而笔记失败时保留正文；有实际整理时间才显示“上次本地整理”。

## 实际代码

- `reading_projection.py`：受来源完整性保护的存档快路径、`PreparedReadingDocument`、只读准备/条件发布、Span 坐标校验。
- `reading_document_api.py`：读快照、非阻塞可选归档、显式刷新前置扫描与来源重验。
- `storage.py`：可选归档专用零等待选项，其他写入维持原超时与串行策略。
- `paper_reading_api.py`、`app.py`、各 Guide/QA/状态/概览/A02/A03/关键词/用量/设置 API：已审计的纯 GET 使用 `query_only` 保护；不改变模型生成与保存事务。
- `app.py`：静态关键词路由优先于问答ID路由，完整应用关键词 GET 不再误命中404。
- `PaperCloseReading.tsx` / CSS / 测试：读取重试、就绪状态及实际整理时间。
- 新增 `test_reading_archive.py`、`test_read_concurrency.py`；保留上一轮缺章与目录树未提交修改。
- 新增 `scripts/smoke-reading-archive.py`：实际独立引擎持写锁读取与源文件缺失后的重启验证。

## 自动化实际结果

- 后端全量 `python -m pytest -q`：**342 passed / 1 skipped / 1 warning，66.68秒**。skip为既有Windows符号链接权限；warning为既有Starlette/httpx弃用。
- 存档专项13项覆盖真实文件WAL、持写锁暖/冷GET、首次归档、旧存档升级、进程连接重建、原PDF缺失、损坏视图/原文/Span坐标/布局失效、乐观竞争、显式刷新、扫描无写锁与扫描中版本变化。
- 实际完整应用并发专项3项：7条基础读取及19条阅读/笔记/模型配置/用量读取，在持有未提交写事务时均成功读取提交快照；笔记保持COMPLETED，读取不改变Job/Usage/Cache数量或暖投影行。只读会话拒绝写入，后续正常writer仍可写。
- Ruff、94文件格式、mypy64源、pip check通过。前端TypeScript/ESLint/Prettier通过；React **9 files / 86 passed，11.94秒**，含新增3项读取失败恢复；Edge **13 passed，11.2秒**。

本轮全量结果包含前次章节树改动，不把前次326后端或83React当本轮结果。测试只使用匿名/合成材料与隔离库，未对正式库实验，未读取真实Key。

## 安装交付

PowerShell7完整PyInstaller/Tauri/NSIS构建通过，114个运行源码/配置SHA前后保持。生产JS单包592.08KB提示与PyInstaller可选模块警告保留。PowerShell5.1隔离静默安装通过，265个sidecar文件逐一SHA匹配、桌面EXE存在，schema仍lite0010，旧翻译404且无translation-runtime；未覆盖日常安装。

未签名安装包：`.local/releases/lite-reading-cache-20261116/ResearchGraph-Studio-Lite-Reading-Cache-0.0.1-x64-setup.exe`，**38,569,335字节 / 36.78MiB**，SHA256 `D7576F3C24DA07830C9BB3A1C8F42659F178897AEE168CF7473C3F00285E2EDC`。同目录完整sidecar含`_internal`，引擎EXE15,226,267字节，SHA256 `45C95D7C5E45879700B6C70332D1CD2481A306842ADCC7394043A358FAECCA47`；不能只复制引擎EXE。

安装后普通引擎/A02+A03/A04 HTTP/SSE smoke通过。A02+A03合成46输入/82输出/128总Token，A04合成23/41/64；各缓存新增请求0、重试0、非loopback请求0、匿名PDF字节保持。合成用量只验证账本，费用未知，不是真实论文成本。

新增存档smoke的源码模式与安装引擎模式均通过：实际首次GET持久化3段匿名正文，独立SQLite writer持锁时7条HTTP读取不变；停止引擎并删除脚本自己生成的PDF后，同一隔离数据重启，存档全文/hash/行时间保持。模型调用、Token、Usage行及新模型任务全0。没有删除用户PDF。

安装引擎原生Host测试 **11 passed / 0 ignored，2.84秒**，含实际启动/重启、路由与错误脱敏；Rust fmt/clippy通过。未用正式库启动GUI，不宣称用户原生界面或干净机已验收。构建、安装、各smoke和源/包清单在忽略目录`.local/verify/reading-cache-20261116/`。

最终源码内容/私人路径规则及Gitleaks323文件通过；9个改动文档/101个本地链接均存在，diff检查通过，暂存为空。114个运行源码/配置与打包清单仍相同。没有Commit/Push或远端CI运行。

## 使用与限制

安装新包后正常选择已有论文即可读取本地内容，无需删库、重新导入或再次生成AI笔记。临时读取失败用“重新读取本地存档”；需要更新标题/图表定位时才使用“重新整理本地阅读版面”。旧存档首次打开自动补校验字段，不会因这次归档优化改变科学投影或收费。原版面发生实际变化时旧笔记仍可能过期。

本地存档保存文字、结构与定位，不是完整PDF副本；查看原始图片和重新扫描仍需要Zotero原文件。长时间独占维护、损坏或磁盘权限问题仍可能影响读取。公式/OCR、真实论文笔记质量、真实成本、用户GUI和干净机仍待验收。无新的Push授权，未Commit/Push。

设计边界见 [ADR0045](adr/0045-persisted-reading-archive-and-read-transactions.md)，当前状态见 [progress](progress.md)。
