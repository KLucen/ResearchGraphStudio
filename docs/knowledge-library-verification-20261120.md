# 研究内容知识库 K1–K3 验证记录

日期：2026-11-20（Asia/Shanghai）。范围：按用户明确授权实施前三阶段闭环、回归并上传GitHub；K4未启动。决策见[ADR0060](adr/0060-durable-research-knowledge-library.md)，实施差异见[方案](research-knowledge-base-plan-20261120.md)。当前为分项实测记录，整体最终验收块由协调交付补充，不以旧成绩替代本轮重跑。

## 实施范围

| 阶段 | 实际功能 | 主要文件 |
| --- | --- | --- |
| K1 | 独立库/入口、零模型收藏本地及模型旧概览、题名根、可靠来源身份、不可变快照、专题/归档/备注/独立布局/导出、应用移除保留/库内永久移除 | knowledge_library_models/contracts/api/service、lite0016、ResearchKnowledgeBase/knowledgeApi/App/PaperOverview |
| K2 | 两来源完整解析adapter、paper-knowledge-1联合卡片/五类图、逐节点/科学边精确引文、严格JSON/DTO/来源终验、版本/缓存/失败与发送预算 | knowledge_sources、paper_knowledge、knowledge_tasks、knowledge_extraction_models、lite0017 |
| K3 | 自动解析收据/知识事件、策略与累计预算、双语词面候选、冻结比较及版本对检查点、双侧依据联系/持久汇报/未读/置顶/备注、图与报告双向定位、独立用量 | knowledge_connections/contracts、knowledge_retrieval、knowledge_workflow_api、knowledge_connection_models、lite0018、knowledge_tasks/App/ResearchKnowledgeBase |

迁移head为lite0018。项目保留原概览v1、精读、译文与大章节状态，已有合法阅读结果无须重新生成。旧无逐项来源图标legacy；新grounded只证明来源可回查。当前K2完整材料容量不足整体拒绝，没有自动长文分批。候选不是全库穷尽，关系语义准确度未验证。

## 已执行分项

| 命令/范围 | 实际结果 | 证据与边界 |
| --- | --- | --- |
| Conda researchgraph-studio Python：pytest tests/engine/test_knowledge_extraction.py tests/engine/test_knowledge_connections.py tests/engine/test_knowledge_workflow_api.py tests/engine/test_knowledge_library.py -q | 67 passed，15.00秒，1条Starlette废弃提示 | K2 26、K3 27、workflow4、K1 10；后续自动事件加固的最终全量另记 |
| Conda项目解释器：pytest tests/engine/test_knowledge_library.py tests/engine/test_knowledge_extraction.py tests/engine/test_knowledge_connections.py tests/engine/test_knowledge_workflow_api.py tests/engine/test_knowledge_usage.py -q | 最新79 passed，20.15秒，1条Starlette废弃提示 | 加入9项用量/输出预算及最终冻结来源/权限回归，完整仓库全量另记；包含前一行多数项目，不相加 |
| K1+app+automation专项 | 最新21 passed | K1 11（新增完整reports/layouts导出及坏报告拒绝）、app3、自动事件7；含原子收据/提交后崩溃重启/旧无标记源不收费/撤权源变回滚/取消失败不重发/生成中开启策略不追认授权；与前行有重叠，不是全量 |
| source scripts/smoke-knowledge-library.py | 通过 | 2匿名PDF自动K2各1次、K3共1次，首篇no_candidates、第二篇双侧引文汇报，GET/重启0重发；合成usage输入69+输出123=192 Token，不是供应商账单 |
| pnpm --dir apps/desktop exec vitest run src/ResearchKnowledgeBase.test.tsx src/knowledgeApi.test.ts | 15 passed /2文件，6.28秒 | 12库交互+3 API；零调用浏览/收藏、显式source+授权、五类展开/准确引文、双侧报告、已读/置顶/备注、实际阅读返回、归档、策略/预算、分页外目标定位、显式失败继续、永久移除确认 |
| pnpm --dir apps/desktop exec playwright test e2e/knowledge.spec.ts | 最终3 passed，6.7秒 | 实际App与ForceGraph，导航顺序/未读、两根展开五类、虚线→报告→双方材料→精确图边定位、布局/固定/相机和备注重载、620/390px无横向溢出、显式假Provider发送；零外网/真实模型 |
| pnpm --dir apps/desktop exec vitest run src/ResearchKnowledgeBase.test.tsx src/LiteReading.test.tsx src/graphAppearance.test.tsx src/ForceGraph.test.tsx | 较早中间版64 passed，15.44秒 | 当时知识库8项+LiteReading47+图例6+renderer3；最终增加交互/DTO及移除入口后需以最终全量为准 |
| pnpm --dir apps/desktop check | 通过（最终前端） | TypeScript与ESLint；最终全量构建另记 |
| 首轮前端全量（永久移除UI最后补齐前） | React193 passed、Edge37 passed | 中间阶段成绩，最终全量另记，不替代最终删除交互回归 |
| 首轮后端全量 | 797 passed /1 failed /1 skipped | 旧Lite清理测试把新`/knowledge/extract`仍当作已删除旧入口；已适配为新严格DTO/显式来源入口断言，最终重跑结果待填；不把失败抹去 |

