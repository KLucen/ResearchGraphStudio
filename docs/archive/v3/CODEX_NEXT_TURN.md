> 历史 v3 平铺图谱设计，已由当前 [阅读辅助设计](../../README.md)取代；不作为新实现要求。

> 后续开发指令模板：仅在用户明确要求开发时参考，不自动执行。当前文档从 [README](README.md) 进入。

请按当前仓库的 `docs/00_decisions_and_scope.md` 至 `docs/09_reference_implementation_notes.md`、`docs/schemas/`、`docs/prompts/`作为新版设计基线，继续在**当前已开发的P2/P3工程**上增量调整，不重建项目：

1. 审计当前数据与图谱实现，先备份并列出兼容迁移差异。
2. 取消“逐条人工审核后才能建图”的前置流程：章节抽取经Schema、证据ID和去重校验后自动入图，已完成批次立即可见，失败批次支持断点重试。科学关系保留AI候选状态。
3. 保留完整Knowledge Schema，新增轻量GraphProjection：默认只展示Paper/Concept/Method/Claim/ResearchQuestion短中文标签；实验条件、Finding、Evidence与双语全文放到详情面板。
4. Graph Explorer实现Obsidian式力导向布局、自由拖动、固定位置、搜索筛选、邻居高亮、点击详情、布局重启持久化；复用现有图谱组件。
5. 尽量把同一章节多类知识抽取合并为P02一次模型调用，P03/P04按需后台融合/补译；保留原证据锚定和既有P3跨论文条件化推理，NO_DECISION不生成科学关系边。
6. Zotero只读选择论文并直接解析，不长期复制PDF；原文阅读仍回Zotero。清理主页面冗余PDF解析块与介绍性展示。
7. 用真实论文和真实模型验证自动建图、双语详情、证据回查、任务超时续跑和重启数据持久化，保留Mock回归。GitHub提交前严格扫描密钥与私人数据，不要未经授权Push。

完成后报告已修改代码、数据库迁移、真实测试结果和剩余风险；不要自动进入新的Phase。
