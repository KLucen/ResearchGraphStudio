# 实施进度

更新：2026-11-01（Asia/Shanghai）。本轮范围为 v1→v2 最小迁移、新版 P1 兼容补全及 P2 Unified Knowledge Engine 最小闭环；停止于 P2。新设计包是主要依据，软件仍为 0.0.1 开发版。P3–P6 未实施。

## 实际实现

- [审计与迁移评估](migration/v1_to_v2_assessment.md)基于代码、旧 API、45 项 Python/16 项 React 基线测试及正式库只读结构审计。保留用户新增设计包与删除旧计划入口的改动。
- [v2 ADR 0001](adr/0001-unified-knowledge-engine.md)：继续 Tauri/React/FastAPI/SQLite/Conda；Paper、AttachmentRevision、Chunk 兼容 Paper、DocumentVersion、paragraph。0005 加性迁移复用旧表/事件，升级前 SQLite 备份。
- P1：PDF/hash/解析版本/来源检查和历史均复用；新 Section/EvidenceSpan；只读 Zotero Local API/AnnotationImporter（高亮、文字、Key、原始位置、未解析锚点）；原生授权目录下 Markdown 枚举、hash、只读历史快照与撤销授权。拒绝 symlink/junction，Windows 文件句柄最终路径再校验，不修改原笔记。
- P2：Concept/Method/Experiment/Condition/Metric/Finding/Claim 的运行 DTO 与节点、证据/依赖、GraphRevision、ModelRun、ReviewDecision。统一 KnowledgeStore 执行 Schema、来源/ID/quote/offset/hash 校验、幂等、事务与事件；缺失条件显式 unknown，来源验证与审核分开。
- P01/P02 有界抽取、离线 Mock/配置式真实 Provider、调用原始记录、失败/超时/取消/重试。真实模型仅文本接口，无 SQL/工具/文件能力；源文本只在单独不可信 user JSON，模板占位段不作为真实输入发出。
- Paper & Reading 连接真实 API：章节、抽取任务、知识卡片、点击卡片显示首条证据/PDF 块高亮、多证据切换、修订/接受/驳回、模型原始结果/修改历史。修复卡片需二次选择证据、旧“无模型”文案及证据按 UUID 排列的问题；证据现在按页/块排序，输入顺序纳入缓存标识。
- 同步 Rust 路由白名单、Schema 0005 health、OpenAPI/TypeScript、Prompt 打包、冻结引擎 smoke 与 PowerShell 安装验收。

## 实际命令与结果

Python 使用 `C:/Users/KLucen/anaconda3/envs/researchgraph-studio/python.exe`，未向 base 安装依赖。日志保存在忽略目录 `.local/`。

