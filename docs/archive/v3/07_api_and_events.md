> 历史 v3 平铺图谱设计，已由当前 [阅读辅助设计](../../README.md)取代；不作为新实现要求。

# 07 — API、事件与数据写入协议

> 示例REST路由是目标契约，Codex应优先与现有FastAPI路由兼容而非重新建重复接口。所有API默认项目作用域、会话鉴权与权限检查。

## 1. 文献与知识构建

| Endpoint（示意） | 功能 | 核心返回 |
|---|---|---|
| `GET /projects/{id}/zotero/collections` | 获取Collection与子分类 | collection_id, children, count |
| `GET /projects/{id}/zotero/collections/{cid}/items` | 获取论文和PDF附件供选择 | item_key, attachments, status |
| `POST /projects/{id}/graph/build-jobs` | 提交选定item+attachment进行图谱构建 | job_id, total_batches?, mode |
| `GET /projects/{id}/graph/build-jobs/{job_id}` | 任务进度/失败批次 | completed, pending, retryable, errors |
| `POST /projects/{id}/graph/build-jobs/{job_id}/resume` | 从未提交批次继续 | job_id, resumed_batch_ids |
| `POST /projects/{id}/graph/build-jobs/{job_id}/cancel` | 取消未完成批次 | durable_committed_batches |
| `GET /projects/{id}/papers/{paper_id}/knowledge-summary` | 论文知识统计和核心内容 | claims, methods, concepts, questions |

`POST /graph/build-jobs`默认可只做解析或立即LLM抽取，以字段`mode=metadata_only|parse_only|parse_and_extract`指定；调用真实LLM前显示预计处理范围及潜在费用。

## 2. 图谱与详情

```http
GET /projects/{id}/graph?scope=paper&scope_id={paper_id}&depth=2&types=Paper,Concept,Method,Claim,ResearchQuestion&include_ai_candidates=true&limit=300
GET /projects/{id}/graph/changes?since_revision=12
GET /projects/{id}/knowledge/{kind}/{node_id}
GET /projects/{id}/graph/edges/{edge_id}
PUT /projects/{id}/graph/layouts/{view_id}
GET /projects/{id}/graph/layouts/{view_id}
```

Graph响应严格符合`GraphProjection`，结构化详细知识由`GET /knowledge/{kind}/{id}`返回。对用户拖动的布局采用单独保存接口，使用乐观并发或更新戳避免多窗口冲突。`graph/changes`只推送已提交变更，不推送未验证的模型原始输出。

## 3. 条件化推理（已有P3兼容）

```http
POST /projects/{id}/reasoning/compare
POST /projects/{id}/reasoning/infer
GET /projects/{id}/reasoning/runs/{run_id}
POST /projects/{id}/knowledge/reviews
```

比较/关系推理只允许有效Claim ID和Evidence ID。`NO_DECISION`返回推理原因并保存run，不创建`CONTRADICTS`等科学边。已接受关系若产生新的AI判断，生成新的候选assertion/revision，而不是直接改旧边。

## 4. 事件协议

- `job.batch_started` {job_id,batch_id,chunk_id,started_at}
- `job.batch_committed` {job_id,batch_id,revision,visible_node_ids,visible_edge_ids}
- `job.batch_failed` {job_id,batch_id,error_code,retryable,attempts}
- `graph.revision_created` {project_id,revision,changed_ids}
- `graph.projection_changed` {view_id,revision,added/updated/removed ids}
- `graph.layout_changed` {view_id,node_id,pinned}（UI事件，**不改知识revision**）
- `knowledge.source_stale` {paper_id,document_version_id,reason}
- `knowledge.review_changed` {target_ref,new_status,revision}

优先复用现有SSE/轮询/事件机制，不能因前端断线丢失任务进度；重连后根据`last_revision`补齐。

## 5. 错误编码示例

| Code | 响应与恢复 |
|---|---|
| `ZOTERO_OFFLINE` | 说明需启动Zotero及开启本地API |
| `ATTACHMENT_NOT_FOUND` | 显示对应附件，需要重新定位 |
| `SOURCE_CHANGED` | 建立新DocumentVersion，旧证据保留 |
| `MODEL_AUTH_FAILED` | 禁止重试；提示检查API Key |
| `MODEL_RATE_LIMITED` | 有界延迟重试，显示限流信息 |
| `MODEL_TIMEOUT` | 保留批次；支持续跑，警告潜在重复费用 |
| `INVALID_STRUCTURED_OUTPUT` | 有界修复重试，不保存未校验内容 |
| `EVIDENCE_REF_INVALID` | 异常队列，不虚构来源 |
| `REVISION_CONFLICT` | 返回最新图谱/布局版本供合并 |

## 6. 安全底线

本机服务只监听回环地址并使用会话令牌；请求中不允许客户端任意指定本地路径读取PDF；Zotero API只读。凭据存储在OS安全存储；日志中不保存完整论文、Authorization、API Key或个人Obsidian内容。上传GitHub前扫描被追踪文件及提交历史敏感信息。
