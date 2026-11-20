# 导入失败与全文章节阅读修复验证

日期：2026-11-18（Asia/Shanghai）。决策见 [ADR0049](adr/0049-import-recovery-and-chapter-reading-progress.md)。

## 修复范围

- 桌面 Host 精确允许论文更新、删除、清旧内容和章节进度路由，继续校验方法、UUID 及查询参数。
- 模型解析在 Session 关闭前复制普通计划和授权值，消除 detached ORM；Job、计划项、解析与导入会话的终态同步，升级不自动重发旧任务。
- 真正 HTTP POST 前检查任务仍为 running，覆盖附件查找、PDF 异步读取和 HTTP 客户端准备；已发送请求不能撤回，取消后不发布结果。
- 新 Zotero 导入立即使用选中的真实论文题名。旧记录不推测回填，可使用编辑题名。
- 阅读状态融合到全文大章节和目录；支持已读计数、继续阅读和版本隔离。小节导读及独立理解状态入口移除，旧接口和历史保留。
- 窄屏续读标题避开固定工具栏，620px/390px 无横向溢出。

## 最终源码回归

| 验证 | 实际结果 |
| --- | --- |
| 引擎完整 pytest | 419 passed / 1 skipped / 1 warning，83.96 秒 |
| 桌面 `pnpm --dir apps/desktop test` | 11 files / 106 passed，13.62 秒 |
| Edge `pnpm --dir apps/desktop test:browser` | 15 passed，12.1 秒 |
| 全 Ruff lint、全引擎 mypy | 通过；mypy 78 files |
| compileall、TypeScript/ESLint、Prettier、契约导出 | 通过 |
| 本轮 Python 修改文件 format | 通过；不把既有无关格式欠账记为全局通过 |
| 最终敏感内容扫描 | 361 files；私人路径规则及 Gitleaks 通过 |
| 当前说明及本轮报告链接 | 75 links / 0 missing；diff 检查通过 |

唯一 pytest warning 是已有的 Starlette/httpx TestClient deprecation。一个跳过项保持跳过，不计通过。浏览器测试使用真实 React 组件和匿名夹具，不是桌面 WebView 原生操作验收。新增模型全文测试覆盖原文、公式、表格、译文、大章状态、目录已读计数、重新打开后的续读以及实际点击后的焦点和标题位置。浏览器夹具模拟本地进度存储；真实后端持久化及重启由隔离 API 回归验证。

取消测试使用 httpx MockTransport：文件读取或客户端进入期间取消/失败/中断时 0 POST、0 输出；正常路径 1 POST；dispatch 后取消仍有 1 POST，但没有发布输出。回调不进入请求正文。

## 安装验证

最终安装包：[ResearchGraph-Studio-Import-Reading-Fix-0.0.1-x64-setup.exe](../.local/releases/import-reading-fix-final-20261118/ResearchGraph-Studio-Import-Reading-Fix-0.0.1-x64-setup.exe)，**160,413,261 bytes**，未签名。完整构建退出 0，构建前后 **151 项运行源及配置**指纹一致；最终安装后的 sidecar 与 **322 项 `_internal` 资源**逐文件配对一致。内部指纹与命令保存在 [final-summary.json](../.local/verify/import-reading-fix-final2-20261118/final-summary.json) 和同目录 `artifact-verification.json`，不作为论文导入门槛。

Windows PowerShell 5.1 执行修正后的 `scripts/verify-windows-install.ps1 -Installer <最终包> -ExpectedSha256 <内部包指纹> -PdfFixture tests/fixtures/pdf/two-pages.pdf -OutputRoot <唯一隔离目录>` 通过：

- schema `lite0012`，题名编辑成功。
- 匿名模型文档 3 个段落/材料段，含公式和表格；已读状态 `COMPLETED` 保存并读回。
- 清理旧内容实际移除 4 个 Chunk；模型材料和已读状态保留，旧阅读存档没有自动重建。
- 删除论文后论文及章节状态读取均为 404，引用 PDF 保留。
- 模型调用、输入/输出 Token 均为 0；未打包已撤下的 translation runtime。

使用最终安装后的 sidecar 设置 `RGS_TEST_ENGINE_PATH`，执行 `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --locked -- --include-ignored`：**14 passed / 0 failed / 0 ignored（2.86 秒）**，包含实际 Host 启动及重启。构建日志、PS5.1 安装报告、Host 日志和资源配对记录在 `.local/verify/import-reading-fix-final2-20261118/`。前两次构建因后续取消守卫和窄屏修复而不交付，原始日志保留；不将首包成绩冒充最终包验证。

首次安装验证曾因 PowerShell 5.1 脚本的空数组嵌套和空 DELETE body 编码失败。只读诊断确认匿名模型解析已成功；脚本分别改为直接接收数组和显式编码 JSON null。这些修复已进入最终冻结源码，不将首次脚本失败改写成产品验证成功。

## 验收边界

真实 Provider/模型调用、Token 和费用为 0。未读取或修改正式用户数据库、Zotero 正式库、私人论文或密钥。真实 Provider 的 PDF 传输能力、真实论文章节/公式/表格质量和桌面 GUI 原生体验仍待单独验收。模型解析是单次非流式请求，界面仅展示实际阶段，不虚构逐章百分比。

安装后旧失败任务只对齐显示状态，不自动重试。已授权联网的旧计划可以点击“重试模型解析”；未授权的旧计划提示重新导入。新解析不会继承旧解析的已读标记。

本轮未 Commit/Push；安装器、运行数据及验证日志保留在忽略目录 `.local`，不进入源码提交。
