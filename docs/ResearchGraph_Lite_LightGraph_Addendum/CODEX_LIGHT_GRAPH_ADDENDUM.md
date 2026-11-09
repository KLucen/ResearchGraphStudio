# 给 Codex：ResearchGraph Lite 轻量知识图谱补充开发指令

本指令是既定 ResearchGraph Lite A+B+D 方案的补充，不重复重建 Lite 产品，也不改变 A（章节导读）和 D（按需问答）的既有设计。

## 执行顺序

### 0. 确认 Git / 备份进度
- 检查当前分支、工作区、远程仓库，以及此前约定的 `backup/pre-lite-refactor` 和 `refactor/researchgraph-lite-p0` 是否存在。
- 如果项目总结、敏感信息检查和备份推送尚未完成，先按此前指令完成：总结当前项目、审查敏感文件与 Git 历史、建立并推送备份分支，再创建/切换 Lite 重构分支。
- 如果分支已正确存在，直接复用，不要重复创建、覆盖或强制推送。
- 不得 `git push --force`；不得盲目 `git add .`。真实 API Key、Token、`.env`、本地数据库、私人 PDF、批注、日志不得上传。发现疑似泄露或远程状态不确定时停止并报告。

### 1. 阅读并合并本补充规范
先阅读本包 README、产品规格、Schema、Prompt、存储/API和验收文档。原 ResearchGraph Lite A+B+D 规范继续有效。本补充只扩展论文概览 B，不重做 A、D。

### 2. 产品行为
将论文概览改为 **PaperCard + 单篇 LightGraph**：
- 用户主动点击“生成论文概览”时，使用一次 LLM 调用同时生成卡片与图谱。
- 不要为图谱再发起第二次模型调用。
- 默认每篇 6–12 个节点、4–16 条关系；信息不足时允许更少或空图，不得编造。
- 节点类型仅使用 `RESEARCH_QUESTION`、`CONCEPT`、`METHOD`、`CONTRIBUTION`、`FINDING`。
- 关系类型仅使用 `INVESTIGATES`、`USES`、`ANALYZES`、`YIELDS`、`CONTRIBUTES_TO`、`RELATED_TO`。
- 节点显示短中文名称，详情中显示英文原词（若原文存在）和中文说明。
- 不生成 Evidence 节点、段落级引用、页码、引文片段、证据链或置信度分数。
- 节点和关系保留 `basis`（`EXPLICIT` / `INFERRED`），区分论文明确表达与模型归纳；UI 明确显示“论文明确提及 / AI归纳关系”。
- 图谱仅表示单篇论文内部的概念导航，不做跨论文合并、支持/反驳判断或科研结论验证。

### 3. 实现边界
- 复用现有 PDF 本地解析、Model Provider、PaperCard 能力和图谱组件。
- 旧版完整科研图谱、Evidence、Claim、Condition、跨论文推理代码和数据不进入当前 Lite 工程；完整旧工程已在 `backup/pre-lite-refactor` 保留回退点，不复制到 Lite 数据库。
- 新增独立 `paper_overview_graph_v1` 契约；不要把轻量节点写入旧版完整科研图谱表，除非已有架构明确支持版本隔离。
- 图谱布局坐标由前端/布局算法生成并单独持久化，不能让 LLM 生成 x/y。
- 先做确定性 Schema 校验、ID 重映射、去重和边端点校验；不要为普通校验失败再调用 LLM 修复。
- 结构化输出优先使用 Provider 支持的 JSON Schema / structured output；不支持时使用 JSON mode 或严格 JSON 提示并在本地解析。
- 网络错误按有限重试策略恢复；Schema 不合法默认标记失败并允许用户手动重试，不做无限修复循环。

### 4. Token 控制
- 论文卡片与图谱共享一次概览请求。
- 概览输入只使用本地抽取的有限文本：标题、摘要、引言末段、方法概览、结果概览、结论；按优先级截断。
- 默认概览输入上限建议 8k–10k tokens，输出上限建议 2k–3k tokens。
- 目标：卡片 + 图谱合计约 8k–16k 总 Token，作为预算目标而非保证值。
- 缓存键包含 PDF 内容哈希、规范化输入哈希、Prompt 版本、Schema 版本和模型标识。
- 缓存命中时不得调用 LLM。

### 5. 交互
- 在论文概览区域增加图谱面板。
- 支持力导向布局、拖动节点、缩放平移、适配画布。
- 点击节点打开详情：中文名称、英文原词、类型、中文说明、basis。
- 点击边显示关系中文释义及 basis。
- 支持按节点类型筛选、局部高亮、重置布局。
- 布局位置单独保存；重新打开论文时恢复。
- 节点过少时显示空状态，不报错。

### 6. 本轮施工边界
- 如果当前正在 Lite P0：本轮只把本补充规范纳入设计与迁移文档，确保 P0 不启动旧版图谱流程；不要提前实现图谱 UI。
- 轻量图谱作为 Lite P1 的论文概览扩展，与 PaperCard 同步实现。
- 若 Lite P0 已完成，则按项目现有进度将图谱纳入 PaperCard 阶段，不重复执行已验收任务。

## 验收
1. 选择 Zotero 论文并完成本地解析：LLM 调用数为 0。
2. 用户主动生成概览：恰好一次模型调用同时返回 PaperCard + LightGraph（不计 API 层网络重试）。
3. 缓存命中：0 次模型调用。
4. 图谱通过 Schema、重复项、端点、类型约束校验。
5. 图谱不含 Evidence、citation、page、quote、source_span 等证据溯源字段。
6. 节点可拖动、缩放、点击查看详情，布局重开后恢复。
7. 旧版完整知识图谱数据和代码只在 `backup/pre-lite-refactor` 对应的旧工程中可用；当前 Lite 工程不加载旧业务。
8. 记录真实 input/output tokens、调用次数、重试次数和费用；不得用估算值冒充实测值。

完成后汇报修改文件、迁移方式、测试结果、真实 Token 统计和未解决问题。未经用户明确授权，不要把新分支合并到 main。