K1隔离专项覆盖：两来源旧图零请求收藏、来源终验、已知SHA身份归并/同题名不合并、不可变快照、应用移除保留、专题/布局重启、永久删除前备份、幂等副本清理、真实lite0015旧库构造后的加性迁移且旧表各行保持。Zotero身份路径在代码保留，但不能把SHA夹具当成真实Zotero验收。

完整JSON导出含论文知识版本、专题、reports与layouts，保留报告read/pinned/note；导出时再验报告raw/来源快照，损坏报告409拒绝，不导出私有raw、凭据或模型配置。

K2/K3专项覆盖：精确引文/occurrence、严格JSON、raw保留、缓存重验、容量零发送、失败保留旧版本、来源漂移、相同输入显式最多2次、合法received本机恢复0网络；累计extract/connect及活动预留/消费墓碑预算；版本对重验、负向原因继承、并发PAIR_PENDING、两批一坏partial后仅补未完成pair及ConfiguredProvider输出不足零发送。

浏览器截图已人工查看：宽屏汇报在独立弹窗中并列双方来源，limitations_zh单独可见，窄屏改顺序显示且无溢出。截图为匿名合成材料，保留在本机apps/desktop/test-results，不上传私人数据。首轮相机测试用固定屏幕坐标未命中画布，改实际renderer缩放控件后通过；首次报告精确定位发现root详情盖住已选关系，已修互斥并重跑3/3。失败记录不被记成产品验收通过。

文档分项：README、文档导航、模型配置、实施方案、ADR0060、本报告、progress和DEV日志共8文件/218本地链接0缺失，所触已有文件diff-check通过。2026-11-20 15:24前端运行源/测试冻结交给协调打包，文档收尾可继续；不修改正式用户库。

## 最终整体交付

最终冻结源码通过 `pwsh -File scripts/check-phase0.ps1`：Ruff检查和177文件格式通过，mypy **109模块通过**；引擎 **819 passed /1 skipped /1 warning，192.00秒**，唯一跳过为现有符号链接权限条件，warning为既有Starlette/httpx弃用。依赖检查、OpenAPI重新导出/TS契约、TypeScript/ESLint/Prettier及生产构建通过；React **19文件/194 passed，16.95秒**。完整实际Edge **37 passed，28.8秒**，最终包含永久移除UI。保留首轮旧入口测试失败；最终通过使用新显式来源DTO断言，不删除安全边界。生产构建仍提示既有主包超过500kB，构建成功。

