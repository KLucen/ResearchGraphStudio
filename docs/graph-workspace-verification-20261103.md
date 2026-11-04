# 图谱工作区、颜色与多论文验收

2026-11-03（Asia/Shanghai）。本轮继续 R5，不进入 P4 Query/P5 Lint/Wiki。用户报告已在真实安装版跑通 3 篇论文，记录为用户实测反馈；本轮不重复请求模型、不读取正式库或私人论文，不把该反馈推断为独立科学质量或 native strict API 验收。

## 问题与改动

1. 白色节点：原 ForceGraph 只为 5 种类型配置背景，Experiment/Condition/Finding/Metric/Argument/Limitation 露出 React Flow 默认白底。新增 graphAppearance 单源类型表，全部 11 类及未知类型都有回退颜色；画布上方横向图例与节点/筛选共享中文名称和颜色。颜色表示类型，不表示审核或科学真假。
2. 多论文首屏：旧分页按 paper_id 排序，第一篇超过 60 个主节点便挤掉其他论文。reading_projection 改为各论文轮换、每篇先中心并交替结论与支撑；仍默认 60/最大 120 个主节点，补齐父节点上下文，游标绑定排序策略和图谱版本。has_more 与构建缺口分离，不把分页误报为 partial。
3. 范围与相机：首次打开尊重保存相机，切换论文/搜索/焦点/页码只在新结果返回后 fit；轮询、语言、展开与窗口尺寸不自动 fit。另提供“适应图谱”，不改固定坐标。深页游标失效可直接“返回第一页”。
4. 全屏：GraphPanel 切换应用视口全屏，同一画布/节点实例保持；支持 Esc、焦点循环与返回、滚动锁恢复。画布和详情分别适应高度，不重排或重挂载。真实浏览器发现初版竖排图例挤占画布，改为上方紧凑横排后重验通过。
5. 布局：集中美化关键词、节点类型、论文和语言筛选；图谱紧接其下，每篇论文的已保存候选/建图选项统一放页末且独立展开。论文列表读取全部分页；打开候选不切换图谱的论文筛选或触发抽取。GraphWorkspace 和 Comparator 移除重复 JobHistory，任务记录仍保留在文献与阅读；模型推理来源/历史保留。

主要源码：GraphWorkspace.tsx、GraphExplorer.tsx、ForceGraph.tsx、style.css、graphAppearance.tsx/.css、GraphPanel.tsx/.css、reading_projection.py。测试包括对应 React 测试、test_reading_project_paging.py，以及真实 React Flow 的 graph/workspace 浏览器 harness。同步 README、AGENTS、交互/阶段计划/API、文档导航和进度。未增加数据库迁移，head0011、领域 reading-extraction-1.0、入口和已保存候选/选择不变。

## 实际命令与结果

Python 使用 Anaconda researchgraph-studio。完整检查首轮在前端 lint 检出新增 readingPapers 的 useMemo 依赖声明与 React Compiler 推导不一致；扩大为实际 graph.data 依赖后，前端格式/类型/lint/全量测试/生产构建全部重跑通过。后端文件未再改动，不重复运行已通过的 Python 全量。

```powershell
$env:RGS_PYTHON='C:/Users/KLucen/anaconda3/envs/researchgraph-studio/python.exe'
pwsh -NoProfile -File scripts/check-phase0.ps1
pnpm format:check
pnpm check
pnpm test
pnpm build:web
pnpm --dir apps/desktop test:browser
pwsh -NoProfile -File scripts/build-windows.ps1
& $env:RGS_PYTHON scripts/smoke-engine.py --executable .local/engine-dist/researchgraph-engine/researchgraph-engine.exe
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml
# RGS_TEST_ENGINE_PATH 指向本轮冻结引擎
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml packaged_engine_connects_through_native_host_and_restarts -- --ignored
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/verify-windows-install.ps1 -EnginePath .local/engine-dist/researchgraph-engine/researchgraph-engine.exe -OutputRoot .local/graph-workspace-20261103/ps51-engine
```

| 检查 | 实际结果 |
| --- | --- |
| Python 全量 | **460 passed / 2 skipped**；符号链接测试受本机权限限制 |
| 后端静态/依赖/契约 | Ruff、144 文件格式、mypy 79 源文件、pip check、OpenAPI/TS 契约生成通过 |
| React | **76 passed**；含图例完整性、首次相机/延迟初始化、筛选与末尾选项独立、全屏保留、游标恢复、布局/候选/历史兼容 |
| 前端静态/生产构建 | TypeScript、ESLint、Prettier 与 Vite 通过 |
| 真实 Edge / React Flow | **8 passed**；悬停/拖动不消失、固定/缩放、共享支撑、11 色与未知回退、范围 fit、三篇/两页文献、全屏增大、DOM/坐标保持、Esc/焦点/滚动恢复 |
| 多论文后端针对性 | 3 篇各 70 主节点，共 210，首屏各 20；全部翻页不丢不重、单篇/搜索父上下文、游标失效、complete 不受分页影响、只读性通过；包含在全量中 |
| Rust / 冻结引擎 | 9 Rust 单测与另行 1 项打包宿主连接/退出/重启、冻结引擎 smoke 通过 |
| PowerShell 5.1 | 隔离 EnginePath 五项通过，子进程 PATH 仅 System32；不认证干净机 |

既有 Starlette/httpx 弃用及前端单 chunk 大于 500 KiB 提示保留。正常与全屏合成截图经过查看，不能替代用户原生反馈。无 Computer Use、真实模型调用、正式库写入或私人文件读取。

## 交付与用户验证

最终安装器为 `.local/releases/graph-workspace-20261103/ResearchGraph Studio_0.0.1_x64-setup.exe`，**38659968 字节**，SHA-256：

```text
d75462a2df3d19ff76ca1a2d2212fd34808a7e1243d42533b3cbfc3ed08f534f
```

16:53 构建收尾：PyInstaller/Tauri/NSIS 成功。前端最终检查修正后又打包一次，确保包含最后源码；一次直接调用 tauri 因当前 Shell 缺 cargo PATH 在编译前停止，按既有构建脚本仅补该进程 `.cargo/bin` 后重包成功，没有改系统设置。最终 NSIS 退出0后复制安装器，校验长度/哈希与构建源一致。delivery.json、最终回归/浏览器/构建/冻结/宿主/PowerShell日志和合成截图配对保存；本机工作日志在 `.local/graph-workspace-20261103/`，release目录不进入源码提交。

退出软件后安装新包，打开现有项目并进入图谱与比较：保持“全部论文”，检查三篇中心及结论/支撑、11 类颜色图例、筛选单篇后恢复全部、全屏/Esc与固定节点。节点较多时可翻页或筛选，首屏并非全部知识。展开页末任一论文选项应保持画布筛选；任务记录只在文献与阅读。不需要删除知识、重新解析或调用模型。

本轮新包的用户原生体验、跨类型全文科学质量及真实 strict 输出仍未独立验收；没有替用户安装/卸载或重做完整安装/干净机测试。四份登记补充原文路径仍不可用，不能重新核验。所有既有未提交改动保留；未暂存、Commit或Push。

16:54 收尾：537 个源码候选文件通过路径规则与 Gitleaks 内容扫描；156 Markdown/554 本地链接/88 项既有资产 LF 哈希核验通过，四份登记外部原文不可用单列。git diff --check 通过、暂存区为空；安装器长度/哈希与最终构建源及 delivery 一致。最终安全/文档结果另与本机 release 配对保存。
