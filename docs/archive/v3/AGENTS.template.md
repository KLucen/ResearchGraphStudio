> 历史 v3 平铺图谱设计，已由当前 [阅读辅助设计](../../README.md)取代；不作为新实现要求。

# ResearchGraph Studio — Codex工程规则附录（v3）

> 如果现有仓库已有AGENTS.md，请将适用条目合并进去，不要整体覆盖。

- 本仓库在v2的Phase 2/3基础上迁移到v3，先检查现有代码、工作区及数据迁移。不得重新初始化、删除用户库或重建另一个Knowledge Engine。
- 采用**领域Schema + Extraction Schema + GraphProjection Schema**，禁止为了短标签破坏现有Evidence/Experiment/Condition/Finding完整数据。
- 默认自动建图：程序Schema/证据/重复校验后可直接展示；不要求人工逐条确认。AI跨论文关系仅是候选，未审核不当成科学真理。
- Zotero只读，原PDF不长期复制；Obsidian私人笔记默认只读。Evidence引用必须有效且在本次允许的ID集合中。
- P02同一章节合并多类抽取；后台部分批次成功即可入图，失败断点继续。不得重复调用已提交批次。
- Mock用于持续集成；真实模型结果必须另列测试并记录未验证项；不可把Mock测试说成真实API验证。
- 复用现有React Flow等组件和迁移工具；数据库变更先备份，且保留旧ID和用户审阅历史。
- Git提交及Push前检查实际待提交内容、Git历史、API Key、数据库、PDF、Obsidian私人资料，禁止泄露。无用户授权不得Push。
- 每次迭代运行格式化、schema契约、后端与前端测试，更新`docs/progress.md`并说明真实通过项与阻塞项。
