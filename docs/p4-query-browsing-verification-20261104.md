# P4 问答完整浏览与论文分组：实际验收

日期：2026-11-04（Asia/Shanghai）。范围：当前“问答与阅读知识”的来源预览、回答、已保存阅读知识及历史；不进入 P5。继承全部未提交 P4 实现，决策见 [ADR0025](adr/0025-query-browsing-and-paper-grouped-answers.md)。数据库 head 仍为 **0014**，本轮无新增迁移或真实模型请求。

## 实现与展示边界

- 来源预览、回答、保存列表/详情和历史分别提供论文多选，互不改变对方的展示筛选，也不改变输入区下一次检索/生成的论文范围。保存知识的衍生图跟随保存列表筛选。
- 新 `POST /api/v1/projects/{project_id}/query/search/page` 浏览本问题全部合法词面命中，先检查版本/来源/权限，再按展示论文范围过滤，每页固定 10 条，返回总数、页数和结果指纹。结果变化须刷新第一页，不能拼接旧页。原 search/prepare 默认 limit、冻结 snapshot/manifest/hash 与模型输入保持。
- 来源标记使用完整默认阅读投影，区分“默认图谱已有知识”“仅供检索、未入默认图谱”“图谱已有知识引用的原文、非独立节点”和不适用类型；不以当前画布分页或 Query 临时展开图判断。完整投影只收集一次，浏览不运行两两 Claim 比较。
- 回答按冻结引用真实根来源归为单篇、跨论文综合、个人资料与未归属内容；跨论文段落只展示一次，保留原文、引用及稳定段落标识。等待冻结引用读取完成再展示答案，避免先收到答案时误标归属。
- 来源、回答段落、引用、保存列表/详情及历史列表均每页 10 条，并显示总数与页码。保存勾选跨页/跨筛选保留，保存命令提交所有已选段落，界面显示已选总数；图谱画布不按列表规则截成 10 个节点。
- 每段回答的引用有两层默认折叠：外层引用容器、内层单条引用；展开外层不自动打开内层。独立“展开所有引用”和“收起所有引用”按钮适用于该段全部引用，包括其它引用页。

“全部内容”是当前问题在现有本地检索规则下的全部合法命中，并非所有数据库记录，也未新增“逐篇识别关键结论”语义检索器。历史问答可按原问题浏览当前命中，但旧答案仍只由其原冻结引用支撑；当前预览不会回写旧答案。

## 修改文件

后端新增 `query_browse.py`、`query_source_scope.py`，调整 `query_api/query_retrieval/query_graph/query_presentation/query_save` 与 `reading_projection`，增加分页、来源归属及投影边界测试。前端更新 `QueryPanel`、`queryApi`、`QueryDerivedGraph`，新增 `QueryBrowseControls` 及真实渲染 Edge 用例。Tauri 仅增加明确的 POST 浏览路由及原有 64KB 请求上限，生成 OpenAPI/TypeScript 同步；Prompt、模型协议和科学存储结构不变。

同步根 README、AGENTS、docs 导航/产品/交互/开发计划/运行 API、协作模板与进度；保留旧验收和安装包。

## 已实际执行

全部 Python 使用 Anaconda `researchgraph-studio` 环境，测试数据独立且为合成资料。

