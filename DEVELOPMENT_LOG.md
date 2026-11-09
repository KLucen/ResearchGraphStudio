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
- [环境报告](docs/archive/reports/environment-check.md)与[机器快照](docs/environment/2026-10-27.json)
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
- 最终检查：21 份 Markdown、98 个本地链接及五份用户原文 SHA-256 通过，安装器哈希与记录一致。PowerShell 脚本语法检查通过。汇总见 [Phase 0 验证记录](docs/archive/reports/phase0-verification.md)和[环境增量 JSON](docs/environment/2026-10-28-phase0.json)。
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
- 更新 [RG-006 原生验收报告](docs/environment/2026-10-31-phase1-jobs-native.json)与 [Phase 1 记录](docs/archive/reports/phase1-verification.md)，撤回无法由旧桌面桥接实现的“加载后 13 项”结论。

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

- 新增 [CI 验收摘要](docs/environment/2026-10-31-phase1-jobs-ci.json)，更新 [原生验收报告](docs/environment/2026-10-31-phase1-jobs-native.json)、[Phase 1 记录](docs/archive/reports/phase1-verification.md)、ADR 0006、API/计划入口相关状态和 README。CI 通过、原生分页未复测、M1/干净环境未完成分别记录。
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

- 新增 [Phase 3 本机验收记录](docs/archive/reports/phase3-verification.md)，记载全局设置迁移、Zotero Test collection、三篇真实论文抽取、来源完整性、P03–P05、Mock 关系审核、侧栏及图谱重启验证和限制。
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
- `main.rs` 增加受限图谱/布局/补译 API 和 Zotero URI 白名单，通过 ShellExecuteW 打开 Zotero，不经过 Shell 命令。契约导出到 `packages/contracts/`；同步 AGENTS、README、API、进度、迁移计划、[实际验收报告](docs/archive/reports/v3-verification.md)与 52 项设计资产清单。
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
- 新 [ADR 0005](docs/adr/0005-model-capabilities-resume-force-graph.md)与[优化验收](docs/archive/reports/refinement-verification-20261102.md)；更新 AGENTS、README、progress、模型/API 说明、v3 架构/交互/迁移/实现注记、导航与映射，52 项设计资产 hash/清单同步。Schema 仍为 0009，无新增迁移。

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
- 更新 AGENTS 的用户验收偏好、README/桌面说明、progress、运行 API、v3 交互/Prompt/计划、[ADR 0006](docs/adr/0006-graph-stability-and-local-reference-repair.md)和[实际验收](docs/archive/reports/stability-verification-20261102.md)，同步设计资产清单。

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
- 更新 AGENTS、README、docs 导航、API/模型说明、v3 架构/Prompt/计划、progress、[ADR 0007](docs/adr/0007-extraction-null-markers-and-timeout-adaptation.md)与[验收记录](docs/archive/reports/extraction-reliability-verification-20261102.md)。Alembic 仍 0009、DTO 仍 unified-v3.1，无数据库迁移；既有改动全部保留。

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
- 新 [ADR 0008](docs/adr/0008-reading-knowledge-graph.md)、[兼容映射](docs/migration/v3_to_reading_assessment.md)、[验证记录](docs/archive/reports/reading-design-verification-20261102.md)与变化摘要；更新根 AGENTS/README、导航、API 目标边界、progress、下一轮模板、清单哈希。

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
- 真实API：两篇真实论文最初全文尝试分别0/9、0/34停在非法关联，另一次90秒timeout。修正后复用两份已收P02响应，局部21候选、2/3核心单元经真实P12/P13发布且标partial，实际投影Paper边2/3条。已知71,260 Tokens，timeout用量未知。不是全文或科学质量通过；详细范围见[验收](docs/archive/reports/reading-implementation-verification-20261102.md)。
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
- 新/扩展Python与React行为测试、Rust路由边界，更新OpenAPI/TypeScript、README、AGENTS、docs/progress/api/model-configuration/06与导航。新增[ADR0011](docs/adr/0011-tencent-streaming-and-reading-recovery.md)、[实际验收](docs/archive/reports/tencent-recovery-verification-20261102.md)。head0010，无迁移；上一轮精确去重实现完整保留。

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
- 新15项wire场景，调整模型上限、普通续接、旧响应回归；同步AGENTS/README、Schema/Prompt/计划/API/模型说明/导航，新增[ADR0012](docs/adr/0012-compact-extraction-and-model-output-ceiling.md)和[验收](docs/archive/reports/compact-output-verification-20261102.md)。ADR0011的旧32K/64K预算和专属按钮标为后续替代，历史实测不改写。

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

## 2026-11-03 00:08 · DEV-0037 · GitHub交付与安装CI收尾

**目标与改动**：继续本轮明确授权，修复首次CI验收配对问题并完成main交付。功能`1c28137`和验收修复`a4cd365`已普通推送；最终更新progress及本轮实际报告，不进入新Phase。

**验证**：[CI 41474458777](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41474458777)的windows/installed-app均成功。远端回归、契约、冻结引擎smoke、Rust及安装构建通过；Windows PowerShell5.1独立安装报告20项通过，包含宿主握手、单实例、正常退出/崩溃清理、来源和知识重启保持、卸载。该报告明确不认证G0干净机。全内容489文件、修复暂存4文件扫描通过；Git历史21提交Gitleaks无泄露；143 Markdown/500本地链接/88资产清单通过。最终文档另行内容/暂存扫描后提交，不上传私人数据或安装产物到源码。

**限制与下一步**：真实论文恢复结果仍为partial，全文支撑/表格质量和用户安装反馈待完成；CI离线验收不能替代这些项目。四份外部原文登记路径不可用。继续R5，不进入P4/P5。

**00:12补记**：CI两个artifact及delivery.json已保存`.local/releases/schema-recovery-ci-41474458777/`。安装器38462458字节，SHA256 `6e07f886c438e5103a1677dcc9672f13d84a636e38d19c389a58affbd06e5c53`，与远端20项安装报告一致。官方直连下载过慢，现有本机代理小范围测试成功后用于该次下载，未修改全局网络/Git配置；API凭据不随跨域重定向发送。最终文档143 Markdown/501本地链接/88资产通过，四份外部原文不可用。未操作用户安装或正式库。

## 2026-11-03 11:10 · DEV-0038 · 结构 PDF、章节窗口与结论支撑

**目标**：按用户顺序先改解析，不使用 MarkItDown；再默认展示核心结论的方法/实验/条件；最后修复第二篇的 kind_note_unused 校验失败。仍在 R5，不进入 P4/P5。

**改动**：新增 pdf_structure/document_structure/structure_models、Alembic0011、section_planner；ingest 使用独立可取消进程解析，KnowledgeStore 精确核对 hash/原块文本/bbox 后发布结构旁表。跨页章节树及可识别表格行列/表头/单元格保留；References、重复页眉页脚不送抽取。纠正合块标题遗漏、内联大字/普通编号误判与小字号参考文献污染正文基准。新 P02_reading_extract_compact_v3 对所有章节同规则，章节连同子节组织，取消6000字符/48证据目标，仅按实际模型容量拆分；表格跨节不拆、排除材料不通过表格元数据旁路进入输入。冻结旧计划、成功操作及原证据不改。

reading_support/selection/projection 与 GraphWorkspace 默认显示有合法来源路径的非 Claim 支撑，增加 collapsed_unit_ids，保留共享节点、分页闭合与布局；不以共享证据猜边。reading_validation 只适配 Claim.kind_note_unused=null 并审计，其他未知字段/非null仍拒绝，原始 JSON 保留。同步宿主/脚本0011握手、运行契约、ADR0014、docs00–09、README/AGENTS和进度。详见 [本轮报告](docs/archive/reports/structured-reading-verification-20261103.md)。

**实际验证**：正式库只读备份后在隔离副本迁移、解析及回放。44旧表迁移/重解析原行保持；27页/766块→35章节/29检测表格，9页/159块→14章节/2表格，References分别排除30/6块。1M/384K离线规划11/6窗口，最大18270/18895字符，不记为模型成绩。真实失败响应的额外值确为null；零新调用重验并保存4候选/0关联，重复apply幂等，262旧知识/47旧ModelRun及原响应全部原列不变。现有真实投影38节点54边（含4方法/1实验/2条件），全部收起10节点；正式库、原PDF和Zotero未改。

scripts/check-phase0.ps1首轮274pass/3fail/2skip，发现旧P01空根上下文及旧48/7测试误用新索引；修复后全检查277pass，最终解析/表格边界补强后 python -m pytest -q **283 passed/2 skipped**。2项符号链接测试受OS权限限制。47 React、3真实React Flow、9 Rust单测及1打包宿主集成通过；Ruff/格式/mypy72文件/pip/契约/前端构建通过。参考契约78/12/5通过。Windows构建、冻结引擎smoke和PowerShell5.1 EnginePath五项通过；首次PS脚本被执行策略拒绝，仅给该次进程使用Bypass后通过，未更改全局策略。

**交付与限制**：新安装器`.local/releases/structured-reading-20261103/ResearchGraph Studio_0.0.1_x64-setup.exe`，38613199字节，SHA256 `d7419a151355bdbf409b7e3b4c1e01cf1a5a875e33ef52b04d68959aeb914cf2`。已保存本地delivery/冻结/PS/宿主报告；未替用户安装，未执行新版完整安装卸载或干净机测试。章节/表格仍为启发式，无OCR/通用复杂公式表格保证。新Prompt两篇全文真实API生成、全文长章节响应与用户原生反馈待验收，本轮新API调用0。四份外部原文路径不可用。本轮未Commit/Push；最终内容扫描和文档一致性收尾另补记。

**11:10 收尾补记（Asia/Shanghai）**：502 个源码候选文件经路径核对与 Gitleaks 内容扫描通过；146 Markdown/493 本地链接/88清单资产及 LF 哈希通过，只有四份已登记外部原文不可用。git diff --check通过，安装器复制后哈希与delivery一致。私人资料、运行库、响应和安装产物均留在忽略的.local，不进入源码。本轮未暂存、提交或推送；下一步等待用户安装后反馈并在R5验证新Prompt全文真实生成，不进入下一Phase。

## DEV-0039 — 2026-11-03 12:56（Asia/Shanghai）：移除整合/选择上下文预算并续用检查点

**目标与根因**：用户报告“选择上下文超过预算，保留整合检查点；未截断必要支撑”，要求不要设置上下文预算。实际是 reading_pipeline.py 在 P13 模型调用前硬拒超过48000字符；P12另有26000/24000字符、60候选及20窗口限制。完整支撑会放大单元输入，增加模型输出额度不能解除本地门槛。

**改动**：reading_pipeline.py移除上述预算，新finish plan记录complete-context-v1，P12全候选/完整引用证据一窗，P13全部单元一次；旧reading_windows优先读，旧签名与P13八单元分组保持，成功检查点不重调。来源/Schema/路径/版本/取消与真实端点能力、有界超时仍生效。新增test_reading_complete_context.py并更新旧大支撑测试，覆盖69候选、68有效支撑、超24K证据/48K选择、161根、旧P13第二组失败续接和真实错误类别模拟。同步README、AGENTS、docs02/05/06/导航/清单及ADR0015；实际报告见[完整上下文验收](docs/archive/reports/complete-context-verification-20261103.md)。

**实际验证**：只读备份正式库，副本找到2预算失败任务，P02为15/15和34/34；P12的4/4与10/10检查点全可复用，P13最大116934字符。无网络Probe保留历史签名，零P02/P12调用直接到87342/52592字符的P13调用边界后主动停止；旧知识/来源表/原ModelRun及冻结计划保持，正式库/PDF/Zotero/凭据未改。真实模型调用0，不记为真实P13选择通过。

最终完整Python **287 passed/2 skipped**（OS符号链接权限限制）；首轮286/1fail/2skip为新增测试回调访问离开Session的ORM对象，保存原始ID后9项定向及最终全量通过。47 React、9 Rust单测+1真实打包宿主集成通过；Ruff/格式/mypy72源文件/pip、前端types/lint/Prettier、PyInstaller/Tauri/NSIS、冻结引擎smoke、PowerShell5.1 EnginePath五项通过。实际命令与警告见报告，前端单chunk>500KiB提示仍保留。

**交付与下一步**：`.local/releases/complete-context-20261103/ResearchGraph Studio_0.0.1_x64-setup.exe`，38609403字节，SHA256 `d579365a3129fcea4456a15f78071c5454076a5ca74e1640d8a85c7d9761667d`。用户安装后直接继续原失败任务，复用抽取/整合并调用真实P13；未替用户安装或完成干净机/真实选择验收。四份外部原文路径不可用；仍在R5，不进入P4/P5。未暂存/提交/推送，末次安全与文档检查另补记。

**12:57 收尾补记（Asia/Shanghai）**：505个源码候选文件经路径检查及Gitleaks扫描通过；148 Markdown/508本地链接/88清单资产核验通过（四份已登记外部原文不可用），git diff --check通过。安装器复制后长度/哈希与delivery.json一致，冻结smoke、PowerShell、宿主、最终Python和匿名检查点报告已配对保存在本机release目录。暂存区为空，无Commit/Push；最终真实P13和安装体验待用户反馈。

## DEV-0040 — 2026-11-03 13:55（Asia/Shanghai）：P13 JSON 严格解析与原响应恢复

**目标与根因**：用户报告 Expecting ',' delimiter: line 1 column 4359 (char 4358)。正式库只读备份定位到P13第5组：P02已34/34、P12已10/10、前4组P13成功；原4359字符响应的末字段coverage_gaps字符串数组漏一个 `]`，最终根 `}` 已存在。历史无timeout/output_limit错误，但未持久化finish_reason，不反推为stop或输出上限不足。

**改动文件与决定**：新增reading_json.py，只有该唯一语法形态可插一个 `]`；P13正常及恢复后解析均拒绝重复键/NaN/Infinity。reading_validation.py使用严格加载器，完整Schema/版本/来源校验不省略；reading_pipeline.py成功保存检查点时清空旧error、设置finished_at。extraction_repair.py提供不回显正文的中文诊断，providers.py为新调用保存真实结束原因。新增test_reading_selection_json.py的30项边界/恢复回归。新增ADR0016、实际报告；同步README/AGENTS、Schema/Prompt/安全/计划/导航与续接模板。原Prompt/领域/head0011及完整上下文策略不变。

**实际验证**：隔离副本精确复用P12的10/10及前4个P13检查点，第5组原响应零调用重验，8建议/10缺口保持；原ModelRun变succeeded且error清空、raw/usage/transport不改，仅新增该组selecting检查点。在第6组无网络Probe边界停止，真实API调用0，不代表后续真实选择通过。其他数据表、旧检查点、其他任务/运行、目标冻结计划/windows/result保持；正式库/PDF/Zotero/凭据未改。

scripts/check-phase0.ps1首轮311 Python/2跳过、47 React及静态/依赖/契约/前端构建通过；独立审计发现普通P13解析重复键可覆盖后收紧并加6项，最终pytest全量**317 passed/2 skipped**，Ruff/格式/mypy73源文件再次通过。9 Rust单测、另行1项打包宿主连接/退出/重启、冻结引擎smoke及PowerShell5.1 EnginePath五项通过。首次用PS5.1调用无BOM UTF-8构建脚本在解析阶段失败，使用项目pwsh构建成功；未更改系统策略。Starlette/httpx弃用与前端大chunk提示保留。

**交付与限制**：`.local/releases/selection-json-20261103/ResearchGraph Studio_0.0.1_x64-setup.exe`，38613488字节，SHA256 `be5a49d39aa8707781e1f0346c7cb92970f4f660209ce949ea1abcf8fe675420`。未替用户安装/卸载、未执行干净机或新包完整安装验收，未使用Computer Use。用户安装后在原任务继续未完成批次，后续真实请求费用按供应商计量；无需重抽。四份补充原文路径不可用限制保留，仍在R5、不进入P4/P5。未暂存、Commit或Push；安全/文档最终检查另补记。

