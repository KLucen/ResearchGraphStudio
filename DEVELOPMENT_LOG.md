# ResearchGraph Studio 开发日志

用于持续记录真实开发过程，时间统一为 Asia/Shanghai。每轮实质性工作追加一条，不覆盖旧结果；后续发现错误时追加更正或清楚注明修订。提交号、测试结果或实验指标未知时写“未执行/待验证”，不填占位成功结论。

## 建立时状态（2026-10-27 历史快照）

以下条目保留工程建立时状态；最新进展见[实施进度](docs/progress.md)和本日志末尾，当前设计见[文档导航](docs/README.md)。

- 当前阶段：QA.md 与四份补充材料整合为开发计划 v0.4；待进入 Phase 0 构建准备与安装探针，尚未实现业务。
- 当前根目录：`C:\Users\KLucen\Desktop\AI科研知识推理平台`。
- Python 环境：Anaconda/Conda `researchgraph-studio`，Python 3.12.16，已创建并完成基础验证。
- GitHub 开发远端：`https://github.com/KLucen/ResearchGraphStudio`，本地 `origin` 已关联；尚无提交/推送。
- Zotero：`D:\Zotero\zotero.exe`，10.0.6，安装位置已核实。
- 已确认方向：证据推理与知识演化一体化，兼顾创新、实用、可实现和可安装运行。
- 技术路线：Tauri 2 + React/TypeScript、Python/FastAPI Sidecar、SQLite/FTS5、React Flow；框架已按 QA 选定，构建和业务实现尚未验证。
- 可运行软件/安装包/算法实验：均尚未完成。

## 2026-10-27 · DEV-0001 · 建立开发基线

### 目标

根据已有设计确定开发位置，检查当前环境，制定开发流程，并建立后续可持续维护的日志。

### 已完成

1. 检查当前目录及父级 `AGENTS.md`：原目录为空，未发现适用的既有项目指令或 Git 仓库。
2. 尝试读取用户提供的分享链接：网页请求超时，本机请求返回 403；浏览器读取未取得正文。Windows Computer Use 随后因无法可靠确定浏览器 URL 而停止，未继续该 UI 路径。
3. 使用应用内聊天读取接口找到《调研设计智能作品》，读取到用户明确选择方案三、要求安装运行与实验设计、询问 Zotero/Obsidian 分工的消息。助手长回答仅返回内容引用，未取得详细设计。已向用户提出补充原文的请求。
4. 决定直接使用当前目录为源码根目录；创建 `apps/desktop`、`apps/web`、`services/engine`、`packages/contracts`、`docs`、`experiments`、`tests/fixtures` 和 `scripts`。
5. 初始化 Git，分支为 `main`。创建忽略规则和编辑规范；未创建提交、配置远程或推送。
6. 完成硬件、命令行工具、WSL、服务、端口、常见软件路径与网络入口检查；保存 JSON 快照。
7. 制定 M0–M6 的阶段任务、交付物、验收标准和初步工作量；将早期安装验证与实验基线纳入流程。
8. 建立需求来源与待确认项、候选技术 ADR、实验计划和每轮日志维护约定。

### 主要产物

- [项目入口](README.md)
- [需求依据](docs/design/requirements-baseline.md)
- [开发流程（后续 v2 历史入口）](docs/archive/v2/02_development_plan.md)
- [环境报告](docs/environment-check.md)与[机器快照](docs/environment/2026-10-27.json)
- [候选技术决策](docs/decisions/0001-local-desktop-baseline.md)
- [实验计划](experiments/README.md)
- [环境复查脚本](scripts/check-environment.ps1)
- [协作约定](AGENTS.md)、`.gitignore`、`.editorconfig`

### 验证与观察

- 环境脚本已实际执行，退出码 0；快照时间为 2026-10-27 12:43:01 +08:00。
- Node 24.20.0、pnpm 12.5.1、uv 0.12.19 可执行；发现独立 Python 3.12.14，默认 Python 为 Anaconda 3.14.6。
- 机器为 i9-14900HX、15.7 GiB RAM、RTX 5060 Laptop 8151 MiB VRAM；GPU 驱动可查询，未运行模型测试。
- npm/PyPI/GitHub 入口 HTTP HEAD 均返回 200；未做依赖安装测试。
- 最终检查通过：13 份 Markdown 的 UTF-8 内容正常，18 个本地文档链接均存在；快照 JSON 可解析且根目录一致；PowerShell 脚本语法无错误。
- Git 状态确认分支为 `main`、文件均为本轮新建、无远程；`.env`、`.venv`、`node_modules`、`.local` 和实验运行目录的忽略规则验证通过。
- 本轮没有应用业务代码，未运行应用测试、安装包测试或算法实验。

### 未解决项与影响

| 编号 | 问题 | 影响与处理 |
| --- | --- | --- |
| B01 | 详细原设计与最后的集成分工回答尚未读到 | 产品细节和技术选型仍是建议；下一轮优先补齐，不能宣称已完整按原方案实施 |
| B02 | Zotero 未在常见路径发现 | 不推断未安装；接入阶段确认位置或以直接 PDF 导入起步 |
| B03 | 具体模型供应商、配置、实验文献和预算未确定 | 可做骨架；真实 AI 效果与费用评估尚不能完成 |
| B04 | 项目依赖、原生构建工具和干净机安装未验证 | M1 必须先做最小安装探针，不能仅依据版本号宣称兼容 |

### 下一步

补齐设计正文 → 逐项校对需求和 ADR → 固定 MVP 与技术栈 → 建立带锁文件的最小可安装骨架。

## 2026-10-27 · DEV-0002 · 采用 Conda、确认 Zotero 与 GitHub 远端

### 目标与用户补充

用户明确指定 Zotero 位于 `D:\Zotero`，Python 开发优先采用 Anaconda 并允许新建独立环境，开发远端为 `KLucen/ResearchGraphStudio`。该补充覆盖此前默认使用 uv 的建议。

### 实际改动

1. 核实 `D:\Zotero\zotero.exe`，产品版本 10.0.6；观察到 `127.0.0.1:23119` 监听。DEV-0001 的 B02 安装位置问题已解决，尚未查询个人文献库或验证 API 数据读取。
2. 创建 Anaconda 环境 `C:\Users\KLucen\anaconda3\envs\researchgraph-studio`，Python 3.12.16；项目命令明确使用该环境，base 与其他环境保持独立。
3. 添加 `environment.yml` 和 `conda-win-64.lock`。锁文件导出 20 个 Conda 包及 SHA-256；业务框架和 pip-only 依赖尚未加入。
4. 添加 `origin=https://github.com/KLucen/ResearchGraphStudio.git`。GitHub API 确认仓库可访问、公开、分支列表为空；无既有历史需要合并。
5. 更新协作约定、项目入口、开发方案、技术决策、需求基线和引擎目录说明，记录 Conda 优先、指定仓库和 Zotero 路径。
6. 环境复查脚本新增 Conda 环境检测、Zotero 自定义路径/版本、Git origin；保存新快照，保留初次快照作为历史记录。

### 验证与问题处理

- Conda 26.7.2 初次解析将 `nodefaults` 当作实际 channel，返回 404；修正环境文件后，通过显式官方 main channel 和 `--override-channels` 成功创建。未改全局源、未关闭 TLS 校验。
- `conda run -n researchgraph-studio` 成功运行：Python 3.12.16、OpenSSL 3.5.9、SQLite 3.53.4、pip 26.2.2；内存数据库查询断言通过，`python -m pip check` 返回无损坏依赖。
- Git HTTPS 首次连接超时；按 github-transfer 技能的官方 SSH 443 路线，`ls-remote` 与 `fetch origin` 均退出码 0、无 refs。保持主机密钥严格校验、原有远端 URL 和全局配置。该结果只证明读取成功，不是推送验证。
- 修正后的 `environment.yml` dry-run 退出码 0，解析出 20 个包，来源均为官方 main；未实际创建临时验证环境。
- 复查脚本实跑通过，最新快照为 2026-10-27 12:57:56 +08:00；确认 Conda 环境、Zotero 10.0.6 和 origin 信息。PowerShell 语法检查通过。
- 最终检查：13 份 Markdown、24 个本地链接均正常，20 条锁文件记录的官方 URL 和 SHA-256 格式有效；Git 仍为 `main`，文件尚未提交。
- 本轮没有创建提交、推送代码、开发应用功能或执行算法实验。

### 下一步

补齐原方案正文并校对细化需求；后续 Python 引擎和实验统一使用新 Conda 环境，业务依赖确定后更新锁文件。GitHub 远端已准备好承接后续版本。

## 2026-10-27 · DEV-0003 · 根据 QA.md 更新开发方向与流程

### 目标

以用户补充的 QA.md 为设计来源，修正之前因正文缺失而提出的暂案，保留 Conda、Zotero 路径与 GitHub 远端偏好。

### 实际改动

1. 阅读 QA.md 全文并记录行号/哈希。主产品、技术、算法和实验设计已取得，DEV-0001 的 B01 主设计缺失问题关闭。文件末尾仅有 MCP 提问无回答，按前文的 Local API/导出方案推进，不伪造最后回答。
2. 更新需求基线至 v0.3，建立 R01–R20 映射；说明 Zotero P0 表述与后续阶段安排、状态示例与正式状态、早期工期与细化工期之间的差异处理。
3. 新建 ADR 0002，选择 Tauri 2，替代 Electron/Forge 暂案。React 归入 apps/desktop，移除 apps/web 的旧占位 README；Python 保留 services/engine，按 QA 模块组织。没有迁移业务代码，因为业务代码尚未建立。
4. 开发流程改为 QA 的四阶段、约 10 周研究版计划；v0.1 聚焦 5 篇论文的证据推理/人工确认/导出闭环，v1.0 扩展演化、Zotero 与实验。新增 T101–T106 第一轮具体任务。
5. 新建领域模型，明确五类关系、六态审核、unknown 条件、引用匹配、事件事务、修订与历史保留。原文示例中 pending 等名称不再进入实际状态契约。
6. 重写实验计划为 E1 条件约束推理、E2 全量/增量对照、E3 人机审核任务；按原文设先导样本和目标值，补齐口径、数据划分、召回、覆盖和复现限制，未产生实验结果。
7. 同步项目入口、协作约定、目录说明与环境报告；保留旧 ADR/日志和环境快照作为历史。为后续 Rust 构建加入 target/ 忽略规则。

### 环境补查与验证

- 只读检测到 WebView2 155.0.4283.62；未在 PATH/常见位置发现 Rust，常见 vswhere 不存在，C++ Build Tools/SDK 状态待确认。专项证据见 docs/environment/2026-10-27-tauri.json。
- 核对 Tauri 官方 prerequisites、Sidecar、Windows installer 文档，将 Rust/MSVC 和 WebView2 分发作为 Phase 1 关卡。未安装工具、未修改 Conda 环境或锁文件。
- 本轮为文档/规划变更，未运行业务测试、模型评测或构建安装包。补记当轮最终检查：15 份 Markdown、40 个本地链接通过，未发现编码替换字符或代码围栏不配对；R01–R20 齐全，Tauri JSON 可解析，QA 哈希未变。该计数对应 DEV-0003，非后续扩展后的文件数。
- QA.md 原文保持不变；未创建提交或推送。

### 下一步与剩余依赖

从 T101/T102 开始核实/补齐 Tauri 构建环境并打包最小 Sidecar；T103 的契约设计可先行。真实推理前需选定 5 篇相关论文和模型配置；用户实验安排在后续阶段。当前不再以分享链接读取失败为阻塞。

## 2026-10-27 17:51 · DEV-0004 · 整合四份材料形成开发计划 v0.4

### 目标

结合桌面 BG.md、Zotero/Obsidian 职责文档、AI 工作文档和 development_plan.md，补齐工程细节并提供一份新的完整文档。本轮范围是计划更新；附件里的“立即执行 Phase 0”没有作为实施指令执行。

### 实际改动

