# 语义协议与阶段恢复验收（2026-11-03）

本轮实施用户提出的四项可靠性改造，仍处于 P3/R5，不进入 Query/Lint/Wiki。设计见 [ADR0017](../../adr/0017-semantic-protocol-and-stage-recovery.md)。保留工作区已有改动、来源、知识及历史任务，数据库 head 0011、内部 reading-extraction-1.0 与入口 paper-reading-v1 不变，本轮不新增迁移。

## 实际改动

1. 新 P02_reading_extract_compact_v4 使用 reading-semantic-1，仅让模型返回 items、links、warnings。文献版本、批次、默认语言及领域版本由冻结的 transport_context 绑定，模型使用请求内短引用。reading_transport 从现有领域/紧凑 DTO 派生传输 Schema；reading_prompt_contract 从实际 Schema 生成字段、枚举、关系方向和哈希规则，启动调用前及测试中核对 Prompt，避免各自维护。相同 local_ref 在展开默认值前比较原始 JSON，只有完全相同的内容才能在完整验证后去重。
2. structured_output 为新模型快照冻结 native_json_schema、json_object 或 prompt 策略。原生 strict 限代码登记的官方精确端点/模型，兼容 JSON 单独请求与审计，不把连接成功当作复杂抽取协议通过。不支持的 Schema 在网络前拒绝；严格转换不删除校验约束或额外引入 null。不付费探测、不失败后降级重发，拒绝响应单独分类。旧快照保持原行为。
3. 新 semantic-reading-1 的 P12_reading_associations_v1 只补语义关联与重复提案；KnowledgeStore.reading().form_units 沿已验证路径确定结论单元成员，不穿过其他 Claim、不按共用证据猜边。P13_reading_ranking_v1 只给完整结论集合的贡献建议，程序绑定身份、执行门槛并发布。新贡献顺序和一基名次持久化，密度及显示偏好调整后保持；旧默认发布指纹不变。
4. reading_stage_validation.validate_stage 统一新响应与缓存的最终资格：JSON/DTO、版本/批次/修订、短引用、候选/根集合、原文 quote/offset/hash、来源及快照均验证，Store 提交再次检查。坏响应不能无条件命中；来源或快照变化停止，保留历史 ModelRun 状态/错误/完成时间，仅记录本次复用诊断，不靠再次付费修复。原始输出不改。

首次 P12/P13 失败且无旧图时，只以有来源、归属明确、非背景/推测且无未解问题的结论及合法支撑生成 provisional 预览。图谱根为 provisional，导航边为 HAS_CANDIDATE_CLAIM，ranking_status=pending、build_state=partial，不能显示为核心排序完成。任务仍失败并提示未完成阶段；已有图保留，可信来源或快照失效不发布预览。成功继续后复用 P02/P12 检查点，临时选择 revision 参与并发保护。

任务历史显示整合/排序进度、失败分类及下一动作；模型调用和 Token 从实际 ModelRun/attempts 汇总，包括失败阶段。无 attempts 的历史运行单列次数未知，费用未报告不估为零。设置页说明连接成功、兼容 JSON 和原生严格协议的区别。

## 隔离数据验证

私人数据库、原始响应、论文及探测脚本只在被忽略的本机目录。正式库没有写入，PDF/Zotero/凭据没有修改，真实模型及网络请求均为 **0**。以下不是新模型抽取或科学质量成绩。

| 场景 | 实际结果 |
| --- | --- |
| 旧任务续接 | 复用 P12 10/10 及前四个 P13 检查点；第五组原 4359 字符响应按 ADR0016 在 offset4358 补唯一缺失的 `]` 后完整重验，保存检查点并清空错误；在第六组 64195 字符请求边界主动停止 |
| 旧数据保持 | 原 raw、usage、传输参数、来源、知识、冻结计划、旧检查点及其他任务/运行保持；成功重验仅正常更新审计、状态、错误和完成时间 |
| 新流程首次失败 | 真实候选副本中 186 候选/651 证据，P12 短编号输入到无网络边界后注入超时；保守预览 51 个符合门槛的结论根，明确 pending/partial，不冒充模型排序成功 |
| 新流程已有图失败 | 140 候选/69 证据的另一副本保留原 21 个结论根及选择头；没有以临时视图覆盖 |
| 合成端到端 | 新 P02→P12→程序组单元→P13→Store→投影；坏 JSON、版本/根/证据错误、网络超时、首次预览与旧图保留、P12 新增关联后继续不重调成功请求 |
| 来源变化 | 合成 P02 在响应后修改可信锚点时拒绝入库，保留 received/raw/attempts，继续不发新请求；历史 succeeded 缓存遇可信快照变化保留历史状态。未对真实副本注入来源破坏 |
| 输出协议 | 合成 HTTP/SSE 验证 strict 请求、拒绝、Schema 不支持、兼容 JSON/提示路径和旧快照；没有真实 strict API 调用 |