**13:59收尾补记（Asia/Shanghai）**：最终严格解析代码在13:57取得的新鲜正式库只读备份隔离重放再次通过，真实API调用0；报告包含strict_json_parser_recheck。509个源码候选文件经路径规则与Gitleaks内容扫描通过，150 Markdown/522本地链接/88既有清单资产核验通过，四份登记外部原文不可用如实保留。git diff --check通过、暂存区为空，安装器复制后长度/哈希与delivery一致。最终回归/构建/冻结/PS5.1/宿主/匿名恢复报告已配对保存至本机release目录；私人库、响应和安装产物不进入源码。未Commit/Push。

## DEV-0041 — 2026-11-03 16:10（Asia/Shanghai）：语义协议、严格输出路径与统一阶段恢复

**目标**：实施用户提出的四项改造，减少模型重复生成程序已知信息，明确严格/兼容输出能力，将确定性支撑组图交回程序，统一新响应及历史缓存的成功资格。继承已有结构解析、完整上下文和P13限定恢复改动，不重建工程、不进入P4/P5。

**修改文件与架构**：新增 reading_transport.py、reading_prompt_contract.py、reading_finish_wire.py、reading_finish_semantic.py、reading_stage_validation.py、structured_output.py，以及独立的P02_compact_v4/P12_associations_v1/P13_ranking_v1模板。新任务冻结reading-semantic-1/semantic-reading-1，程序绑定文献版本、批次和短编号，Prompt生成块自动核对真实Schema。providers/chat_stream/model_settings冻结输出策略、转换审计及拒绝分类；只对已登记官方精确端点/模型启用native strict，兼容json_object不伪称严格，不付费探测或自动降级。

reading_store/selection由程序沿所有合法支撑路径形成单元，P12只补关联/重复，P13只给贡献建议；新contribution_order/一基名次经密度/显示偏好重发保持，旧默认指纹不改。首次失败可发布通过来源门槛的provisional/pending/partial候选预览，已有图保留，可信来源冲突禁止预览。extraction/unified_extraction/reading_pipeline共用终验；坏响应分类排除，可信context变化保留历史status/error/finished_at，仅记录复用诊断并停止，不因继续再次付费。KnowledgeStore仍为唯一知识写入口，head0011/领域1.0不变，旧计划/Prompt/签名/检查点不切换。

前端GraphWorkspace/JobHistory/ModelSettings和运行契约增加临时图谱标识、整合/排序进度、失败原因/下一动作及真实调用统计，历史无attempts次数单列未知；整合/失败阶段Token纳入统计。新协议/Provider/Prompt漂移/阶段终验/语义端到端/真实投影和React回归已补充。ADR0017、README、AGENTS、docs00–09/API/模板与本轮验收报告同步；参考契约与运行协议保持区分。

**实际命令与结果**：Conda researchgraph-studio绝对解释器运行，pwsh scripts/check-phase0.ps1最终全量457 Python passed/2 skipped、59 React通过；Ruff、143文件格式、mypy79源文件、pip、契约、TS/ESLint/Prettier和前端生产构建通过。pnpm --dir apps/desktop test:browser为3项真实React Flow通过；cargo test为9单测通过，打包宿主另用RGS_TEST_ENGINE_PATH执行1项连接/退出/重启通过。pwsh scripts/build-windows.ps1构建PyInstaller/Tauri/NSIS成功；scripts/smoke-engine.py冻结引擎通过；PowerShell5.1 verify-windows-install.ps1 -EnginePath五项通过，子进程PATH仅System32。全量前新增测试import排序已修，既有httpx弃用和前端大chunk提示保留。完整命令及边界见docs/semantic-reliability-verification-20261103.md。

**隔离核验与数据保持**：只读备份三个新副本：旧任务P12的10/10及前4P13检查点保持，第5原响应按ADR0016完整重验后保存检查点/清错，第6组64195字符请求边界主动停止，P02/P12不重跑；原raw/usage/传输/来源/知识/其他运行及冻结计划保持。新语义副本分别在186候选/651证据首次失败保守展示51根、140候选/69证据已有图保留原21根，均明确pending/partial。真实调用0，正式库写入0，PDF/Zotero/凭据不改；合成provider另证实响应后锚点变化拒绝入库、保留received/raw/attempts，继续不新增调用。不能把注入超时或NoNetwork边界当模型抽取成功。

**安装与未验收项**：.local/releases/semantic-reliability-20261103/ResearchGraph Studio_0.0.1_x64-setup.exe，38652410字节，SHA256 f949240aa7394753e2680d5f4f81ef7aedf15267182467e9412a0cbb07da6393。安装器与delivery/最终日志/匿名报告配对，仅本机保存。未替用户安装/卸载、未用Computer Use、未做干净机认证；真实strict API、新模板两篇全文及科学质量/原生体验待用户验收。四份外部原文路径不可用，不能重新核验。本轮未暂存、Commit或Push，末次安全/文档检查另补记。下一步仅R5真实全文、失败继续与安装反馈，不进入P4/P5。

**16:14 收尾补记（Asia/Shanghai）**：525个源码候选文件通过路径规则与Gitleaks内容扫描；155 Markdown/549本地链接/88既有资产LF哈希核验通过，四份登记外部原文不可用单列。git diff --check通过、暂存区为空；安装器长度/哈希与构建源及delivery一致，最终安全和文档检查与回归/构建/匿名报告配对保存到本机release目录。无真实请求、正式库写入或Git上传。仅剩新模板真实全文、严格输出和原生安装反馈，未进入下一Phase。

## DEV-0042 — 2026-11-03 16:53（Asia/Shanghai）：图谱颜色、多论文、全屏与工作区整理

**目标与反馈**：用户已真实安装跑通3篇，记为用户反馈，不冒充独立全文科学质量/strict测试。本轮仅继续R5：修复白节点、全项目仍只见一篇、增加图例/全屏，移除重复任务区并按搜索→图谱→候选选项整理界面。

**改动文件与原因**：ForceGraph原只配置5类背景，其余6类露出默认白底；新增graphAppearance.tsx/.css统一11类/未知回退与中文标签、横向GraphLegend。GraphPanel.tsx/.css提供全屏/Esc/焦点约束/滚动恢复且保留画布DOM。GraphWorkspace.tsx/style.css整理搜索筛选及末尾全部论文选项，读取论文全部分页，optionsPaper独立filter；GraphExplorer.tsx移除JobHistory，Papers的任务记录和推理历史保持。ForceGraph范围变更/显式fit在新结果后更新相机，轮询/resize不打断，固定位置不改。reading_projection.py改paper-round-robin-1，单篇交替结论/支撑并轮换论文，避免首篇占满60主节点；cursor绑定图版本，失效可回第一页，has_more不冒充partial。没有数据库迁移或知识写入。相应React/后端210节点/真实浏览器测试、README/AGENTS、docs04/06/07/API/导航/进度与实际验收报告同步。

**实际验证**：Conda绝对解释器运行check-phase0，460 Python passed/2 skipped（OS符号链接权限），Ruff/144文件格式/mypy79源文件/pip/契约通过；首轮前端lint检出新增memo依赖不匹配，修复后pnpm format:check/check/test/build:web全部通过，76 React。真实Edge/React Flow最终8passed，含11色/未知、悬停拖动、固定、共享支撑、范围fit、3篇两页文献/筛选恢复、页末独立、全屏DOM/坐标/尺寸与Esc。首次竖排图例使全屏高度变小，已改横排并重验。9 Rust单测+1打包宿主、冻结smoke及PowerShell5.1隔离EnginePath五项通过。build-windows成功后为包含最终memo修正再打NSIS；直接tauri一次因当前shell无cargo在编译前退出，按既有脚本补进程PATH后成功，不改系统。保留既有httpx弃用/大chunk提示。

**交付与限制**：最终安装器`.local/releases/graph-workspace-20261103/ResearchGraph Studio_0.0.1_x64-setup.exe`，38659968字节，SHA256 `d75462a2df3d19ff76ca1a2d2212fd34808a7e1243d42533b3cbfc3ed08f534f`；最终NSIS退出0后复制/核对，delivery/全部日志/合成截图配对。没有真实API调用、正式库或私人原文访问，不替用户安装/卸载，不用Computer Use；用户新包原生反馈、科学质量/strict及干净机仍有待验收项。四份登记外部原文仍不可用。保留全部原未提交成果，暂存区为空，未Commit/Push；下一步仅用户原项目三篇/颜色/全屏反馈，不进入P4/P5。最终敏感与文档收尾另补记。

**16:54 收尾补记（Asia/Shanghai）**：537个源码候选文件经路径规则与Gitleaks内容扫描通过；156 Markdown/554本地链接/88资产LF哈希核验通过，只有四份既已登记外部原文不可用。git diff --check通过，暂存区为空；最终安装器长度/哈希与构建源和delivery一致。安全、文档报告与最终回归/浏览器/包/宿主/冻结/PS日志及合成截图配对保存，私人资料/运行库/安装产物均在忽略的.local。未Commit/Push，不要求用户重抽三篇论文。

## DEV-0043 — 2026-11-03 17:16（Asia/Shanghai）：P4 Query / P5 Lint-Wiki实施与验收规划

**目标与范围**：按用户“先制定”要求，仅规划P4/P5具体任务、实现方法、顺序及验收，实际工程保持P3/R5，不自动启动后续开发。

**修改文件与内容**：docs/06_development_migration_plan.md新增Q01–Q08与L01–L04/W01–W05，共17项；逐项列实现/交付/验收，补齐运行契约缺口、拟定API、真实/离线/原生分层验收和阶段退出条件。Query覆盖完整候选/原文，默认只读、保存显式经Store；Lint先确定性规则/依赖，再P09语义建议；Wiki按P10有据段落、受管渲染/授权导出、持久发布账本、P11局部差异推进。授权撤销穿透综合/缓存/草稿，零字节及其他私人文件同样受冲突保护，无人工审核。README、docs/README、docs/07_api_and_events及progress同步入口和“仅计划未实现”状态，不改运行契约。

**只读审计发现**：现有FTS仅knowledge_nodes.text，原文/表格/中文/笔记无完整索引；现有候选召回仅Comparator。ModelRun强制单文献，跨篇问答/整理须加项目级scope与来源manifest；KnowledgeStore.event会推进GraphRevision，执行审计不能直接沿用。依赖表尚非逐段反向追踪，参考RetrievalHit不含note/wiki、ReadingSynthesisDraft单selection_revision不足多篇、LintIssue缺规则/诊断生命周期、批注comment无法直接套note依赖，均列入前置契约任务。

**验证与限制**：本轮规划以只读代码/Schema/Prompt审阅及文档一致性核验为依据；未执行P4/P5实现、真实模型、正式库迁移/写入或安装构建。并行辅助复核另重跑既有160项Python、76React、8浏览器回归，无代码改动；这些不是P4/P5新功能验收，不据此标后续Phase已通过。所有旧工作区成果保留，无暂存、Commit或Push。四份外部原文路径不可用，未虚报复核。最终文档编号/链接/资产哈希与敏感内容结果收尾补记。下一步须按后续明确开发任务推进Q01，不在本轮实施。

**17:17 收尾（Asia/Shanghai）**：Conda解释器执行`.local/p4-p5-plan-20261103/check_docs.py --refresh`、17项任务编号/顺序/状态一致性检查及`scripts/check-sensitive.py --gitleaks .local/tools/gitleaks-8.30.1/gitleaks.exe`通过。156 Markdown/561本地链接/88资产LF哈希一致，四份登记外部原文不可用；537源码候选路径/内容扫描通过。独立审阅收紧合法跨篇引用、零字节文件保护和授权撤销穿透衍生对象的验收措辞。未改运行实现、未新调用模型或构建安装器，暂存区为空；规划不是后续Phase实测完成。

## DEV-0044 — 2026-11-03 17:38（Asia/Shanghai）：Query读取Wiki状态与问答沉淀/Obsidian职责

**目标与设计修正**：回应用户关于Wiki是否为图谱、Query该读什么/保存到哪里以及Obsidian内容如何Lint的疑问。上一版Q03把Wiki消费推迟到P5以后，现改P4先有最小文档registry/只读快照/段落manifest/状态，P5复用并完成生成/渲染/安全发布；没有Wiki不阻塞原文问答。

**修改文件**：新增docs/adr/0018-query-wiki-and-obsidian-lifecycle.md，更新AGENTS、docs00/01/02/03/05/06/07/08、docs/README、progress及本日志。Wiki是有据阅读文档，图谱是结构化论文知识视图，Obsidian是可选受管文件与独立私人资料；同一Store无平行科学库。保存Query新增有归属/根依赖的阅读综合，不改原论文Claim，文档更新/导出另行明确。内容有效性与磁盘同步/草稿状态分开；文件缺失不否定内部有效内容，外部编辑不继承旧证据，Query需明确所读版本。Lint分知识/依赖/受管文件/私人只读材料，文件hash与语义过期分开，不能把私人笔记缺元数据判为科学错误。补循环自证/重复支持/撤权穿透及外部手改验收。

**验证与范围**：只读复核既有规范与独立审阅；17项任务编号保留，各阶段任务和退出条件同步。本轮不改运行代码、参考/运行Schema或Prompt、不迁移用户库、不调用模型、不构建安装器或操作Obsidian；保留全部原工作区成果，无Commit/Push。文档脚本及最终实际结果收尾另记，四份原文路径不可用。当前软件仍为P3/R5，新增边界不宣称P4/P5已有功能。

**17:39收尾（Asia/Shanghai）**：Conda解释器执行文档refresh、17项任务及P4 Wiki消费一致性、源码路径/内容Gitleaks核验通过；157 Markdown/573本地链接/88资产LF哈希、538源码候选文件通过，四份外部原文不可用如实保留。独立审阅补明Q07内部登记已验段落与P5主题生成/增量重写/渲染/发布分工。git diff --check、暂存区检查完成后收尾；没有应用功能变更，因此不重跑应用测试，不将本轮文档检查算作Query/Wiki实测。


## DEV-0045 — 2026-11-03 21:32（Asia/Shanghai）：图谱驱动的阅读生命周期与开发计划重写

**目标与范围**：按用户确认的论文→知识图谱→Query→显式保存综合→Wiki→授权MD/Obsidian、Lint横向诊断流程，重写计划并同步项目介绍。只调整文档，不开始P4/P5实现，保留全部原未提交工程成果。

**修改文件与内容**：README.md新增全流程Mermaid及职责/沉淀位置；docs/README.md与01_product_design同步；06_development_migration_plan按当前资产、R5收尾、完整生命周期和17项P4/P5任务重排，增加图谱路径扩展/条件补全对照、衍生图层回溯、按结论单元组织Wiki及Lint结构/依赖验收。docs00/02/03/04/05/07/08、ADR0018、AGENTS及协作/续接模板统一组织层与画布、科学边/导航/衍生引用、默认只读和保存/文档/文件的独立边界。P4最小文档状态/只读adapter前置，P5复用registry。

**只读核对与风险**：现有ReadingUnit/Member、SourceAssertion、support_paths/form_units、证据与条件校验可复用；旧Comparator的3跳/100节点/48K限制不直接继承，新Query不从画布60/120节点分页取全集。knowledge_fts仅索引knowledge_nodes.text；ModelRun强制单文献，Store.event及Obsidian新增快照会推进GraphRevision，计划要求先解决项目多源scope和执行/科学修订耦合。来源身份可验证不代表科学结论真实，无人工审核队列，私人材料默认只读且授权用途分离。

