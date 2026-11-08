> 历史 v3 平铺图谱设计，已由当前 [阅读辅助设计](../../README.md)取代；不作为新实现要求。

2026-11-07 整理：以下保留原设计和当时状态；验收报告链接随目录归档更新，本目录 MANIFEST/SHA256SUMS 对应整理后的 LF 字节，不是原包逐字节指纹。

# 文档导航

2026-11-02 起，v3 自动建图与轻量图谱规范是当前设计依据，设计章节直接放在本目录，参考资产按功能分目录存放。它描述目标行为；[实施进度](../../progress.md)、[运行 API](../../api.md)和验收报告描述已经实现、实际验证及尚未完成的内容。用户当前任务和根目录 [AGENTS.md](../../../AGENTS.md)优先；规范包中的下一轮指令和 SQL 不自动执行。

## 核心决议

**Zotero选论文 → 后台解析并锚定证据 → 章节级LLM一次提取多类知识 → 自动校验/去重/入图 → 立即展示可拖动的简洁图谱 → 点击节点加载中英双语详情。**

不再要求逐条人工审核才能显示图谱。保留来源状态、模型推断状态和可选纠错；不把作者观点或模型推理误称为科学真理。完整领域知识Schema保持稳定，单独增加`GraphProjection`投影，不把复杂证据、实验条件和完整文本全塞入前端可视节点。

## 当前设计：v3

| 内容 | 入口 |
| --- | --- |
| 决策、范围与产品流程 | [00 决策](00_decisions_and_scope.md) · [01 产品设计](01_product_design.md) |
| 统一引擎与数据契约 | [02 架构](02_architecture_and_workflows.md) · [03 Schema](03_schema_design.md) |
| 图谱与详情交互 | [04 图谱交互](04_graph_interaction_spec.md) |
| 抽取与模型任务 | [05 Prompt 规范](05_prompt_engineering.md) · [模板目录](prompts/) |
| 兼容迁移与实施顺序 | [06 迁移计划 M0–M6](06_development_migration_plan.md) |
| 目标接口、验证和实现说明 | [07 API/事件](07_api_and_events.md) · [08 验证/安全](08_validation_and_security.md) · [09 实现注记](09_reference_implementation_notes.md) |
| 可运行的参考契约与合成示例 | [Pydantic](schemas/contracts.py) · [JSON Schema](schemas/generated/) · [示例](examples/) · [契约测试](tests/test_contracts.py) |

v3 M0–M6 核心代码已接入；GraphProjection、布局和统一抽取的实际结果见 [v3 验收](../reports/v3-verification.md)。实时点图、模型能力和真实断点续跑见 [本轮优化验收](../reports/refinement-verification-20261102.md)。P4 Query、P5 Lint/Wiki 不在当前开发授权范围。

## 现有工程与实际结果

- [空占位字段与抽取超时验收](../reports/extraction-reliability-verification-20261102.md)、[兼容与超时恢复 ADR](../../adr/0007-extraction-null-markers-and-timeout-adaptation.md)
- [图谱与抽取稳定性验收](../reports/stability-verification-20261102.md)、[局部引用修复 ADR](../../adr/0006-graph-stability-and-local-reference-repair.md)
- [项目使用与构建](../README.md)、[当前进度](../../progress.md)、[开发日志](../../../DEVELOPMENT_LOG.md)
- [已实现 API（Schema 0009）](../../api.md)、[全局模型设置](../../model-configuration.md)、[安全检查](../../security-checks.md)
- [v3 本轮验收](../reports/v3-verification.md)、[v2→v3 审计](../../migration/v2_to_v3_assessment.md)、[v3 迁移 ADR](../../adr/0004-v3-projection-and-unified-extraction.md)
- [P3 本机验收](../reports/phase3-verification.md)、[P1/P2 验证记录](../reports/phase1-verification.md)、[P0 验证记录](../reports/phase0-verification.md)、[环境记录](../reports/environment-check.md)
- [v1→v2 工程评估](../../migration/v1_to_v2_assessment.md)、[统一引擎 ADR](../../adr/0001-unified-knowledge-engine.md)、[全局设置与 P3 ADR](../../adr/0002-phase3-models-and-reasoning.md)

## 版本与归档

[文档整理映射](../../migration/v3-documentation-map.md)记录旧路径去向、Prompt 编号对应和待澄清项；[ADR 0003](../../adr/0003-v3-documentation-baseline.md)记录采用 v3 文档基线的决定。[历史索引](../README.md)保留 v2 规范、早期来源、决策与验收。

运行时 Prompt 仍位于 [services/engine/researchgraph/prompts](../../../services/engine/researchgraph/prompts)，不因文档归档而替换。v3 设计版本不等于应用版本或 Alembic 迁移号。

参考契约在仓库根目录分别运行（两个版本有同名 Python 模块，使用独立进程）：

```powershell
conda run -n researchgraph-studio python -m pytest docs/tests -q
conda run -n researchgraph-studio python -m pytest docs/archive/v2/tests -q
```

这些测试仅验证参考契约，不代替应用回归、真实模型和原生安装验收。

## 文件所有权

| 系统 | 权威数据 | ResearchGraph行为 |
|---|---|---|
| Zotero | 论文元数据、PDF、批注 | 本地API只读；通过附件路径读取，不复制长期PDF |
| ResearchGraph SQLite | Evidence索引、知识对象、关系、模型任务、布局、版本 | 本地事务写入，自动可用，完整审计 |
| Obsidian | 用户个人精读笔记；授权生成目录中的Wiki/综合文档 | 用户私有文件默认只读；生成Markdown时防止覆盖 |

## 环境说明

- Markdown规范可直接用于当前工程；不强制替换既有目录或数据库。
- 参考契约基于 Python 3.11+ / Pydantic v2 / pytest。
- `schemas/generated`通过`schemas/contracts.py`生成，具体供应商的Structured Output支持程度需适配。
- `examples`全部为**虚构数据**，不是真实文献事实。
- 设计支持 Windows 桌面、Tauri+React+FastAPI+SQLite，保留 Mock 自动化测试。

## 关键外部参考

- Zotero Local API: https://www.zotero.org/support/dev/web_api/v3/local_api
- React Flow与d3-force布局: https://reactflow.dev/learn/layouting/layouting
- React Flow 示例: https://reactflow.dev/examples/layout/force-layout （部分示例为Pro许可；仅参考交互思路，不复制受限代码）

## 附属材料

- [v2→v3 变化摘要](CHANGELOG_FROM_V2.md)、[工程规则模板](AGENTS.template.md)、[后续开发指令模板](CODEX_NEXT_TURN.md)；模板仅供明确启动开发时参考。
- [文件清单](MANIFEST.md)与 [SHA-256](SHA256SUMS.txt)按当前 docs 相对路径维护，覆盖本套 v3 规范与参考资产；不代表整个仓库的发布校验。
- [忽略规则示例](.gitignore.sample)作为参考，实际敏感信息检查仍执行[仓库安全规则](../../security-checks.md)。
