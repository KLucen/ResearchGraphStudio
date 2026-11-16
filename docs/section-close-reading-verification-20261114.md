# Lite P2 双栏精读增量验证 · 2026-11-14

## 范围与事实边界

按用户提供的 [双栏精读规范](researchgraph_lite_ABD/ResearchGraph_Lite_Section_CloseReading_Bilingual_Annotation.md) 完成 P2-a/b/c，保留既有 A01、PaperCard + LightGraph、D 问答、Zotero/PDF 本地解析、Section/Span、Provider、缓存和统一用量。不重建 A+B+D，不恢复旧完整 Knowledge Engine、跨论文推理、Lint/Wiki 或已撤下的整篇 PDF 翻译服务器。本轮停止于本阶段。

真实模型调用、真实输入/输出 Token、真实重试和新增收费均为 **0**。测试只用匿名合成 PDF、隔离数据库与 loopback 合成 Provider，不读取正式 Key、用户库、Zotero 库或私人论文。未 Commit/Push，没有运行本轮远端 CI。

## 界面与调用行为

论文阅读工作区 → 章节精读 → 选小节 → “双栏精读 / 小节导读”。双栏精读先读取本地段落；选择范围和页面导航不发送模型。用户勾选本次发送授权并点击生成后，A02 一次生成该范围译文、批注和论证摘要。

- 桌面英文/常驻中文约占 60%，对应中文批注约占 40%；每段放在同一行容器。窄屏按每段英文 → 中文 → 批注堆叠。
- 英文直接读取本地 Chunk/Span。中文始终显示，未生成或失败也保留译文占位；五色高亮只施于英文。React 安全文本渲染，不注入模型 HTML。
- 原文高亮按精确引用及零起始出现序号校验，固定优先级处理重叠。无效高亮或外来图谱 ID 单独移除并给警告。
- 不完整响应保留可独立验证的段落；仅显式重试缺失段，父范围重新打开可从持久化后继恢复译文。子范围摘要不提升为完整父范围摘要。局部范围始终标明范围。
- “我的理解”保存阅读进度、自评、困惑概念和问题。A03 仅主动提交复述后调用，检查建议不覆盖自评或个人笔记。
- LightGraph 使用独立阅读状态圈层，保持节点类型/basis 的原语义颜色。详情可以返回相关章节/段落或准备限定段落的 D 问答。
- A01 保留 quick/standard/deep；可显式启用或关闭自适应，最多发送三项可靠相关状态，不发送历史全文，不强制连调 A01+A02。

## 数据、Prompt 与缓存

Alembic `lite0008 → lite0009` 加性创建四表：`lite_section_close_readings`、`lite_understanding_checks`、`lite_reading_states`、`lite_concept_understanding`。升级沿用自动 SQLite 备份，不 downgrade、重建、清空旧成果或删除外部文件。兼容测试保留原项目和旧表行，备份仍是旧 head，升级后完整性通过。

`Chunk.id` 作为 paragraph_id，按页/块/ID 确定顺序；验证 Section/修订归属、Span 连续完整覆盖、identity normalization、offset、quote/hash。A02 输出覆盖、顺序、重复、范围、高亮均受校验；模型不输出英文全文、正式 ID 或文件操作。

- A02：`A02_bilingual_argument_annotation_v1`，`section_reading_analysis.v1`。
- A03：`A03_understanding_check_v1`，`understanding_check.v1`。
- Prompt 和输出 Schema 的内容哈希、Prompt/Schema 版本、源文版本/hash、段落范围及归一化输入、Provider/模型/Base URL/参数共同约束缓存。
- 当前源、模型、配置或 Prompt 变化时旧成果只读显示 `STALE`，不覆盖到当前原文；没有当前模型配置时仍可读取旧成果。状态点击不使 A02 译文失效。
- 概念状态匹配需要同修订、稳定节点 ID 和语义指纹；不可靠匹配保留为待重新关联。A03 只作用于与所选原文有可靠关联的现有概念。
- 每个 A02/A03 任务一个持久请求槽，原子认领及任务唯一约束；轮询、重复执行、重启、取消不自动重发。原始输出、失败和已返回 usage 保留。相同范围进行中合并或明确冲突，不重复计费。

无 tokenizer 时用公开标明的本地估算预检；A02 原文约 2,000 Token、A03 约 1,200 Token 上限，超过要求用户缩小范围，不自动拆整篇。A02 4,000–9,000 总 Token 只是设计目标，尚未真实标定。累计实际用量与本次缓存读取零新增调用分别显示；Provider 不返回用量或价格时保留未知。

## 实际测试

