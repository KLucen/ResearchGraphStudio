# ResearchGraph Studio 开发流程入口

当前版本为 **[开发计划 v0.4](development-plan-v0.4.md)**，日期 2026-10-27（Asia/Shanghai）。该新文档整合 QA.md 与用户提供的四份补充材料，是当前完整开发方案；计划版本号不表示产品已经完成。

## 当前路线

- v0.1：至少 5 篇论文的 PDF → 证据/主张/条件 → 关系推理 → 人工审核 → 图谱 → 保存/导出闭环。
- v1.0：Zotero 默认只读入口、授权笔记回流、受控 Wiki 与 Ingest/Query/Lint、增量演化、批量实验和正式发布。
- Tauri 2 + React/TypeScript、Conda Python/FastAPI Sidecar、SQLite/FTS5、React Flow；不改用 uv。
- Phase 0–6 逐阶段纵向交付；v0.1 约 5–8 周，完整 v1.0 约 12–19 周，均为范围估算。
- 当前 RG-001–RG-004 已实现并验证；RG-005 的远端构建和独立 runner 安装生命周期验证于 2026-10-29 通过，G0 尚待无开发环境的 Windows 10/11 实机/虚拟机。实际状态以 [Phase 0 记录](phase0-verification.md)为准。
- 开发结束后自动提交并推送 `main`（用户 2026-10-28 授权），跟进 CI 失败；禁止强推覆盖。RG-005 增加独立 runner 的已安装产物验收与可携带 PowerShell 脚本，完整 G0 仍单独记录。

## 配套记录

- [来源与冲突处理](design/source-register.md)
- [需求基线 R01–R34](design/requirements-baseline.md)
- [领域模型](design/domain-model.md)
- [当前技术决策 ADR 0002](decisions/0002-tauri-evidence-workbench.md)与[演化/工具边界 ADR 0003](decisions/0003-controlled-knowledge-evolution.md)
- [实验计划 E1–E6](../experiments/README.md)
- [开发日志](../DEVELOPMENT_LOG.md)
- [历史计划 v0.3](development-plan-v0.3.md)：仅供追溯，不再作为当前排期。
