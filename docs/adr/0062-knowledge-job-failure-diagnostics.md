# ADR0062：知识任务错误分类与只读任务诊断

日期：2026-11-20（Asia/Shanghai）

状态：已实施；实际验证见[本轮报告](../knowledge-diagnostics-verification-20261120.md)。

## 背景

知识建模和联系分析把ProviderError当作ValueError统一归到`KNOWLEDGE_RESPONSE_INVALID`，无法区分请求未取得可校验结果和正文DTO错误。失败路径还丢失实际Provider metadata。用户要求将原因直接显示在任务记录，知识库只保留显式继续入口。

## 决策

- 分类顺序先处理ProviderError，再处理JSON/DTO/来源/预算及未知异常。HTTP服务拒绝、限流、超时、空响应、截断分别有稳定错误码；不得通过字符串拼接原异常或供应商body作为公共诊断。
- `knowledge-diagnostic-1`以`job.result.knowledge_diagnostic`作只读投影，包含code/category/summary、安全issues路径和规则、request_sent/raw_available及action。完整任务列表、项目分页和单条详情一致，叠加现有解析批次恢复投影。
- 新失败在现有私有JSON中保存诊断和实际传输metadata，无数据库迁移。公共投影只提取白名单安全信息，不透传raw、partial_output、来源文本、配置端点、凭据或任意字段名。问题数量有界，剩余数量明确记录。
- 历史通用失败若有完整raw，可本机只读重验并报告格式或来源原因，不发布或改变原记录。历史没有raw或细因时明确“未保留具体原因，无法判定”，不猜测为超时或格式错误。发送槽标记不作为收费证明。
- 任务记录直接显示原因和下一步；知识库不新增原因面板，也不再提示前往知识库查原因。打开/读取任务无模型请求，继续仍走已有显式授权和有限重试，不自动重发。

## 边界

此轮不放宽JSON、字段、引文、来源及输出终验，不增加自动格式修复或自动重发，不修改历史raw或冻结模型。诊断说明机制是否失败，不证明任何科学结论正确。真实模型、用户日常原生和干净机结果与合成回归分开记录。
