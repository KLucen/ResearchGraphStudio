# P4 Query实施与实际验收 — 2026-11-04

本报告记录Q05～Q08的继续开发，继承[Q01～Q04实际报告](p4-query-foundation-verification-20261104.md)；设计决策见[ADR0023](../../adr/0023-grounded-query-and-explicit-saving.md)。Q05有据回答、Q06页面和Q07明确保存已接入；Q08按下面的实际结果记录。未进入P5。

R5源码交付`80552d3`与其远端CI属于前轮成果。本轮Query增量尚未Commit/Push；私有数据库、论文、笔记、密钥、模型raw验收材料与安装产物不进入源码提交。

## 实际实现

| 范围 | 当前实现与边界 |
| --- | --- |
| P07回答 | `P07_query_grounded_v1` / `query-grounded-semantic-1`，运行DTO生成输出Schema与Prompt规则；只返回段落语义/归属/短引用/限制，程序绑定正式身份 |
| 多来源终验 | 项目级QueryRun/QueryModelRun/不可变答案，复用Q04完整上下文；入队、发送前、返回、读取和首次保存检查当前来源/权限及冻结raw谱系 |
| 恢复 | 初次一个请求槽位、明确继续至多第二个；I/O前持久账本，超时/中断不自动重发；完整合格raw可零调用恢复，两个不合格响应不能继续收费 |
| 页面 | 项目问答、本地预览、论文选择、个人材料用途、网络授权、生成/取消/继续、引用与限制、调用/用量、执行历史、明确保存及独立衍生层 |
| 保存 | Store统一保存所选合法段落，新增Synthesis/Insight；确定性复制新增模型调用为0，不为复制强制P08；同答案/选段/kind/目标幂等 |
| 文档与来源 | 默认综合文档；明确目标+基线才追加不可变文档版本，旧段落/版本保留；有效根依赖与原文档lineage分开；不发布Markdown |
| 数据迁移 | Alembic0013加性新增`query_saved_knowledge`；旧来源/ModelRun/raw/答案/任务保留；正常Query不推进科学图版本，明确保存推进一次 |

科学段落须有论文根证据，个人观点须有已授权笔记根且独立归属，跨篇解释不能变成作者Claim。引用校验只证明来源/坐标和协议一致性，不证明科学结论正确。独立Annotation Query引用、P5 Lint/Wiki组织/发布仍未实现。

## 已执行的专项检查

统一使用Conda `researchgraph-studio`。以下是各次实际命令记录，不能把独立运行的数量直接相加作为全量去重总数。

```powershell
& C:/Users/KLucen/anaconda3/envs/researchgraph-studio/python.exe -m pytest tests/engine/test_query_save.py tests/engine/test_query_documents.py tests/engine/test_query_api.py -q
& C:/Users/KLucen/anaconda3/envs/researchgraph-studio/python.exe -m ruff check tests/engine/test_query_api.py
```

- 保存/文档/API组合：46项通过。新保存文件包含17项测试，其中一项使用真正P07执行、完整raw及实际`validate_answer`，随后追加同Wiki、幂等重放、检索与读取衍生图；不是仅用保存stub替代整条链路。
- HTTP集成：10项通过。真实TestClient且`start_worker=False`，显式注入离线Provider；覆盖prepare→generate→执行→GET答案→save→saved/derived/检索→关闭后重开。包含错purpose、缺少/拒绝网络授权、假ID/跨项目、请求前及请求中取消、超时后明确第二槽位、坏raw保留与继续、来源改变拒绝dispatch、同时间历史分页/新插入/坏cursor、笔记用途当前值及撤销两项false。
- 迁移测试：0012隔离库含旧QueryRun/QueryModelRun raw/答案及FTS数据；0013升级后旧表原列/行逐项相同，外键/完整性正常，升级前备份仍为0012且原行相同，重复启动只保留一份升级备份。
- 语义hash补强：新node依赖冻结`payload_sha256`，直接引用与旧文档wrapper穿透两路径均覆盖；即使payload被改而revision/text未变，保存详情/列表、文档读取、检索、衍生图和幂等回放均不能继续提供旧有效正文。旧无字段契约和请求hash形状保持，不新增迁移。
- Q07代码Ruff、格式和mypy通过；API测试Ruff通过。已有Starlette/httpx弃用提示保留。

