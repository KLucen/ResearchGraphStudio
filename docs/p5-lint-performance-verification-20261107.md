# P5 Lint 性能与阶段反馈验证（2026-11-07）

日期和时间按 Asia/Shanghai。用户要求优化依赖重建/反向影响查询、批量读取/数据库索引/阶段耗时、准备/推进/末批重建的进度，以及固定规模基准/内存峰值。实现决策见 [ADR0030](adr/0030-lint-performance-and-progress.md)。本轮没有 Commit/Push 或真实模型预算；正式库实验写入 0、真实模型调用 0。

## 实现范围

- `lint_service.py`：catalog 对大表使用完整列投影，来源/关联/成员批量读取；节点检查按本批预取来源行，仍逐 link 验证 EvidenceSpan、Chunk、Section 和版本，不跨调用缓存。增量对账只取所需边列，旧/新边并集传播保持。
- `lint_dependencies.py`：分块列读取、批量写派生边；正反向查询使用有方向索引的递归完整闭包，先当前权限过滤再统计/分页，不因隐藏中间节点截断合法公共后继。
- `0020_lint_phases_and_indexes.py`、模型及启动握手：持久化 phase/timings，增加三个已核对方向的索引。旧 targets/input_hash/operation/科学行/raw 保持；启动前自动备份沿用原机制，测试只在新合成库运行。
- 桌面：准备范围不伪造总数；对象扫描和依赖重建分开，末批对象满数仍显示“正在重建依赖”；明确等待/继续/完成，阶段幂等 key 与迟到响应保护。实际耗时按阶段展示，旧报告标未记录。读取报告本身不推进任务。
- `tests/benchmarks/lint_dependencies.py`：固定规模离线基准，输出逐批 JSONL、SQL 计数、OS RSS/峰值、阶段、完整闭包和来源指纹；拒绝复用既有输出目录。

`CONDITION_UNKNOWN` 仍是信息缺口，保留 unknown，不推断矛盾或补造条件；`SOURCE_UNCHECKED` 不等于文件不可用或科学错误。性能字段不进入冻结工作流、Prompt、wire hash 或问题指纹。

## 输入与依赖等价

本轮封存优化前 163 个后端运行文件到 `.local/lint-performance-20261107/baseline-source`，清单保留，不覆盖旧交付包。

对相同合成数据库快照，以 SQLite mode=ro / query_only=1 分别运行前后 catalog，30,011 个有序 target 逐项完全相同；两者 digest 与原报告 input_hash 精确相同：

`68e3c45b75667ceb72ce98355643cf6ad7350dfd2fd8d859130cb9681f31a1f4`

只读快照前后文件 SHA256 保持。实际凭据为本机 `catalog-baseline.json`、`catalog-after.json`，没有读取正式库。

6 类合成场景覆盖程序阅读单元/选择、Wiki 节点/成员根、note/external/annotation、原文 hash 失效、节点根证据缺失、外部文件缺失、批注与读取根撤权。前后完整依赖边的 ID、expected、state、cursor objects，以及 72 次双向/全量查询响应完全一致；每场景边数为 36/36/35/35/33/31。凭据保存在本机 `dependency-equivalence/report.json`。

1200 层含循环/重复路径的双向闭包测试排除 2000 条无关边与跨项目边，并核对稳定分页。EXPLAIN 实际验证递归和结果连接均通过方向索引完整三键 SEARCH；首次普通 INNER JOIN 被 SQLite 重排为按项目扫边的失败尝试保留，最终固定已到达对象的外层顺序后通过。

## 本轮固定规模基准

两轮采用同字节封存 harness，SHA256 `090dfe9f54ee72ab4bf46bb2f547a5087d842cb7f90726b7333cdf9acb33c964`。规格为 10,000 候选 / 20,000 块 / 2 Wiki / 30,011 目标，每批 100；大多数候选共用同一合法 span，19,999 新增独立 raw chunks，不能借分布变化解释为同规模加速。

前后基准均已完成、断言通过，运行源各自前后指纹一致。旧 2026-11-05 的 430.284749 秒保留为历史成绩，不作本轮 before。

