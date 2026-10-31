# ResearchGraph Studio 开发流程入口

当前版本为 **[开发计划 v0.4](development-plan-v0.4.md)**，日期 2026-10-27（Asia/Shanghai）。该新文档整合 QA.md 与用户提供的四份补充材料，是当前完整开发方案；计划版本号不表示产品已经完成。

## 当前路线

- v0.1：至少 5 篇论文的 PDF → 证据/主张/条件 → 关系推理 → 人工审核 → 图谱 → 保存/导出闭环。
- v1.0：Zotero 默认只读入口、授权笔记回流、受控 Wiki 与 Ingest/Query/Lint、增量演化、批量实验和正式发布。
- Tauri 2 + React/TypeScript、Conda Python/FastAPI Sidecar、SQLite/FTS5、React Flow；不改用 uv。
- Phase 0–6 逐阶段纵向交付；v0.1 约 5–8 周，完整 v1.0 约 12–19 周，均为范围估算。
- 当前已完成 RG-006 的 PDF 导入、来源/附件修订、来源检查/重新定位、临时工作区回收、真实任务阶段和稳定历史分页增量；G0 按用户决定放行，但未执行的干净机/缺失 WebView2 场景仍保留至发布检查。实际验收见 [Phase 1 记录](phase1-verification.md)。
- 2026-10-30 的来源检查与重新定位见 [ADR 0005](decisions/0005-source-check-relocation.md)；2026-10-31 的任务历史和临时回收规则见 [ADR 0006](decisions/0006-job-history-workspace-recovery.md)。下一步进入 RG-007，完成 Evidence/span 锚定、原页高亮和人工校正；M1 安装版定位验收仍待完成。
- 开发结束后自动提交并推送 `main`（用户 2026-10-28 授权），跟进 CI 失败；禁止强推覆盖。RG-005 增加独立 runner 的已安装产物验收与可携带 PowerShell 脚本，完整 G0 仍单独记录。

## 配套记录

- [来源与冲突处理](design/source-register.md)
- [需求基线 R01–R34](design/requirements-baseline.md)
- [领域模型](design/domain-model.md)
- [当前技术决策 ADR 0002](decisions/0002-tauri-evidence-workbench.md)、[演化/工具边界 ADR 0003](decisions/0003-controlled-knowledge-evolution.md)与[任务历史/临时回收 ADR 0006](decisions/0006-job-history-workspace-recovery.md)
- [实验计划 E1–E6](../experiments/README.md)
- [开发日志](../DEVELOPMENT_LOG.md)
- [历史计划 v0.3](development-plan-v0.3.md)：仅供追溯，不再作为当前排期。
