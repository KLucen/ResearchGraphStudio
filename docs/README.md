# 文档导航

更新：2026-11-20（Asia/Shanghai）。活跃文档维护 ResearchGraph Lite 的产品规范、运行边界、迁移评估、清理盘点、进度和安全说明。当前保留本地阅读整理、全文精读、PaperCard + LightGraph 与旧 D01/D02；目录树支持三级折叠，旧 PDF 章节结构可自动升级。Alembic head 为 `lite0018`，新模型解析默认5页含1共享页顺序分批（可设2–8页），已校验检查点保存，格式修复需独立授权；600/1800秒为单请求时限。模型优先导入按章节保存正文、公式和表格，并按用户选择生成概览或全文精读及可选逐段中文翻译。桌面支持编辑题名、模型章节和生成内容、逐篇清理旧本地解析/缓存或删除论文；清理保留笔记、模型文档与源文件，操作前创建数据库备份。全文精读已整合大章节阅读状态、目录已读标记和续读定位，小节导读与独立理解状态入口已移除。真实 Provider、论文科学质量和桌面 GUI 原生操作仍待验收。测试与交付读 [进度](progress.md)，管理边界见 [ADR0048](adr/0048-paper-content-management-and-legacy-cleanup.md)，完整 v3/P4/P5 保留在 `backup/pre-lite-refactor`。

## 先读

- [研究内容知识库实施方案](research-knowledge-base-plan-20261120.md)、[ADR0060](adr/0060-durable-research-knowledge-library.md)及[本轮验证](knowledge-library-verification-20261120.md)：K1独立快照、K2带来源建模、K3增量联系和持久汇报已实施，整体交付状态以验证报告为准；K4规模与概念聚合留待后续。当前加性head为`lite0018`。

- [右侧直接分析与章末阅读状态](adr/0059-reading-analysis-and-chapter-end-progress.md)及[本轮验证](reading-sidebar-footer-verification-20261120.md)：去除重复原文卡，分析留在右侧，读完本章后选择阅读状态。

- [精读标记对应卡与就近批注](adr/0058-anchored-reading-annotations.md)及[该次验证](reading-annotations-verification-20261120.md)：原摘录卡/定位方案，显示部分已由ADR0059修正。

- [精读输出与论文工作区修复](adr/0057-reading-output-and-workspace-recovery.md)及[本轮验证](workspace-fixes-verification-20261119.md)：固定槽位生成、准确失败分类、精读标记本地部分恢复、轻量问答目录、统一页签和圆形解析操作。

- [本地/模型阅读统一与显式格式修复决策](adr/0056-unified-reading-from-parser-sources.md)及[本轮验证](unified-reading-verification-20261119.md)。其实现版本为 `lite0014`；后续 `lite0015` 增加独立精读部分恢复记录。

- [根 README](../README.md)
- [Lite A+B+D 规范](researchgraph_lite_ABD/README.md)
- [LightGraph 补充规范](ResearchGraph_Lite_LightGraph_Addendum/README_ADDENDUM.md)
- [双栏精读补充规范](researchgraph_lite_ABD/ResearchGraph_Lite_Section_CloseReading_Bilingual_Annotation.md)
- [双栏精读与状态决策](adr/0041-section-bilingual-close-reading.md)
- [阅读整理层与全文精读决策](adr/0042-paper-reading-document-and-notes.md)
- [全文精读与解析整理验证及安装交付](paper-reading-verification-20261114.md)
- [阅读目录侧栏决策](adr/0043-reading-outline-and-formula-source-boundary.md)
- [阅读侧栏验证与安装交付](reading-sidebar-verification-20261116.md)
- [缺章修复与三级目录树决策](adr/0044-versioned-pdf-chapter-tree.md)
- [三级目录树验证与安装交付](reading-tree-verification-20261116.md)
- [本地阅读存档与并发读取决策](adr/0045-persisted-reading-archive-and-read-transactions.md)
- [本地存档读取验证与安装交付](reading-cache-verification-20261116.md)
- [旧 PDF 章节结构一次性自动升级](adr/0046-auto-upgrade-legacy-pdf-structure.md)
- [论文导入后的模型处理历史设计](adr/0047-import-time-post-processing-plan.md)；当前分页实现见 [ADR0052](adr/0052-resumable-document-batches.md)
- [论文内容管理与旧解析清理](adr/0048-paper-content-management-and-legacy-cleanup.md)
- [导入失败恢复与全文精读章节进度](adr/0049-import-recovery-and-chapter-reading-progress.md)
- [导入失败与章节阅读修复验证及安装包](import-reading-fix-verification-20261118.md)
- [本地与模型双解析及后续重新解析](adr/0050-explicit-local-and-model-parsing.md)
- [双解析验证与安装包](dual-parse-verification-20261118.md)
- [文档超时修复与页面图片输入](adr/0051-document-timeouts-and-visual-pdf-input.md)
- [可续接论文批次、格式修复与边界复核](adr/0052-resumable-document-batches.md)
- [论文分页解析本轮验证](document-batches-verification-20261118.md)
- [边界JSON模式HTTP400与受控恢复](adr/0053-boundary-json-compatibility-recovery.md)及[本轮验证](document-http400-verification-20261118.md)
- [模型章节发布完整性失败后的仅发布恢复](adr/0054-document-publication-integrity-recovery.md)及[安装验证](document-integrity-verification-20261118.md)
- [章节发布外键顺序修复与旧任务受控恢复](adr/0055-document-postprocess-foreign-key-order.md)及[本轮验证](document-fk-order-verification-20261119.md)
- [模型优先导入实现与安装验证](progress.md)
- [旧章节结构自动升级验证](structure-auto-upgrade-verification-20261116.md)
- [公式解析问题与后续方案](formula-parsing-assessment.md)
- [可选公式 OCR 运行时](formula-ocr-setup.md)
- [双栏精读本轮验证与安装交付](section-close-reading-verification-20261114.md)
- [当前项目基线](current_project_baseline.md)
- [Lite 迁移评估](migration/lite_from_v3_assessment.md)
- [清理盘点](lite_cleanup_inventory.md)
- [实际进度](progress.md)
- [模型配置](model-configuration.md)
- [撤下文献翻译的决策](adr/0040-remove-pdf-translation.md)
- [文献翻译撤下说明](pdf-translation.md)
- [安全检查](security-checks.md)
- [Lite P0 决策](adr/0031-researchgraph-lite-p0.md)
- [Lite 清理与联合论文概览决策](adr/0032-lite-clean-engine-and-paper-overview.md)

翻译实现的演进历史保留在 [ADR0036](adr/0036-optional-pdf-translation-bridge.md)、[ADR0037](adr/0037-managed-translation-server.md)、[ADR0038](adr/0038-bundled-translation-and-reading-layout.md) 和 [ADR0039](adr/0039-translation-proxy-request-policy.md)。其翻译相关决策已由 ADR0040 覆盖，不作为当前配置或运行指南；ADR0038 的阅读布局继续保留。

## 文档规则

Lite 文档只描述当前活跃工程和可复现实验。历史完整图谱、跨论文 Query、Lint/Wiki、旧安装包、数据库、日志和原始模型响应不进入活跃目录。真实模型调用、价格和科学质量必须按实际账本记录；没有可用实验条件时继续保留 `unknown`。

设计 Schema、Prompt 和契约测试以 `docs/researchgraph_lite_ABD` 与 `docs/ResearchGraph_Lite_LightGraph_Addendum` 为准。`docs/researchgraph_lite_ABD/schemas/sqlite_reference.sql` 之类参考文件不直接执行，运行数据库由代码初始化和版本检查负责。