| 指标 | 本轮 before | 本轮 after |
| --- | ---: | ---: |
| 准备范围 | 1.961454 秒 / 44 SQL | 1.706389 秒 / 42 SQL |
| 完整扫描推进（含首次重建） | 856.662931 秒 / 301 批 / 132,367 SQL | 469.026664 秒 / 302 批 / 12,573 SQL |
| 准备 + 全部推进 wall | 858.624385 秒 | 470.733053 秒 |
| 显式依赖重建 | 13.185584 秒 / 40,064 SQL | 3.217814 秒 / 232 SQL |
| 单块变化显式对账 | 13.424384 秒 / 40,064 SQL | 3.344553 秒 / 232 SQL |
| 反向完整闭包 P50 / P95 | 0.861421 / 1.027968 秒 | 0.026222 / 0.030090 秒 |
| 正向完整闭包 P50 / P95 | 0.886865 / 1.051412 秒 | 0.026496 / 0.031464 秒 |
| 进程生存期峰值 RSS | 315,301,888 字节（300.695 MiB） | 259,489,792 字节（247.469 MiB） |

两轮完成态均为 completed、error0/warning0/info1，唯一 info 为 SOURCE_UNCHECKED，规则异常 0；30,016 条依赖边，单块变化准确影响 1 段 / 1 文档。完整推进耗时减少 45.25%，SQL 减少 90.50%；依赖重建耗时减少 75.60%，反向查询 P95 减少 97.07%，峰值 RSS 减少 17.70%。两轮各用全新隔离数据目录；前后源指纹在各轮开始/结束核对。阶段计时与基准 wall 分开，SQL 数包含 flush，executemany 记为一次执行；峰值来自 Windows GetProcessMemoryInfo.PeakWorkingSetSize，包含导入/建库/seed，不是 Python 分配峰值。正反向各 12 样本，nearest-rank P95 为最大样本。

after 第 301 批已处理 30,011/30,011，状态仍 running、phase 为 rebuilding_dependencies，1.750802 秒 / 65 SQL；第 302 批重新验源并重建后 completed/finished，4.666942 秒 / 270 SQL。基准直接观察了该中间状态，不只用 Mock 响应证明阶段存在。节点段每批约 46 SQL，before 同段约 840 SQL。

最终持久计时：prepare 1.592222、validate 433.712787、check 3.805495、dependencies 2.831475、finalize 0.030519 秒，累计 441.972498 秒；最近一次 advance 4.391369 秒，302 次推进。其余 wall 包括报告加载/反序列化、幂等/flush、事务及调用开销。完整目录终验仍占主要时间，性能改进没有省略来源或授权重验；大项目仍可能持续数分钟。

匿名本机凭据分别在 `.local/lint-performance-20261107/before/report.json`、`after/report.json` 与 `comparison.json`。运行源集合清单的摘要 before 为 `98582b6c8325af7b4d4940f1da1cb37823c64b62deedc2547ac470a008fc8073`，after 为 `4f63f5a4acf005b80e0a05bcf6d16e9154ccea3da77844c7bc9a9eb6532dff69`；这些是基准源集合摘要，不是安装器指纹。

本机串行运行仍受系统负载影响；before 运行期间另执行过小型开发检查和约 3 秒只读快照核对，after 期间避免大测试/打包。只有每版本一次完整扫描，不建立统计显著性或跨机器 SLA，不套用 P4 两秒检索目标。

## 回归、迁移与交付

最终运行源冻结后，完整 `python -m pytest -q` 实际 **1185 passed / 3 skipped / 1 warning，469.05秒**。跳过与当前账户文件符号链接权限有关；既有 TestClient/httpx 弃用提示保留。中间80项 Lint/文档/依赖专项和179相关后端/1跳过，以及新增阶段7、迁移1、批读取3已包含在最终全量中，不重复累加。

完整 React **164 / 17 文件，18.93秒**，P5 Edge真实渲染组件 **5/5**，Rust常规 **20通过/1打包Host忽略**；构建后显式运行该Host测试，**1通过，3.08秒**。mypy **136源文件**、Ruff和 **249文件格式检查**（含交付基准）、pip check、TypeScript/ESLint/Prettier、OpenAPI与TypeScript生成通过。此前旧1124全量和19 Edge不作本轮成绩。

0020 专项从真实 0019 Alembic 库出发，包含五种旧报告状态、旧 operations、依赖边、科学行/raw/图修订：升级前备份精确等于旧库，所有旧列逐值保持，phase 和空历史 timings 正确，三索引 EXPLAIN、二次迁移幂等、两次完整 worker 重启与旧 start key 只读重放均通过，零模型请求。

