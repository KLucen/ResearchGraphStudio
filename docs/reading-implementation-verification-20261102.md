# 阅读辅助图谱 R1–R5 实际验收（2026-11-02）

> 安装反馈更正：旧安装包的宿主仍要求Schema0009，导致0010引擎被拒绝。此前installed-app只检查子进程端口401，不能证明宿主已连接；该验收缺口已补上，修复包与实测范围见本文末尾。

本轮先安全提交既有 P3/v3/R0 成果并推送 `8d3ba1d`，再按顺序实现 R1–R4，执行 R5。**R5 部分通过，不能称全部完成；未进入 P4/P5。** 实现决策见 [ADR 0009](adr/0009-reading-pipeline-implementation.md)。

## 已实施

| 阶段 | 结果 |
| --- | --- |
| R1 | 0010 加性迁移、旧候选适配、单元/成员/快照/偏好/检查点；统一 Store 写入、外键/证据/CAS 校验 |
| R2 | 独立 reading-extraction-1.0、10 类候选、原语言/中文、旧任务不换协议、原文与响应保留 |
| R3 | P12/P13 窗口与缓存、结论路径闭合、自动质量门槛、密度/偏好、失败保留候选和上一有效图 |
| R4 | 默认核心主干、支撑展开/收起、共享节点、全部候选搜索、密度/展示偏好、去除审核流程 |
| R5 | 自动化和局部真实链路已执行；全文、科学质量与用户安装体验未全部验收 |

## 数据保护与迁移

只读 SQLite 一致性备份当前正式 0009 库，备份及验收副本存本机忽略目录。当前实测原知识 **275 条**，不能再沿用此前 156 条作当前基线。0010 升级前后逐一比较所有旧表原列/记录（仅排除 alembic_version），完全一致；SQLite integrity_check/foreign_key_check 通过。真实调用后原知识全列及旧 ModelRun 原输出再次核对保持。正式库、源 PDF/Zotero/笔记均未回写或升级。

## 自动化命令与结果

Python 均使用 Conda researchgraph-studio 的解释器；实际命令如下。最终汇总见本文后续交付记录。

```powershell
pwsh -NoProfile -File scripts/check-phase0.ps1
pnpm --dir apps/desktop test:browser
cargo fmt --manifest-path apps/desktop/src-tauri/Cargo.toml --check
cargo clippy --manifest-path apps/desktop/src-tauri/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml
pwsh -NoProfile -File scripts/build-windows.ps1
```

新增测试覆盖迁移备份、旧内容不变、候选幂等、伪造证据/offset/未知字段、条件未知值、理论/方法/综述类型、整合/选择失败恢复、跨任务缓存、展示偏好、版本冲突、端点闭合、候选分页与跨论文边界。7 批第 2 批超时的离线故障注入：首批只调用一次，继续后 7/7，共 8 次抽取调用（含 1 次失败），无重复入图。此结果明确不是供应商超时恢复的真实全文成绩。

真实 React Flow 在 headless Edge 执行 3 项：持续悬停不闪烁、快速拖动/缩放/固定/容器变化、共享支撑展开后收起另一个单元且固定位置保留。没有使用 Computer Use，也未把浏览器测试写成原生安装体验。

## 真实模型与论文

沿用用户已经在全局设置中配置的真实兼容模型与 Windows 凭据管理器。在独立副本使用两篇已有 Zotero 论文的真实解析证据；没有发送私人笔记。最初全文计划分别为 8 批（首批超时二分后 9 批）和 34 批。首篇一次响应等待达到 90 秒；随后两份合法候选输出因关联类型不符失败。没有无限提高 timeout 或重复发送整个论文。

针对实测问题实现自动隔离后，复用已收到的两份 P02 输出，**没有重新支付 P02 费用**；在局部范围继续真实 P12/P13：

| 样本 | 保存候选 | 隔离非法关联 | 发布结论单元 | 构建状态 |
| --- | ---: | ---: | ---: | --- |
| 论文 A 的一个响应批次 | 11 | 3 | 2 | partial |
| 论文 B 的一个响应批次 | 10 | 1 | 3 | partial |

P12 还提出部分无根路径成员，保留为检索候选并显示覆盖限制；合法单元可发布。两篇投影实测分别只有 2/3 条 Paper→核心边，支撑仅在结论下展开。P12 耗时约 58.1/42.0 秒，P13 约 16.2/12.7 秒。已知供应商用量合计 **71,260 Tokens**（P02 23,647，P12 31,740，P13 15,873），另一次超时用量未知、价格未提供；复用 P02 记录不重复计费。

这验证真实输出→校验→Store→P12/P13→投影的**局部链路**，不等于两篇全文完成，不等于普适科学准确率，也不是新版跨论文真实关系推断验收。完整论文仍需进一步衡量批次数、响应时延、贡献覆盖、条件/限制遗漏。最终 Prompt 补充了端点矩阵；本轮复用此前输出的结果不冒充新 Prompt 全文实测。

## 安装与用户反馈步骤

安装器只保存在本机 `.local/releases/reading-graph-20261102/`，不会上传仓库。构建/冻结引擎验证与安装执行分别记录；未自动替换用户正在运行的软件。

安装后可执行：

1. 退出旧窗口，运行本轮安装器；首次启动自动备份并迁移，检查原项目/文献/知识仍存在。
2. 在图谱选择一篇旧论文，展开“结论选择与全部候选”，授权首次整合并点击“基于已有候选更新图谱”。此操作不重抽 PDF。
3. 默认应只看到论文与核心结论；选择结论“展开支撑”，双击固定并拖动，收起后共享支撑仍按其他展开单元保留。
4. 搜索未选候选，尝试显示/隐藏/恢复自动；切换密度不会重新抽取。重启后检查选择与布局保留。
5. 新论文从 Zotero/PDF 启动建图；观察抽取→整合→选择→发布，失败后继续未完成阶段。记录错误与阶段即可，不发送密钥或私人原文。