| 命令/范围 | 实际结果 |
| --- | --- |
| `./scripts/check-phase0.ps1` | 整体退出 0；Python **888 passed / 2 skipped**，394.70秒；React **122 passed**；Ruff、190文件格式、mypy102源文件、依赖、OpenAPI/TS契约、Prettier、TypeScript/ESLint与生产构建通过 |
| `pnpm --dir apps/desktop exec playwright test` | 首轮 **15 passed**，含真实图谱/工作区和新问答浏览用例 |
| `pnpm --dir apps/desktop exec playwright test e2e/query.spec.ts` | 最后加载时序修复后 **5 passed**；与全套交叠，不累加 |
| Rust格式/Clippy及单测 | `cargo fmt --check`、`cargo clippy --all-targets -- -D warnings`和 **15项单测通过** |
| `./scripts/build-windows.ps1` | PyInstaller、Tauri Release、NSIS 全部通过，构建退出0 |
| `python scripts/smoke-engine.py --executable <新冻结引擎>` | 通过：合成 HTTP/SSE 问答→保存→批注→重启→移除→重启，1次本地协议stub POST；既有导入/证据/图谱/历史/进程退出回归通过，不是实际模型质量认证 |
| `cargo test ... packaged_engine_connects_through_native_host_and_restarts -- --ignored` | 使用新冻结引擎，打包Host **1 passed**，两次启动握手正常；环境变量 `RGS_TEST_ENGINE_PATH` 指向该引擎 |
| `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/verify-windows-install.ps1 -EnginePath <新冻结引擎> -OutputRoot <新隔离目录>` | PS5.1、System32-only PATH隔离 **5项通过**（鉴权、诊断、临时工作区回收、项目幂等重启及EOF退出）；本次未给PdfFixture，不把旧17项记成本次成绩 |
| `.local/query-browsing-20261104/frozen_query_browse.py --engine <新冻结引擎>` | 29条匹配10/10/9、论文过滤28/1、图谱节点/被引用原文/仅检索标记、过期hash拒绝、两次启动结果一致；**47张非Query表哈希保持**，Query/模型记录与模型端点请求新增0，完整性/FK通过 |

专项覆盖 28 条来源按 10/10/8 完整遍历、过滤范围与查询范围独立、变更指纹/非法页、撤权后旧页拒绝、当前图谱/原文引用/未选候选区别，以及实际 145 节点图谱中画布页外的成员。浏览器用例覆盖 23 条来源、14 段回答、23 条引用、论文分组、跨页选择和嵌套折叠；组件另覆盖完整历史、保存详情及答案/来源反序加载。专项与全量测试交叠，不累加为总数。

保留 Starlette/httpx 弃用提示、Vite 大 chunk 提示和两项系统符号链接权限跳过；没有将跳过记为通过。

## 安装包与最终收尾

新包保存在 `.local/releases/p4-query-browsing-20261104/ResearchGraph Studio_0.0.1_x64-setup.exe`，**38,805,905字节**，SHA256 `8ae2e658dcff4f45ad47a6139332315355cdfb831a14c2b77886ce0e75a6b5d8`；冻结引擎 SHA256 `553b07939d864d4852abbba404bfafaa4804d09e56196bad9edd02192542f076`。174份运行源码指纹与281份资源（排除生成pycache）一致，安装包保留独立副本，不覆盖历史包。资源无私人PDF、数据库、密钥或日志。

构建、冻结协议与原生Host通过；本轮未安装该包或使用用户正式资料交互，新包用户原生结果仍待反馈。第一次Host命令因当前终端PATH无cargo未执行，改用 `.cargo/bin/cargo.exe` 后实际通过；不将未执行尝试算通过。离线browse样本预检发现启动会为新增合成块回填锚点，已在样本构造时先登记完整锚点，再用不变表基线验收；没有改变产品代码或掩盖科学写入。

最终 **610份源码候选实际内容/路径及Gitleaks**、**175份Markdown/768本地链接/88规范资产LF哈希**通过；4份外部登记原文仍不可用，未伪造核验。`git diff --check`通过，暂存区为空。匿名命令日志和delivery记录保存在忽略目录，不进入源码提交；安装器副本与构建输出hash一致。

## 限制与下一步

本轮没有读取/修改正式用户数据库作实验，没有新真实/付费模型调用、翻译请求或重新抽取；未使用 Computer Use，也未替用户安装/卸载。代码回归、离线 HTTP/SSE 协议和用户原生反馈分别记录。新包原生交互与现有私人资料效果仍需用户安装反馈，真实 strict、干净机、无 OCR/复杂版面与 S1–S4 四份不可用外部补充原文的限制继续保留。

没有 Commit/Push，原有上传授权不自动延伸；HEAD 和本地 origin 记录仍为 `80552d3`，历史 R5 CI 不算本轮 Query CI。完成本轮安装包交付后停在 P4，不自动进入 P5。
