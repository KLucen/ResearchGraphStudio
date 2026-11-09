# 04 Codex渐进式迁移计划（基于已施工的P0–P3工程）

> 这是历史迁移计划与验收参考，不是当前施工顺序。当前工程沿用 Tauri/React/FastAPI 基础结构，但活跃运行集已清理为 Lite；旧项目、旧缓存和旧图谱通过 `backup/pre-lite-refactor` 回退，不加载或迁移到 Lite 数据库。

## 0. 迁移策略与风险控制

- Lite 项目使用独立 `researchgraph-lite.sqlite3` 和 `lite0001` 空 Schema；来源解析、章节和索引表按 Lite 结构初始化，不把旧 Graph 模式放入活跃运行集。
- 复用 Paper/DocumentVersion/Section/EvidenceSpan 的本地解析能力和稳定来源身份，但不迁移旧业务表、旧缓存或旧模型响应。
- **Lite 干净工程不携带旧完整 Schema、P02/P12/P13 等实现**；旧工程在 `backup/pre-lite-refactor` 保留回退点，Lite 数据库不迁移旧数据。
- `read/parse/index` 不产生LLM任务；通过服务端能力边界和测试强制落实。
- 建立 Lite 数据库前保留旧工程备份和 schema 版本记录；Lite 初始化拒绝把旧数据库升级成 Lite 数据库，不在用户旧数据上做实验。
- 不改动Zotero条目、原始PDF、Obsidian私人笔记；沿用现有安全密钥与Sidecar生命周期处理。
- 每步使用可运行、可演示的纵向闭环；Mock测试与真实API测试分离。

## Lite P0 — 审计、测量与模式开关（首轮，优先）

**目标**：不影响旧功能的前提下证明新默认工作流不会消耗模型Token。

任务：
1. 审计旧任务图：识别“选择/解析文献”阶段隐式触发 P02/P12/P13、Wiki、Lint、全量GraphRAG 的调用位置和队列。
2. 验证真实日志里的 `input_tokens/output_tokens`、重试、模型、每批时延；若不存在，先建立统一计量表，区分估算与Provider原始usage。
3. 增加 `experience_mode=lite`（新项目默认）并禁用旧自动任务触发；旧任务和已有图谱不迁移到 Lite，历史访问通过备份工程完成。
4. 给出 `docs/migration/lite_from_v3_assessment.md`：旧表复用、API兼容、开关位置、已测Token基线与风险。
5. 修改前端默认入口：Zotero选论文→本地解析章节/FTS5→Lite工作台；不要求先建图。

**验收**：对至少2篇样例PDF选择、解析和建立章节索引，MockProvider调用数为0；已有图谱、文献和笔记无变化；真实数据未自动发往云端。

## Lite P1 — B 极简卡片 + Section基础

**目标**：单篇论文第一次用户主动请求后得到可回查的六字段卡片。

任务：
1. 确认现有本地章节索引可用；处理多附件选择、扫描PDF解析不足、页码/Span版本。
2. 新增 `PaperCardDraft` 契约、B01模板、卡片输入选择器、EvidenceRef白名单验证。
3. 增加持久化缓存、ModelRun/TokenUsage写入；前端“生成卡片/查看原文/重新生成”操作与状态。
4. 卡片需要中文解释，保留专业英文词汇、每字段证据位置；缺失信息状态`not_found`。
5. 实现生成中与失败重试的 single-flight/幂等，保留原结果。

**验收**：一篇英文科研论文成功生成卡片；缓存二次打开0调用；找不到的字段不被补造；真实模型Token/引用验证记录。

## Lite P2 — A 章节导读

**目标**：真正帮助用户逐节读论文，而非全篇总结。

任务：
1. 按段落/标题建立可点击小节目录，回显选中章节、源位置和缓存状态。
2. 引入 A01、`ReadingGuideDraft` 和深度 quick/standard/deep；默认标准导读；用户点击后才调用模型。
3. 处理长章节（用户选范围或拆子节），不自动循环请求全部章节。
4. 展示概览、关注点、阅读问题、困难术语和原文位置；支持复制导读。
5. 测试切换章节不会自动请求模型，缓存/版本变化后标记过期。

**验收**：选中3节，分别生成、重新打开不增加Token；不同深度使用独立缓存；段落无证据不捏造。

## Lite P3 — D 局部问答 + 可信检索

**目标**：避免原来Query默认接近16万Token上下文。

