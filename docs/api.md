# 本地接口（Phase 1 首轮）

版本：0.0.1 开发增量；协议：1；Schema：0002。Pydantic 为单一来源，生成文件为 [OpenAPI](../packages/contracts/openapi.json) 与 [TypeScript](../packages/contracts/generated.ts)。本页只描述已实现接口。

## 连接和权限

Tauri 启动随安装包分发的 Python 引擎，通过私有 stdin 传入随机会话令牌。引擎绑定系统分配的 `127.0.0.1` 端口，迁移与 FTS5 检查成功后输出就绪信号；宿主核验协议和 Schema。令牌不进入前端、命令行或日志。React 只能通过 Rust `engine_request` 的方法/路径白名单调用 API；不存在通用 URL、shell 或文件访问命令。

所有 HTTP 请求（包括 OpenAPI）需要 `Authorization: Bearer <session-token>`；带 Origin 的请求拒绝，Host 受限。生产包 CSP 不允许前端直接访问任意 HTTP 地址。会话令牌不保护同一操作系统账号下能够读取进程内存的恶意程序。

## 接口

| 方法与路径 | 行为 |
| --- | --- |
| GET `/api/v1/health` | status、version、protocol_version、schema_version、database（ready）、fts5 |
| GET `/api/v1/projects?cursor=0&limit=50` | items、next_cursor；当前 cursor 是偏移量，limit 为 1–100 |
| POST `/api/v1/projects` | name（去空白后 1–120 字符）、description（最多 4000）；201 返回项目 |
| GET `/api/v1/jobs` | 最近 50 个任务 |
| POST `/api/v1/jobs` | 当前只接受 `{"kind":"diagnostics"}`；202 返回任务 |
| GET `/api/v1/jobs/{id}` | 获取任务；不存在返回 404 |
| POST `/api/v1/jobs/{id}/cancel` | 取消 queued/running 任务 |
| POST `/api/v1/projects/{id}/papers/import/pdf` | path、mode=reference/managed；202 返回持久化 PDF Job。仅原生 import_pdf_file 选择文件后提交，普通桥不开放此路径 |
| GET `/api/v1/projects/{id}/papers?cursor=0&limit=50` | 项目文献分页 |
| GET `/api/v1/papers/{id}` | 文献、全部已保存附件修订和来源路径；路径是登记记录，不保证当前可读取 |
| GET `/api/v1/revisions/{id}/chunks?cursor=0&limit=50` | 不可变文本块、0 起始页索引、page label、块索引与 bbox |
| POST `/api/v1/jobs/{id}/retry` | failed/interrupted/cancelled 重排队；最多执行 3 次 |

所有 POST 必须带 8–120 字符的 `Idempotency-Key`。相同操作/标识/内容返回首次保存的响应，不重复写入；同标识不同内容返回 409。任务响应可能是首次提交时的状态，应再次查询取得最新状态。项目列表按创建时间降序，当前偏移分页在并发插入时可能重复；Phase 1 若增加持续导入，应换成稳定游标。

输入校验、业务冲突和鉴权失败返回 `error: {code, message, retryable, request_id}`。未知底层异常可能返回通用 500，由宿主转为连接/无效响应错误；不把数据库堆栈或原始输入作为用户提示。

## 持久化和恢复

Windows 默认数据位置为 `%LOCALAPPDATA%\com.researchgraph.studio`，以设置页实际显示路径为准。`researchgraph.sqlite3` 保存 projects、jobs、events、idempotency、papers、paper_sources、attachment_revisions、chunks 和 Alembic 版本；项目创建、PROJECT_CREATED 事件和幂等记录在一个事务中提交。PDF 结果、来源、文本块、PDF_IMPORTED 事件和任务成功状态也在一个事务中提交。当前尚无科研主张审核，后续 Review/KnowledgeEvent 不得省略或用运行任务状态替代。

仅引擎写数据库，文件锁防止多个引擎同时打开同一工作区。SQLite 启用外键、5 秒 busy timeout 与显式事务。迁移既有数据库前使用 SQLite backup API 留存快照；失败迁移回滚，禁止自动降级。恢复备份应先退出应用，并同时保留故障文件；用户恢复界面将在后续阶段实现。

诊断任务实际执行 quick_check、外键检查和 FTS5 临时表检索。单 worker 串行执行；取消阻止结果回写，但不能抢占已开始的短时 SQLite 检查。启动将上次 running 改为 interrupted，queued 恢复执行。PDF Job 使用单独子进程，取消/正常退出终止解析；50 MiB、300 页、200 万字符、120 秒上限。Job payload 保存重试参数，JobView 仅暴露 project_id 和任务结果。重试需人工触发。模型任务尚未实现。

关闭宿主 stdin 会通知引擎退出，宿主正常退出最多等待 5 秒再终止子进程；宿主崩溃时管道 EOF 同样触发引擎退出。启动日志位于数据目录的 engine-startup.log，令牌不写入该文件。
