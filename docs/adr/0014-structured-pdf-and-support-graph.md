# ADR 0014：结构 PDF、章节上下文与默认结论支撑

日期：2026-11-03（Asia/Shanghai）。状态：本轮实施，R5 质量迭代；实际验证以 [progress](../progress.md) 为准，未进入 P4/P5。

## 背景与范围

用户要求先将 PDF 从文本块列表升级为结构文档，跨页建立章节树并尽量保留表格行列、表头和单元格关系；不使用 MarkItDown，不按章节改变抽取重点，也不沿用 6000 字符批次目标。随后让图谱默认显示核心结论的方法、实验、条件等支撑，最后处理实际 `items.1.Claim.kind_note_unused (extra_forbidden)`。保留原论文、来源、知识、证据与模型历史。

## 解析与持久化

1. 复用 PyMuPDF。`pdf-structure-1` 保存原文块及行/字体/bbox、阅读顺序、带父子层级及跨页范围的章节树、可恢复表格的表头/行列/单元格/合并跨度、排除标志和诊断。页码变化不创建章节，表格先识别以免单元格文本成为标题。原块文本及坐标精确保留，阅读排序另用 ordinal。
2. 标题识别综合书签、编号、常见标题及字体/粗体线索；双栏按几何信息恢复顺序。References/Bibliography/参考文献及重复页眉页脚保留原材料但不进入新抽取；参考文献后的 Appendix 可恢复正文。原文保留与不抽取参考文献并不冲突。
3. Alembic 0011 只新增 `document_parses`（文献版本/解析器版本唯一、源 hash、结构 JSON、时间）。不重建来源表，不修改旧 Chunk/EvidenceSpan/知识/ModelRun。新 PDF 按完整原文块建立 span；旧版本补解析先核对源 hash 及全部块的精确文本/坐标，不能匹配即拒绝写入结构，保留旧证据。迁移前一致性备份，实验只用隔离数据。
4. 原 GET `/revisions/{id}/structure` 保留 sections/evidence，新增可空 structured_document。解析产物与领域、选择、布局版本分开。来源离线时已保存证据可读，不为了新结构静默改写旧锚点。

## 章节输入与调用边界

新任务使用独立 `P02_reading_extract_compact_v3`，传输仍 reading-compact-1，领域仍 reading-extraction-1.0。所有章节使用相同候选/证据规则；section_path 和 source_tables 是上下文，不是新的科学类型或证据 ID。只允许引用 supplied allowed_evidence。

`section-context-v1` 优先完整跨页章节，不设 6000 字符/48 证据目标。已知模型上下文不足时，按完整段落/表格上下文组安全拆分并预留 Prompt、Schema 与输出；未知能力不猜固定模型上限。完整单组无法容纳就明确失败，不能裁断表格、丢弃正文或虚报完整。容量估计是保守传输估计，不冒充精确 tokenizer。

章节窗口包含其子节，细分标题保留在 section_path，不因每个子标题单独调用。检测到同表上下文跨章节标签时合并窗口；表格元数据若夹带被排除的材料则只保留于解析产物，不发送给模型，并标记上下文不完整。

计划冻结 parse_artifact_id、输入、Prompt/Schema 和模型参数；旧任务已冻结的计划及成功操作不重排。普通继续需要升级时创建独立兼容续接，保留旧 Job/ModelRun 并复用成功操作及可完整重验响应。响应超时、有限拆分、退避和总时限仍有界；章节输入不保证所有论文一次请求完成，更大输出能力也不保证无超时。整合/选择失败不重复已成功抽取。

## 默认图谱与支撑补全

Paper 仅直接连接自动选择的核心 Claim。其有据的非 Claim 支撑默认显示，包括 Method、Experiment、Condition、Finding、Metric；支撑连接结论分支。`collapsed_unit_ids` 显式收起，已有 `expanded_unit_ids` 保留并优先。共享知识 ID 不复制，收起一个分支不移除另一分支仍需的节点。

投影可从核心沿已有有效有向 SourceAssertion/显式依赖补出旧选择漏列的支撑，不修改旧快照或原知识。仅共享证据不能推出归属或科学关系，不把别的 Claim 当作支撑，不编造实验/条件。UNIT_MEMBER 是导航关系，真实路径仍在详情；缺少有据支撑标缺口。所有边保持端点闭合，分页和布局仍独立。

P02 v3 明确要求对核心结论提取实际存在的必要支撑及合法有向关联，不为填满分支创造内容。来源有效、领域合法与候选保留的门槛不因展示调整降低。

## 限定 Schema 适配

正式库只读备份中定位到一个完整 JSON 失败响应：Claim 的 `kind_note_unused` 值恰为 JSON null，属于额外占位说明，不是截断或缺少正式字段。限定适配只移除 `kind=Claim`、字段名精确为 kind_note_unused、值精确为 null 的组合。紧凑响应将字段路径和规则记入 `ModelRun.parameters.reading_wire.expanded_fields`，其他响应记入 `ModelRun.parameters.reading_envelope_normalization`；原始 raw_output 保持不变。

该字段非 null、出现在其他 kind、其他未知字段或对象扩展仍拒绝。科学数值、条件、归属、证据 ID 不能被适配改写；之后执行完整字段、来源及 Store 验证。该完整响应在隔离副本零新调用重验通过（4 候选、0 关联），原 raw_output 不变，重复 apply 幂等；原知识和模型记录保持。此结果只证明已收到响应可以安全复用，不等于新 Prompt 真实生成、全文科学质量或安装验收通过。

## 限制与验收

无 OCR、公式语义或通用复杂版面保证；无边框/跨页复杂表格依赖 PyMuPDF 能力，失败保存原材料和 warnings，不猜行列。PDF 原块已混合两栏时不凭空拆成新锚点。章节标题与短跨栏标题也可能有歧义，真实全文质量须单独评价。

合成回归覆盖跨页/层级、双栏、表格与合并格、References、原文/坐标保持、容量安全拆分、旧计划不变、默认支撑/共享收起、限定 null 正反例及旧库原列逐行保持。真实渲染、真实模型、冻结引擎、安装和用户反馈分别记录；零网络回放不冒充新模型调用。私人材料/库/响应/日志/安装器不入源码，无新授权不 Push。
