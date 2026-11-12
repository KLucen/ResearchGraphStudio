# ResearchGraph Lite 进度

更新：2026-11-12 11:56（Asia/Shanghai）。

## 当前状态

本地工作区已按用户 2026-11-12 的要求撤下文献翻译，保留 Lite P0、PaperCard + LightGraph、章节精读、证据问答、英文关键词辅助、模型配置和项目导航。阅读工作区置顶，论文信息在底部独立默认折叠。当前数据库保持 `lite0008` 以兼容已有数据，不降级、不重建、不删除历史成果；旧翻译任务不恢复或重发。撤下边界见 [ADR0040](adr/0040-remove-pdf-translation.md)。下方 2026-11-11 的翻译测试、安装包和 GitHub 记录均为历史，不表示当前工作区仍提供翻译功能。

撤回源码已按用户新增授权普通推送至 GitHub `main`，提交 `a2ed78f9db31f7d61dcc79a707bdfaea0d4a210b`。本机安装包保持下方已验证版本；远端 CI 状态单独记录，不与本机成绩混用。

| 能力                                               | 实际状态                                                                                                                                                                         |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tauri 2 + React/TypeScript + FastAPI + SQLite/FTS5 | 保留并已精简，静态检查通过                                                                                                                                                       |
| Zotero 连接、论文选择、PDF/章节解析、文本索引      | 已实现；选择和本地解析阶段 0 次模型调用                                                                                                                                          |
| Lite 模式、`lite0008`、用量与缓存基础              | P0 已实现；保留既有迁移链及翻译表兼容映射，已有 Lite 数据、历史运行快照和用量保持；翻译业务已撤下 |
| PaperCard + LightGraph                             | P1 联合抽取、缓存、任务、布局 API 与交互已实现；由一次模型调用生成                                                                                                               |
| 图谱交互                                           | 已支持节点拖动、缩放、点击详情、关系详情、布局/相机持久化和重置                                                                                                                  |
| A 章节导读                                         | P2 已实现：单节显式生成、quick/standard/deep、缓存/失效、证据白名单、复制导读                                                                                                    |
| D 证据问答                                         | P3 D01 已实现最小闭环：section/paper/selection 契约、FTS5 Top-K Span、显式授权、严格引用校验、缓存、失败/取消/重启记录和桌面问答区；D02 已实现为本地无命中后的可选英文关键词辅助 |
| 完整图谱抽取、跨论文推理、Lint/Wiki                | 已从活跃 Lite 工程移除；历史工程只保留在备份分支                                                                                                                                 |
| 设置与阅读信息架构                                 | Lite 用量在设置与诊断中按全部项目查看；模型连接单独保存 Base URL/API Key；论文阅读工作区保留论文概览、章节精读、论文问答三个独立板块 |
| 文献翻译                                           | 已按用户要求撤下界面、业务 API、执行器、模型代理、服务启停和打包资源；历史记录只读，未完成任务停止为已取消，不删除旧文件 |

## 2026-11-12 · 撤回版本 GitHub 交付

用户在本地交付后明确要求“push到github”。提交前核对 `main`、官方 origin 和 60 个显式路径；当前全部 260 个源码文件的内容/私人路径规则及 Gitleaks 通过，提交前全部 Git 历史 37 个提交扫描通过。暂存区的 39 个新增/修改文件内容扫描通过，另 21 个删除路径已核对；`git diff --cached --check` 通过。没有上传凭据、私人论文、数据库、日志、翻译资源或安装器。

默认 HTTPS 连接失败，按 github-transfer 技能使用已验证主机密钥的官方 SSH443，认证、远端基线与 fetch 核对通过，先 dry-run 后普通 push；没有 force push，也没有改变 origin、全局 Git 或网络设置。源码提交 `a2ed78f9db31f7d61dcc79a707bdfaea0d4a210b` 已成功推送，官方远端 refs 返回同一 SHA。

GitHub Actions `Windows build and acceptance`，run `43151333334`，head SHA 为上述源码提交；11:56 查询为 `in_progress`、conclusion 为 null，尚不宣称远端 CI 通过。本次只提交/上传已验收源码并补交付记录，没有重新运行完整开发测试或真实模型。本机安装包 SHA 仍为 `B01F56AF08D2CBB0C2D0E2591D12038430FDC2D2BD3B82D19EAC630E2C652835`，运行源和安装内容未变；其后仅补本文档和开发日志。

## 2026-11-12 · 撤下文献翻译并交付轻量安装包

用户反馈 `TRANSLATION_PROVIDER_TRUNCATED` 后明确要求退回没有翻译功能的版本。本轮定向移除翻译功能，没有整体回退同时包含阅读/导航/模型配置改进的提交。保留论文概览（PaperCard + LightGraph）、章节精读、论文问答、Zotero、本地解析/索引、英文关键词辅助、项目树、模型连接、统一用量和底部折叠信息卡。

前端翻译板块、设置、DTO/API 和样式已删除；后端翻译路由、执行器、代理、外部服务与随包 CLI 已删除；Rust 宿主删除翻译文件操作并拒绝旧路由；构建和 CI 不再下载、准备或分发翻译运行环境。OpenAPI 与 TypeScript 契约已重新导出，不含翻译 API/DTO。旧本地资源、安装包和生成文件没有被主动清除。

