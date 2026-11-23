# 侧栏空间、知识图关系合同与本机恢复验证

日期：2026-11-21（Asia/Shanghai）。本报告覆盖左侧个人研究空间布局、`KNOWLEDGE_RESPONSE_SCHEMA_INVALID`关系错误的定位与恢复、文档记录、回归和Windows隔离安装。

## 结果

个人研究空间现在是侧栏主要弹性滚动区；移除顶部品牌块和底部宣传/版本内容，统一导航字号、行高与图标尺寸，保留项目/论文选择、新建、导入、折叠和键盘操作。新建项目不再沿用上一个论文选择。Edge实测1280×800、1440×1024和900×640，论文树至少占侧栏高度45%且独立滚动；620/390窄屏可展开、滚动并选择长列表论文。

正式失败任务的只读检查确认返回完整JSON（19个模型知识节点、20条模型关系），JSON字段、来源和节点有效，关系端点类型/方向中有11条不符合程序已有关系规则；其余19节点、9关系及引文/来源均通过原验证。没有改写原始响应、失败状态或账本，也没有发起真实模型请求。

新知识提取Prompt/Schema版本`paper-knowledge-extract-2`由实际关系端点规则生成；旧任务仍按精确v1合同处理。失败诊断在任务记录逐条说明错误关系的字段位置、类型和两端节点，不展示raw或论文正文。用户从对应失败任务打开本机恢复预览，查看原始/保留数量和逐条隔离原因；确认后只隔离确定不合法的关系，完整重验其余字段、引用和当前来源，并发布明确标记为`partial`的版本。知识库只提供任务记录跳转，不重复显示原因。原任务仍为failed且raw/账本不变；不请求模型，也不触发联系分析。恢复记录读取时从原raw重新构建验证。任务列表仅为当前页失败抽取任务计算完整恢复预览，避免对分页外历史任务重复验源；任务记录不会跟随每次进度轮询重复拉取恢复候选，打开预览/确认则分别重验。

相关决策见[ADR0064](adr/0064-knowledge-relation-contract-and-local-recovery.md)。本轮模型调用故障经验与固定排查流程已汇总到[大模型调用故障与修复经验](llm-integration-lessons.md)，并追加至`DEVELOPMENT_LOG.md`。

## 验证

- `scripts/check-phase0.ps1`：最后一次完整后端 **906 passed / 1 skipped / 1 warning**（159.81秒）；位置调整后完整React **222 passed / 20 files**（15.55秒）；Ruff、mypy **112 source files**、依赖锁12项、依赖完整性、OpenAPI/TypeScript契约、TypeScript/ESLint、Prettier和生产Web构建通过。保留既有Vite大型chunk提示和Starlette/httpx弃用警告。
- 知识恢复API专项：**15 passed**；覆盖旧v1精确Prompt/schema哈希、全关系端点矩阵、19/20→19/9预览、明确发布partial、原失败/raw/用量账本保留、来源改变/陈旧指纹拒绝、重复确认幂等和不回退新当前版本。
- Edge完整 **44 passed（27.6秒）**；包含任务记录中本机恢复先预览再显式确认且零模型操作、知识库不重复原因、侧栏桌面高度和独立滚动、键盘/导入/新建、620/390窄屏访问。
- Rust Host：**17 passed**；包含知识恢复路由白名单和打包sidecar连接、停止、重启。第一次未设置`RGS_TEST_ENGINE_PATH`的探针未通过；随后为本轮打包sidecar设置路径复跑，完整17项通过。
- 首次Windows NSIS包和隔离安装通过；后续将恢复入口按用户此前要求移到任务记录，首次包 **160,726,447 bytes**、SHA-256 `C8F722D6A23FFD323E252FCAA3FB9598DFF5CDDB25BE5D013CA55643D9C0BF0D`保留作中间验证证据，最终交付以下方最后记录为准。
- PowerShell 5.1全新隔离静默安装/sidecar smoke通过：schema `lite0018`、匿名PDF导入、模型章节/公式/表格材料、章末阅读状态、旧本地材料清理/重建及删除、引用PDF保留，模型调用0。安装版知识库K1–K3合成HTTP闭环通过：合成建模2次、联系分析1次、全部只走loopback，GET及重启没有额外调用；**这不是实际模型质量或真实用量验证**。
- 新包安装副本位于`.local/verify/knowledge-relations-recovery-20261121/install/installed`；原安装器位于`.local/releases/knowledge-relations-recovery-20261121/ResearchGraph-Studio-Knowledge-Relations-Recovery-0.0.1-x64-setup.exe`。两处均保留。

## 最终交付

位置调整后重新封装的最终未签名[安装器](../.local/releases/knowledge-relations-recovery-20261121-final/ResearchGraph-Studio-Knowledge-Relations-Recovery-0.0.1-x64-setup.exe)，**160,737,754 bytes**，2026-11-21 15:26:08构建，SHA-256 `84C4980EE3772CCAC65D50E4FD4C1DE6F5A49E51D8F641D87ABDD2761E4E4A36`。PowerShell5.1在新的`install-final`目录完整安装/sidecar验收通过；前述匿名PDF、材料、章末状态、旧解析清理/重建与源文件保留断言全部通过，模型0。

`scripts/smoke-knowledge-local-recovery.py`使用合成19/20关系失败raw，在源码、打包引擎和最终安装版通过真实HTTP预览/发布/重启：保留19模型知识节点/9关系、11项隔离；错误指纹409、确认前GET零发布、显式POST唯一partial、同幂等键跨重启同一版本，原failed/raw/usage/job保持，Provider/模型/自动联系事件0。最终安装版Host **17 passed /0 ignored**（3.35秒）。166项运行源/配置构建后首次核对稳定；最后仅JobHistory排版收尾，重新Web构建的全部62项产物逐字节保持相同。安装sidecar SHA-256 `029FAFBBCF09F16D3D7CC9C7E33A91A77D1BC42DCBCD1F830AA326036FADD850`及334项内部资源与打包源逐文件一致。最终格式与Gitleaks/私人路径500文件扫描通过，相关文档本地链接有效，`git diff --check`通过。

安装后到“任务记录”打开对应失败的“论文知识建模”条目，先查看安全错误原因，点击“预览本机恢复”检查保留/隔离内容，再点击“确认保存为部分知识”。旧正式失败任务没有由本轮开发自动恢复或收费重试；来源改变或仍有其它字段/引用问题时将拒绝本机发布。用户真实关系输出质量和原生桌面体验仍需单独反馈。

## 清理状态与边界

只读清理盘点列出`.local`中的 **61个旧纯二进制展开副本**（18个release引擎、43个隔离安装），共170,962个文件、18,925,580,649逻辑字节（约17.63 GiB）。删除前已逐项重新验证路径位于`.local`、根内容白名单、候选大小/文件数与审计快照一致、无重解析点；本轮新安装器和新installed副本明确排除。删除命令随后被自动安全审查以“blocked by policy”拦截，**实际没有删除任何候选目录**，也没有尝试以其它方式绕过拦截。原安装器、报告、hash/manifest、数据库/备份和所有当前任务安装证据均保持。

仓库源码扫描未发现可确定安全删除的未用文件；不按文件名猜删历史报告、迁移、锁文件或兼容协议。正式数据库只读检查、实验写入0、真实模型/外部HTTP请求0、未Commit/Push，未覆盖用户日常安装。

真实供应商关系输出和论文科学质量、用户日常桌面原生体验仍需后续单独验收。关系规则校验和引用通过不证明科学关系正确；恢复版本会持续显示partial。