匿名报告为 `.local/semantic-reliability-20261103/real-copy-verification.json`。旧 P13 的限定语法恢复只保留在旧协议，新语义响应不套用通用 JSON 修补。全部阶段继续校验领域和证据；新语义三阶段及旧 P13 拒绝重复键与非 JSON 常量，其他历史协议的兼容边界见对应 ADR。

## 命令与最终结果

Python 使用 Anaconda researchgraph-studio 环境。主要命令：

```powershell
$env:RGS_PYTHON='C:/Users/KLucen/anaconda3/envs/researchgraph-studio/python.exe'
pwsh -NoProfile -File scripts/check-phase0.ps1
pnpm --dir apps/desktop test:browser
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml
pwsh -NoProfile -File scripts/build-windows.ps1
& $env:RGS_PYTHON scripts/smoke-engine.py --executable .local/engine-dist/researchgraph-engine/researchgraph-engine.exe
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml packaged_engine_connects_through_native_host_and_restarts -- --ignored
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/verify-windows-install.ps1 -EnginePath .local/engine-dist/researchgraph-engine/researchgraph-engine.exe -OutputRoot .local/semantic-reliability-20261103/ps51-engine
& $env:RGS_PYTHON scripts/check-sensitive.py --gitleaks .local/tools/gitleaks-8.30.1/gitleaks.exe
```

打包宿主集成测试另设置 RGS_TEST_ENGINE_PATH 指向本轮 Sidecar。16:10（Asia/Shanghai）最终结果：

| 检查 | 实际结果 |
| --- | --- |
| 完整 Python | **457 passed / 2 skipped**；文件符号链接场景受本机 OS 权限限制 |
| Python 静态与依赖 | Ruff、143 文件格式、mypy 79 源文件、pip check 通过 |
| 前端 | **59 React passed**；TypeScript、ESLint、Prettier、契约生成、生产构建通过 |
| 真实图谱渲染 | **3 passed**；悬停、拖动、固定、缩放、容器调整和共享支撑收起 |
| Rust | **9 单测通过**；另行 **1 项打包宿主连接/退出/重启集成通过** |
| 构建及隔离启动 | PyInstaller/Tauri/NSIS、冻结引擎 smoke、PowerShell 5.1 EnginePath 五项通过；子进程 PATH 仅 System32 |

全量检查前修正了新增投影测试的 import 排序。集成时发现并补齐 P12/P13 调用统计、贡献排序持久化和可信输入变化时历史状态保护；对应定向回归及最终全量均通过。既有 Starlette/httpx 弃用提示与前端单 chunk 大于 500 KiB 的构建提示仍在。没有将 Mock、合成 HTTP 或零网络回放当作真实模型验收。

安装器保存在 `.local/releases/semantic-reliability-20261103/ResearchGraph Studio_0.0.1_x64-setup.exe`，**38652410 字节**，SHA-256：

```text
f949240aa7394753e2680d5f4f81ef7aedf15267182467e9412a0cbb07da6393
```

delivery.json、最终回归/构建/宿主/冻结/PowerShell 日志及匿名副本报告与安装器配对保存，仅本机可用。复制后长度和 SHA-256 与构建源一致。

## 用户验证与限制

退出软件后安装本轮安装器并打开原项目。旧失败任务使用“继续未完成批次”，沿原协议复用历史成功结果，不需删除论文、证据或知识。新抽取任务使用新 P02；尚未发布或临时图可通过“基于已有候选更新图谱”进入新 P12/P13，无需重抽全文。已有有效选择仅调整密度时复用选择，不额外调用抽取模型。

请反馈一次新建图的阶段进度、原文回溯和支撑展示结果；若末阶段失败，观察任务是否保留候选、图谱是否明确标注排序未完成，以及继续是否只处理未完成阶段。程序不承诺大输出容量下所有论文一次请求完成；兼容服务仍可能产生无效 JSON/Schema 或超时，完整校验和有界恢复保留。

新模板的两篇真实全文、真实严格输出、最终科学贡献质量及用户原生安装体验尚未验收。本轮不使用 Computer Use、不替用户安装/卸载，未做干净机认证。四份登记补充原文路径仍不可用，不能重新核验。无 Commit/Push，运行数据库、私人材料、密钥、日志及安装产物不进入源码。

16:14收尾核验：525个源码候选文件经路径规则及Gitleaks扫描通过；155份Markdown、549个本地链接、88项既有资产LF哈希核验通过，四份登记原文不可用单列。git diff --check通过、暂存区为空。安装器复制后长度/哈希与构建源及delivery一致；最终安全及文档检查报告配对保存于本机release目录。
