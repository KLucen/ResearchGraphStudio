# ADR 0019：支撑路径冻结与发布再验证

日期：2026-11-03（Asia/Shanghai）。状态：已实现；实际验收与交付见 [R5报告](../r5-final-verification-20261103.md)。不进入 P4/P5。

## 问题

候选 snapshot 覆盖知识与来源，但不包含 SourceAssertion 或 KnowledgeDependency。候选内容未变、关联却被删除或改变时，仅比较候选哈希无法证明已保存 KnowledgeUnit 的成员仍有合法支撑路径。P13 等待期间、失败续接以及成功发布检查点复用都存在这一窗口。

## 决策

程序额外生成 `reading-support-context-1`，记录经来源和身份验证的当前候选范围内的关联 ID、项目、端点、类型、证据及依赖三元组。该 manifest 保存在新 finish plan、单元检查点及程序校验输入，不发送给模型，不增加模型需要生成的字段，也不改变模型 wire 或旧请求签名。

`form_units` 复用前核对 manifest、结论集合、每条成员路径和完整可达成员集合。P13 请求前与响应终验核对冻结成员输入及当前合法路径；持久单元在 `form_units` 复用及 Knowledge Store 发布时重新加载并独立再验，成功发布检查点也不能绕过当前路径检查。

路径只能沿来源有效、同文献版本、证据合法且类型允许的显式有向关联，不能穿过另一 Claim，也不能根据共享原文或版面邻近造边。多跳及共享成员保留；旧依赖仅按既有 USES_METHOD、IN_EXPERIMENT、HAS_CONDITION、MEASURES 端点类型规则使用。

可信关系/成员变化返回 `SUPPORT_CONTEXT_CHANGED`。阶段诊断为 context、`response_invalid=false`，保留原始响应及历史 ModelRun status/error/finished_at、已有图谱；停止继续并要求新构建，不自动再次付费。模型自己回错证据或结论编号仍是响应错误，不能与可信输入变化混淆。

## 历史兼容

已有无 manifest 计划与检查点不伪造历史关系快照、不改原指纹。它们只有在当前所有持久路径、完整成员闭包与根集合仍合法时才可复用；有 manifest 后必须与其一致。单元没有支撑成员仍可仅有直接原文依据，不能补造支撑。

数据库 head 0011、领域 reading-extraction-1.0、入口 paper-reading-v1、Prompt/传输协议不变，无迁移、原文改写或人工审核。

## 验证

新增针对性用例覆盖响应中途关联删除、超时后关联变动、缓存/发布再验、跨版本与无效锚点、依赖类型、共享多跳及旧无 manifest 兼容。代码与合成故障验证不能代替真实模型科学质量或干净机安装，结果分别登记。
