# ResearchGraph Studio — Codex交付包（规范，不是完成的软件）

**版本：2026-11-01 / Graph-Centric v2.0**

## 内容

1. `01_product_design.md`：产品目标、系统角色、五大工作区、业务流程图、验收场景和关键风险。
2. `02_development_plan.md`：技术栈、可安装架构、Phase 0～6、API、测试、Codex开发规则。
3. `03_knowledge_schema_and_prompts.md`：知识本体、审查和来源状态、关系推理契约、10个Prompt设计、质量审计与Wiki依赖。
4. `schemas/contracts.py`：参考Pydantic v2 DTO；不含实际数据库/算法/运行服务。
5. `schemas/*.schema.json`：从以上DTO生成的JSON Schema，可用于结构化模型输出与契约校验；服务端仍需对ID、证据和权限进行二次验证。
6. `prompts/P01...P10.md`：10个独立的版本化Prompt模板；`{{...}}`字段由运行时安全替换，并严格限制输入白名单。
7. `examples/*.example.json`：虚构的输入输出结构样例，不是论文事实。
8. `AGENTS.template.md`：可迁入真实仓库根目录的编码Agent协作规范。

## 建议交付到Codex仓库

```text
researchgraph-studio/
├── AGENTS.md                       # 可由AGENTS.template.md起草
├── docs/
│   ├── 01_product_design.md
│   ├── 02_development_plan.md
│   └── 03_knowledge_schema_and_prompts.md
├── engine/researchgraph/contracts/  # 参考schemas/contracts.py，逐Phase扩展
├── prompts/                          # P01...P10
└── tests/fixtures/                   # examples/*.json
```

**注意**：三个Markdown是设计依据；`schemas/contracts.py`是一个经过语法与基本类型验证的**参考起点**，不能视为已经实现的模型服务或数据库。当前包不附带真实PDF或用户Zotero/Obsidian数据。

## 本地验证参考模型（需要Python 3.12+与pydantic v2）

```bash
python -m py_compile schemas/contracts.py
python -c "import sys;sys.path.insert(0,'schemas');from contracts import ExtractionBatch;import json;ExtractionBatch.model_validate(json.load(open('examples/extraction_batch.example.json', encoding='utf-8')));print('ok')"
```

## 历史初始化指令（已有工程不执行）

当前工程从旧 P1 迁移至新版 P2，实际实现见[进度](progress.md)和[迁移评估](migration/v1_to_v2_assessment.md)。以下只保留原设计包的新项目启动模板，不适用于本次迁移。

阅读`docs/01_product_design.md`、`docs/02_development_plan.md`、`docs/03_knowledge_schema_and_prompts.md`并检查仓库现状。按照**新版统一Knowledge Engine**方案先完成Phase 0；只实现可启动桌面壳、FastAPI Sidecar、SQLite迁移、项目CRUD、本地会话鉴权、MockProvider及构建/测试脚本。禁止提前伪造AI功能、绕过审核修改科研结论或直接改用户Obsidian笔记。每Phase结束提交可运行成果和`docs/progress.md`。
