# ResearchGraph Studio

辅助阅读、理解和整理科研论文的本地桌面产品：从论文证据构建知识图谱，支持原文回查与条件比较。

当前目标采用 **v3.3 阅读辅助设计**：论文直接生成图谱，后台完成候选抽取、论文级整合与自动选择，默认“论文→关键结论→支撑知识”。没有人工审核步骤；原文、证据、模型输出与未选候选保留。入口见[设计导航](docs/README.md)。

**R1–R4 已接入运行软件，R5 部分验收。** 数据库 0010，正常入口 paper-reading-v1；独立 P02 候选抽取、P12 整合、P13 选择和分层图谱已实现。旧任务继续旧协议。两篇真实论文局部链路通过，完整全文与安装体验仍有缺口，未进入 P4 Query/P5 Wiki。见[实际验收](docs/reading-implementation-verification-20261102.md)、[实施进度](docs/progress.md)和[迁移计划](docs/06_development_migration_plan.md)。

技术栈继续使用 Tauri 2 + React/TypeScript、Python/FastAPI Sidecar、SQLite/FTS5；继承 P0–P2 的导入、证据、审核与数据。G0 保留用户放行记录，不等同于干净机实测。历史结果见 [Phase 1](docs/phase1-verification.md)和 [Phase 0](docs/phase0-verification.md)。