Alembic head 保持 `lite0008`，既有迁移和表映射仅作兼容，不降级、不重建数据库。启动/领取时将旧 queued/running 翻译停止为已取消；retry 在幂等重放之前拒绝，GET 不推进。旧完成/失败等终态、快照、实际/未知 usage 和文件保持；历史特殊阶段只在 DTO 展示时映射，避免历史详情/列表报错，不改终态原始行。兼容验证使用隔离合成数据，没有读取或修改正式用户库。

实际验证：

- 后端 `python -m pytest -q`：**204 passed / 1 skipped / 1 warning，73.63 秒**；回退与迁移专项 **19 passed，7.22 秒**。覆盖历史库逐表保持、旧任务不发网络/不启动子进程、幂等重放阻断、CLI 参数拒绝及旧阶段展示。跳过为本机符号链接权限，警告为既有 Starlette/httpx 弃用。Ruff、71 文件格式、mypy 49 源文件通过，另 4 个 Python 脚本 Ruff/格式和 `pip check` 通过。
- 前端 TypeScript/ESLint、Prettier、**6 files / 51 passed（10.41 秒）**及生产构建通过。浏览器真实图谱 **2 passed（7.5 秒）**，含拖动、固定、缩放、选择、轮询和重载布局。初次加载超时及中间代理假设保留；构建结束后的串行对照中，原 Vite 监听仍有 1 失败/1 通过，仅排除 `src-tauri/**` 监听后两项通过。最终未改变 Edge 代理、断言或超时，仅调整开发服务器监听；最终生成的前端文件与安装包构建时逐字节一致。既有 531.42KB chunk 提示仍在。
- Rust fmt/clippy 通过；`RGS_TEST_ENGINE_PATH` 指向最终安装后的引擎，`cargo test --locked -- --include-ignored`：**9 passed / 0 ignored**，含原生宿主启动、重启和翻译路由拒绝。
- `scripts/build-windows.ps1` 使用项目 Conda Python 和 PowerShell 7 完成 PyInstaller、Tauri、NSIS。构建后 **49 个 Python 源文件哈希保持**。Windows PowerShell 5.1 隔离静默安装通过，安装后引擎 SHA 与封存一致；schema `lite0008`，匿名 PDF 解析/索引 **0 模型调用、0 输入/输出 Token**，翻译 API 404，安装目录无 `translation-runtime`。首次安装验证在默认 fixture 参数求值时退出，尚未安装；将路径默认值移至参数绑定后，使用默认 fixture 重跑通过。
- 内容/私人路径规则与 Gitleaks **260 文件**通过；改动涉及的 **18 个文档 / 93 个本地链接**均存在，最终 `git diff --check` 通过。暂存区为空，未 Commit/Push，未启动远端 CI。

本轮最终未签名 Windows 安装包：`.local/releases/lite-no-translation-20261112/ResearchGraph-Studio-Lite-No-Translation-0.0.1-x64-setup.exe`，**38,407,246 bytes（36.63 MiB）**，SHA-256 `B01F56AF08D2CBB0C2D0E2591D12038430FDC2D2BD3B82D19EAC630E2C652835`。同目录完整 `researchgraph-engine/` 包含 `_internal/`；引擎 EXE **15,081,736 bytes**，SHA-256 `33CCF7DE718E8AC9218D2889E749159F607445A06011834348723C9A38571461`，不能只复制引擎 EXE。安装验证位于 `.local/verify/lite-no-translation-20261112/`，构建/静态/安全资料位于 `.local/pdf2zh-audit/rollback-*`；图谱失败与串行对照位于 `.local/verify/translation-rollback-20261112/frontend-browser/`，均被忽略。

本轮真实模型调用、真实输入/输出 Token、真实重试和新增费用均为 **0**。没有覆盖用户日常安装、清空正式数据或读取正式 Key/私人论文/Zotero 库。隔离安装与原生宿主验证不等于干净机或用户正式库 GUI 验收；新版用户界面反馈仍待。退出旧版后可安装此包，无需手工删库或重新导入已有论文。

## 2026-11-11 · GitHub 交付记录

用户在本轮验证完成后明确要求 push。已将此前未上传的 Lite 清理/P0 提交及当前经验证的阅读、模型配置、导航、随包翻译和代理修复一并普通推送至 `KLucen/ResearchGraphStudio` 的 `main`。运行源码提交为 `e399357b36f70881a2eca1f701939bbc43d3454f`，推送后通过官方远端 refs 核对同一 SHA。默认 HTTPS 连接失败，使用已验证主机密钥的 GitHub 官方 SSH443，先 dry-run 后普通 push；origin 的 HTTPS 配置、全局 Git/网络设置均未修改，没有 force push。

提交前逐项核对98个源码/迁移/测试/契约/文档/脚本路径，源码内容扫描278文件、暂存内容98文件及全历史Gitleaks均通过；无私人论文、数据库、Key、运行日志、安装器或随包二进制。两处个人Skill安装路径改为环境变量示例，ADR日期行尾空格在暂存差异检查发现后已修正，最终暂存差异检查通过。

GitHub Actions `Windows build and acceptance` 已启动，run `43049353054`，源码 SHA 为上述提交；记录时状态 `in_progress`，**不宣称远端CI通过**。本机最终安装包与验证结果仍以下方记录为准；后续仅补交付文档，不改变运行源码或本机包。

## 2026-11-11 · 翻译代理兼容与错误分类

用户反馈的历史错误码是 `TRANSLATION_PROVIDER_FAILED`。旧后端将模型服务失败、预算及协议问题统一显示为“模型代理预算或请求校验失败”；这个码不足以还原该次失败的 HTTP 或响应原因，不能认定用户一定发生参数错误或 HTTP 400。

