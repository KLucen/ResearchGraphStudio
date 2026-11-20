# 论文分页解析、检查点与受限修复验证

日期：2026-11-18（Asia/Shanghai）。实现边界见[ADR0052](adr/0052-resumable-document-batches.md)，之前单请求超时修复见[ADR0051](adr/0051-document-timeouts-and-visual-pdf-input.md)。用户本轮已明确要求工程实施，此前仅设计的限制不再适用。

## 实施范围

- 新模型计划默认按页顺序解析，每批最多5页（公开设置2–8页），相邻前1页共享；实际容量规划只缩小范围。核心页保留原始页码，必须由片段来源范围或带警告的unavailable_pages覆盖。共享页为上下文，不重复发布。
- 新document-batch-1和document-boundary-1契约、源元数据版本与冻结快照/范围核验；validated批次立即保存。失败原始响应不落库或日志，仅同进程内可用于一次已授权格式修复。中断后成功批次复用，未完成请求须用户明确继续，结果不确定可能再次收费。
- 格式修复默认关闭，独立授权后每抽取批次最多1次，发送该批响应/Schema/安全错误，不上传PDF。第二次仍严格校验，并保护文字、公式表格、页码、归属与顺序；无法证明仅格式调整时拒绝。
- 边界仅按末首片段续接标记按需复核，最多B−1次，使用相邻原始2页和两个片段；模型只决定merge/separate/uncertain。程序确定性拼接；简单同列表格仅精确去重明确重复表头，复杂情况保留needs_review。不能宣称全论文语义无缝。
- UI显示批次/原始页/已校验/请求预算/修复/边界进度及脱敏字段错误。初始预算B＋授权边界最多B−1＋授权修复最多B；每批至多3次用户显式执行，继续会增加预算。修改批次/修复授权选项重置联网勾选；600/1800为单请求时限，准备阶段也有取消与默认1800秒deadline，不是整篇SLA。
- lite0013加性迁移并先备份；旧任务未开批次保持整篇原路径。清旧保留模型批次，删论文清理关联批次、保留引用PDF。用量按实际抽取/修复/边界请求汇总，缺失usage或价格保留unknown，不把未知费用写零。

## 已执行专项

最终运行源已冻结。完整后端在最后的边界质量保护修正后重新执行，React/Edge之后未再修改前端运行源；下面的专项集合与完整集合有重叠，不能相加当作独立总数。

| 检查 | 实际结果 | 证据 |
| --- | --- | --- |
| 最终完整后端 | 562 passed / 1 skipped / 1 warning，105.55秒 | backend-release.log；含最后4组状态保护回归 |
| 最终完整React | 15 files / 133 passed，13.93秒 | frontend-final.log |
| 最终完整Edge | 19 passed，13.1秒 | browser-final.log；实际React组件 |
| 最终静态检查 | Ruff、mypy 85 source files、TypeScript/ESLint和契约导出通过 | 主代理实际执行；不把过滤或跳过记通过 |
| 分页契约/传输及关联旧传输 | 102 passed / 1 warning，4.48秒 | transport-final-tests.log、transport-agent.txt |
| 存储/升级/清理/公开Schema关联 | 48 passed / 1 warning，13.37秒 | storage-tests.log、storage-agent.txt |
| Rust head/兼容专项 | 2 passed，12 filtered | storage-rust-schema-tests.log |
| 用量汇总与既有用量 | 16 passed / 1 warning，4.36秒 | usage-tests.log、usage-agent.txt |
| 当前集成专项 | 122 passed / 1 warning，23.19秒 | integration-tests.log |
| UI首轮完整React | 15 files / 129 passed，14.32秒 | frontend-agent.txt；后续JobHistory新增项不冒充该轮完整重跑 |
| 批次UI重点组件 | 5 files / 19 passed，2.41秒 | frontend-agent.txt |
| JobHistory收费续接提示 | 14 passed，2.43秒 | browser-agent.txt |
| Edge实际React组件 | parsing.spec.ts 3 passed，2.6秒；其中新增2项 | browser-agent.txt |
| 静态检查 | 各负责范围Ruff/mypy、TypeScript/ESLint、Prettier和限定diff检查通过 | 对应agent报告；最终全范围由主代理记录 |

证据目录为源码根下 .local/verify/document-batches-20261118/。现有warning为Starlette/httpx TestClient deprecation，不作新增功能故障；跳过/过滤不计通过。