开发目录：`C:\Users\KLucen\Desktop\AI科研知识推理平台`。开发远端：[KLucen/ResearchGraphStudio](https://github.com/KLucen/ResearchGraphStudio)，本地 origin 已关联。

## 开发与构建

Windows x64 需要 Node 24.20.0、pnpm 12.5.1、Rust（见 rust-toolchain.toml）、Visual Studio C++ Build Tools/Windows SDK 和 WebView2。Python 优先使用 Anaconda 的独立环境 `researchgraph-studio`，不向 base 安装依赖。

```powershell
# 在项目根目录；创建环境只需执行一次
conda create --name researchgraph-studio --file .\conda-win-64.lock
conda run -n researchgraph-studio python -m pip install --require-hashes -r requirements-win-64.lock
pnpm install --frozen-lockfile

# 静态检查、契约生成、测试及前端构建
pwsh -File .\scripts\check-phase0.ps1

# 构建 Sidecar 并启动原生开发窗口
pwsh -File .\scripts\dev.ps1

# 打包 Windows 当前用户 NSIS 安装器
pwsh -File .\scripts\build-windows.ps1
```

脚本自动定位指定 Conda 环境；Conda 未加入当前 shell 时可设置 `$env:RGS_PYTHON='C:\Users\KLucen\anaconda3\envs\researchgraph-studio\python.exe'`。根目录 `pnpm dev` 启动 Tauri，但要求已构建 Sidecar；`pnpm --dir apps/desktop dev` 只启动 Web UI。修改 Python 后重新运行开发脚本以重建引擎。

安装器输出在 `apps/desktop/src-tauri/target/release/bundle/nsis/`。随包携带 Python 解释器；当前 WebView2 缺失时需要联网安装。默认用户数据在 `%LOCALAPPDATA%\com.researchgraph.studio`，精确路径可在设置页查看。运行数据库、日志和个人材料不进入源码。

`environment.yml` 表达 Conda + pip 依赖意图；`conda-win-64.lock` 锁定基础解释器，`requirements-win-64.lock` 锁定 Python 包及哈希，`pnpm-lock.yaml`、Cargo.lock 和 rust-toolchain.toml 锁定前端与 Rust。优先用上面的两步方式复现 Python 环境。

## 现行软件：论文阅读与抽取

打开项目，选择 Zotero 附件开始建图，或通过原生选择器导入 PDF；论文知识概览展示真实模型生成的知识与抽取进度，点击卡片回查证据。现行版本保留旧编辑/审核接口供历史兼容；新设计流程移除审核操作。来源可定位不等于作者主张已被科学证明。缺失条件保留 unknown。

真实模型在全局“设置与诊断”中管理，供所有项目共用，支持 OpenAI、兼容 API和本地模型；产品入口仅使用真实模型。保存后测试连接并选择 Extraction/Reasoning 角色；API Key 保存在 Windows 凭据管理器，数据库仅保存随机引用。阅读区使用全局 Extraction 模型，明确同意发送当前论文片段后抽取。参数、端点和旧环境变量入口见[模型配置说明](docs/model-configuration.md)。每次抽取保存模型、Prompt 哈希、输入哈希、参数、原始结果和状态；私人笔记不进入输入。默认统一 P02 合并相邻段落、每批一次抽取多类知识并生成中英标签；正常界面不再提供旧基线或 Mock 选择器。失败/取消可在任务历史重试；已提交批次和收到但未提交的合法响应可复用。界面展示批次状态、模型调用与供应商 Token；未知费用明确显示未知。中文缺失允许英文回退，详情可按需补译，补译不修改科学内容。

“文献与阅读”分为导入论文、任务记录、项目文献三个可折叠板块，展开状态按项目保留。导入论文提供同级“本地 PDF / Zotero”入口；任务区显示阶段、批次、失败原因和继续入口；项目文献包含列表、知识概览、来源证据与模型记录。收起不清空当前选择。Obsidian 位于独立“笔记来源”，授权目录仅扫描只读 Markdown 快照，不实现 Wiki 发布。

Zotero 仅使用本机 Local API 读取条目、附件位置与高亮/文字批注，不读写 Zotero SQLite。在“导入论文 → Zotero”连接后选择 Collection、搜索论文、勾选 PDF 或全选本页可用附件，选择“解析后直接建图”后使用全局抽取模型开始处理，默认只读引用原 PDF。真实模型必须先勾选原文发送许可；也可仅解析、稍后抽取。每附件独立显示任务阶段、失败重试和去重结果；原条目与附件关联保留。批注无法唯一匹配时显示“锚点未解析”。

局部关系引用缺失会报告具体路径，并最多执行一次受限引用修复；原始响应、修复响应及关联运行编号均保留。修复不允许改写知识正文、证据、关系类型或已有合法端点，之后仍经过完整校验和 Knowledge Store。旧失败任务可复用此类响应，成功批次不重跑。详见 [图谱与抽取稳定性验收](docs/stability-verification-20261102.md)。

新任务使用 P02_reading_extract / reading-extraction-1.0，目标 6000 字符/48 证据。候选先保存，再由 P12/P13 整合/自动选择；非法关联和无路径支撑自动隔离并标明覆盖缺口，原输出保留。旧 P02 3.2 与旧任务分块签名不变。超时只对未完成根批有限拆分，成功批次和整合选择检查点复用。见[ADR 0009](docs/adr/0009-reading-pipeline-implementation.md)。

0005–0010 为兼容迁移，启动升级前自动备份旧库；0006 增加模型配置，0007 将配置共享到全局并保留旧凭据引用和项目选择记录。0008 增加推理尝试、关系/实体对齐候选、语义审核和 FTS5 索引。0009 新增显示元数据、来源结构边和布局，0010 新增候选质量、单元/成员、选择快照/偏好/检查点旁表；原 Paper/附件修订/文本块及 API 保留。原文使用 identity-v1 字符映射，黄色只表示解析块范围；暂不包含 OCR、精确逐字定位、跨页单一 span、完整章节语义和 Wiki。全局导航可折叠，状态在本机重启后保留。

## 现行软件：跨论文关系与图谱

项目内切换到“图谱与比较”，默认只显示论文和核心结论，点击结论可展开/收起方法、实验、条件、结果、论证和限制。共享节点不复制。拖动联动、双击固定、缩放和平移保持；布局独立保存。按论文筛选后可搜索包括未选内容的全部候选，设置主图显示/隐藏/恢复自动。基于已有候选整合无需重抽 PDF，已有选择切换密度不再调用模型；旧论文未整合时明确显示说明。

打开“Claim Comparator / 实体对齐”复用旧比较流程，选择主张、概念或方法节点，使用关键词和 top-k 检索其他论文候选。Comparator 显示当前条件节点、双方来源状态、原文和 PDF 高亮。选择全局 Reasoning 模型并同意发送双方证据后，主张执行 P04→P05，概念/方法执行 P03。比较器显示条件、证据和模型记录；图谱统一由点与边呈现。正常界面已移除审核控件；模型解释和历史记录仍可查看。

推理写入统一 KnowledgeStore，引用双方已校验证据，保存模型原始输出、条件快照、历史记录和图版本；来源或条件变化后标为失效。NO_DECISION 只有历史记录；实体对齐候选不会物理合并知识。FTS5/BM25 召回不是语义同一性判断。完整增量演化、Query 与 Wiki 尚未实现。

## 设计与过程记录

- [当前文档导航](docs/README.md)、[v3.3 产品设计](docs/01_product_design.md)、[v3.3 实施计划](docs/06_development_migration_plan.md)、[v3.3 Schema](docs/03_schema_design.md)与 [Prompt 规范](docs/05_prompt_engineering.md)
- [文档整理映射与待澄清项](docs/migration/v3-documentation-map.md)、[v3 基线 ADR](docs/adr/0003-v3-documentation-baseline.md)、[历史文档索引](docs/archive/README.md)
- [迁移评估](docs/migration/v1_to_v2_assessment.md)、[统一引擎 ADR](docs/adr/0001-unified-knowledge-engine.md)、[实际进度](docs/progress.md)；[旧开发计划 v0.4](https://github.com/KLucen/ResearchGraphStudio/blob/8e15a9583a7a6becff9d49800af3717eee867121/docs/development-plan-v0.4.md)仅保留历史
- [历史需求基线](docs/design/requirements-baseline.md)、[原文 QA](QA.md)、[补充材料登记](docs/design/source-register.md)
- [早期领域约定](docs/design/domain-model.md)、[Tauri 决策](docs/decisions/0002-tauri-evidence-workbench.md)、[工具/Wiki 决策](docs/decisions/0003-controlled-knowledge-evolution.md)、[来源检查决策](docs/decisions/0005-source-check-relocation.md)、[任务历史与临时工作区决策](docs/decisions/0006-job-history-workspace-recovery.md)
- [已实现 API](docs/api.md)、[Phase 0 验证与待验收项](docs/phase0-verification.md)、[环境报告](docs/environment-check.md)
- [开发日志](DEVELOPMENT_LOG.md)、[实验计划](experiments/README.md)

历史 v3 增量见 [v2→v3 工程审计](docs/migration/v2_to_v3_assessment.md)和 [ADR 0004](docs/adr/0004-v3-projection-and-unified-extraction.md)。DEV-0026 在真实库副本上完成 4 次真实 API 续跑，旧知识不变；新分批规划将原 48 批样本合并为 16 批。完整结果及有限验收范围见 [历史优化验收](docs/refinement-verification-20261102.md)。Query、Lint、Wiki 仍属后续范围，未自动开始。设计版本不等于应用发布版本；当前应用仍为 0.0.1，工期与效果指标均为目标。

Zotero 安装程序为 `D:\Zotero\zotero.exe`，此目录不代表文献数据目录。Zotero 管原文题录，ResearchGraph 管证据/候选/知识版本，Obsidian 管个人笔记及授权 Wiki。MCP 不是前置依赖。

Git HTTPS 不通时，可使用已验证的官方 SSH 443 通道，保持 origin 和全局配置不变：

```powershell
git -c 'url.ssh://git@ssh.github.com:443/.insteadOf=https://github.com/' -c 'core.sshCommand=ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10' fetch origin
```

用户本轮 P3 指令覆盖旧自动推送授权：**未经新的明确授权不得 Push**。任何 Commit/Push 前须检查实际文件内容、暂存差异和 Gitleaks 结果，详见[敏感信息检查](docs/security-checks.md)。现有 CI 会在 Windows 构建后，由另一 runner 安装产物并运行 PowerShell 验收；本轮尚未推送或运行远端 CI。
