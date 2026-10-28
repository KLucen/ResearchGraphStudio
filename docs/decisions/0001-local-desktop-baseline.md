# ADR 0001：开发位置与本地桌面候选路线

日期：2026-10-27。状态：**历史暂案，技术路线已被 [ADR 0002](0002-tauri-evidence-workbench.md) 替代。**

以下保留当时的设计记录，不作为当前框架选择依据。QA.md 到位后已选择 Tauri 2，放弃本文的 Electron/Forge 暂案；源码根目录、Conda、数据隔离和 GitHub 远端决定继续有效。当前实施以 ADR 0002/0003 和[开发计划 v0.4](../development-plan-v0.4.md)为准。

## 开发位置

使用 `C:\Users\KLucen\Desktop\AI科研知识推理平台` 作为唯一源码根目录和 Git 仓库根目录。当前目录原为空，无需迁移或合并既有代码。

运行数据与源码分离：开发阶段使用被忽略的 `.local/`；安装版本暂定使用 `%LOCALAPPDATA%\ResearchGraphStudio\`，内含数据库、项目文件、索引和日志。此数据目录本轮不创建。只把有分发许可的固定样本放入 `tests/fixtures/`。

## 候选架构

| 层 | 暂定实现 | 原因与待验证点 |
| --- | --- | --- |
| 桌面入口 | Electron，候选打包工具 Electron Forge | 复用现有 JS 工具链；首轮验证安装包和引擎生命周期。包体与内存开销需实测 |
| 工作台界面 | React + TypeScript + Vite | 便于独立开发文献、证据、图谱、时间轴界面；依赖版本在建骨架时锁定 |
| 本地引擎 | Python 3.12 + FastAPI/Uvicorn | 文献解析、图处理与实验使用同一套 Python 核心；重任务进入独立进程 |
| 桌面与引擎连接 | 主进程管理本地引擎，受限 IPC / 回环请求 | 仅绑定 127.0.0.1，运行期随机令牌和端口；验证就绪、退出、崩溃恢复及重复启动 |
| 持久化 | SQLite + 文件存储，图节点/关系先用表表达 | 减少单机安装前置服务；向量索引和图遍历先做小样本性能验证 |
| AI 接口 | Provider 适配层 + 可复现的离线测试替身 | 隔离供应商，区分真实推理与演示数据；接入方式和凭据尚未配置 |
| Python 分发 | 优先验证 PyInstaller onedir，再随桌面应用打包 | 先验证干净 Windows 环境不依赖 Python/Conda；原生扩展必须实测 |

本机有 Node 24、pnpm 12 和 Anaconda。用户于 2026-10-27 明确要求 Conda 优先，Python 开发环境采用独立的 `researchgraph-studio`（Python 3.12），不再以 uv 环境为项目默认环境。环境管理决策已确认，应用框架仍待原方案校对。16 GB 内存、约 8 GB 显存下，先限制索引和推理并发；尚未测得模型吞吐或兼容性，不据此承诺本地模型能力。

依赖意图记录在根目录 `environment.yml`；Windows 的精确 Conda 包记录在 `conda-win-64.lock`，安装与升级后重新导出。后续若加入 pip 包，需另维护其版本/哈希锁定，Conda explicit 锁文件不覆盖 pip-only 包。保持 base 和其他环境独立。

开发仓库确定为 [KLucen/ResearchGraphStudio](https://github.com/KLucen/ResearchGraphStudio)。Zotero 安装位置已核实为 `D:\Zotero\zotero.exe`；这补齐了环境事实，不改变尚待校对的软件集成分工。

Docker、Redis、PostgreSQL、Neo4j 不作为这条单机候选路线的初始依赖。若原方案已指定它们，或实测数据规模需要服务化存储，应另记 ADR。Tauri 同样可作为替代方案，但当前 PATH 未发现 Rust 工具链，且尚未完成其打包前置验证。

## Zotero、Obsidian 与本软件分工建议

| 组件 | 建议职责 | 第一阶段边界 |
| --- | --- | --- |
| Zotero | 管理书目信息、文献组织和原始附件来源 | 可选导入适配器，保留 library/item/attachment 标识；不直接改写其内部数据库 |
| ResearchGraph Studio | 证据提取、主张管理、关系推理、人工校验、知识变化记录与实验 | 维护自身数据库、索引和版本；直接 PDF 导入可独立工作 |
| Obsidian | 长期笔记和人工写作 | 导出 Markdown、引用和来源链接；先不承诺双向同步 |
| MCP | 向外部 AI 工具提供受控检索/查询能力，或承接已有连接器 | 属于可选接口方式；具体是否采用须与原对话最后回答对齐 |

Zotero 本地 API 和 MCP 并非同一层：本地 API 是数据接口，MCP 可对数据接口再封装。直接 PDF 与 Zotero 导入应汇入同一导入模型，统一做文件哈希、来源记录和去重，避免两套处理流程。

## 数据与运行边界

- 文献正文、AI 提议、人工确认、正式知识版本分别保留状态，AI 输出不能直接成为已验证事实。
- 每次分析记录来源哈希、解析器/模型/提示词版本和时间；凭据不进入日志或图谱。
- 任务记录持久化，支持失败、重试、取消；重试不得重复生成同一导入文献或证据。
- 发布安装包前验证数据迁移与备份恢复。应用可离线打开已有文献和图谱；需要网络模型的功能明确显示不可用原因。

## 已核对的官方资料

- [Electron 打包说明](https://www.electronjs.org/docs/latest/tutorial/tutorial-packaging)：应用打包与安装分发需要配套工具；Forge 是官方教程使用的方案。
- [PyInstaller 使用说明](https://pyinstaller.org/en/stable/usage.html)：支持目录式和单文件分发，具体依赖仍需构建验证。
- [FastAPI 手动运行服务](https://fastapi.tiangolo.com/deployment/manually/)：本地引擎可使用 ASGI 服务方式运行。
- [Zotero API 文档](https://www.zotero.org/support/dev/web_api/v3/basics)：包含 Web 与本地 API 的区分。

访问日期均为 2026-10-27。以上资料只支持接口与分发可行性，不构成本项目已通过兼容性验证的证据。