已修复可由代码确认的参数兼容缺陷：新建随包任务冻结 `text-chat-minimal-1`，复用模型连接、ID、凭据引用、超时和已知输出能力，但不重新注入阅读 Profile 的 temperature/top_p/reasoning_effort 或适配器附加字段。策略进入预检和缓存身份；旧无字段任务的快照、参数策略、缓存键及旧译文访问保持。Schema 仍为 `lite0008`，没有数据库迁移。

代理校验 SDK 的有限兼容字段后重建冻结请求，仍拒绝流式、工具、结构化输出和未知字段。上游鉴权、限流、其他 4xx、截断及响应格式错误分别显示具体代码和中文提示；未知结束状态不推定为 stop。失败后撤销临时票据，SDK、worker 和 GET 不得触发自动收费重发；已返回 usage 保留，缺失仍未知。用量审计只增加实际上游字段名，不记录正文、凭据、票据或上游错误正文。详见 [ADR0039](adr/0039-translation-proxy-request-policy.md)。

实际验证：

- 代理/API 专项 **81 passed / 1 warning，9.09 秒**；最终后端全量 **355 passed / 1 skipped / 1 warning，65.18 秒**。跳过为本机符号链接权限，警告为既有 Starlette/httpx 弃用。Ruff、格式 **91 files** 和 mypy **54 source files** 通过。前端未因本修复改动；本轮早先 TypeScript/ESLint/Prettier 与 **7 files / 61 passed** 通过，最终生产构建再次通过，保留既有 549.60KB chunk 提示。
- `scripts/build-windows.ps1` 使用项目 Conda Python 完成资源复核、PyInstaller、Tauri 与 NSIS；最终引擎封存后 **54 个 Python 源文件哈希未变化**。PowerShell 7 执行完整构建，本轮不将其冒充为整个构建脚本的 PowerShell 5.1 验证。
- 最终安装器隔离静默安装通过，schema `lite0008`、bundled 默认和资源检查正常；匿名 PDF 解析/章节索引 **0 模型调用**。安装后引擎 SHA 与封存副本一致。`RGS_TEST_ENGINE_PATH` 指向该安装后引擎，`cargo test -- --include-ignored`：**9 passed / 0 ignored**，含原生 Host 启动与重启。
- **安装后实际随包 CLI 增强 smoke 通过**：mono **42.922 秒 / 175,012 bytes / 2页**，dual **47.969 秒 / 177,747 bytes / 2页**，中文文本、双语页宽及各自整篇缓存命中均通过。所选 Profile 显式配置 temperature/top_p/reasoning_effort，合成 Provider 若收到这些字段即拒绝；实测出站字段只有 `max_tokens/messages/model`。
- 该独立安装 smoke 合成 Provider **27 次**：mono13、dual13、HTTP400负向1。负向约 **7.828秒**进入 FAILED，显示 `TRANSLATION_PROVIDER_REQUEST_REJECTED` 及具体中文，重试0、无产物、不回显上游模拟私密正文；再次GET不调用模型。两个成功格式的模拟 usage 合计442输入/182输出/624总 Token，HTTP失败无usage仍未知。这些都是固定夹具，不能作为真实 Token、真实质量或费用成绩。源码增强 smoke 另行通过，数据与安装版本分开记录。
- 封存最终 sidecar 的 manual/managed 合成协议 smoke 分别通过；各1次合成 Provider、17/7/24模拟 Token、2次缓存命中，managed完成前确认端口释放。首次 managed 命令漏传必填 `--runtime-python`，解析参数即退出、未执行验证；补齐参数后通过，不把首次记成测试通过。
- 源码内容/私人路径规则与 Gitleaks **278文件**通过；29个本地文档链接及 `git diff --check` 通过。暂存区为空，未提交或上传。

最终 Windows 安装包：`.local/releases/translation-proxy-fix-final-20261111/ResearchGraph-Studio-Translation-Proxy-Fix-0.0.1-x64-setup.exe`，**754,646,101 bytes（719.69MiB）**，SHA-256 `11D9F2ADAFC639DC334D9FE15AB383864C5875AC1173C4CF99F2ACB8C6FE944F`。同目录完整 `researchgraph-engine/` 保留 `_internal/` 与 `translation-runtime/`，EXE **15,174,112 bytes**，SHA-256 `1B71C55505DD4A849776F212AEF6E9D3E61377381E6D5CAE02196CE02C5BAB31`，不能只复制该EXE。未签名；本轮中间包与旧包保留，不作为最终交付。资料位于忽略目录 `.local/pdf2zh-audit/proxy-final-*`、`.local/verify/translation-proxy-fix-final-20261111/`。

本轮真实模型调用、真实输入/输出 Token、真实重试及增量费用均为 **0**；未读取正式 Key、用户运行库、私人 PDF 或 Zotero 正式库，未 Commit/Push。用户原任务的准确上游原因仍未知，旧失败及其实际/未知用量保留；修复版本的用户 Provider、真实译文科学质量、复杂版式、干净机与用户原生界面体验仍待反馈。使用新包后重新预检并显式提交新任务，不自动续发失败任务。

## 2026-11-11 · 内置翻译运行时与阅读布局

按用户最新要求，Windows 安装器提供完整翻译核心及运行环境，默认 enabled/bundled。只在用户明确授权的非缓存翻译任务中无窗口启动；翻译结束、失败、取消或退出时回收本应用的进程树。无需另装 Zotero XPI、Server 或 Python，也无需配置解释器和脚本路径。高级外部 managed/manual 继续可用。来源 PDF 不覆盖，模型只接收翻译文本与提示，真实 Key 继续留在本机模型代理中。