- 最终后端全量：`python -m pytest -q`，**242 passed / 1 skipped / 1 warning，77.39 秒**。跳过为本机符号链接权限，警告为既有 Starlette/httpx 弃用。专项包含原文/范围/高亮/图谱约束、乱序/缺段/截断/重复键、缓存损坏、模型/Prompt 失效、取消/重启、父范围恢复、理解状态隔离、A01 缓存兼容和迁移备份。
- Python Ruff 通过，**86 文件**格式通过，mypy **56 源文件**通过，`pip check` 通过。
- 前端 TypeScript/ESLint、Prettier 通过；Vitest **7 文件 / 59 passed**。真实 Edge Playwright **6 passed**，包含旧图谱交互两项、独立阅读圈层一项及双栏阅读三项。实际组件截图已查看，验证桌面/窄屏对齐、常驻译文、安全文本、缺段重试、过期旧稿及本地导航。
- 前端生产构建通过：CSS 57.48 KB、JS 562.66 KB；仍有既有单包超过 500 KB 提示。OpenAPI 和 TypeScript 契约已重新导出。
- 源码 sidecar 实际 HTTP/SSE smoke 通过：匿名 PDF 四段，本地处理零模型调用；A02 一次完整输出，缓存额外零调用；A03 一次，自评 `PARTIAL` 保留，原 PDF SHA 保持。

首轮全量为 240 passed / 1 failed / 1 skipped；失败来自撤下翻译测试仍断言旧 head `lite0008`，更新为 `lite0009` 后完成上述全量重跑。最初格式检查发现 smoke 脚本相邻字符串格式，修正后全局格式通过。未把失败尝试计为成功。

每次独立 SSE smoke 的合成 Provider 固定返回输入 23/输出 41/总 64，两次合计 **46/82/128**、缓存命中 1、重试 0，费用未知；这些是夹具计量值，不能当作真实论文成本。A02 专项的另一 Provider 固定 123/234/357，亦非真实消耗，不能与 smoke 值混作生产统计。

## Windows 安装交付

PowerShell 7 执行 `scripts/build-windows.ps1`，使用项目 Conda Python 完成 PyInstaller、前端、Tauri 和 NSIS。打包前后 **56 个 Python 源文件 SHA 保持**，未签名安装包封存在独立目录，没有覆盖旧包。

- 安装器：`.local/releases/lite-section-reading-20261114/ResearchGraph-Studio-Lite-Section-Reading-0.0.1-x64-setup.exe`，**38,480,943 bytes（36.70 MiB）**。
- 安装器 SHA-256：`3E27C040FBF893AEF21B1C1F4C91B36DD0E44F685A5FD0EF934B3DD914C96DB5`。
- 同目录完整 `researchgraph-engine/` 含 `_internal/`；EXE **15,149,749 bytes**，SHA-256 `CCC3CAB1057C2F732B314EBD6F65BA8E8A65CC5A478664A91D738C55EF16E2A3`。不能只复制引擎 EXE。

Windows PowerShell **5.1** 执行 `scripts/verify-windows-install.ps1`，隔离静默安装通过；schema `lite0009`、匿名 PDF 本地解析/索引零模型调用、整篇翻译 API 404 且没有 `translation-runtime`。安装目录的 **263 个 sidecar 文件**与封存文件逐一 SHA 匹配，桌面 EXE 存在。

安装后 `scripts/smoke-engine.py` 通过：本地四段读取、阅读进度保存均零模型。安装后 `scripts/smoke-section-reading.py` 通过：实际 HTTP/SSE 合成 Provider 的 A02 一次、A03 一次、缓存新增零次，模拟用量仍为 **46/82/128**，自评 `PARTIAL` 保留、原 PDF SHA 保持、非 loopback 请求零次。真实模型及收费均零，合成费用仍未知。

Rust fmt/clippy 通过；`RGS_TEST_ENGINE_PATH` 指向最终安装后的引擎，`cargo test --locked -- --include-ignored` 为 **10 passed / 0 ignored，3.03 秒**，包含原生 Host 启动、重启、schema 握手及路由安全。没有启动用户正式数据目录的 GUI，不把宿主测试表述为完整 GUI 或干净机验收。

隔离验证材料位于 `.local/verify/lite-section-reading-20261114/`，均被 Git 忽略。最终源码内容/私人路径规则与 Gitleaks **284 文件**通过，**17 个改动文档 / 83 个本地链接**无缺失，`git diff --check` 通过，暂存区为空。没有提交、上传凭据、私人论文、数据库、运行日志或安装器；没有 Commit/Push。

## 剩余问题

真实论文译文忠实度、论证批注的语义质量、真实 Token 分布及费用尚未验收；需要另行明确样例和预算。PDF 解析无 OCR，图表/公式缺失如实提示，不由模型补造。自动化浏览器、隔离安装和原生宿主验证不能替代干净机或用户正式库 GUI 验收。没有提前开发其他阶段。