| 命令/场景 | 实际结果 |
| --- | --- |
| `pwsh -File scripts/check-phase0.ps1` | 76 Python passed、2 skipped、20 React passed；Ruff/format/mypy/pip check、契约生成、TS/ESLint/Prettier/Web build 通过 |
| `python -m pytest docs/tests -q` | 5 项参考契约通过，参考包不替代运行契约 |
| `cargo fmt --manifest-path apps/desktop/src-tauri/Cargo.toml --check`、`cargo clippy … --locked --all-targets -- -D warnings`、`cargo test … --locked` | fmt/clippy 通过，2 项 Rust 通过；使用用户 `.cargo/bin` |
| `pwsh -File scripts/build-engine.ps1`；`python scripts/smoke-engine.py --executable apps/desktop/src-tauri/binaries/researchgraph-engine-x86_64-pc-windows-msvc.exe` | 冻结引擎、P1 来源/回收/分页与 P2 抽取/证据/审核/重跑/重启通过；子进程 PATH 移除开发工具 |
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-windows-install.ps1 -EnginePath … -PdfFixture tests/fixtures/pdf/two-pages.pdf -OutputRoot .local/v2-ps51-release` | PowerShell 5.1 引擎模式通过；首次无进程级参数因本机策略拒绝，未改全局策略 |
| `pnpm --dir apps/desktop tauri build --debug --no-bundle --config ../../.local/v2-native-config.json` | 独立标识窗口可启动；自造/公开 PDF 验证见下节 |

负例覆盖不存在证据、跨版本/offset/quote/hash、已接受内容重跑不覆盖、新来源保留旧 accepted/证据、缺失条件、转述他人、可疑数值/单位、非法人工 payload 422/事务回滚、revision 冲突、原始模型结果保留、失败/超时/非法 JSON/取消不杀 worker、0001/0004 升级备份与失败回滚。两项 skip 为本机无法创建文件 symlink；既有 Windows junction 安全验证通过。保留 Starlette/httpx 弃用提示及 PyInstaller tzdata hidden-import 提示。

## 原生及数据验证

报告：[隔离原生验收](environment/2026-11-01-v2-phase2-native.json)。生产库只读核对始终为 0001、1 project、1 job，未用其做迁移实验。隔离库 0004→0005，备份中旧 schema/project 可读。

窗口完成旧任务历史 10→13 项、自造 1 页 4 块 PDF 选择器导入、Mock 抽取 8 张卡片、PDF 黄色块高亮、人工修订 v1→v2→接受 v3、展开两条历史。最终重建并重启窗口后，8 张卡片、已接受版本 3、原文高亮与两条审核历史读回通过。原始模型结果与原文保留。另通过选择器导入公开论文 Attention Is All You Need（15 页），Mock 生成 221 张摘录卡片，点击方法卡片显示第 4 页 quote/PDF。这不是科学质量评分；Mock 可能把作者信息等文本也摘成候选。

PDF、数据库与备份只留本机忽略目录。公开 PDF SHA-256：`BDFAA68D8984F0DC02BEACA527B76F207D99B666D31D1DA728EE0728182DF697`。Zotero Local API 本机只读连接可用；真实私人条目/批注不作为提交物或质量验收样本。

## 远端交付与安装验收

代码提交 `e67854d50c0b286d0b511b7b1f92892d682a1f0b` 已普通推送 `main`。[CI 41271020398](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41271020398) 的 `windows` 和 `installed-app` 均成功；后者在另一 runner 用 Windows PowerShell 5.1 实际安装、启动桌面/Sidecar、验证 P1/P2、重启读回及卸载。子进程 PATH 仅含 System32；该 runner 自身有开发工具，不据此宣称干净 Windows 认证。

已下载两份官方 artifact 并逐一核对 GitHub SHA-256；安装器摘要与原始安装报告一致。见 [CI 与产物摘要](environment/2026-11-01-v2-phase2-ci.json)、[原始安装报告](environment/2026-11-01-v2-phase2-installed.json)。本机新验收包 `.local/v2-phase2-acceptance-kit-41271020398.zip` 包含安装器、报告、验证脚本、自造 PDF、隔离原生记录和逐文件校验清单，大小 37,702,773 字节，SHA-256：`9E7E24A14244DCBD0471369CFB26706ECE93EE7944C7884DB6097207DB9DD608`。安装产物、运行库和下载 PDF 未进入源码提交。

## 限制与后续入口

1. 真实模型未配置，没有发送云端论文文本，未验证厂商兼容性和科学抽取质量。Zotero 批注匹配使用 fixture 验证，未导入私人批注验收。
2. identity-v1 原文和块级 bbox 不等于 OCR、逐字框、跨页单一 span 或断词/连字映射。章节为保守标题/页索引，Mock P01 为 other。复杂多栏、公式/图表需专项验收。
3. 人工修订语义字段时不重接证据/依赖；Condition 卡片是当前节点，Claim payload 的 conditions 是原抽取快照。新增 PDF 版本只提示旧知识，不自动改 accepted。完整依赖重算/实体合并不在 P2。
4. 成功 P02 批次保留，后续失败可重试续接；重跑记录新的 P01 调用，成功 P02 复用。取消阻止后续写入，不保证远端服务立即停止生成。
5. Obsidian 只读接入不自动生成个人观点节点；Zotero 先浏览条目，再授权 PDF/关联批注，尚无完整收藏夹选择工作流。
6. 干净 Windows、缺失 WebView2、跨平台和完整安装版人工阅读体验仍待外部验收。G0 用户放行保持有效。
7. S1–S4 四份旧补充材料原登记路径仍不可用，无法核对当前原文/哈希；未改原文，QA 原件与历史登记保留。

P1 兼容补全与 P2 最小闭环已完成本机、原生及远端安装 CI 验收，本轮停止于 P2。P3 建议从 RelationAssertion 候选、Condition 当前节点比较、NO_DECISION 拒绝边、证据依赖与审核开始，先准备授权的真实论文/真实模型基准。本轮不实现 P3、Query、Wiki 或多 Agent 系统。
