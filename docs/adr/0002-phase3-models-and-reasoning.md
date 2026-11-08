# ADR v2-0002：全局模型配置、Zotero 批量导入和条件化关系

> 本页记录已实现的 v2 P3 行为，P03–P05 使用旧编号。v3 目标设计和编号映射见 [ADR 0003](0003-v3-documentation-baseline.md)及[整理索引](../migration/v3-documentation-map.md)；本轮未改写运行 Prompt 或审核历史。

日期：2026-11-01（Asia/Shanghai）。状态：实现已落地；真实 Claim 关系候选→审核→图谱边验收未通过，详见[实际进度](../progress.md)和[Phase 3 本机验收](../archive/reports/phase3-verification.md)。范围截止 P3，用户本轮禁止未经明确授权 Push。

1. 复用 Tauri/React/FastAPI、单任务 worker、SQLite/Alembic、Conda 和 KnowledgeStore，不新增服务。保留工作区两份旧计划删除改动，历史版本由 Git 保留。
2. 先实现全局模型配置和 Zotero 批量导入，运行 P2 回归并交由用户在原生设置页录入真实凭据；真实验证结果与 Mock 测试分开记录。随后完成 P03–P05 与图谱闭环。
3. Windows API Key 使用 Credential Manager Generic Credentials，数据库只保存不可推导密钥的凭据引用。返回 API 不含密钥；参数采用白名单；错误不回显请求和响应头。测试连接发送固定非论文文本。无安全凭据后端的平台拒绝保存密钥。
4. 按用户追加要求，模型配置集中在全局“设置与诊断”，全部项目共用 Extraction/Reasoning 默认模型。0007 兼容迁移保留配置、凭据引用和旧项目角色；旧选择有冲突时不自动指定全局默认。旧项目设置 API 保留为全局配置兼容别名。排队时冻结非敏感配置和凭据引用，记录实际模型、参数、Prompt 与输入 hash。真实调用需要明确同意所选论文/主张的文本传输；私人笔记不参与。
5. Zotero 批量导入只接受被用户勾选的 library/collection/item/attachment ID，服务端核验归属并通过官方 Local API 定位 PDF，不接受客户端任意路径。每个附件独立可重试 Job，复用 PDF hash 去重、版本及 KnowledgeStore 批注入口，不写 Zotero。
6. P03 只生成可审核的实体对齐候选，不自动破坏性合并。P04 使用当前条件节点且保留双方版本快照，unknown 不视作一致或冲突。P05 关系一律 proposed；NO_DECISION 只记录推理，不创建科学关系边。
7. 关系写入/审核经统一 Store，验证两侧 Claim、证据、项目和版本；保存模型记录、前后版本和图 revision。图谱默认有界分页/状态筛选，不将模型关系冒充事实。完整依赖重算和 Query/Wiki 不在本轮。

验证计划：密钥不落库/不回显与 OS 存储 roundtrip、端点变更、连接失败；Zotero 归属/缺附件/重试/重复/取消；P03 非法 ID、P04 未知/指标差异、P05 双侧证据/NO_DECISION；审核冲突/原始模型保留；旧库升级备份、全回归、原生图谱与折叠状态。至少两篇真实论文和真实 LLM 的结果单独登记。真实模型目前对三组 Claim 比较均给出 NO_DECISION，不能视为完成真实关系审核闭环；自造 Mock 关系仅验证审核界面和持久化，不替代科学验收。


## 实施边界与数据兼容

- 0008 加性迁移新增 reasoning_attempts、relation_assertions、entity_alignments、semantic_reviews；建立 knowledge_fts 及文本增删改触发器，回填旧知识。迁移前自动 SQLite 备份，保留原 P0–P2 表、ID、来源、accepted 状态及审核历史。禁止原地降级。
- KnowledgeStore.apply_reasoning / review_semantic 是候选和审核的统一写入口。候选写入、幂等响应、KnowledgeEvent 和 GraphRevision 处于同一事务，模型没有数据库/工具能力。
- 输入必须是同项目不同论文的两条 Claim，或同类型 Concept/Method。候选召回采用有界 FTS5/BM25 OR 词项匹配，可调整 query/top-k；没有伪称已实现向量召回。图谱 UUID keyset 浏览及焦点邻域限制单次大小，科学关系与实体同一性判断分开。
- P04 从当前依赖节点重建条件，Claim.payload.conditions 仅是原始抽取快照。unknown/conflicting 不等于 same/different，not_applicable 要求双方明确；CONTRADICTS 还须任务、指标、单位和主题可比。不同指标不会自动成为矛盾。
- 保存双方完整来源/知识/条件快照及 hash。模型期间变化拒绝入库；读取和审核时发现变化标 stale，不能接受，但仍能驳回。审核只修改候选状态并追加前后快照，不能覆盖原始模型结果。自动依赖重算留待后续阶段。
- 同一模型/端点/参数/Prompt/上下文复用已存推理。P03 的接受仅确认对齐判断，不物理合并实体；NO_DECISION 仍有尝试和事件，不画科学关系边。

## 真实模型输入契约调整

真实兼容模型曾混淆 paragraph ID 与 EvidenceSpan ID、截短 UUID，并在 90 秒时超时；失败被校验拒绝、ModelRun 原始结果保留。没有通过猜测 UUID 修复模型输出。

P01 改为每批最多 8 节，每节给有界代表段落；P02 仍抽取全部原文证据。P02–P05 使用本批 ev0001 等短编号，调用参数中的 input_manifest 保存不可变短编号→正式 ID 映射。DTO 校验后只解析证据字段，不接受其他编号/缩写；入图使用正式 EvidenceSpan，原始输出保留模型所用短编号。Prompt hash 与输入契约版本进入缓存身份。批次保存进度在 JobHistory 显示，后续失败不丢失已有进度。

真实配置由用户在原生设置页录入，后移到全局设置，凭据引用保持。此次实测兼容模型采用 180 秒超时；这不是对所有服务的推荐值或质量保证。供应商、论文与原始结果详情保存在本机隔离验收库，不将私人论文/批注/日志提交。

## 验证与局限

回归包含旧库 FTS 回填、跨项目隔离、陌生实体/证据 ID 拒绝、未知条件/错误冲突拒绝、模型失败/超时/JSON 错误、原始输出保留、审核后重跑不覆盖、条件修订失效与新应用读回。冻结引擎实际执行 P03–P05、审核/图谱、强制退出恢复和失效提示。真实模型结果与 Mock 自动化结果分开报告，见 [实施进度](../progress.md)。不包含 Query、Wiki、物理实体合并、完整后台演化和跨平台凭据后端。
