# 知识任务失败分类与任务记录诊断

日期：2026-11-20（Asia/Shanghai）。用户要求修复 `KNOWLEDGE_RESPONSE_INVALID`，并把错误原因直接汇报在任务记录条目，不再引导到研究内容知识库查原因。

## 诊断事实

只读 `mode=ro` / `query_only` 检查当前失败记录：发送槽已标记，未保存完整模型正文，usage未知，私有metadata只保留了发送前预检结果。程序在K2/K3异常处理中把继承自ValueError的ProviderError也归入通用响应格式失败，并未在失败路径保存实际传输metadata或具体诊断。旧记录没有足够信息区分超时、服务拒绝、空响应等情况；不能将其反推为模型内容格式错误，也不能据发送槽标记确认费用。

合成、本机零网络构建已确认当前火山Agent Plan的max/json_object/省略max_tokens组合可通过本地冻结策略检查；公开官方文档未找到确定参数冲突。因此本轮修复失败分类与诊断保存，不以未经验证的配置猜测覆盖用户模型配置或收费重试。

## 改动范围

新增`knowledge_diagnostics.py`集中固定错误码/类别/中文说明，K2/K3先识别ProviderError，分别记录超时、网络、服务拒绝、限流、输出截断、空正文、协议外壳、JSON和DTO问题。字段问题仅保留协议白名单路径、规则和固定说明；未知字段名用`_extra_field`，不回显模型生成的键或值。失败路径保存实际Provider metadata及安全诊断，HTTP仅保留状态数值，不读取或回显供应商错误body。K3片段继续私有保留，以response_complete=false区分完整响应。

三个任务GET入口在现有批次恢复投影上叠加`knowledge-diagnostic-1`：全局列表、项目分页和单条任务详情。新诊断重新从安全字段生成；旧通用失败有完整raw时本机只读校验，缺失细因时明确无法判定。没有迁移或GET写入、发布/自动请求。实际正式库只读投影已确认该历史条目将显示：`KNOWLEDGE_FAILURE_UNRESOLVED` / 原任务未保留完整响应和足够的失败细因、无法判定格式/网络/超时、费用未知。

前端任务条目直接显示分类、摘要、字段问题、发送槽/完整响应保留状态和处理建议。知识库不加原因面板，只保留任务记录提示和显式继续入口；有详细诊断时不重复旧通用提醒。发送槽标记明确费用未知。新组件按React检查规范复核，继续使用现有React/Query/CSS栈。

旧响应、失败、冻结策略和重试账本保持；没有放宽Schema/引文/来源检查，也没有因为分类修复自动继续旧失败或为查原因调用模型。

## 验证与交付

通用Provider新增5种HTTP失败安全状态测试；`test_chat_stream.py` **38 passed，0.36秒**。新`smoke-knowledge-diagnostics.py`已用源码侧车实际HTTP验证400拒绝和字段失败两个情景：分别为`KNOWLEDGE_PROVIDER_CLIENT`、`KNOWLEDGE_RESPONSE_SCHEMA_INVALID`，全局/项目/单条GET一致、公开输出不含合成private sentinel、重启保持且0额外请求。每情景1次loopback合成请求，真实模型0。第一次在app投影接入前提前跑时result=None，接通后复验通过；该初次集成尝试保留，不混作最终回归。

独立审查发现K3孤儿Job缺Run时except变量未初始化，已在except入口建立安全默认诊断，隔离零网络复测正常failed并补回归。后端诊断新专项 **24 passed，2.20秒**；诊断/提取/联系/API/预算联合首轮 **95 passed，19.12秒**，此后补充两项保存诊断脱敏和K3完整坏DTO用例纳入最终全量，专项数量互有重叠不相加。mypy112、Ruff/185文件格式通过。

前端任务/库/API专项 **51 passed**；Edge专项 **5 passed，6.8秒**，最终390px截图已查看。首轮完整Edge **38 passed/1 failed**，旧workspace local用例等待页签时5秒内元素为空；未修改生产页签或放宽断言，该文件单独复验 **3 passed，4.4秒**，完整复验 **39 passed，28.4秒**。首轮异常原因未确定，不写成产品根因已修复。

新打包引擎的HTTP诊断闭环两个情景通过；fixture在HTTP拒绝后keep-alive关闭会产生ConnectionAbortedError日志，脚本只对这两种已知连接关闭异常收尾，原请求次数/隐私/三GET/重启断言保持，最终新引擎再验通过。知识库正常三null建模→联系→重启HTTP闭环也通过：2K2+1K3/合成192Token、GET与重启额外0。新引擎Host **17 passed /0 ignored，3.62秒**。192项源码/配置冻结中仅诊断smoke收尾改动已单独验证后更新指纹，应用源码不变。

最终完整`check-phase0.ps1`通过：后端 **868 passed /1符号链接权限跳过 /1既有Starlette warning，209.86秒**；React **210 passed /19文件，16.24秒**；Ruff/185文件格式、mypy112、12项runtime锁覆盖、pip依赖、OpenAPI/TS契约、前端类型/ESLint/Prettier与生产构建通过。Vite既有大chunk提示保留，未作为本轮性能优化。诊断smoke脚本仅调整拒绝HTTP后夹具连接关闭的收尾，该脚本另行Ruff/格式及打包引擎实际HTTP通过，应用源码冻结保持。

工作区私人路径与Gitleaks **485文件通过**，`git diff --check`通过；7文档 **212个本地链接**（含新安装器）最终无缺失，192项源码/配置再次核对无变化。本轮新增真实模型请求0、正式用户库实验写入0、无新Commit/Push授权。安装器及最终指纹见下节；上一轮839/202/38未当作本轮重跑。

## 最终安装交付

新未签名安装器：[ResearchGraph-Studio-Knowledge-Diagnostics-0.0.1-x64-setup.exe](../.local/releases/knowledge-diagnostics-20261120/ResearchGraph-Studio-Knowledge-Diagnostics-0.0.1-x64-setup.exe)，2026-11-20 **23:50:21**完成封装，**160,736,175 bytes**。SHA-256：`3657aef9025aeb62410782cbe93517aa260d1a11475bc08346c04b72b11ecda3`。

PowerShell5.1新隔离目录安装完成，phase complete/passed：lite0018、匿名本地PDF、3段模型材料/章末阅读进度、题名、清理/重建/删除及原PDF保留，真实模型0。安装版诊断HTTP闭环再次通过：400拒绝与坏DTO分别报告CLIENT/SCHEMA，三种任务GET一致、私人sentinel不外露，每场景1次loopback合成请求，读取和重启无额外请求。

192项源码/配置最终冻结保持；sidecar SHA-256 `4efe27bc65ebf5dbfd11a9b3540e09e55eac6363c3561ae09267483b46c1bc6b`与Tauri打包资源、安装版一致，334内部资源逐项相同。安装宿主与原构建宿主只有标准Tauri bundle标记`UNK`→`NSS`的3字节差异，其余全部字节一致，未误记两个raw哈希相同；证据保存于`.local/verify/knowledge-diagnostics-20261120/`。未覆盖日常安装或修改正式用户库。

安装新版后打开任务记录，原知识失败条目会直接显示新增的只读诊断。旧错误码保留，缺失细因时说明无法判定；不需要为显示诊断重新生成或调用模型。需要新建后继时仍在知识库显式继续，该操作与查看原因分开。真实平台/长文科学质量和用户日常原生体验仍待独立反馈；本轮未Commit/Push。
