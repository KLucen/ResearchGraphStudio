# 新版范围与抽取恢复：实际验收

日期：2026-11-02，Asia/Shanghai。范围R5；未进入下一Phase。用户在本轮收尾时明确授权提交与推送；Git交付结果另行补记。

## 根因与改动

- waiver不是截断：旧P02阅读响应完整返回19候选，但附加了Schema未声明的顶层说明。另一超时来自原90秒非流式、默认思考任务。普通继续此前只换请求策略，仍沿用旧抽取模板。
- 新续接创建独立计划，保留旧Job/原响应，复用已提交的新版领域批次；可校验响应零调用恢复，未完成部分使用P02_reading_extract_compact_v2。
- 正常候选、阅读、整合、图谱统一reading-extraction-1.0；422旧知识中147条具备新版来源，275条旧unified知识保留历史且不混入新图。没有删除用户数据库或修改原PDF/Zotero。
- P12/P13公共Prompt指示warnings/limitations，与其实际Schema冲突，已使用明确闭合的新模板。领域/传输/head分别仍为reading-extraction-1.0/reading-compact-1/0010。
- 整合窗口改为根优先；自成员、外层说明采用有审计的确定性规范化；非法组织建议隔离，归属/条件不同的候选不折叠。不是放宽全部Schema、替换来源ID或把模型错误当事实。

实现集中在reading_wire/validation/upgrade/scope、unified_extraction、reading_pipeline/selection/store/projection/api及任务/阅读界面。决策见[ADR0013](adr/0013-current-schema-and-bounded-recovery.md)。

## 真实模型与数据保留

使用正式库只读SQLite backup建立本机忽略目录下的隔离副本，密钥仅从OS凭据存储读取。未修改正式库、未安装覆盖正在使用的软件。

1. 原waiver响应本地重验恢复19候选、11合法关联，4关联隔离，0新增模型调用。
2. 原任务9/12续到12/12；剩余两批真实调用约24.75秒/19.44秒，reasoning=0，响应未截断。有效输出额度393216，本轮没有增加总超时。
3. 首次整合失败暴露根优先级问题；随后实际暴露根自成员、limitations、窗口外ID、非法边、重复条件冲突等问题，修复后复用原响应，未重抽全文。
4. P12/P13真实闭环发布22核心结论单元；重开隔离数据库，默认23节点，全部展开28节点/29边，所有边闭合且所有知识节点均属于新版候选范围。该论文共有140新版候选，其余保留检索。
5. 最终P13_reading_selection_v3单独验证一个8根真实窗口，12.219秒，无附加字段归一化。完整建图过程使用其紧邻前版P13模板及同一严格领域验证；不把单窗口最终Prompt验证写为全篇重复验证。
6. 总计15次真实调用（含本轮诊断中失败的整合及最终Prompt检查），供应商报告prompt171027/completion42476/total213503 Tokens，reasoning0；供应商未返回金额。成功抽取和已完成检查点未重调。
7. 422原知识、48原ModelRun、9原Job、934证据、925文本块、2论文/版本/来源逐行不变。SQLite integrity_check=ok，foreign_key_check为空。

以上是一个已有论文的真实恢复闭环，未对另一篇全文重新收费验收。结果明确为partial：表格/公式上下文不足、部分关联被隔离；展开的支撑只有3个Method、2个Concept，仍需继续改善支撑覆盖和选择质量。不能宣称全文理解质量已经通过。

## 自动化与安装

- scripts/check-phase0.ps1：243 Python passed / 2 skipped，46 React passed；Ruff、mypy（66文件）、依赖、契约生成、前端格式/类型/lint/build通过。
- pnpm --dir apps/desktop test:browser：3项真实React Flow渲染交互通过。
- 两项Python跳过为现有文件链接环境条件；仍有Starlette弃用与前端包大于500kB提示。

最终补齐比较器范围后，check-phase0再次243 Python/2 skipped、46 React通过，静态/契约/前端构建全部通过。scripts/build-windows.ps1再次构建成功。冻结引擎smoke、PowerShell5.1 EnginePath五项与1项原生宿主连接/重启复核通过；Rust9单测通过。真实图谱浏览器3项通过后仅改变比较器列表范围，未改图谱渲染器。

