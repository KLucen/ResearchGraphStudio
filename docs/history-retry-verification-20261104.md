# 历史抽取错误与续接结果反馈修复（2026-11-04）

本轮处理用户报告的 `items.1.Claim.kind_note_unused (extra_forbidden)` 和点击“继续未完成批次”无反馈。仍P3/R5，不进入下一Phase；未调用真实模型或写入正式用户库。

## 实际定位

使用SQLite只读模式检查任务状态及额外字段类型，不输出私人论文标题、原文或模型响应。该错误来自旧P02v2历史任务：原任务失败、执行3次、已保存31/34批；字段精确为Claim上的JSON null。其独立P02v3续接任务已于2026-11-03成功完成34/34批并发布图谱。历史错误没有代表当前文献仍抽取失败。

后端再次点击原任务会幂等返回同一个已成功后继，避免重抽和重复付费。原界面只invalidate任务历史，丢弃返回Job；原历史行仍失败，且没有实际操作结果反馈，造成“无响应”。既有null限定兼容已生效，不需要放宽Schema或删除历史记录；非null、其他kind或其他未知字段仍拒绝。

## 处理与验证

`JobHistory.tsx`显示操作提交中、实际返回状态与“查看续接结果”，同步列表和单任务缓存；不在当前分页的后继单独可见，进行中每1.5秒读取现有单任务GET，终态停止定时。刷新失败保留上次结果并提示；已完成后继明确无需重复抽取，`ranking_status=pending`仍显示核心排序待完成。写操作结果前取消该任务在途GET，防止迟到的旧running覆盖已返回的cancelled；失败提示不暗示尚未执行或未产生费用。保留原失败记录及原raw，不自动重排已完成后继，历史分页cursor不改。`api.ts`复用既有GET路由，无新增后端路由或数据库变更。接口边界同步[API说明](api.md)及[目标接口说明](07_api_and_events.md)。

`test_reading_upgrade.py`补充离线旧计划/失败raw回归，覆盖精确null兼容、零抽取调用复用、成功后使用两个新幂等键点击原历史任务仍返回同一成功后继、原任务/raw/状态/结果保持。与`test_reading_unused_note.py`共17项通过；没有付费调用。新增10项前端回归，覆盖进行中反馈、完成/失败/未完成排序、分页外轮询及停止、刷新失败、拒绝、旧queued缓存覆盖和在途GET取消竞争，任务历史共32项通过。

使用Anaconda `researchgraph-studio`绝对解释器和现有脚本执行，日志保存在忽略的`.local/claim-note-retry-20261104/`：

| 实际命令 | 结果 |
| --- | --- |
| `python -m pytest tests/engine/test_reading_upgrade.py tests/engine/test_reading_unused_note.py -q` | 17 passed，离线自造旧响应 |
| `pwsh -NoProfile -File scripts/check-phase0.ps1` | 625 Python passed/2 skipped；初轮88 React；Ruff、154文件格式、mypy83源文件、依赖、契约、前端静态与构建通过 |
| `pnpm format:check`、`pnpm check`、`pnpm test`、`pnpm build:web` | 最终两项前端修正后全部通过，90 React（任务历史32项） |
| `pwsh -NoProfile -File scripts/build-windows.ps1` | PyInstaller/Tauri/NSIS成功，退出0 |
| `python scripts/smoke-engine.py --executable apps/desktop/src-tauri/binaries/researchgraph-engine-x86_64-pc-windows-msvc.exe` | 最终冻结引擎通过；独立数据/无真实模型 |
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-windows-install.ps1 -EnginePath <冻结引擎绝对路径> -PdfFixture <tests/fixtures/pdf/two-pages.pdf绝对路径> -OutputRoot <独立新目录>` | Windows PowerShell 5.1，17项通过，子进程PATH仅System32 |

保留既有httpx弃用及前端大chunk提示；两项本机文件链接权限跳过，不冒充干净机。后端运行代码和图谱未变，本轮不重复图谱浏览器/Rust测试，上一轮结果不作本轮成绩。无Alembic迁移，head0011/领域1.0/入口不变。

## 安装包与操作

安装器保存在本机`.local/releases/history-retry-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,710,564字节，SHA256 `d5320ac80159fca0ead50da3298c5f7e52352f226cc733126a62aba2bbbad34c`。冻结引擎SHA256 `1879c766f393f6716ad83e7b9ca4aa594a5a69caa886b45ba13071b3d0c101d5`与上轮相同，前端更新；旧包保留。

退出当前软件后安装此包，打开原项目的任务记录，点击原失败行的“继续未完成批次”；应显示“此前的续接任务已完成，无需重复抽取”，并提供“查看续接结果”，对应34/34成功任务。若后继已在历史列表中，直接显示关联和结果入口。旧错误保留，不需删除知识或重新抽取。本轮没有替用户安装/卸载，原生反馈待用户确认。

## 限制

本轮证明这条历史错误已有成功后继，不代表已完成所有论文科学质量验收。R5真实P13/已知语义无支持与上标误读、strict及干净机仍按原记录；四份登记外部补充原文路径不可用。用户新包反馈单独记录；不修改私人材料、Zotero/Obsidian、来源PDF或旧知识，不提交或推送。

收尾：554个源码候选文件通过路径规则和Gitleaks内容扫描；165 Markdown/637本地链接/88清单资产LF哈希通过，四份登记外部原文不可用独立记录。`git diff --check`通过，暂存区为空，最终包与构建源长度/hash一致；交付清单及本轮回归/构建/冻结/PS5.1/安全/文档结果仅本机配对保存。没有Commit/Push或远端CI。
