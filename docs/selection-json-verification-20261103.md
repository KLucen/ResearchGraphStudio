# P13 JSON 响应恢复验收（2026-11-03）

本轮仍属 R5，修复用户报告的 `Expecting ',' delimiter: line 1 column 4359 (char 4358)`。没有进入 P4/P5，没有新增上下文预算或数据库迁移。设计见 [ADR0016](adr/0016-selection-json-syntax-recovery.md)，先前完整上下文策略继续按 [ADR0015](adr/0015-complete-reading-context.md) 生效。

## 实际根因

正式库只读备份中找到唯一匹配的失败任务：P02 已完成 34/34 批，P12 已完成 10/10 整合检查点，前 4 组 P13 已成功。失败在第 5 组自动核心选择，不在 PDF 解析或候选抽取。原始响应为 4359 字符，最后已有根对象 `}`；末字段 coverage_gaps 的非空字符串数组缺少一个 `]`，解析器在字符 4358 报错。

该请求约 26.437 秒，历史记录没有 timeout/output_limit 错误，历史 finish_reason 未持久化，不能反推为 stop，也不能将此次问题写成最大输出不足。原响应插入唯一缺失的 `]` 后，8 条建议、10 条缺口、文献版本、输入 revision 和全部根 ID 均通过原有校验；没有改写科学内容。

## 实现与边界

- `reading_json.py` 仅识别根末 coverage_gaps 非空完整字符串数组、根 `}` 已存在且只漏一个 `]` 的情况。使用 JSON token 解码识别字符串边界，不平衡通用括号，不补逗号、引号、EOF 或科学字段。
- P13 正常及恢复后解析都拒绝重复键（包括转义后同名）与 NaN/Infinity，避免后值静默覆盖。恢复结果继续经过完整 Schema、白名单、文献版本、输入快照及 KnowledgeStore 校验。其他阶段不套用此语法恢复。
- raw_output 逐字符保留；`ModelRun.parameters.integration_normalization` 记录规则、插入字符、Unicode 字符 offset、原始/恢复结果 SHA-256。它不是重新生成的模型输出。
- `reading_pipeline.py` 复用原失败响应，成功保存选择检查点时清空旧 error 并设置 finished_at。已成功 P02/P12/P13 不重调。
- `extraction_repair.py` 将 JSON 失败呈现为不回显私人正文的中文诊断；`providers.py` 为新调用记录实际 finish_reason，不补写历史事实。

Prompt、reading-extraction-1.0、reading-compact-1、Alembic head 0011、旧任务签名和冻结计划不变；本轮没有扩大超时或重新引入固定上下文预算。

## 正式数据隔离恢复

所有执行在 `.local/reading-json-20261103/` 的只读备份及隔离副本完成，未写入正式库、PDF、Zotero 或凭据。匿名结果保存为 `recovery-report.json`，私人响应、数据库和诊断脚本不进入源码。

| 验证 | 实际结果 |
| --- | --- |
| 已成功阶段 | P12 10/10、前 4/4 个 P13 检查点精确复用；P02/P12 没有模型调用 |
| 第 5 组失败响应 | 仅在 offset 4358 插入 `]`，8 条建议及 10 条缺口保持，通过严格 JSON、Schema、版本与根白名单检查 |
| 恢复状态 | 原 ModelRun 变为 succeeded，error 清空，完成时间设置；原 raw、usage、传输参数保持，审计双 hash 正确 |
| 新记录 | 仅新增第 5 组 selecting 检查点；在第 6 组无网络 Probe 边界主动停止 |
| 数据保持 | 其他表、旧检查点、其他 Job/ModelRun，以及原 Job 的 payload、冻结计划、窗口和 result 保持 |
| 外部调用 | 真实网络及模型调用 0；Probe 只是下一组的调用边界，不能写成真实模型成功 |

上述检查证明已收到响应可在本地安全续用，不代表后续第 6 组或全文已完成，也不代表后续模型请求免费。

## 自动化与构建

Python 全部使用 Anaconda `researchgraph-studio` 环境。