Rust `cargo fmt --check`、`cargo clippy --locked --all-targets -- -D warnings`通过；常规Host **16 passed/1 ignored**，随后显式指定最终打包引擎执行该ignored集成测试 **1 passed，4.34秒**，实际验证连接和重启。新PyInstaller引擎 `smoke-engine.py` 本地PDF/目录/按章读取通过，schema lite0018、模型0；`smoke-knowledge-library.py --executable ...` 通过两建模/一关联、双侧引文和GET/重启0重发，用量为合成69输入+123输出=192，真实模型0。匿名PDF字节保持。

181项运行源、测试与构建配置在最后引擎构建后核对全部不变。暂存实际198文件已逐路径检查并运行 `check-sensitive.py --staged`，私人路径/Gitleaks通过；最终文档与契约补齐后再扫描。
新未签名安装器：[ResearchGraph-Studio-Knowledge-Library-0.0.1-x64-setup.exe](../.local/releases/knowledge-library-20261120/ResearchGraph-Studio-Knowledge-Library-0.0.1-x64-setup.exe)，**160,752,786 bytes**，SHA-256 `b5c20fa89d4d9e075d08424cec8cd5e471737416ac2bf082fd85a19f4054f7ce`。2026-11-20 15:30:54完成封装。Windows PowerShell5.1隔离安装通过：lite0018、本地匿名PDF/三段模型材料、阅读状态/题名修改、清理重建/删除及原PDF保持，模型0。安装目录sidecar再跑知识库HTTP闭环：两自动K2+一自动K3、双侧引文/报告元数据/重启保持，GET和重启0重发；3请求均loopback合成，不是收费模型。