1. 阅读四份材料并记录路径、行号、SHA-256；新建[来源登记](docs/design/source-register.md)。QA 原文及四份桌面材料均未改写，未复制其中的本地图片。
2. 新建[完整开发计划 v0.4](https://github.com/KLucen/ResearchGraphStudio/blob/8e15a9583a7a6becff9d49800af3717eee867121/docs/development-plan-v0.4.md)，包含产品范围、工具所有权、归属/条件/证据版本、实体合并、AI 流水线、API、UI、Wiki 发布恢复、阶段验收、RG-001–RG-015、评测和剩余依赖。旧计划保留为 docs/development-plan-v0.3.md；docs/development-plan.md 改为当前入口，避免两份活动全文漂移。
3. 按现有项目约定保留 v0.1 五篇 PDF 闭环；完整产品采用 Zotero 默认入口，但适配、自动演化与批量实验仍在 v1.0。新范围加入受控 Wiki、授权笔记回流、Query/Lint；Phase 0–6 初估 12–19 周，v0.1 初估 5–8 周，均不是实测工期或交付承诺。
4. 新建[ADR 0003](docs/decisions/0003-controlled-knowledge-evolution.md)记录范围与权限取舍。保留 Conda、services/engine、唯一开发日志和六态；新材料的 uv、progress.md、machine_checked/pending_review 均作映射或替换。
5. 同步 docs/design/requirements-baseline.md 至 R01–R34、domain-model.md 的归属/来源修订/RelationAssertion/Wiki 对象；实验计划保留 E1–E3 并新增 E4 抽取、E5 合并、E6 问答/新鲜度。
6. 同步 README、AGENTS、引擎/桌面/契约目录说明、旧 ADR 的当前入口和环境报告阶段名；补记 DEV-0003 当轮已执行但未写入的验证结果。

### 验证

- 使用 researchgraph-studio 的绝对 Python 解释器检查 19 份 Markdown 的 UTF-8；原设计 QA 仅作编码/哈希核对，项目自编文档检查代码围栏、本地链接和编号。新增计划 326 行，R01–R34、RG-001–RG-015 均齐全且无重复；未发现缺失本地链接、替换字符或不配对围栏。
- 五份用户原文的 SHA-256 均与读取前一致；四份桌面链接仅供本机查看，源码仓库未包含其全文。
- 核对 Zotero Local API、Tauri Sidecar 和 LLM Wiki 原始文档；在计划中区分官方接口能力与项目拟实现功能。未访问个人文献库或 Vault，未重新安装/改动环境。
- 本轮只有文档改动，未运行应用测试、模型实验或安装构建；未创建 GitHub Issues、提交或推送。现有文件仍未提交，不能据本轮文档宣称 Phase 0 完成。

### 未解决问题与下一步

构建工具、干净 Windows 验证环境、首批论文与模型配置仍需在对应阶段补齐；Wiki 原位更新的外部编辑竞态需专门验证，不能把哈希检查加 replace 当作跨进程 CAS。下一轮优先 RG-001–RG-005：构建准备、Tauri/Sidecar、项目存储和安装探针。模型效果、Zotero 实接、Wiki 发布和实验按后续关卡逐项验证。

## 2026-10-28 09:51 · DEV-0005 · Phase 0 工程实现与本机安装探针

### 目标

响应用户“开始 Phase 0 / 继续开发”，实施 RG-001–RG-005：可运行桌面、私有 Sidecar、项目存储、任务/迁移与安装探针。实现跨 10 月 27–28 日，先前安装中断后继续；不把补充材料中的指令当作授权。

### 实际改动

1. 创建根目录 package.json/pyproject.toml、pnpm workspace、Rust 工具链和平台锁文件；Python 依赖安装在 researchgraph-studio。增加 scripts/common.ps1、dev.ps1、build-engine.ps1、build-windows.ps1、check-phase0.ps1 和独立引擎 smoke 脚本。
2. apps/desktop 实现 React 项目空态、创建、列表/分页、详情、设置与真实存储诊断。Rust 管理单实例、动态回环端口、私有 stdin 令牌、版本握手、有限 IPC 白名单及退出/重启。
3. services/engine/researchgraph 实现 Project、Job、Event、Idempotency；Alembic 0001、外键/事务、单写入者文件锁、迁移前备份、失败回滚。诊断任务有取消、三次执行上限和中断恢复。
4. 导出 packages/contracts/openapi.json/generated.ts；加入 Python、React、Rust 针对性测试及 .github/workflows/phase0.yml。CI 尚未推送执行。
5. README、目录说明、environment.yml、docs/api.md、开发计划/需求和环境报告同步实际实现；新增 docs/phase0-verification.md。Phase 0 用普通 CSS/原生 dialog，保留后续组件选择空间；没有架构路线变更。
6. 补齐官方 Rust/MSVC/Windows SDK；处理 PyInstaller 资源绝对路径与 Conda 输出空行问题。NSIS 常规 GitHub 下载超时，改用官方 API 资源并校验官方哈希；未修改全局网络设置。

### 验证

- 锁定依赖安装后 scripts/check-phase0.ps1 通过：11 项 Python、3 项 React 测试；ruff/mypy/TypeScript/ESLint/格式检查、契约生成、pip check 和生产 Web 构建通过。Starlette TestClient 的 httpx 弃用提示保留，未伪称无警告。
- Rust fmt/clippy 通过，1 项路径白名单单元测试通过，release 原生程序编译成功。
- PyInstaller onedir 引擎在中文/空格临时目录、仅系统 PATH 下通过鉴权拒绝、项目幂等、诊断、退出/重启读回；该测试仍在开发机运行。
- computer-use 检查原生窗口：空态、本地引擎连接、中文项目“Phase 0 安装验证”创建成功，诊断显示检查通过。测试数据为自造内容，无个人论文或笔记。
- 安装器后续验证结果在本条末补记；干净 Windows G0 尚未执行，不宣称 Phase 0 全部验收完成。

### 问题与下一步

完成安装器、本机安装/重启/退出与宿主异常退出检查，汇总路径和哈希；独立 Windows G0 仍需测试机/虚拟机。之后进入 Phase 1 的来源/附件版本和 PDF 证据锚定。未调用模型，未接触 Zotero 文献库/Vault，未创建提交或推送。

### 2026-10-28 09:57 验证补记

- 最终 NSIS 安装器构建成功：23,999,729 字节（约 22.89 MiB），SHA-256 `E36DB25CA2614643956C07C759EEAF00E339D852114ACDBD83D894669A4E5C59`。本机安装于 `.local/安装验证 ResearchGraph`，静默安装退出 0；在仅 System32 的子进程 PATH 下启动原生窗口并读回项目。
- 安装目录中的打包引擎再次通过独立 smoke。实际桌面完成诊断、单实例、引擎异常退出后报错/重连；强制终止宿主后子引擎在 15 秒等待窗口内退出，正常关闭后也无残留服务。
- 静默卸载退出 0，程序文件移除而用户数据库保留；修复 UI 后重新构建安装器，重装退出 0，项目仍可读回。应用与自造项目保留供用户查看。
- 故障测试发现缓存的健康值在断连后仍显示“FTS5 可用”，修正为等待检查，侧栏明确“引擎未连接”。相关 TypeScript/ESLint、格式、3 项 React 测试与 release 构建再次通过；引擎重试上限补充断言后 11 项 Python 测试通过。
- 最终检查：21 份 Markdown、98 个本地链接及五份用户原文 SHA-256 通过，安装器哈希与记录一致。PowerShell 脚本语法检查通过。汇总见 [Phase 0 验证记录](docs/phase0-verification.md)和[环境增量 JSON](docs/environment/2026-10-28-phase0.json)。
- RG-001–RG-004 本机实现/验证完成；RG-005 安装器与 CI 已写，独立 Windows G0、缺 WebView2 安装及远端 CI 尚未验证。未提交或推送代码，安装包未签名。下一项是独立 Windows G0；Phase 1 再做 PDF 来源与证据链。

## 2026-10-28 20:19 · DEV-0006 · Phase 0 验收脚本与 main 自动推送

### 目标

继续 Phase 0 验收并推送远端；用户明确要求以后每轮开发完成自动推送 main。

### 实际改动

- AGENTS.md、README、开发流程入口保存自动提交/普通推送 main 的长期授权；每轮检查与日志继续有效，禁止强推覆盖。
- 新增 scripts/verify-windows-install.ps1：Windows PowerShell 5.1 原生验收，不调用开发工具；打包引擎鉴权/幂等/诊断/重启，安装模式另验证宿主/单实例/退出/卸载。已有安装或用户数据时拒绝桌面测试；仅使用自造项目。
- CI 拆分构建和已安装应用两份 Windows runner，后者只下载产物、执行 PowerShell 验收；设置超时、并发控制、失败报告上传。文档更新不重复构建。
- 新增 .gitattributes 统一源码行尾，QA.md 禁止转换以保留原文哈希。更新 Phase 0 验证说明与 G0 可携带操作命令。

### 已执行验证

- 本地 check-phase0.ps1 再次通过：11 项 Python、3 项 React 测试及类型/lint/契约/生产构建；保留一条已知 Starlette httpx 弃用提示。
- 新脚本在 Windows PowerShell 5.1.26100.9444 下通过 EnginePath 模式，子进程仅 System32 PATH；鉴权、诊断、幂等保存、重启读回和 stdin EOF 退出均通过。记录在 .local/acceptance-powershell51-final/verification.json。
- 官方 SSH 443 ls-remote 成功，远端当前为空；GitHub 连接确认具有 push 权限。源码候选未发现常见密钥格式，运行数据/私有配置/构建产物被忽略。
- 本机无 Windows Sandbox 或已发现的 VM 工具，不以本机/预装工具的 CI runner 宣称干净 Windows G0。首次推送和 CI 实际结果待后续补记。

### 问题与下一步

首次提交并推送 main，跟进远端构建与安装验收；如失败就地修复。独立 Windows UI、缺 WebView2 安装仍为 G0 待验收项。

### 2026-10-28 20:25 推送与 CI 补记

- 首次提交 d1a39fa006b1ded5c7e7f7decf941414b65c41a5 经 SSH 443 普通推送到 origin/main，建立上游跟踪；远端此前为空，没有覆盖已有历史。已验证提交中的 QA.md 字节哈希保持原值。
- [CI 运行 40686890045](https://github.com/KLucen/ResearchGraphStudio/actions/runs/40686890045) 已执行；截至本条记录，环境重建、Python/React 测试、契约漂移检查、打包引擎验证通过，Rust/安装器构建运行中。GitHub 连接工具的日志读取出现传输层 403，改用官方公开 REST 查询，未接触凭据。
- Windows PowerShell 5.1 复核摘要入库为 docs/environment/2026-10-28-phase0-powershell.json；已有安装保护实测生效。已在 .local/phase0-acceptance-kit.zip 准备本地安装器、验收脚本和说明，未将二进制包放入源码提交。

## 2026-10-29 10:57 · DEV-0007 · 修复 Windows CI 安装验收的管道编码

### 目标与改动

- 继续 Phase 0 安装验收，按授权修复 CI 并普通推送 main。
- 首次远端运行 40686890045 的构建 job 全部通过；独立安装 job 在安装成功后，引擎启动配置解析失败。下载该运行的安装产物到 `.local`，只解包，不覆盖本机日常安装。
- `scripts/verify-windows-install.ps1`：Windows PowerShell 5.1 / .NET Framework 在 UTF-8 控制台下创建 stdin writer 时会写入 BOM。临时使用无 BOM UTF-8 创建管道并恢复原编码，配置按 UTF-8 字节写入；启动失败附带退出码和 stderr。
- `.github/workflows/phase0.yml`：失败时额外上传 engine-stderr.txt，保留定位依据。

### 验证

- 同一 CI 安装产物在本机原控制台编码下通过；切换 UTF-8 控制台后复现 JSONDecodeError；修复后 Windows PowerShell 5.1 复测通过鉴权、诊断、项目幂等/重启、EOF 退出。结果在 `.local/ci-reproduce-utf8-fixed2/verification.json`。
- 本次没有修改应用协议或数据库，仅修复验收工具；远端完整构建及安装重验结果待补记。

### 问题与下一步

- 推送修复并跟进 CI，更新验收材料。独立 Windows 10/11 无开发环境及缺 WebView2 的 G0 仍待真实测试机执行，CI runner 不替代该关卡。

### 2026-10-29 11:23 验收与推送补记

- 修复提交 `8df4e1e4d8e25391b650fb1eb6db87c55e57f87d` 已普通推送 main。[CI 40809339440](https://github.com/KLucen/ResearchGraphStudio/actions/runs/40809339440) 已完成且 success：windows 构建与 installed-app 独立安装两个 job 全部成功。
- 远端完成锁定依赖重建、11 项 Python / 3 项 React / 1 项 Rust 测试、静态检查、契约漂移检查、生产构建、打包引擎测试和 NSIS 生成。安装 runner 通过安装、鉴权、诊断、项目幂等及重启持久化、EOF 退出、桌面 Sidecar 启动、单实例、正常关闭、崩溃清理、卸载及数据保留。
- 本机附加验证脚本运行后恢复调用方 UTF-8 编码及 BOM 设置；结果、CI 摘要和原始安装报告分别保存为 docs/environment/2026-10-29-phase0-encoding.json、2026-10-29-phase0-ci.json、2026-10-29-phase0-installed.json。
- 已下载 CI 安装器与报告，校验两份 artifact ZIP 官方 SHA-256，安装器哈希与验收报告一致：`9EC242A883044079E02DFDEF5BF3E25D730EC93C7E1146AA9CFD4B0FF4B4E437`，23,976,140 字节。更新 `.local/phase0-acceptance-kit.zip`，其中包含该产物、修复脚本及说明；没有覆盖本机现有安装或提交二进制、数据库、密钥。
- 同步 README、环境报告、开发流程入口与 Phase 0 验证记录；文档与机器报告作为收尾提交推送 main。G0 仍未关闭：Windows 10/11 无开发工具、缺失 WebView2 和人工 UI/离线场景需独立机器验收；当前系统无现成 Sandbox/VM，未另行安装虚拟化组件。之后开展 Phase 1 PDF 来源/附件版本与证据锚定，保留 G0 发布门槛。
- 收尾检查：21 份 Markdown、103 个本地链接、五份原文哈希通过；三份新增 JSON 可解析，PowerShell 语法检查通过，git diff --check 通过。推送前 fetch 确认本地与 origin/main 同步。

## 2026-10-29 19:18 · DEV-0008 · G0 用户放行与 Phase 1 PDF 导入首轮

### 目标

用户明确默认 G0 通过并开始 Phase 1，随后要求继续开发。按 ADR 0004 放行流程，保留未执行的实机测试事实；交付 RG-006 的首个纵向增量，不提前宣称 RG-007/M1 全部完成。

### 实际改动

- 迁移 0002 新增 Paper、PaperSource、AttachmentRevision、Chunk；Job 保存项目/输入。新增 ingest 子进程、来源哈希去重、托管快照、版本追加与事务事件。前端支持原生文件选择、引用/托管、任务取消/重试、修订/原文块查看；IPC 白名单不开放任意路径导入。
- PyMuPDF 1.26.7 安装在 researchgraph-studio 环境，依赖及哈希锁已更新；Rust rfd 原生选择器及 Cargo.lock 更新。生成四个 CC0 自造 PDF fixture 与哈希清单，原始设计材料未改。
- 扩展冻结引擎和 PowerShell 验收加入 PDF 导入/重启检查，CI 的安装 runner 也运行该检查；新增 ADR 0004、Phase 1 实施/剩余工作文档，同步 README、计划、接口和基线。

### 已执行验证

- 20 项 Python 测试、7 项 React 测试通过；ruff/mypy/TypeScript/ESLint/契约/生产 Web 构建通过。保留 Starlette httpx 弃用提示。Rust 初次 fmt/clippy/test 通过，新增白名单断言后继续复核。
- 冻结 multiprocessing 路径曾导致导入任务保持 running；改为明确的内部解析 CLI 子进程后，打包引擎 smoke 通过 PDF 导入、页码/原文、托管及重启持久化，子进程无开发工具 PATH。PowerShell 5.1 同样通过。开发环境的成功没有冒充此失败尝试完成。
- PDF 自造文本页已渲染检查；原生窗口使用独立应用标识/数据目录验证，避免迁移现有安装数据。界面操作和远端 CI 尚待本条末补记。

### 问题与下一步

完成原生窗口与远端安装检查，按授权提交并推送 main。随后完善 RG-006 的来源检查/缓存回收/进度，再实现 RG-007 Evidence、多 span、原页高亮及人工校正。当前块级文本与坐标不是已审核科学证据；未接入 AI/Zotero/Vault，未扫描用户论文库。

### 2026-10-30 02:24 本机验收补记

- 续接本轮工作；Rust 新增路由断言后的 test 与 clippy 均通过。原生调试窗口使用独立数据目录，成功读回之前的项目/样本，原生文件选择器再次导入同一自造 PDF 后保持一篇文献，两个任务均完成。详情显示两页原文、S-1/S-2 标签、72%/81% 数值、哈希和解析限制。
- 文档检查通过 23 份 Markdown、111 个本地链接和五份原始材料 SHA-256。补充 Phase 1 实测说明及任务历史显示范围；远端 fetch 确认与 origin/main 同步。接下来提交本轮实现并跟进 Windows 构建/安装 CI。

### 2026-10-30 02:29 推送与远端检查进展

- 实现提交 `9b7a306be1e73e0392e81b6a576706d3aa712042` 已普通推送 main。提交前检查 146 个源码候选及四份自造 PDF 哈希，没有将运行数据、安装产物或常见凭据格式加入提交。
- [CI 40930522934](https://github.com/KLucen/ResearchGraphStudio/actions/runs/40930522934) 的环境重建、引擎/界面/契约检查和打包引擎验证已通过；Rust/安装器步骤运行中，安装 runner 尚未执行。
- 原生验收窗口已关闭，未发现残留 ResearchGraph 宿主或引擎进程。接口文档补充实际新增的数据表与 PDF 事务边界；继续等待安装版实测后记录最终结果。

### 2026-10-30 02:40 远端验收与本轮收尾

- CI 40930522934 已完成且 success：windows 与 installed-app 两个 job 全部成功。远端日志确认 20 项 Python / 7 项 React / 1 项 Rust 测试通过，另有静态检查、契约漂移、生产构建、打包引擎 smoke 与 NSIS 构建；保留一条已知测试依赖弃用提示。
- 独立安装 runner 通过 PDF 导入/原文重启持久化，以及安装、鉴权、诊断、项目幂等/重启、EOF 退出、桌面 Sidecar、单实例、正常关闭、宿主异常退出清理、卸载与数据保留。摘要和原始报告分别入库 docs/environment/2026-10-30-phase1-ci.json、2026-10-30-phase1-installed.json。
- 下载并校验两个官方 artifact ZIP 的 SHA-256；安装器 37,606,027 字节，其 SHA-256 `DBE45D7678F387D3B28AAC1D762BC86BEF9A2ED5BF64A13760682FE45B87FC89` 与安装报告一致。本地 `.local/phase1-acceptance-kit.zip` 已包含安装器、CC0 样本、脚本、校验清单和说明，不进入源码提交，也未覆盖本机原有安装。
- 同步接口、环境与 Phase 1 验证文档。RG-006 首轮已可运行；下一步补来源丢失/变更/重定位、缓存回收和进度，再完成 RG-007 跨页 Evidence、原页高亮与人工校正；不宣称 M1/Phase 1 全部完成。G0 按用户决定放行，仍未补做干净机和缺 WebView2 场景。将本次验收文档作为收尾提交普通推送 main。
- 收尾检查：23 份 Markdown、114 个本地链接、五份原文哈希通过；两份新增 JSON 可解析且与真实 CI 提交/结果一致；验收 ZIP 的六个条目完整，安装器、脚本与样本字节核对通过。git diff --check 通过，推送前 fetch 确认 main 与 origin/main 同步。本次收尾仅修改文档及 docs 内报告，不重复触发构建。

## 2026-10-30 11:08 · DEV-0009 · 来源检查与同内容重新定位

### 目标

继续 Phase 1 RG-006，补齐原文件/托管副本可用性检查与移动文件后的重新定位；保存来源变化记录，避免旧任务覆盖新来源，不把文件状态当作知识审核状态。

### 实际改动

- 迁移 0003 为 PaperSource 添加 generation、last_check；source_files 模块执行有界哈希检查并分别报告原文件和托管副本状态。ingest 的子进程框架复用于导入/检查/重定位，继续支持取消、退出终止、幂等、手动重试和事务发布。
- app/schema/契约新增来源检查、重新定位和项目任务查询。原生宿主选择重定位文件，普通前端桥只开放检查接口；同内容、无路径冲突且代次仍匹配时才更新路径，历史修订/原文不改写，事件保存前后路径。
- SourceFiles 界面显示检查时间、独立文件状态、历史修订不匹配提示及操作入口；项目文献任务显示导入/检查/重定位进展。来源任务不再混入诊断任务，也不受其他项目最近任务挤占。
- 增加源文件、迁移、并发代次、取消/重试与界面测试；冻结引擎及 Windows PowerShell 验收加入“原文件移动、托管副本仍可用、重新定位、重启读回”。新增 ADR 0005，同步 README、计划、领域模型、API 和 Phase 1 记录。无依赖新增，继续使用原 Conda 环境与锁文件。

### 验证

- 32 项 Python、12 项 React、1 项 Rust 测试通过；ruff/mypy/TypeScript/ESLint/格式/生产构建和 pip check 通过，保留一条既有测试依赖弃用提示。
- 打包引擎在中文/空格路径及仅系统 PATH 下通过新增来源流程；Windows PowerShell 5.1 验收通过，报告为 docs/environment/2026-10-30-phase1-sources-powershell.json。首次脚本启动被本机执行策略拒绝；仅对重试进程使用执行参数后成功，未修改全局策略。
- 原生调试构建使用独立测试数据目录，已迁移并读回旧项目/原文，默认显示尚未检查；完整按钮操作与远端 CI 结果待补记。当前 24 份 Markdown、121 个本地链接及五份原材料哈希检查通过。

### 问题与下一步

完成原生界面复核并按授权提交、推送 main，跟进 CI。后续仍需缓存回收、任务阶段进度/完整分页历史、更多真实 PDF 样本，再完成 RG-007 证据片段、高亮与人工校正。本轮不扫描私人目录、不接入模型/Zotero/Vault，不宣称 M1 全部完成。

### 2026-10-30 11:10 本机原生复核与提交准备

- 原生窗口完成“尚未检查 → 内容一致/时间 → 选择同内容副本重新定位”；任务均已完成，路径更新后文献仍为一篇，附件哈希及 S-1/S-2 两页原文未变化，测试窗口随后关闭。
- 完成源码候选敏感格式与运行产物排除检查、24 份 Markdown/121 个本地链接/五份原文哈希检查及 git diff --check；推送前 fetch 确认与 origin/main 同步。准备普通提交并推送本轮实现；远端结果仍待实际执行。

### 2026-10-30 16:11 远端失败定位与验收修复

- 实现提交 `d16ad837d779f16f1572298e8f04439ec6976fa0` 已推送 main。[CI 40995909703](https://github.com/KLucen/ResearchGraphStudio/actions/runs/40995909703) 的依赖重建、32 项 Python / 12 项 React 测试与静态检查成功，但打包引擎 smoke 在重新定位路径字符串比较处失败；Rust/安装器与安装 runner 未执行，不能记为通过。
- 定位到 scripts/smoke-engine.py 的断言没有匹配 API 的规范化路径规则。使用本机 Windows 8.3 短路径作为 TEMP 重现同一失败；改为比较解析后的路径并核对文件身份、附件版本，修复后该场景全部通过。应用路径保存逻辑和数据库没有改动。
- Windows PowerShell 5.1 验收在短路径输出目录下原样通过；该脚本无需修改。修复文件的 ruff 检查/格式通过；接下来普通推送修复并重新执行远端完整构建与安装验收。

### 2026-10-30 16:20 修复推送与远端复验

- 修复提交 `4410ef380633a603ec3b221f439259a4b879894b` 已普通推送 main。推送前确认远端无新增提交，修改范围为验收脚本及记录，没有新增应用依赖或运行数据。
- [CI 41024830613](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41024830613) 已通过环境重建、代码/界面检查及此前失败的打包引擎验证；桌面安装器构建仍在执行，独立安装验收尚未完成。
- 本机普通临时目录与 Windows 8.3 短路径场景均通过；复现摘要保存为 docs/environment/2026-10-30-phase1-sources-paths.json。同步细化 Phase 1 的下一轮缓存回收边界：临时任务目录与历史托管附件分开处理，保留旧版本、共享附件和外部原文件；这部分仍是计划，尚未实现。

### 2026-10-30 16:28 远端安装验收与本轮收尾

- CI 41024830613 已完成且 success；windows（123960353071）与 installed-app（123965535784）两个 job 均成功。远端日志确认 32 项 Python / 12 项 React / 1 项 Rust 测试通过，包含静态/格式检查、契约、生产构建、打包引擎来源流程和 NSIS；保留一条既有测试依赖弃用提示。
- 独立安装 runner 通过安装、PDF 导入、来源检查/重新定位、项目/原文/来源重启持久化、鉴权、诊断、EOF 退出、桌面 Sidecar、单实例、正常关闭、崩溃清理及卸载。摘要和原始报告分别保存为 docs/environment/2026-10-30-phase1-sources-ci.json 与 2026-10-30-phase1-sources-installed.json，首次失败和本机复现记录保留。
- 已下载新安装器与报告并校验官方 artifact ZIP SHA-256。安装器 37,623,738 字节，SHA-256 `7F6CF7463FCB0C4F39DFBD492A5EF83CDED330D95D0297D9924ED2D0F8DE6B17` 与安装报告一致；新建 `.local/phase1-sources-acceptance-kit.zip`，六个条目完整，安装器、脚本、样本字节匹配。未覆盖既有安装/旧验收包，二进制、运行数据、私人材料和密钥不入库。
- 同步 Phase 1、环境和开发计划记录。RG-006 来源检查增量验收完成；下一轮先实施崩溃临时目录回收及任务进度/分页历史，再推进 RG-007 证据锚定、高亮与人工校正。本次未执行新的真实论文质量评估、干净 Windows 或缺 WebView2 测试，不宣称 M1/Phase 1 全部完成。验收记录检查后作为文档提交普通推送 main。
- 收尾检查：24 份 Markdown、125 个本地链接、五份原文哈希及四份来源 JSON 报告解析通过，git diff --check 通过；待提交仅为七份文档/验收报告。fetch 确认与 origin/main 同步，收尾提交不重新触发应用构建。

## 2026-10-31 19:46 · DEV-0010 · 临时回收、任务进度与历史分页开发交接

### 目标

2026-10-30 按用户要求继续 RG-006，实施临时任务回收、真实阶段进度和项目任务分页；2026-10-31 用户要求阶段总结与下一次开发提示词，本次整理交接并保留未完成验收的改动。

### 实际改动

- 新增 workspaces.py、迁移 0004、JobHistory 界面与三份测试文件；修改引擎生命周期、阶段上报、项目任务游标、契约、Rust 白名单和回收统计展示。新回收逻辑仅删除带归属标记且未被子进程锁定的普通临时文件，保留历史附件、未知内容和目录链接。
- 扩展打包引擎与 PowerShell 验收，加入分页、阶段、暂存目录回收和来源/托管附件保留。环境与依赖锁未改变。
- 创建 [2026-10-31 开发交接](docs/handovers/2026-10-31-phase1-status.md)，详细区分已交付基线、本机未提交实现、验证证据和下一轮收尾步骤。

### 验证

- 2026-10-30 本机 44 项 Python / 16 项 React / 1 项 Rust 测试，以及静态检查、契约、依赖检查、生产 Web 构建通过；一条既有依赖弃用提示保留。打包引擎 smoke 与 Windows PowerShell 5.1 引擎模式验收通过。证据位于 `.local/phase1-jobs-*` 日志及 `.local/phase1-jobs-ps51/verification.json`。
- 2026-10-31 复核日志与 Git：本地 HEAD 和远端 main 均为 `a642d66de1f6bc17f1ceda3f596a69f16875720a`；新功能源码尚未提交/推送。当前无 ResearchGraph 宿主/引擎残留进程。
- 本轮原生 debug 构建已发起，但续接时旧命令会话不可查询，最终退出结果待复核；界面人工操作及本轮远端构建/安装 CI 未执行，不记为通过。
- 交接文档与日志的 Markdown 结构、23 个本地链接及 git diff --check 通过。全仓库文档检查因登记在桌面的四份补充原文当前均不在原路径而失败，无法重查其哈希；原文与来源登记未被改写，后续按仓库内既有基线继续并记录该限制。

### 未解决问题与下一步

- 先复核现有实现并完成独立数据目录中的原生窗口验收；再补 ADR 0006、API Schema 0004、README/计划/Phase 1 文档和正式验收报告。此前文档补丁失败，ADR 0006 尚不存在，旧 API 文档尚未更新。
- 通过相关检查、敏感文件检查及远端更新核对后，按既有授权普通提交并推送 main，跟进 CI、保存对应新安装产物并补记结果。本次用户要求总结交接，未把未完成验收的工作当作已交付提交。
- 当前增量收尾后进入 RG-007 证据片段/高亮/人工校正；真实论文质量、M1 与外部环境检查仍待相应验证，不宣称 Phase 1 全部完成。

## 2026-10-31 20:40 · DEV-0011 · RG-006 验收与交付准备

### 目标

- 验收临时工作区回收、子进程租约、权限失败重试、任务实际阶段和稳定历史分页。
- 用独立原生测试数据复核旧库升级、历史加载、取消/重试、回收统计和原文保留，并完成本轮交付前检查。

### 实际改动

- 保留并收尾本机 RG-006 实现：Schema 0004、`JobHistory`、临时工作区白名单回收、旁侧 `.lock` 租约、真实阶段上报和带快照上界的 keyset 历史分页。
- 补充租约入口对符号链接、重解析点和多链接普通文件的拒绝，避免 `.lock` 路径触碰外部文件；对应边界测试位于 `tests/engine/test_workspaces.py`。
- 补齐 ADR 0006、API Schema 0004、README、开发计划、Phase 1 记录和原生验收报告 `docs/environment/2026-10-31-phase1-jobs-native.json`。

### 验证

- Conda `researchgraph-studio`：45 项 Python 测试通过、1 项平台能力跳过；ruff、格式、mypy、pip check、契约导出通过。React 16 项测试、TypeScript/ESLint、Prettier、生产构建通过；Rust fmt、clippy、1 项测试通过。保留一条既有 Starlette/httpx 弃用提示。
- 打包引擎 smoke 和 Windows PowerShell 5.1 引擎模式验收通过，覆盖 Unicode/空格路径、来源重新定位、稳定历史分页、实际阶段、强制退出回收、重启和来源/托管附件保留；新 PowerShell 报告保存在 `.local/phase1-jobs-ps51-*`。
- 原生 debug 窗口曾使用 `com.researchgraph.studio.phase1test` 独立数据目录检查旧 Schema 0003→0004、取消/重试、来源检查、回收统计及两页/四块原文重启读回；但此前记录的“13 条任务加载”在本轮代码复核中被发现与 Tauri 的 UUID 游标白名单冲突，已从验收证据撤销。修复后窗口复测待执行。
- 26 份 Markdown 的本地链接检查无断链，`git diff --check` 通过。已检查 tracked 文件和忽略目录边界，未发现运行数据库、安装器、密钥或私人材料进入提交。
- HTTPS fetch 因网络失败；按仓库约定使用仅本次命令生效的官方 SSH 443 通道，确认 `origin/main` 仍为 `a642d66de1f6bc17f1ceda3f596a69f16875720a`。

### 限制与下一步

- `docs/design/source-register.md` 登记的 S1–S4 桌面路径当前均不存在，无法重新核对原文内容和哈希；没有修改登记或原文，保留该限制。
- 本机调试、合成 PDF、引擎模式和既有 G0 放行均不等同于干净 Windows、缺失 WebView2 或本轮安装器验收；本轮远端安装 CI 待提交后执行。
- 通过收尾检查后普通提交并推送 `main`，跟进本轮 CI，下载并校验对应安装验收包，再补记最终结果。随后进入 RG-007 证据锚定、高亮与人工校正。

### 2026-10-31 21:11 · DEV-0012 · 分页桥接复核与交付检查

#### 目标

- 接续 DEV-0011，完成 RG-006 任务历史分页的桌面桥接复核，并按实际结果更新验收记录。

#### 实际改动

- 发现 `apps/desktop/src-tauri/src/main.rs` 把任务历史 `cursor` 按 UUID 检查；服务端 `next_cursor` 是 Base64URL JSON 快照令牌，导致桌面第二页请求会被宿主白名单拒绝。
- 将白名单改为接受 1–512 位 ASCII Base64URL 字符，保留查询参数去重、限制字符和服务端解码校验；增加 Rust 路由回归断言。
- 更新 [RG-006 原生验收报告](docs/environment/2026-10-31-phase1-jobs-native.json)与 [Phase 1 记录](docs/phase1-verification.md)，撤回无法由旧桌面桥接实现的“加载后 13 项”结论。

#### 验证

- `scripts/check-phase0.ps1`：45 项 Python 通过、1 项平台能力跳过；Ruff、格式、mypy、pip check、Schema 契约导出、Prettier、TypeScript/ESLint、16 项 React 测试及 Web 生产构建通过。保留一条既有 Starlette/httpx 弃用提示。
- Cargo fmt 检查、Clippy `-D warnings` 和 1 项 Rust 测试通过；新增测试覆盖 Base64URL 游标、超长游标及不安全字符。
- 修复后原生窗口复测未执行：Computer Use 在 `list_apps` 阶段返回“用户按 Escape 停止”，遵守技能要求停止所有后续窗口操作。引擎层分页用例通过不代替该桌面复测。
- S1–S4 补充材料在 `docs/design/source-register.md` 登记的桌面路径仍不存在；本轮无法核验原文内容/哈希，未更改原文或登记。

#### 问题与下一步

- 原生桌面加载更早任务仍需在修复构建上实际复测；远端安装 CI 与对应安装验收包也待推送后完成。旧库升级、重试、回收统计和原文保留仅沿用 DEV-0011 的既有原生记录，本轮未重做。
- 推送前继续执行敏感文件、文档链接与远端更新检查；按用户授权提交并普通推送，跟进 CI。交付关闭后进入 RG-007 证据锚定、高亮与人工校正。

## 2026-10-31 21:31 · DEV-0013 · RG-006 自动化验收与交付提交

### 目标

- 完成临时工作区回收、子进程租约、权限失败重试、任务实际阶段和稳定历史分页的交付前复核。
- 核对独立测试数据、旧库升级、重试、回收统计和原文保留，并在检查通过后提交、推送和跟进本轮 CI。

### 实际改动

- 保留 RG-006 的实现、测试、Schema 0004 契约、ADR 0006、README、开发计划和 Phase 1 验收记录；工作区回收仍限定于带 `workspace.json` 归属标记的平坦目录，使用旁侧 `.lock` 租约，失败时保留 marker 供下次重试。
- 记录修复后的 Tauri Base64URL 不透明游标白名单和已撤回的旧桌面分页结论；原生窗口修复后复测未完成，不能把引擎分页结果写成桌面通过。

### 验证

- `pwsh -File scripts/check-phase0.ps1` 通过：45 项 Python、1 项平台能力跳过、16 项 React；Ruff、格式、mypy、pip check、契约导出、Prettier、TypeScript/ESLint 和生产构建均通过。保留一条既有 Starlette/httpx 弃用提示。
- Cargo fmt、Clippy `-D warnings` 和 1 项 Rust 路由白名单测试通过；冻结引擎重建和 `scripts/smoke-engine.py` 通过 PDF 导入、来源重新定位、阶段/稳定分页、强制退出回收、原文及托管附件重启保留、Unicode/空格路径和 EOF 退出。
- Windows PowerShell 5.1 引擎模式通过，报告位于 `.local/phase1-jobs-ps51-final-010d4454e00545d4b916df0912f72621/verification.json`，包含分页/阶段、暂存回收、重启和来源/托管附件保留；`clean_windows_G0` 仍为未认证。
- 使用独立应用标识和自造 PDF 的修复后原生窗口复测在 `list_apps` 阶段再次被 Computer Use 的物理 Escape 中止；没有产生新的桌面分页结果，旧库升级、取消/重试、回收统计和原文读回仅保留此前报告证据。
- SSH 443 fetch 确认 `origin/main` 仍为 `a642d66de1f6bc17f1ceda3f596a69f16875720a`。敏感/运行产物检查、`git diff --check` 和 Markdown 本地链接检查通过；`source-register.md` 登记的 S1–S4 桌面原文仍不存在，无法重新核对其内容和 SHA-256，未修改登记或原文。

### 问题与下一步

- 当前工作区改动尚未提交；下一步在本条日志落盘后执行普通提交并推送 `main`，等待新 CI。CI 若失败，继续修复并普通推送；成功后下载并核验新安装器、安装报告与 SHA-256，建立独立验收包并补记结果。
- 本轮交付后进入 RG-007：Evidence/span 对象、跨页引用、归一化映射、原页面高亮和人工校正版本。干净 Windows、缺失 WebView2、修复后原生分页和真实论文版式质量仍是待验收项。

## 2026-10-31 22:14 · DEV-0014 · RG-006 CI 验收与交付收尾

### 目标

- 接续 RG-006 已推送实现，收齐远端 Windows 安装 CI 证据，更新验收文档并完成普通提交/推送。
- 对本轮原生窗口分页、四份补充材料及干净环境验收限制如实留档。

### 实际改动

- 新增 [CI 验收摘要](docs/environment/2026-10-31-phase1-jobs-ci.json)，更新 [原生验收报告](docs/environment/2026-10-31-phase1-jobs-native.json)、[Phase 1 记录](docs/phase1-verification.md)、ADR 0006、API/计划入口相关状态和 README。CI 通过、原生分页未复测、M1/干净环境未完成分别记录。
- 保留 GitHub artifact 内的原始安装报告副本 [安装验收报告](docs/environment/2026-10-31-phase1-jobs-installed.json)，SHA-256 `D2F3F06B031B2C6B7C3D65E968E50DBBD2CB5FFF0D762732D82C46291BFD6842`。验收包 `.local/phase1-jobs-acceptance-kit-41206071801.zip` 含安装器、自造 PDF、PowerShell 脚本、报告、说明和校验清单；压缩包 SHA-256 `5D0D497C533DB85FE1CE7EE05A79CF0619DB6A2796CA2BC12B5C3E52BE7E25EA`，安装器 37,622,305 字节、SHA-256 `B8F1E66D2665B4C920F827E860637C9D8C5206288120070195233E19500B22F7`。二进制及验收包位于忽略目录，不进入源码提交。
- S1–S4 登记的桌面原文路径均未找到，不能复核当前内容或哈希；未修改原文及来源登记。

### 验证

- GitHub Actions [41206071801](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41206071801) 对应源码提交 `5a3c124254192a418af8bc5c4de5d1b1f9c1f32d`，`windows`（124551286807）与 `installed-app`（124554048915）均 completed/success。构建、测试、安装/卸载、Schema 0004、PDF 来源检查、任务分页/阶段、临时工作区回收、重启后原文/托管附件保留、Sidecar 生命周期通过。artifact 摘要和安装器/报告哈希已核对并入档。
- 安装 runner 报告将 `clean_windows_G0` 标为 `not_certified_by_this_script`；缺失 WebView2 未测。CI 不等于修复后原生窗口分页复测。
- 原生窗口的既有独立数据报告仍保留 Schema 0003→0004 升级、取消/重试、回收统计和两页/四块自造 PDF 重启读回证据；该记录早于分页桥接修复。本轮第三次在 `list_apps` 阶段被物理 Escape 中止，没有进入应用窗口；修复后分页仍未验收，不将 API、Rust 或安装脚本结果替代 UI 证据。报告改用 `%LOCALAPPDATA%` 表示测试数据目录，并去除重复 JSON 键。
- 已拉取并检查 `origin/main`；开始文档收尾时与本地 `main` 同步于 `5a3c124`。`git diff --check` 通过。S1–S4 路径核对为空；原始验收报告 JSON 可解析，哈希与 CI 摘要一致；验收压缩包可列出全部预期文件且 SHA-256 已记录。
- 本轮变更限于 Markdown/JSON，工作流对 Markdown/docs 路径不触发构建；应用代码已经由上述成功 run 验收，本轮未重复运行代码测试。

### 问题与下一步

- 保留修复后原生窗口加载第 2 页历史为待验收项；并保留 M1 安装版证据定位、干净 Windows、缺失 WebView2 和真实 PDF 版式质量验收。G0 仍按用户决定放行，不将放行记成测试通过。
- 文档检查通过后，按既有授权普通提交并推送 `main`；此文档提交不触发应用 CI。RG-006 交付收尾后进入 RG-007：Evidence/span、跨页引用、归一化映射、原页面高亮与人工校正版本。

## 2026-10-31 22:19 · DEV-0015 · RG-006 提交推送核验

### 目标

- 记录 DEV-0014 文档提交的实际推送结果，并核验代码提交对应的安装 CI 与本地验收包。

### 实际改动

- DEV-0014 的文档收尾提交 `c104a0156ca40c9e576f984ec99b87f059f1b33d` 已经通过项目约定的 SSH 443 通道普通推送至 `origin/main`；推送前 fetch 确认远端仍为其父提交 `5a3c124254192a418af8bc5c4de5d1b1f9c1f32d`，推送后本地与远端一致。
- 文档提交没有改动应用代码，CI 的 `paths-ignore` 排除 Markdown 与 `docs/**`，因此该提交没有触发新构建；RG-006 代码提交 `5a3c124` 对应的安装 CI 与验收证据已在 DEV-0014 记录。

### 验证

- GitHub API 核验 Actions run [41206071801](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41206071801)：`windows` 与 `installed-app` 均 completed/success。
- 本地忽略目录中的验收包 `.local/phase1-jobs-acceptance-kit-41206071801.zip` 存在，大小 37,621,633 字节；重新计算 SHA-256 与 DEV-0014 记录一致：`5D0D497C533DB85FE1CE7EE05A79CF0619DB6A2796CA2BC12B5C3E52BE7E25EA`。验收包不进入源码提交。
- 文档提交推送后再次 fetch，`HEAD` 与 `origin/main` 均为 `c104a0156ca40c9e576f984ec99b87f059f1b33d`，工作区干净。

### 问题与下一步

- 修复后的原生窗口任务历史第二页仍未复测；Computer Use 曾在应用枚举阶段被物理 Escape 中止，本轮不把先前原生记录、引擎测试或安装 CI 替代为桌面分页通过。
- RG-006 的自动化与 CI 交付证据已归档；下一功能阶段为 RG-007 证据锚定、高亮与人工校正。M1 证据定位、干净 Windows、缺失 WebView2 与真实 PDF 版式质量仍须分别验收。

## 2026-11-01 11:49 · DEV-0016 · v2 P1 兼容迁移与统一 Knowledge Engine P2

### 目标

- 按用户新设计完成旧 P0/P1 工程审计、最小迁移、P1 兼容补全和 P2 最小闭环，不重做 P0、不进入 P3。继承起点 `18b4598` 的代码及用户新增设计包/删除旧计划入口的改动。

### 实际改动

- 新增[迁移评估](docs/migration/v1_to_v2_assessment.md)、[架构 ADR](docs/adr/0001-unified-knowledge-engine.md)、[实际进度](docs/progress.md)，更新 AGENTS、README、API、旧基线/计划历史标记及 Phase 1 记录。新设计包保持主要依据；参考 schema/prompt/test 与运行实现区分。
- Python 新 knowledge_models/contracts/store/api、integrations、providers、extraction、Prompt 资源及 0005 加性迁移。旧 Paper/AttachmentRevision/Chunk 和 API 不变；统一 Store 校验证据/写入/事件/revision/审核。Zotero 只读批注、授权 Markdown 快照、未知条件、模型原始结果/人工历史均持久化。
- React 新 KnowledgeReading、SourceIntegrations、知识 API/阶段/阅读样式；Rust 新精确白名单和目录授权选择器。修复点击卡片需二次选证据、证据 UUID 排序、模型模板占位输入及过时文案。同步 Schema 0005、生成契约、打包 Prompt、smoke/安装脚本 P2 验收。
- 新测试覆盖离线端到端、锚点篡改/非法 ID、归属/数值/unknown、重跑去重、人工修订/乐观冲突/原始输出、新来源保留 accepted、模型失败/超时/非法 JSON/取消、只读目录/批注与迁移恢复。

### 验证

- Conda `researchgraph-studio`：完整检查 76 Python passed、2 skipped，20 React passed；Ruff/format/mypy/pip/生成契约/TS/ESLint/Prettier/Web build 通过。参考契约 5 passed；Rust fmt/clippy 与 2 tests 通过。两项 skip 为文件 symlink 权限，Windows junction 测试通过；保留已有弃用提示。
- 重新冻结引擎，扩展 smoke 和 Windows PowerShell 5.1 验收通过 P1 导入/来源/分页/阶段/回收/重启以及 P2 Mock/preview/审核/重启。第一次 PS5.1 被执行策略拒绝后采用单进程参数，不改全局设置。顺序测试初稿忘计 PyMuPDF 原文换行，改为仅在顺序断言中 strip，运行证据仍保留原文，完整复测通过。
- [原生报告](docs/environment/2026-11-01-v2-phase2-native.json)：独立 0004→0005 与备份、历史 10→13、原生自造 PDF 导入、8 张 Mock 卡片、块高亮、修订/接受 v3 与两条历史；公开 15 页论文导入和 221 张摘录卡片，第 4 页点击回查。仅流程验收，不是模型科学质量指标。
- 正式用户库只读审计仍为 0001、1 project、1 job，没有在其上实验。四份 S1–S4 原登记路径均缺失；QA 哈希保持登记值。Markdown/本地链接/JSON 检查通过，明确排除四个不可用外部原文。
- 推送前 fetch 确认 `origin/main` 仍为 `18b4598`。Git SSH 443 可用；API 的继承代理连接失败，显式直连官方 API 200，未改全局配置。最终提交、CI 和新安装验收包待下条记录，不提前记成功。

### 问题与下一步

- 真实模型未配置；真实 Zotero 仅验证只读连接，批注用自造 fixture；干净 Windows/缺失 WebView2、复杂版式/精确字级锚点、完整安装版人工阅读验收未完成。所有私人材料/数据库/公开下载 PDF/安装产物留在忽略目录。
- 本轮按授权普通提交推送并跟进 CI。P2 后停止；P3 建议入口为条件化 RelationAssertion 候选和证据/审核约束，详见进度中的边界，不提前实现 Query/Wiki/多 Agent。

## 2026-11-01 12:20 · DEV-0017 · v2 P2 远端安装验收与交付归档

### 目标

- 收齐 DEV-0016 对应代码的远端构建、安装验收和产物校验，保存新验收包；本轮在 P2 收尾。

### 实际改动

- 代码提交 `e67854d50c0b286d0b511b7b1f92892d682a1f0b` 已通过官方 SSH 443 普通推送 `main`，保留现有工程与用户设计包。
- 新增 [CI/产物摘要](docs/environment/2026-11-01-v2-phase2-ci.json)和[原始安装报告](docs/environment/2026-11-01-v2-phase2-installed.json)，同步 [实际进度](docs/progress.md)。本次收尾只改文档与验收记录，不改应用代码。
- 建立本机忽略目录中的 `.local/v2-phase2-acceptance-kit-41271020398.zip`，包含安装器、原始报告、PowerShell 验证脚本、自造 PDF、原生验收记录及逐文件校验清单。未将安装器、私人材料、运行数据库或下载论文纳入源码。

### 验证

- [CI 41271020398](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41271020398) 对应上述代码提交，`windows`（124743640642）与 `installed-app`（124746438251）均 completed/success。本机完整结果继续为 76 Python passed、2 skipped、20 React、2 Rust 和 5 参考契约通过；详见 DEV-0016，不将本次文档检查记作重新运行全部测试。
- 另一 runner 的 PowerShell 5.1 报告实际通过安装、桌面/Sidecar 启动、单实例、正常/异常退出、P1 导入/来源/分页/阶段/回收/原件保留、P2 Mock 抽取/证据/审核/重启以及卸载。子进程 PATH 仅 System32；runner 自身存在开发工具，`clean_windows_G0` 保持未认证。
- 官方 artifact ZIP 摘要分别为 `9CA6CDF9D2DC9A1CADE03D8C7EC5AD86E9A8F9AA401A324BD9718365EB7AFA97`（安装产物）与 `6895992C668426697011A2C0864A3368B84E1CCE56466110A12E39FE9F2D1A74`（报告），下载核验通过。直连传输较慢，实测本机代理对官方产物端点更快后分段下载；未更改全局网络设置，API 凭据未转发至产物端点。
- 安装器 37,702,337 字节，SHA-256 `0EB849D1B5290830049E7F9DBD6F48B6EF4B30970A11B0A88B945BC286AD990A`，与报告一致；原始报告 SHA-256 `48E2E1371EA35777E30FE21745E96CA1B724AB861D23E1CF588F28B1C58F45D8`。
- 新验收包 37,702,773 字节，SHA-256 `9E7E24A14244DCBD0471369CFB26706ECE93EE7944C7884DB6097207DB9DD608`；ZIP 完整性与逐文件 hash 校验通过。源码仅保留无敏感数据的验收摘要。
- 45 份 Markdown、160 个本地链接、QA 原始 hash 和环境 JSON 检查通过；四份不可用外部原文明确排除。暂存的 4 份文本文件通过敏感路径/凭据模式检查，`git diff --cached --check` 通过；提交前 fetch 确认 `HEAD` 与 `origin/main` 均为 `e67854d`。

### 问题与下一步

- 真实模型科学质量、真实私人 Zotero 批注匹配、干净 Windows/缺 WebView2、复杂版式/字级定位和完整安装版人工阅读体验仍未验收。四份 S1–S4 原文登记路径仍不可用，未声称核验其内容或 hash；G0 用户放行保持有效。
- 按既有授权普通提交推送收尾记录。工作流排除 Markdown 与 `docs/**`，本次文档提交不需要重建安装器；安装包对应代码提交仍为 `e67854d`。
- P2 结束，不实施 P3。下一轮可从条件化 RelationAssertion 候选、证据依赖与人工审核开始，并先建立授权真实论文/模型基准。

## 2026-11-01 13:58 · DEV-0018 · P3 前置配置、批量接入与全局模型设置

### 目标与实际改动

- 本轮目标仍为真实模型与两篇论文验收后完成 P3，不进入 P4；未经新的明确授权不 Push。
- 新增 credentials/model_settings/settings_api、0006/0007 迁移、ModelSettings、ZoteroImport、zotero_batch 和对应测试；扩充原生白名单/超时、抽取配置快照、OpenAPI/TS、smoke、敏感内容检查脚本及 .gitignore。模型设置依用户补充从项目内迁到全局“设置与诊断”，保留旧 ID、凭据引用、角色记录和 API 别名。统一模型供所有项目使用，论文知识仍项目隔离。
- 侧边栏图标折叠与本机持久化已实现。补 ADR v2-0002、模型配置/安全说明，并更新 README/API/进度。两份旧计划的用户删除保持，相关历史链接改为 Git permalink。

### 实际验证

- Conda researchgraph-studio：全局设置版本 86 Python passed、2 skipped；Ruff/format/mypy/pip check 通过。check-phase0 在 SourceIntegrations 格式处停止，修复格式后单独继续 Prettier、TS/ESLint、25 React、Web build 均通过；3 Rust、fmt/clippy 通过。
- 全局配置的 8 项针对性测试包含无项目创建、跨项目共享、0006 升级保留凭据引用/角色/项目及备份、旧选择冲突留空。真实 Windows 凭据 roundtrip 通过，测试假密钥已清理。
- build-engine、独立 debug Tauri 构建、冻结引擎模型配置/角色/重启 smoke、Windows PowerShell 5.1 引擎验收通过；日志在 .local/p3-global-*。不等于干净机或本轮远端安装 CI 通过。
- 原生全局设置已显示用户刚保存的配置与安全密钥标记，Extraction/Reasoning 默认角色已选。用户报告先前连接成功；迁移后复测进行中。TEST 只读浏览为 5 篇论文/6 个可用 PDF，真实导入/抽取待后续执行，不能把 Mock 当真实验收。

### 意外启动与数据核对

- Computer Use launch_app 接收完整开发程序路径后仍启动了已安装 P2 程序；立即正常关闭，后续改用显式 Start-Process 启动隔离 exe。安装版自动将正式 com.researchgraph.studio 数据库从 0001 升至 0005，留下升级前 SQLite 备份。未恢复/覆盖数据库。
- 只读逐行比较备份与升级库中原有 projects、jobs、knowledge_events、idempotency_keys 四表的旧列，全部完全一致；原有 1 个项目保留。应如实记录这次正式库 schema 变动，不能继续声称正式库仍为 0001。

### 未完成与下一步

- 两篇真实论文 P2/P3 端到端验收、P03–P05、图谱/Comparator/关系审核尚未完成。下一步原生批量导入和真实抽取，再推进 P3。
- 初版 Gitleaks 历史/候选扫描通过，收尾需对新改动重扫；没有 Commit/Push。S1–S4 外部原文路径仍不可用，未声称已重新核验。

## 2026-11-01 16:02 · DEV-0019 · P3 原生与真实模型验收收尾

### 目标

- 完成本轮 P3 原生验收、记录真实与 Mock 结果差异、核对文档和敏感内容；按用户本轮要求不推送。

### 实际改动

- 新增 [Phase 3 本机验收记录](docs/phase3-verification.md)，记载全局设置迁移、Zotero Test collection、三篇真实论文抽取、来源完整性、P03–P05、Mock 关系审核、侧栏及图谱重启验证和限制。
- 同步 README、开发计划、ADR v2-0002 与 [实施进度](docs/progress.md)：明确 P3 最小功能已实现，但真实 Claim 关系候选→审核→图谱边尚未验收通过。Mock 只作为软件路径验证。
- 保留两份旧计划的既有删除；历史指向改用固定 Git permalink。S1–S4 原文登记路径不可用，无法复核本轮原文或哈希；QA 原件和既有登记值保持不变。

### 验证

- 原生真实模型：三篇论文 P01/P02 批次为 3/3、11/11、11/11；1683 EvidenceSpan 来源、页码、quote、offset/hash 校验通过，4 份 PDF hash 未变。三组 Claim 比较均为 NO_DECISION；真实关系审核闭环未通过。P03 same_as 候选已在原生 UI 驳回并读回历史，但此为验收操作，不代表用户领域判断。
- 原生隔离 Mock：RELATED 候选接受、图谱边/状态筛选及重启读取通过，模型原始输出、事件与审核历史保留。侧栏折叠跨页和重启保持；图谱调整尺寸后节点未裁切，任务历史 10→15。
- 既有本轮自动化结果：104 Python passed、2 skipped；修复后 28 React、4 Rust、5 参考契约通过；冻结 Sidecar smoke、PowerShell 5.1 引擎验收通过。Symlink skip 原因及未完成真实关系项见验收报告。
- 未构建新安装器、未推送、未运行本轮远端 CI；不得将历史 P2 CI 41271020398 当作本轮结果。正式安装库 0001→0005 的既有事件及备份/旧列比较见 DEV-0018，本轮使用隔离验收数据。
- `conda run -n researchgraph-studio python scripts/check-sensitive.py --gitleaks .local/tools/gitleaks-8.30.1/gitleaks.exe` 通过：扫描 248 个候选源码文件，路径规则及 Gitleaks 均通过。暂存区为空，因此 `--staged` 扫描为 0 文件，不能代替候选源码扫描。`conda run -n researchgraph-studio python .local/v2-doc-check.py` 检查 50 份 Markdown、136 个本地链接、QA hash 与环境 JSON 通过，准确列出四个不可用外部原文；`git diff --check` 通过。扫描报告只在忽略目录。

### 问题与下一步

- P3 仍需用户在真实证据充分且实验条件可比的 Claim 对上完成领域审核；不得降低 NO_DECISION 门槛或以 Mock 代替。其后才进行有授权的远端安装验收。
- 一个兼容模型供应商完成真实测试；OpenAI 直连、其他兼容服务、本地真实模型、私人 Zotero 批注和复杂图表/公式仍未验证。未进入 P4。
- 本轮不 Commit/Push，遵循用户 P3 消息中的新授权边界。S1–S4 仍待恢复可访问原文后核验。

## 2026-11-01 18:10 · DEV-0020 · 抽取恢复计数与重试边界复核

### 目标

- 延续当前 P3 增量，修复真实模型抽取出现中途批次失败时的恢复计数和重复调用风险；不进入 P4，不提交或推送。

### 实际改动

- `services/engine/researchgraph/extraction.py` 以 `KnowledgeOperation` 的成功记录作为批次进度真相源，恢复已提交节点计数；任务重试只处理未完成批次，避免成功批次重复调用。相同任务、输入、模型、Prompt 和参数下，已收到且可通过契约校验的 P01 大纲会复用。
- `tests/engine/test_knowledge.py` 扩充 7 批次中途失败场景，验证首批知识保留、恢复后完成批次与节点计数一致、首批和 P01 不重复调用。`docs/api.md` 将批次上限从旧的 16000 更正为 10000，并记录恢复语义；`docs/progress.md` 同步本轮限制。

### 验证

- `conda run -n researchgraph-studio pytest -q tests/engine/test_knowledge.py -k 'failed_later_batch_preserves_saved_progress or model_failures_preserved_without_fake_success'`：5 passed。
- 上一轮已通过的 `104 passed, 2 skipped` Python、`28` React、前端构建和敏感扫描结果继续保留；本轮没有重复宣称全量结果。
- 本轮未重新启动原生窗口、未构建安装器或运行远端 CI；当前 shell 找不到 `cargo`，Rust 检查未执行。真实 Zotero/真实模型七批次中途失败场景未重新复测，不能以离线测试替代。
- 未发现需要更新的公开 API Schema；仅文档和抽取恢复逻辑发生变化。`git diff --check` 与候选源码敏感扫描待最终收尾再次执行。

### 问题与下一步

- 真实模型仍需在用户授权下复测中途失败后继续，重点确认服务端超时、退避和模型实际批次大小；真实关系审核仍保持此前 `NO_DECISION` 限制。
- 继续留在 P3，先完成原生窗口/安装器复核和最终安全检查，再由用户决定是否提交；不自动 Push。

## 2026-11-01 19:16 · DEV-0021 · P3 启动、抽取与论文入口增量复核

### 目标
- 修复正式桌面启动时的控制台窗口风险，复核真实模型抽取超时边界，并精简论文/Zotero交互；不进入 P4。

### 实际改动
- `main.rs` 的 Windows GUI 子系统与 Sidecar `CREATE_NO_WINDOW` 保持一致；stderr 仍写入 `engine-startup.log`，未删除调试入口。
- `ConfiguredProvider` 使用可取消的异步 `httpx` 流式请求，限制 2 MiB 响应并区分超时、网络、限流、服务端、客户端、重定向和输出截断；保留 `_request` 兼容入口，避免旧集成测试失效。
- 首页空状态和项目卡片的宣传占位语句、页脚口号及 Zotero 重复说明已移除；论文区改为知识概览导向。Zotero 批量导入成功项增加显式“解析并抽取知识”入口，不绕过用户传输授权。

### 验证
- `conda run -n researchgraph-studio pytest -q`：104 passed、2 skipped。
- `pnpm --dir apps/desktop test -- --run`：28 passed；`pnpm --dir apps/desktop build`：通过。
- Provider 测试 8 passed；Ruff check/format 通过；敏感扫描 248 个候选源码文件通过；`git diff --check` 通过。
- 7 批次失败续跑专项测试通过。真实 Zotero/真实模型中途失败场景、本轮原生窗口及安装器未重新实测，不能以自动化结果替代。

### 问题与下一步
- 需要在隔离安装包中确认 GUI 子系统实际无 PowerShell 窗口且关闭窗口只退出 Sidecar；当前环境找不到 `cargo`，Rust 检查沿用上轮结果。
- 真实模型仍只验证过既有兼容供应商；用户论文的 7 批次中途失败续跑待在设置页授权后复测。保持 P3，下一步为真实关系候选的证据锚定与人工审核。

## 2026-11-01 19:26 · DEV-0022 · 最新 Windows 安装器构建

### 目标
- 卸载旧版 ResearchGraph Studio，并构建当前工作区最新安装器；保留用户数据和源码改动。

### 实际改动
- 旧版用户级卸载目录已不存在，清理残留卸载注册项；未删除项目数据库、模型凭据、论文、笔记或 AppData 数据。
- 使用 `scripts/build-engine.ps1` 重建无控制台 Sidecar，再运行 `pnpm --dir apps/desktop tauri build` 构建 NSIS 安装器。

### 验证
- 新安装器：`apps/desktop/src-tauri/target/release/bundle/nsis/ResearchGraph Studio_0.0.1_x64-setup.exe`
- 文件大小：38,371,834 bytes；SHA-256：`A2B179B1D05864EC1961A399AC4D91A055B57B8D94431D3949316297F9E94F63`。
- 旧版卸载注册项查询不到；构建后没有 ResearchGraph 进程残留。
- Gitleaks/敏感路径扫描 248 个候选源码文件通过；`git diff --check` 通过。

### 问题与下一步
- 安装器已构建但尚未自动安装；用户可手动运行并反馈启动窗口、数据迁移和真实 Zotero/模型行为。
- 构建阶段有 PyInstaller 的 `tzdata` 缺失警告和前端 chunk 体积提示，未阻断构建；需在安装后重点观察时区与启动日志。

## 2026-11-02 00:25 · DEV-0023 · v3 文档基线整理与历史归档

### 目标

- 按用户新提供的 v3 包整理 docs 中相关设计内容，合并当前入口与工程规则，保留旧规范和实际验收证据。本轮不开发新功能、不执行迁移。

### 实际改动

- 旧 v2 的 README、三份主文档、AGENTS 模板及 prompts/schemas/examples/tests 共 29 文件移至 `docs/archive/v2/`。5 份入口 Markdown 添加历史标识并修复相对链接，其余 24 份文件内容保持不变；既有两份旧计划删除保持。
- 新建 [文档导航](docs/README.md)、[历史索引](docs/archive/README.md)、[整理映射](docs/migration/v3-documentation-map.md)和 [ADR 0003](docs/adr/0003-v3-documentation-baseline.md)。合并 v3 自动建图、完整领域模型/轻量投影、断点续跑和数据保护要求到根 AGENTS，保留原环境与禁止未经授权 Push 的约束。
- 更新 README、进度、API/模型配置说明、旧需求/领域/来源/ADR/迁移与实验入口；标明当前设计、已实现运行契约和历史上下文。同步 DEV-0022 的安装器已构建未验收状态，不把构建当作安装测试。
- v3 原包保持原样；Prompt 编号映射及双击交互、嵌套 DTO、中文必填与英文回退、证据 hash 命名等参考差异登记待实施前澄清。没有改写运行 Prompt、数据库 Schema、用户数据或既有代码改动。

### 验证

- 使用 Anaconda `researchgraph-studio` 绝对解释器执行两个独立进程：`python -m pytest docs/researchgraph_studio_v3/tests -q`：12 passed；`python -m pytest docs/archive/v2/tests -q`：5 passed。
- v3 SHA256SUMS 的 52 项全部相符；16 份生成 JSON Schema 与参考 Pydantic 在内存中逐项一致。与本轮开始前的文件哈希比较确认代码、QA 原件和 v3 原包未改写，29 个归档文件齐全，24 份非入口资产原样保留。检查备份仅留在本机忽略目录 `.local/docs-v3-reorganization-20261102/`。
- `python .local/v2-doc-check.py`：Markdown 编码、代码围栏、本地文档链接、QA 哈希和环境 JSON 通过，S1–S4 四份不可访问外部原文单列为限制。
- `python scripts/check-sensitive.py --gitleaks .local/tools/gitleaks-8.30.1/gitleaks.exe`：306 个候选文件内容/路径及 Gitleaks 通过；`git diff --check` 通过。暂存区未变，不 Commit/Push。
- 本轮只调整文档与参考包位置，未重跑应用 Python/React/Rust、真实模型、原生窗口或安装 CI；不将此前 104/28/4 等结果冒充本轮或 v3 验收。

### 问题与下一步

- 旧资料的四个外部原文路径仍不可用，未重新计算原文哈希；保留历史登记。
- v3 M0 工程审计尚未执行，不能将本次文档映射当作迁移评估。后续先核对现有 P2/P3 代码与用户数据兼容，再按 M1–M6 推进投影和详情等增量，保留真实关系及安装验收缺口；不自动进入 P4/P5。

## 2026-11-02 00:38 · DEV-0024 · 将 v3 规范并入标准 docs 目录

### 目标

- 按用户要求取消 `docs/researchgraph_studio_v3/` 外层目录，将内部内容放回 docs 对应位置；保留旧 v2 归档、工程代码与用户数据。

### 实际改动

- 10 份设计章节移至 `docs/00_decisions_and_scope.md` 至 `docs/09_reference_implementation_notes.md`；Schema/Prompt/示例/测试放入 `docs/schemas/`、`docs/prompts/`、`docs/examples/`、`docs/tests/`，Schema 的 generated 子目录保留。
- 共搬移 53 份文件；原包 README 合并到 `docs/README.md`，保留产品决议、文件所有权、环境与外部参考。附属模板、CHANGELOG、忽略规则示例及清单放到 docs 根目录，后续开发模板仍不自动执行。
- 同步根 README/AGENTS、文档索引、ADR、整理映射和历史文档中的链接；调整参考测试命令，重建 MANIFEST 与 52 项 SHA256SUMS。历史日志中的旧执行命令保留为当时记录。
- 目录删除操作被自动审批策略拒绝（工具仅返回 blocked by policy，未提供更具体理由）。改用可回滚的搬移，将残留的已合并 README 和生成缓存移入本机忽略备份；确认 docs 下旧目录已不存在。原始输入与哈希清单同样保存在 `.local/docs-flatten-20261102/`。

### 验证

- Anaconda researchgraph-studio 绝对解释器：`python -m pytest docs/tests -q`：12 passed；独立进程 `python -m pytest docs/archive/v2/tests -q`：5 passed。
- 新路径下 52 项 SHA-256 全部通过；16 份生成 JSON Schema 与 Pydantic 一致。26 份 Schema/SQL/示例/测试文件字节未变；与本轮开始快照核对，应用代码、运行 Prompt、生成 API 和 QA 原件未改动。
- `python .local/v2-doc-check.py`：79 份 Markdown、272 个本地链接、QA 哈希与环境 JSON 通过；四份外部原文仍不可用，未假称核验。
- `python scripts/check-sensitive.py --gitleaks .local/tools/gitleaks-8.30.1/gitleaks.exe`：305 文件通过；`git diff --check` 通过。未 Commit/Push，未执行应用回归、真实模型或安装验收。

### 问题与下一步

- 无目录整理遗留项。v3 参考设计待澄清点和 M0 工程审计仍见文档整理映射；此次文件搬移不代表工程迁移已完成。

## 2026-11-02 02:00 · DEV-0025 · v3 M0–M6 核心增量、兼容迁移与验收

### 目标

- 按 `docs/06_development_migration_plan.md` 在原工程中完成 M0–M6 核心功能；继承现有 P0–P3 数据、API 和未提交改动，不进入 P4/P5。

### 实际改动

- M0 修改前执行 104 Python passed/2 skipped、28 React passed，保存 305 个源码文件快照与四份 SQLite 一致性备份到 `.local/v3-m0/`；新增 [v2→v3 迁移评估](docs/migration/v2_to_v3_assessment.md)和 [ADR 0004](docs/adr/0004-v3-projection-and-unified-extraction.md)。没有重搭工程。
- `graph_models.py`、`graph_contracts.py`、`graph_projection.py`、`0009_graph_projection.py` 新增显示元数据、来源结构边、独立布局；五类默认投影、带 revision 的分页、限定邻域及按需完整详情。旧 ID、知识/证据/审核/模型结果沿用，不删除实验与条件。
- `unified_contracts.py`、`unified_extraction.py`、`unified_store.py`、`unified_mock.py` 与运行 P02 实现 unified-v3.1 单批多类型抽取，严格证据/局部引用检查后经 KnowledgeStore 写入。`translation.py` 与运行 P04 只补译显示字段，保留 accepted 科学内容、原始英文与模型输出。
- `extraction.py`、`app.py`、`ingest.py`、`knowledge_api.py`、`knowledge_store.py`、`providers.py`、`zotero_batch.py` 等接入新流程；按章节 6000 字符预算、批次幂等/恢复、有界退避、调用时长/Token 记录。Zotero 解析后在同事务排队确定性抽取子任务，默认引用原文；旧 API 默认 legacy-v2 保持兼容。
- `GraphWorkspace.tsx`、`graphLayout.ts`、`App.tsx`、`KnowledgeReading.tsx`、`ZoteroImport.tsx`、`JobHistory.tsx`、`GraphExplorer.tsx` 等接入图谱主视图、双语/英文回退、证据详情、拖动固定、独立布局自动保存、可选旧抽取对照与旧 Comparator。P3 候选关系保留虚线、审核与模型依据；NO_DECISION 不建科学边。
- `main.rs` 增加受限图谱/布局/补译 API 和 Zotero URI 白名单，通过 ShellExecuteW 打开 Zotero，不经过 Shell 命令。契约导出到 `packages/contracts/`；同步 AGENTS、README、API、进度、迁移计划、[实际验收报告](docs/v3-verification.md)与 52 项设计资产清单。
- 原生发现并修复论文无限分页与图谱论文筛选的缓存键冲突白屏；统一图谱位置状态并调整快速拖动起始阈值，原地点击不保存/固定；收窄详情关联遍历并折叠实验详情。新增 `test_graph_v3.py`、`test_v3_compatibility.py`、`GraphWorkspace.test.tsx`，扩展冻结引擎 smoke。

### 验证

- Anaconda researchgraph-studio：`scripts/check-phase0.ps1` 执行 Python 123 passed/2 skipped、Ruff/format/mypy、pip check、契约生成通过；随后因前端格式中止。修复后单独运行 `pnpm format:check`、`pnpm check`、`pnpm --dir apps/desktop test`、`pnpm build:web`，均通过；最终前端 **33 passed**。不把最初中止脚本记为完整通过。
- 详情修复后 `pytest tests/engine/test_graph_v3.py tests/engine/test_v3_compatibility.py -q`：19 passed；Rust `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml`：5 passed；参考 `pytest docs/tests -q`：12 passed，独立运行 `pytest docs/archive/v2/tests -q`：5 passed。
- 七批第 2 批分别注入客户端失败、timeout、429、非法 JSON、非法 Evidence ID；首批保留，恢复完成七批，相同配置再跑无新增模型调用。已收到但未提交结果可恢复，翻译不会覆盖 accepted 科学语义。此处均为离线 Mock，不是本轮真实供应商验证。
- 四份旧库副本 0004/0005/0008→0009，旧表旧列逐行一致，SQLite/外键检查通过，含 1508 节点 P3 副本。Zotero Local API 只读 TEST 分类实测 5 篇/6 PDF 可读，5 个登记源文件 hash 一致。
- 独立 v3 原生窗口：旧项目/论文/历史可读、证据页号/英文回退、打开 Zotero、拖动/固定/解除/缩放、侧栏折叠与重启保留通过；布局版本 8 的全份 JSON 重启前后一致。无 PowerShell 窗口，关闭后 GUI/Sidecar 进程为 0。最终再比对隔离原生库的 33 个旧表（不含运行任务和迁移版本表），原列原行无变动，integrity/foreign_key 均通过。
- `scripts/build-engine.ps1` 冻结引擎成功；扩展后的 `scripts/smoke-engine.py --executable ...` 在 System32-only PATH 下通过 P1/P2/P3 与统一抽取/投影/布局/补译/幂等/重启；PowerShell 5.1 `scripts/verify-windows-install.ps1 -EnginePath ...` passed，不能当作安装器验收。
- 本轮 `pnpm --dir apps/desktop tauri build` 正式 NSIS 构建成功，保存在 `.local/releases/v3-m0-m6-20261102/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,441,992 bytes；SHA-256 `A4A9B710DBDEF02508134302653227056775042C33737C8435002978B6ED3253`。仍为开发版本 0.0.1，包含 Schema 0009；安装器未安装或卸载验收。此目录及构建日志均被 Git 忽略。
- 安全：`python scripts/check-sensitive.py --gitleaks .local/tools/gitleaks-8.30.1/gitleaks.exe` 候选 324 文件通过；`git diff --check` 通过。最终 `python .local/v2-doc-check.py` 检查 84 份 Markdown、285 个本地链接、QA hash 和环境 JSON 通过；52 项设计资产 hash 全部匹配，四份不可用外部原文明确排除。暂存区为空，安装器/数据库备份被忽略。

### 问题与下一步

- 原生工具首次按 exe 路径误开同名旧安装版，使正式库经既有迁移 0005→0008。已关闭并只读核对原表原列逐行相同，备份保留；未执行抽取/编辑，未擅自覆盖或回滚。后续全部使用精确 process 路径与独立 v3 标识。此意外如实登记，不能声称正式库从未升级。
- Windows Credential Manager 中旧模型密钥不可读；已请用户在设置页重新录入，本轮尚未回复。真实 v3 P02/P04、供应商七批恢复/费用及真实关系审核均未验收；旧 v2 真实结果不替代本轮。M6 自动化和原生/构建已完成，不能称全部验收通过。
- 新安装器安装/卸载、干净 Windows、缺失 WebView2 与远端 CI 未测；现有安装保护未绕过。两项 symlink 权限跳过、Starlette/httpx 弃用、tzdata 与前端 chunk 提示保留。
- 四份补充外部原文路径仍不可用；QA 原件/来源登记保留。大图性能、真实术语/翻译科学准确率、OCR/逐字坐标仍非已验收能力。
- 下一步先补真实 API 与安装验收，完成本轮 M6 缺口；不自动进入 P4/P5。未 Commit/Push，私有数据/安装包/日志留在本机忽略目录。

## 2026-11-02 12:33 · DEV-0026 · 自动输出预算、截断恢复与实时点图

### 目标

- 处理用户 48 批任务第 2 批截断，取消手工最大输出上限；图谱改为点与边、实时力导向、双击固定；正常产品入口移除旧基线和 Mock。保留数据，不进入下一 Phase。

### 实际改动

- `model_capabilities.py`、`model_settings.py`、`providers.py`、`settings_api.py`、`extraction.py`：精确模型能力探测，未知使用服务默认；历史手工上限保留审计但不外发。失败/截断用量、推理用量、有效请求预算与部分原始输出留档，超时与设置一致、有界重试。
- `unified_extraction.py`：新计划合并相邻段落；持久化 plan/config/signature/证据 hash；旧 48 批任务按原身份恢复。仅失败叶批二分、最多三层；成功批与拆分子批幂等复用。
- `ForceGraph.tsx`、`forceSimulation.ts`、`graphLayout.ts`、`GraphWorkspace.tsx`、`style.css`：点与半透明低饱和边、实时邻居响应、hover、平移缩放、双击固定和独立聚焦；RAF 冷却停止，松手/稳定保存。原生发现快速拖动首事件阈值及受控坐标问题，使用零起始阈值与 position change，原地点击不写布局；冲突重载清空草稿并重新挂载画布。
- `src-tauri/src/main.rs`：原生发现跨页布局超过 16 KiB，只有已授权 graph/layout POST 放宽至 512 KiB；服务端仍最多 2000 个有限坐标，其他请求预算不变。新增 Rust 边界测试。
- `knowledge_visibility.py`、`graph_projection.py`、`graph_contracts.py`、知识/推理 API：正常视图隐藏未经人工修改的 Mock 节点，人工接受/修订及历史详情保留；分页最多附加 24 个真实父论文上下文节点和 REPORTS 来源边，主游标不变。
- `ModelSettings.tsx`、`KnowledgeReading.tsx`、`ZoteroImport.tsx`、`GraphExplorer.tsx`、`JobHistory.tsx`、`App.tsx`：真实全局模型入口、移除旧基线/Mock/手工 Token、去旧卡片画布、压缩项目头、长批次详情折叠与明确继续入口。同步生成 API 契约；离线测试与冻结 smoke 显式使用测试 Provider。
- 新 [ADR 0005](docs/adr/0005-model-capabilities-resume-force-graph.md)与[优化验收](docs/refinement-verification-20261102.md)；更新 AGENTS、README、progress、模型/API 说明、v3 架构/交互/迁移/实现注记、导航与映射，52 项设计资产 hash/清单同步。Schema 仍为 0009，无新增迁移。

### 验证

- 全量 `scripts/check-phase0.ps1` 最终通过：131 Python passed/2 skipped、35 React；Ruff/format、mypy 47 源模块、pip check、契约导出、TypeScript/eslint、前端构建均通过。最初新增测试计数与布局草稿失败已修复，没有把失败运行算作通过。最后快速拖动修改后再次运行 React 35 passed 与 format:check 通过。
- `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml`：6 passed；`pytest docs/tests -q`：12 passed；归档参考单独运行 5 passed。Windows symlink 两项跳过与 Starlette 弃用/前端 chunk 提示保留。
- `scripts/build-engine.ps1`、冻结 `scripts/smoke-engine.py --executable ...` 和 PowerShell 5.1 `scripts/verify-windows-install.ps1 -EnginePath ...` 通过；System32-only PATH、P0–P3 兼容、统一抽取/布局/补译/重启等均有本机报告。
- Windows 应用文件虚拟化导致普通路径读到旧副本，本轮经 UNC 定位真实库并一致性备份，凭据读取阻塞解除，未打印密钥。真实失败任务排队时冻结 8192，而当前设置已为 65536；不能宣称 65536 已实测截断。新计划样本 48→16、11→4，只算规划。
- 原 48 批真实失败任务在隔离副本恢复：跳过原成功第 1 批，拆分第 2 批为两个 11 证据子批，再完成两批 30/36 证据；新增 4 次真实调用全部通过 Schema/证据/Store，原 405 节点逐行不变、新增 55。保存进度 1→3→5/49，剩余 44 批未执行。正式库最后只读比对仍为 405 条且逐行一致。
- 四次实际调用 41,374 Token（reasoning_tokens 12,967 已包含其中），供应商无费用数据。验收调用预算产生两条未外发 acceptance_stop 记录，脚本包装器遗留 usage 使测试库汇总虚高；已单独计算校正报告，不把 65,773 当真实账单，不改写正式记录。
- 独立原生窗口：快速拖动/邻居响应、hover、双击固定、中文详情/英文证据/页码/PDF预览、平移/滚轮/Fit View、侧栏折叠及设置字段移除均通过；布局版本 15、110 个位置/1 固定节点全行 JSON 重启一致。启动无 PowerShell，退出后独立 GUI/Sidecar 为 0，用户原窗口保留。
- 正式 `pnpm --dir apps/desktop tauri build` 生成 NSIS，交付 `.local/releases/v3-refinement-20261102/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,439,880 bytes，SHA-256 `4F72C39C7C980D093E02C95A28CE58D918BD0CCCDA36AF9BC0884145D2AF147C`。安装器未安装/卸载实测，当前安装版未替换。
- 安全候选内容/Gitleaks 扫描通过，暂存区为空；文档链接/QA hash/环境 JSON 与 52 项设计资产校验通过，`git diff --check` 通过。所有真实库、调用日志、截图、安装器位于本机忽略目录。最终命令日志保存在 `.local/v3-refinement-20261102/`。

### 问题与下一步

- 当前供应商未返回模型输出或上下文上限，使用服务默认不等于已知模型最大值。完整剩余论文抽取、真实关系审核、干净机/安装器执行和万节点性能仍未验收；不能用离线测试代替。
- 4 份外部补充原文登记路径仍不可用，历史来源/QA 保留。原文定位仍为解析块范围，不宣称 OCR/逐字坐标准确率。
- 本轮结束；下一步由用户安装试用并反馈模型与图谱体验，按需补全文验收，不自动开始后续 Phase。未 Commit/Push。

## 2026-11-02 13:32 · DEV-0027 · 图谱可见性、局部引用修复与文献分区

### 目标

- 修复用户报告的悬停闪动、拖动消失、第二篇 Schema 失败；将论文导入/任务/文献分区折叠，PDF 与 Zotero 同级、笔记独立。减少 Computer Use，回归后交付安装包供用户反馈，不进入下一 Phase。

### 实际改动

- `ForceGraph.tsx`、`forceSimulation.ts`、`graphLayout.ts`、`style.css`：受控点节点稳定 width/height/measured，防止 React Flow 清空尺寸造成隐藏；坐标有限性检查、RAF 清理和边标签指针处理。新增 `e2e/graph.*`、Playwright 配置/开发依赖/脚本，真实渲染验证悬停、持续/快速拖动、邻居联动、固定/缩放/容器改变；原单元测试保留。
- `unified_contracts.py`、`extraction.py`、`unified_extraction.py`、新增 `extraction_repair.py` / `P02_local_link_repair.md`：精确 Schema 错误，仅对缺失局部引用执行一次受限端点修复。旧 P02 与 JSON Schema 不变、原始结果保留、修复运行关联来源；修复越界/拒绝/失败不入图，同任务不无限调用。其他非法响应仍可重新抽取未完成批次。新增 `test_extraction_repair.py` 覆盖七批恢复、禁止虚构/改写、原结果及旧节点保留、无额外调用。
- `WorkbenchSection.tsx`、`Papers.tsx`、`SourceIntegrations.tsx`、`App.tsx`、`KnowledgeReading.tsx` 与测试：三块折叠及项目内记忆，PDF/Zotero 平行入口，Obsidian 移至独立笔记来源，模型运行显示原始响应/修复来源。API 与数据库保持兼容，Schema head 0009，无迁移。
- 更新 AGENTS 的用户验收偏好、README/桌面说明、progress、运行 API、v3 交互/Prompt/计划、[ADR 0006](docs/adr/0006-graph-stability-and-local-reference-repair.md)和[实际验收](docs/stability-verification-20261102.md)，同步设计资产清单。

### 验证

- 实际失败源是本批 links 引用不存在的 local_ref；响应 JSON 合法、文献版本正确。备份/私人诊断在 `.local/stability-20261102/`。隔离副本真实模型 1 次端点修复，通过 Schema/Evidence/Store，生成 14 个领域节点标识；原 183 个知识节点全列逐行相同、旧任务签名匹配、原始 raw_output 保留、SQLite integrity/foreign_key 通过。1,725 Token（含 62 reasoning），供应商未报费用；未写正式库，未运行剩余 15 批。
- `scripts/check-phase0.ps1` 最终完整通过：139 Python passed/2 skipped、37 React；Ruff/format、mypy 48 模块、pip check、契约生成、TS/eslint、前端格式/构建通过。首轮 2 个 JSON/证据重试回归失败已修复并完整重跑；前端测试选择器错误修正。`test:browser` 2 passed，参考 v3/v2 分别 12/5 passed。
- `scripts/build-windows.ps1` 构建 PyInstaller/Tauri/NSIS 成功；冻结 `smoke-engine.py` 与 PowerShell 5.1 `verify-windows-install.ps1 -EnginePath ...` 通过，均使用独立数据；不是安装器原生验收。Rust 未改，本轮未单独重跑 Rust 单测。
- 新安装器保存在 `.local/releases/stability-20261102/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,442,557 bytes；SHA-256 `9BD990ED8B434E27A151C1F668282B6929181928F6CB1B713905D603D1569B62`。未替换用户当前窗口和安装版。
- 敏感内容/路径与 Gitleaks 扫描通过，暂存区为空；文档本地链接、QA hash、环境 JSON、52 项设计资产校验和 `git diff --check` 通过。所有备份、原始模型数据、安装包/运行日志在本机忽略目录，未 Commit/Push。

### 问题与下一步

- 用户按验收步骤安装，反馈悬停/拖动、三块折叠与第二篇“继续未完成批次”的结果。本轮未使用 Computer Use，不把浏览器/单批结果当作原生或全文完成。图谱科学准确性、真实关系审核、干净机/安装执行和远端 CI 未验收。
- 两项 symlink 权限跳过、Starlette 弃用/前端 chunk 提示保留；四份外部补充原文登记路径仍不可用。无新增 Phase 工作。

## 2026-11-02 14:28 · DEV-0028 · 空占位字段兼容与有界超时恢复

### 目标

- 修复两个新任务的 findings_placeholder Schema 失败和请求超时，保留成功批次/原模型响应/用户知识；完成回归和可供用户安装的包，不进入下一 Phase。

### 实际改动

- 新 `extraction_normalization.py`，以及 `extraction_repair.py` / `extraction.py`：只规范化 ClaimDetail 中已观察到的 null 空占位键，不接受其他额外字段；保存规范化路径与原始响应。旧失败响应可直接复用，Schema/来源/证据/Store 仍强制校验，不增加模型调用。成功后清理旧错误状态。
- `unified_extraction.py`、新运行模板 `P02_unified_section_extract_v3_2.md`：新任务持久化 Prompt 名称，旧任务保留旧签名与计划；新计划 8000 字符/64 证据目标、4–16 候选提示，表格缺列头不得猜测。按原文字数二分超时根批一次，子批再失败即停；旧已三次超时的同证据根批恢复时直接拆分。成功批次与成功子批不重发。
- `providers.py` / `extraction.py`：记录连接/请求发送/响应头/响应体阶段与耗时，不打印密钥或原文；明确响应超时转交有界拆分，连接/429/5xx 等保留有限重试；未增加 90 秒/180 秒时限。
- `KnowledgeReading.tsx`、`JobHistory.tsx`：展示空占位规范化和“超时后缩小”。新 `test_extraction_reliability.py` 14 项覆盖精确兼容、旧结果零调用续跑、拆分停止/恢复/幂等、超时阶段脱敏。
- 更新 AGENTS、README、docs 导航、API/模型说明、v3 架构/Prompt/计划、progress、[ADR 0007](docs/adr/0007-extraction-null-markers-and-timeout-adaptation.md)与[验收记录](docs/extraction-reliability-verification-20261102.md)。Alembic 仍 0009、DTO 仍 unified-v3.1，无数据库迁移；既有改动全部保留。

### 验证

- 对实际 UNC 用户库做只读一致性备份，当前基线 156 条知识；前轮 183/405 是历史，不恢复覆盖。诊断确认 5 个 `findings_placeholder:null`，UI 摘要只列前 4 个；另一任务第 7 批 8371 字符/75 证据已三次约 90 秒超时。
- 真实副本 Schema 任务恢复成功 4/4：原成功批及空标记失败响应均复用，只调用剩余两批，分别 88.656/45.219 秒、22,842/12,829 Token。原 156 条知识全列逐行相同、原 raw_output 保留、SQLite integrity/foreign_key 通过；未写回正式库。
- 超时任务保留六批后根批拆分，进度 6/17；4185 字符/34 证据子批发送 0.032 秒，等待响应头 90.047 秒仍超时。新版 P02 与进一步减少候选/表格约束的同源实验也各一次超时，未运行其余批次。短连接请求 1.907 秒成功、138 Token；已知真实用量合计 35,809 Token，三次超时无供应商用量，不能当作零费用。没有宣称超时已修复完成。
- 完整 `pwsh -NoProfile -File scripts/check-phase0.ps1` 通过：153 Python passed/2 skipped、37 React；Ruff/format、mypy 49 模块、pip check、契约、TS/eslint、前端构建通过。最后候选提示/旧错误清理/表格约束调整后 `pytest tests/engine/test_extraction_reliability.py tests/engine/test_extraction_repair.py tests/engine/test_extraction_refinement.py tests/engine/test_graph_v3.py -q`：44 passed。
- 最终 `scripts/build-windows.ps1` 构建 PyInstaller/Tauri/NSIS 成功；最终冻结 `scripts/smoke-engine.py --executable ...` 与 PowerShell 5.1 `scripts/verify-windows-install.ps1 -EnginePath ...` 通过。PS 5.1 首次被主机执行策略在运行前拒绝，仅对本次子进程加 ExecutionPolicy Bypass 后通过；未改系统策略。图谱/Rust 源码未改，未重复交互/单测，Tauri release 编译通过。
- 安装器保存于 `.local/releases/extraction-reliability-20261102/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,448,362 bytes，SHA-256 `446A533B287C19E3FDEBCC088B15854B932D5A37FFAC45F46307CB19BB9B0AF5`。未执行安装器、未替换用户窗口；最终报告及本地试验日志位于 `.local/extraction-reliability-20261102/`。
- 收尾安全内容/Gitleaks 扫描 347 候选文件通过，暂存区为空；92 份 Markdown/327 个本地链接、QA hash、环境 JSON、52 项设计资产与 `git diff --check` 通过；4 份不可用外部原文明确排除。真实响应/论文/备份/运行日志/安装器均在本机忽略目录，不进入源码。未 Commit/Push。

### 问题与下一步

- Schema 故障已有真实恢复证明；当前真实模型在缩小批次后仍响应慢，尚不能保证第二个任务完成。短请求通过不能替代论文抽取；后续需在明确的模型/推理配置与调用预算下调查供应商生成延迟，避免不断重试产生未知费用。未静默改变用户配置，旧任务快照不自动随设置变更。
- 按用户偏好未使用 Computer Use；先由用户安装本轮包，对 Schema 失败任务“继续未完成批次”并反馈。原生安装/卸载、干净 Windows、完整超时论文与真实关系审核仍未验收。
- 两项 Windows symlink 权限跳过、Starlette/httpx 弃用和前端 chunk 提示保留；四份补充外部原文登记路径仍不可用，QA/历史来源保留。没有新增 Phase。

## 2026-11-02 16:25 · DEV-0029 · 阅读辅助分层知识图谱设计与参考契约

### 目标

- 按用户讨论重设计 Schema/Prompt/docs：通用科研论文阅读辅助、论文直达知识图谱、核心结论组织支撑、完整证据与候选保留；追加要求取消流程中的人工审核。不开发下一 Phase。

### 实际改动

- 重写 docs/00–09，确立 indexing/extracting/integrating/selecting/publishing 自动工作流，Paper→核心 Claim→支撑、多对多单元、选择/知识/布局分版本；未选候选可检索，未来 Query/Wiki 逐段来源依赖。没有人工审核/待审/接受驳回步骤；历史状态保留，新流程只用自动有效性与显示角色。
- docs/schemas/contracts.py 及 29 份 JSON Schema、sqlite_reference.sql：显式候选 union、SourceTable、CandidateRecord、KnowledgeUnit、GraphSelection、显示偏好、上下文守卫和未来问答/页面引用。引用类型、source hash/offset、条件状态、单元路径、完整选择快照与默认图谱拓扑可执行校验；正式运行仍 0009/unified-v3.1/P02 3.2。
- docs/prompts 13 份重写（reading-1.0），新增 P12 论文整合、P13 核心选择。25 个虚构示例、index/README 与 78 项参考测试；不使用用户论文或模型数据。原 v3 52 项资产归档到 docs/archive/v3，保留旧契约测试和来源；不把旧报告反写为新验收。
- 新 [ADR 0008](docs/adr/0008-reading-knowledge-graph.md)、[兼容映射](docs/migration/v3_to_reading_assessment.md)、[验证记录](docs/reading-design-verification-20261102.md)与变化摘要；更新根 AGENTS/README、导航、API 目标边界、progress、下一轮模板、清单哈希。

### 验证

- Conda researchgraph-studio：`python docs/schemas/contracts.py` 生成29；`pytest docs/tests -q` 78 passed，归档 v3/v2 分进程 12/5 passed。Ruff check/format 通过；生成资产与 Schema 相等、Prompt 输出契约对应、内存 SQLite FK/共享成员/保留旧节点用例通过。
- 先前参考文件格式/冒号问题已经修正并重新执行，不把失败尝试计为成功。应用源码/运行 Prompt/API 生成文件未改；本轮未跑应用全量回归、真实模型、迁移或安装，不复用前轮成绩当本轮实测。
- 收尾 201 个非文档文件哈希不变；当前 88/归档 52 项资产校验，归档 27 项非 Markdown 原字节一致；125 份 Markdown/420 本地链接、QA hash、环境 JSON 通过，四份外部不可用原文明示排除。440 候选文件路径/内容与 Gitleaks 及 diff 检查通过。本机忽略目录保存范围快照和日志；暂存区为空、未 Commit/Push。

### 问题与下一步

- 本轮 R0 设计交付，软件仍 P3/v3 自动建图质量迭代，M0–M5 核心已接入、M6 未全部验收。下一步 R1 审计/备份、加性持久化与旧 ID/历史状态/DTO 适配，随后 R2 候选抽取、R3 自动整合选择、R4 分层 UI、R5 真实验收；不进入 P4 Query/P5 Wiki。
- 真实响应超时仍 6/17、真实科学关系边和安装/干净机仍有未验收项；参考 Schema 不等于科学准确或真实 Provider 兼容。模型预算/输出体积需在 R2/R3 真实验证。
- 四份外部补充原文登记路径仍不可用，历史来源/QA 保留。用户现有知识、原始资料和安装版本未改。


## 2026-11-02 17:36 · DEV-0030 · 安全推送基线与 R1–R5 阅读图谱实现

### 目标

用户授权先提交推送已有成果，再顺序开发 R1–R5；保留私人数据与现有知识，不进入 P4/P5。

### 实际改动

- 先提交306文件既有P3/v3/R0成果 `8d3ba1d`，内容扫描304暂存文件、候选440与13提交历史Gitleaks通过，官方SSH443普通推送main并核对远端；HTTPS实测连接失败，没有修改全局Git/网络。该提交CI 41415123193全部成功。
- R1：Alembic0010和reading_models/store，新增候选质量、结论单元/成员、选择快照/活跃指针、展示偏好、阶段检查点；复用原知识/原文/证据/模型表。隔离备份当前正式库275知识，迁移前后所有旧表逐行一致，原文/原模型输出保留。
- R2：独立reading_contracts/P02_reading_extract，10类候选及严格证据/归属/状态；正常PDF/Zotero入口显式paper-reading-v1，旧任务不换Prompt/签名。R3：P12/P13有界整合、重复组范围检查、根路径闭合、冻结窗口与跨任务缓存、CAS发布和密度/偏好重算。见[ADR0009](docs/adr/0009-reading-pipeline-implementation.md)。
- 实测修正：严格候选合法时仅隔离非法端点关联，参数记录原因且原输出不改；无路径成员保留可检索并标partial，不编造替代关系。
- R4：graph_projection/reading_projection及GraphWorkspace/ReadingControls/KnowledgeReading，默认论文→核心Claim→展开支撑、共享节点、候选搜索、密度/偏好，无人工审核控件。旧API与review历史保留。Comparator能读取新SourceAssertion支撑条件。
- Tauri桥接新增白名单，任务阶段/用量/覆盖缺口展示，OpenAPI生成同步；更新README、AGENTS、docs00–09、progress、ADR和实际验收。

### 实际验证

- Conda researchgraph-studio；`scripts/check-phase0.ps1`最终通过：175 Python passed / 2 symlink skipped，Ruff/format/mypy、依赖、契约、前端格式/类型/lint/build。之后新增共享投影用例，针对性4通过；React最终39通过。浏览器真实React Flow3通过，Rust7通过和clippy -D warnings通过；参考docs/tests78通过。
- 7批第2批超时离线故障注入：首批不再调用、续跑7/7，8次抽取请求含1失败；整合/选择失败不重抽。Mock仅自动化，不作为真实质量证明。
- 真实API：两篇真实论文最初全文尝试分别0/9、0/34停在非法关联，另一次90秒timeout。修正后复用两份已收P02响应，局部21候选、2/3核心单元经真实P12/P13发布且标partial，实际投影Paper边2/3条。已知71,260 Tokens，timeout用量未知。不是全文或科学质量通过；详细范围见[验收](docs/reading-implementation-verification-20261102.md)。
- 最终PyInstaller/Tauri/NSIS通过；冻结引擎smoke包含paper-reading-v1完整离线闭环及重启，原功能兼容通过；PowerShell5.1仅System32 PATH测试通过。首次PowerShell受执行策略阻止，使用当前进程Bypass执行；又发现旧0009断言，更新0010后通过，未更改系统策略。
- 安装包仅本机 `.local/releases/reading-graph-20261102/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,526,897字节，SHA256 `a7fd43ef7818a682a3ff490dd7706f58b6e3965a9aca59c60ca5171de0794660`。未安装替换当前软件，未使用Computer Use。
- 17:58 收尾去除 Comparator 遗留审核筛选/文案，保留明确标识的历史状态；边详情区分导航/原文/模型推断。React39、TS/eslint/格式、重打包与冻结smoke、PowerShell5.1再次通过。测试启动曾遇 Vitest 不支持 runInBand、Conda 控制台编码错误，改为直接 Node 命令；文案断言不一致修正后完整前端通过，未将失败尝试记为通过。

### 问题与下一步

R1–R4代码已实施；R5部分通过，完整真实论文超时/贡献覆盖、不同论文类型科学质量、用户安装体验仍待验收。精确表格/OCR/逐字定位未完成；四份外部补充原文路径不可用。提供安装操作步骤，下一步只补当前R5，不进入P4/P5。私人PDF、批注、密钥、数据库、原输出、日志、安装器继续留本机，最终提交安全检查和远端结果追加记录。

## 2026-11-02 18:13 · DEV-0031 · 远端验收等待修正与交付记录

### 目标与改动

- `94b3a4d` 的75文件实现已普通推送main，462候选/75暂存及1提交历史Gitleaks与路径审查通过；安装器、私人论文、数据库、凭据和模型响应没有进入提交。
- 首次CI 41425098035为177 Python通过/1失败：48批旧任务续跑超过测试助手固定20秒期限。仅长用例改为90秒有界等待，助手补阶段/批次诊断，不改变产品请求timeout或回退重试。
- 修正文档导航、Schema/API首页、下一轮模板中的旧R0/0009指引，重算88项规范资产清单；下一步仍是R5全文质量/响应可靠性和用户安装反馈。

### 验证与剩余

- 首次CI安装阶段因上游失败跳过，不能称安装通过；Conda环境运行 `pytest tests/engine/test_extraction_refinement.py tests/engine/test_ingest.py -q` 为19 passed（23.41秒），Ruff/format通过。后续远端结果在完成后补记。
- 修正后 CI [41426893999](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41426893999) 全部成功：Windows 178 Python/39 React/7 Rust、冻结引擎、NSIS 及 installed-app 验证通过。GitHub 工件 ID 为 13133122133（安装器）和 13132573949（安装验收报告）；本机交付包仍以 `.local/releases/reading-graph-20261102/` 的 SHA256 为准。
- 两篇真实论文的局部链路与本机安装器保持，全文/原生反馈仍未完成，不进入P4/P5。

## 2026-11-02 19:03 · DEV-0032 · 修复原生宿主Schema握手与安装验收盲区

### 目标与实际改动

- 用户安装后提示本地引擎未连接。定位到 `apps/desktop/src-tauri/src/main.rs` 仍比较Schema0009，而Python返回0010；修复为协议/Schema常量，并检查database ready及FTS5。
- 增加对Python迁移head的版本一致性测试、真实打包引擎通过原生Host启动/停止/重启测试。`.github/workflows/phase0.yml`显式执行打包集成测试。
- 修正 `scripts/verify-windows-install.ps1`：子进程返回401不再足够，必须读取无凭据的宿主启动握手记录并匹配父子进程。上一轮CI确实success，但没有测到宿主已接受版本，现明确更正其验收范围。
- 更新progress和阅读图谱验收报告；不改正式库、来源原件、密钥或旧知识，不进入后续Phase。

### 验证

- Rust9通过/1显式忽略，打包集成另行1通过；fmt/clippy通过。PowerShell5.1对实际握手检查函数的6项合成场景通过。独立数据，无Computer Use。
- 本轮PyInstaller/Tauri/NSIS、冻结smoke与PowerShell5.1 EnginePath已通过；增加握手记录后重建最终宿主与安装器，包哈希和交付结果在完成后补记。
- 用户本机覆盖安装后的连接/数据反馈待验证；前轮全文抽取和质量限制保持，不将此启动修复写成全文验收完成。
- 最终修复包38,523,711字节，SHA256 `3ef49f88f70b5d6b4f82cdbacc3f7185e85500f39734b5d0d3b14b2cb0661203`，保存在本机 `.local/releases/reading-graph-20261102-schema-fix/ResearchGraph Studio_0.0.1_x64-setup.exe`，未替用户执行覆盖安装。
- 修复提交 `21b64f6` 已普通推送main，远端与本机一致；462候选文件/6暂存文件及该提交Gitleaks通过，工作区无私人运行产物。新的 [CI 41433986320](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41433986320) 已触发，截至记录时仍运行，未计为通过。

## 2026-11-02 19:31 · DEV-0033 · 阅读抽取精确重复恢复与批次状态说明

### 目标

- 回答全文单次调用与后台分批的区别，定位用户新任务的超时拆分和 batch(value_error)，在 R5 范围内修复可确定恢复的问题。

### 实际改动

- `reading_validation.py` 先验证完整字段/列表上限/证据，再仅合并同编号、完整原始对象相同的重复；冲突编号明确报错。原始响应保留，领域 Schema 未放宽。
- `extraction.py`、`unified_extraction.py` 允许原失败阅读响应经过重校验续用，记录 `reading_normalization` 索引审计，Store 和成功批次幂等保持；`extraction_repair.py` 为已知引用校验错误提供安全中文原因。
- `JobHistory.tsx`、`KnowledgeReading.tsx` 显示“已保存（超时拆分后）”和去重信息，区分子批保存与全文完成。增加合成恢复/边界和 React 状态测试。
- 新 ADR 0010 与实际报告，同步 AGENTS、docs/progress、docs/README、06 计划与资产清单。运行 Prompt/Schema/计划签名/head0010 不变，无迁移；不更改正在运行软件或用户正式数据。

### 验证

- Conda `python -m pytest -q tests/engine/test_reading_response_recovery.py tests/engine/test_reading_recovery.py tests/engine/test_reading_extraction.py tests/engine/test_extraction_reliability.py`：39 passed；旧失败响应零新增 P02 调用恢复，成功批次保留。
- `scripts/check-phase0.ps1`：189 Python passed/2 skipped、40 React passed；Ruff/format/mypy/依赖/契约/前端类型/lint/build 通过。非阻塞的 Starlette 弃用及前端包体积提示仍在。
- 用户真实失败响应在 `.local/reading-failures-20261102/replay-data/` 回放：28→20 候选、24 关联保留；307 原知识全列逐行不变，原 raw_output 均保留，重复恢复不新增知识，SQLite 完整性/外键通过。副本仅 1/34，到下一批需模型调用时停止；新调用/Token=0，不是全文验收。
- `scripts/build-windows.ps1`、`scripts/smoke-engine.py --executable ...`、PowerShell5.1 `verify-windows-install.ps1 -EnginePath ...` 通过；`cargo test --locked packaged_engine_connects_through_native_host_and_restarts -- --ignored` 1 passed。源代码和打包 smoke 的 Provider 为离线合成，不冒充真实模型新调用。
- 包 `.local/releases/reading-response-recovery-20261102/ResearchGraph Studio_0.0.1_x64-setup.exe`：38,527,857 字节，SHA256 `073ae8dd5559e5b23383f0ebda476e4a489bf95dc27bc5d308c8f51d54fb1498`。未替用户安装，不使用 Computer Use。

### 问题与下一步

- 全文新流程、用户覆盖安装和科学质量仍未全部验收；保留原任务等待用户续跑反馈。预算自适应单批/多批只记录方案，当前仍使用冻结分块，不宣称“单次全文”已实现。
- 当前旧 unified-v3 任务快照为 5/5、17/17 成功，前轮 6/17 仅为历史。四份外部原文登记路径不可用限制保留。
- 本轮无 Commit/Push；私人库、响应、诊断、安装器仅在 `.local/`。465 候选文件内容/路径与 Gitleaks 扫描通过，diff 检查通过，暂存区为空。132 Markdown/457 可用本地链接/88 项资产清单通过；4 个已登记外部来源不可用，未计为通过。

## 2026-11-02 20:52 · DEV-0034 · 腾讯云流式适配、旧任务续接与部分图谱

### 目标

- R5：针对腾讯云Token Plan企业版 `deepseek-v4.1-flash` 核验能力与思考行为，处理子批超时及默认图仅论文的问题；保护原库、冻结任务和未提交成果，不进入P4/P5。

### 实际改动

- 新 `model_adapters.py` / `chat_stream.py`，修改providers/model_settings/settings_api/extraction：准确端点/模型的官方能力兜底，1M/384K；新抽取非思考JSON预算32K、新推理思考预算64K，端点更低上限优先。SSE流、2MB正文/32MB传输边界、总时限≤300秒、活动计数、失败partial安全保留。
- 新 `reading_resume.py`，修改app/models/schemas/unified_extraction及原生main.rs/api.ts/JobHistory：用户显式创建确定ID续接任务，原模型快照/签名/计划/成功批次不变，只有剩余调用使用新策略。原任务不改，新增调用用量独立记录；当前文献活动任务拒绝并发建图。
- 新 `reading_status.py`、更新reading_api/reading_projection/graph_contracts与GraphWorkspace/ReadingControls：显示候选保存/发布差异、未完成批次和部分图入口；P12/P13保留覆盖缺口，不重抽PDF、无人工审核。
- 新/扩展Python与React行为测试、Rust路由边界，更新OpenAPI/TypeScript、README、AGENTS、docs/progress/api/model-configuration/06与导航。新增[ADR0011](docs/adr/0011-tencent-streaming-and-reading-recovery.md)、[实际验收](docs/tencent-recovery-verification-20261102.md)。head0010，无迁移；上一轮精确去重实现完整保留。

### 验证

- 官方腾讯文档确认默认thinking.high、不建议同时JSON；真实库快照失败请求主要等待非流式响应90秒。两篇新流程保存6/12、4/35批，206/190条知识，0单元/选择，解释主图空而非数据丢失。
- 真实一次小批调用：2137字符/14证据，9.531秒、4候选/2关联、7541 Tokens、reasoning0，Schema/证据/Store通过，396旧知识逐行保持。新增网络仅1次，正式库未改；费用供应商未报告。
- 同真实响应零网络回放到旧任务续接副本，6/12→7/12，签名/旧Job/396原知识不变，SQLite完整性/外键通过。回放脚本首次查询错误状态未执行，修正为succeeded后在新副本通过；不属于额外API调用。
- `scripts/check-phase0.ps1`：214 Python passed/2 skipped、45 React passed；Ruff/format/mypy63文件/依赖/契约/前端lint/type/build通过。`pnpm --dir apps/desktop test:browser`：3真实ReactFlow通过。Cargo9单测及clippy通过；打包后单独宿主握手/重启1项通过。
- `scripts/build-windows.ps1`、冻结引擎smoke、PowerShell5.1 EnginePath通过。包`.local/releases/tencent-streaming-recovery-20261102/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,552,219字节，SHA256 `c6febf559b1b0223d5bfd1234b9f7cff2f1c658fa47ed4bea18457fa00bfd723`。未覆盖安装/操作原生窗口。
- 最终敏感内容/路径与Gitleaks扫描474文件通过，diff检查通过、暂存区为空；文档134份Markdown/472本地链接/88当前资产清单通过，4个登记外部来源不可用如实保留。没有Commit/Push。

### 问题与下一步

- 真实单批通过不能替代全文或P12/P13真实部分建图；两篇完整任务、科学质量和用户安装反馈待验收。其他真实服务SSE未测，单次全文策略未实现，既有Starlette/前端包体警告保留。
- 四份外部原文路径不可用限制保留。私人副本、诊断、响应、安装器仅在忽略目录；未Commit/Push。最终内容/链接检查见本轮报告。

## 2026-11-02 21:27 · DEV-0035 · 按模型上限输出、紧凑Schema与普通续接

### 目标

- 按用户纠正取消“使用腾讯云适配继续”专属界面，让384K可用能力减少输出截断；精简知识抽取表示，保护原知识/证据/成功批次，不进入下一Phase。

### 实际改动

- `model_adapters.py`删除额外32K/64K预算，保留端点能力/剩余上下文约束；`app.py`将适用续接合入普通retry，JobHistory/ModelSettings移除供应商操作与旧预算说明，旧接口兼容留存。
- 新`reading_wire.py`、`prompts/P02_reading_extract_compact.md`，wire=reading-compact-1；共同language、相同summary省略、Schema限定SourceText原文字符串形式，确定性展开到原领域1.0。不会把任意数值、未知键或错误证据转换为合法内容，数值/条件/原语义保留。
- `unified_extraction.py`按冻结计划选择新旧Prompt/Schema，`reading_validation.py`展开后严格字段/来源验证，保留raw_output和逐字段规则审计，重复检查基于原wire对象；`extraction.py`兼容新格式失败响应复用，Mock仅测试。旧领域/Prompt文件无diff，head0010无迁移。
- 新15项wire场景，调整模型上限、普通续接、旧响应回归；同步AGENTS/README、Schema/Prompt/计划/API/模型说明/导航，新增[ADR0012](docs/adr/0012-compact-extraction-and-model-output-ceiling.md)和[验收](docs/compact-output-verification-20261102.md)。ADR0011的旧32K/64K预算和专属按钮标为后续替代，历史实测不改写。

### 验证

- 真实API一次请求：2137字符/14证据，max_tokens393216被接受，1秒首字节、26.984秒完整返回、10445 Tokens（reasoning0）。未截断；首次因Finding.baseline字符串触发model_type，完善新版明确简写后重验同一响应，新增调用0、保存12候选/10关联、2无效关联隔离。396旧知识逐行不变，原raw_output/SQLite完整性/外键保持。正式库未改动。
- 该真实响应wire14968字节、展开19672字节，约24%节省；Schema10419/原11734字节。不是通用压缩率，不把字节当Tokens。最终Prompt增加简写说明后未再收费调用；真实证据是已收到响应的最终本地校验。
- `scripts/check-phase0.ps1`最终229 Python passed/2 skipped、45 React passed，Ruff/format/mypy64文件/pip/契约/前端lint/type/build通过。一次lint行宽失败后修正并完整重跑。两项文件链接条件跳过和既有Starlette/单包体积警告保留。
- `scripts/build-windows.ps1`、冻结引擎smoke、PowerShell5.1 EnginePath通过；打包宿主握手/重启1项通过。没有将前轮9项Rust单测/3项浏览器测试算作本轮执行。
- 新包`.local/releases/compact-extraction-20261102/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,557,759字节，SHA256 `b23c132f7c4833354ecb3141be3dd2ed513bf9746ff82907598f8e159b8bc109`。未覆盖安装、无Computer Use。
- 最终479源码候选内容/路径/Gitleaks扫描通过；diff通过、暂存区为空，137 Markdown/491本地链接/88资产清单通过。4个登记外部路径不可用如实保留。

### 问题与下一步

- 全文质量、最终Prompt再次真实生成、完整图谱与用户安装体验仍待验收。更大上限不保证供应商永不超时/截断，仍保留有限停止/拆分/恢复。下一步仍R5，不进入P4/P5。
- 四份外部原文登记路径不可用保持。私人数据、响应、安装器只在忽略目录，未Commit/Push；最终扫描与链接结果见报告。

## 后续条目模板

```markdown
## YYYY-MM-DD HH:mm · DEV-XXXX · 本轮标题

### 目标
- 对应需求/阶段：
- 本轮完成条件：

### 实际改动
- 改了什么、原因、关键文件：
- 设计/数据迁移决定（链接 ADR）：

### 验证
- 执行的命令/场景：
- 实际结果及证据路径：
- 未执行的检查与原因：

### 问题与下一步
- 已知问题、影响和解决方向：
- 下一项可执行任务：
- Git 提交/版本（确实存在时填写）：
```

## 2026-11-02 22:59 · DEV-0036 · 新版范围、Schema闭合与真实续接验收

**目标**：解决waiver校验及拆分后超时，统一新版阅读Schema，检查整条抽取—整合—图谱链路，保留原数据。

**实际改动**：
- reading_scope/store/api/projection/selection及knowledge_api把新版候选与旧图谱历史分开；reasoning_api/context/contracts和GraphExplorer补齐比较来源/召回过滤。领域1.0/head0010不变，无数据库迁移。
- reading_upgrade、unified_extraction、app/models为旧失败任务创建独立续接；成功批引用旧操作，合法已收响应复制并记录零调用，保留原Job/ModelRun。新计划升级Prompt/模型传输策略，未无限加timeout。
- reading_wire/validation与新P02_compact_v2/P12_v2/P13_v3修正说明字段矛盾；严格科学/来源校验仍保留。整合根优先、非法建议隔离、异条件重复不折叠，所有raw保持。
- JobHistory区分旧失败/新续接，正常阅读/图谱/比较均限定新Schema。新增升级、范围、说明映射、非法提议和预算窗口回归；更新既有fixture的真实领域来源及历史隔离预期。
- 同步README/AGENTS、docs/03/05/06/api/参考Prompt，新增ADR0013及实际报告，更新清单。

**实际验证**：使用Anaconda researchgraph-studio。真实正式库只读备份后隔离执行：waiver响应19候选/11关联恢复、4关联隔离；9/12→12/12，两次新P02为24.75/19.44秒。后续逐步发现并修复整合缺陷，用已收到响应和检查点继续，发布22核心单元。重开默认23/展开28节点29边，节点均新版，边闭合；422原知识、48原模型记录、9原任务、934证据/925块及来源全列保持，完整性/外键通过。最终P13模板另1窗口8根真实通过。累计15真实调用/213503 Tokens，含诊断失败，供应商未提供金额。

scripts/check-phase0.ps1首次集成回归暴露旧测试API升级和历史适配预期，修复后243 passed/2 skipped、46 React通过；Ruff/mypy66文件/pip/契约/前端检查构建通过。pnpm --dir apps/desktop test:browser为3通过。Windows构建、冻结引擎smoke、PowerShell5.1 EnginePath五项、Rust9单测及1原生打包宿主连接/重启通过；补齐比较范围后再次构建/复核结果见本轮报告。未用Computer Use操作用户界面，未替用户安装，未Commit/Push。

**限制/下一步**：实际图为partial，展开支撑仅3 Method/2 Concept，表格上下文和有据关联覆盖仍不足；本轮不是两篇全文质量通过。最终P13新模板单窗口不冒充全篇重复验证。等待用户安装续接反馈，继续R5质量。四份外部补充原文登记路径仍不可用；保留原知识、历史批注/附件/来源，不进入下一Phase。

**提交前补记**：用户本轮明确授权提交与推送。比较器范围补齐后最终243 Python/2跳过、46 React及所有静态/契约/构建再次通过；新包冻结引擎smoke、PowerShell5.1五项与原生宿主连接/重启再次通过。全内容Gitleaks与路径扫描489文件通过，143 Markdown/500本地链接/88资产清单通过，4外部原文仍不可用。待核对暂存内容后普通推送main，Git/CI结果另补记。

**2026-11-02 23:36交付补记（Asia/Shanghai）**：暂存77文件内容/路径扫描通过，已提交并普通推送main `1c28137`。首次CI 41468861276回归/契约通过，PyInstaller成功，smoke因关系详情404失败，安装任务跳过。脚本按各列表首行配对可能得到不相关合成Claim，NO_DECISION无候选却请求空ID；原脚本本机5次通过，控制列表首条样本后复现相同404。`scripts/smoke-engine.py`改为按明确共同原文配对Claim/Method，并先断言候选存在。修复后冻结smoke连续两次通过、Ruff/格式通过；未更改产品源码、安装器或用户数据。即将安全扫描后提交推送CI修复；远端复跑结果另补记。
