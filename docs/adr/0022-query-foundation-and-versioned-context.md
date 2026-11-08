# ADR0022：项目级 Query、只读文档适配与可重放证据上下文

日期：2026-11-04（Asia/Shanghai）。状态：P4-Q01～Q04 已实现；Q05～Q08、P5 仍待开发。延续 [ADR0018](0018-query-wiki-and-obsidian-lifecycle.md)，实际结果见[本轮报告](../archive/reports/p4-query-foundation-verification-20261104.md)。

## 范围与继承

用户授权先提交推送 R5，再按顺序开发 Q01～Q04。R5 已提交为 `80552d3`；本轮 Query 增量不因此自动获得再次推送授权。继承来源、结构解析、EvidenceSpan、Knowledge Store 和图谱；不重抽论文、不引入平行科学知识库，也不提前增加问答生成界面、P07/P08 调用或 Wiki 发布。

## 项目级执行与科学变更分开

迁移 0012 只新增 Query 及文档表和可重建 FTS。旧 ModelRun 的单文献非空约束、历史行、原始输出、任务签名和来源 ID 不变；新增 query_runs、query_model_runs 和 query_answer_versions，跨论文执行归属项目和完整 manifest，不能随意挂到第一篇论文。QueryAnswer/QuerySaveCommand 预留 Q05/Q07 严格契约，当前没有执行入口。

KnowledgeStore.audit_event 记录 Query、笔记授权/用途变更/扫描等操作，before/after 为当前科学图 revision，既不新建也不递增 GraphRevision。科学写入仍走原 Store 变更入口。索引和查询记录可以写派生/执行表，论文知识、科学关系、选择及布局保持。

## 文档表达与根来源

QueryDocument 的稳定身份、不可变 DocumentVersion/Passage、逐段 dependencies 与独立 FileBinding 共用同一 SQLite。Store.query() 提供内部登记、基线冲突和幂等检查，供只读适配及后续 Q07/P5 复用；当前没有用户保存回答或 Markdown 发布接口。

内容 valid/stale/invalid/unverified 与文件 not_exported/in_sync/modified/missing/conflict/unavailable 独立。in_sync 只证明磁盘字节匹配已登记基线，不证明未实现的渲染器已确认 Markdown 语义等价。有效内部版本不因文件缺失或外改自动失效；外部新文本不继承旧 manifest。查询返回使用的内部版本和文件状态。

依赖区分 Chunk 精确区间、EvidenceSpan、节点 revision、NoteSnapshot 和其他文档段落。递归穿透到论文证据/个人快照，拒绝跨项目、循环、假 hash/offset/quote、失效来源及未保存草稿。非法/过期段落不给出可供回答的正文；同页其他有效段落仍可读。节点不得经 Wiki 绕过当前候选有效性、隔离或 Mock 排除规则。

原目录授权只允许本地读取；NoteUseGrant 单独控制 local/model 用途，模型外发默认关闭。默认文献查询不读取私人笔记，也不打开最终被排除的个人文档绑定文件。撤销目录会清除外发用途；重新授权不会静默恢复。原始笔记字节、快照解码文本与 hash 一起核对，BOM 兼容，历史保留不能绕过新请求的授权。

## 检索与图谱的职责

query_index_entries/query_fts 是派生索引，不是知识写入入口。刷新从当前权威数据重建或增量同步，包含题名、所有合法候选的原语言/已有中文/别名、原文和表格材料、有效已保存文档及本次用途允许的笔记。FTS5/BM25 与精确短语/术语融合，中文句子补确定性二字片段召回，不调用模型改写或引入向量服务。项目/论文/版本/来源类型/知识类型过滤在最终排名之前执行。

默认排除 Mock、隔离、旧驳回、superseded、失效锚点和旧文献版本；References/页眉页脚保留于来源但不作科学查询证据。画布分页、折叠、隐藏和核心选择不限制检索全集。索引恢复不修改来源，缓存不能代替实时权限与依赖检查。

从节点命中、真实 NodeEvidence 关联的 Chunk 或 Wiki 根依赖发现种子；沿合法论文内关联计算完整支撑闭包，反查共享成员所属结论，不造 KnowledgeUnit 或 EvidenceSpan。科学跨篇扩展只采用种子结论相邻且完整重验的实际科学关系，再补另一端完整支撑，不递归吸入整个 RELATED 连通图。导航边、布局邻近和 NO_DECISION 不作科学依据。保留根、所有合法关联、逐成员路径、条件四态、数值原字符串及不同归属；单位不同不自动换算。

## 版本化上下文与恢复

query-context-1 冻结实际项目/论文版本范围、根来源 hash/解析器、节点 revision/payload、完整合法图路径、证据或只读 Chunk 区间、章节路径、表格网格、文档版本/内容/文件状态、用途授权和请求内短编号映射。外部 PDF 不在本轮读取验证时标 not_checked；已有不可变证据仍可使用，不声称已经核验当前磁盘 PDF。

结构解析缓存须再核对 schema、来源 hash、解析器、每块原文/坐标/章节树及全覆盖。表格 block/cell 引用、行列与跨度均检查；命中一行补回全部相关表头/单元格/注释；缺表头或未恢复完整结构明确 insufficient，不猜列含义。

当前无固定 48K、100 节点、3 跳或任意字符预算。只有明确模型能力才评估容量；本地估算超出时保留完整上下文并返回不足，不截掉必要条件或表头。估算不是供应商 tokenizer 实测，Q05 仍须绑定实际发送协议与时限。

prepare 保存检索/上下文和全局 Reasoning 快照（未配置时本地准备仍可运行），不读取密钥、不调用模型。新快照按 Provider 同一精确端点/模型登记冻结有效容量，保留端点更低上限；未知能力保持未知，不探测、不改用户配置或历史 run。新记录、相同幂等请求、缓存读取和显式 validate 共用重新组装/终验；变更或撤权时拒绝返回旧上下文，保留原执行记录。实际 P07 输出前后调用这套终验属于 Q05，不能把本轮本地测试算作真实回答验收。

Tauri 仅放行精确 Query 方法/项目与运行 UUID/文档参数，以及笔记用途授权；拒绝额外或重复参数、跨形态路径。统一要求单斜杠本地 API 路径，避免宿主拼接 URL 时解释为外部 authority/userinfo。只有合法 search/prepare 请求使用 64KB body 上限，容纳契约允许的 Unicode 问题，其他端点沿用原限制；这不是对证据上下文设置字符预算。

## 验收与后续

本轮覆盖加性迁移与准确备份、重启读取、默认零科学写入、完整支撑与 6 题图扩展对照、文档/权限矩阵、持久解析和关系篡改、表格完整组以及冻结引擎接口。命令、实际数量、失败修复与限制另记验收报告。

下一步为 P4-Q05 有据回答与有界恢复，再 Q06 页面、Q07 显式保存、Q08 真实链路与交付。没有启动 P5；真实 API 回答质量、24 题完整 P4 基准、1万候选/2万正文性能和跨平台/干净机仍须后续实测。