新界面默认生成左右双语 PDF，可选择仅中文 PDF。`output_mode` 进入预检指纹、任务与缓存键；切换格式须重新预检，只有所选文件通过校验才发布。API 缺字段及旧历史保持 both；`lite0008` 加性升级保留原论文、章节、用量、旧译文、外部路径及任务快照，缺快照的旧任务仍按 manual 解释。升级前自动备份，不重新初始化数据库。

阅读工作区和四个功能入口置顶。完整标题、分类、Zotero 打开、修订、解析警告、来源检查及原文移到页面末尾的独立“论文信息”卡，默认折叠；解析原文进一步按需加载，切论文恢复折叠。

实际验证：

- 后端全量 `python -m pytest tests/engine -v`：**330 passed / 1 skipped / 1 warning，95.16 秒**。跳过是本机符号链接权限，警告为既有 Starlette/httpx 弃用提示。包含输出模式/缓存、lite0006/0007 升级保留、内置 adapter 的固定参数/鉴权/路径/产物、无启动预检、进程归属及失败/取消清理。
- TypeScript、ESLint、Prettier 通过；前端 **7 files / 61 passed**，其中翻译 16、阅读 24。覆盖首屏顺序、默认折叠、原文按需读取、dual/mono、切格式预检失效及高级外部模式。生产构建通过，保留既有 **549.60KB** JS chunk 提示。
- Ruff 与 Python 格式 **88 files**、mypy **54 source files** 通过；Rust fmt/clippy 通过。Rust 含打包原生 Host **9 passed / 0 ignored**；安装后的引擎 Host 启动/重启另跑 **1 passed**。
- 源码及封存 sidecar 使用**实际随包 CLI**连接本地合成 Provider，匿名两页正文样例 mono/dual 均完成且各自整篇缓存命中不再调用。每个独立双模式 smoke 合成 Provider **26 次**（每格式13），模拟 usage 合计输入 **442** / 输出 **182** / 总 **624**；这些固定合成数字不是真实 Token。封存 sidecar 还验证实际中文文字和左右双语页面宽度。最初极稀疏 fixture 被上游判为扫描件，应用正确拒绝发布；该失败保留，不改成通过。
- Windows PowerShell 5.1 资源准备、重复校验及坏缓存拒绝通过；固定官方下载校验后，完整保留 Python、依赖、字体/模型/分词/CMap 资源和原始许可证，并提供匹配版本的第三方源码资料。运行资源共 **25,263 文件 / 1,457,616,856 bytes**，其中来源材料 **221,829,005 bytes**。构建脚本与 CI 均接入资源准备，资源和源码压缩包不进入 Git；本轮没有上传或运行远端 CI。
- `scripts/build-windows.ps1` 完整 PyInstaller/Tauri NSIS 构建通过。最终安装器隔离静默安装成功，schema lite0008，默认 bundled 已启用，安装资源校验通过，匿名 PDF 解析/章节索引 **0 次模型调用**，安装后引擎 SHA 与封存副本一致。**安装后实际 CLI 双模式 smoke 通过**：mono **44.500 秒 / 175,012 bytes / 2页**，dual **38.281 秒 / 177,747 bytes / 2页**；中文文字、双语宽度与两种整篇缓存复用均检查通过。该独立 smoke 合成26次、模拟442/182/624 Token，与源码/封存引擎测试分开记录，真实模型仍0。
- 封存引擎的旧 manual/managed 合成 HTTP smoke 分别通过，各为 **1** 次合成 Provider、**17/7/24** 模拟 Token及 **2** 次缓存命中；managed 完成前确认端口释放。
- 内容/路径及 Gitleaks 扫描 **277 文件**通过；`git diff --check` 通过，无暂存、Commit 或 Push。

可启动 Windows 安装包：`.local/releases/bundled-translation-20261111/ResearchGraph-Studio-Bundled-Translation-0.0.1-x64-setup.exe`，**753,899,166 bytes（718.97 MiB）**，SHA-256 `EAD2191E9E3F95494A935D32FDC472FEDB0658D63D292AC7D9E5C4422CBA1C06`。完整 sidecar 位于同目录 `researchgraph-engine/`，包含 `_internal/` 与 `translation-runtime/`，EXE **15,171,417 bytes**，SHA-256 `D98728D461E61A2646BB89B48AB8D30E4F24CC45B540B1596A538FE9D9AAF9E8`；不要单独复制其 EXE。未签名，隔离验收资料在 `.local/verify/bundled-translation-20261111/`，构建/测试报告在 `.local/pdf2zh-audit/`，均被 Git 忽略。

本轮真实模型调用、真实输入/输出 Token、真实重试和增量费用均为 **0**。未读取正式 Key、数据库、私人 PDF 或 Zotero 正式库。实际引擎合成联调只验证运行与产物，不代表真实论文翻译准确性、复杂公式/表格或干净机器兼容性；用户原生桌面体验仍待反馈。没有执行两个随包 VC++ 安装器或更改系统全局依赖，不能将本机隔离安装当成干净机验收。说明见 [文献翻译](pdf-translation.md) 和 [ADR0038](adr/0038-bundled-translation-and-reading-layout.md)。

## 2026-11-11 · 翻译服务按需自动启停