本机安装器：`.local/releases/schema-recovery-20261102/ResearchGraph Studio_0.0.1_x64-setup.exe`，38569886字节，SHA256 `7577a6f036e9602cfdf0b2d228f9484ec22e92c190de1a248ad0b4eea1393f83`。安装器仅保存在忽略目录，不纳入源码提交；应用版本仍0.0.1，用此独立目录/哈希区分本轮包。用户原生安装反馈尚未执行，不记为通过。

## 用户复核

安装本轮新包后，在任务记录找到较新的waiver失败任务，点击“继续未完成批次”。应该创建新版续接，复用成功批次和收到的响应；旧错误保留为历史。图谱仅显示新版内容。也可从论文入口新建新版抽取；无需先删除论文或知识数据库。

四份补充原文的登记路径仍不可用，本轮未声称核验其内容。当前仍为R5；下一步是安装反馈及全文支撑/表格证据质量，不进入Query/Wiki。

## Git交付与CI修复

2026-11-02 23:36（Asia/Shanghai）：77文件已提交`1c28137`并普通推送main。提交前全内容489文件、暂存77文件的Gitleaks与私人路径检查通过。首次[CI 41468861276](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41468861276)通过回归/契约，打包成功，但smoke读取关系详情404，installed-app跳过。

验收脚本先前分别选择两份合成论文列表的首条Claim；批内证据ID/时间并列排序不能保证它们是同一段落，NO_DECISION正确返回空proposal_id。原脚本本机普通复跑5次均通过，但控制首条样本顺序后复现了同样空ID与404。现按显式共同原文选择双方Claim/Method，并断言proposal_id非空，继续完整执行关系、历史审核兼容和重启/stale检查，不放宽产品的NO_DECISION规则。修复脚本本机连续两次冻结smoke通过，Ruff检查/格式通过；无产品源码变动，现有安装器仍适用。远端复跑和新安装验收包待补记。

## 最终交付

2026-11-03 00:08（Asia/Shanghai）：功能提交`1c28137`与验收脚本修复`a4cd365`均已普通推送main。[CI 41474458777](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41474458777)的windows、installed-app均成功，替代上一次失败的交付状态。代码检查、冻结smoke、Rust及安装器构建均通过。

独立Windows Server 2022 runner使用Windows PowerShell5.1执行安装验收，报告20项全部通过：安装、鉴权、诊断、PDF导入与来源重定位、任务历史/阶段、离线抽取/证据/历史审核兼容、临时工作区恢复、重启持久化与原件保留、EOF退出、桌面Sidecar启动及宿主握手、单实例、正常退出、崩溃清理、卸载。子进程PATH仅System32；runner本身有开发工具，报告明确不认证干净机G0。离线验收不冒充真实模型质量通过，也不代表用户本机已经安装反馈。

源码内容489文件与修复暂存4文件的Gitleaks/路径扫描通过；随后21个Git提交全历史扫描无泄露。文档143份Markdown/500本地链接/88资产清单通过，四份不可用外部原文仍单独保留限制。私人数据库、原文、模型响应/日志和安装器未进入源码提交；原正式库未修改。最终仅补交交付文档，不改变已通过CI的产品代码。

00:12补记：对应CI安装器与验收报告已保存到本机忽略目录`.local/releases/schema-recovery-ci-41474458777/`，包含两个原始artifact ZIP及delivery.json。安装器位于其`researchgraph-phase0-windows/ResearchGraph Studio_0.0.1_x64-setup.exe`，38462458字节，SHA256 `6e07f886c438e5103a1677dcc9672f13d84a636e38d19c389a58affbd06e5c53`，与远端安装报告逐字一致。此为CI编译包，与前述本机编译包哈希不同，源代码一致；均未替用户安装。收尾文档链接复核为143 Markdown/501本地链接/88资产，四份外部原文仍不可用。
