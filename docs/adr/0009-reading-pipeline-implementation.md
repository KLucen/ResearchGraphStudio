# ADR 0009：分层阅读图谱运行实现与自动隔离

- 日期：2026-11-02（Asia/Shanghai）
- 状态：已实施；真实全文质量与安装体验仍待验收
- 依据：[ADR 0008](0008-reading-knowledge-graph.md)、[R1–R5 计划](../06_development_migration_plan.md)

沿用 Paper、AttachmentRevision、Chunk、EvidenceSpan、KnowledgeNode、ModelRun、SourceAssertion 和统一 KnowledgeStore。Alembic 0010 只增加 candidate_metadata、reading_units、reading_members、reading_selections、reading_heads、reading_preferences、reading_checkpoints；迁移前用 SQLite backup，禁止自动降级删除记录。

新任务显式使用 paper-reading-v1，P02_reading_extract 的 reading-extraction-1.0 类型 union 与旧 unified-v3.1 分离。运行协议在 reading_contracts.py，不导入 docs，也不覆盖旧 Prompt/签名。每批仍通过原任务调度、有限超时/退避、分裂账本和原输出缓存，成功候选原子提交。P02 目标 6000 字符/48 证据，不按页机械拆分；大段不截断。表格提及仅保守标记上下文不完整，不声称实现精确表格结构解析。

P12 将候选按最多 8 个根、60 个候选的窗口整合，保留完整候选和必要证据；单次候选 26000 字符、证据 24000 字符、整篇最多 20 窗口。超预算停止或明确 coverage_gaps，不偷偷截断正文。P13 最多 8 个单元一批，48000 字符上限。整合窗口、输入 hash、模型配置、Prompt/Schema 签名冻结；相同输入跨任务复用阶段检查点，失败不重抽全文。选择发布检查候选快照和 expected_revision；偏好/来源变化时拒绝过期发布。

真实模型暴露两类结构问题：合法候选带非法关联端点；整合声明的成员没有根路径。采用保守自动隔离：先严格验证全部候选字段与所有证据白名单；仅丢弃非法 local_ref/端点类型的关联建议，并把索引、原因记录到 ModelRun 参数。原始响应不改，剩余候选经完整 Store 验证。无路径成员不发布，继续保存在候选层；图谱标 partial/覆盖缺口。不猜替代边，不新增人工审核，不放开 extra=forbid。非法字段、伪造证据、跨文献引用仍拒绝批次。

默认投影以当前选择快照生成 Paper→核心 Claim→支撑，导航边明确标记 navigation；科学关系保留 model_inferred 和虚线。多单元共享同一 node ID，收起一个单元不删除其他展开单元的共享支撑；布局版本独立。旧全量投影只作为 API 兼容，正常界面使用 paper_backbone。旧来源不足或尚未整合的论文显示构建说明，不能用旧星形全连接冒充新版主图。

显示/隐藏/恢复自动只更新偏好和新选择；已选快照切换密度复用 P13 建议，不再调用模型。首次从旧候选整合需用户已授权发送候选及必要证据，运行于现有后台任务。候选检索包含未选内容，分页固定候选及选择版本；详情和原模型历史继续可读。历史 review API/数据保留，产品界面移除审核控件。

限制：语义支撑依赖模型判断，不把可定位当科学证明；不同论文类型的结构契约通过不等于质量通过。两篇真实论文只完成局部候选→整合→选择→投影验证，全文任务仍有超时/覆盖问题。科学关系推断仍沿用现有 P3；本轮不实现 P4 Query 或 P5 Wiki。
