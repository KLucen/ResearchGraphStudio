# P4 性能与科学支撑改进（2026-11-05）

本轮用户明确授权提交推送当前P4成果，并尝试解决未达标内容。继承[前次验收](p4-final-acceptance-20261105.md)原始成绩，不删失败样本、不进入P5，不将定向补验写成全量科学准确率。设计见[ADR0028](../../adr/0028-query-scientific-guidance-and-citation-closure.md)。

## 已交付基线与代码

`main`已普通推送`8d67ed1fb9ec83d575a562ac43c7c707b1a3627f`，包含P4-Q01～Q08、0012～0014加性迁移和数值保护。[对应远端CI](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41954098280)的windows和installed-app全部成功，含真实Edge、冻结引擎、Rust/NSIS及VerifyDesktop实际安装；旧R5成绩不混入。历史Gitleaks、618源码候选内容/路径、104暂存文件及暂存diff通过，仅修ADR0026日期行空白。私人PDF/验收库/raw/凭据和本地安装器未上传。

后续优化修改query_graph/query_retrieval/unified_store，只减少NodeEvidence ORM、递归临时集合/列表、固定UUIDv5前缀及JSON编码器重复构造；不跨调用缓存、不裁剪候选或支撑，DTO/版本/哈希/权限/边/锚点终验保持。