设置增加“按需自动启停（推荐）”和“手动连接服务”，支持浏览选择 Python 解释器与专用 `server.py`。首次仍需在工程之外安装完整 Server 4.1.8 / pdf2zh_next 环境；之后无需手动打开或关闭命令窗口。新安装无设置行时推荐 managed；`lite0006 → lite0007` 加性迁移将已有设置保持为 manual，并保留原有论文、解析、用量和译文，升级前自动备份。

配置检查和预检只读验证本机路径、脚本版本与端口，不执行 Python 或启动服务，也不证明排版依赖完整。只有非缓存、明确授权的翻译任务才启动服务；创建时冻结 `runtime_snapshot`，后续设置变化不会改写已排队任务。健康检查、提交、每次轮询及其历史回退、下载前重验自建进程与监听端口归属，失去归属时停止并保留诊断，不接管替代服务。

Windows 通过 CreateProcess 的 Job List 原子绑定专属 kill-on-close Job，隐藏窗口并仅继承 NUL 标准句柄；回收只针对自建树，不按进程名称杀 Python 或 Zotero。正常成功先下载、验证和保存译文，再确认 Job 活动进程数归零，最后发布 COMPLETED；失败、取消和正常退出也回收自建树，硬崩溃由 Job 句柄关闭清理。停止无法确认时不发布成功。任务界面增加启动与关闭阶段；取消后的最终清理警告可能在重新进入页面后显示，当前提示只表示请求关闭。

实际验证：

- 后端全量 `python -m pytest tests/engine -v`：**258 passed / 1 skipped / 1 warning，67.27 秒**；跳过为本机符号链接权限条件，警告为既有 TestClient/httpx 弃用提示。取消清理提示最终修补后，API 专项再次 **19 passed**。首次 `-q` 运行以退出码 1 提前结束、没有完整报告，不作为通过成绩；随后上述全量与专项成功。
- Runtime 专项包含真实合成 Server/子/孙三层进程、占用端口不接管、运行期端口被替代、启动超时/早退/版本错误、取消及 owner 被强制终止后的 Job 回收。Bridge 专项验证每个 HTTP 请求前检查，包括 history 回退；服务停止未确认不得发布成功。
- `pnpm --dir apps/desktop check`、`pnpm format:check` 通过；Vitest **7 files / 54 passed**。Ruff、Python 格式检查 **83 files**、mypy **52 source files**、Rust fmt 通过。
- `cargo test -- --include-ignored`：**9 passed / 0 ignored**，含最终打包引擎的 Host 启动与重启；安装后的最终引擎另跑 Host **1 passed**。
- `scripts/build-windows.ps1` 通过 PyInstaller 与 Tauri NSIS 构建。前端产物仍有约 **546.51KB** JS chunk 提示，不影响构建。
- 源码和最终打包引擎的自动/手动合成翻译 smoke 均通过；安装后引擎的自动模式 smoke 再次通过。自动模式实际创建后台合成服务进程，COMPLETED 时端口已释放，整篇缓存不再启动。每个独立 smoke 为合成 Provider **1** 次、**17 输入 / 7 输出 / 24 总 Token**、**2** 次缓存命中；模拟产物为匿名原 PDF，不能作为真实翻译或真实 Token 成绩。
- `verify-windows-install.ps1` 隔离静默安装通过：schema `lite0007`、默认翻译关闭、匿名 PDF 解析/章节索引、本地处理 **0** 次模型调用；安装后引擎 SHA 与封存 sidecar 一致。
- `scripts/check-sensitive.py --gitleaks .local/tools/gitleaks-8.24.3/gitleaks.exe`：**267 文件**内容/路径及 Gitleaks 扫描通过；`git diff --check` 通过。没有暂存、Commit 或 Push。

本轮可启动安装包：`.local/releases/managed-translation-20261111/ResearchGraph-Studio-Managed-Translation-0.0.1-x64-setup.exe`，**38,482,111 bytes**，SHA-256 `8BFB67708455E45BB87CE6202AE5763E5818A92A9A773175ED48A19AD24E598C`。完整 sidecar 位于同目录 `researchgraph-engine/`；EXE **15,149,511 bytes**，SHA-256 `F4C9806BFFBC60BF135AAD429A7966C6DEE7E22834AA3EEC05A114A3C794BA66`，须保留 `_internal/`。安装器未签名，隔离验收材料在 `.local/verify/managed-translation-20261111/`，均不进入 Git。

本轮真实模型调用、真实输入/输出 Token、真实重试和增量费用均为 **0**。没有读取正式 API Key、数据库、私人 PDF 或 Zotero 正式库；独立外部 Server/排版引擎仍未实际安装运行，真实译文、复杂版式、公式/表格、OCR/字体和用户桌面原生体验仍待验收。外部启动已关闭环境创建与源码更新，但通知检查和首次资源下载仍可能联网，不能宣称完全离线。使用说明见 [文献翻译](pdf-translation.md)，决策见 [ADR0037](adr/0037-managed-translation-server.md)。

## 2026-11-11 · 可选版式文献翻译

论文阅读工作区增加独立“文献翻译”板块，设置与诊断增加默认关闭的本机翻译服务配置。复用已保存的模型 Profile 和连接，不需要重复输入 API Key。本轮适配 `zotero-pdf2zh@e783bb9ffd5cf3caf0efbb2cfd4d19f8d9f8a09e` 自报 Server **4.1.8** 的 `pdf2zh_next / OpenAI` 协议；不捆绑外部源码、Server 或排版引擎，用户须独立安装专用本机服务。只支持全文英文到简体中文，同时请求中文与左右双语 PDF。

