# Phase 1 来源与证据开发记录

更新时间：2026-10-30（Asia/Shanghai）。G0 已按用户决定放行，依据 [ADR 0004](decisions/0004-g0-waiver-phase1.md)。当前为 Phase 1 首个可运行增量，未宣称 M1 全部完成。

## 本轮范围

打开研究项目后，在“文献与原文”选择 PDF。默认引用原文件；选择“复制到项目存储”才保存托管副本。任务列表显示排队、解析、失败、取消和重试；已导入文献可查看附件修订、哈希、解析器版本、页码、原文块和块级坐标。

原生宿主打开文件选择器并提交所选路径，通用前端 HTTP 桥不允许直接调用文件导入路由。引擎 API 仍要求私有 Bearer 令牌。解析仅在本机执行，不调用模型，不读取 Zotero 或个人笔记。

- 迁移 0002：papers、paper_sources、attachment_revisions、chunks，Job 保存项目和导入参数。
- 文件名只用作暂定标题，不作为文献身份；不猜测 DOI 或作者。
- 同项目相同内容去重；不同路径保留映射；同一路径内容变化追加修订，旧块及哈希不覆盖。
- 原文按 PyMuPDF blocks 排序保存。字符定位目前是块内 Python Unicode 字符索引；文本不做归一化。块坐标不是精确字符框。
- 每份最多 50 MiB / 300 页 / 200 万字符，解析超时 120 秒，任务最多三次尝试；不执行 OCR。无文本页、损坏、加密、丢失文件均有实际状态提示。

## 验证与样本

`tests/fixtures/pdf/` 为项目自造 CC0 样本；生成脚本为 tests/fixtures/make_pdf_samples.py。包括两页文本、图片页、加密文件和故意损坏文件，不含用户文献。

本机已通过：20 项 Python 测试（含从 0001 升级与备份、故障回滚、跨页块定位、去重、历史修订、项目隔离、失败不留半成品、取消后重试、运行中取消/退出终止子进程）、7 项 React 测试、1 项 Rust 路由测试及 fmt/clippy；冻结引擎在仅系统 PATH 下完成托管导入和重启文本读回，[Windows PowerShell 5.1 报告](environment/2026-10-29-phase1-powershell.json)亦通过 PDF 导入/重启和 EOF 退出。

2026-10-30 原生窗口复核：使用独立标识 `com.researchgraph.studio.phase1test` 启动调试构建，读回此前保存的验收项目和样本。通过原生文件选择器再次导入 two-pages.pdf 后，两次任务均完成，项目仍只有一篇文献；详情显示一致的 SHA-256、两页原文、S-1/S-2 页标签及 72%/81% 样本数值。此结果来自开发机，不代替干净 Windows 验收。

[CI 40930522934](https://github.com/KLucen/ResearchGraphStudio/actions/runs/40930522934) 已全部通过，对应实现提交 `9b7a306be1e73e0392e81b6a576706d3aa712042`：Windows runner 重建依赖并通过 20 项 Python、7 项 React、1 项 Rust 测试、静态检查、契约和打包引擎验证，生成 NSIS；另一 runner 通过安装、PDF 导入、项目/原文重启读回、鉴权、诊断、宿主启动/单实例/正常退出/崩溃清理及卸载。见 [CI 摘要](environment/2026-10-30-phase1-ci.json)和[原始安装报告](environment/2026-10-30-phase1-installed.json)。

CI 安装器 37,606,027 字节，SHA-256 `DBE45D7678F387D3B28AAC1D762BC86BEF9A2ED5BF64A13760682FE45B87FC89`；已下载并核对官方 artifact ZIP 摘要与安装报告。开发机 `.local/phase1-acceptance-kit.zip` 保存该安装器、样本、脚本和说明，未提交二进制；未覆盖原有本机安装。

解析实现依据 [PyMuPDF 官方文本抽取文档](https://pymupdf.readthedocs.io/en/latest/recipes-text.html)，版本固定为 1.26.7；原文块阅读顺序可能受 PDF 排版影响，不能视为语义阅读顺序已验证。

## 剩余工作

1. RG-006 后续：来源可用性/内容变化显式检查，来源重定位界面、异常退出后临时缓存回收、任务阶段进度及更多真实 PDF 质量样本。当前任务列表从全局最近 50 项中筛选本项目并显示最近 10 项，需补项目级分页历史。
2. RG-007：Evidence/span 对象、跨页引用、断词及归一化映射、原页面高亮、人工校正的新版本和原因记录。
3. M1：完整安装版导入与证据定位验收；G0 未执行的干净 Windows 和缺 WebView2 实测留在发布检查中。

当前原文块可回看，但尚不能创建或接受 Claim/Relation；不能把“导入完成”理解为证据审核通过。