API集成先复现两个真实生产兼容缺口：Q05使用的`answering/completed`阶段不在通用JobView中，以及通用Job重试幂等命中返回缓存`queued`而非后继当前状态。已改用兼容的`reasoning`/完成空阶段，并在Query重试记忆命中时重载实际后继、校验项目；修复后上述10项通过。

确定性用例核对：默认生成前后论文知识、科学关系、选择、布局、原文/证据与R5 ModelRun逐行保持；明确保存只新增衍生记录/文档和一次图修订。取消和失败保留已发送请求及原raw，重复操作不双写或重调。个人来源撤权后，缓存prepare/答案、保存、已保存列表与衍生图不能提供原私人正文；源Markdown字节保持。

## 自动化与真实执行

- `pwsh -NoProfile -File scripts/check-phase0.ps1`：首次完整流水线 Python **838 passed/2 skipped**（既有本机符号链接权限限制）、Starlette/httpx弃用警告保留；最终所有源码稳定后再跑全量 **862 passed/2 skipped**（332.31s）；最后全Query **237项**通过，交叠专项不累加为全量。第一轮遇到旧head断言、正在开发的负例fixture和孤儿FTS漏清理，均已修复，未降低生产来源校验。
- React **108项**、真实Edge合成IPC **13项**通过；最终原文根点击分流再测Query Edge3项通过。Rust **14项**通过，正式冻结引擎Host验收另记。浏览器测试使用合成资料，不等同用户新安装版反馈。
- 离线金标 **24题/3种文献类型**通过：16有据题全部命中前20内金标版本（100%），8无证据/旧版/跨项目/Mock/驳回/坏引文/个人资料关闭/撤权负例按定义排除。6题图扩展对照、121节点闭包、条件四态和表格边界另有专项；本地召回成绩不是科学准确率。

## 两篇真实论文、10题与保存

使用上一轮已授权并通过R5的两篇论文隔离副本（mode=ro backup后迁移0013），复用前轮全局Reasoning配置快照和OS凭据。默认正式库当时无reasoning角色，因此没有宣称使用该库的当前角色，也没有替换用户设置。验收脚本注入的是实际ConfiguredProvider HTTP客户端，仅为隔离库选择原OS凭据命名空间，不是Mock。

10题覆盖方法/贡献、稀疏数值及条件、未选候选/限制、解释与信任、跨篇比较/不可比、中文提问英文来源和无证据。**9题完成有据回答，1题无证据insufficient且零调用；实际发送10次**。第4题第一次响应虽finish_reason=stop但JSON未闭合，严格解码拒绝发布并保留raw，明确续接使用第二槽后成功；成功题未重发、没有重抽P02/P12/P13。总用量 **737,701 Token**（prompt683,387/completion54,314，其中记录reasoning36,998），供应商未提供金额。此处费用未知不是零，真实调用已停止。

两篇各保存一份综合，同key及新key复用均不重复；完整引擎退出后重启，10题答案、2份已保存综合及独立衍生引用仍可读取。原4篇Paper/4版来源、1921Chunk、1930Span、758知识节点、1705证据关联、129旧ModelRun整行/raw、18旧Job、6选择/3活跃头/262单元/1043成员及822来源关系保持，完整性/外键通过；正式库实验写入0。脚本首轮保存时遇到开发中lazy模块热改导致的契约混用422，稳定源码重启后零新增模型调用完成保存，原日志保留；发布引擎不采用热改源码模式。

对9份成功回答共62段做逐段来源上下文核对：58段支持、4段部分支持，未观察到完全无源的科学断言、捏造数值或作者归属错误。4段问题包括架构适用边界/最强对照引用不全，以及比较表头子列/两方向条件说明不清；这是有限样本的保守人工审读，不是全局准确率或论文结果复现。原回答/raw保留，不通过修改旧答案伪造通过。软件继续明确来源校验不是科学事实认证。

第9题原上下文虽选两篇，排序前4命中却全部来自一篇；模型正确说明不能完成两篇比较，没有编造另一篇，但原问题未完整回答。本轮据此修复显式多论文召回：先保留每篇最高相关真实命中，再补原排名；题名不作科学覆盖，没有命中或limit不足均明确missing。新scope_coverage由context按实际根证据复核，缺选中论文时insufficient并零外发；旧无字段的manifest/hash/回答仍按原计划重验。同一真实第9题在修复后仅重新prepare，本地上下文已覆盖两篇、missing=0且prepared；旧答案仍原样通过重验，总真实请求保持10。没有为新上下文追加付费答案，不将新召回复查冒充新回答质量通过。逐题原文、模型raw、完整来源与逐段报告只保存在忽略的 `.local/p4-completion-20261104`，不进源码。