**验证与下一步**：本轮仅做文档/一致性、资产哈希、源码保持及敏感检查，实际命令/结果收尾补记；不运行应用测试、读用户库/私人论文、调用模型或构建安装器，不把历史成绩当本轮验收。四份外部原文路径不可用，不能复核。实际阶段仍P3/R5；先完成新包原生反馈、全文质量/失败继续等剩余验收，后续明确开发P4时从Q01开始。无暂存、Commit或Push。


**21:44收尾（Asia/Shanghai）**：Conda环境绝对解释器执行`.local/lifecycle-plan-20261103/check_docs.py --refresh`与`check_plan.py`，17项唯一有序任务/非空实现验收列、流程图围栏与介绍锚点、284个非文档文件逐字节保持、暂存区及git diff --check通过；157 Markdown/591本地链接/88资产LF哈希通过。首次源文件保持检查因Windows反斜杠误把docs计入源码范围而报变化，规范化路径后通过，没有实际源码变化。`scripts/check-sensitive.py --gitleaks .local/tools/gitleaks-8.30.1/gitleaks.exe`对538源码候选内容/路径扫描通过。独立复核后补明无结论单元的合法原文/候选仍可Query/Wiki，Zotero评论使用独立note/annotation快照来源，外部MD明确登记不继承系统证据或写权。图形仅作Mermaid源文本/基本结构检查，未执行渲染器或应用回归；四份外部原文不可用。无API调用、迁移、打包、暂存、Commit或Push。


## DEV-0046 — 2026-11-03 23:42（Asia/Shanghai）：R5路径与证据感知选择、真实质量失败及本轮交付

**目标/范围**：完成R5剩余验收，不进入P4/P5；保留全部原未提交工程成果。用户本轮确认上一安装包五项原生全部通过，之后明确选择“先交付本轮结果，稍后更换模型验收”。因此停止进一步付费调用，不将未通过的科学质量写成R5完成。

**修改文件**：reading_support/reading_store.form_units/reading_selection/reading_finish_semantic/reading_finish_wire/reading_stage_validation，新增reading_evidence_quality和P13_reading_ranking_v2，及相应engine测试；e2e graph/workspace/合成布局服务；verify-windows-install、smoke-engine、CI真实Edge步骤；AGENTS/README/docs导航、03/05/06/08/协作续接模板、ADR0019/0020、progress及实际R5报告。程序冻结关系manifest，完整路径复验并保留response_invalid=false历史状态；新P13核对全部引用原文/疑点/排版风险，旧无ranking_prompt计划继续v1。核心拒绝全碎片依据，支撑疑点汇总limited，needs_context/insufficient_support标insufficient；安全Schema诊断有界且不回显私密输入。无DB迁移/head变化或人工审核。

**实际命令与结果**：最终pwsh scripts/check-phase0.ps1退出0，547 Python passed/2 skipped、76 React，Ruff/格式/mypy/依赖/契约/前端静态与生产构建通过；pnpm --dir apps/desktop test:browser --reporter=line本轮10真实Edge/ReactFlow通过（前端此后未改）。build-windows证据最终版退出0；Rust fmt/clippy/9单测与独立packaged host1通过，最终冻结smoke和PowerShell5.1 EnginePath+自造two-pages.pdf 16项通过。保留已有httpx弃用/大chunk提示，符号链接权限两项跳过，不冒充干净机安装。

**真实验收与发现**：只读正式库备份写隔离副本，P02两篇6/6、15/15完成；原6批通过新签名/原提交操作引用保留，none配置只处理9个未完成叶，原max任务/计划/raw不改，不宣称产品已有任意配置切换按钮。87/256本轮候选的186/426证据链接版本/坐标/quote/hash检查0错误；但第二篇32条不受原文语义支持、2条上标展平错数。补P13v2原文与排版上下文后，两篇各2次仍因冲突/重复编号或额外字段失败，未发布新选择、旧图保留；无删字段、合并冲突建议或改数值伪造成功。第一篇旧v1 15核心/50支撑、80合法成员链仅有限正例，另有同义重复和疑点支撑。新layouthelper命中真实上标块，风险识别不等于修正科学含义。

**调用与数据**：主验收32次，已返回prompt1063689/completion265842/total1329531（reasoning158591）；并行误调度2次P12精确停止，一次180秒超时、一次等待中止，用量/费用未知。共34已知发出，金额未提供；本轮已停止后续收费。415条原知识/95条原raw逐行保持，4源hash相同，SQLite integrity/foreign_keys通过，正式库写入0。私人标题/原文/原始响应/质量逐条清单仅忽略.local，不进源码。

**交付/未完成**：.local/releases/r5-final-20261103/ResearchGraph Studio_0.0.1_x64-setup.exe，38674011字节，SHA256 dc5a1ab1c8961947dc51a5a4acf31fc812a6f4c22f244a82ce62579b4d84d6bc，与最终源匹配；新包原生待反馈。真实strict/干净机/四份不可用外部原文未验收，R5仍待换模型后P13终验、已知语义错误过滤/同义代表/必要条件与支撑质量复核。未经新授权未Commit/Push、远端CI未执行。最后安全/文档/暂存区核验收尾另记。


**2026-11-03 23:45（Asia/Shanghai）收尾：161 Markdown/613本地链接/88资产LF哈希通过，四份登记外部原文仍不可用；544源码候选内容/路径及Gitleaks通过，git diff --check通过、暂存区为空。最终安装器副本与构建源长度/hash一致，离线日志与匿名结果封存；未Commit/Push，真实P13未过且用户选择稍后换模型，不进入下一Phase。**


## DEV-0047 — 2026-11-04 10:31（Asia/Shanghai）：程序绑定贡献评估槽位与有界恢复

**目标与责任**：按用户“应该修复软件连续返回冲突编号或额外字段，而不是换模型”的纠正，修复P13协议、恢复与兼容续接。仍在P3/R5，不进入P4/P5，保留全部原未提交成果；本轮没有新增真实模型调用或正式库写入。

**根因与修改文件**：只读复盘上轮4份响应，旧数组要求模型重复抄编号，精确覆盖/唯一性仅后置Python检查；有相反建议、遗漏、重复及未知根字段。新增reading_ranking_wire、P13_reading_ranking_v3、reading_ranking、reading_finish_upgrade及对应测试；修改reading_finish_semantic/extraction/providers/reading_mock/models/app与JobHistory。运行Schema固定assessments完整required短编号，建议/理由复用领域约束，priority严格0–100整数，程序稳定排序；Schema与Prompt同源。外壳合法才独立保留合法槽位，均为私有检查点；修复只输出未完成槽位，保留全文/所有单元/疑点/排版及已完成建议。全部完整后终验与Store再验，不删未知字段、不合并冲突或伪造结果。

**费用与历史兼容**：发送前持久账本，每构建最多2请求含超时/投递不明，底层max_attempts=1；继续重解原raw和哈希/配置/manifest/来源，不重发已消耗槽位，耗尽后零追加调用。修改误导“批次将缩小”的总超时提示，前端分别显示抽取和贡献评估进度/修复/停止原因。旧v1/v2计划、签名、raw、历史ModelRun参数保持；原selecting失败可独立v3后继，逐级核验显式P12 adoption链并经Store采用，新增诊断写后继。两篇隔离真实旧任务mode=ro核验均available、integration_input精确一致、session无改动，第一篇祖先真实run、第二篇本任务run，未输出私人原文。无迁移、head0011/领域/入口不变。

**文档与验证**：新增ADR0021及ranking-protocol-verification-20261104，更新README、AGENTS、docs导航/02/03/05/06/08/协作模板/续接/progress和历史报告后续说明。最终pwsh scripts/check-phase0.ps1：623 Python passed/2 skipped、80 React；Ruff/格式/mypy83源文件/依赖/契约/前端静态与生产构建通过。最终恢复/升级47项另复验，wire/恢复/预览48项针对检查通过；10真实Edge/ReactFlow通过。Rust fmt/clippy与9单测、1冻结宿主独立通过，build-windows的PyInstaller/Tauri/NSIS退出0；最终冻结smoke明确键控协议/全槽位及重启，PS5.1 EnginePath+自造two-pages.pdf 17项通过。首轮607过/1失败为旧投影fixture未识别新title，扩展显式自造fixture后修复；首次PS调用漏写pdf子目录，改参数/新隔离目录后通过。保留失败日志及已有httpx弃用/大chunk提示、两项本机符号链接权限跳过，不冒充干净机或真实模型成功。

**交付与未完成**：新包.local/releases/r5-protocol-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe，38,708,292字节，SHA256 a10e7b14dbb9d8f283d3e973ce79fab92980cc974ae89cc6f1e158405f53b37c；冻结引擎1879c766f393f6716ad83e7b9ca4aa594a5a69caa886b45ba13071b3d0c101d5。旧包/来源/知识/历史记录保留；退出软件安装后可保持当前模型，继续原失败任务，不需要删知识/重抽P02。没有替用户安装/卸载或Computer Use；本包原生/真实P13/32条语义无支持与2条上标误读过滤、同义代表/必要条件/支撑质量仍待复验，strict/干净机/四份不可用外部原文分别保留限制。553源码候选Gitleaks/路径检查已通过，文档/最终安全/交付核验另补记；暂存区为空，未Commit/Push/远端CI。下一步仅用当前模型验证新版续接和科学质量，不把换模型当软件修复前提。

**10:33（Asia/Shanghai）收尾**：最终553源码候选内容/路径与Gitleaks、164 Markdown/632本地链接/88资产LF哈希通过，四份外部原文仍不可用；git diff --check通过、暂存区为空。最终安装器副本与构建源、delivery元数据hash一致，核心改动文件时间早于引擎构建，自动化/浏览器/打包/冻结/PS5.1日志与匿名结果配对封存。没有追加真实请求、Commit/Push或远端CI；保留所有原未提交成果及历史安装包。

## DEV-0048 — 2026-11-04 11:11（Asia/Shanghai）：历史抽取错误与续接结果反馈

**目标与实因**：处理用户再次报告的`items.1.Claim.kind_note_unused (extra_forbidden)`及点击继续无响应。仅SQLite mode=ro核验状态/协议/计数及字段类型，不输出私人标题/原文/raw；这是旧P02v2任务第3次失败31/34、字段为Claim上的null，其P02v3独立后继已11月3日成功34/34并发布。后端再次操作正确返回同一成功后继，界面丢弃返回Job只刷新历史，原失败行自然不变，造成无反馈。现有精确null兼容已生效，不放宽Schema、不重抽成功内容。正式库写入0、真实模型调用0。

**修改文件与行为**：JobHistory.tsx/.test.tsx、api.ts显示提交中/实际后继状态/查看续接结果，同步列表与单任务缓存；分页外后继单独可见并每1.5秒GET实际状态，终态停定时，刷新失败保留结果。成功+pending排序不冒充完成；原错误/raw保留。独立复核发现queued→failed文案误称未处理，改中性错误提示；在途GET可能覆盖cancelled，现写操作结果前await取消该精确查询，并回归旧queued缓存覆盖成功。test_reading_upgrade补旧null响应零抽取复用及多新幂等键重试同一成功后继/历史不变。同步API/07、AGENTS、docs导航/续接模板/progress及history-retry-verification-20261104。无后端运行代码或架构/Schema/Prompt变更，无新ADR/迁移，head0011/领域1.0不变。

**实际命令与验证**：Conda researchgraph-studio绝对解释器专项17项通过。pwsh scripts/check-phase0.ps1退出0，625 Python passed/2 skipped、初轮88 React；Ruff/154文件格式/mypy83源文件/依赖/契约/前端静态与构建通过。最终两项前端修正后pnpm format:check/check/test/build:web全部重跑通过，90 React（任务历史32项、新增10项）。pwsh scripts/build-windows.ps1的PyInstaller/Tauri/NSIS退出0；最终冻结smoke及PowerShell5.1 EnginePath+tests/fixtures/pdf/two-pages.pdf独立数据17项通过，子进程PATH仅System32。无图谱/宿主改动，本轮不重复浏览器/Rust回归，上一轮结果不冒充本轮。保留既有httpx弃用/大chunk提示和本机文件链接权限两项跳过。

**交付与限制**：.local/releases/history-retry-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe，38,710,564字节，SHA256 d5320ac80159fca0ead50da3298c5f7e52352f226cc733126a62aba2bbbad34c；引擎1879c766f393f6716ad83e7b9ca4aa594a5a69caa886b45ba13071b3d0c101d5与上轮相同。退出软件安装后从原任务查看成功续接，不需删知识/重新抽取；不替用户安装/卸载，不使用Computer Use。保留全部原未提交成果、私人PDF/Zotero/Obsidian/用户知识与历史安装包。实际仍P3/R5，本包原生反馈、真实P13/科学质量/strict/干净机待验收，四份外部原文路径不可用如实保留。无Commit/Push/远端CI；最后敏感/文档/交付校验另补记。

**11:13（Asia/Shanghai）收尾**：554源码候选路径/内容与Gitleaks、165 Markdown/637本地链接/88清单资产LF哈希通过，四份登记外部原文仍不可用；git diff --check通过，暂存区为空。最终安装器副本与构建源长度/hash一致，前端运行文件冻结早于构建；交付清单及本轮专项/全量/最终前端/构建/冻结/PS5.1/安全/文档日志配对保存。本轮未新增真实请求或正式库写入、未Commit/Push，不因旧历史错误要求用户重抽。

## DEV-0049 — 2026-11-04 12:49（Asia/Shanghai）：R5三项实际补验收

**目标与授权**：按用户“进行R5实际剩下三项的检验”，验证当前模型P13v3、安全续接、已知科学缺陷和最新安装包。本轮明确任务授权有界真实调用，不沿用此前“暂停付费”的历史轮次状态；完成即停止。保留全部既有未提交成果，不进入P4/P5，无Commit/Push。

**数据/执行**：正式库SQLite mode=ro备份，基线head0011/4论文/429节点/97模型记录完整性和FK通过，实验写入0。另复制前轮real-fulltext，复用6/6、15/15抽取以及经过终验的真实P12谱系；reading_finish_upgrade创建新v3后继，新后继尚未冻结/请求前显式绑定当前全局max配置并记录旧/新快照hash，原任务/计划/签名/raw不改。根代理独占发送，guarded runner禁P02/P12/探测，发送前fsync journal/两槽账本，每篇最多2、总4。实际上两篇各1次P13v3，38/105槽位一次通过、7/20单元发布，143.735/124.891秒；真实finish_reason=stop、SSE、180秒总时限内完成，无格式修复/超时/隐藏重试/自动降级。P02/P12新请求0，成功后再--resume新请求0。总2请求、prompt230245/completion46454/total276699，其中reasoning36867，金额未提供；不追加调用。

**科学/数据复验**：32语义无支持+2上标误读均retrieval_only，不进核心/支撑；5同义组各1核心代表。7/20核心、30/98唯一支撑，36/232成员路径（5/138多跳）及候选/可见锚点错误0；343新P02候选全部保留并在选择快照，6主要贡献有代表、15参照组全可检索。条件2/17个，第二篇known15/unknown2，unknown数值/单位为空；可见Limitation2/7，全部成员issues进caveats，有限证据核心2/1均有提示。没有真实conflicting/not_applicable样本；22/45条coverage_gaps继续使图partial，排序complete不等于全文100%。独立只读代理再验P12祖先/输入及新旧快照、实际run/attempt/账本/raw哈希，旧16任务/127模型整行raw+parameters/758节点/来源/块/证据/解析全列逐行保持，原数据库文件hash和完整性/FK通过。4附件PDF哈希匹配；不同于S1–S4外部补充原文，后者仍不可用。

