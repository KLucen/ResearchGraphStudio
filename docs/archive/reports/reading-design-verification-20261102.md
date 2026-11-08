# 阅读辅助知识图谱设计验证（R0）

记录：2026-11-02 16:25（Asia/Shanghai）。本轮授权为重新设计 Schema、Prompt 与 docs 细则，追加取消人工审核流程。不是运行软件功能交付。

## 交付

10 份产品/架构/Schema/交互/Prompt/计划/API/验证细则，13 份参考 Prompt（含 P12/P13），Pydantic + 29 份生成 JSON Schema，25 个虚构示例及索引，目标关系 SQL，ADR 0008、代码映射、变更摘要、协作/进度/下一轮模板。设计 v3.3，参考 reading-* 合约独立于运行版本。

原 v3 的 52 项资产先复制归档，Schema/Prompt 原内容可追溯；归档文档仅标注历史和修复相对链接，当前规范继续放在 docs 原位置。历史验收/QA 原件保持。

## 实际命令与结果

| 命令/检查 | 结果 |
| --- | --- |
| `python docs/schemas/contracts.py` | 生成 29 份参考 JSON Schema，与 Pydantic 内容一致 |
| `python -m pytest docs/tests -q` | 78 passed，包含 25 示例、引用/来源/条件/单元/选择/拓扑、未来引用、内存 SQL |
| `python -m pytest docs/archive/v3/tests -q` | 12 passed，独立进程验证原参考资产 |
| `python -m pytest docs/archive/v2/tests -q` | 5 passed，独立进程验证旧契约 |
| `python -m ruff check docs/schemas/contracts.py docs/tests/test_contracts.py` | 通过 |
| `python -m ruff format --check docs/schemas/contracts.py docs/tests/test_contracts.py` | 通过 |

Python 均为 Anaconda researchgraph-studio 环境解释器。初次生成时有参考代码冒号/格式错误，修正后重新导出并全部通过；未把失败尝试记为通过。检查日志在本机忽略目录 `.local/reading-design-20261102/`。

关键用例：没有源证据/错误文献/非法引用/重复局部 ID 拒绝；known/unknown/conflicting 保持语义；理论与综述无须实验；共享 Method 两单元同 ID；默认 Paper 不能连支撑节点；未选有效候选可检索；图谱导航不是科学支持；Query/Wiki 段落依赖版本和来源匹配；历史审核字段只为兼容，新流程无审核关卡。目标 SQL 验证关系约束和不级联删除既有知识，不代表正式迁移实现。

## 范围证明与剩余验证

收尾检查：**201 个非文档文件哈希与开始时一致**；当前 88 项设计资产和归档 52 项资产哈希通过，其中归档 27 项非 Markdown 文件与归档前字节一致。125 份 Markdown、420 个本地链接、QA hash、环境 JSON 检查通过，四份不可访问外部原文明确排除。440 个候选源码文件的路径/内容与 Gitleaks 扫描通过，`git diff --check` 通过、暂存区为空。

本轮不修改运行 Schema、Prompt、OpenAPI、数据库或安装包；未调用真实模型、不跑 Computer Use。本轮文档测试不能替代运行应用回归、真实科学质量、迁移或安装验收。当前旧软件不会因文档更新自动获得分层图谱。

当前阶段 P3/v3 自动建图迭代，R0 完成；R1–R5 待开发，详见[计划](../../06_development_migration_plan.md)。原 M6 仍有真实响应超时、关系边和安装等缺口。四份外部补充原文不可用，未重新核验内容/哈希，QA 和登记保留。未 Commit/Push。
