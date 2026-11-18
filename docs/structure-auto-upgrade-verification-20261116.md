# 旧章节结构自动升级验证 · 2026-11-16

## 触发原因

已有 Lite 数据库中的论文可能只有 `pymupdf/...;structure-v1`。该版本会把印刷目录中的章节题名写入当前章节树，同时漏掉部分正文标题。因普通读取复用旧树，用户会看到 `1 INTRODUCTION` 后直接出现 `5 CONCLUSION`，并看到目录材料中的重复 `5 Conclusion`。这是旧解析存档未升级造成的投影问题，不是前端目录折叠排序，也不表示 PDF 缺页。

## 本轮实现

- 新增 `services/engine/researchgraph/structure_upgrade.py`，只在当前解析版本不是 `structure-v2` 时执行一次本地升级。
- `reading-document`、`revisions/{revision_id}/sections` 和结构读取入口先检查旧版本，再使用已登记且 SHA 一致的 PDF 调用现有结构扫描、`apply_structure` 与索引重建。
- 升级前后均重新核对论文、revision 和来源 SHA；解析失败、源文件缺失或数据库忙时保留旧树，不删除 Chunk、Span、历史结果、用量、笔记或外部 PDF。
- `structure-v2` 已存在后，普通 GET 不再扫描 PDF；升级过程不调用模型，也不创建模型任务或 Token 记录。

## 隔离测试

当前已完成的定向测试：

- `tests/engine/test_structure_versions.py`：22 passed / 1 warning。
- 覆盖结构升级函数、章节列表 GET、全文阅读 GET、二次读取不重复扫描、旧结构数据保留与当前章节优先级。

完整结果：

- `conda run -n researchgraph-studio pytest -q tests/engine`：348 passed / 1 skipped / 1 warning，95.31 秒。跳过项为既有 Windows 符号链接权限条件，warning 为既有 Starlette/httpx 弃用提示；自动升级组合回归为 38 passed / 1 warning。
- Ruff、Ruff format、mypy（65 个源文件）、pip check、TypeScript/ESLint/Prettier 和 React 9 个测试文件 86 项通过；Vite 生产构建通过，保留约 592.08KB 单 chunk 提示。
- `scripts/build-windows.ps1` 的 PyInstaller、Tauri、NSIS 构建通过。PowerShell 5.1 隔离静默安装、lite0010 健康握手、匿名 PDF 导入、章节索引和 0 模型调用检查通过。
- 未签名安装包：`.local/releases/lite-structure-auto-upgrade-20261116/ResearchGraph-Studio-Lite-Structure-Auto-Upgrade-0.0.1-x64-setup.exe`，38,575,252 bytes，SHA-256 `18523C9D4EF784EB310B8CC6F6F24194322710C7E8910AD30BE23C82D175A147`。完整 sidecar 的引擎 EXE SHA-256 为 `A93FC736474AA785C5B3C4D361C0AAEC4085B1459027A1B91B26B6896C995DCA`。
- 真实模型调用、真实 Token、重试和费用为 0；隔离测试只使用匿名 PDF、SQLite 和合成响应。没有访问或修改正式数据库。

## 边界

自动升级仍依赖可读取的原始 PDF。若 Zotero/登记路径不可用或文件字节已变化，应用继续显示可验证的旧本地存档并提示重新整理；不会把新文件静默绑定到旧 revision。扫描页 OCR、公式恢复、复杂版面和表格语义仍按现有边界处理。

## 2026-11-16 后续修复

用户继续反馈旧包界面仍显示 `1 INTRODUCTION` 后直接到 `5 CONCLUSION`。为覆盖正文标题与普通段落使用相同字体的论文，`pdf_structure.py` 现在会从已标记的印刷目录行提取规范化标题、层级和近似页码，并仅在正文页精确匹配时恢复标题。目录材料继续留在材料区，不会成为重复章节。`PaperCloseReading` 在全文阅读投影完成后失效章节查询，解决结构升级与目录请求并发时的旧缓存窗口。

新增回归覆盖：非粗体一级/二级/三级正文标题恢复、目录行不重复显示、全文投影完成后刷新目录。解析和结构专项为 `48 passed / 1 warning`，前端 `PaperCloseReading` 与 `ReadingOutline` 为 `19 passed`；后端全量为 `349 passed / 1 skipped / 1 warning`，真实模型调用和 Token 仍为 0。

更新后的未签名 Windows 安装包：

- `.local/releases/lite-structure-outline-repair-20261116/ResearchGraph-Studio-Lite-Structure-Outline-Repair-0.0.1-x64-setup.exe`
- 安装器 SHA-256：`854B436EEB2C50D987A4D416F03AD4F0359EB25691570F9016CF956A3E4F9CA6`
- sidecar `researchgraph-engine.exe` SHA-256：`01E5B9A09A21522AA61733A72F8D9EC83655F0C5BA235F5BA660C7582E06F127`
- sidecar 文件数：265（必须与 `_internal/` 一起使用）
- PowerShell 隔离安装和 Lite 健康/匿名 PDF/0 模型调用验收通过，验证结果位于 `.local/verify/lite-structure-outline-repair-20261116-run2/verification.json`。