**安装/回归**：最新history-retry包只解包，不执行安装器；SHA256 d5320ac80159fca0ead50da3298c5f7e52352f226cc733126a62aba2bbbad34c与delivery一致，7源码/289资源/引擎一致。桌面target与payload只有Tauri NSS/UNK标记3字节差异，双原始hash保留，不改二进制。实际PowerShell5.1 EnginePath17项、生产Host打包测试1项（两次握手启动停止）、合成0008/0009/0010→0011及两次启动通过，34/37/44旧表逐行不变且每库仅1份准确升级前备份。用户明确反馈新包原项目与证据可读、原失败继续显示成功后继、退出重开知识/任务三项全部通过，记用户反馈而非CUA实测。Conda解释器pytest五个ranking/recovery/upgrade/evidence/unused-note文件101通过；pnpm vitest JobHistory32通过，保留Starlette/httpx提示。无运行代码改动，不重复全量回归/打包，不冒充前轮625项等本轮重跑；未Computer Use/替用户安装卸载/写正式库。

**修改文件与结论**：新增docs/r5-acceptance-verification-20261104.md，更新README、AGENTS、docs/README、06计划、progress、协作与下一轮模板及日志；规范清单/hash收尾刷新。私有脚本/备份/逐条报告只在忽略.local/r5-acceptance-20261104，不进源码。三项在本轮明确范围内通过，无新增阻塞缺陷；兼容提示路径实测不等于strict，干净机/复杂版面/全局准确率及S1–S4限制保留。P4/P5仍未开始，后续明确开发指令从Q01开始，不自动再收费。最后文档/敏感/diff/暂存区检查另补记。

**12:53收尾（Asia/Shanghai）**：文档检查166 Markdown/642本地链接/88项规范资产LF哈希通过，S1–S4四份外部补充原文仍不可用；555源码候选内容/路径及Gitleaks通过，git diff --check通过（已有CRLF规范化提示保留）、暂存区为空。.local实验数据库/模型快照/安装产物忽略边界核验通过。匿名科学报告、安装报告、模型请求账本和真实用量与最终新报告配对留存；本轮实际仅2请求，成功后继续零请求，无正式库实验写入，无Commit/Push/远端CI。本轮到此停止，不进入P4/P5。

## DEV-0050 — 2026-11-04 13:57（Asia/Shanghai）：先交付 R5，再实现 P4-Q01～Q04

**目标与授权**：按用户“先将本轮 Push 到仓库后，进入 P4-Q01 到 P4-Q04”推进。先完整保留并提交 R5 已有成果，经555源码候选、140暂存文件独立敏感/Gitleaks及diff检查，以普通 Push 推送 main 的 `80552d3`（140文件）；未强推，origin保持HTTPS，仅该命令使用已验证官方SSH443。远端[Actions 41778202007](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41778202007)的windows和installed-app全部成功，包括完整回归、真实Edge图谱、冻结引擎、Rust、NSIS和独立安装验收，13:40:30完成。公开状态/artifact元数据留在忽略.local；匿名日志403，没有下载日志或远端安装artifact。该次授权不自动用于再次Push后续Query新增量。

**实现文件与行为**：新增query_contracts/query_models/query_documents、query_retrieval/query_graph/query_context/query_api及0012_query_foundation，注册app API；调整KnowledgeStore/knowledge_api/integrations/storage、Rust宿主、smoke-engine、verify-windows-install和OpenAPI/generated.ts。Q01项目级QueryRun/QueryModelRun/回答预留与多源manifest，不把跨篇挂第一篇；文档不可变版本/逐段根依赖/独立文件绑定与内容状态、NoteUseGrant用途权限。audit_event不推进科学GraphRevision，笔记授权/扫描/撤销改用该入口。0012只增Query、文档、授权和派生FTS表，旧ModelRun/知识/来源/raw/任务签名保持，升级前准确备份与幂等重启在隔离合成库验证，正式库无实验升级。

Q02可重建query_fts索引当前合法候选原语言/中文/别名、题名、原文/表格、有效Wiki/综合与明确授权笔记，FTS/BM25/精确术语及中文双字片段，不用向量服务或付费改写，来源/类型先过滤后排名。Q03从文本/Wiki根种子补完整合法结论路径及种子相邻科学关系，保留共享成员/条件四态与原值单位；导航/NO_DECISION/布局不作科学依据。Q04 query-context-1冻结根来源/版本/hash/解析器、章节/表格、引用、图路径/节点revision和用途授权，原文无span时只读Chunk，不生成知识。缓存GET/幂等prepare/validate均重组终验，撤权穿透Wiki及缓存；默认不读私人笔记/被排除文档绑定文件。文件缺失/外改不否定内部有效版本，外部新文本不继承manifest，in_sync仅登记字节基线。无固定48K/100节点/3跳预算，容量不足保留完整组并标不足，当前PDF未核验标not_checked。

**发现与修复**：独立测试复现持久解析hash/schema/原文/坐标/表头引用等5类篡改及7类cell引用/行列/跨度错误，补全逐块/章节树/表格终验。来源筛选Sequence解决首轮mypy型变失败。最后复核补齐Tauri Query和笔记用途精确方法/UUID/参数白名单，拒绝非单斜杠本地路径，防URL拼接被解释为外部authority/userinfo；合法search/prepare的64KB请求体容纳契约允许的Unicode问题，不是上下文预算。prepare新快照冻结Provider同一精确端点/模型登记容量，未知保持未知、更低端点上限保留，不改profile或旧run、不做付费探测。

**实际命令/结果**：Conda researchgraph-studio绝对解释器，`pwsh -NoProfile -File scripts/check-phase0.ps1`退出0，734 Python passed/2 skipped、90 React；Ruff/168文件格式/mypy91源文件、依赖/OpenAPI-TS/前端静态及生产构建通过。最终容量/宿主补丁后六个test_query_*.py再运行113 passed（含4新增配置用例），专项不与734交叠累加。Rust fmt/clippy all-targets -D warnings、11单测通过；最终build-windows的PyInstaller/Tauri/NSIS退出0，冻结smoke新增Query幂等/终验/重启/零科学写入并回归旧流程，生产packaged host1项（两次启动/停止）通过。PS5.1 EnginePath+自造two-pages.pdf/System32-only PATH全新隔离目录17项通过；首次因本机ExecutionPolicy拒绝未运行，改为仅该进程Bypass后通过，未改系统策略。保留httpx弃用/大chunk提示及两项本机symlink权限跳过。本轮前端运行代码未变，不重复浏览器回归，不把已推R5远端结果记成新Query CI。

