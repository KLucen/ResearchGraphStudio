# 下一轮开发模板（需要用户明确启动）

最新2026-11-04：R5三项补验收范围内通过，见[新报告](r5-acceptance-verification-20261104.md)。当前模型max配置两篇P13v3各一次成功，38/105槽位、7/20单元；P02/P12新请求0，再继续0。32+2已知错误均留候选不入默认图，5组重复各1代表；新包隔离/旧库升级及用户三项反馈通过。两图partial/有限证据、strict/干净机与S1–S4外部原文限制保留，不追加付费调用。下方旧轮未测描述保留为背景，当前状态以本段及progress为准。

2026-11-04历史续接反馈见[核验记录](history-retry-verification-20261104.md)：用户再次提到的 `Claim.kind_note_unused=null` 是旧P02v2的31/34失败历史，其P02v3后继已34/34成功发布。本轮修前端丢弃返回Job导致的“无响应”，显示实际后继/定位、分页外独立刷新和取消竞争保护；无新增真实请求或正式库写入，不因旧错误重抽已完成文献。原失败/raw保留，非null/其他未知字段仍拒绝，排序pending不冒充完成。最新包与检查以progress为准。

当前R5协议见[ADR0021](adr/0021-keyed-ranking-and-bounded-correction.md)：用户要求软件修复冲突编号/额外字段，不以换模型为前提。新finish计划冻结P13_reading_ranking_v3/reading-ranking-keyed-1，程序固定assessments完整required短编号；模型仅填建议/理由/说明/0–100整数priority，程序降序，同分按冻结输入顺序。Schema/Prompt同源；合法外壳下有效槽位仅私有保留，定向修复未完成输出但保留完整上下文，最多两个持久请求槽位含超时，继续不重发。旧v1/v2计划/raw保持，旧排序失败独立续接并重验原P12谱系，零重复P02/P12。本轮无新增付费调用。

[ADR0020](adr/0020-evidence-aware-core-selection.md)的原文/疑点/数字排版风险、碎片核心门槛和成员caveats继续生效。32条语义无支持及2条上标误读本轮v3复验均不进默认图，未修改原候选；不将此范围外推全局准确率。命令/交付见[progress](progress.md)，历史[R5失败验收](r5-final-verification-20261103.md)不改写，不自动追加模型费用。

当前（2026-11-04）：head 0011，领域 reading-extraction-1.0，入口 paper-reading-v1。结构文档与默认支撑见 [ADR0014](adr/0014-structured-pdf-and-support-graph.md)，本轮语义协议及恢复资格见 [ADR0017](adr/0017-semantic-protocol-and-stage-recovery.md)与ADR0021。新 P02_reading_extract_compact_v4 / reading-semantic-1 只输出 items/links/warnings，程序绑定来源身份；semantic-reading-1 的 P12 仅关系/重复提案，程序组单元，P13v3仅贡献评估槽位。实际命令、真实调用与安装状态查 [progress](progress.md)，不要把设计或代码接入当验收通过。

整合/选择最新策略见 [ADR0015](adr/0015-complete-reading-context.md) 和[实际验收](complete-context-verification-20261103.md)：无固定软件上下文预算，新P12全候选/完整引用证据一窗、新P13全部单元一次；旧窗口/签名/八单元P13组及检查点复用。两实际失败任务15/15、34/34已提取，副本零网络探测到达P13边界；用户安装后继续验证真实选择，不能重抽或把探测写成真实模型通过。

历史 P13 JSON 故障的限定恢复见 [ADR0016](adr/0016-selection-json-syntax-recovery.md)：只补根末 coverage_gaps 完整非空字符串列表遗漏的一个 `]`，不改内容。旧 P13 正常及恢复后均拒绝重复键/NaN/Infinity；“其他阶段不变”只指当轮范围，Schema 不放宽。检查原始响应/审计和完整终验，复用成功 P02/P12/P13 与可重验响应；剩余真实调用和费用单独记录。恢复不等于语义完整，历史 finish_reason 未记录时保持未知。

上述 ADR0015/0016 为旧冻结计划的兼容路径，不把新协议写回旧 Job。新语义三阶段严格解码且无通用修复；新响应与全部缓存状态同终验，protocol/schema/context/evidence 留诊断。仅 response_invalid=true 更新 validation_failed/error/finished_at；可信来源/候选/快照变化为 false 时保留历史 status/error/finished_at，只记复用诊断并停止、不再收费。新语义贡献顺序/排名显式保存，旧字段缺省不改指纹；失败阶段实际调用与供应商 Token 纳入统计，缺历史明细保持未知。Provider 新快照冻结 output_policy，只有精确官方能力登记才strict，兼容JSON是requested，不自动降级收费；真实strict API尚未验收。

当前R1–R4已实施，R5本轮三项补验收范围内通过，软件仍停在P3收尾，未进入P4/P5。阅读根AGENTS、README、progress、最新日志及00–09，后续按用户明确的新指令推进，不重复已完成的真实验收。

完整后续路线现按“图谱组织知识→Query图路径扩展与证据回答→明确保存衍生综合→整理Wiki→授权MD导出，Lint横向诊断”编排。见[生命周期ADR0018](adr/0018-query-wiki-and-obsidian-lifecycle.md)及计划中的Q01–Q08/L01–L04/W01–W05；先有P4最小文档状态/只读适配，P5扩展。若后续用户明确启动P4，从Q01多源scope/修订分离/逐段依赖开始，不把当前计划编写当开发授权，也不重复搭建既有图谱。

下一步（不自动开始）：

1. 检查 git status/diff 与最新提交，保留未提交改动；阅读实际验收报告，避免重复已完成的 R1–R4。
2. 保留本轮已完成的真实P13/已知缺陷/安装反馈证据，不重抽、不复跑付费probe，不把partial改成全文100%。正式库仍不作试验对象。
3. 用户明确要求进入P4时从Q01多源作用域、执行/科学修订分离与依赖身份开始，再按Q02–Q08；未授权不启动Query/Wiki。跨模型、复杂版面、strict或干净机的额外验收需另定明确范围。

真实论文、密钥、运行库和安装器不入源码；未经授权不 Push。使用 Conda researchgraph-studio，优先自动化和用户原生反馈。不要因存在 Query/Wiki 模板就进入下一 Phase。
