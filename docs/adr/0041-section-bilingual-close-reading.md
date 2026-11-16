# ADR0041：在现有 Lite P2 增量加入双栏精读与个人理解状态

日期：2026-11-14（Asia/Shanghai）

状态：采纳；实现和验收结果以 [progress](../progress.md) 与开发日志为准。

2026-11-14 后续调整：默认范围生成入口、Chunk 直接作为阅读段落及其排序决策由 [ADR0042](0042-paper-reading-document-and-notes.md) 覆盖。本文保留 A02 历史协议、个人状态、A01/A03 与旧成果兼容规则。

## 背景与范围

用户提供 [章节双栏精读补充规范](../researchgraph_lite_ABD/ResearchGraph_Lite_Section_CloseReading_Bilingual_Annotation.md)，要求保留 A01 导读、Zotero、本地 PDF 解析、Section/Span、Provider 与缓存，增量实现 P2-a/b/c。该授权不恢复已撤下的整篇 PDF 翻译服务器，也不恢复完整 Knowledge Engine、跨论文推理、Lint 或 Wiki。

## 决策

- 本地 Chunk ID 作为稳定 paragraph_id，按页面与块顺序读取，并核验 Section/EvidenceSpan 的归属、跨度及原文哈希。英文正文直接来自本地索引，模型不重复输出英文。
- A02 使用 `A02_bilingual_argument_annotation_v1` / `section_reading_analysis.v1`，一次显式范围调用同时生成每段常驻中文译文、五色原文高亮、中文论证批注和当前范围论证摘要。长小节由用户选择范围，不自动递归生成。
- 高亮必须是本段原文的精确子串，重复引用用零起始 occurrence_index 定位；无效高亮或图谱引用单独移除并记录警告。缺段保留已独立核验的结果，显示不完整，仅允许用户手动重试缺失段落。
- ReadingState 和 ConceptUnderstanding 是个人理解状态，与论文事实、LightGraph 的类型/basis 和 AI 派生成果分离。图谱刷新只匹配稳定 ID 与语义指纹，不能可靠匹配的旧状态保留为待重新关联。
- A03 使用 `A03_understanding_check_v1`，仅在用户主动提交短范围复述时运行，保存反馈和 last_check_result，不覆盖用户自评。图谱节点可回到已关联段落或进入现有局部证据问答。
- A01 可显式启用或关闭自适应模式。程序最多选择三项可靠相关状态作为 reader_context，没有可靠关联时保持普通导读。普通旧 A01 的 Prompt/缓存身份兼容；理解状态的点击不使 A02 翻译缓存失效。
- 新表通过 `lite0009` 加性迁移创建，升级前沿用 SQLite 备份机制。不重建已有 Lite 数据，不删除 Zotero 或其他外部文件。

## 调用、缓存和成本边界

打开论文、切换小节、读取已生成结果、标记理解状态、跳转图谱和准备问答均为本地操作。A02/A03 各自需要显式提交；一个已发送任务不因 GET、重启、取消或重复 worker 自动再次发送。缺段重试另建有审计关联的任务。

缓存身份包含来源版本/哈希、段落范围、常驻翻译模式、Schema/Prompt、模型与配置、规范化输入。发送前、响应后及结果读取时重验来源；旧记录保留，来源变化显示过期。所有调用进入既有统一用量账本；Provider 未返回 usage 或费用时保留未知，估算不冒充实测。

建议起始范围约 1,200–2,000 英文估算 Token，4,000–9,000 总 Token 是待真实校准的设计目标。当前轮次仅合成 Provider 验证，不能据此宣称真实文献的成本、译文质量或科学准确率已达标。

## 验证要求

隔离验证段落/原文校验、部分结果和缺段重试、来源与版本失效、重复请求、重启/取消、实际或未知用量、状态隔离、A01 缓存兼容、桌面和窄屏逐段对应、图谱与局部问答联动。构建未签名 Windows 安装包，隔离安装并验证原生宿主启动及本地 PDF 处理零模型调用。正式用户库和 Zotero 数据不作为实验环境。
