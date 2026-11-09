# 05. Token 控制与验收

## 预算目标
- 联合生成 PaperCard + LightGraph：输入目标8k–10k tokens，输出目标2k–3k tokens。
- 总量目标约8k–16k tokens，属于设计目标而非保证值。
- 节点最多12，边最多16；节点说明保持简短。
- 不生成证据引用、长解释、完整实验条件或独立 Evidence 对象。

## 缓存
缓存键包含 paper_id、PDF hash、input hash、schema version、prompt version、provider/model。同一缓存键二次请求必须命中缓存，模型调用数为0。

## 错误策略
- 网络超时、429、5xx：有限指数退避，沿用项目重试上限。
- Schema 错误：本地记录，默认不自动调用 LLM 修复。
- 用户主动重试：复用相同输入，生成新 usage 记录。
- 部分响应：不保存为 COMPLETED。
- 不允许无限重试或无上限扩大上下文。

## 验收
### 生成
- 选择 Zotero 论文并完成本地解析：LLM调用数为0。
- 点击生成概览：一次调用同时返回 PaperCard + LightGraph。
- 图谱生成不触发旧版 P02/P12/P13。
- 缓存命中：0 次模型调用。

### Schema
- 节点/关系枚举正确。
- 所有边端点存在；无自环、重复边。
- 节点≤12、边≤16。
- 不含 Evidence、citation、page、quote、source_span、confidence、x、y。
- 信息不足时允许空图或少量节点。

### UI
- 论文概览同时显示 PaperCard 和 LightGraph。
- 节点显示中文短标签，详情显示英文原词、中文说明、类型和 basis。
- 节点可拖动，画布可缩放和平移。
- 点击节点/边显示详情。
- 可筛选节点类型、重置布局。
- 布局重新打开后恢复。
- 空图和少节点状态正常显示。

### 语义边界
- UI 显示“AI生成的单篇论文概念图；非独立证据验证”。
- EXPLICIT 不能描述为“已证实”；只表示输入文本明确表达。
- INFERRED 必须显示“AI归纳”。
- 不展示跨论文支持、反驳或冲突关系。

### 兼容性
- 旧版完整知识图谱数据不进入 Lite 数据库；需要回退时从 `backup/pre-lite-refactor` 恢复。
- 新旧 Schema 版本隔离。
- 旧版图谱需要通过 `backup/pre-lite-refactor` 回退访问；当前干净工程不保留历史入口。
- 旧版模块停用不得影响应用启动和 Lite A/B/D 功能。

### 真实测试
至少选取3篇不同类型论文（方法类、实验类、综述/理论类）：
- 记录输入/输出 Token、调用次数、缓存命中。
- 快速检查节点重复、关系合理性、中文标签准确性。
- 对比仅 PaperCard 与 PaperCard+LightGraph 的输出 Token 增量。
- 检查信息不足时模型是否编造节点。
- 不上传私人 PDF 或 API Key 到 GitHub。
