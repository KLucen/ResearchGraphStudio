# 下一轮续接：ResearchGraph Lite P0 收尾 / P1 规划

更新：2026-11-09（Asia/Shanghai）。Lite P0 已在 `refactor/researchgraph-lite-p0` 完成代码和回归收尾；本文件用于接续已有工程。产品规范见 00–09 与 [`researchgraph_lite_ABD`](researchgraph_lite_ABD/README.md)，当前状态和验证分母统一见[实施进度](progress.md)。根[协作规则](../AGENTS.md)和用户当前指令优先。

## 开始前

先读根 README、文档导航、progress、开发日志最新条目，再按任务读取 Lite 规范、00–09 和相关 ADR。保留已有完整工程、Lite P0 运行源、迁移、测试和文档；备份分支已推送，当前 Lite 分支未提交/推送，不能将旧 CI 当作当前 Lite 源码验收。

当前 Alembic head `0022`。`0021` 增加 `projects.experience_mode`，`0022` 增加 Lite 用量/缓存表；不要重建工程、重抽已有论文或改写旧 Prompt/hash/raw、历史任务和原科学知识。旧 P5/head0020 作为兼容能力和历史基线保留。

## 已完成，避免重复开发

- Lint 确定性规则、稳定问题生命周期、反向依赖/影响闭包、首次启用后的后台有界增量诊断。
- P09/P10/P11 严格独立传输与统一 Job、最多两持久请求槽位；已有完整 raw 在凭据/网络前重验，显式继续，不自动重发。
- Wiki 稳定页面/段落、不可变草稿/保存、根依赖与安全 Markdown；独立写根、受管发布和检查点恢复。
- note 快照、Annotation.comment、外部 Markdown 独立版本逐份选择；local/model/写根授权分别验证。批注评论是用户观点，批注当前性只指最后显式导入。
- 普通 Query 兼读有效保存 Wiki 及个人根；P5 显式逐份选择不退回“默认全部个人来源”。
- 扫描状态修复：活动报告只读刷新、终态/进度防回退、准备/推进/待继续/完成提示；桌面每批 100 项，API 默认 25、逐调用终验不变。
- Lint性能与阶段：catalog批量读取保持旧目标及hash，检查仅在本批预取来源并逐项终验；依赖重建批量读取/写入，反向查询用递归CTE取完整闭包后按当前权限筛选分页。首次全范围扫描需要依赖重建时先提交末批对象进度，下次推进重验来源后重建；阶段加入幂等key并防回退。新耗时持久保存，旧空记录显示“未记录”。
- `CONDITION_UNKNOWN` 是 info 信息缺口，不推断矛盾或补造条件；`SOURCE_UNCHECKED` 不等于文件丢失或科学错误。
- 问题卡片的只读处理方案按规则/生命周期给出后续步骤；模型需求为三态，展示不调用模型或执行修复。`repair_plan` 不进入冻结工作流、模型输入、hash 或问题指纹，旧任务兼容。条件仅在有据的受控重建/新版本中处理，不提供旧节点直接编辑入口。

实现及失败尝试见[Lint 性能与进度报告](p5-lint-performance-verification-20261107.md)、[ADR0030](adr/0030-lint-performance-and-progress.md)、[P5 报告](p5-verification-20261105.md)、[扫描反馈修复](p5-scan-feedback-verification-20261105.md)和[ADR0029](adr/0029-lint-wiki-workflows-and-managed-publication.md)。参考模板不代替运行 DTO，软件存在不等于真实科学/原生退出验收通过。

## Lite P0 结果与边界

- 新项目默认 Lite；Zotero/PDF/章节/FTS5 本地处理已验证不调用模型，旧项目回填 legacy 并继续可读。
- Worker、抽取入口和 Lint 维护任务阻断 Lite 的完整模型流程；用量汇总接口和版本缓存基础已接入。
- 真实模型调用、正式库实验写入、B 卡片、A 导读、D 问答均为 0/未实现；不要把设计规范或离线协议 stub 当真实模型验收。
- 费用、无 Provider usage 的 Token 和实验条件保持 unknown；不据此推断矛盾或补造条件。

## 下一步与边界

1. Lite P1 先实现 B01 论文卡片：受限输入、六字段、证据 Span 白名单、版本缓存和逐尝试用量。
2. Lite P2/P3 再评估 A01 章节导读与 D01 局部证据问答；没有新的明确预算和真实模型授权，不发起真实调用。
3. 旧 P5 的扫描/处理方案和原生包反馈仍按历史报告记录，不自动恢复为 Lite 默认流程。
4. 迁移、故障注入和新回归继续使用隔离数据；不删除旧数据库、图谱、Zotero 数据或私人材料。

[历史报告索引](archive/reports/README.md)与[完整旧进度](archive/reports/progress-through-20261105.md)保留旧成绩及阶段授权。当前用户若授权提交/上传，再进行实际内容、路径、历史、暂存区和 Gitleaks 检查；私人资料和本地安装器不上传。
