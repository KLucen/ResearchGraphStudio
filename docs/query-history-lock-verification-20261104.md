# 本地问答历史数据库锁修复：实际验收

日期：2026-11-04（Asia/Shanghai）。用户在新安装版“本地问答历史”收到“本地服务返回了无效响应”；本轮修复该问题，不进入 P5，不清理或重建任何用户数据。决策见 [ADR0026](adr/0026-query-read-snapshots-and-worker-locks.md)，继承[浏览增量](p4-query-browsing-verification-20261104.md)的论文筛选、分页和引用分组。

## 已确认的原因

只读提取实际宿主 `engine-startup.log` 的异常类型与栈位置，历史、文档和保存列表均在 `scope_versions → Session → BEGIN IMMEDIATE` 报 `sqlite3.OperationalError: database is locked`。没有输出日志正文、SQL参数、论文或密钥，也没有读取正式数据库作实验。

此前所有数据库会话（包括纯读取）都会申请写锁，遇到长检索/索引事务时等待5000毫秒后失败；未处理的数据库异常返回非JSON 500，Rust的JSON解码又统一提示“无效响应”。正常启动的后台工作器空轮询也申请写锁，且同步等锁会占用异步事件循环。仅在禁用worker的HTTP测试中修复读取，仍不足以解决正常桌面运行。

在隔离样本中，旧行为被实际复现：持有独立写锁时，历史及同页读取失败；修只读事务而未修worker的正常进程预检仍在4秒超时。原失败结果保留在本轮.local目录，不改写为成功。

## 修复边界

- `storage.py`启用WAL、保留FULL默认耐久策略及5秒busy等待。专用`read_session`使用只读快照和SQLite `query_only`保护；连接归池、写事务开始均恢复写模式。不能在该会话中悄悄flush或升级为写事务。
- `query_api.py`的8个纯读取/校验路由使用该会话，继续来源、权限和项目终验。检索/浏览仍须同步派生索引，prepare/生成入队/保存/批注/移除仍使用IMMEDIATE写事务，保留Store幂等与原子性。
- `app.py`工作器先只读检查queued，有任务才短事务认领并重验状态、增加attempt；认领和诊断完成的同步数据库步骤移出事件循环。认领锁冲突保持queued，未发送模型请求；取消时等待已投递认领线程完成后再关闭清理。P07等待模型期间的`_active`状态检查同样只读，原付费账本和两槽限制不变。
- 数据库BUSY/LOCKED返回标准JSON：HTTP503、`DATABASE_BUSY`、可重试及request_id；其它OperationalError返回500 `DATABASE_ERROR`，均不暴露SQL、参数或driver详情。Rust遇到非JSON错误保留HTTP状态，不回显原始body。
- 历史失败时新增“重新读取问答历史”，只重新读取历史，无prepare/generate/模型重发；断连或读取中不可重复点击。

无Alembic迁移，head保持0014；不改历史snapshot/manifest/hash、答案、模型raw、科学GraphRevision或论文知识，不要求重新抽取。WAL仅改变运行日志模式；现有一致性备份继续使用SQLite backup API，不能仅复制活动主库文件替代备份。

## 实际验证

全部Python使用Anaconda `researchgraph-studio`，数据为隔离合成样本，无真实模型调用。

| 命令/范围 | 实际结果 |
| --- | --- |
| `pytest tests/engine/test_query_concurrency.py tests/engine/test_query_answers.py -q` | **46 passed**，含7项并发/错误保护新测试；与全量交叠 |
| `./scripts/check-phase0.ps1` | 整体退出0，Python **895 passed / 2 skipped**（460.69秒）、React **123 passed**，Ruff/191文件格式/mypy102源文件、依赖、契约生成、Prettier/TypeScript/ESLint与生产构建通过 |
| `pnpm --dir apps/desktop exec playwright test e2e/query.spec.ts` | **5 passed**，既有问答/保存/历史/分页与折叠回归 |
| Rust fmt、Clippy和单测 | **19 passed**，含4个错误响应解码测试；非JSON 500/503、标准JSON错误、成功坏JSON均覆盖，原body不外露 |
| `./scripts/build-windows.ps1` | 新PyInstaller/Tauri/NSIS构建通过，源与安装器最终指纹另记 |
| `cargo test ... packaged_engine_connects_through_native_host_and_restarts -- --ignored` | 新冻结引擎打包Host **1 passed**，两次启动握手正常 |
| `python scripts/smoke-engine.py --executable <新引擎>` | 旧导入/证据/图谱/历史及合成HTTP/SSE问答→保存→批注→重启→移除→重启通过；本地协议stub仅1 POST，不是科学质量实测 |
| PS5.1 `verify-windows-install.ps1 -EnginePath <新引擎>` | System32-only PATH隔离 **5项通过**；未给PdfFixture，不把前轮17项记为本轮成绩 |
| `.local/history-lock-20261104/frozen_concurrency.py --engine <新引擎>` | 正常worker启用，两启各7个HTTP读均200；独立writer保持且另一个写请求等锁时，读取分别0.063/0.062秒，未提交status不可见。两次真实SQLite写争用均503 JSON，含DATABASE_BUSY/retryable/request_id；快照内writer可提交，旧快照稳定。**47张来源表哈希保持**，Query=1/Model=0/Answer=0不变，模型端点请求0，完整性/FK及EOF退出通过 |

并发冻结样本实际覆盖历史、文档、保存列表、衍生图、run、answer和validate七个接口，未另造已保存详情；该第八个路径由现有保存/API回归及只读SQL审计覆盖，不扩大为八接口持锁实测。组件新增失败→手动重读→成功测试，验证所有生成和写入入口调用0。另测只读会话写入被拒绝、池复用恢复写权限、读者不阻塞writer提交、worker认领等待不阻塞历史且attempt仅1、模型等待状态轮询在持锁下仍正常。

两次全量运行在后续同类轮询问题定位后主动中止，均无完整通过摘要，不算通过；最终完整运行单列。一个新增worker测试最初使用错误路由、一个前端测试最初假设旧按钮仍在重读DOM，修正测试后通过；没有放宽产品校验。已有httpx弃用、Vite大chunk及2项系统符号链接权限跳过继续记录。

## 新安装包与收尾

新包`.local/releases/query-history-lock-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe`，**38,823,098字节**，SHA256 `318f14db52341b6c865f48d0a8cdf9cc08916510c162bc780434cf1790d8f73a`；冻结引擎SHA256 `3efce8e0d0069c7ed84cb3cd99d284b2faba7bb4b3d6430f8ba933649c6514c1`。174运行源码与281份资源（不含生成pycache）指纹一致，资源无私人PDF/数据库/密钥/日志；新目录保留独立副本，旧包不覆盖。**613份源码候选内容/路径及Gitleaks、177 Markdown/788本地链接/88规范资产LF哈希、diff及空暂存区通过**；四份登记外部原文仍不可用。文档刷新首次写hash文件出现OSError22，重试UTF8命令成功，未把失败尝试算通过。

当前修复尚未由用户安装并反馈，不宣称用户原生通过。退出旧应用后安装此包，重开原项目确认“本地问答历史”正常加载；若此前读取失败，可用新按钮重新读取，无需重新抽取论文或生成答案。

正式数据库实验读写0、真实/付费模型请求0；只读日志诊断与合成协议测试分别记录。未经新授权不Commit/Push，HEAD及本地origin记录仍80552d3，不把旧R5 CI算作本轮结果。没有Computer Use、替用户安装/卸载或进入P5。干净机、真实strict、无OCR复杂版面和S1–S4四份不可用外部补充原文限制保留。
