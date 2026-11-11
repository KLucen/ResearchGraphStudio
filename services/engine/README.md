# 本地 Lite 研究引擎

researchgraph 实现 FastAPI 鉴权、Lite 项目/任务、SQLite 单写入者、Zotero 读取、PDF/章节解析、FTS5 索引、Provider 配置、统一用量、PaperCard + LightGraph、章节导读、证据问答及可选 PDF 翻译。

开发使用 Conda 环境 `researchgraph-studio`。主 Sidecar 使用 PyInstaller onedir 打包；用户运行不依赖 Conda。默认翻译运行时另以官方 Windows 发行包完整分发，含嵌入式 Python、PDFMathTranslate-next 2.10.2、BabelDOC 0.7.1 与离线字体/模型资源，不要求用户配置 Server/Python 路径，不向 base 安装依赖。

Lite 数据库为 `researchgraph-lite.sqlite3`，当前 head `lite0008`。本轮是已有 Lite 库的加性升级，升级前自动备份，不重新初始化或删除已有论文、成果、布局、译文或任务。旧完整系统数据库仍与 Lite 库隔离，完整抽取、跨论文推理、Lint/Wiki 不属于活跃服务。

`pdf_translation` 使用 `launch_mode=bundled|managed|manual`，新任务默认 `bundled`。原创 adapter 调用随包官方 CLI；`translation_proxy.py` 负责一次性票据、冻结模型配置、文本请求预算、实际 usage 与取消。PDF/排版在本机，模型仅接收文本和提示；真实 Key 不交给排版引擎。高级模式兼容专用 Server 4.1.8，旧外部路径保留。

`output_mode=dual|mono|both` 绑定预检和缓存，新 UI 默认 `dual`，旧无字段请求/记录保持 `both`。历史 runtime snapshot 不回写，无快照按 `manual` 处理。仅用户明确非缓存提交启动进程；预检、GET、缓存读取不启动。正常任务验证所选产物、回收自建进程树后才发布完成；失败、取消及退出同样回收，不接管用户已有服务。

`scripts/prepare-translation-runtime.ps1` 校验固定来源与关键文件，准备默认 Tauri 安装资源目录；源码包、原始许可和构建说明随资源分发，不进入 Git。详情见 [文献翻译](../../docs/pdf-translation.md)、[ADR0038](../../docs/adr/0038-bundled-translation-and-reading-layout.md) 与 `scripts/translation-runtime-notices.md`。

本轮真实模型调用为 0。准备资源校验、实际引擎合成联调、隔离安装、真实翻译质量是不同验证范围，具体结果以 [进度](../../docs/progress.md) 为准，不把合成调用记作真实 Token 验收。