预检不调用模型，并用 `prepare_fingerprint` / `expected_fingerprint` 绑定来源字节、模型/连接/凭据引用、服务与版本、输出选项及预算；变更后重新预检。非缓存任务须显式确认模型外发和专用服务/留存副本。每个任务启动一次性 loopback 模型代理，外部服务只得到短期票据；真实密钥保留在系统凭据存储，模型响应若回显密钥会被拒绝，已产生用量仍保留。代理执行请求数和累计 UTF-8 输入字节估算限额，单请求输出最多 8192 Token（已知能力更低时取低值）；这些限制不是费用硬上限。

原 PDF 不覆盖，来源读取时校验实际字节 SHA-256。译文保存到受管的 `translations/<translation_id>/{mono,dual}.pdf`，下载与打开检查文件名、路径、大小、PDF 页结构和哈希；不进入作者原文 Span、FTS5 证据或 LightGraph，不自动回写 Zotero。整篇缓存和任务内相同成功请求可复用，外部缓存关闭。发布前要求有成功模型账本且无失败/在途请求；只显示“引擎已生成，全文质量尚未验证”。取消撤销票据、阻断新请求并尽力关闭本机在途连接；外部服务没有停止子进程 API，排版可能继续。重启不自动续发，任务中心禁止通用重试。

实际验证：

- `python -m pytest tests/engine -q`：**230 passed / 1 skipped / 1 warning，61.17 秒**；包含翻译 API、Bridge、代理、迁移与既有阅读功能。最后凭据回显保护后的代理专项 **24 passed**。
- `pnpm --dir apps/desktop check`、`pnpm format:check`：通过；Vitest **7 files / 49 passed**，覆盖最终预检指纹、授权、预算失效、版本隔离、打开、取消和缓存。生产构建通过，保留既有约 542.53KB JS chunk 提示。
- Ruff、mypy **50 source files**、Rust fmt：通过。`cargo test -- --include-ignored` **9 passed / 0 ignored**，包含最终打包引擎的原生 Host 启动和两次握手/停止；安装后的引擎另跑 Host 测试 **1 passed**。
- `lite0005 → lite0006` 迁移测试通过：升级前自动备份，来源、历史用量、外键/数据库完整性和 FTS5 保留；没有对正式库升级作实验。
- `scripts/build-windows.ps1` 完成 PyInstaller 与 Tauri NSIS 构建；最终侧载引擎和隔离安装后的引擎均通过 `scripts/smoke-translation.py --executable ...`。协议测试走实际 HTTP → Bridge → 临时代理 → 合成 Provider → 受管 PDF 下载；每个独立 smoke 中合成调用 **1**，输入 **17** / 输出 **7** / 总 **24** Token，缓存命中 **2**。匿名 PDF 被作为模拟产物返回，**不是实际翻译，也不是本轮真实 Token 用量**。
- `scripts/verify-windows-install.ps1 -Installer ... -ExpectedSha256 ...`：隔离静默安装、schema `lite0006`、默认翻译关闭、匿名 PDF 本地解析通过，导入阶段模型调用 **0**。安装后引擎 SHA 与封存 sidecar 一致。
- `scripts/check-sensitive.py --gitleaks .local/tools/gitleaks-8.24.3/gitleaks.exe`：**262 文件内容/路径扫描通过**；`git diff --check` 通过。本轮不 Commit/Push。

最新可启动安装包：`.local/releases/pdf-translation-20261111/ResearchGraph-Studio-PDF-Translation-0.0.1-x64-setup.exe`，**38,452,244 bytes**，SHA-256 `25983BFC1F5BC182B02CE71A0AAA3A7897652BF25974A3879FEE96BF0B5084A1`。完整 sidecar 在同目录 `researchgraph-engine/`，EXE **15,126,340 bytes**，SHA-256 `D7321D2DA5096260BC9D25634A03B03789936453F1B41004143871BCBEC61365`；必须携带 `_internal/`，不要单独复制 EXE。包未签名，构建与隔离验收材料在忽略目录，不进入 Git。

本轮真实模型调用、真实输入/输出 Token、真实重试与增量费用均为 **0**。没有读取正式 API Key、正式数据库、Zotero 正式库或私人 PDF。**独立外部 Server/引擎尚未实际安装运行**，复杂版面、公式/表格、OCR、字体、实际译文质量、真实 Provider 费用和用户桌面原生体验均未验收；源码与合成协议通过不能替代这些项目。使用步骤见 [文献翻译](pdf-translation.md)，决策见 [ADR0036](adr/0036-optional-pdf-translation-bridge.md)。

## 2026-11-10 · 模型提供商设置重排

设置页的模型配置已按提供商卡片重排：常见的 DeepSeek、OpenAI、OpenRouter、SiliconFlow、智谱 AI、通义千问和本机 Ollama 作为可编辑的兼容接口预设；“自定义模型 API”提供 Provider ID、显示名称、API 地址、当前支持的 OpenAI Chat Completions 协议、API Key 和本地模型目录。一个提供商可以维护多个模型，模型目录保存为现有的 Lite model profile，并可在论文概览模型、章节精读与问答模型中分别选择。

API Key 仍只写入系统凭据存储，模型目录不会自动调用供应商 `/models` 接口；原生 Anthropic 等未接入的协议不在界面中伪装成已支持。Provider ID 当前用于配置表单中的本地标识，连接持久化仍由现有连接名称/Base URL/兼容 provider 字段承担，后续若需要跨设备同步再增加数据库字段。

