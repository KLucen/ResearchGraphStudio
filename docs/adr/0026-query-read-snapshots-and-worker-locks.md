# ADR0026：Query只读快照、任务认领与数据库锁错误边界

日期：2026-11-04（Asia/Shanghai）
状态：已采用；实际验证和安装反馈分别记录于[本轮报告](../archive/reports/query-history-lock-verification-20261104.md)。

## 问题

用户打开本地问答历史时收到“本地服务返回了无效响应”。实际宿主脱敏日志显示SQLite `database is locked`。原连接事件为所有事务执行`BEGIN IMMEDIATE`，因此纯读取历史也申请写锁；工作器即使没有排队任务，空轮询同样申请写锁。同步等待锁还可能占用异步事件循环，使其他请求和任务状态更新被一并延迟。数据库异常缺少统一JSON错误时，桌面桥只剩“无效响应”，掩盖了具体故障类型。

修复必须保留既有原文、Query/模型原输出、回答、科学知识及保存数据，不能通过清库、重建工程、取消来源终验或重发模型请求消除症状。

## 决策

### 区分只读快照与写事务

SQLite连接启用WAL，保留默认FULL同步耐久策略、外键和5000毫秒busy timeout，不使用降低同步等级来换取成功。WAL使读取可使用已提交快照，不等于允许多个并发写入者或保证永久无锁等待。应用工作区单引擎锁及迁移前SQLite backup API继续保留；活动数据库及其WAL状态不能用只复制主文件的方式替代一致性备份。

新增`read_session(engine)`，使用独立执行选项`sqlite_readonly`、`autoflush=False`、`PRAGMA query_only=ON`和deferred `BEGIN`。连接归还池时恢复`query_only=OFF`，写事务开始时也明确关闭只读保护。只读会话既不申请IMMEDIATE写锁，也不能因隐藏flush或意外写语句污染数据；不能从同一个只读事务直接升级写入。

仅已审计的八个Query路径切换到该只读会话：读取准备记录、显式validate、文档读取、问答历史、回答读取、保存列表、保存详情和衍生图。它们继续核验项目、来源、依赖和当前用途授权，不能为减少锁竞争而返回失效缓存。`search`、`search/page`及索引重建仍需同步派生索引；prepare、generate入队、save、批注和移除仍有持久化写入，继续使用`BEGIN IMMEDIATE`及原事务/幂等规则。此决策不将所有GET或全部引擎路径笼统改成只读。

P07等待模型期间的`_active`取消/任务状态检查同样只读，不再每100毫秒申请写锁；原发送账本、超时、取消规则及最多两槽保持，状态轮询不会重新调用模型。

### 工作器先探测再短事务认领

空轮询先以只读快照查找最早queued任务，无候选时不创建写事务。有候选后，使用新的短IMMEDIATE事务重新读取并确认其仍为queued，再将状态、stage和attempt一起提交。取消或其他认领在两步之间先发生时，原候选不被再次执行。

工作器的认领及诊断执行/完成持久化通过`asyncio.to_thread`离开事件循环，不让SQLite同步busy等待阻塞所有异步服务。认领发生锁冲突时，任务保持queued；成功认领前不得发送模型请求，不能把数据库繁忙记成已消耗模型槽位。取消工作器时先等待已投递的认领线程结束，再进行关闭清理，避免后台刚提交running却错过interrupted收尾。此调整不宣称全部模型流水线的每个数据库步骤都已移出事件循环。

### 明确错误与恢复动作

SQLAlchemy OperationalError按SQLite错误码识别BUSY/LOCKED，返回HTTP503、`DATABASE_BUSY`和标准`error:{code,message,retryable,request_id}`；其余数据库OperationalError返回HTTP500、`DATABASE_ERROR`。响应不包含SQL、绑定参数、原始driver异常、数据库路径或私人正文。

Rust桥保留结构化服务错误；遇到非JSON错误响应时保留HTTP状态并给出通用诊断，不回显body。成功HTTP响应含坏JSON时同样明确记录HTTP状态，不能把其当成合法结果。前端历史读取失败显示手动“重新读取问答历史”入口，仅重新读取历史，不创建QueryRun、generate、retry或付费调用；数据库错误不自动触发模型恢复。

## 兼容及范围

无Alembic迁移，head保持0014；WAL和事务策略不改变领域版本、抽取计划、旧snapshot/manifest/hash或科学GraphRevision。已有IMMEDIATE写路径保留，知识写入仍经KnowledgeStore。迁移、备份、任务恢复及Sidecar单实例生命周期沿用现有实现。

本轮修复不进入P5，不读取密钥、不新增真实模型请求、不在正式用户库作实验，也不包含Commit/Push授权。已有用户失败反馈保留；离线回归、隔离打包引擎、安装包与用户原生确认分开记录，不能把计划写成通过。

## 验证要求

- 在隔离库持有独立写锁时，八个纯读取路径可以读到已提交快照；未提交内容不可见，来源/用途终验和跨项目隔离继续生效。
- 对只读会话执行意外DML/flush须失败且不改变数据；连接归池后普通Store写入仍可成功，读写模式不串漏。
- 无queued任务的工作器轮询不争写锁；认领期间取消、其他认领、锁超时和关闭竞态不造成重复执行或遗留running；锁等待不阻塞事件循环。
- BUSY/LOCKED与其他OperationalError返回分型JSON，不泄露SQL或driver秘密；Rust对结构化错误及非JSON响应保留状态且不回显body。
- 手动重读历史可恢复列表，失败/重读均不调用模型或生成新任务；旧数据、回答及科学版本不变。

实际命令、结果、未测项和新包身份见[本轮锁修复报告](../archive/reports/query-history-lock-verification-20261104.md)。[ADR0025](0025-query-browsing-and-paper-grouped-answers.md)的分页/论文筛选与冻结引用边界继续生效。
