# 文字生成活动超时修复验证

日期：2026-11-21（Asia/Shanghai）。用户再次报告`KNOWLEDGE_PROVIDER_TIMEOUT`，要求持续生成时不要被固定总时限截断，连接失败或生成停止时才按相应等待计时。

## 实际诊断

正式库只读`mode=ro`和`query_only`读取安全metadata：`timeout_seconds=90`、旧`total_timeout_seconds=180.0`、`timeout_phase=total`、elapsed179.985秒；请求体约0.063秒发完，HTTP200/首字节1.016秒、末字节179.938秒，response_bytes1843225、reasoning_characters77935、content_characters0。确定连接很早建立、收到大量公开推理，最后仍有网络数据，且由固定total停止等待；不是180毫秒或连接超时。旧记录未单独保存最后一次实际正文/推理增量时间，无法据末字节还原最后时刻是新推理还是心跳，不能断言全程无停滞。新metadata分别记录最后网络字节与实际生成活动，消除此诊断盲区。没有读取凭据或公开模型/论文内容，没有正式库实验写入或收费重试。

## 改动

`providers.py`对activity文字请求在请求体写完后开始首生成计时，只在已解析正文或公开reasoning字符增加时续期；没有固定total deadline。HTTPX独立15秒连接及网络/上传停滞保护仍在；SSE心跳/空delta/role/usage不续期。`[DONE]`可直接结束读取并进行完整结束状态验证，避免等服务器keep-alive EOF。非SSE只记录非空白响应字节进展，空白保活不刷新，不冒充生成Token。超时/cancel/断线关闭socket，片段和旧成果保留、不自动重发。

`model_settings.py`增加nullable文字policy，新任务快照为activity，显式legacy和已有快照保持；三种新知识/阅读文字用途共享Provider，不仅改K2。文档请求仍独立有界，迁移head保持lite0018。`knowledge_diagnostics.py`显示首生成/停滞的固定中文原因与安全数值；ModelSettings新增两种等待方式、5–180秒整数验证和单位说明，详细解释公开推理/心跳/隐藏思考边界。显式继续知识任务按现有逻辑使用当前设置创建后继，原失败/账本不改。

## 已完成验证

活动与模型设置联合 **42 passed，6.75秒**：19项活动流覆盖连续正文、两种公开reasoning字段越过旧total、纯心跳/usage/role/空delta、生成后停滞、无headers/连接失败、上传不占生成等待、非SSE空白/接收进展、DONE无EOF、取消及legacy；模型设置验证新增快照默认/显式策略、旧profile与旧snapshot不变、文档600/1800独立。Provider/诊断联合早期80项通过，专项重叠不相加。mypy112与Ruff通过；增加标签时出现的类型细化和长行已修正，不记录失败尝试为通过。

前端初步ModelSettings/JobHistory **41 passed**，Edge设置 **2 passed，3.8秒**，含两策略保存重开/1280与390宽度、文档设置独立与零自动重试；最后文案复验和全量另补。独立复核发现非SSE空白续期及connect随较短idle缩短两点，已修复并加入专项，未忽略该发现。

新增`scripts/smoke-knowledge-activity.py`以真实loopback SSE连续12秒公开推理后返回完整合成带来源知识。源码运行通过：idle5秒、旧派生总时限10秒，新activity完成 **12.015秒**，252推理字符/479正文字符；1次合成请求，知识发布及重启保持、额外请求0、真实模型0。首轮流程断言已通过但夹具只读SQLite句柄未关闭导致临时目录清理失败，改closing后完整复验通过；未忽略清理异常或写正式库。

## 交付状态

最终前端文案明确“已冻结任务原计划保持，显式继续知识任务会按当前设置创建后继”，设置专项11项再次通过；完整Edge **40 passed，53.0秒**，含实际模型设置与旧知识/阅读界面，已查看两种宽度截图。新sidecar实际HTTP活动流也通过：idle5/旧total10、elapsed **12.016秒**、252推理/479正文字符，1合成请求/重启0重发。新sidecar原有两种错误诊断HTTP通过，Host **17 passed /0 ignored，5.86秒**。193项源码/配置已冻结。

最终完整`check-phase0.ps1`通过：后端 **891 passed /1符号链接权限跳过 /1既有Starlette warning，280.86秒**；React **216 passed /19文件，18.60秒**；Ruff/187文件格式、mypy112、12项runtime锁、pip依赖、OpenAPI/TS契约、前端类型/ESLint/Prettier和生产构建通过。Vite既有大chunk提示仍在，不当作本轮性能改进。应用源码193项冻结无变化；Gitleaks/私人路径 **489文件通过**，diff检查通过。未把前轮868/210/39当作本轮成绩。

新未签名安装器：[ResearchGraph-Studio-Activity-Timeout-0.0.1-x64-setup.exe](../.local/releases/text-activity-20261121/ResearchGraph-Studio-Activity-Timeout-0.0.1-x64-setup.exe)，2026-11-21 **00:25:06**完成封装，**160,742,972 bytes**，SHA-256 `c04f494d18b4b6979e04356befebe8bba17f90f319b763e6a12eafe5ab517f63`。用户再次要求继续后，11:39在新隔离目录完成PowerShell5.1安装/烟测：lite0018、匿名PDF、模型材料/阅读状态/题名、清理/重建/删除及原PDF保持，模型0。安装版实际活动HTTP通过：idle5/旧total10，elapsed **12.015秒**，252推理/479正文字符，1合成请求、保存及重启保持、额外请求0。

安装sidecar SHA-256 `c94b012c59c7cc7e18c7b0a852a17b7b65be0463a16c8226d342f3eeae35b0e5`与打包源/Tauri资源相同，334内部资源逐项匹配；宿主仅标准Tauri bundle标记`UNK`→`NSS`3字节差异，其余字节一致，raw hash分列。193项源码/配置最终复核保持，证据在`.local/verify/text-activity-20261121/`，不上传测试数据或本地安装器。

最终交付前再次完成489文件敏感扫描、diff检查及7文档221个本地链接检查，均通过，含新安装器路径；193项冻结指纹无变化。

安装后可在模型设置确认“按生成活动等待（推荐）”；旧profile未显式选legacy时，新任务自动冻结activity。知识库中显式继续本次失败会创建采用当前设置的后继，原失败保持、不会安装后自动发送。已有冻结的其他任务仍按原计划。文档独立时限不变。

旧失败不会自动收费重发，当前轮未Commit/Push、未修改正式库或日常安装。公开活动检测不等于观测服务内部思考，不宣称真实模型科学质量或延迟SLA。第一次清理失败留下的合成临时目录，单独删除请求被自动安全审查拒绝（仅返回blocked by policy），已保留该目录、不尝试绕过；后续夹具显式关闭只读SQLite句柄后可正常清理，正式数据不受影响。
