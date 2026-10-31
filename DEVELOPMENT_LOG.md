# ResearchGraph Studio 开发日志

用于持续记录真实开发过程，时间统一为 Asia/Shanghai。每轮实质性工作追加一条，不覆盖旧结果；后续发现错误时追加更正或清楚注明修订。提交号、测试结果或实验指标未知时写“未执行/待验证”，不填占位成功结论。

## 项目状态

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
- [开发流程](docs/development-plan.md)
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
2. 新建[完整开发计划 v0.4](docs/development-plan-v0.4.md)，包含产品范围、工具所有权、归属/条件/证据版本、实体合并、AI 流水线、API、UI、Wiki 发布恢复、阶段验收、RG-001–RG-015、评测和剩余依赖。旧计划保留为 docs/development-plan-v0.3.md；docs/development-plan.md 改为当前入口，避免两份活动全文漂移。
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
