# 知识库预算与 DeepSeek 配置验证

日期：2026-11-20（Asia/Shanghai）。本轮用户要求三项预算支持无上限、修复输入预算报错并调查 DeepSeek V4.1 Flash。实现和核验延续现有 K1–K3，不启动 K4、不调用付费模型。

## 实际诊断

只读 SQLite `mode=ro` 与 `query_only` 检查设置和任务元数据：默认输入 48,000 / 输出 6,000 / 单次请求 2 / 累计请求 20。失败码 `KNOWLEDGE_INPUT_BUDGET_EXCEEDED`，`request_sent=false`、没有 raw。仅在内存重建该任务已存输入并计算大小：旧规划估算 73,905 Token，当前完整消息估算 79,268 Token / 234,400 UTF-8 字节，未访问模型或改变正式数据库。说明预算确实小于完整请求，同时字节不能当作 Token。

当前五种用途共用火山方舟 Agent Plan 的 `deepseek-v4.1-flash`，顶层 `reasoning_effort=max`、普通文本等待 90 秒、context/output 能力未填。本轮没有读取凭据、输出私人论文或任务身份，也没有代改这些配置。官方来源与建议见[模型推荐](deepseek-v41-flash-recommendations-20261120.md)。

## 实现

- 知识库三预算为 nullable DTO，null 表示取消该软件限制；默认值、有限校验、候选数及累计预算保持。
- K2/K3 及通用文字 Provider 统一 Token 估算、实际消息再次预检；无上限不绕过端点容量、来源/授权终验、累计账本或显式重试限制。
- 冻结策略与当前设置取较严限制。旧预算失败保留，保存新设置后可显式继续并采用新预算；没有自动重发。
- 前端无上限切换/取消恢复/重载、任务预算显示和可操作的中文错误说明；任务记录指向知识库继续，避免显示不适用的“重试本地处理”。

## 验证记录

分项实际结果：

- 后端预算/提取/联系/自动化四模块：**76 passed，24.21秒**。新增12项预算覆盖null交集、48K失败→保存无上限→显式后继、真实已知容量仍拦截、10批超过旧8请求限制但累计预算仍拒绝、prepare期间收紧及完整消息字节/Token分离。
- 通用Provider/流式/设置/结构化联合专项：**86 passed，8.14秒**。新增5项容量用例覆盖长ASCII误判、无软件输出cap、已知context但未知output仍拒绝过大输入、未知输出不臆造端点限制。
- 知识库React/API专项：**21 passed**；JobHistory专项 **22 passed**，包括两个知识任务不会显示泛型本地重试。最终React全量另记，专项数有重叠不相加。
- 实际Edge全量 **38 passed，32.3秒**，含三项null保存/重载、有限值恢复和620/390窄屏；新增控件截图已查看。
- 独立只读复核预算/Provider专项 **17 passed，4.29秒**，未发现本轮新增实质缺陷。
- 新sidecar执行更新后的 `smoke-knowledge-library.py`：三项null、累计上限3，两自动K2+一自动K3，双侧引文/保存报告/重启保持、GET和重启额外0。3次均loopback合成，夹具usage为192 Token，非真实模型用量。
- 新打包引擎Host完整测试 **17 passed /0 ignored，4.31秒**，含原生连接与重启。

完整 `check-phase0.ps1` 实际通过：**839 passed /1 skipped /1既有Starlette warning，284.07秒**；跳过是本机符号链接权限，未关闭来源检查。Ruff/182文件格式、mypy111、12项runtime依赖锁覆盖、pip依赖检查、OpenAPI/TypeScript契约导出、前端类型/ESLint/Prettier及生产构建均通过。React全量 **202 passed /19文件，17.70秒**。通用文字Provider和知识库类型检查均包含在此次全量；完整检查启动后只扩充了smoke脚本的null持久化断言，该脚本另行Ruff/格式检查与实际新sidecar闭环通过，应用源码未继续修改。

最终Edge与上述回归使用同一冻结应用源码。新sidecar打包完成后，187项源码/配置指纹复核无变化。构建仍有Vite大chunk提示，未作为测试失败或本轮性能优化处理。

最终源码内容扫描 **479文件通过**（私人路径规则与Gitleaks），`git diff --check`通过。7份活跃文档的 **208个本地链接**（含新安装器）最终检查无缺失，187项源码/配置冻结再次无变化。

## 交付与边界

新未签名安装器：[ResearchGraph-Studio-Knowledge-Budget-0.0.1-x64-setup.exe](../.local/releases/knowledge-budget-20261120/ResearchGraph-Studio-Knowledge-Budget-0.0.1-x64-setup.exe)，2026-11-20 21:50:28完成封装，**160,716,046 bytes**。SHA-256：`ac857e36cfe84bffb4dc692550229616750e4f76c586f44adf0c9ce96fd69ceb`。

Windows PowerShell5.1新隔离目录安装通过，phase complete/passed：lite0018、匿名本地PDF、3段模型材料、阅读进度/题名更新、清理后数据保留、重建/删除及原PDF保持，模型0。安装版 `smoke-knowledge-library.py` 再独立通过：两篇带来源知识、一份双侧引文联系报告、三项null/累计上限3和个人报告元数据重启保持、GET/重启0重发；同样只用loopback合成3请求/192夹具Token。

187项源码/配置冻结保持；打包、Tauri资源与安装版sidecar SHA-256均为 `e82784abef522812ecb280dafd36d0bb51f38eea3259de64a4a33b67c1925ec5`，**334内部资源**逐项字节匹配。首次宿主EXE直接SHA比较未通过，已精确定位只有Tauri标准bundle marker `UNK`→`NSS`的3字节差异，安装EXE与构建EXE在其余所有字节一致；Tauri本机源码platform.rs明确NSS代表Nsis，未以该预期标记差异冒称直接原始SHA相同。验证指纹分别保留在`.local/verify/knowledge-budget-20261120/fingerprints.json`，数据与本地产物不上传。

使用步骤：安装后打开“研究内容知识库 → 自动分析设置”，为三项预算按需勾选“无上限”，点击“保存分析策略”；回到最近任务，对原预算失败任务点击“确认继续知识任务”。仅保存设置不会发起请求，原失败仍保留。输入96000也可容纳本次已观察材料的估算，但真实供应商计数不由本机估算保证。

数据库 head 仍 `lite0018`，无迁移。正式用户库实验写入 0、付费模型 0，未覆盖日常安装目录。当前请求没有新的 Commit/Push 指令，本轮未提交或上传新改动。真实 DeepSeek 响应质量、长文科学效果、干净机及用户日常原生使用反馈待独立验证。
