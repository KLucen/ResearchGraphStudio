# v2 → v3 工程审计与兼容迁移

日期：2026-11-02（Asia/Shanghai）。范围：M0–M6，继续现有 P2/P3，不进入 P4/P5。审计工作区包含此前未提交实现与文档调整，均已备份，不重置分支。

## 审计证据

- 修改前实跑 Conda Python：104 passed、2 skipped（Windows symlink 权限）；React：28 passed。Starlette/httpx 弃用提示保留。
- `KnowledgeStore.apply` 已执行严格 DTO、证据 ID/quote/offset/hash、局部引用、事务、幂等及事件校验。未审核知识已经可保存，旧 Graph API 没有全局人工接受前置门槛。
- `GraphExplorer.tsx` 直接消费完整 NodeView，仅 claim/concept/method 分页，节点不能拖动，没有持久化布局；详情、证据、模型记录和 Comparator 已存在，可复用。
- `extraction.py` 固定 P01→P02，P02 按 10000 字符分批；KnowledgeOperation 已持久化成功批次，七批恢复已有离线测试。启动会将 received 模型结果标 interrupted，需改善收到结果但尚未提交时的恢复。
- Zotero 只读 API、Collection/PDF 勾选及引用导入已经实现；抽取仍是第二次操作。模型全局配置和 Windows Credential Manager 已存在，密钥不在数据库。
- Alembic head 0008；Paper/AttachmentRevision/Chunk 对应论文/版本/段落，KnowledgeNode 保存完整实验、条件、结果及指标。ModelRun、ReviewDecision、RelationAssertion 和 KnowledgeEvent 均继续使用。

## 备份与数据

本轮修改前把 305 个候选工程文件打包并保存逐文件哈希；通过 SQLite backup API 只读备份本机 4 个应用数据库（0004、0005、0008），不对原库执行实验迁移。旧 P3 验收库含 2 项目、5 论文、1508 知识节点。备份在 `.local/v3-m0/`，不提交论文、数据库、配置或日志。

## 映射与实施顺序

| 对象/能力 | 处理 |
| --- | --- |
| Paper、DocumentVersion、EvidenceSpan、知识 ID | 复用原表和 ID，不重抽旧证据、不删完整领域对象 |
| GraphProjection | 新增读取服务，默认五类短标签节点；完整详情另取，旧图谱 API 保留 |
| 中文显示 | 独立显示元数据，英文回退；已接受内容不被模型静默覆盖 |
| ResearchQuestion | 复用 KnowledgeNode 增加类型，要求论文来源和有效证据 |
| 来源结构边 | 程序校验的同批局部引用，和跨论文 AI 推理关系分开 |
| 布局 | 0009 加性表，项目作用域与乐观并发；拖动不增加知识 revision |
| 抽取 | 增加版本化统一 P02 适配器，转换到现有 KnowledgeStore；旧流程保留为显式基线 |
| 任务恢复 | 冻结模型/Prompt/输入身份，复用已提交批次和已收到合法结果；记录批次错误/尝试/用量 |
| Zotero | 兼容现有导入 API，增加解析后自动抽取选项，默认引用 PDF；真实请求须明确同意 |
| 比较和关系 | 复用现有推理、审核和 stale 校验；NO_DECISION 无科学边，候选虚线 |

## 风险和测试方案

- 旧节点指纹、accepted 状态和审核记录不能因新显示字段发生重写；先在旧库副本验证逐表旧行保持。
- 参考 DTO 缺少部分实验细节，需明确扩展运行契约，不能删去 Experiment/Metric 以迁就展示。
- 中文缺失允许英文回退，并单独标明待补译；禁止伪造翻译或证据。后续优化采用双击固定、详情按钮聚焦、拖动实时联动，见 ADR 0005。
- 跑旧回归及新投影隔离/有界查询、布局冲突与重启、结构边证据、严格抽取、七批失败恢复、原始模型/审核保留等测试。
- 最后构建冻结引擎与 Windows 安装器，使用隔离目录原生复核；真实模型与 Mock 分开记录。四份外部历史原文仍不可用。

本文记录审计与方案，实际 M1–M6 结果持续更新在 `docs/progress.md` 与本轮验收报告。
