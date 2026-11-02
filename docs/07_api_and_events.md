# 07 — 目标 API 与事件（设计 v3.3，与实现差异）

> 实现状态（2026-11-02）：R1–R4 已按本设计接入，R5 部分验收；运行差异及自动隔离规则以 [ADR 0009](adr/0009-reading-pipeline-implementation.md) 和[实际验收](reading-implementation-verification-20261102.md)为准。参考 Schema 仍不等同于运行 API；Query/Wiki 保持后续范围。

已实现接口见 [api.md](api.md) 与生成 OpenAPI。自动构建、候选/选择/偏好和 paper_backbone 已接入；下文目标字段不保证与当前响应逐项同名。实际使用 expected_revision、selection_revision，项目投影 selections 按论文记录版本；未实现单独的 selection_revision 请求固定参数。

## 自动构建

优先扩展现有 `POST /api/v1/knowledge/extract`，新增 pipeline=`paper-reading-v1`、density=`standard`，仍带 document_version_id 和 Idempotency-Key。Zotero/PDF 一键入口串接现有导入/解析任务，再启动此管线，无多余本地导入确认或人工审核步骤。

GET `/api/v1/jobs/{id}` 扩展阶段 indexing/extracting/integrating/selecting/publishing、阶段完成量、已保存候选数、已发布单元数、build_state、coverage_gaps、调用和未知费用。继续复用 retry/cancel；仅未提交阶段执行。模型、Prompt、证据或签名变动创建新构建版本，不能称旧任务续跑。

## 候选与选择

| 目标接口 | 语义 |
| --- | --- |
| GET `/api/v1/papers/{id}/candidates` | 分页/搜索全部候选，含角色、选择原因和来源状态 |
| GET `/api/v1/papers/{id}/knowledge-units` | 固定版本结论及成员引用，不复制内容 |
| GET `/api/v1/papers/{id}/graph-selection` | 活跃 GraphSelection 及完整度 |
| POST `/api/v1/papers/{id}/graph-selection/rebuild` | 基于已保存候选重算密度/策略，不自动重抽 PDF |
| POST `/api/v1/papers/{id}/graph-selection/preferences` | SelectionPreference + expected revision，设置显示偏好 |

不存在新的 review/approve/reject 路由。现有旧 review API 只为历史客户端兼容保留，不在新工作流/UI 中调用。展示偏好既不写审核记录，也不能绕过来源门槛；无效核心提升返回 BLOCKED_CORE_REASON。

## 图谱与详情

扩展现有 `POST /api/v1/projects/{id}/graph/projection`，增加 view=`paper_backbone`、paper_id、selection_revision、expanded_unit_ids、limit/cursor。新响应以 reading-projection-2.0 区分；旧响应适配暂留。默认根上下文及核心结论，展开返回支撑成员，所有边端点闭合。

项目级视图可组合按文献分页的单论文投影与候选科学关系，响应须标每篇选择版本，不能让一个 selection_revision 代表不同论文。光标固定输入、选择和过滤快照，过期/跨项目光标返回冲突并要求重新分页。

继续沿用节点详情/布局接口。布局保存只改 layout revision；搜索命中未选候选可加载独立详情，临时查看不隐式提升为核心。

## 事务事件

| 事件 | 内容与约束 |
| --- | --- |
| candidate.batch_committed | batch、候选 ID、knowledge revision；不是全部主图发布 |
| paper.integration_committed | 输入 revision、单元及关联变化 |
| graph.selection_published | paper/version、knowledge/selection revision、partial/complete、策略及差异 |
| graph.preference_changed | 展示偏好及选择 revision，不表示科学审核 |
| knowledge.source_invalidated | 来源版本和受影响对象，保留旧记录 |
| graph.layout_changed | 仅 UI 状态，不触发知识/Wiki 语义失效 |

候选/阶段检查点与事件同事务，选择快照与活跃指针同事务。事件方案待实现；轮询必须能够完整重建状态，断线不能丢进度。

## 失败与权限

SOURCE_CHANGED、EVIDENCE_REF_INVALID、INTEGRATION_CONTEXT_STALE、UNRESOLVED_MEMBERSHIP、SELECTION_REVISION_CONFLICT、BLOCKED_CORE_REASON、MODEL_TIMEOUT 等分别给恢复方案；技术/来源失败不转为待人工审核。保留最后可用图和已提交知识。日志不得包含真实凭据或整篇私人文本。

所有接口回环鉴权、项目/文献隔离；新增桥接路径需明确方法和正文上限。不可通过任意路径读取 PDF。Query/Wiki 后续仅接收白名单引用；文件导出授权独立，不属于科学审核。