Edge覆盖默认本地入口、模型批次默认5页/共享1页、修复默认关闭、费用与请求预算、修复/页数修改后的联网重置、实际提交字段、仅有document_batches时的进度、字段错误安全投影及正文屏蔽。620px弹窗仍跟随视口并可滚动；两张批次授权与诊断截图已目检。其模拟数据不等同真实模型识别。

独立只读worker审查发现并推动修正续接快照/范围复验、准备取消与deadline、核心页覆盖、合并质量从严、聚合校验脱敏和修复内容/归属/顺序保护。最终又发现不确定边界会把 unavailable/failed 改为 needs_review，已修正为仅降级 ok/degraded，4组回归同时验证原检查点不被修改。worker-audit.txt 与 worker-audit-final.txt 保留发现历史及修复确认，不将只读审查冒充测试。

## 本机HTTP与恢复链路

使用匿名合成7页PDF及127.0.0.1模拟Provider，开发sidecar的 chat_images 和 chat_file 均实际通过：每批3页，核心1–3/4–5/6–7、发送1–3/3–5/5–7，检查原页序、像素标签或分割PDF。共5次POST（3抽取、1纯文本修复、1边界复核），预算8，最终3/3批次与2/2边界完成，保留6段含公式和表格的材料及3/4页合并来源。公开Job GET分别70次/61次无500；模拟Token合计150、修复1次、费用未知，重启后零追加POST。证据为 smoke-development-final 与 smoke-development-file 内 verification.json；这些都是本机测试，不是供应商或真实论文验收。

## 操作

1. 设置中选择实际支持PDF文件或图片输入的论文解析模型；连接测试通过不证明输入能力。
2. 导入或在论文页“使用模型重新解析”，保留“按页分批解析（顺序执行）”，选择每批2–8页。边界检查可关闭；格式修复默认关闭，阅读额外费用提示后再自行授权。
3. 确认联网授权后提交。界面显示B公式，准备完成后显示实际批次和请求预算；概览/全文精读/翻译单独选择和计费。
4. 失败时先查看安全字段路径、批次、页码与请求阶段。明确继续只处理未成功批次；已发未定请求可能已经计费，不能视为免费重试。此前未分批的420秒契约失败任务点击旧“重试”仍走旧计划，不会升级为分批；要使用本轮分页或格式修复，必须在论文页点击“使用模型重新解析”创建新任务并确认选项。修改模型配置同样需创建新任务，旧任务续接仍沿用冻结配置。

## 安装与交付

本轮最终安装包于2026-11-18 20:28:56（Asia/Shanghai）构建成功，为未签名 [ResearchGraph Studio Document Batches](../.local/releases/document-batches-20261118/ResearchGraph-Studio-Document-Batches-0.0.1-x64-setup.exe)，160,485,540 bytes（153.05MiB）。160项运行源/配置在构建前冻结、构建后及最终复核均一致。未将旧18:34包冒充本轮包。

- Windows PowerShell5.1隔离安装通过，schema lite0013；覆盖重命名、旧本地清理、原paper_id本地重建、模型三类材料与章节进度保留、删论文404和引用PDF保留。仅安装至本轮.local隔离目录，没有替用户安装日常目录。证据 installed-acceptance/verification.json。
- 安装版 chat_images 与 chat_file 两条本机模拟HTTP链均通过：每条5次POST、3/3批次、2/2边界、1次纯文本修复、6段材料覆盖7页，3/4页来源合并；公开Job GET分别77次/64次无500。请求日志确认分割页与页序、修复无PDF或图片，重启后零追加POST；公开用量5调用/1修复/150模拟Token，费用未知。证据 smoke-installed-images 与 smoke-installed-file 内 verification.json。
- 安装版Rust Host 14 passed / 0 ignored，2.82秒，含真实sidecar启动与重启。sidecar可执行文件和324项内部安装资源与本轮构建逐文件配对。证据 host-final.log 与 artifact-verification.json。
- 最终私人路径规则/Gitleaks内容检查395 files passed，git diff --check通过；6份当前说明135个本地链接、0 missing。汇总在本轮final-summary.json与安装器同目录verification.json，安装器和测试数据均位于.local忽略目录。

真实模型调用、外部HTTP及正式库实验为0；未读取私人论文或凭据，未Commit/Push。用户原生GUI、真实供应商文件/图片能力、真实论文公式/表格与跨页准确性、干净机兼容均未验收。模拟Token不是实际模型用量，隔离安装与HTTP测试不能替代科学质量验收。

页码覆盖是模型的结构声明，stat源版本不是等字节核验；无续接标记会跳过边界模型，复杂表格保留片段，格式修复可能被保守保护拒绝。整篇可能依然等待较久，不能保证收费更少或单次请求必定成功。
