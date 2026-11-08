# P13 编号与字段协议修复验收（2026-11-04）

本轮按用户要求修复软件，不以更换模型为前提。仍在 P3/R5，不进入 P4/P5；head 0011、领域 reading-extraction-1.0、入口 paper-reading-v1 不变。架构决策见 [ADR0021](../../adr/0021-keyed-ranking-and-bounded-correction.md)。

## 根因与处理

只读检查上轮保存的四份 P13v2 失败响应：第一篇首轮40行/38个唯一编号，两个编号存在相反建议；续接覆盖38个编号，但多出未知根字段。第二篇首轮100行/99个唯一编号、遗漏6个，另有冲突；续接110行/101个唯一编号、遗漏4个，并有完全重复行和冲突行。没有输入外编号。旧数组传输没有把精确编号集合及唯一覆盖要求表达为运行 JSON Schema，只能生成后拒绝，重复整份列表容易再次失败。

新计划使用 `P13_reading_ranking_v3` / `reading-ranking-keyed-1`。程序将完整输入编号固定为 `assessments` 对象的 required 属性，模型只填写贡献建议、理由、说明和整数优先级；正式身份与稳定排序由程序完成。Prompt 与运行 Schema 同源核对，保留全部原文、支撑、疑点和数字排版风险上下文。

外壳、未知字段、未知编号、重复 JSON 键或非法 JSON 不合法时不保留任何槽位；合法外壳下独立合法的槽位仅作私有检查点。一次定向修复只输出缺失/不合法槽位，仍提供完整论文上下文及已完成建议以维持一致性。全部槽位完整后，阶段终验和 KnowledgeStore 发布再验仍是必要条件。不删字段、不合并相反建议、不猜补科学内容。

发送前持久化请求账本，每构建最多两次请求，含超时和投递状态不明的请求；继续不重发旧槽位。恢复从原始响应重建并校验，不信任已保存的“成功”标签。达到上限保留候选与旧图，反复继续不再收费。界面分别显示抽取批次与贡献评估进度、修复状态和停止原因。

## 旧任务与数据

原 v1/v2 计划、签名、raw 和历史记录不改。旧排序失败的“继续未完成批次”创建独立 v3 后继任务，不重抽 P02。P12 必须重验真实 ModelRun、冻结输入、manifest、候选快照、支撑路径及显式 adoption 链，才可零调用复用。缺少可信检查点时停止，不悄悄重新请求 P12。

对上轮隔离真实验收库只读核验：两篇原 P12 均可通过；第一篇通过显式谱系找到祖先任务的真实运行，第二篇为本任务运行。无真实 API 请求，无正式库写入。测试使用隔离、自造材料；没有迁移、删除或覆盖用户知识/PDF/Zotero/Obsidian。

## 实际执行

全部 Python 命令使用 Anaconda `researchgraph-studio` 环境。

| 命令 / 范围 | 实际结果 |
| --- | --- |
| `pwsh -NoProfile -File scripts/check-phase0.ps1` | 623 Python passed / 2 skipped；80 React；Ruff、格式、mypy 83源文件、pip依赖、契约导出、前端检查及生产构建通过 |
| 最终 `pytest -q tests/engine/test_reading_finish_upgrade.py tests/engine/test_reading_ranking_recovery.py` | 47 passed；最终谱系/参数保持改动另复验，30项旧任务兼容和17项实际编排恢复 |
| 新传输/恢复/预览针对回归 | 48 passed；含30项 wire、17项恢复及1项真实投影预览；其中后续续接兼容改动由上行覆盖 |
| `pnpm --dir apps/desktop test:browser --reporter=line` | 10项真实 Edge / React Flow 通过；悬停、拖动、固定、多论文、全屏及布局重启 |
| Rust fmt / clippy / test | 格式、警告作错误检查通过，9单测通过；需冻结引擎的1项默认忽略后独立显式执行通过 |
| `pwsh -NoProfile -File scripts/build-windows.ps1` | PyInstaller无控制台引擎、Tauri及NSIS构建退出0 |
| `python scripts/smoke-engine.py --executable <冻结引擎>` | 退出0；明确检查 `reading-ranking-keyed-1`、全槽位完成及重启知识/图谱保持 |
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-windows-install.ps1 -EnginePath <冻结引擎> -PdfFixture tests/fixtures/pdf/two-pages.pdf -OutputRoot <独立目录>` | PowerShell 5.1、17项通过；子进程PATH仅System32，不是干净机认证或用户安装模式 |
| `python scripts/check-sensitive.py --gitleaks .local/tools/gitleaks-8.30.1/gitleaks.exe` | 553个源码候选内容/私人路径规则及Gitleaks通过；最终文档收尾后另复验 |

第一轮全量回归607通过、1失败，原因是旧投影测试复用的显式fixture只识别旧 P13 title；扩展自造fixture支持新协议后最终623项通过。两项跳过为本机符号链接权限。首次PS验证的调用参数漏写`pdf/`目录，已更正并以新隔离输出目录重跑通过，保留失败日志。既有httpx弃用和前端大chunk提示保留。没有用异常响应放宽校验来获得通过。

## 交付与未验收项

最终安装器：`.local/releases/r5-protocol-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe`，38,708,292字节，SHA-256 `a10e7b14dbb9d8f283d3e973ce79fab92980cc974ae89cc6f1e158405f53b37c`。冻结引擎 SHA-256 `1879c766f393f6716ad83e7b9ca4aa594a5a69caa886b45ba13071b3d0c101d5`。安装器与构建源核对，日志、匿名结果及交付清单仅存本机忽略目录，保留所有旧安装附件。

退出旧应用后安装，在任务历史点击原失败任务“继续未完成批次”；可保持原模型配置，不需要删知识或重新抽取论文。若原任务快照/来源已变化，软件会明确停止并提示基于当前候选新建构建。没有替用户安装/卸载或频繁操作原生窗口；待用户反馈本包的贡献评估及图谱结果。

本轮没有新增真实模型请求，不能把离线协议测试写成当前模型真实 P13 成功。此前第二篇32条语义无支持候选、2条上标数值误读及同义代表/必要条件/支撑质量仍需真实复验。真实 native strict、新包原生、干净 Windows 账号验收分别待完成；四份登记外部补充原文路径仍不可用。未 Commit/Push，未执行远端 CI。

10:33（Asia/Shanghai）收尾：最终553个源码候选Gitleaks/私人路径扫描、164 Markdown/632本地链接/88资产LF哈希通过，四份外部原文不可用单列；git diff --check通过、暂存区为空。最终安装器与构建源/交付清单hash一致，验证日志配对封存。
