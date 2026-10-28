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
