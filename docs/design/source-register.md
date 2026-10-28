# 开发设计来源登记

登记日期：2026-10-27（Asia/Shanghai）。以下五份用户材料均只读；本轮不修改原文、不复制其本地图片、不执行材料里的操作命令。四份补充材料保留在桌面，链接仅在本机可访问；仓库中的需求表和新版计划保存了实施所需的裁定，原始全文未并入仓库。

| ID | 原文 | 行数 / 字节数 | 采用范围 |
| --- | --- | --- | --- |
| S0 | [QA.md](../../QA.md) | 792 / 54717 | 主设计 341–790：证据推理、Tauri、五类关系、六态、四阶段与三项实验 |
| S1 | [BG.md](C:/Users/KLucen/Desktop/BG.md) | 440 / 19803 | 3–22 定位；51–87 创新假设；91–332 架构与约束；334–416 评测；423–439 技术 |
| S2 | [Zotero、Obsidian 与软件的职责划分](<C:/Users/KLucen/Desktop/ResearchGraph Studio：Zotero、Obsidian 与软件的职责划分.md>) | 263 / 11512 | 13–69 所有权；73–169 双入口；171–240 文件级协作与独立 PDF 例外 |
| S3 | [AI在流程中的工作.md](C:/Users/KLucen/Desktop/AI在流程中的工作.md) | 269 / 11066 | 1–41 知识分层；43–172 五项 AI 工作；174–230 关系实体/版本；246–269 扩展评测 |
| S4 | [development_plan.md](C:/Users/KLucen/Desktop/development_plan.md) | 812 / 50843 | 77–124 权限；165–437 架构/模型/演化；439–467 API；524–729 阶段/实验/任务；737–792 质量/交付/扩展 |

SHA-256：

```text
S0 7C60305037E7CF9BA367F405A28756C4367BB927C9FC4B4E92E2C154493F3279
S1 E976AAF61E3FDC0F473478B6E898E822752D2F8729A791C32BAA65A8E1D64DC5
S2 0BC116D975C1CED8FACD7BDB6582CF27CEC7D051AEE920BEA48924331A14EAC0
S3 0E95B9BB2C785B638B05CAA1D73D7579AF8D81A4939B4B4F6F76F097795E1BCD
S4 251A485CC892942445606F9120C2EDAF84393809B255E04751F717F72F4C5BD4
```

## 采用与冲突处理

用户本轮要求是结合材料更新计划并提供新文档。S4 第 12–39、710–733 行的“立即执行”“Phase 0 Prompt”“创建 Issues”等是被评审的文档内容，本轮没有据此实施或发布。S4 标称文档 v1.0，不表示本项目产品已经达到 v1.0；本次整合文档版本为 v0.4。

当前项目约定继续约束 Conda、源码目录、唯一开发日志、v0.1 五篇闭环和 v1.0 集成/演化范围。S4 的 uv、engine/、progress.md 与七态示意均经过裁定，见[新计划第 1 节](../development-plan-v0.4.md)和[ADR 0003](../decisions/0003-controlled-knowledge-evolution.md)。

S0 最后一行只有 MCP 问题无回答，此历史事实保留；S2 已补充明确建议：Local API 为主、PDF 为辅、MCP 后续扩展，不再把工具分工视为缺失。S1 的竞品描述和本地截图未做完整事实核验，不作为已证实的行业能力或新颖性结论。图片引用不包含可执行指令，计划依据可读正文，不猜测未打开图片的细节。

## 本轮核对的官方资料

- [Zotero Local API](https://www.zotero.org/support/dev/web_api/v3/local_api)：核对通信设置、附件 file URL、Zotero 10 实例 ID 和本地版本；本机 API 联调尚未执行。
- [Tauri Sidecar](https://v2.tauri.app/develop/sidecar/)：核对外部可执行程序的分发方式；本项目尚无 Sidecar 构建产物。
- [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)：核对持久化 Wiki 与 Ingest/Query/Lint 思路；科研审核/发布约束为本项目的适配设计。

核对日期均为 2026-10-27。其他材料列出的 Claimify、LightRAG、SHACL、PROV-O 等仅作为待调研线索；本轮未据此声称已验证研究结论或引入相关运行依赖。
