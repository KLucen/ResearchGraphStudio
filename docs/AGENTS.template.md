# 工程协作规则附录：阅读辅助知识图谱

> 2026-11-02 实现更新：R1–R4 已接入，R5 部分验收；Schema head 0010，产品入口 paper-reading-v1。P02_reading_extract/P12_reading_integration/P13_reading_selection 为独立运行模板，旧任务模板不改。默认分层图谱、全部候选搜索与显示偏好已可用，无人工审核。下一步限于 R5 全文质量/响应可靠性与安装反馈，未进入 P4/P5。当前正式库 275 条知识在隔离迁移中逐行保持。报告见 docs/reading-implementation-verification-20261102.md（相对仓库根）。

现有根 AGENTS 优先，不整体替换。产品面向科研论文阅读，统一称知识图谱，无特定研究方向前置。

- 一键自动构建：来源→候选→论文整合→核心选择→分层投影。无人工审核、待审队列、接受/驳回步骤。
- 完整保留原文/表格材料/证据定位/模型原输出；未选候选仍检索。Candidate/Unit/Selection 共用 KnowledgeStore。
- Paper 只直接连接核心 Claim，成员按结论展开；来源关系不全部画线，共享节点不复制。
- 按论文类型使用实验/方法/论证/综述结构，不强造实验；质量/归属/条件/限制必须明确。
- 新 validation/source/graph_role 分离；legacy_review_status 只保留旧数据，不新增审核流程；已有人工作品/状态不覆盖。
- 用户显示偏好不是科学审核，不能绕过来源门槛；Query/Wiki 是未来契约，保存/导出授权单独处理。
- 运行 0009/unified-v3.1/P02 3.2 保留旧任务签名。设计参考不直接替换代码；先 R1 备份、迁移和适配再接 Prompt。
- 可按职责重构，不受最少改行限制；不重建工程/第二套知识库，不删除来源或私有材料。
- Conda researchgraph-studio；使用隔离数据做迁移和验收，参考测试不代替真实 API。按用户偏好减少 Computer Use。
- 每轮更新 progress/开发日志，记录实际命令/结果/未测；Commit/Push 前内容扫描，未获新授权不 Push。