## 性能、打包与安全交付

以下记录最终实跑结果，未测项不记通过：

| 项目 | 当前状态 |
| --- | --- |
| 完整回归/静态/契约/构建 | check-phase0退出0，最终源码全量862 Python/2 skipped、全Query237；108 React。Ruff/182文件格式/mypy97源文件、pip依赖/OpenAPI/TS/ESLint/Prettier、Rustclippy/fmt与生产构建通过 |
| 1万候选/2万正文纯本地混合检索 | 最终cold1.985481s，warm12样本P50=1.7356675s、nearest-rank P95=max=1.985979s；本机≤2s目标达到，模型调用0 |
| 冻结引擎/Host/PowerShell | build-windows的PyInstaller/Tauri/NSIS通过；冻结smoke完整旧链路及新Query本地HTTP/SSE协议stub生成→保存→强退重启→回放通过（stub POST1次），打包Host1项/两次启动停止，PS5.1/System32-only PATH隔离17项通过 |
| 源码安全与文档 | 最终Gitleaks/实际内容及路径扫描、文档本地链接/88资产LF hash、git diff --check通过；暂存区为空，未Commit/Push；596源码文件、171 Markdown/704本地链接/88资产LF hash核验，无坏链接；四份登记外部原文不可用保留 |
| 新包原生问答/干净机 | 尚未执行或获得用户反馈，不能用前轮R5反馈替代 |

性能脚本为 `tests/benchmarks/query_retrieval.py --data-dir <新目录> --report <新文件>`；拒绝打开已有库或覆盖报告。Windows11 10.0.26200/Python3.12.16，10,000知识节点、20,000Chunk、30,001索引/FTS条目。FTS正文+alias逻辑UTF8为3,687,347字节，总数据库45,961,216字节，峰值RSS279,097,344字节（含导入/造数/检索）。本机SQLite未编译dbstat，物理FTS页体积不可测，字段为null并记录unsupported，不能把逻辑字节当磁盘索引体积。

合成分布：9,996独立候选共享一个合法span，4个原支撑节点/3条合法边，19,999独立raw块；12次warm混合raw、知识支撑命中和未命中。不包含复杂表格/多论文真实图规模，P95为小样本本机结果，不能外推全负载SLA。旧实现冷建192s/混合warm P95 2.639s的瓶颈为逐条FTS删除、同调用重复验证和丢弃的诊断hash，优化后再测，未删必要支撑。

## 安装包与用户操作

安装器：`.local/releases/p4-query-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe`，**38,786,476字节**，SHA256 `861ef988c12ef5bfba8f70fa0d0e5b68348903cefa987698cc932273b6bbe97e`。Sidecar SHA256 `4dbf5210ba7482e74a9abb244427262a086af8d5e22f8a3955ccc455068ba741`；delivery.json记录165份实际打包源文件指纹，构建后核验未变，资源中无PDF/数据库/.env/运行日志。本轮未替用户安装/卸载或启动正式桌面库。

退出旧软件后安装新包，打开原项目→确认旧知识/证据仍可读→问答页选择论文并提问→逐段查看引用及限制→明确选择段落保存→重启读取。无需删除知识或重新抽取；新的模型回答仍需用户明确网络授权。新包原生反馈已请求，尚未反馈不记通过；前轮R5反馈不替代P4新页面。

## 已知限制与下一步

首次真实P07响应即使返回合法JSON，也只在引用/归属/来源终验后发布；遇到实际服务商拒绝、超时、截断或不合格响应仍可能失败。软件不会通过无限timeout、删除未知科学字段或反复付费请求掩盖问题；历史和完整合格raw可恢复，来源/权限变化须重新准备。

模型语义、归属、条件遗漏与科学准确性需要逐题真实评价，不把Schema及锚点测试当作科学质量成绩。现存PDF未在本轮读盘核验时继续标`not_checked`；不能据已有证据宣称已验证当前附件。无OCR及复杂版面保证，真实strict、跨平台/干净机以及S1–S4外部补充原文不可用等限制独立保留。

本轮已完成Q08本机链路、回归与安装包交付，停止于P4；用户新包原生确认和上述质量/平台限制仍单列，不启动P5。后续Lint/Wiki应复用当前逐段根依赖、内容/文件双状态及用途授权；主题组织、增量改写和文件可靠发布仍需各自任务及明确写入授权。
