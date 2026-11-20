# 模型文档请求超时调查

日期：2026-11-18 18:04（Asia/Shanghai）。范围为用户反馈的导入超时诊断，不修改产品行为，不重试收费请求，不构建新安装包。

## 实际任务证据

通过 SQLite `mode=ro` 与 `PRAGMA query_only=ON`，只读当前软件任务的时间、状态和模型参数；没有读取论文正文、笔记、原始模型响应或系统凭据。为核对上传体量，仅对任务登记的源文件执行文件大小查询，没有读取文件内容。脱敏汇总见本地 [runtime-summary.json](../.local/verify/document-timeout-investigation-20261118/runtime-summary.json)，不包含论文题名、文件路径或任务标识，不进入 Git。

| 项目 | 实际值 |
| --- | --- |
| 任务 | PDF 导入，第一次执行，failed |
| 创建时间 | 2026-11-18 17:57:06.956 +08:00 |
| 失败更新时间 | 2026-11-18 17:58:37.148 +08:00 |
| 创建到失败 | 90.191 秒；包含排队/准备，不能冒充精确 HTTP 耗时 |
| 服务 | 火山方舟，`ark.cn-beijing.volces.com` 的 `/api/plan/v3` |
| 模型 | `deepseek-v4.1-flash` |
| 冻结超时 | `timeout_seconds=90` |
| 冻结推理参数 | `reasoning_effort=max` |
| 输入方式 | `modality=pdf`、`document_input=image`、`document_transport=chat_file` |
| 文件大小 | 1,279,798 bytes，约 1.22 MiB |
| 错误 | “模型文档请求超时”，`MODEL_DOCUMENT_PROVIDER_ERROR` |

此前两次失败发生在能力声明检查，均少于 0.5 秒；此次已经进入文档网络请求。不能把当前失败归为旧能力声明未保存。

## 代码机制与复现

`services/engine/researchgraph/providers.py` 的 `complete_document` 将整份 PDF 编码后，以 `type=file` / `file_data` 发送到 `/chat/completions`；`stream=False`，要求一次返回章节、段落、公式、表格的完整 JSON。没有按页图片输入或分页分批请求。

HTTP 参数为连接 15 秒、读取/上传/连接池各 90 秒；另有 180 秒总时限。四种 `httpx.TimeoutException` 子类被统一映射为“模型文档请求超时”，外层总时限则显示“模型文档请求达到总时限”。默认 90 秒由 `model_settings.py` 定义，后端范围 5–180 秒；界面目前没有修改超时的输入控件。

离线 [timeout-harness.py](../.local/verify/document-timeout-investigation-20261118/timeout-harness.py) 使用匿名合成 PDF 和 `httpx.MockTransport`，实测 **5 cases passed**，真实网络与模型调用均为 **0**。输出见 [timeout-harness.json](../.local/verify/document-timeout-investigation-20261118/timeout-harness.json)：

| 注入情况 | 实际提示 |
| --- | --- |
| ConnectTimeout | 模型文档请求超时 |
| ReadTimeout | 模型文档请求超时 |
| WriteTimeout | 模型文档请求超时 |
| PoolTimeout | 模型文档请求超时 |
| 单独触发总时限 | 模型文档请求达到总时限 |

## 结论与不确定项

已确认直接原因是 HTTP 交互的超时分支。实际任务 90.191 秒与 90 秒读取/上传阈值高度吻合，不符合单独连接 15 秒或总时限 180 秒的典型时长。最可能候选是非流式整篇输出期间长期等待响应；上传停滞仍无法排除。`reasoning_effort=max` 是潜在耗时因素，但供应商实际是否采用此参数、当时是否排队，现有证据均不能确认。

当前错误未保存异常子类、上传完成时刻、响应头到达时刻、响应字节数或供应商请求 ID。失败 parse 的 started_at/finished_at 都是记录失败时刻，不能据此计算请求耗时。provider 的 input_bytes 在嵌入 PDF 前统计，也不能当实际上传大小。HTTP 不兼容若正常返回 4xx 会走拒绝提示；本次 timeout 既不能证明 PDF 格式受支持，也不能单凭超时证明不受支持。

18:02:57 的无凭据 DNS/TCP/TLS 探测通过：火山约 0.062 秒，腾讯约 0.094 秒，两者均完成 TLSv1.3。见 [connectivity.json](../.local/verify/document-timeout-investigation-20261118/connectivity.json)。仅建立连接，没有发送 HTTP、PDF 或模型请求。它说明调查时基本直连可达，不证明失败当时状态、模型处理速度或文件兼容性。软件客户端 `trust_env=False`，不自动读取环境 HTTP 代理。

## 后续处理建议

1. 先补安全诊断：保存 timeout 子类、实际阶段、耗时/阈值、上传完成及响应开始时间；不记录凭据、论文正文或 Base64。
2. 为文档解析提供独立可调读取/总超时，界面显示本次任务冻结配置。单纯增加 90 秒并不能解决文件格式不兼容。
3. 按实际端点适配其支持的文件/图片输入。若走按页图像路径，本地仅渲染页面，正文、公式和表格由模型识别，并采用有界分批与完整性检查。
4. 旧任务“重试模型解析”仍复用原快照；修改配置后应通过“使用模型重新解析”创建新任务。调查未自动重试、未修改用户设置或数据。

本轮仅更新调查文档/进度/开发日志和隔离证据，153 项已交付运行源/配置保持原样；没有 Commit/Push、新包或新的真实模型调用。用户此前任务本身已经发生的供应商调用及费用不因本轮零调用而记为零，实际处理状态和费用仍需供应商账单核对。

最终检查：私人路径规则/Gitleaks **371 files passed**，`git diff --check` 通过；本报告 **4 个链接 / 0 missing**，离线复现5项结果核对通过。未改运行源，因此没有重复执行上一轮全量后端/React/安装回归。
