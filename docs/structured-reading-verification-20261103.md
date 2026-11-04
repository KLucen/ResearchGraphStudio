# 结构解析、默认支撑图谱与空占位响应验收

日期：2026-11-03，Asia/Shanghai。范围为当前 R5，不进入 P4 Query/P5 Lint/Wiki。决策见 [ADR 0014](adr/0014-structured-pdf-and-support-graph.md)。本报告不包含私人论文标题、原文、模型响应或密钥。

## 实现

- 复用 PyMuPDF，新增 `pdf_structure.py`、`document_structure.py` 和 `structure_models.py`。结构产物包括跨页章节树、阅读顺序、行/字体/bbox、可识别表格的行列/表头/单元格及合并跨度。原始 Chunk 文本、坐标和块索引不变。
- Alembic 0011 仅新增 `document_parses`，按文献版本/解析器版本唯一。旧库先一致性备份；旧证据不重编号。新导入建立完整原文块证据；旧来源补解析必须 hash、全部文本块和坐标匹配。GET structure 新增 `structured_document`，旧 sections/evidence 保持。
- 新阅读任务使用 `P02_reading_extract_compact_v3` 和 `section-context-v1`。跨页章节连同子节整体输入，保留子节路径，不设 6000 字符/48 证据目标；已知模型容量不足才按完整段落/表格组拆分。References 和重复页眉页脚保留但不送给模型；每个章节采用相同抽取规则。跨章节表格合并上下文，混有排除材料的表格元数据不送入模型。历史冻结计划和成功操作继续使用原分组。
- 默认图谱展示 Paper→核心 Claim→有据非 Claim 支撑，方法、实验、条件等不再等待手动展开。`collapsed_unit_ids` 显式收起，`expanded_unit_ids` 优先。仅沿有效来源关联/显式依赖补全，不凭共享证据推测归属，不跨另一个 Claim；共享节点去重，旧快照不改写。
- 仅兼容 Claim 上精确的 `kind_note_unused: null`，记录 `reading_wire.expanded_fields`，原始响应保留；非 null、其他类型或未知字段仍拒绝。完整 Schema、证据白名单、quote/offset/hash 及 Store 检查保持。

## 真实资料的隔离验证

正式库通过 SQLite 只读备份访问，迁移、重解析与响应回放只在 `.local/structured-reading-20261103/` 副本执行。未改用户数据库、PDF、Zotero 或凭据。

实际失败响应为完整 JSON，第二个 Claim 多出一个 null 占位字段。限定适配后零新调用重验，4 候选、0 关联通过 KnowledgeStore；重复 apply 幂等。262 条旧知识和 47 条旧 ModelRun 的全部原列保持，原始失败响应不变。没有因本次重验调用真实 API，也没有将其记为新 Prompt 的真实生成成绩。

现有真实候选与有效关联的只读投影显示 38 节点/54 边，其中 4 Method、1 Experiment、2 Condition；另有结果、概念、研究问题、指标、论据及限制。全部支撑收起后 10 个 Paper/Claim 节点，边端点闭合，无分页遗漏。无关联的 4 条回放候选不会被编造进某个结论分支。

两篇真实 PDF 完整重解析结果：27 页/766 块形成 35 个章节节点、29 个检测表格；9 页/159 块形成 14 个章节节点、2 个检测表格。参考文献分别排除 30/6 个原文块；页眉页脚另排除。迁移和重解析后 44 个旧表全部原行保持。按 1M 上下文/384K 输出做离线容量规划，分别得到 11/6 个章节窗口，最大 18270/18895 字符；这是计划复核，不是模型调用或全文生成成绩。

## 检查记录

使用 Anaconda `researchgraph-studio` 的绝对 Python 解释器；主要命令：

```powershell
.\scripts\check-phase0.ps1
pnpm --dir apps/desktop test:browser
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml
.\scripts\build-windows.ps1
python scripts/smoke-engine.py --executable <packaged-engine>
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/verify-windows-install.ps1 -EnginePath <packaged-engine>
python scripts/check-sensitive.py --gitleaks .local/tools/gitleaks-8.30.1/gitleaks.exe
```

完整回归首轮发现三项兼容问题，已修复：P01 不再发送无直接证据的结构父节点；旧 48/7 批恢复测试按真正旧库索引构造，并验证冻结配置、chunk 哈希、成功批次及原响应保持。三项失败定向重跑通过，相关 30 项兼容回归通过。最终结果如下：

| 检查 | 实际结果 |
| --- | --- |
| Python 最终完整回归 | 283 passed / 2 skipped；两项文件符号链接测试受 OS 权限限制 |
| React / 真实 React Flow | 47 / 3 passed，覆盖默认支撑、收起、拖动、悬停、固定和共享节点 |
| Rust / 打包宿主 | 9 单测 + 1 原生宿主集成 passed，0011 握手及重启通过 |
| 静态 / 依赖 / 契约 / 构建 | Ruff、格式、mypy 72 文件、pip check、OpenAPI/TS、前端检查和 Windows NSIS 构建通过 |
| 冻结引擎 / PowerShell 5.1 | smoke 通过；EnginePath 五项通过，子 PATH 仅 System32；未执行新版安装器的完整安装卸载验收 |
| 参考契约回归 | 当前 78、归档 v3 12、归档 v2 5 passed；不替代运行软件回归 |
| 内容安全 / 文档 | 502 个源码候选文件通过路径检查及 Gitleaks；146 Markdown / 493 本地链接 / 88 清单资产通过，四份已登记外部原文不可用 |

PowerShell 5.1 默认策略拒绝首次脚本启动，后用仅该进程的 ExecutionPolicy Bypass 执行成功，未修改全局策略。前端打包仍有单 chunk 大于 500 KiB 的构建提示，不影响构建成功。

## 安装包与复核步骤

安装器保存在仓库下 `.local/releases/structured-reading-20261103/ResearchGraph Studio_0.0.1_x64-setup.exe`，38613199 字节，SHA-256：

```text
d7419a151355bdbf409b7e3b4c1e01cf1a5a875e33ef52b04d68959aeb914cf2
```

同目录 delivery.json、冻结 smoke、PowerShell 和宿主报告均保留在本机，不进入源码。本轮未替用户安装、卸载或覆盖正式库；原生安装体验等待用户反馈。

1. 退出当前软件，运行新安装器并打开原项目，核对文献与已有知识仍可读取。
2. 对原 Schema 失败任务点“继续未完成批次”，确认已保存批次保留且空占位响应可复用。
3. 选择一篇论文新建抽取任务，核对新的章节窗口、无固定 6000 字符拆批、References 排除以及模型进度。该步骤会使用用户配置的真实 API。
4. 打开图谱，检查核心结论下的方法、实验、条件支撑和收起/恢复，再核对证据；没有有效关联的内容保持候选，不补造连线。

## 限制与用户复核

章节/双栏/表格由版面与目录启发式识别，不能保证每篇论文的语义结构准确。无 OCR、公式语义或通用复杂无边框/跨页表格保证；无法确认时保留原材料和警告，不补造行列。table resolved 只表示网格被检测，不认证科学解释。

本轮没有使用新 Prompt 对两篇真实全文重新付费生成；真实生成质量、全文长章节超时表现和用户安装后的原生交互仍需反馈。继续失败任务复用已完成批次和可重验响应；若要验证新的章节规划，应创建新的抽取任务，旧冻结任务不会被暗中重排。

四份外部补充原文的登记路径仍不可用，不能记为核验通过。没有新增 Commit/Push 授权，本轮不上传源码或私人资料。
