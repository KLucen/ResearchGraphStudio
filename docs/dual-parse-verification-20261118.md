# 双解析与模型能力配置验证

日期：2026-11-18（Asia/Shanghai）。决策见 [ADR0050](adr/0050-explicit-local-and-model-parsing.md)。

## 实际修复

- 保存模型时保留明确声明的 PDF/文档输入、文件传输和多模态能力；编辑提供商不再用默认参数覆盖已有声明。手填数值限额仍不被当成端点能力。
- 设置新增独立“论文解析模型”和每模型文件能力声明。用户声明的文档能力优先于 `/models` 自动发现；文本连接测试仍仅证明固定文本 JSON 通道。
- PDF/Zotero 默认本地解析，不传模型生成计划，不触发模型。模型模式才显示概览/精读/可选中文翻译及发送授权。
- 论文页新增“本地解析 / 重试”和“使用模型重新解析”，沿用已登记源文件，绑定已有论文 ID。模型重新解析使用新 ImportSession 与当前模型设置，历史结果保持。
- 本地清理后的显式重新解析恢复缺失 Chunk/章节/FTS 并清除清理标记，不新建重复论文，旧笔记和个人记录保留。
- 可切换查看已有本地和模型材料；模型失败不删除或隐藏本地材料。修改配置后的操作说明区分旧任务重试与当前配置重新解析。

## 最终验证

| 验证 | 实际结果 |
| --- | --- |
| 完整引擎 `python -m pytest -q --tb=short` | 429 passed / 1 skipped / 1 warning，98.01 秒 |
| React `pnpm --dir apps/desktop test` | 12 files / 109 passed，15.14 秒 |
| Edge `pnpm --dir apps/desktop test:browser` | 16 passed，12.5 秒 |
| Ruff / mypy | 全引擎 lint 通过；mypy 79 files 通过 |
| TypeScript/ESLint / 契约导出 | 通过；导出使用项目 Conda 与 `PYTHONPATH=services/engine` |
| 安装后 Rust Host | 14 passed / 0 ignored，2.90 秒，含实际 sidecar 启动/重启 |
| 最终交付检查 | 私人路径/Gitleaks 内容扫描 370 files 通过；`git diff --check` 通过；153 项运行源/配置不变；本轮三份文档 10 个链接无缺失 |

后端新增 7 项 API/实际本地解析专项，覆盖本地建库、清旧后重建、同 paper_id、幂等、活动任务冲突、模型新快照、无授权/任意 UI 路径拒绝，以及模型失败后本地恢复与重试。模型设置补验声明保存、重启、纠正回文本、旧快照不变及 metadata 不覆盖显式声明。唯一 warning 为既有 Starlette/httpx TestClient deprecation；跳过项保持跳过。

真实 React/Edge 新用例验证默认本地、没有模型生成选项、选择模型显示解析模型、局部失败重试、滚动后模态窗口仍在视口内、发送前需授权和实际请求 DTO。匿名浏览器 native bridge 与 Provider 使用合成响应；不代表真实供应商接收 PDF。

## 安装包

[ResearchGraph-Studio-Dual-Parse-0.0.1-x64-setup.exe](../.local/releases/dual-parse-20261118/ResearchGraph-Studio-Dual-Parse-0.0.1-x64-setup.exe)，**160,435,399 bytes**，未签名。完整 `scripts/build-windows.ps1` 成功；153 项运行源/配置构建前后不变。安装后 sidecar 与 322 项 `_internal` 资源逐文件一致。内部打包指纹只用于交付核对，不是论文导入门槛。

Windows PowerShell 5.1 执行 `scripts/verify-windows-install.ps1` 在唯一隔离目录实际安装并通过：schema `lite0012`；清旧后调用新解析 API 恢复本地块，结果仍是同一 paper_id，再清理成功；3 段模型材料、COMPLETED 章节状态在清旧后保留，整篇删除后状态 404，引用源 PDF 保留，真实模型调用 0。新增 local-reparse 断言实际执行，不凭报告字段推断。

日志与包资源核对在 `.local/verify/dual-parse-20261118/`，汇总为 [final-summary.json](../.local/verify/dual-parse-20261118/final-summary.json)。安装器、隔离数据和日志不进入 Git。

## 限制与操作

真实模型调用、Token 与费用 0，未访问正式用户数据库、私人论文、Zotero 正式库或 API Key。用户截图所用端点/模型的 PDF 实际支持情况未验收，不因为选择多模态策略或联网授权就宣称支持。需提供商实际接受当前 Chat Completions 文件内容请求；不支持时使用本地解析并保留错误。真实论文章节/公式/表格质量、桌面 WebView 原生操作及干净机兼容仍待单独验收。

安装后先在“设置与诊断 → 模型 → 编辑提供商”保存实际文档能力，再选择“论文解析模型”；旧失败任务沿用原快照，应在论文页使用“使用模型重新解析”以采用新配置。仅需本地库可直接选择本地解析。schema 保持 `lite0012`，没有新增迁移。本轮未 Commit/Push。
