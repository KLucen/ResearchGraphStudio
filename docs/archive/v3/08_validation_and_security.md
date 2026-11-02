> 历史 v3 平铺图谱设计，已由当前 [阅读辅助设计](../../README.md)取代；不作为新实现要求。

# 08 — 质量验证、安全与科研实验设计

## A. 必须检验的业务不变量

1. GraphProjection节点短标签不改变领域数据库中的原文英文主张、中文完整翻译与EvidenceSpan。
2. 自动建图不要求`review_status=accepted`；仅满足来源锚点/Schema等程序条件即可正常可见。
3. `source_status=anchored`不等于科学真实性；`AI候选`关系不得显示为确定事实。
4. LLM引用的证据ID必须属于本次允许集合，ID存在但不属于本次任务仍视为错误。
5. `NO_DECISION`不创建科学关系边；Condition unknown不能当different。
6. 图谱拖拽仅更新布局偏好，不会修改科研知识GraphRevision。
7. 更换Prompt/模型/文献版本重跑，形成可区分的ModelRun，不直接覆盖用户修订知识。
8. 翻译不能更改原文数值、否定、主张强弱或范围；中文标签不作为Evidence。
9. 同一批次提交两次不会重复创建知识节点；持久化与Event/Outbox同事务完成。
10. 用户原始PDF和精读笔记不得被应用自动修改或重复保存。

## B. 自动化测试矩阵

| 层 | 测试 |
|---|---|
| Schema | 在仓库根目录运行 `conda run -n researchgraph-studio python -m pytest docs/tests -q`；合法ExtractionBatch/GraphProjection/Inference案例通过 |
| Extraction | 五类节点同批输出；引文归属/否定/unknown/中英数字一致 |
| Evidence | 虚构ID、跨chunk ID、offset错位、源文件更改阻断或诊断 |
| KnowledgeStore | 事务幂等、重复批次、版本迁移、人工修订不覆盖 |
| Projection | 默认5类、detail_ref合法、边线型状态、旧节点兼容 |
| Jobs | 7批第2批超时可恢复、429/401分类、取消保留成功批次 |
| UI | 拖动/固定/重启布局、搜索/筛选/局部图、侧边栏折叠画布自适应 |
| Zotero | API不可用、Collection为空、多附件、PDF不存在、源版本变化 |
| Privacy | API Key不进logs/DB/响应，Git扫描密钥/论文/私有文件 |
| E2E | 真实Zotero论文→真实LLM→自动图谱→Claim详情→证据及Zotero打开 |

## C. 真正需要科研验证的比较实验

### 实验1：统一抽取是否比原多阶段抽取更有效？

Baseline：旧版多Extractor串行 + 审核前置；Variant：新章节级P02 + 程序校验 + 自动入图。控制模型、论文、温度和总输入证据预算，比较Claim/Method/Condition字段F1、证据准确率、术语一致性、模型调用数、总Token、耗时、单篇可用图谱首屏时间。**不能只比较速度而忽略正确率下降。**

### 实验2：不同类型节点默认隐藏是否改善用户检索？

A：全量复杂节点图；B：五类节点+按需详情。任务包括“找论文A的主要方法”“比较条件差异”“打开Claim证据”，比较完成时间、正确率、操作次数与用户主观负担。用户样本不足则称可用性观察，不夸大统计显著性。

### 实验3：自动入图与状态标记的可靠性

比较“只显示人工已接受”与“证据自动锚定+来源状态可见”，测量图谱首次可用时间、无证据节点误入率、后续纠错成本、用户对AI候选关系的误读率。不能将自动入图视为科学事实准确性的证明。

### 实验4：条件化关系推理保持独立验证

Baseline：LLM直接判定关系；Variant：Schema条件比较+证据约束。指标Macro-F1、错误CONTRADICTS率、NO_DECISION识别、证据正确率。使用人工标注真实论文小集；虚构示例仅用于单元测试。

## D. 安全规则

- **密钥**：系统凭据管理，不把真实API Key写入普通DB、前端持久化、日志、fixture或Git；远程论文发送需要用户知情与可控范围。
- **文件**：仅允许用户授权的Zotero附件/直接导入路径；拒绝路径穿越、符号链接越权、恶意文件；PDF解析失败隔离任务。
- **Prompt Injection**：PDF、Obsidian笔记和批注均视为数据；忽略其中执行命令、访问本地文件、上传机密等指令。
- **GitHub**：`.gitignore`、Secret Scanner如Gitleaks、提交前实际暂存区/历史扫描；已跟踪内容不受`.gitignore`保护，发现泄露需停止上传及轮换密钥。
- **本地服务**：回环地址绑定、鉴权令牌、受控CORS、日志脱敏；禁止未授权本地端口转发。
- **日志与评测**：默认记录哈希和指标，不存完整私有论文内容；需存全文用于实验时显式设定本地私有目录并阻止提交。

## E. 真正的“完成”定义

文档是设计提案，不宣称已有代码通过。Codex需要运行真实命令与测试并保存日志；API不可用时明确标记`NOT_TESTED_REAL_API`；能启动但无法访问Zotero时标记`BLOCKED_ZOTERO`；Windows打包在非Windows环境无法验证时说明限制。禁止输出“全部完成”而没有可核对的报告。
