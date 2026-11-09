# Codex：同会话接续指令（精简）

按新 `docs/01_product_design.md`、`02_schema_and_api.md`、`03_prompt_spec.md`、`04_progressive_migration.md` 修改现有ResearchGraph，不重建工程、不删除已有P2/P3知识和Zotero数据。

本轮**只做 Lite P0**：先审计当前代码及实际Token/重试日志，出 `docs/migration/lite_from_v3_assessment.md`；新增Lite模式开关并确保“选择Zotero论文→本地解析/章节索引”**默认0次LLM调用**；旧全量抽取、跨论文推理、Lint/Wiki停止默认触发但保持老项目可读。补基础计量/缓存接入及回归测试，验证旧数据不受损。

完成后汇报实测调用量、改动文件、测试和Lite P1入口；不要提前进入P1–P4。Git提交/推送前检查API Key、Token、PDF、私人数据库与日志，未经授权不Push。
