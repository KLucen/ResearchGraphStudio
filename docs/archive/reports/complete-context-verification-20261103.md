# 完整整合与选择上下文验收（2026-11-03）

本轮属于 R5 可靠性修复，未进入 P4/P5。实现见 [ADR0015](../../adr/0015-complete-reading-context.md)，Alembic head 0011、领域 Schema 和现有 Prompt 文件保持不变。

## 根因与修复

“选择上下文超过预算，保留整合检查点；未截断必要支撑”来自 P13 调用前的 48000 字符检查，模型尚未收到请求。完整支撑以及多个单元共享成员时，请求容易超过该旧门槛，增大模型输出额度不能解除它。

`reading_pipeline.py` 已删除 P12 的 26000 字符候选、24000 字符证据、60 候选和 20 窗口限制，同时删除 P13 的 48000 字符阻塞。新 `reading_finish_plan.context_policy=complete-context-v1` 用一次 P12 输入本篇全部当前有效候选及所引完整证据，一次 P13 输入全部结论单元；不因软件字符、候选、根或窗口预算省略材料或拒绝选择。

旧 `reading_windows` 在重新构造前读取，冻结内容和缺口不变。旧 finish plan 的签名与 P13 八单元分组保持，已成功检查点按原键复用；不为新策略重抽 P02 或重做成功 P12。模型自身容量、超时、取消、Schema、证据白名单、关联方向、来源、单元路径和发布版本检查仍生效。真实容量不足时保留旧图与已成功阶段，明确失败，不截断必要支撑或假报完成。

## 实际失败任务的隔离验证

通过 SQLite 只读连接取得正式库的一致性备份，执行仅限 `.local/complete-context-20261103/` 副本。没有读取密钥，没有真实 API 请求，没有操作正式数据库、PDF 或 Zotero。

| 匿名失败任务 | 已保存抽取批次 | 可复用 P12 检查点 | 整合单元 | P13 超过旧 48K 门槛的组数 |
| --- | --- | --- | --- | --- |
| A | 15/15 | 4/4 | 30 | 3/4 |
| B | 34/34 | 10/10 | 76 | 9/10 |

最大 P13 请求为 116934 字符。只做边界探测的无网络 Provider 复现历史模型签名，分别在 87342、52592 字符的 P13 输入上被调用，随后主动停止；证明新代码已解除本地门槛、直接复用全部 P12 检查点，没有 P02/P12 重调。

副本的旧知识、来源表、原 ModelRun、其他 Job、目标任务冻结计划/窗口/原结果逐项保持。探测仅在副本新增一次诊断 ModelRun 并改变目标执行字段；没有将这次主动停止记录为真实选择成功。私有明细为 `real-checkpoint-report.json`。

## 自动化与构建结果

全部 Python 使用 Anaconda `researchgraph-studio` 环境。

| 检查 | 实际结果 |
| --- | --- |
| 完整 Python 回归 | 287 passed / 2 skipped；两项符号链接测试受 OS 权限限制 |
| 新完整上下文测试 | 4 passed，覆盖 69 候选、完整超 24K 证据、超 48K 选择、68 个有效支撑、161 根和旧检查点续接 |
| 相关独立复核 | 16 passed，覆盖选择、阶段恢复及新测试；超时/context_limit 保留旧图，继续不重做整合 |
| React | 47 passed；前端类型、ESLint、Prettier 通过 |
| Python 静态与依赖 | Ruff/格式、mypy 72 个源文件、pip check 通过 |
| Windows 构建 | PyInstaller/Tauri/NSIS 成功；前端单 chunk 大于 500 KiB 提示仍存在 |
| Rust 与原生宿主 | 9 单测通过；另行执行的 1 项真实打包宿主握手、退出及重启通过 |
| 冻结引擎 | smoke 通过，含新阅读链、发布/重启与来源保留；合成 Provider 仅限显式测试 |
| PowerShell 5.1 | EnginePath 五项通过，子进程 PATH 只有 System32；仅该脚本进程使用 ExecutionPolicy Bypass |
| 安全与文档 | 505 个源码候选文件经路径规则及 Gitleaks 内容扫描通过；148 Markdown / 508 本地链接 / 88 清单资产通过，四份登记外部原文仍不可用；git diff --check 通过 |

首轮完整回归为 286 passed / 1 failed / 2 skipped；失败在本轮更新的测试回调访问已离开 Session 的 ORM 对象。将回调需要的 ID 在 Session 内保存后，9 项定向检查通过，最终完整回归为上表 287 passed / 2 skipped。未放宽产品校验或修改用户数据。

主要命令：

```powershell
& 'C:/Users/KLucen/anaconda3/envs/researchgraph-studio/python.exe' -m pytest -q
& 'C:/Users/KLucen/anaconda3/envs/researchgraph-studio/python.exe' -m ruff check services/engine tests/engine scripts
& 'C:/Users/KLucen/anaconda3/envs/researchgraph-studio/python.exe' -m ruff format --check services/engine tests/engine scripts
& 'C:/Users/KLucen/anaconda3/envs/researchgraph-studio/python.exe' -m mypy
& 'C:/Users/KLucen/anaconda3/envs/researchgraph-studio/python.exe' -m pip check
pnpm test
pnpm check
pnpm format:check
pwsh -NoProfile -File scripts/build-windows.ps1
python scripts/smoke-engine.py --executable <packaged-engine>
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml packaged_engine_connects_through_native_host_and_restarts -- --ignored
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/verify-windows-install.ps1 -EnginePath <packaged-engine> -OutputRoot <isolated-output>
```

上述简写 `python` 同样使用指定 Conda 解释器；宿主测试设置 `RGS_TEST_ENGINE_PATH` 指向刚构建的 Sidecar。详细日志只保存在忽略的本机目录。

## 安装包与继续步骤

安装器：`.local/releases/complete-context-20261103/ResearchGraph Studio_0.0.1_x64-setup.exe`，38609403 字节，SHA-256：

```text
d579365a3129fcea4456a15f78071c5454076a5ca74e1640d8a85c7d9761667d
```

退出软件后安装修复包，再打开原项目，对原失败任务点击“继续未完成批次”。这两个任务已经抽取完成，应复用整合检查点后进入选择；不需要删除知识、重建项目或重新抽取。续跑未完成 P13 会调用用户配置的真实模型，费用按供应商实际计量；不能将本轮零调用探测理解为后续真实选择免费。

本轮未替用户安装/卸载、未做新安装器完整安装卸载或干净机验收；真实模型的最终选择和用户原生反馈待续跑确认。完整上下文仍受模型服务实际能力约束。四份补充原文的已登记外部路径仍不可用，未记为核验通过。源码、私人材料、运行库与安装产物分开；未暂存、Commit 或 Push。