本轮修改：`apps/desktop/src/ModelSettings.tsx`、`apps/desktop/src/ModelSettings.test.tsx`、`apps/desktop/src/style.css`。前端测试 **6 files / 42 passed**，TypeScript、ESLint 通过；真实 Provider、真实 Token/费用和正式数据库仍未使用。

最终可启动包：`.local/releases/model-provider-settings-20261110/ResearchGraph-Studio-Model-Providers-0.0.1-x64-setup.exe`，SHA-256 `6A09DAA7AE992F02F5278BD7B91F08249B9E562E08FE56F8A456643635F553DB`；完整 sidecar 位于同目录 `researchgraph-engine/`，EXE SHA-256 `1A460FB53316C22817EFCACC93CEA921EC6993EE7A6B9C13D42CFEACAFC72A3D`。sidecar smoke 和最终静默安装隔离验证通过，schema `lite0005`、匿名 PDF 导入成功、`model_calls=0`。

## 2026-11-10 · Lite 信息架构重排

本轮按 ADR0035 将项目页面从“导入论文 / 任务记录 / 项目文献”三段式工作台改为三层结构：左侧项目树负责项目和论文定位；一级导航增加与研究项目并列的“任务记录”；右侧只显示当前论文的论文概览、章节精读和论文问答。项目文献列表不再在右侧重复渲染。

导入论文保留在左侧当前项目操作和项目空状态，继续支持本地 PDF 与 Zotero。论文阅读标题区保留本地分类偏好。全局任务中心读取所有项目任务并显示项目名称、状态、阶段和取消/重试动作；本地解析、模型授权、Token 用量和 `unknown` 语义均未改变。

实际修改包括 `apps/desktop/src/App.tsx`、`Papers.tsx`、`JobHistory.tsx`、`style.css` 与前端测试。前端 Vitest **6 files / 41 passed**，TypeScript、ESLint、生产构建通过。最终 Windows 安装包为 `.local/releases/lite-navigation-layout-20261110/ResearchGraph-Studio-Lite-Navigation-0.0.1-x64-setup.exe`，38,380,988 bytes，SHA-256 `55719fb81c48eaa6c1c4776d293f2667fed8e1b16b6416ce901606191482905d`；sidecar 为同目录 `researchgraph-engine.exe`，15,076,947 bytes，SHA-256 `1a460fb53316c22817efcacc93cea921ec6993ee7a6b9c13d42cfeacafc72a3d`，须与 `_internal/` 同目录。静默安装、sidecar smoke、匿名 PDF 解析均通过，schema `lite0005`，模型调用为 0。当前未 Commit/Push，尚未完成用户原生桌面验收。

## 力导向图谱设计固化

新增 `apps/desktop/src/ForceGraph.design.test.tsx` 作为 LightGraph 力导向引擎设计契约（6 项断言），验证稳定节点 ID 布局恢复、确定性种子、有限坐标、局部力学、固定/拖动/冷却、双语标签、关系语义、相机保存、持久化回调以及不读取证据字段或模型坐标。该测试总结的是实际保留的 `ForceGraph`、`ForceSimulation`、`graphLayout` 与 `graphAppearance` 行为，不代表恢复旧版完整图谱业务。

已建立可复用 Skill：`C:\Users\KLucen\.codex\skills\researchgraph-force-graph`，入口为 `SKILL.md`，详细参数与边界见 `references/engine-design.md`。Skill 明确单篇 PaperCard + LightGraph 的边界：一次联合模型调用、布局与语义分离、同论文同版本才恢复布局、不生成 Evidence/证据字段或模型坐标、不恢复 Query/Lint/Wiki/跨论文推理。

## 清理结果

已完成全项目分类和清理：删除旧安装包、构建输出、数据库/WAL/SHM、日志、实验响应、Python/Node/Rust 缓存、旧 v2/v3 文档归档、旧 Prompt/Schema、完整图谱/Query/Lint/Wiki/Reading/Reasoning 业务代码、旧迁移和对应测试。根目录旧选题说明 `QA.md` 也已移除；必要的 Lite 规范、当前基线、迁移评估、安全说明和匿名 PDF fixture 保留。

活跃工程只保留本地阅读基础、Zotero、PDF/章节/FTS5、Provider/模型配置、任务、用量/缓存和可复用 React Flow 图组件。运行代码和契约中没有指向已删除旧业务的路由或导入；历史完整实现仍可从备份分支恢复。

## Lite 数据边界

新数据库使用 `researchgraph-lite.sqlite3`，当前 Alembic head 为 `lite0006`（从 `lite0001` 空基线加性增加章节导读、D01 局部问答、D02 英文关键词、全局模型连接和可选翻译设置/结果表），不迁移旧图谱、Query、Lint、Wiki、任务记录、缓存或抽取结果。已有 Lite 数据升级前自动备份并通过加性迁移保留，不重新初始化。检测到完整旧系统数据库结构时会停止并提示使用新的 Lite 数据目录。

选择 Zotero 论文或导入本地 PDF 后，解析、章节识别、文本块保存和 FTS5 建索引均在本机完成；不会自动排队 PaperCard、A、D 或任何完整知识图谱任务。生成概览必须由用户明确允许一次模型调用；PaperCard 和 LightGraph 共用同一请求，缓存命中不产生新调用。`unknown` 只表示信息或计量缺口，不据此补造实验条件、推断矛盾或把未知费用写成零。