使用实际安装sidecar执行完整Host `cargo test --locked -- --include-ignored`：**17 passed /0 ignored，3.93秒**。181项源/测试/构建配置保持，sidecar SHA-256 `405af6f088b0e88c479642662c7007fd6d4a0e760b7f75cd68c9e79173dfa94c`，334内部资源与打包源逐项哈希匹配。本机证据目录`.local/verify/knowledge-library-20261120/`，保留source-manifest、fingerprints及源码/安装HTTP结果，不上传该目录。
本轮已按用户明确授权普通推送分支`codex/research-knowledge-library-k1-k3`，源码提交`9a618946af6ee4c0718bf843556c52e999a9cd1d`；已建立[PR #1](https://github.com/KLucen/ResearchGraphStudio/pull/1)，未合并main。GitHub官方SSH443读取/上传预检和实际push通过，保留origin官方HTTPS配置，没有force或全局网络改动。GitHub API操作仅在内存使用现有Git凭据，不把凭据写入源码/日志。

提交前实际暂存198文件私人路径规则/Gitleaks与diff-check通过，完整工作区源码扫描也通过。收尾只补本验证、progress和开发日志，运行源及本机安装包指纹保持。PR已启动Windows build and acceptance，包含完整check-phase0、真实Edge、打包引擎两种HTTP烟测、Rust/Host、NSIS及安装版PowerShell验收；此记录提交时远端仍在运行，实时结果查看[PR检查](https://github.com/KLucen/ResearchGraphStudio/pull/1/checks)，最终结论由本轮交付消息记录，不把启动当作通过。

## 尚未验证

真实收费模型0、正式用户库实验0。合成Provider说明机制，不能证明跨论文关系科学成立；严格引文也不等于科学语义正确。用户原生WebView、实际旧库升级、真实论文科学样本、干净机和K4规模/语义召回/实体聚合未通过本轮分项验收。当前容量不足不自动拆批、不承诺长文完整建模；费用未提供保持未知，不以估算Token或固定候选数承诺价格或SLA。


## 远端锁定环境问题与修复

最终首个远端run `44696102100`（head15739be）在mypy前后发现本机/锁定环境差异：`formula_ocr.py:70`无法导入PIL；Ruff和177文件格式通过，其后浏览器/打包/Rust/安装步骤未执行，不记为通过。根因是pyproject已经声明的numpy2.2.6、Pillow12.0.0、onnxruntime1.24.4和tokenizers0.22.2未纳入requirements-win-64.lock，本机已安装所以本机回归未揭露缺口。新增check-runtime-lock.py并置于check-phase0最前面，实际在旧锁上准确拒绝这4项；Windows锁已重新生成：原46个固定版本保持，新增4个runtime及9个transitive，共59 pins。新增版本与本机已打包环境精确匹配；官方PyPI版本JSON提供SHA-256，生成时只对当前pip-tools子进程使用版本元数据，未改系统/pip-tools或放宽TLS/哈希。初次freeze含Conda本机构建file URL，已仅规范化成实际distribution版本；原失败尝试不当作生成成功。

实际 `pip install --dry-run --require-hashes --no-index -r requirements-win-64.lock` 返回所有依赖已满足，零安装/升级；`pip check`、12项runtime锁覆盖、mypy109、Ruff及178文件格式通过。修复只涉及冻结依赖/构建前置检查/说明，知识库运行源、已验本机安装器和334资源保持；修复上传后远端从干净锁定环境重新验收，结果以PR检查为准。


## 远端同时间戳夹具修复

锁修复后的run44697853179（head3379169）已通过干净依赖复现、12项锁覆盖、Ruff/178格式/mypy109；后端实际819passed/1failed（448.49秒），后续前端/打包/安装未执行。唯一失败为`test_current_mapping_rejects_changed_source_or_anchor[artifact_text]`：测试只按created_at.desc选待篡改解析，两个版本同时间戳时改到历史记录，当前来源实际未变。

保留原断言的隔离副本强制相同时间戳后，本机准确复现DID NOT RAISE；改为`current_structure`精确选当前章节材料并断言归属，再参数化普通/相同时间戳，结构版本专项27passed（1.94秒）。未改生产来源校验或关闭断言。修复只改测试与报告，运行源/本机安装器保持；后续远端结果以PR检查和最终交付消息为准。


相同时间戳只读复核另把81项K1/K2/K3/API/用量测试的时钟全部固定，全部通过。SQLite反向未排序读取检查发现两处来源修改夹具仅parse_id scalar，可能误选被排除的References，已实际复现3个参数失败；改为明确chapter_ref=c0正文，并在测试修改事务启用reverse_unordered_selects。此为同类夹具加固，生产来源门槛和运行源不变，专项结果另记。


## 远端浏览器测量竞态修复

run44700256767（head956286e）远端完整检查通过：后端823passed（438.20秒，新增同时间戳3项；Runner可创建符号链接故无本机跳过）、React194passed、契约/类型/格式/生产构建均成功。真实Edge36passed/1failed，新知识库3项均通过；旧paper-reading窄屏用例分别读取译文和批注boundingBox时布局/目录滚动变化，取到不同时刻视口坐标。后续引擎打包/Rust/安装因该失败未执行。

仅修该E2E测试：等待fonts.ready，逐行在一次evaluate原子读取所有矩形，并重试实际anchored/stacked模式及原严格几何条件；顶部差<2px/严格右侧/严格译文下方/窄屏宽度>300px均保留，无固定sleep、无生产源码修改。实际Edge目标普通repeat10为10/10（18.3秒），CDP四倍CPU repeat10为10/10（29.9秒），整文件3/3（4.2秒），Prettier/diff检查通过。安装包指纹不变，后续最终CI继续验证。


run44702786033（head67a4abb）后端823passed（401.02秒）及锁/格式/mypy/契约通过；新E2E可选CPU环境开关引用process，项目不引入Node全局类型，前端tsc报TS2591，React/浏览器/打包未执行。移除只用于降速补验的开关，不添加新依赖，保留原子测量与严格布局断言；实际pnpm check/format复查通过，再完整跑浏览器。此前10次四倍CPU成绩来自明确临时降速测试，不作为应用运行依赖。此次缺完整tsc复查的遗漏和失败记录保留。
