# ADR 0006：图谱尺寸稳定、局部引用修复与文献工作区

- 日期：2026-11-02（Asia/Shanghai）
- 状态：已实施；原生交互由用户安装反馈，未进入下一 Phase。

## 问题与证据

受控 React Flow 节点在 hover/物理模拟更新时重建，却未携带 measured 尺寸；库会清空测量并设置 visibility:hidden。真实渲染浏览器测试复现拖动期间节点不可见，原 mock 组件测试不能发现此问题。

实际第二篇论文返回合法 JSON，但 links[1].source_local_ref 不在该批 items.local_ref 中；文献版本匹配，没有两个论文任务混写。旧校验只保存通用错误，旧重试无法利用该响应。原始私人响应和数据库副本仅存本机忽略目录。

## 决定

1. 点节点显式携带 18×18 尺寸与 measured，坐标只传 x/y。hover 边文字不截获指针；过滤非有限布局/指针值；StrictMode 清理 RAF 时归零。维持既有 React Flow 和力模拟，不换栈。
2. 对缺失局部引用返回明确路径/引用值；其他 Pydantic 错误仅报告路径和类型，不把原文输入转储进任务错误。
3. 新增独立运行 Prompt `P02_local_link_repair` v1，保留原 P02 与 DTO JSON Schema，保证旧任务签名仍可恢复。仅在 items 结构正确、文献/批次匹配、证据别名有效时调用。
4. 模型只返回 link_index 与两个局部端点。程序要求唯一覆盖错误关系，只改缺失端点；原正文、数值、证据、关系类型和合法端点不能改变。模型无法判断可返回空修复并明确失败；不采用拼写模糊替换。修复后完整 Schema、来源和 Evidence 校验仍为入图门槛。
5. 每份错误响应最多一次修复 ModelRun；沿用传输层最多三次有界重试，不进行多轮内容修复。修复失败或中断后同任务重试不再花费修复调用；合法修复响应可复用。非局部引用错误（如 JSON/证据失败）仍允许用户重试重新抽取未完成批次。
6. 原 ModelRun 保留 validation_failed 与原始 raw_output；修复运行保存独立 Prompt/input hash、raw_output、Token、状态，input_manifest.repair_of_run_id 连接原运行。最终知识指向修复运行，经 KnowledgeStore 单事务落库。已完成操作继续幂等跳过。
7. 文献工作区有导入论文、任务记录、项目文献三个独立折叠板块；PDF/Zotero 同级，笔记来源独立。折叠仅隐藏子树，保留会话内选择与查询，展开状态按项目记忆。

## 兼容与限制

无数据库迁移，Schema head 0009；旧 API、知识 ID、原始模型结果、原件和审核历史保留。新修复不会修改已接受的科学语义。修复局部引用仍属于模型候选判断，不证明科学关系成立。

真实失败批次已在隔离副本以一次真实调用通过校验与 Store，全文其他批次没有重跑。交互采用真实 React Flow 的 headless Edge 回归；本轮不把浏览器结果当作 Windows 安装/原生实测。见[验收报告](../stability-verification-20261102.md)。