优化已提交并普通推送为`75061d2e3804a37c9b6209d716fa207f86173bb4`，28个实际暂存文件经内容/路径/Gitleaks和diff检查通过。178运行源与该提交的Git blob按仓库LF规范化逐字一致；[本增量独立CI](https://github.com/KLucen/ResearchGraphStudio/actions/runs/41959965368)已全部成功，不继承8d67ed1成绩。后续仅补验收文档，不重建或更改已封存运行源码/安装器。

新增query_scientific_grounding.py、P07_query_grounded_v3.md，context/API/answers/answer_wire接入独立冻结scientific_guidance、真实来源角色/根链接/已检测表格组及scientific_binding审计。旧v1/v2的Prompt、hash、raw和恢复不自动升级；wire DTO不新增字段，head0014无迁移/依赖新增。程序仅补合法node→evidence→chunk及真实检测表格组，不猜公式/表列，绑定后重验归属，GET/保存重算；背景介绍允许但不冒充新贡献。引用完整性不是语义证明。

## 自动化和性能实测

- `pwsh -NoProfile -File scripts/check-phase0.ps1`完整退出0：**934 Python passed/2 skipped（402.45秒）、124 React**；Ruff、198文件格式、mypy104源文件、依赖、生成契约、前端类型/lint/生产构建通过。2项跳过仍为Windows符号链接权限。
- 新科学指导/表格/答案/保存99专项、表示兼容7项通过，与全量交叠不累加。178运行源在全量前后和最终基准后指纹相同。前端/Rust源未改，初始提交对应CI的15 Edge和19 Rust/Host均通过；优化提交的远端结果另记。
- 候选P95=4.249秒、诊断P95=2.240秒均如实保留。GC有实测成本但不足解释全部波动，未禁用/调整GC、丢慢样本或归因未测热降频。
- 在回归、构建、真实调用和冻结检查全部结束后，仅一次串行原规格主源码基准：10,000候选/20,000块/30,001索引与FTS，cold **1.457742秒**，warm **P50=1.229685/P95=1.583589秒**（12样本nearest-rank，P95=max），本机≤2秒目标达到。前次最终P95=3.016278秒不改写，本次不是通用工作负载SLA。
- 峰RSS275,161,088B，总库45,969,408B；FTS逻辑UTF8文本3,687,347B，dbstat不可用故物理大小未知。8场景完整响应/30,001索引字节与旧实现相同、47来源表保持，缺17条FTS恢复/恶意派生行清理/下次变源重验通过。Unicode/冒号/emoji对象ID重建后保持原stable_id和持久字节。

## 两次真实定向补验

选原两篇真实论文的原问题q03（公式/表格）和q07（解释/信任），基线只读备份创建新副本；使用该基线冻结的真实全局Reasoning配置及OS凭据，未声称重新读取正式库当前选择。密钥仅内存使用，不读取或实验写入正式数据库，不重新抽取论文。执行前持久冻结最多2次初始请求账本，失败不自动重发。

两个P07v3均成功，共**19段**，无超时/Schema失败/第二槽续发。新增真实请求**2次**，prompt304,290、completion12,881、total **317,171 Token**，reasoning9,243为细分，供应商金额未知。预算已结束，不追加请求；前次10次及1,623,354 Token账本不改。

独立逐段语义审读为**16支持/3部分/0无支持**：q03为10支持，q07为6支持/3部分。q03仍无检测表格组，回答通过明确原文叙述支持定性说明并保留数量未知，不能写成表格恢复成功。q07残余三项分别为：将five rounds和five proposals括号等同；将组内前后显著改善扩大成组间优越；未来工作内容包括全上下文中的前段但仅引用跨页尾段。程序/Prompt未证明这些语义全正确，不能自动改写raw或无预算继续收费。原十题64/7/1和v2补验5/1保持，新19段单列，不能合并抹平失败。

程序补42个已有合法引用，不是新增科学来源；raw正文/归属不改，scientific_binding/展示审计/GET逐字段重建一致。普通问答期间45来源表及GraphRevision保持，旧Job/模型/raw/答案行保留，完整性/外键通过。随后显式保存两份综合，同/新键均幂等，完整引擎退出重启两次后答案、引用和保存可读，新增模型调用0。

当前源码再次读取旧十题/旧数值补验，答案完全保持；已知错数的新保存拒绝且不新增行，44原来源表及原任务/raw/事件保持。私人正文、逐段审读和副本仅.local，本报告只写匿名统计。

## 最终包与检查

`build-windows.ps1`完成PyInstaller/Tauri/NSIS。最终冻结smoke、原生Host显式1项、PowerShell5.1/System32-only PATH隔离17项通过。正常worker冻结并发两启，每轮7读200（0.078/0.078秒），写竞争标准503 DATABASE_BUSY，47来源表/Query计数保持，模型请求0。首次复用旧验收脚本时新报告路径被旧BASE边界拒绝，未启动实验；复制脚本到本轮独立BASE后通过，未放宽安全边界。

新安装器`.local/releases/p4-grounding-followup-20261105/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,839,020字节，SHA256 `23079790f3c7717e26cf9a9561b4b3308e039bd438554c7b60a6d2dc2b4d4e7d`；引擎SHA256 `5534b788f4a5afda87c00bb3a1cfb35321486e46bf92d41a5a37c40bf32cd079`。178运行源与最终回归前后及安装器一致，283资源与引擎副本逐字匹配，未含私人PDF/DB/密钥/日志；安装器与匿名delivery已封存，旧包保留。624源码候选内容/路径/Gitleaks、24提交历史Gitleaks、183 Markdown/824本地链接/88资产LF hash及diff为源码提交前实际成绩，4外部原文仍不可用单列。28实际暂存文件另经检查通过；最终文档补记再检查，不将旧计数写成新增检查。新包用户原生反馈另计。

## 远端最终结果

2026-11-05 11:33（Asia/Shanghai）确认独立run41959965368的windows及installed-app全部success，失败步骤0。新提交的环境复现、契约/后端/前端/构建、真实Edge、冻结引擎、Rust/Host、NSIS与产物上传通过；独立runner实际安装并以Windows PowerShell运行VerifyDesktop成功（03:31:17～03:31:57 UTC）。远端测试项数未提取，不声称等于本机934/124，也不用离线CI证明科学质量。

匿名run/jobs/summary及2份产物元信息保存于`.local/p4-followup-20261105/ci/followup/`，未下载或替用户安装远端产物。CI构建自己的安装器；本机封存包由上述本机冻结/Host/PowerShell验证及源码指纹配对，不将不同二进制哈希混写。最后仅提交验收文档，运行源码仍为75061d2。

最终文档收尾：624源码候选内容/路径/Gitleaks、25提交历史Gitleaks、10个实际文档暂存文件内容/路径/Gitleaks及暂存diff通过；183 Markdown/825本地链接无破损、88规范资产按LF核验一致，4外部原文不可用单列。文档提交不改变已通过CI的运行源码，完整交付指纹保存在本机delivery，不上传安装器或私人验收资料。

## 保留问题

检索本机目标已达成，但不是通用SLA；新真实19段仍有3部分支持，需要进一步改进术语、比较限定和逐句引用，不能宣称科学全通过。真实strict、多模型/平台、干净机、复杂版面无OCR与未检测表格/公式语义、S1～S4四份外部原文不可用继续保留。本轮止于P4，不自动进入P5。
