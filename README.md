# ResearchGraph Studio Lite

ResearchGraph Studio Lite 是一个本地论文阅读辅助工具。它把 Zotero 或本地 PDF 转成可检索的章节和文本索引，再按需生成论文概览、章节导读和局部证据问答。论文选择、PDF 解析和全文索引都在本机完成；没有明确请求时不会调用模型。

当前工作区已经切换到 Lite 基础工程：

- **本地阅读**：连接 Zotero、选择论文、解析 PDF、识别跨页章节、建立 FTS5 文本索引。
- **论文概览**：PaperCard 与 LightGraph 使用一次联合模型调用生成；缓存命中不重复调用。图谱是单篇论文的概念组织，不是独立证据验证。
- **文献翻译**：安装包自带 PDFMathTranslate-next 2.10.2、BabelDOC 0.7.1 与离线字体/模型资源，无需配置外部 Server/Python。复用已有模型 API，按需生成双语、中文或两种 PDF；新界面默认双语，预检、查看和缓存命中不调用模型。高级外部连接仍保留，真实翻译质量单独验收。
- **模型与用量**：设置与诊断中分开管理全局 Provider/Base URL/API Key 连接和模型参数配置；凭据保留在本机凭据存储中，统一记录输入/输出/总 Token、调用、重试、缓存命中和费用未知状态。
- **数据边界**：Lite 数据库从空库初始化，不迁移旧版完整图谱、Query、Lint、Wiki 或历史任务。旧工程回退点保存在 `backup/pre-lite-refactor`。

阅读工作区位于论文页面上方，论文信息收纳到下方默认折叠区域。当前 `lite0008` 升级在已有 Lite 库上自动备份并增量更新，保留原有论文、成果、布局与历史任务；这与早期从完整旧工程创建干净 Lite 库是不同阶段。

## 文档

- [Lite A+B+D 规范](docs/researchgraph_lite_ABD/README.md)
- [LightGraph 补充规范](docs/ResearchGraph_Lite_LightGraph_Addendum/README_ADDENDUM.md)
- [当前项目基线](docs/current_project_baseline.md)
- [清理盘点与保留范围](docs/lite_cleanup_inventory.md)
- [开发进度](docs/progress.md)
- [模型配置](docs/model-configuration.md)
- [文献翻译设置与使用](docs/pdf-translation.md)
- [安全检查](docs/security-checks.md)

当前活跃迁移 head、已完成阶段和未完成范围以 [docs/progress.md](docs/progress.md) 为准。

## 开发环境

Windows 环境使用 Conda 环境 `researchgraph-studio`、Node 24、pnpm 12 和 Rust 工具链。依赖由 `environment.yml`、`conda-win-64.lock`、`requirements-win-64.lock`、`pnpm-lock.yaml` 和 `Cargo.lock` 固定。

```powershell
conda create --name researchgraph-studio --file .\conda-win-64.lock
conda run -n researchgraph-studio python -m pip install --require-hashes -r requirements-win-64.lock
pnpm install --frozen-lockfile
pwsh -File .\scripts\check-phase0.ps1
```

启动桌面开发环境：

```powershell
pwsh -File .\scripts\dev.ps1
```

应用数据写入用户本地的 Lite 数据目录。Zotero 原始附件和私人笔记仍由用户的本机应用管理，不进入 Git。

## 约束

`unknown` 表示信息缺口，不据此推断实验条件、矛盾或数字。模型只能返回受 Schema 约束的内容；正式 ID、来源定位、文件路径、数据库写入和缓存键由本地程序生成和校验。