**文档/交付**：新增ADR0022及p4-query-foundation-verification-20261104；同步README/AGENTS、docs导航/00–03/05–09/API/续接模板/进度和规范清单。新包`.local/releases/p4-query-foundation-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,717,661字节，SHA256 `55fb899ea2c603cb4488a7b98c0cea4c6fe97bc0826f785df71adeea4ca406c2`；引擎SHA256 `7cbe885e3e11b09131fa7d74a4f363ce1f6c59ca890abe6eeace1074b6bc8c2a`。副本/构建源hash、源码指纹与delivery/最终日志配对保存于忽略.local。未安装/卸载或启动正式桌面库，不将新包原生或干净机标通过。571源码候选内容/路径/Gitleaks通过；最终文档/hash/diff/暂存区收尾另记。

**未完成与下一步**：本轮真实模型请求0、正式库/PDF/Zotero/私人笔记实验写入0，止于Q04。Q05 P07有据回答、Q06页面、Q07显式保存、Q08真实质量/完整24题/1万候选2万正文性能仍待开发，P5未进入。Q01仅预留回答/保存契约和内部文档登记，不宣称已有问答生成/用户保存/受管MD发布。strict/OCR复杂版面/跨平台干净机及S1–S4四份外部补充原文登记路径不可用限制如实保留。Query增量未暂存、Commit或Push，原已推R5历史保持。

**13:58 收尾（Asia/Shanghai）**：571源码候选内容/路径与Gitleaks、168 Markdown/662本地链接/88规范资产LF哈希通过，4份登记外部原文仍不可用；git diff --check通过（已有CRLF规范化提示保留）、暂存区为空。HEAD/origin main均80552d3；本轮Query未再Commit/Push，实验数据库/模型快照/安装器/打包引擎忽略边界已核对。最终安装副本与构建源hash一致，源码指纹和本轮全量/113项专项/最终Rust/构建/冻结/Host/PS5.1/安全/文档报告配对保存。后续从Q05开始，本轮到此停止。

## DEV-0051 — 2026-11-04 15:04（Asia/Shanghai）：P4剩余Q05～Q08开发与验证

**目标与范围**：按用户“完成P4下剩余内容并进行验证回归”续接已有未提交Q01～Q04，不重建工程、不进入P5。前轮R5的80552d3及CI保留；本轮没有新的Commit/Push授权，不上传私人论文、笔记、数据库、raw、密钥或安装产物。Conda researchgraph-studio绝对解释器，测试使用合成独立库/已有授权真实验收副本，正式库实验写入0，未替用户安装。

**源码**：新增query_answer_contracts/query_answer_wire/query_answers与P07_query_grounded_v1，app统一query_answer worker/取消/继续；入队/发送/返回/GET/保存当前来源/用途/raw谱系终验，严格JSON/Schema/归属/短引用，发送前持久槽位最多2且失败不自动重发、收到合格raw可零调用恢复。新增query_save/query_saved_models和0013_query_saved_knowledge，KnowledgeStore.save_query确定性复制用户选段（0新增P08调用），Synthesis/Insight及文档版本/逐段根manifest/事件，独立DERIVED_FROM不冒充科学边。新保存node根可选payload_sha256，防payload不增revision漂移；旧依赖/请求hash兼容。React QueryPanel/queryApi/QueryDerivedGraph接入问答、预览/范围、用途与网络授权、引用/原图定位、错误/继续/历史、显式保存和独立衍生图；SourceIntegrations读/外发授权独立。

**缺陷与修复**：JobView不识别回答阶段、重试幂等缓存queued、Host拒绝URL编码cursor填充、原文根误当知识节点已修；FTS逐条删除改批量、撤权孤儿FTS缺行仍清理、单次同步retrieve局部显式复用验证且下次重验、去掉丢弃的诊断hash，边/根/seed/scope校验不删。真实q09显式两篇却单篇独占召回，新增lexical-graph-scoped-2按篇公平保位与scope_coverage；context从科学根重算，题名不计、缺论文零外发/不可保存，noPDF/版本过滤/范围篡改拒绝，旧无字段manifest/hash保持。真实同题仅本地prepare现覆盖2篇，旧答案不改/新增模型0。

**实际回归**：check-phase0完整流水线838 Python/2 skipped、108 React及静态/依赖/OpenAPI-TS/格式/生产构建通过；最后补丁全Query237项再通过，最终全量另补。Edge全13、最后分流3再通过；Rust14+打包Host1（两次启动停止）、clippy/fmt通过。build-windows PyInstaller/Tauri/NSIS退出0；冻结新P07使用父进程loopback合成HTTP/SSE端点走生产ConfiguredProvider，生成/Store保存/强退重启/幂等回放通过、stub POST仅1次，不能冒充真实模型；PS5.1 EnginePath隔离17项/System32-only PATH通过。首轮7失败为旧head断言、正在开发的安全fixture与孤儿FTS缺陷，修复重跑；脚本曾因日志相对路径出错未执行cargo，改绝对路径后clippy通过。httpx弃用/大chunk提示、2项本机权限跳过保留。

**真实**：沿用前轮授权的两篇不可变验收来源和既有全局Reasoning快照，OS凭据只读；默认正式库无当前role，故未假称其现选配置。9题成功、1无证据insufficient零调用，总10HTTP发送/737701 Token（prompt683387/completion54314；reasoning36998，金额未提供）。q04第1槽JSON未闭合被严格拒绝，原raw保留，唯一第2槽成功；其他成功题不重发/新增抽取0。长运行源码验收期间lazy模块热改致q05首save422，稳定源码重启后零模型调用保存成功，非发布引擎热改；日志保留。2综合保存幂等/重启、原4来源/1921Chunk/1930Span/758节点/129ModelRun整行及18Job等旧行保持/FK完整性通过。62段独立来源审阅58支持/4部分支持、0完全无据/作者归属错；架构/表头/方向/引用覆盖限制保留，q09原问题未完整回答如实记录，未改raw虚报。真实调用到此停止。

**性能与交付**：新增tests/benchmarks/query_retrieval.py，可复现新隔离目录造数/冷建/12warm/OS峰值；1万候选/2万Chunk/30001索引条，cold1.985481s、P50=1.7356675s/P95=1.985979s，本机目标达到。DB45961216B、峰值RSS279097344B含造数，FTS逻辑3687347B；dbstat未编译，物理页大小null/unsupported，不伪造。合成分布/小样本/不含复杂表格限制保留。新包.local/releases/p4-query-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe，38786476字节，SHA256 861ef988c12ef5bfba8f70fa0d0e5b68348903cefa987698cc932273b6bbe97e；Sidecar 4dbf5210ba7482e74a9abb244427262a086af8d5e22f8a3955ccc455068ba741。delivery记录165源指纹与构建资源一致，资源无PDF/DB/.env/日志。用户新包原生已请求、尚未反馈不记通过，干净机/真实strict/无OCR复杂版面及S1～S4四份外部原文不可用仍保留。

**文档与下一步**：新增ADR0023和p4-query-verification-20261104；同步README/AGENTS、docs导航/00–03/05–09/API/协作与下一轮模板/进度，区分历史Q01/head0012与当前0013。最终全量、安全/Gitleaks、链接/88资产LF hash、diff/空暂存区及包源hash收尾另记。止于P4；P5-L01依赖失效/L02规则和Wiki整理/导出须后续明确指令，不自动开发。

**15:07 最终回归（Asia/Shanghai）**：所有源码稳定后完整pytest再次通过862 passed/2 skipped（332.31s），最后全Query237通过。Ruff/182文件格式/mypy97文件/OpenAPI-TS/前端静态/生产构建通过；安装包源/165源指纹复核无变化，冻结smoke、Host1及PS5.1的17项最终通过。用户新包原生问题已发出，尚未反馈不记通过。真实调用账本仍10，q09仅新本地prepare覆盖两篇，旧答案和原raw保持。最终文档与安全计数随后补记；本轮不进入P5、不Commit/Push。

**最终安全/文档收尾（Asia/Shanghai）**：15:08收尾：最终862 Python/2 skipped、237 Query专项、108 React/13 Edge/14 Rust+Host1、PS5.1隔离17及冻结smoke通过；596源码候选实际内容/路径/Gitleaks、171 Markdown/704本地链接/88资产LF哈希、diff与空暂存区通过。四份外部原文不可用保留，用户新包原生反馈待确认；安装副本/165打包源指纹一致，真实请求保持10。未Commit/Push，P5未开始。

## DEV-0052 — 2026-11-04 18:09（Asia/Shanghai）：P4安装反馈修复与保存内容生命周期

**目标与实因**：用户已安装0013包并反馈来源缺中文、回答露内部ID、查看原问答无反应、问题与来源/回答分散、保存后无法批注或移除。来源预览直接显示检索索引拼接串，引用又将内部短编号当标签；保存跳转只设activeId，没有重新读取、滚动或焦点反馈。本轮续接全部未提交P4成果，不进入P5，不新增真实模型请求，不升级/覆盖正式用户库作实验。

**源码与边界**：新增query_presentation及对应测试，调整query_contracts/query_api和QueryPanel/queryApi/CSS/单元及Edge harness；顶层只读presentation在来源终验后提供题名、原文、已有中文及定位，不进入冻结snapshot/manifest/hash或模型请求。缺中文如实提示，已验证答案要点标AI综合；跨页节点不标首条单页、null页码不补第1页。问题/来源/答案/保存集中显示，原问答实际刷新且可见定位/加载/错误，同ID再次点击也有效，不触发生成。

新增query_saved_preferences模型及Alembic0014、query_saved_lifecycle，修改query_save/query_documents/KnowledgeStore、API、Rust白名单/握手、storage、smoke-engine/PS验证及生成契约。个人annotation独立revision，Idempotency-Key与expected_revision防重放/并发，个人观点不改答案/Claim、不入检索/context；移除排除保存库/检索/衍生层及后续同文档复制，不物理删原文/Query/raw/答案/文档。退休按(document_id,local_ref)，避免独立另存互相误伤。复核发现旧0013只有flatten根依赖，补从冻结context/answer/source_refs只读重建并核对身份及已有哈希；无法核验仅隔离相应保存项，保留旧manifest。批注/移除只记Store审计，不推进科学GraphRevision；相同已移除指纹重存明确拒绝。

**实际验证**：Anaconda researchgraph-studio绝对解释器。首轮check-phase0有4失败（3旧head断言、1开发中幂等测试断言），修复后870 Python/2 skipped、114 React通过；一次被用户中断的回归停99%无摘要，不计通过。最后兼容/跨页补丁专项50及3项通过，最终完整pytest879 passed/2 skipped（445.56秒）；Ruff/186文件格式/mypy100源文件、依赖/OpenAPI-TS/前端静态与生产构建通过。React114（QueryPanel19）、实际Edge14（Query4）、Rust15与clippy/fmt通过，Host1（两次握手）单独执行通过。最后源码稳定后重新build-windows，PyInstaller/Tauri/NSIS退出0；最终冻结smoke通过问答/保存/批注/重启/移除/再重启（合成HTTP/SSE仅1 POST，不冒充真实模型）、PS5.1隔离17项/System32-only PATH通过。冻结0013→0014合成旧库62表全部列/行保持、旧保存/答案/raw可读、完整性/FK通过，两次启动仅1份准确旧备份。已有httpx弃用/大chunk及2项符号链接权限跳过保留。

**交付与文档**：最终包`.local/releases/p4-query-feedback-final-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe`，38793801字节，SHA256 `163a6cb9a1f68040d0482a11a0c989c85be781516d348175955b1c14bd575f9f`；Sidecar `2767bd8e4493cbed4e6c810fa5f369d38c6c4358324586fdffb77ee75fc9ad1c`。171源码指纹及281资源（不含运行生成pycache）与构建源一致，资源无私人PDF/DB/.env/日志，旧包/中间构建均保留。新增ADR0024及反馈验收报告，同步README/AGENTS、docs导航/00–03/05–09/API/协作模板/下一轮/开发计划/progress；603源码候选内容/路径/Gitleaks、173Markdown/742本地链接/88资产LF哈希通过，diff/空暂存区及最终包配对收尾补记。

**限制与下一步**：本轮真实调用0、正式库实验写入0；原十次真实Query及原raw不改，不要求用户付费重答/重抽。未Computer Use、未替用户安装/卸载；旧包反馈不能算最终修复包原生通过。下一步仅请用户安装final包核对已有问答/中文引用/原问答跳转、个人批注重启与移除；P5需后续明确指令。真实strict、干净机、无OCR复杂版面及S1–S4四份外部补充原文不可用仍保留。未经新授权未Commit/Push，HEAD和本地origin记录保持80552d3，不把历史R5 CI当本轮Query CI。

**18:11收尾（Asia/Shanghai）**：最终check-phase0整体退出0，879 Python/2 skipped、114 React及静态/契约/依赖/生产构建全部完成；最终打包smoke、Host1、PS5.1的17项与冻结0013迁移通过。603源码候选内容/路径/Gitleaks、173Markdown/742链接/88资产LF hash、git diff --check与空暂存区通过；四份登记外部原文不可用继续保留。最终安装器副本/171源指纹/281资源与构建源一致，日志和匿名结果配对封存，未追加真实调用/Commit/Push/Computer Use或正式库实验写入。仅修复包用户原生确认待反馈。

## DEV-0053 — 2026-11-04 19:17（Asia/Shanghai）：按用户要求删除旧问答供重试

**范围**：用户先要求移除旧答案，随后明确“不要保存内容，直接将旧记录删除”。本轮对实际安装版数据库执行该项维护，删除该1条Query、1个答案版本、1条专属Query模型raw、2份关联保存内容及其2份文档/版本/段落、1条派生索引及FTS、8条幂等结果、1个已完成问答任务和8条专属事件；未删除或重建论文、原文证据、抽取模型记录或论文图谱，不回退GraphRevision。此次明确删除覆盖前轮对该条问答历史保留的默认约定，产品正常“移除保存内容”仍保持软移除。

**实施/验证**：隔离环境与实际宿主路径分别只读确认，临时Computer Use仅打开并关闭了非目标隔离窗口，不算正式原生验收。原拟只清显示指针的LevelDB备份读取因缺少表文件失败，未写入宿主WebView数据；后按用户最新指令停止该方案。实际删除使用忽略目录下的一次性维护脚本，先在内存SQLite副本演练（不留旧问答内容副本），再以EXCLUSIVE事务按精确归属和外键顺序清理；44张非Query来源/科学图谱表逐行哈希不变，其他任务/事件不变，保留4篇论文/429知识节点，integrity_check=ok、foreign_key_check=0。第二次独立只读核验Query/答案/专属模型/保存/段落均为0。执行Anaconda researchgraph-studio绝对解释器，无真实模型调用；匿名计数报告仅在.local，不纳入源码。

**文件/下一步**：仅更新docs/progress.md和本日志，产品源码与安装包未改，无需重跑代码回归；不把前轮879等回归重新计为本次测试。请用户重新打开问答页并重新输入问题重试，若旧页面缓存仍在需先重启应用；显示层重新验证仍待反馈。未Commit/Push、不进入P5。

## DEV-0054 — 2026-11-04 20:38（Asia/Shanghai）：完整问答浏览、独立论文筛选与引用分层

**目标与范围**：用户要求每个问答板块可选一/多篇论文、来源标明是否在图谱、浏览全部检索内容并每页10条，以及按论文归类回答和两层默认折叠引用。本轮继承全部未提交P4代码，不重建工程，不重复上轮旧问答删除，不读取/写入正式库作实验，不进入P5。

**实现**：新增query_browse及query_source_scope，调整query_api/query_retrieval/query_graph/query_presentation/query_save、reading_projection与生成契约；独立search/page不改变旧QueryRequest/prepare默认limit或冻结snapshot/manifest/hash，先取完整合法词面命中再显示过滤/分页，每页来源/权限重验，变化hash明确要求刷新。完整默认backbone单次收集而非反复画布分页，浏览跳过不必要的两两Claim比较；已有节点、图谱引用原文、仅检索候选及不适用区分。历史/保存paper_ids从实际冻结引用根派生，不按整问题scope假归属，个人资料不造论文关系，无数据库迁移，head0014。

前端更新QueryPanel/queryApi/QueryDerivedGraph，新增QueryBrowseControls；来源/回答/保存列表与详情/历史独立论文多选，列表及引用10条分页、总数/页数，跨页勾选保存保留。按真实引用根将段落归为单篇、跨篇综合、未归属，跨篇段只显一次；引用外层/单条均默认折叠，单独展开外层不会联动内层，全展开跨引用页有效。最终只读复核发现答案缓存先于run GET时会暂时归入未归属组，已修成冻结引用到齐后才展示，新增异步反序单测。Tauri新增精确POST浏览路由及64KB边界；Prompt/模型协议、旧科学数据/选择/布局不变。

**实际命令与结果**：Anaconda researchgraph-studio绝对解释器运行check-phase0，整体退出0：888 Python passed/2 skipped（394.70秒）、122 React，Ruff/190文件格式/mypy102源文件、依赖/OpenAPI-TS/Prettier/TS-ESLint/生产构建通过。首轮全Edge15通过，最后加载时序修复后query.spec.ts5通过；Rust15/fmt/clippy与新引擎打包Host1通过，交叠专项不累加。新build-windows退出0，PyInstaller/Tauri/NSIS通过；冻结smoke覆盖旧导入/知识/图谱及合成HTTP/SSE问答→保存→批注→重启→移除→重启（仅1本地stub POST）。PS5.1/System32-only PATH本轮未给PdfFixture，5项通过，不冒称旧17项。独立冻结browse合成29条10/10/9、论文28/1、节点/支撑原文/仅检索区别、hash拒绝和两启稳定，47张非Query表hash保持，Query/模型记录及模型端点请求新增0，integrity/FK通过。

Host首次用裸cargo因PATH缺失没有执行，改绝对.cargo/bin/cargo.exe后1项实际通过；本地合成样本预检需预先登记新增Chunk锚点以隔离正常启动回填，随后最终冻结验收通过，未改产品逻辑。已有httpx弃用/Vite大chunk及2项符号链接权限跳过继续记录。

**文档/交付**：新增ADR0025与p4-query-browsing-verification-20261104，同步README/AGENTS、docs产品/交互/开发计划/API/导航/协作模板/下一轮/progress。新包.local/releases/p4-query-browsing-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe，38805905字节，SHA256 `8ae2e658dcff4f45ad47a6139332315355cdfb831a14c2b77886ce0e75a6b5d8`；Sidecar `553b07939d864d4852abbba404bfafaa4804d09e56196bad9edd02192542f076`，174源指纹与281资源（不含生成pycache）一致，资源无私人PDF/DB/密钥/日志；新目录保留副本，旧包不覆盖。源码内容/Gitleaks、链接/规范hash和交付记录最终收尾另记。

**限制与下一步**：真实/付费模型调用0，正式库实验读写0，未Computer Use或替用户安装/卸载；完整浏览只意味着词面规则下全部合法命中，不等于新增逐篇语义综述。新包原生反馈待用户安装确认，真实strict/干净机/无OCR复杂版面/S1–S4四份不可用外部补充原文仍保留。HEAD和本地origin记录80552d3，没有Commit/Push，历史R5 CI不冒充本轮Query CI；交付后停P4，不自动开始P5。

**20:40 收尾（Asia/Shanghai）**：610源码候选实际内容/路径/Gitleaks、175 Markdown/768本地链接/88规范资产LF哈希、git diff --check及空暂存区通过；4份登记外部原文仍不可用。最终新包与构建副本相同，174运行源码/281资源指纹核对，匿名日志与delivery配对保存在.local，安装器不进入源码。无需新增付费调用或用户正式库实验，等待用户安装后的原生反馈。

## DEV-0055 — 2026-11-04 22:11（Asia/Shanghai）：修复本地问答历史数据库锁与无效响应

**问题与实因**：用户新安装版本地问答历史显示“本地服务返回了无效响应”。只读宿主engine-startup.log并仅提取异常类型/文件行号，定位history/documents/saved在scope_versions→BEGIN IMMEDIATE报database is locked，无日志正文/SQL参数/秘密输出，未读取或改写正式数据库。原纯读会话也申请写锁，长检索/索引事务令其等待5秒后失败；worker空轮询同样抢锁并在async线程同步等待，旧未处理DB异常返回非JSON500，Rust解码掩盖实因。隔离源测试及正常worker进程分别复现锁失败/4秒读取超时，失败成绩保留。

**修改**：storage启用WAL与保留FULL默认同步，新增只读read_session（执行选项/query_only/deferred BEGIN/autoflush关闭），归池及writer开始恢复写模式；8个Query读/校验路由和P07等待状态检查使用它，所有索引/prepare/生成入队/Store写保留IMMEDIATE/幂等。app工作器先只读探测queued，再短事务重验认领，claim及诊断完成DB步骤to_thread避免阻塞事件循环，BUSY未认领保留queued且零模型发送，取消等待认领线程完成再关闭清理。SQLAlchemy锁错误按码返回503 DATABASE_BUSY标准JSON，其它OperationalError脱敏500 DATABASE_ERROR。Rust decode_engine_response保留标准JSON消息及非JSON错误HTTP状态，不回显body/SQL。QueryPanel失败新增手动重新读取历史，只GET，无模型恢复；Prompt/Schema/历史manifest/科学知识/布局不改，head0014无迁移。

**验证**：Anaconda researchgraph-studio。新增test_query_concurrency7项，API/保存/纸篇归属等专项与全量交叠不累加；最终check-phase0完整退出0：895 Python passed/2 skipped（460.69秒）、123 React，Ruff/191文件格式/mypy102源文件、依赖/OpenAPI-TS/前端静态及生产构建通过。5 Query Edge、19 Rust/fmt/clippy与新引擎打包Host1通过。两次开发中全量在后续同类轮询修复时主动中止，不算通过；一个测试初用错误Job路由、一个前端重读DOM预期错误，修正后通过，未放宽产品校验。httpx弃用/Vite大chunk/符号链接权限2跳过继续记录。

**正常进程与包**：新build-windows退出0，PyInstaller/Tauri/NSIS通过。冻结normal worker两启，held writer且另一个prepare等锁时，7读全200（0.063/0.062秒），未提交状态隐藏；写争用两次503 JSON含retryable/request_id，未泄SQL；快照内writer可提交且原快照稳定。47来源表hash保持，Query1/Model0/Answer0不变，guard模型请求0，EOF/完整性/FK通过。冻结smoke旧导入/证据/图谱及合成SSE问答→保存/批注/移除/重启通过（仅1本地stub POST），PS5.1/System32-only PATH本轮5项通过，不冒称前轮17项。源码正常/失败/冻结记录均在.local/history-lock-20261104，未用于正式库实验。

**文档与交付**：新增ADR0026及query-history-lock-verification-20261104；同步架构/安全/运行API、README/AGENTS/导航/progress与日志。新包.local/releases/query-history-lock-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe，38823098字节，SHA256 `318f14db52341b6c865f48d0a8cdf9cc08916510c162bc780434cf1790d8f73a`；引擎 `3efce8e0d0069c7ed84cb3cd99d284b2faba7bb4b3d6430f8ba933649c6514c1`，174运行源码/281资源指纹一致，资源无私人PDF/DB/密钥/日志，旧包保留。最终敏感扫描、链接/规范LF hash及delivery配对随后收尾。

**限制与下一步**：真实/付费调用0，正式数据库实验读写0，未Computer Use/替用户安装或卸载。请用户退出旧应用、安装新包后在原项目重开历史；读取失败可手动重读，不重抽论文/生成答案。新包原生反馈待确认；真实strict、干净机、复杂版面无OCR和S1–S4四份外部原文不可用仍保留。未Commit/Push，HEAD/本地origin记录80552d3，不以历史CI代替本轮；停P4不自动进入P5。

**22:14 收尾（Asia/Shanghai）**：613源码候选实际内容/路径/Gitleaks、177 Markdown/788本地链接/88规范资产LF哈希、diff/空暂存区通过；4份登记外部原文仍不可用。文档刷新首次写SHA文件OSError22，重试UTF8后hash与链接全部通过，未将尝试记为完成。安装器/174源码/281资源及匿名报告指纹最终配对封存于.local，新安装器用户原生反馈仍待确认，未增加真实调用/正式库实验/Commit/Push。

## DEV-0056 — 2026-11-05 09:57（Asia/Shanghai）：P4最终回归、真实问答及数值保护

**范围与数据**：用户要求当前P的回归与真实验收，并反馈旧锁修复安装包数据功能正常。本轮为P4-Q08，不进入P5；旧包反馈不继承新包。先保留既有未提交Query成果，以mode=ro/SQLite backup API建立独立副本，不复制活跃WAL主文件作备份；正式库实验写入0。复用当前全局Reasoning及OS凭据，不写密钥到脚本/数据库/日志，不重抽论文，不改PDF/Zotero/私人笔记，head0014无迁移。

**真实验收**：两篇已有partial图谱，固定十题后发出9次P07，9成功/1无据不足零调用；72段/396引用，冻结来源/offset/归属逐项核验。独立原PDF完整页/上标几何复核将初审一项partial更正为实际数值错误，最终64支持/7部分/1数值错误，raw和失败样本保持，不冒充全部科学正确。部分项仍含表列/公式引用覆盖、措辞与轮次/提议混用，限制明确记录。真实分页76非空+1空页、独立论文范围/默认图谱标记、历史两页、3份显式保存及1份移除、批注/幂等与两次完整重启均通过；44来源表及科学修订、旧raw/任务/布局保持。私人问题/题名/正文/副本仅.local，报告只写匿名成绩。

**修复**：query_graph按本调用唯一runID批量加载ModelRun，query_retrieval采用必要标量并复用完整新鲜合法entries，保留逐候选/边/来源/锚点/权限终验，无跨调用cache/裁剪；270Query及8场景完整响应/30001索引等价先通过。新增query_numeric_layout、P07_query_grounded_v2和专项测试，context冻结numeric_layout，新旧Prompt/manifest/hash分开；正文已知压平危险数字终验拒绝，旧v1新保存对所选段落作当前版式检查，presentation只读警告。唯一额外真实v2请求产生六段正文，涉及歧义数值的段落留未知，专用limitations列举危险token被初版守卫误拦；程序仅对这两个字段8处token按原Unicode跨度占位，留display_normalization哈希审计，不改正文/raw、不猜数值。显式recovery-only锁定runID/rawSHA/plan及已有槽预算，provider/新槽前重验、失败零网络，不回退付费；实际同raw新增0请求/0槽恢复，原失败Job/审计保留、保存及重启通过。补验独立5支持/1部分，原十题64/7/1不冲销。总10真实请求、1,623,354 Token，供应商金额未知，验收结束不自动追加。

**最终回归与包**：Conda researchgraph-studio，check-phase0完整退出0：914 Python passed/2符号链接权限跳过（443.17秒）、124 React，Ruff/194格式/mypy103源文件/依赖/契约/前端类型/lint/build通过；含289Query，15真实Edge组件测试、19Rust/fmt/clippy和打包Host1通过。176运行源指纹前后不变，首次最终全量因后续误拦修复主动中断不算通过。最终build-windows完成PyInstaller/Tauri/NSIS；冻结smoke本地合成SSE、PS5.1/System32-only PATH隔离17项通过。正常worker两启每轮7读200，0.109/0.078秒，竞争writer标准503、47来源表/Query计数保持、0模型请求。Host初跑缺RGS_TEST_ENGINE_PATH失败，补环境后实际1项通过。安全扫描把两个长合成幂等字符串误报generic-api-key，缩短测试常量后内容/路径/Gitleaks实际通过，未加忽略规则或放宽校验；定向重验和最终性能/文档封存随后收尾。

**交付与下一步**：新增ADR0027和p4-final-acceptance-20261105，更新README/AGENTS、Schema/Prompt/API/安全/开发计划/导航/进度与续接说明。新包.local/releases/p4-final-acceptance-20261105/ResearchGraph Studio_0.0.1_x64-setup.exe，38,832,356字节，SHA256 `19929c6990fb1ae0fa166450431a586025664d219a40b942c3d240755c38a6b8`，旧包保留；新包原生待用户安装反馈。真实strict、跨模型/平台、干净机、复杂版面无OCR、S1–S4四份登记外部原文不可用仍保留。未Computer Use/替用户安装/Commit/Push，P4收尾后停止，不自动开始P5。所有实际命令、完整账本与补验分母见本轮报告。

**10:03 收尾（Asia/Shanghai）**：最终主源码串行万候选/两万块基准cold3.129851秒、warm P50=2.608713/P95=3.016278秒，未达≤2秒；隔离候选1.922秒不能替代最终成绩，保留为P4性能问题，不为追指标删慢样本或减验证。峰RSS275472384B，总库45969408B，FTS逻辑UTF8 3687347B、物理页大小未知。两项合成幂等key首次缩至7字符导致INVALID_INPUT，改12字符后19数值专项实际通过(7.57s)，不改产品/不重叠累加。618源码内容/路径/Gitleaks、180Markdown/806本地链接/88资产LF hash、diff和空暂存区通过。176源码与最终回归前后/交付完全一致、282资源与引擎副本一致，无私人运行资料；新安装器与匿名delivery封存，正式库实验写入0，真实总调用仍10，金额未知。所有P4门槛未宣称全过；新包原生反馈、科学partial/复杂版面及性能保留，不自动进入P5。

## DEV-0057 — 2026-11-05（Asia/Shanghai）：交付P4成果并继续处理未达标项

**用户授权与顺序**：用户明确要求提交并推送GitHub，再尝试解决未达标内容。保留DEV0056的真实科学失败/部分支持、性能3.016秒、新包原生待反馈等事实；先扫描交付当前快照，再在P4优化，不进入P5。正式库不实验写入，不重新抽取或自动追加已结束的模型验收。

**开始状态**：HEAD80552d3，既有P4未提交改动全部保留；SSH443官方通道fetch成功，origin地址及全局配置不变；候选源码618文件实际内容/路径/Gitleaks通过。性能与科学质量审查先在.local隔离执行，不改交付快照；提交/CI与后续实际修改/测试结果在本条后续追加。

**11:08 实际结果（Asia/Shanghai）**：先经历史/内容/路径/104暂存文件Gitleaks与diff检查，将P4成果提交为8d67ed1并普通推送main；对应GitHub Actions 41954098280的windows与installed-app全部成功，含真实Edge/冻结引擎/Rust/NSIS/实际安装VerifyDesktop。未上传私人验收库/raw/PDF/凭据或安装产物。

**改进代码**：query_graph仅取NodeEvidence必要两列；query_retrieval与unified_store减少本调用遍历、固定UUIDv5前缀及JSON编码器重复构造，不跨调用缓存、不减来源/权限/DTO/锚点/边验证。新增query_scientific_grounding.py、P07_query_grounded_v3.md及表示兼容/科学支撑测试，接入context/API/answers/answer_wire。新prepare冻结scientific_guidance，程序沿真实node/evidence/chunk及已检测表格组补合法根引用、绑定后再验归属，scientific_binding审计在GET/保存重建；不猜表列/公式。旧v1/v2 Prompt/hash/raw/答案不改，wire DTO不变、head0014无迁移。README、Schema/Prompt/API/安全/开发计划/导航/续接、ADR0028、进度与实际报告同步。

**最终回归与性能**：Conda researchgraph-studio执行check-phase0完整退出0：934 Python passed/2 Windows符号链接权限跳过（402.45秒）、124 React，Ruff/198格式/mypy104源文件/依赖/契约/前端类型/lint/build通过。99科学相关与7表示测试交叠不累加；178运行源在全量前后及最终基准后一致。8场景完整响应、30001索引hash/字节、47来源表保持，FTS缺项恢复/恶意派生行清理/下次变源重验与Unicode身份兼容通过。保留候选P95=4.249及诊断2.240失败，不删慢样本或改GC/负载；所有构建/真实/冻结检查结束后一次串行原规格万候选/两万块基准cold1.457742秒、warm P50=1.229685/P95=1.583589秒（12样本nearest-rank，P95=max）。本机≤2秒目标达到，旧3.016278不改写，不宣称通用SLA；峰RSS275161088B、总库45969408B、FTS逻辑UTF8 3687347B，物理页未知。

**真实定向补验**：从前轮只读备份建新副本，使用该基线冻结的全局Reasoning及OS凭据，仅内存处理密钥；正式库实验写入0，无论文重抽。执行前持久冻结2请求预算，两次P07v3成功/19段、0超时或Schema失败/自动重试。prompt304290、completion12881、total317171 Token（reasoning9243为细分），金额未知，预算结束不追加。独立审读q03为10支持，q07为6支持/3部分，共16/3/0；残余术语等同、组内扩大组间、跨页引用不足如实保留，程序补42个已有合法引用不算科学正确性证明。原十题64/7/1和v2补验5/1不冲销，raw正文不改。普通Query期间45来源表/GraphRevision/旧任务raw答案保持；两份显式保存、同/新键幂等及两次完整引擎重启通过，后续0模型调用。旧副本重新验证44来源表和旧十题/数值补验逐字保持、已知错数的新保存拒绝。

**打包与限制**：build-windows完成PyInstaller/Tauri/NSIS，冻结smoke（本地合成协议）、Host1、PS5.1/System32-only PATH隔离17项通过；正常worker并发两启每轮7读200（0.078/0.078秒）、竞争写503 DATABASE_BUSY、47来源表及Query计数保持/0模型请求。并发脚本初次被旧BASE拒绝报告路径且未启动实验，迁入本轮独立BASE后通过，未放宽边界。新包.local/releases/p4-grounding-followup-20261105/ResearchGraph Studio_0.0.1_x64-setup.exe，38839020字节，SHA256 23079790f3c7717e26cf9a9561b4b3308e039bd438554c7b60a6d2dc2b4d4e7d，引擎5534b788f4a5afda87c00bb3a1cfb35321486e46bf92d41a5a37c40bf32cd079。624源码候选内容/路径/Gitleaks已通过，最终暂存/文档/封存与优化提交CI随后追加。新包原生待用户反馈；科学3部分、真实strict、跨模型/平台、干净机、复杂版面无OCR与4外部登记原文不可用保留；不进入P5。

**11:10 封存（Asia/Shanghai）**：178运行源与最终回归及新包一致，283资源与引擎副本逐字匹配，无私人运行资料；安装器及匿名delivery封存成功。624源码候选内容/路径/Gitleaks、24提交历史Gitleaks、183 Markdown/824本地链接/88规范资产LF hash及diff通过；4份外部原文不可用继续单列，不声称核验完成。

**11:11 优化交付（Asia/Shanghai）**：28个实际暂存文件的内容/路径/Gitleaks与diff通过后，提交75061d2e3804a37c9b6209d716fa207f86173bb4并普通推送main；未强推、未改origin或全局Git/网络配置。178运行源与该提交blob按LF规范化逐字匹配，安装器不变。独立CI run41959965368已启动，最终构建和安装结论继续核实，不用8d67ed1成绩替代。

**11:33 远端收尾（Asia/Shanghai）**：优化源码75061d2的独立GitHub Actions run41959965368全部success，windows及installed-app均成功、失败步骤0；环境/契约/后端/前端/真实Edge/冻结引擎/Rust/Host/NSIS/产物上传通过，独立runner实际安装并以Windows PowerShell运行VerifyDesktop成功（03:31:17～03:31:57 UTC）。远端项数未提取，不假称等于本机成绩，CI不替代科学语义验收。本轮两份CI各自有精确SHA和匿名receipt；新run/jobs/summary及2产物元信息保存在.local/p4-followup-20261105/ci/followup，未下载或替用户安装远端产物。最后仅提交验收文档和规范hash，不改178运行源或封存安装器；最终内容/暂存/Gitleaks/文档检查后普通推送，包原生与科学3部分等保留，不进入P5。

**11:36 最终检查（Asia/Shanghai）**：624源码候选内容/路径/Gitleaks、25提交历史Gitleaks、10个实际文档暂存文件内容/路径/Gitleaks与暂存diff通过；183 Markdown/825本地链接/88资产LF hash通过，4外部原文不可用仍单列。最终文档提交与运行源码75061d2明确分开，源码、资源、安装器及匿名CI receipt保存在本机delivery配对；私人资料和安装器不上传，真实调用保持本增量2次、验收已结束。

## DEV-0058 — 2026-11-05 13:36（Asia/Shanghai）：恢复中断的 P5 Lint / Wiki

**目标与授权**：用户明确要求重新核对开发文档/已有内容并继续P5，覆盖旧轮“不进入P5”的阶段限制；无新的Commit/Push或付费预算。已读取上一中断会话与未提交源码，保留其全部工作；正式库实验写入0，真实模型调用0。

**实现及修复**：保留0015～0017加性迁移，接入KnowledgeStore Lint/Wiki delegate、确定性报告/反向依赖、Wiki页面/稳定段落/草稿保存、独立目录授权和发布恢复账本；P09/P10/P11独立DTO/Prompt/请求槽/统一Job，首次成功/GET/保存重验。修正可信来源变化与坏响应分类、materialize首次返回不完整、双槽后合法raw恢复入口、Wiki损坏/缓存正文和引用信任、新文件绑定扫描、桌面路径/参数白名单、模型同意绑定范围。生产HTTP smoke又暴露并修正非法Job stage和P11把自己旧页作证据导致更新后历史失效，目标页现仅为基线上下文。

**增量检查**：首次显式完整Lint初始化cursor，普通worker空轮询每秒最多维护1项目/25目标，事件差距与30秒权威对账兜底，旧/新依赖边并集找影响，不自动请求模型；已选个人范围和当前权限保留，未启用项目不写诊断。运行源已冻结，正在完整check-phase0。

**已实际验证**：139 React/18 Edge、Rust20及fmt/clippy、P5工作流21、Lint28、Wiki46/1权限跳过、0014→0017迁移/双重完整重启2通过（重叠不累加）。生产源码HTTP/SSE本地stub P09/P10/P11各1、3槽，草稿/保存/首次导出/单段更新/重新导出/外改冲突/重启通过，真实模型0。全量与最终冻结包结果随后追加，不沿用P4成绩。

**性能实况**：固定万候选/两万块最终Lint来源freeze0.907763秒，单块变化reconcile+4目标检查10.260801秒，反向影响查询0.340672秒，准确1段/1页，无变化1.365660秒/零新报告，峰RSS322482176B。中间源码完整扫描444.901秒另列，不冒充最终全量或≤2秒。完整catalog重验/反向索引重建仍是性能限制。

**文档与未完成**：新增ADR0029及p5-verification-20261105，更新README、AGENTS、docs00～08/API/导航/续接/进度；历史P4分母/raw/协议保持。真实P09/10/11科学质量、独立Zotero Annotation.comment模型来源/授权、逐份note选择、外部MD显式新文档登记、原生目录选择器/新包用户反馈未完成，不能标P5退出。私人文件仅只读诊断，标准替换非任意外部编辑器原子CAS。未Commit/Push/收费/替用户安装。

**13:52 基线与继续补齐（Asia/Shanghai）**：head0017最终check-phase0完整退出0：1044 Python passed/3权限跳过（442.15秒）、139 React，静态/依赖/契约/build通过。0017封存包07627380及其冻结P5/旧smoke、Host1、PS5.1隔离17项均实际通过，但核对W01/W02发现逐份个人选择、Annotation.comment独立用途链及外部MD登记仍属软件缺口，因此继续开发并将该包保留为中间基线，不以它冒充后续0019交付。新增0018外部来源与0019批注权限/最后显式导入索引；最终验证与重建随后记录。未新增真实请求、正式库实验或上传。

**15:17 最终功能与回归（Asia/Shanghai）**：新增p5_personal/p5_sources/external_documents及API/模型/契约、0018/0019迁移；P5Sources/P5Workspace接逐份note/Annotation.comment/外部版本，授权与选择分开。query_documents/answer_wire/context及新query_local_access贯穿普通Query兼读和HTTP双用途保护；Wiki/external GET、旧diff、历史不同根与旧批注列表均重验local，撤权保留原行但隐藏正文。修复P09规则报告间接外发、P11失效根/旧基线选择漏洞；评论是用户观点，external_source不冒充用户或论文作者。模型raw/hash不重写，当前批注只保证最后显式导入。P5前端补中文归属/授权提示，Tauri schema为0019、白名单匹配真实路由。

最终head0019完整check-phase0退出0：1124 Python passed/3符号链接权限跳过（460.77秒）、148 React；Ruff/242格式/mypy134源文件/依赖/契约/前端静态与build通过。两次失败全量保留：首次旧note-only fixture误设model_synthesis（1123/3/1），依据旧P07规则改user_view后19专项通过；第二次未知锚点断言整份MD不含100误中随机SHA（1123/3/1），只删宽泛断言、保留PDF页标签/链接门槛，37专项通过。未放宽产品验证。历史非法归属的新Store保存可能拒绝，旧行/raw/hash不改。

最终19 Edge（33.7秒）、Rust20/fmt/clippy、打包Host1（3.34秒）、冻结P5与旧smoke、PS5.1/System32-only PATH隔离17项通过。首次Edge与打包并行时Vite监听被占用exe报EBUSY，串行重跑19通过；失败尝试未覆盖。213运行源/312资源配对一致，无私人运行数据资源；PyInstaller/Tauri/NSIS成功。最终包.local/releases/p5-lint-wiki-complete-20261105/ResearchGraph Studio_0.0.1_x64-setup.exe，39,025,809字节，SHA256 8aef46ad987518532eaf2569cc4b1f6aa2373f6bed038f10336c417b6e1471e6；引擎a3a842d276d321a5981a00918d9997123638d6a1139f54d9945c14e5fc09ab67。包封存与构建副本一致，未替用户安装。最后性能、安全、文档配对另续。

未完成真实P09/P10/P11科学逐段验收、新包用户原生/目录选择器/干净机/跨平台/strict；未继承已结束P4收费预算。本轮真实调用0、正式库实验写入0，未Computer Use/Commit/Push。复杂版面/公式/无OCR、文件并发非任意编辑器原子CAS及四份不可用外部原文限制保留；下一步先完成固定规模性能和文档安全封存，再交付操作步骤，不标P5退出全过。

**15:25 性能与封存（Asia/Shanghai）**：所有测试/构建结束后串行最终Lint基准：10,000候选/20,000原文块/2Wiki/30,011目标，冻结1.036694秒、完整扫描430.284749秒，completed且error0/warning0/info1、规则异常0；初次依赖重建7.524021秒，单块变化显式对账7.663831秒，反向影响查询0.496275秒，准确1段/1页。峰RSS304955392B、总库48369664B，301批样本及8源指纹保持；不冒充P95、当前自动增量端到端或继承P4≤2秒目标，完整catalog复验/重建仍待性能优化。报告在.local/p5-lint-complete-20261105/report.json，隔离新库不触碰用户库。

README/导航和docs00～09的当前状态、批注/外部来源及真实运行路由已统一（12文档、352本地目标、30组P5方法/路径独立复核）；带日期历史分母/授权保留。最终678源码候选实际内容/路径/Gitleaks、188Markdown/853本地链接目标/88资产LF hash、diff及空暂存区通过，4外部原文不可用仍单列。213运行源与312资源在最终基准后再次逐字配对，封存安装器hash与构建产物相同，匿名delivery/失败日志分别保留。未新增真实调用/正式库实验/Commit/Push；本轮软件、自动化与安装器交付完成，下一步由用户按P5报告步骤反馈原生结果，真实科学验收需新的明确预算，不自动收费。

## DEV-0059 — 2026-11-05 16:00（Asia/Shanghai）：修复 P5 扫描状态停留

**用户反馈与定位**：用户确认unknown提示出现后，上方仍显示“正在处理”，进度停住。规则CONDITION_UNKNOWN原为info，_emit只增提示计数，processed照常推进；没有因unknown阻塞完成。发现P5Workspace报告只读一次、未主动观察后续状态，旧GET/advance可能晚到回退显示；桌面25项一批而每调用复验全catalog，首个全项目扫描末批还建依赖索引，真实耗时与界面滞后都需区分。只读默认目录状态计数/异常类型未找到对应run，不据此宣称用户后台已完成；未读私人正文/raw/凭据、未修改正式数据。

**改动**：P5Workspace.tsx增加准备范围/本页推进/待继续提示、2秒只读轮询及手动读取，终态停轮询，进度/终态/读取版本护栏与cancelQueries避免迟到响应回退，取消/卸载operation代次保护。p5Api.ts桌面每批25→100，仍为原允许上限，不改后端默认25和逐调用验源；P5Workspace.test.tsx/e2e/p5.spec.ts复现unknown可见+进度停住、旧GET/advance晚到、取消/完成、只读观察零推进和零模型。scripts/smoke-p5.py改实际HTTP100项，与桌面一致。unknown仍info、条件原值保留，不推断矛盾/补条件；完成计数区分错误/警告/信息。Python/Rust运行源、schema0019、Prompt/旧raw/hash/科学知识不改。

**实际验证**：本轮31后端Lint/文档专项通过（10.33秒），155完整React/17文件通过（17.15秒，含P5专项27），Prettier/TS/ESLint、smoke脚本Ruff/format通过；最终19真实Edge通过（34.3秒）。首次Edge与Host并行时监听debug exe报EBUSY、未启动，保留失败日志，Host结束后串行重跑通过。新PyInstaller/Tauri/NSIS退出0，642.48KB chunk提示保留。冻结P5实际HTTP100项完成；P09/P10/P11仅本地合成SSE各1、3槽，草稿/保存/导出/局部更新/外改/重启/撤权通过，旧冻结smoke也通过。打包Host1（3.65秒）、PS5.1/System32-only PATH隔离17项通过，不算实际安装。213运行源/312资源配对，Python引擎hash仍a3a842d276d321a5981a00918d9997123638d6a1139f54d9945c14e5fc09ab67。

**交付与限制**：新包.local/releases/p5-scan-status-20261105/ResearchGraph Studio_0.0.1_x64-setup.exe，39,048,185字节，SHA256 e432990a527c2de3e4fc17550af9bd2d258f2eb30c3c84011c58e38ca77b6304，旧包保留；新增反馈报告，更新ADR0029/progress/CODEX/AGENTS。旧1124全量与430.284749秒不冒充本轮重跑；8后端基准源一致、旧基准本就是100项，只减少请求轮次不宣称4倍实测加速，完整catalog/末批索引仍可能慢。真实模型0、正式库实验写入0、无Computer Use/替用户安装/Commit/Push，新包原生待用户反馈。操作为退出旧版安装→原报告重新读取→实际未完成则显式继续，不删知识或重抽。最后敏感内容/文档哈希收尾另记。

**16:03 封存（Asia/Shanghai）**：679源码候选实际内容/路径/Gitleaks、189Markdown/858本地链接目标/88规范资产LF hash、diff和空暂存区通过；4外部原文仍不可用。213运行源/312资源及e432990a安装器副本配对无漂移，匿名validation/失败与最终日志分别保留于.local/p5-scan-feedback-20261105和本轮release；用户原生反馈、真实科学和性能限制不改，无收费/正式库实验/上传。

## DEV-0060 — 2026-11-07（Asia/Shanghai）：整理当前文档与历史归档

**目标与范围**：用户要求先整理 docs，更新过时说明、移除重复和不需要的文档。当前仍为 P5/head0019，保留已有未提交的运行源码、迁移、Prompt、测试及两份 P5 报告。本轮仅调整文档与文档清单，没有新的 Commit/Push、模型预算或正式库实验授权。

**当前入口**：更新根 README/AGENTS、桌面 README、docs/README、progress、CODEX_NEXT_TURN、00–09、api 和 model-configuration；当前进度集中在 progress，设计章节指向当前状态，续接文件明确为开发指令。移除重复的 P4/head0014/P5未启动状态段；修正旧 P02 固定输入预算、模型用途与个人资料授权说明；区分设计参考与运行 DTO、确定性 Lint 与 P09建议、内部保存与文件发布。历史时间、失败分母、费用未知和未测项不写成当前限制或新成绩。

**归档与删除**：30 份已结束轮次的报告（含环境报告）移至 docs/archive/reports，新增分类索引；整理前的完整 progress 保存在 progress-through-20261105.md。报告正文只修改链接目标，31 份历史正文逐一对照本轮备份，失败、科学分母、调用预算、授权和包指纹保持。删除 docs/AGENTS.template.md 重复协作模板、docs/CHANGELOG_FROM_V2.md 纯跳转页；归档规范中的同名原文保留。同步根协作规则、ADR、旧设计与交接引用，迁移映射标明历史语境；不保留第二套同内容跳转页。本轮前完整文档、路径映射及检查凭据仅存忽略目录 .local/docs-cleanup-20261107，不进入源码交付。

**实际验证**：使用 Conda researchgraph-studio 的绝对解释器执行 .local/docs-cleanup-20261107/check_docs.py --refresh 后再只读复核。189 份 Markdown、804 个本地链接目标通过，仓库内断链 0；四份已登记外部原文仍不可用，单列为既有限制，未假称已核验。当前 86 项规范资产及归档 v3 的 52 项资产 LF 字节/大小/哈希一致；归档清单明确标注链接调整后的字节，不冒充原包指纹。366 个非文档文件对照整理前 SHA256 和路径集合，无修改/新增/删除；32 个原路径删除对应 30 个已核对归档及 2 个重复入口，没有意外删除。git diff --check 与空暂存区检查通过。首次本地校验脚本以 __file__ 定位时遭遇 Windows 路径编码错误，改用实际工作目录后通过；该失败未改写文档或触及运行数据。

**结果与下一步**：文档整理完成，应用仍是已有 P5 实现；本轮未执行应用回归、性能重跑、模型调用、数据库实验、安装器重建、原生操作或 Commit/Push。真实 P09/P10/P11 科学质量、最新包用户原生反馈、Lint 完整 catalog 复验/重建性能、strict/跨模型/平台/干净机/无 OCR 等限制保留，不标 P5 全部退出通过。后续按当前 progress 和用户新指令继续。

## DEV-0061 — 2026-11-07（Asia/Shanghai）：为 Lint 诊断增加修复/处理方案

**用户反馈**：用户确认扫描可以继续，并指出当前问题卡片已经能显示 Lint 结果，但只有问题说明和依赖影响范围，没有下一步处理方案。截图中的 `SOURCE_UNCHECKED` 与 `CONDITION_UNKNOWN` 需要分别说明如何处理，不能把信息缺口当成科学矛盾。

**实现**：Lint 后端为每条诊断增加只读 `repair_plan`，包含状态、摘要、处理步骤、动作标识和保护边界；通过 OpenAPI/TypeScript 契约同步。按 26 条规则区分来源、证据/支撑、依赖、私人笔记、独立外部阅读材料和受管文件，结合已消失/输入过期生命周期生成方案。`SOURCE_UNCHECKED` 方案为在文献页检查文件、记录可用性、重新运行受影响范围的 Lint。`CONDITION_UNKNOWN` 方案为回查正文/表格/图注，有明确证据时才准备受控重建或新版本，没有证据时继续保留 `unknown`；不提供直接编辑旧条件的入口，不据此推断矛盾或补造条件。

桌面每个问题卡片新增“修复 / 处理方案”区域，展示步骤、是否需要用户确认、模型需求和保护边界。模型需求 false/true/null 分别显示“此步骤不调用模型”“需要模型（需单独授权）”“由后续受控流程决定”，缺省不冒充 false。方案展示不执行修复或调用模型，不修改原文、EvidenceSpan、知识节点、Wiki 正文、私人文件或历史 raw。旧报告读取时即可派生新方案；旧响应没有 `repair_plan` 时使用安全回退。

**兼容边界**：方案只在 `issue_view` 派生，不新增数据库字段/迁移、不进入稳定问题指纹。`_lint_snapshot` 在冻结前排除 `repair_plan`，避免旧 P09 工作流被只读展示变化误判 `P5_BASE_CHANGED`。回归从旧问题形状准备任务，再更换当前方案文案，检查 API、幂等准备、GET、执行及重启；冻结 snapshot/input_hash/wire_hash、原 raw/rawSHA 与科学行保持，只有一次合成 provider 请求。生产 HTTP/SSE smoke 另核对问题 API 有方案、模型输入没有方案。

**中间验证**：最初 `test_lint.py` 29 passed、前端 28 passed 属于初版；随后后端 Lint/工作流 86 passed，其余八个 P5 相关文件 141 passed/1 符号链接权限跳过。前端三态版完整 157 React/17 文件及 Edge P5 专项 4 项通过；Conda `researchgraph-studio` 的 mypy 134 源文件、Ruff、TypeScript/ESLint、契约导出及生成通过。首次最终 Prettier 检查发现两个前端文件格式不符，格式化后检查通过；不把首次失败记为成功。源码 HTTP/SSE 合成 P09/P10/P11 各一次、3 持久槽，方案输出和模型输入隔离、草稿/保存/发布/局部更新/外改/重启通过，真实模型 0。最终对象归属修正、回归及安装器结果继续追加，不沿用旧包成绩。

**最终归属及入口修正**：只读审查发现 `NOTE_CHANGED` 不能套用受管发布，外部文档也会发出 FILE_MODIFIED/MISSING/UNAVAILABLE；最终按 object_type 分支，外部材料仅检查授权/原文件并显式登记新版本，旧快照保留。隔离真实文件改写、删除和原路径变目录三类扫描验证方案、版本/段落和 GraphRevision。受管文件名由程序生成，冲突方案指向现有“授权目录与 Markdown 导出”选择不同独立授权目录，不误导选择文件名或覆盖冲突文件。断链仅恢复目标或在原编辑器处理私人文本，不把生成新草稿列为无模型动作。前端缺字段回退也先处理 resolved/input_stale：已消失只查看历史，过期先新扫描。

**21:44 最终验证与交付（Asia/Shanghai）**：冻结最终运行源后执行下列后端专项，234 passed / 1 skipped / 1 warning，80.09 秒：

```powershell
python -m pytest tests/engine/test_lint.py tests/engine/test_p5_workflows.py tests/engine/test_lint_documents.py tests/engine/test_p5_document_access.py tests/engine/test_p5_personal.py tests/engine/test_p5_migration.py tests/engine/test_external_documents.py tests/engine/test_wiki_documents.py tests/engine/test_wiki_publication.py tests/engine/test_query_local_access.py -q
```

Python 使用 `C:\Users\KLucen\anaconda3\envs\researchgraph-studio\python.exe`；唯一跳过为当前账户无 symlink 权限，junction 项通过，TestClient/httpx 弃用提示保留，未换依赖或放宽验证。`pnpm test` 最终 159 passed / 17 文件（含 P5Workspace 31，18.04 秒），`pnpm --dir apps/desktop exec playwright test e2e/p5.spec.ts` 4 passed（14.3 秒，真实 headless Edge 合成组件）；mypy 134 源文件、六个相关文件 Ruff/format、pnpm check/format:check 及 OpenAPI/TypeScript 生成通过。旧 1124 全量后端和 430.284749 秒规模基准本轮未跑，不能沿用为新成绩。

`scripts/build-windows.ps1` 的 PyInstaller/Tauri/NSIS 全部退出 0；保留 646.94KB 前端 chunk 提示。最终引擎执行 `scripts/smoke-p5.py --executable <本轮冻结引擎>` 与 `scripts/smoke-engine.py --executable <同引擎>` 均通过；P5 为两篇合成 PDF、本地 HTTP/SSE P09/P10/P11 各一次、3 持久槽，核对方案 API、模型输入隔离、保存/发布/局部更新/外改/撤权/重启，真实请求 0。Windows PowerShell 5.1 执行 `scripts/verify-windows-install.ps1 -EnginePath <同引擎> -OutputRoot <本轮新隔离目录>`，System32-only PATH 的 5 项检查通过；本轮未传 PDF fixture，没有套用旧 17 项，也未运行 Host 或实际安装应用。

213 运行源在回归/构建前后 LF 指纹一致，312 引擎资源与 Tauri 副本逐字匹配、无私人运行资料路径。安装器封存到 `.local/releases/p5-lint-repair-20261107/ResearchGraph Studio_0.0.1_x64-setup.exe`，39,057,863 字节，SHA256 `7c08d3b841edce5af7177b52d3acf5408731ba8b15ddaeef72b652bed62c494a`；引擎 SHA256 `ae038a2efc6ad45989638ad7608c4bb21e85d07e68150018671d7b265b56e2b7`，副本与构建产物相同。源、资源清单、最终原始日志及匿名 delivery 保存在 `.local/lint-repair-20261107`，旧报告/失败日志不覆盖。

**用户操作及边界**：退出旧应用、安装本包，打开原 Lint 报告并“重新读取报告”即可看到方案，不需要重抽论文或为了显示方案重新扫描。实际处理来源/保存新版本后再重跑受影响范围；unknown 信息缺口允许继续保留。用户确认此前扫描可以继续只记录为该项原生反馈，新方案包、目录选择/发布/重启及真实科学质量仍待验收。schema0019 无新增迁移，真实模型调用 0、正式库实验写入 0、未 Computer Use/替用户安装/Commit/Push；后续模型任务需自身用途授权与清楚预算，不继承 P4/R5 请求许可。

**21:53 文档与内容收尾（Asia/Shanghai）**：189 份 Markdown / 806 个本地链接目标、86 项当前规范资产与 52 项归档资产的 LF 大小/哈希通过，仓库内断链 0；四份已登记外部原文仍不可用，未计通过。679 个源码候选的实际内容/路径规则与 Gitleaks 通过，`git diff --check` 通过且暂存区为空。最后再核对 213 运行源与封存安装器指纹无漂移；这些检查没有读取正式库、私人正文或凭据，没有上传或提交。

## DEV-0062 — 2026-11-07（Asia/Shanghai）：Lint 性能、阶段进度与固定规模基准

**目标与授权**：用户要求优化依赖索引重建/反向影响查询、批量读取/数据库索引/阶段计时、准备/推进/末批依赖重建的进度，以及固定规模基准和峰值内存。保留所有已有未提交 P5 与文档整理内容；无新的 Commit/Push、收费或正式库实验授权。基准和迁移仅使用新建匿名合成库，真实模型调用 0、正式库实验写入 0。

**实现**：lint_service 对 Chunk/KnowledgeNode 使用流式完整列投影，对来源记录/关联/成员批量读取，保持原 target 排序和嵌套 hash；advance 按当前批次预取节点及来源/关联/端点，原 validate_evidence 仍逐 link 调用，结束或异常清空引用。lint_dependencies 独立 helper 使用列读取和分块 Core executemany 重建派生边；递归 UNION 完整双向闭包以已到达对象为外层、按方向索引完整键探测，先当前权限过滤再计数/分页；隐藏中间节点不泄漏、不剪断公共后继，旧/新边并集对账保持。

0020 加性迁移新增 LintRun.phase/timings 和 paper_sources(revision_id)、reading_members(node_id)、reading_units(root_claim_id,document_version_id) 三索引，同步 ORM、引擎/Tauri/安装验证握手及当前 head 断言。旧活动报告 scanning、旧终态 finished、历史 timings={}，不补造旧耗时，不改 targets/input_hash/operation/科学行/raw/图修订。P5Workspace 区分准备范围、对象扫描、依赖重建；末批对象满数先提交仍 active 的 rebuilding_dependencies，下一调用重验再建索引结束。桌面和自动继续 key 含 phase，迟到同进度响应不能回退阶段；GET 不写不推进。timings 单调时钟记录阶段与实际推进次数，不计用户等待/全部提交网络开销，不进入 P09/P10/P11 冻结科学输入/hash。unknown 保持 info，不补条件或推断矛盾。

**等价与专项证据**：优化前163运行文件封存至.local/lint-performance-20261107/baseline-source。相同query_only只读快照的30,011有序targets逐项完全相同，digest精确等于原input_hash `68e3c45b75667ceb72ce98355643cf6ad7350dfd2fd8d859130cb9681f31a1f4`，DB前后sha不变。6类科学/文档/私人来源/损坏/撤权场景整边全部字段、cursor objects和72次查询响应等价。1200层循环/多路径、2000无关边、双向稳定分页、隐藏中间节点专项通过；首次普通INNER JOIN被SQLite重排为项目扫边的计划失败保留，改固定外层方向索引后实际EXPLAIN通过。

批读取专项105复制候选逐link调用原validator、两批关联SQL每表每批≤3、strongref/映射清空和weakref释放；下一调用变原文/删link即input_stale且processed不进。真正0019→0020隔离迁移的全部旧列/备份、五种旧报告状态/操作、raw/修订保持，三索引计划、二次迁移和两次worker重启/旧key零模型通过。阶段7项覆盖重启、实际GET零SQL写入、阶段幂等、两阶段取消、重建前源变、异常回滚恢复和P09冻结兼容。中间80 Lint专项、179相关后端/1符号链接权限跳过、新迁移+批读取4项通过；范围交叠不累加，最终全量随后记录。完整前端164/17文件、P5 Edge5、Rust20/1 ignored、mypy136源文件及Ruff/248格式/前端check/format和契约通过。

**23:19 固定规模实测（Asia/Shanghai）**：原字节harness sha `090dfe9f54ee72ab4bf46bb2f547a5087d842cb7f90726b7333cdf9acb33c964`，串行before/after各新合成库，10,000候选/20,000原文块/2Wiki/30,011目标/每批100，多数候选共用1合法span及19,999新增独立raw chunks分布保持。prepare1.961454→1.706389秒；完整advance856.662931→469.026664秒（-45.25%）、132367→12573 SQL；含prepare总wall858.624385→470.733053秒。显式rebuild13.185584→3.217814秒/40064→232 SQL，单块对账13.424384→3.344553秒；双向各12完整闭包样本，逆向P50/P95 0.861421/1.027968→0.026222/0.030090秒，正向0.886865/1.051412→0.026496/0.031464秒，每调用SQL仍28条，不将少载行优化说成少查询次数。峰RSS315301888→259489792B（300.695→247.469MiB，-17.70%），为OS进程生存期high-water含seed，不是Python分配峰值。

两轮completed/error0/warning0/info1（SOURCE_UNCHECKED）/规则异常0、30016依赖边，单块准确影响1段1文档。after第301批满30011仍running/rebuilding，第302批重新验源重建后completed/finished。阶段累计441.972498秒与端到端470.733053秒区分，validate433.712787秒仍占主要成本；未通过缓存/裁剪减验源。before含小型开发负载/约3秒额外只读快照核对；每版本仅1次完整扫描，不宣称统计显著性或通用SLA，旧430.284749秒/P4两秒目标不冒充本轮成绩。前后163/165运行文件各自稳定，完整events/report/comparison/catalog/等价凭据在本轮.local，旧失败和包保留。

**基准脚本交付**：tests/benchmarks/lint_dependencies.py及README提供复现方式，拒绝既有output和缺失source。测量后仅作Ruff格式/Callable与UTC别名/同步闭包变量绑定修正，规范化AST严格相等；交付版sha `da4686f670286e176b8e89004fe1fcefb45b4cea3ed2018ba0719d1769954c2f`，不冒充原harness字节、不因格式修正重跑大基准。原harness和两轮原始报告sha保持，harness-revision.json保留证据。

**失败与剩余**：首轮契约导出因未设PYTHONPATH失败，补services/engine后重新导出/生成通过；首次mypy本地list缺注解、Ruff遗留unused import和基准风格已修正并复核。首次用Windows PowerShell5.1执行含中文的BOMless build-windows.ps1被解析器拒绝，保留build-windows-ps51-failed.log，改项目当前PowerShell7.6.9执行；该失败未生成新安装器、不冒充PS5.1验收成功。最终完整后端回归、包构建/冻结smoke/指纹、文档安全收尾继续追加。真实P09/P10/P11科学质量、新包原生/目录选择/发布重启、strict/跨模型/平台/干净机/复杂表格公式无OCR/4外部原文不可用仍未闭环；无Computer Use/替用户安装/Commit/Push。

**23:43 最终回归与交付（Asia/Shanghai）**：冻结后完整 `python -m pytest -q` 为 **1185 passed / 3权限相关skipped / 1既有TestClient弃用warning，469.05秒**；不重复累加中间专项。完整React164/17文件、P5真实Edge5、Rust20及构建后显式打包Host1（3.08秒）通过。mypy136运行源、Ruff/249文件格式（含交付基准脚本）、pip check、TypeScript/ESLint/Prettier和OpenAPI/TS生成通过。Python均使用researchgraph-studio绝对解释器，未向base安装依赖。

PowerShell7.6.9构建PyInstaller/Tauri/NSIS成功，保留649.05KB chunk提示。冻结P5和旧smoke成功；P09/P10/P11仅本地合成HTTP/SSE各1、3持久槽，非真实科学验收。首次P5 smoke遗留旧head0019断言导致失败，仅同步测试脚本期望到0020后完整重跑通过，保留smoke-p5-old-schema-failed.log，无运行源变更。Windows PowerShell5.1 `verify-windows-install.ps1 -EnginePath <新引擎> -PdfFixture tests/fixtures/pdf/two-pages.pdf -OutputRoot <本轮隔离目录>` 的System32-only PATH实际17项通过，含双页PDF/来源/阅读支撑/重启，不沿用前轮没传PDF的5项、不算实际安装或干净机。

215运行源LF指纹在冻结/回归/构建前后稳定，基准自身165后端文件实测前后也保持；314资源含引擎与Tauri副本逐字配对，无私人数据资源路径。封存安装器 `.local/releases/p5-lint-performance-20261107/ResearchGraph Studio_0.0.1_x64-setup.exe`，39,054,979字节，SHA256 `afd062f6f700f9081db2f756d37e6b8fa38b5206f06c1f25d7d4488fd4d12198`；引擎 `e56076072856c567b83367fb309b5c33651050fd491472c1aaca57890f539bd7`，schema0020，旧包保留。新包原生升级/扫描和目录发布重启待用户反馈，不重抽已有论文，旧报告可只读重取，未完成可继续。

新增ADR0030与性能报告，同步README、docs00～09、API、导航/续接、progress、AGENTS及开发日志。最终192 Markdown/832本地链接、86当前规范与52归档资产LF大小/hash通过，内部断链0；4份已登记外部原文仍不可用。689源码候选实际内容/私人路径/Gitleaks、git diff --check及空暂存区检查通过。所有最终凭据在.local/lint-performance-20261107，真实模型0/正式库实验0/未Computer Use/替用户安装/Commit/Push；科学质量与原生退出门槛保持未验，未标P5退出全过。

## DEV-0063 — 2026-11-09（Asia/Shanghai）：ResearchGraph Lite P0 重定位

**目标与执行顺序**：用户要求先总结完整工程，再备份推送，确认后建立 Lite 分支，最后只实施 Lite P0。已先阅读 README、docs/README、progress、DEVELOPMENT_LOG、docs/00–09 和 Lite A+B+D 规范包；当前基线写入 `docs/current_project_baseline.md`，区分已实现、部分实现、仅设计、问题与技术债务，并记录当前高 Token 流程和可复用模块。未直接在原分支上重构。

**备份与分支**：检查当前分支、未提交文件、origin 和敏感内容路径；`.env`、密钥、Token、本地数据库、Zotero数据、私人PDF/批注/日志均未加入本轮备份。`check-sensitive.py` 与 Gitleaks（源文件/私人路径及全历史28个提交）通过，未发现泄露。完整工程和基线文档已提交为 `7b45f0dce9168f8b547fca95f06a117e80404198` 并普通推送到 `origin/backup/pre-lite-refactor`；未推送main、未强推。随后从该备份创建 `refactor/researchgraph-lite-p0`，当前分支仅本地工作区改动，未Commit/Push。

**Lite P0 实现**：

- `0021_lite_project_mode.py` 增加 `projects.experience_mode`；旧项目回填 `legacy`，新项目默认 `lite`，显式 legacy 继续可创建，旧幂等响应兼容。
- `0022_lite_usage_and_cache.py` 增加 `lite_token_usage`、`lite_cache_entries` 及项目/任务/论文/版本索引；不删除旧表、旧知识、历史 raw 或图谱。
- `lite_mode.py`、Worker、抽取入口、Zotero批量导入和 Lint 后台维护共同阻断 Lite 的完整抽取、跨论文推理、Query/P5、翻译修复和自动依赖维护；Lite导入强制本地路径。
- Lite PDF/Zotero保存事务复用 PyMuPDF、跨页章节、Chunk/EvidenceSpan，并直接物化 query_index_entries/query_fts；本地读取、正文MATCH和重启保持不创建模型任务。
- `lite_usage.py` 提供只读用量聚合接口和可复用基础：已知/未知调用、缺失 attempts、无法论文归属、Token来源、重试、费用、缓存命中均分别披露。每条实际请求一行，重试另记一行；缓存命中计0新调用/0新Token。缓存身份绑定项目、论文、文献版本、小节、任务、输入、Prompt、Schema、Provider、模型、配置和源hash；来源归属、源hash和不可变响应在读写/失效时重验。
- 桌面 Lite 入口保留Zotero、论文、解析、章节/索引和用量显示；隐藏完整图谱、Query、Lint/Wiki和默认个人来源入口；legacy仍保留原入口。Tauri白名单、OpenAPI/TypeScript、README、docs/API、ADR0031、迁移评估、progress和清单同步。

**实际验证**：

- 后端：最终 `1208 passed / 3 skipped / 1 warning`，456.23秒；警告为既有 Starlette/httpx TestClient 弃用提示。P0/用量/模式专项18 passed，Ruff 256文件、mypy141源文件、pip check和契约生成通过。
- 前端：最终17个测试文件、169 passed（17.82秒）；TypeScript、ESLint、Prettier和生产构建通过，652.72KB chunk提示保留。
- Rust/Tauri：20 passed、1 ignored；cargo fmt通过。用最终0022引擎执行原生Host启动/健康连接/停止/重启1 passed（3.41秒）；Windows PowerShell5.1/System32-only PATH隔离验证17项通过。
- Lite专门验收使用两份不同的合成PDF和匿名Zotero fixture。模型Provider哨兵始终未被调用；PDF解析、章节结构、Chunk/EvidenceSpan、query_index_entries、query_fts正文MATCH和重启保持通过。Lite本地流程实际输入Token=0、输出Token=0、调用=0、重试=0、增量费用=0。
- 最终冻结引擎补充Lite探针：默认创建项目返回`experience_mode=lite`，合成PDF导入成功并保存4个文本块，`GET /lite/usage`返回calls/input/output/total均为0；引擎正常EOF退出。一次过短（少于32字符）测试令牌未计入结果，已清理进程后用合法会话令牌重跑通过。
- `scripts/smoke-engine.py` 的最终冻结引擎回归包含1次离线P07 HTTP/SSE协议stub，用于旧Query兼容路径；它不是Lite本地流程，也不是真实Provider请求。真实模型调用0，正式用户数据库实验写入0。
- 真实用户数据库、Zotero库、私人PDF/批注、真实API Key/Token、真实Provider和NSIS安装器均未读取/调用/安装。隔离库升级和重启证明旧数据结构可保留、legacy历史数据可读；不能表述为用户正式库已经实际升级验收。

**文档与安全**：当前文档专项208份Markdown、868个目标（含4个登记外部路径），仓库内断链0；最终额外包含30份QA原件的检查为238份Markdown、864个仓库内链接目标全部有效，S1–S4四份外部原文仍不可用，未计通过。当前规范86项、archive/v3 52项、用户Lite规范包28项校验通过。最终729个源码候选的内容/私人路径/Gitleaks与全历史28个提交扫描无泄露，diff空白检查通过；远端备份hash再核对为7b45f0d，当前Lite分支未暂存、未提交、未推送。

**未解决问题与下一步**：Lite P0没有实现B论文卡片、A章节导读、D证据问答，也没有把未来Provider调用点接入逐尝试真实usage回调；旧账本缺失Token/费用时保留unknown，不能据零值推断免费。复杂表格/公式、OCR、真实模型质量、真实价格、跨平台/干净机和用户原生安装仍待后续验收。Lite P1只计划做B01六字段论文卡片、受限证据Span、版本化缓存、显式生成/重生成和逐请求Provider用量；本轮已停止，未开始P1。
