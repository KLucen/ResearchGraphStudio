# 全局模型配置

2026-11-07（Asia/Shanghai）整理。本文说明当前工作区的配置和调用边界；实际通过与未完成项见[实施进度](progress.md)、[P5 验证](p5-verification-20261105.md)及[扫描反馈验证](p5-scan-feedback-verification-20261105.md)。本次文档整理没有新增模型调用或真实验收。

## 配置入口与角色

打开左侧“设置与诊断”，新增并保存模型配置，点击“测试连接”，再选择全局 Extraction 和 Reasoning 角色。两个角色可使用同一配置，所有项目共用选择。论文阅读构建使用冻结的 Extraction 配置；Query 及 P09/P10/P11 使用冻结的 Reasoning 配置。修改设置只影响后续新任务，不回写已有任务的模型、参数、Prompt、计划或原始响应。

| 服务类型 | 地址与接口要求 |
| --- | --- |
| OpenAI | 固定 `https://api.openai.com/v1`，填写账户实际可用的 Model ID 和 API Key |
| 兼容 API | 填写供应商实际 API 根地址，通常包含 `/v1`，须支持 Chat Completions 文本接口 |
| 本地模型 | 仅允许 loopback 地址，如 `http://127.0.0.1:8000/v1`，使用兼容文本接口 |

正常入口不能选择 Mock；它只用于显式自动化测试和历史兼容。远端必须 HTTPS，URL 不接受凭据、查询参数或片段。当前异步请求不继承系统代理、不跟随重定向。连接测试只发送固定非论文文本并检查 JSON，不能代替论文抽取或科学质量验收。

## 参数、能力与超时

Temperature、Top P 留空时不发送；Reasoning effort 留空通常使用服务默认，已登记腾讯适配按下文角色策略处理。设置页没有手动最大输出 Tokens。程序从同一端点 `/models` 精确匹配 Model ID 读取上下文和输出能力；缺失字段只在准确端点/模型已有登记时使用版本化文档兜底。未知能力使用服务默认，不从别名或上下文长度猜输出上限，也不发送额外生成请求探测能力。

请求使用可信最大输出额度并预留指令、Schema 和输入上下文，不额外固定为 32K/64K。额度不是实际用量；旧手工输出值保留审计，但当前 Provider 不继续发送该手工上限。

新 P02 优先使用 `section-context-v1` 的完整跨页章节，仅实际容量不足时按完整段落/表格组拆分，不设固定字符数或证据条数目标。P12/P13 使用完整候选、证据和合法单元，不设软件固定字符数、候选数或根数量预算。实际模型容量不足时明确停止，不静默删除条件、表头或支撑，不能承诺所有论文一次调用完成。见[Prompt 规范](05_prompt_engineering.md)和[ADR0017](adr/0017-semantic-protocol-and-stage-recovery.md)。

无响应超时默认 90 秒，可设置 5～180 秒。SSE 流式接收另有总时限：配置值的两倍、最多 300 秒，持续输出不能无限延长等待。兼容服务若返回单份 JSON，仍须完整验证。超时、中断或输出截断保留可安全保存的原始/部分响应与诊断；部分 JSON 不能作为合法候选入库。

## 结构化输出与协议

新任务冻结 `output_policy`，记录端点、模型、模式及依据：

- `native_json_schema`：仅代码登记的官方准确端点和模型启用；登记范围见[实现](../services/engine/researchgraph/structured_output.py)，不从模型前缀或同名网关推断。
- `json_object`：兼容模式，`support=requested` 只表示请求 JSON，不保证服务遵守严格 Schema。
- `prompt`：关闭 JSON 模式或已知思考参数冲突时使用，记录原因，输出仍接受本地严格校验。

Schema 转换不能删除领域约束或额外加 null；不支持的关键字调用前失败。拒绝、能力冲突或严格模式错误不会自动付费探测、降级重发。真实 strict API 效果尚未单独验收。

| 流程 | 当前新任务协议 |
| --- | --- |
| P02 | `P02_reading_extract_compact_v4` / `reading-semantic-1`；模型输出 items/links/warnings，程序绑定身份 |
| P12 | `P12_reading_associations_v1`；模型建议关联/重复，程序沿全部已验证路径组单元 |
| P13 | `P13_reading_ranking_v3` / `reading-ranking-keyed-1`；程序固定编号槽位，模型给建议、理由和整数 priority，程序稳定排序 |
| P07 | `query-grounded-semantic-1`；新准备有科学指导用 v3，历史仅有 numeric_layout 用 v2，两者均无保持 v1 |
| P09/P10/P11 | `reading-workflows-1`；分别给语义诊断建议、整理段落及显式目标段落的局部编辑提案 |

参考模板与运行 wire Schema 分开版本化，旧 Prompt/hash/raw/成功检查点不覆盖。模型不生成正式 ID，不执行 SQL、Shell 或文件操作；论文、表格、笔记、批注和外部文档中的指令均为不可信数据。JSON/DTO 通过后仍检查来源、引用白名单、锚点、条件、支撑、当前授权与冻结快照，KnowledgeStore 写入时再验；这些门槛不等于程序证明科学结论正确。