## 前次阅读功能验证记录（2026-11-10）

- 后端：D01 专项 **8 passed**，D02 合约/API 专项 **5 passed**；完整后端回归 **185 passed / 1 skipped / 1 warning**。Ruff、mypy、compileall 和 OpenAPI/TypeScript 契约导出通过。
- 前端：TypeScript、ESLint、Vitest **41 passed / 6 files**，覆盖项目侧栏、论文分类偏好、任务中心、D02 显式授权/关键词展示和本地重检索；生产构建仍保留既有 >500KB chunk 提示。
- Rust/Tauri：已加入 D02 三条白名单路由、模型连接/设置入口和 schema `lite0005` 校验；修复关键词列表路由被通用 QA 详情路由提前匹配的问题，并补齐 `scope=selection|section|paper` 查询校验。`cargo fmt --check` 通过，Rust 单元测试 **7 passed / 1 ignored**（本轮未重复运行缺少 cargo 的环境）。
- Lite 专项：匿名 PDF 两份、章节结构、Chunk/EvidenceSpan、FTS5 正文检索、重启读取和 Provider 哨兵均通过；解析阶段实际调用数、输入 Token、输出 Token、总 Token、重试和增量费用均为 0。
- Windows 交付：当次导航布局安装包为 `.local/releases/lite-navigation-layout-20261110/ResearchGraph-Studio-Lite-Navigation-0.0.1-x64-setup.exe`（38,380,988 bytes，SHA-256 `55719fb81c48eaa6c1c4776d293f2667fed8e1b16b6416ce901606191482905d`）；sidecar 完整目录为同目录 `researchgraph-engine.exe` 与 `_internal/`（EXE 15,076,947 bytes，SHA-256 `1a460fb53316c22817efcacc93cea921ec6993ee7a6b9c13d42cfeacafc72a3d`）。sidecar smoke、直接 sidecar 隔离验证和静默安装隔离验证均通过：schema `lite0005`、匿名 PDF 导入成功、`model_calls=0`。构建产物不进入 Git。
- 论文功能入口修复：选中论文但解析版本尚未写入时，详情页会明确显示本地解析/章节索引等待状态，并每 1.5 秒刷新论文详情；解析版本出现后自动显示章节导读、局部证据问答、PaperCard 和 LightGraph，不再出现“选中论文但页面空白”的状态。
- 本轮未读取正式用户数据库、Zotero 正式库、私人 PDF/批注或真实 API Key，未调用真实 Provider；真实输入/输出 Token、重试和增量费用均为 0。安装包和构建目录位于被忽略的 `.local`/`target`，不进入提交。工作区安全检查与 `git diff --check` 通过；本轮仍未 Commit/Push。

## 下一步

Lite P4 的真实 Provider 验证、全局预算守卫、selection Span 选择器，以及独立外部翻译引擎的真实联调与译文验收仍待后续。复杂表格/公式、OCR、跨平台和用户原生安装体验尚未完成验收。翻译已有独立请求数和输入估算限额，不代表全部 A/B/D 流程已有统一费用硬上限。本轮测试使用匿名/合成数据和合成 Provider，真实模型调用、输入/输出 Token、重试和增量费用均为 0。

## 2026-11-10 · 设置与阅读工作区调整

- 用量入口已从项目文献页移到设置与诊断，设置页显示全部 Lite 项目的统一账本；原有 unknown 用量仍按未知显示，不按 0 估计。
- 新增 lite0005_model_connections 加性迁移。连接单独保存 Provider、Base URL 和凭据引用；模型 profile 通过 connection_id 复用连接，只保存 Model ID 和思考/采样/超时/JSON 参数。旧 profile 请求仍可兼容，历史任务快照继续冻结完整连接信息。
- 论文选中后显示独立的论文阅读工作区：论文概览（知识卡片 + 轻量图谱）、章节精读、论文问答。概览内继续使用一次联合 PaperCard + LightGraph 请求，布局和图谱交互保持。
- 实际验证：后端 tests/engine 185 passed / 1 skipped / 1 warning；前端 Vitest 39 passed / 6 files，TypeScript 与 ESLint 通过。真实 Provider、真实 Token/费用、正式数据库和桌面原生窗口本轮均未验证；安装包已重建并完成 sidecar/静默安装隔离验证。

## 2026-11-10 · 可交付包修复与最终验证

- 独立 sidecar 必须携带 PyInstaller 生成的 `_internal/` 目录；先前只复制 EXE 会出现 Python DLL 找不到的弹窗。已将完整 sidecar 目录补齐到 `.local/releases/lite-settings-20261110/`，并重新通过 smoke 和直接 sidecar 隔离验证。
- 安装包 `ResearchGraph-Studio-Lite-Settings-0.0.1-x64-setup.exe`：38,396,216 bytes，SHA-256 `0f353b850e94291e1f46272c158b01300d02322df7619f3183d932467d9185cd`。
- sidecar `researchgraph-engine.exe`：15,076,836 bytes，SHA-256 `8d5b4648fb724f55f99d1f79c7e776da8a29d20e4cc48af37c5e7182997e68db`；与 `_internal/` 同目录使用。
- smoke、直接 sidecar 验证和静默安装验证均返回 `result=passed`，health schema 为 `lite0005`，匿名 PDF 导入成功，模型调用为 0。
- Gitleaks 未安装；已完成工作区敏感模式扫描、暂存范围检查和 `git diff --check`。当前仍未 Commit/Push，未读取真实 API Key、正式数据库、私人论文或批注。
