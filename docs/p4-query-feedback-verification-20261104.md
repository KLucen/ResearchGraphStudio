# P4 Query 用户反馈修复与验收 — 2026-11-04

本报告续接[P4 实施与验收](p4-query-verification-20261104.md)，记录用户安装后提出的来源可读性、原问答导航、整组阅读和保存生命周期问题。原包已安装但用户报告存在问题，不能继续将状态写成“尚未反馈”，也不能据此记为原生验收通过。决策见[ADR0024](adr/0024-query-reading-cards-and-saved-lifecycle.md)；本轮仍处于 P4 收尾，不进入 P5。

## 修复范围

| 用户反馈 | 修复与边界 |
| --- | --- |
| 来源预览缺少中文关键总结 | 本地显示投影复用已保存辅助翻译，展示论文题名、原文与定位；没有中文摘要时明确缺失，不追加翻译调用 |
| 回答引用露出内部 ID | 引用展示对应原文、已有中文要点和论文信息；引用编号只作核对，不代替内容；本次答案要点独立标为 AI 综合 |
| 查看原问答与引用无反应 | 按保存对象原 query_id 读取并定位整组问答；加载与错误均可见，不重新生成 |
| 问题、来源与回答分散 | 一次问答按问题、范围、来源、答案、限制和保存操作成组展示，历史恢复使用原问题 |
| 保存后无法批注或移除 | 0014 独立偏好表、Store 幂等和元数据并发控制；移除穿透检索、衍生层和保存谱系，保留原答案、raw、文档版本及论文证据 |

来源 `presentation` 不进入冻结 snapshot / manifest / input_hash；旧准备、答案和保存行不因新显示字段改变。个人批注不会改论文 Claim 或模型答案，也不自动成为科学来源。移除是用户阅读库状态，不是物理清库或人工科学审核。

额外兼容复核发现：旧0013保存综合只冻结最终根来源，若曾引用另一份保存综合，需要从原问答快照只读恢复中间谱系；不能让被移除内容借根证据展开重新出现。补丁保留旧行与哈希，并隔离无法核验的单个对象。同一回答另存到不同文档分别管理；同文档后续版本中的复制段落继续跟踪。跨页节点的合并原文也不再标为第一条证据的单一页码。

## 本轮实际验证记录

本节只记本增量的实际执行；前轮 862 Python、108 React、真实 10 次请求等仍保留在旧报告，不充当本轮重跑结果。

| 检查 | 本轮状态 |
| --- | --- |
| 来源显示与冻结契约专项 | 3项通过：原文/已有中文、缺失中文不借用其他论文、跨页不编单页定位；冻结上下文/hash及科学行不改 |
| 批注/移除、用途与依赖重验 | 兼容补丁专项50项通过；批注/清空/幂等/冲突/撤权、移除/复制/下游谱系及旧0013恢复与损坏隔离覆盖，交叠不累加 |
| 0013→0014 加性迁移、备份和旧行保持 | 源码隔离升级及最终冻结引擎升级通过；62张旧表的列/行保持，旧保存manifest/raw不改，两次启动仅1份准确0013备份，integrity/FK通过 |
| React / 浏览器 / 后端回归及静态检查 | 最终879 Python passed/2 skipped；114 React（含QueryPanel19）、14 Edge（含4问答）、15 Rust与Host1通过；静态/生成契约/依赖/生产构建通过 |
| 冻结引擎、宿主与 Windows 安装脚本 | 最终PyInstaller/Tauri/NSIS退出0；冻结HTTP/SSE合成协议→保存→批注→重启→移除→重启通过，stub POST=1；Host1项两次握手通过，PowerShell5.1/System32-only PATH隔离17项通过 |
| 修复包、包内源码指纹和敏感内容检查 | 最终包与171份源码指纹、281份资源（不含运行生成pycache）一致；603份源码候选内容/路径/Gitleaks、173 Markdown/742本地链接/88资产LF哈希通过；资源无私人PDF/数据库/.env/日志 |
| 修复包用户原生确认 | 尚未取得；旧包问题反馈不算修复包通过 |

本轮新增真实模型请求0，正式用户库实验写入0；旧 P4 的实际 10 次 / 737701 Token 与原 raw 保持历史记录，不为界面修复重复付费。合成HTTP端点、显式OfflineProvider和真实模型分别记录。真实 strict、干净机、复杂版面与无 OCR 的限制继续保留；S1–S4 四份登记外部补充原文不可用，不能宣称已核验。

## 实际命令与修复包

使用Anaconda `researchgraph-studio` 环境，测试均为独立合成数据。实际命令：

```powershell
pwsh -NoProfile -File scripts/check-phase0.ps1
pnpm --dir apps/desktop test:browser
cargo test --locked
cargo clippy --locked --all-targets -- -D warnings
pwsh -NoProfile -File scripts/build-windows.ps1
python scripts/smoke-engine.py --executable apps/desktop/src-tauri/binaries/researchgraph-engine-x86_64-pc-windows-msvc.exe
```

Python实际由Conda环境绝对解释器执行，Rust在`apps/desktop/src-tauri`执行。打包宿主另以`RGS_TEST_ENGINE_PATH`运行ignored专项；Windows PowerShell5.1以仅该进程ExecutionPolicy Bypass运行`verify-windows-install.ps1 -EnginePath ... -PdfFixture tests/fixtures/pdf/two-pages.pdf`，没有修改系统策略。冻结0013升级、源码指纹和匿名报告脚本只保存在忽略的`.local/p4-feedback-20261104`，不读取正式用户库。

首轮全量4项失败：3项旧head断言未同步、1项正在补充的幂等测试断言；修复后完整流水线870 passed/2 skipped、114 React通过。随后独立复核补旧0013保存谱系和跨页定位，专项通过，并再次执行最终完整流水线及重新打包：最终879 passed/2 skipped（445.56秒），静态Ruff/186文件格式/mypy100源文件、依赖和生成契约通过。React114、Edge14、Rust15及打包Host1通过，交叠专项不累加。一次被主动中断的回归停在99%，没有结束摘要，不记为通过。保留既有Starlette/httpx弃用、前端大chunk提示及2项本机符号链接权限跳过。

最终安装器：`.local/releases/p4-query-feedback-final-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe`，**38,793,801字节**，SHA256 `163a6cb9a1f68040d0482a11a0c989c85be781516d348175955b1c14bd575f9f`。引擎SHA256 `2767bd8e4493cbed4e6c810fa5f369d38c6c4358324586fdffb77ee75fc9ad1c`。旧包和本轮中间构建保留；只有此final目录为本次最终修复交付，未替用户安装或卸载。

## 修复包原生反馈步骤

1. 退出旧软件后安装本轮修复包；打开原项目和已有问答，无需重新抽取论文或发出新问题。
2. 确认问题、来源和答案在同一阅读区；来源与引用显示可读原文和已有中文要点，缺失中文时有明确提示。
3. 在已保存阅读知识中点击“查看原问答与引用”，确认出现加载状态并定位原问题、答案与引用；失败时能读到具体原因。
4. 添加个人批注并保存，退出重开后确认仍在，模型答案和论文原文未被改写。
5. 移除一份测试保存内容，确认其不再出现在已保存库、检索和衍生层；原问答、原论文及其证据仍可读取。不要用重要个人记录验证移除。

当前修复包用户原生反馈尚未取得，不把上述步骤记为通过。本轮无新的 Commit / Push 授权，也未进入P5。