## 继续、恢复与费用

任务历史统一用“继续未完成批次”。继续先重验响应及成功检查点；符合条件的旧任务创建独立后继，原任务与成功内容保留，不原地升级协议或重抽已完成阶段。新响应和缓存共用终验；坏响应与可信来源变化分开记录，后者保留历史成功状态并停止复用，不能用新收费请求掩盖来源变化。历史精确重复/占位处理只适用于已登记形态，不作通用 JSON 修补。见[ADR0017](adr/0017-semantic-protocol-and-stage-recovery.md)。

请求上限按阶段执行：

- P13 每构建最多两个持久槽：首次请求加一次定向格式修复。已发送槽不重发，超时/投递不明计入上限；完整上下文与已通过槽位保留，不能合并冲突建议假装成功。见[ADR0021](adr/0021-keyed-ranking-and-bounded-correction.md)。
- P07 每 Query 最多两个持久槽，失败不自动重发。显式仅恢复已有响应时，先验证冻结 run/raw/plan 与槽位，不可复用则零网络失败，不退回新请求。见[P4 最终验收](archive/reports/p4-final-acceptance-20261105.md)。
- P09/P10/P11 每工作流最多两个持久槽，每次显式动作至多新增一槽，不自动格式重试/降级。完整 raw 先保存后验证，可恢复响应在读取凭据或网络前重验。见[ADR0029](adr/0029-lint-wiki-workflows-and-managed-publication.md)。

调用数和 Token 按持久请求记录及供应商实际返回统计，缓存不虚构新调用。未报告的用量/金额保持未知，超时无用量不代表免费；已结束验收预算不延续到新任务。

## 密钥与资料授权

Windows 使用 Credential Manager Generic Credentials 保存密钥，数据库只存随机引用；API、记录和错误消息不返回密钥。React 不写入 localStorage/查询缓存，提交后清空输入；无安全后端的平台拒绝保存密钥。编辑时留空保留密钥，更换服务类型或 Base URL 后须重新录入。排队任务保留冻结凭据引用；删除配置会删除其各版本 OS 凭据并清除角色选择，已有知识/模型记录保留。数据库备份不含凭据，换机器或 Windows 用户需重新录入，丢失时不回退明文。

模型配置和连接测试不授予来源外发权限。抽取、推理、Query 和 P5 生成仍需满足本次来源范围及发送同意。普通 Query 默认不读私人资料，显式 include_personal 后仍验当前用途权限。

个人资料的 `local` 读取与 `model` 用途独立授权；新 P5 另须逐份选择 note 快照、`Annotation.comment` 和外部 Markdown 版本，授权不会自动选中。用户读取、内部保存和发布需 local，模型发送需 model，发布另验独立写目录；撤销 model 不自动撤销 local，间接个人根与历史段落同样重验。批注评论是用户观点，高亮仅在锚点有效时显示位置，当前性指最后显式导入，不直接读取 Zotero 数据库；外部版本不继承 Wiki 证据或写权限。见[ADR0029](adr/0029-lint-wiki-workflows-and-managed-publication.md)。

确定性 Lint、状态刷新和依赖索引不调用模型。P10/P11 成功后，创建内部草稿、保存 Wiki 和导出 Markdown 仍是独立动作，模型不直接写文件。

## 已登记适配与历史验证

当前代码对准确腾讯 TokenHub HTTPS 端点和 `deepseek-v4.1-flash` / `deepseek-v4.1-flash-1017` 登记上下文 1,000,000、最大输出 393,216 Tokens，端点元数据可用字段优先，其他端点同名模型不套用。新任务 effort 留空时 Extraction 非思考、Reasoning high；显式 none 关闭思考，xhigh/max 映射 max，其他启用档位映射 high。思考模式省略不兼容的 response_format，仍本地完整校验。准确匹配规则见[适配实现](../services/engine/researchgraph/model_adapters.py)。

这是代码登记的能力依据，本轮未重新联网核验供应商承诺。历史接受该额度与零调用恢复见[紧凑输出验证](archive/reports/compact-output-verification-20261102.md)、[ADR0012](adr/0012-compact-extraction-and-model-output-ceiling.md)；早期固定输入目标/较小额度已被后续协议替代，原结果见[抽取可靠性报告](archive/reports/extraction-reliability-verification-20261102.md)和[腾讯恢复报告](archive/reports/tencent-recovery-verification-20261102.md)，不作为当前配置要求。

旧 `RGS_MODEL_BASE_URL` / `RGS_MODEL_NAME` / `RGS_MODEL_API_KEY` 环境入口保留供显式兼容调用；正常界面使用全局角色，API 保留历史 provider=project 兼容值。早期凭据及真实调用见[Phase 3 验收](archive/reports/phase3-verification.md)。当前自动化、真实科学与用户原生反馈分别见[进度](progress.md)，连接测试或历史单批成功不替代整条链路验收。