任务：
1. 在现有PDF索引上实现最小FTS5检索，三种作用域 selection/section/paper；默认section。
2. 通过用户问题检索3–5个短Span；设置总上下文硬性截断/预检及低相关性提示。
3. 引入 D01、QARecord、回答引用校验、无证据回答与“用户点击扩大范围”的明确操作。
4. 中文问题检索英文原文先用本地术语映射；D02只在检索失败且用户主动同意时调用。
5. QA调用支持取消、记录重试和失败；缓存完全相同的输入、检索证据及模型参数。

**验收**：普通问题只带入有限片段，不发送整篇PDF；误引用的span ID被校验拦截；没有证据时不生成虚假结论；有实测上下文与Token日志。

## Lite P4 — UX、预算守卫、真实验证与交付

任务：
1. 统一全局导航：项目、文献、卡片、章节导读、问答；设置/诊断在侧栏底部，侧栏可折叠且记忆状态。
2. 预算控件：每请求/每论文/每日额度；成本预检、可取消、超限需明确同意；任务页面显示实际 input/output/retry/cache。
3. 源文件变化处理：`document_version_id`变更使旧成果标记 stale，旧内容保留，可主动生成新版本。
4. 修复残留PowerShell空窗口、重启任务状态、模型429/超时、Zotero不可用等历史问题；不重写无关UI。
5. 完成Windows安装/启动回归、Mock端到端与**获准的真实模型**集成测试；检查Git暂存区、历史与私有文献/API Key泄露。
6. 旧 Graph、Wiki 和 Obsidian 流程不进入 Lite 入口；后续若需要导出或历史访问，另行从备份工程实现。

**验收**：Windows安装包正常关闭不依赖外置PowerShell；完整 B+3A+3D 的实际Token、耗时、证据正确性有报告；没有真密钥时明确写“未完成真实API验证”。

## 6. 迁移表（旧功能 → 新流程）

| 旧功能 | Lite处理方式 | 删除？ |
|---|---|---|
| Zotero Collection/附件选择、直接PDF备用 | 复用，**只读原始PDF** | 否 |
| PyMuPDF、Section/Span/文件SHA | 复用，作为阅读信息核心 | 否 |
| Provider设置、Mock、Sidecar和任务历史 | 复用，新增预算/计量 | 否 |
| P02/P12/P13完整抽取与贡献排序 | 默认关；原代码作为历史/高级能力 | 否 |
| GraphProjection、拖动图谱、Claim Comparator | Lite 不保留旧入口；轻量图谱使用 PaperCard + LightGraph | 否 |
| 全量跨论文推理/实体融合 | 默认不运行 | 否 |
| P07老Query大上下文拼接 | Lite D01限定范围检索；旧接口不进入干净工程 | 否 |
| 语义Lint、Wiki批量或增量生成 | 默认关 | 否 |
| Obsidian Wiki自动维护 | 从主路径移除，可保留手动Markdown导出 | 否 |
| 论文阅读大段解析结果页面 | 隐藏/改诊断入口 | 仅移除默认UI |

## 7. 工程接口与最小目录演进

```text
engine/researchgraph/
  lite/
    card_service.py        # B01 + 输入选择 + 证据校验
    guide_service.py       # A01 + 小节范围
    qa_service.py          # D01 + 检索 + 引用
    caching.py             # 版本化键 + single-flight
    budget.py              # 预算预检 + 实测token
    contracts.py           # 复用 schemas/contracts.py 目标契约
  documents/              # 现有Parser, Evidence, FTS索引保持
  providers/              # 现有模型适配器保持
apps/desktop/src/features/lite/
  PaperCard.tsx
  SectionGuide.tsx
  PaperQA.tsx
  UsageSummary.tsx
```

现有项目若已有等价模块**复用而不重复建目录**。后端业务服务不应该自己访问未经授权的文件路径；统一通过现有Zotero Adapter和Source Repository。

## 8. 新版与旧版比较必须诚实

任务不同，不能只比较Token并称Lite抽取质量提高。要对同一篇论文报告：总调用次数、总input/output tokens、成功/失败、缓存命中、用户要求的任务完成率、引用正确率、阅读帮助评分。旧版“完整科学知识图谱”的功能不等价，已取消的功能需明确陈述而非视为等价替代。

## 9. 交给同一Codex会话的执行方式

迁移阶段接续指令已移除。当前工作以 `docs/progress.md` 和 Lite ADR 为准；不凭空声称真 API、Windows 安装或学术结论已经通过测试。