阶段专项覆盖对象满数后实际 API GET 零 SQL 写入、重启继续、旧 key 不重建/新 key 只重建一次、扫描/重建取消、重建前来源变化终止、重建异常事务回滚后恢复，以及 telemetry 不进入 P09 冻结 snapshot/wire/Prompt hash。真实科学质量、用户新包原生反馈、干净机、跨平台/模型/strict、复杂表格/公式、无 OCR 和四份不可用补充原文限制继续保留。

主要实际命令均在仓库根执行，Python为 `C:\Users\KLucen\anaconda3\envs\researchgraph-studio\python.exe`：

```powershell
python -m pytest -q
python -m mypy
python -m ruff check services/engine tests/engine scripts tests/benchmarks/lint_dependencies.py
python -m ruff format --check services/engine tests/engine scripts tests/benchmarks/lint_dependencies.py
python -m pip check
# 导出时设置 PYTHONPATH=services/engine
python scripts/export-contracts.py
pnpm contracts
pnpm check
pnpm test
pnpm format:check
pnpm --dir apps/desktop exec playwright test e2e/p5.spec.ts
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml
```

首次导出漏设PYTHONPATH、mypy局部list缺类型、Ruff遗留import/基准格式、E2E fixture异步函数，以及专项test helper假定无原GraphRevision的失败均已纠正并实际复跑；没有把失败记为成功。普通递归JOIN查询计划失败、旧基准与旧包原生未验继续保留。

## 冻结引擎和新安装包

项目当前 PowerShell7.6.9 执行 `scripts/build-windows.ps1`，PyInstaller/Tauri/NSIS全部成功，保留649.05KB前端chunk提示。首次误用Windows PowerShell5.1执行BOMless含中文的构建脚本被解析器拒绝，日志单列 `build-windows-ps51-failed.log`；切回项目Shell重建成功，没有修改构建脚本或把初次失败记为通过。

最终冻结引擎实际运行 `scripts/smoke-p5.py --executable <本轮引擎>` 与 `scripts/smoke-engine.py --executable <同引擎>` 均成功。P09/P10/P11为本地合成HTTP/SSE各一次、3持久槽；检查方案展示与模型输入隔离、草稿/保存/发布/局部更新、外改、撤权和重启，不是真实科学验收。首次P5 smoke仍断言旧head0019而失败；同步测试脚本到0020后完整重跑成功，保留失败日志，没有改运行源或重建历史包。

Windows PowerShell5.1执行独立 `scripts/verify-windows-install.ps1 -EnginePath <同引擎> -PdfFixture tests/fixtures/pdf/two-pages.pdf -OutputRoot <本轮新隔离目录>`，System32-only PATH **17项通过**，包括实际双页PDF/来源重定位、当前阅读流程/支撑图、证据预览及重启；该脚本未安装应用、不代表干净机或用户原生通过。本轮与前方案轮未传PDF的5项明确分开。

215运行源在冻结、完整回归与构建前后LF指纹一致，基准自身165后端文件实测前后也保持；314资源（含引擎）与Tauri副本逐字匹配，无私人运行资料路径。安装器封存：

`.local/releases/p5-lint-performance-20261107/ResearchGraph Studio_0.0.1_x64-setup.exe`

- 大小：39,054,979字节。
- 安装器SHA256：`afd062f6f700f9081db2f756d37e6b8fa38b5206f06c1f25d7d4488fd4d12198`。
- 引擎SHA256：`e56076072856c567b83367fb309b5c33651050fd491472c1aaca57890f539bd7`。
- schema：0020；旧安装器、失败尝试和原始基准日志保留。

退出旧应用后安装新包，首次启动先自动备份再升级。打开原报告并重新读取，未完成则继续；新的推进会记录阶段耗时，旧报告不补造历史计时。要观察新的完整阶段，可在原项目显式开启一轮Lint，无需重抽论文。对象检查100%时仍可能等待依赖重建；重启后可显式继续。unknown可以继续保留，不是要求补造条件或执行模型修复。

无真实模型调用、无正式库实验、无Computer Use/替用户安装/Commit/Push。用户原生升级/扫描、目录选择/发布/重启和真实科学质量仍需分别验收，未将P5标成退出全过。

最终文档检查为192份Markdown/832个本地链接、86项当前规范资产与52项归档资产的LF大小/hash通过，仓库内断链0；4份已登记外部原文不可用单列。689源码候选的内容/私人路径/Gitleaks、差异空白及空暂存区检查通过。开发日志DEV-0062记录完整命令、失败和最终分母；本轮所有本机原始凭据保存在独立的 `.local/lint-performance-20261107`，不覆盖旧包和旧基准。
