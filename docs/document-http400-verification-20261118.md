# 分页边界HTTP400修复验证

日期：2026-11-18（Asia/Shanghai）。当前决策见[ADR0053](adr/0053-boundary-json-compatibility-recovery.md)，分页基础见[ADR0052](adr/0052-resumable-document-batches.md)。

## 只读调查

任务元数据显示正文3批均HTTP200/validated，负责原页1–5、6–9、10–13，耗时分别301.797/270.109/358.829秒。第一个边界原页5–6连续3次HTTP400，最近于21:25:53.934开始、约1.218秒被拒绝；因此继续时重复的是边界复核，已成功正文没有重发。请求为火山/api/plan/v3、deepseek-v4.1-flash、chat_file、json_object。未读正文或凭据，未重新发送真实请求；脱敏证据在.local/verify/document-http400-20261118/runtime-summary.json，不含论文题名、路径、任务ID或credential_ref值。

边界提示缺少JSON指令，而接口JSON Object要求输入包含json；合成端点复现，文件与图片修复回归各恰好1次POST。实际旧400响应正文已被旧版丢弃，因此不能宣称已取到供应商明确报错参数；本次根因是高度匹配任务阶段的可复现请求缺陷。

## 改动与回归

providers边界提示补有效JSON对象；安全metadata加入boundary_prompt_version。新document_batch_recovery只读判断旧400资格；文档worker请求前持久记账、防崩溃重复，保留成功正文及3次旧账本，允许已耗尽旧边界显式恢复一次。全局/项目/详情GET均只读投影，普通和计划项retry拒绝已经耗尽且不符合资格的任务。UI区分边界/正文进度，400提示停止重复点击并显示安全状态。

恢复专项40 passed /1既有warning（15.39秒），覆盖旧3次后只请求边界、材料/页码/账本不变、修复版失败后零请求拒绝、GET无写入、发送前取消不耗恢复资格、两个retry入口及幂等。新HTTP传输专项104 passed /1既有warning（5.80秒）。最后取消保护修正后完整后端重新执行 **576 passed /1 skipped /1 warning（139.99秒）**，React全量15 files /147 passed（16.72秒），Edge19 passed（18.9秒）；Ruff/mypy86/TypeScript/ESLint/契约导出通过。跳过项和既有Starlette/httpx deprecation单列，不计通过。

独立审查发现全局历史漏投影和not_sent覆盖旧元数据两处P2，均已修正并加回归；最初中间构建在最后修正前启动，不交付该构建。发现历史和修复确认在recovery-audit.txt保留。

## 最终安装验证

最终未签名Windows包于21:46:26构建，安装器为 [Boundary HTTP400 Fix](../.local/releases/document-boundary-http400-20261118/ResearchGraph-Studio-Boundary-HTTP400-Fix-0.0.1-x64-setup.exe)，160,516,874 bytes（153.08MiB）。161项运行源/配置构建前冻结，构建后及安装验证后保持一致，sidecar和324项内部资源逐文件匹配。

- Windows PowerShell5.1实际隔离安装通过，schema lite0013；旧本地清理、同paper_id重建、模型材料/章节已读保留、删除及引用PDF保留通过。只安装至.local隔离目录。
- 安装版旧任务恢复：chat_file/chat_images各成功与仍400两例，共4例通过。原extract3检查点逐字节不变，仅新增1个boundary POST，旧3次账本完整保留加新1条、attempt/request_count=4；JSON指令与版本2标记正确。失败例再次job/item重试均409、零新POST。GET只读，全部重启零POST，进程/假服务正常退出。
- 安装版普通分页两种传输均通过，3批抽取+1纯文本修复+1边界、6材料覆盖7页，重启无追加请求，确保修复没有破坏正常链路。安装Host14 passed /0 ignored（3.68秒），含真实sidecar启动/重启。

全部HTTP验收只用127.0.0.1模拟端点和匿名合成PDF。证据在本轮.local验证目录下installed-acceptance、legacy-smoke-installed-file/images、smoke-installed-file/images、host-final.log和artifact-verification.json。真实服务修复后尚未调用，不冒充实测供应商恢复。

## 使用

1. 退出软件并安装本轮修复包，重新打开原论文/任务。无需删除论文或重新导入。
2. 确认显示正文已完成、边界复核失败后，点击“确认继续边界复核（可能收费）”或论文模型解析中的对应按钮。只重验并复用成功批次，再继续未完成边界。
3. 修复版仍400时停止重复点击，保留安全状态用于进一步调查；已耗尽的兼容恢复会被拒绝，不自动重新解析正文。

真实修复后的服务请求、论文科学质量、用户原生GUI与干净机尚未验收。用户此前实际请求及费用不因本轮新增模型请求0而记成0。本轮未修改正式库/配置或任务状态，未Commit/Push。