| 检查 | 实际结果 |
| --- | --- |
| 最终完整 Python | **317 passed / 2 skipped**；两项文件符号链接场景受 OS 权限限制 |
| 本轮 JSON 定向测试 | **30 passed**；涵盖唯一恢复形态、转义/中文、双 hash、15 类拒绝边界、正常/恢复分支重复键、Schema 拒绝、旧失败响应零调用续用及成功清错 |
| Python 静态/依赖 | Ruff、格式、mypy 73 个源文件、pip check 通过 |
| React / 前端 | **47 passed**；类型、ESLint、Prettier、契约生成和生产构建通过 |
| Rust | **9 单测通过**；另行执行的 **1 项打包宿主握手、退出与重启测试通过** |
| 打包 | PyInstaller、Tauri、NSIS 通过；冻结引擎 smoke 通过 |
| PowerShell 5.1 | EnginePath 五项通过，子进程 PATH 仅 System32 |

首轮全检查为 311 passed / 2 skipped、47 React；独立复核发现普通 JSON 路径会接受重复键后，收紧 P13 并补 6 项测试，最终全量为 317 passed / 2 skipped。没有将首轮结果当作最终代码测试。

首次误用 Windows PowerShell 5.1 执行无 BOM 的 UTF-8 构建脚本，脚本解析阶段失败，未完成构建；使用原工程指定的 `pwsh` 重跑后成功。没有改变系统执行策略。前端单 chunk 大于 500 KiB 和既有 Starlette/httpx 弃用提示仍在。新包没有重新执行完整安装/卸载或干净机验收；本轮没有 Computer Use。

主要命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-phase0.ps1
& 'C:/Users/KLucen/anaconda3/envs/researchgraph-studio/python.exe' -m pytest -q
& 'C:/Users/KLucen/anaconda3/envs/researchgraph-studio/python.exe' -m pytest -q tests/engine/test_reading_selection_json.py
& 'C:/Users/KLucen/anaconda3/envs/researchgraph-studio/python.exe' -m ruff check services/engine tests/engine scripts
& 'C:/Users/KLucen/anaconda3/envs/researchgraph-studio/python.exe' -m ruff format --check services/engine tests/engine scripts
& 'C:/Users/KLucen/anaconda3/envs/researchgraph-studio/python.exe' -m mypy
pwsh -NoProfile -File scripts/build-windows.ps1
& 'C:/Users/KLucen/anaconda3/envs/researchgraph-studio/python.exe' scripts/smoke-engine.py --executable .local/engine-dist/researchgraph-engine/researchgraph-engine.exe
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml packaged_engine_connects_through_native_host_and_restarts -- --ignored
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/verify-windows-install.ps1 -EnginePath .local/engine-dist/researchgraph-engine/researchgraph-engine.exe -OutputRoot .local/reading-json-20261103/ps51-engine
```

宿主测试的 `RGS_TEST_ENGINE_PATH` 指向本轮刚构建的 Sidecar。最终日志、匿名检查点报告和 delivery.json 与安装包一同保存在本机 release 目录。

## 安装与继续

安装器：`.local/releases/selection-json-20261103/ResearchGraph Studio_0.0.1_x64-setup.exe`，**38613488 字节**，SHA-256：

```text
be5a49d39aa8707781e1f0346c7cb92970f4f660209ce949ea1abcf8fe675420
```

退出软件后安装修复包，重新打开原项目，在原失败任务点击“继续未完成批次”。无需删除知识、重新导入 PDF 或新建全文抽取任务。程序应复用抽取、整合和已成功选择检查点，本地重验第 5 组原响应后继续剩余选择；剩余阶段按实际需要调用配置的真实模型并计费。

尚未替用户安装或执行正式库续跑，后续真实模型选择、全文质量和用户原生体验待反馈。四份已登记补充原文路径仍不可用，未记为核验通过。本轮未暂存、Commit 或 Push；源码不包含私人材料、响应、运行库、密钥、日志和安装产物。安全与链接检查最终结果见 progress 及开发日志收尾补记。

13:59 收尾检查：509 个源码候选文件通过路径核对及 Gitleaks 内容扫描；150 Markdown、522 本地链接、88 份既有清单资产核验通过，四份已登记外部原文不可用限制保留。git diff --check 通过，暂存区为空。安装器复制后长度与 SHA-256 和 delivery.json 一致，最终严格解析版本再次隔离重放通过，真实调用仍为 0。