## 仍未通过或未执行

- 两篇全文真实抽取及完整质量评价、不同论文类型的真实模型样本尚未完成。
- 原生安装执行/用户交互反馈和干净机仍待验证；G0 已放行，不将未测内容写成通过。
- 精确表格、OCR/逐字锚定、全面语义正确性不属于本轮已完成能力。
- 四份外部补充原文登记路径仍不可用；保留来源记录，未伪造复核。
- P4 Query/P5 Wiki 未开发，仅保留完整候选、证据与版本供后续消费。


## 已完成的命令结果

- check-phase0 最终执行：Python **175 passed / 2 skipped**（Windows 符号链接权限相关跳过），Ruff/format/mypy、pip check、OpenAPI/TypeScript 契约、前端格式/lint/build 均通过。初次全检查曾停于一个前端格式问题，修复后重跑通过。
- React 初次37项通过，新增候选/密度/偏好用例后最终结果补记如下；真实浏览器3项通过，Rust7项通过，clippy -D warnings 通过。
- docs/tests 78项通过；130 Markdown/445本地链接、QA hash/环境JSON检查通过；4份不可用外部原文明确排除。文档收尾后再次检查链接与清单。

- 最终 React **39 passed**；新增后端共享节点用例所在模块 **4 passed**（全量175之后增加1项，未再次宣称全量重跑）。
- PyInstaller/Tauri/NSIS最终成功；冻结引擎smoke新增reading闭环/选择/重启并通过。PowerShell5.1 EnginePath在仅System32 PATH通过；第一次旧0009断言失败已修正到0010后复测。安装执行未做。
- 收尾移除 Comparator 遗留的审核筛选/文案，历史状态明确标为历史；边详情显示导航/原文/模型推断。React 39项、TS/eslint/格式再次通过，重新完成 PyInstaller/Tauri/NSIS、冻结引擎 smoke 与 PowerShell5.1 EnginePath 验证。
- 最终安装包38,526,897字节，SHA256 `a7fd43ef7818a682a3ff490dd7706f58b6e3965a9aca59c60ca5171de0794660`，版本仍0.0.1，以哈希和本轮文件夹区分。

## GitHub 交付与 CI

- 实现提交 `94b3a4d` 已普通推送 main；462候选文件、75暂存文件及该提交Gitleaks通过，暂存路径复核没有私人数据或安装产物。
- 首次 CI [41425098035](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41425098035) 后端为177通过/1失败：48批旧任务恢复在共享的20秒测试等待期限内未完成，安装阶段因此跳过。仅该长任务测试改为90秒有界等待，并输出阶段/批次诊断；产品模型timeout不变。修复后的实际结果另行补记。
- 收尾同步 API首页、Schema说明、文档导航和下一轮模板，明确0010/reading入口与R5剩余范围。
- CI修正针对性回归：`pytest tests/engine/test_extraction_refinement.py tests/engine/test_ingest.py -q` 为19 passed（23.41秒），Ruff/format通过。
- 修正后的 [CI 41426893999](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41426893999) 已全部成功：Windows job 178 Python、39 React、7 Rust 测试通过，冻结引擎与 NSIS 构建通过；`installed-app` job 通过。对应 GitHub artifacts 为 `researchgraph-phase0-windows`（ID 13133122133）和 `researchgraph-installed-verification`（ID 13132573949）。

## 安装后版本不匹配修复

2026-11-02 用户安装后报告“本地引擎未连接 / 引擎或数据库版本不匹配”。根因是 `main.rs` 健康握手仍比较0009，后端和迁移已经为0010；并非根据该提示即可判断数据库损坏。宿主统一版本常量并校验database=ready/fts5；版本一致性测试对照Python迁移head，避免之后只升级一端。

此前CI存在验收盲区：仅看到子进程401即可通过，尚未确认宿主完成握手。现在宿主每次启动写无凭据的 `host-startup.json`（父子进程ID、connected、预期协议/Schema及错误），安装脚本必须确认对应宿主和子进程已成功握手。记录不是实时连接状态，也不包含Token、端口、论文或模型配置；写入失败不影响正常启动，但验收不能通过。

实际命令与结果：

- `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --locked`：9通过；依赖打包引擎的1项显式忽略。
- 设置 `RGS_TEST_ENGINE_PATH` 后另行运行 `cargo test ... packaged_engine_connects_through_native_host_and_restarts -- --ignored`：1通过，调用实际Host.start/status/stop及冻结引擎，在独立临时库完成两次握手与重启；已加入CI。
- `cargo fmt --check`、`cargo clippy ... --all-targets -- -D warnings`通过；Windows PowerShell5.1直接解析并执行安装脚本握手检查函数，6个合成场景通过（成功、宿主拒绝、仅子进程、父进程过期、子进程过期、Schema不符）。这不是原生界面验收。
- PyInstaller/Tauri/NSIS构建、冻结引擎smoke及PowerShell5.1 EnginePath验证通过；宿主握手记录加入后另行重建最终安装包。没有用正式库做升级实验，没有更改用户PDF/Zotero/凭据，没有调用真实模型。
- 新安装包不改变Schema、不需要降级或删除数据库。退出旧窗口后覆盖安装，再确认设置页连接和原项目数据；用户本机反馈尚待收到。
- 最终修复安装器位于本机 `.local/releases/reading-graph-20261102-schema-fix/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,523,711字节，SHA256 `3ef49f88f70b5d6b4f82cdbacc3f7185e85500f39734b5d0d3b14b2cb0661203`。替代上文旧安装包，源码仓库不含安装器。
