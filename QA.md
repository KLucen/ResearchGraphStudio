Q：我感兴趣的软件方向是：06 ResearchGraph · 科研知识推理。作品侧重点：创新、实用和可实现性均衡。请进一步对比这些方向的技术创新点、现有同类软件、核心功能、具体交互形式和可行性，帮助我最终确定选题。ResearchGraph：AI科研知识推理平台——选题深化与可行性研究

方向：AI Agent × 科研知识图谱 × 跨文献推理 × 可解释人工智能

ResearchGraph 是一个值得深入考虑的方向。相比传统的AI论文阅读助手，它可以进一步解决科研中一个很实际的问题：

读完多篇论文后，如何知道这些论文之间究竟有什么联系、哪些结论相互支持或矛盾，以及下一步值得研究什么？

我建议把 ResearchGraph 定位为：

> 一款能够安装在个人电脑上的科研知识推理工作台。用户导入论文后，AI自动抽取研究问题、方法、实验结果与证据，建立跨论文的知识关系，并支持可追溯的科研问题分析。

不过，这个方向已经有不少成熟产品。要形成有价值的创新作品，不能只做“上传PDF—AI总结—生成知识图谱”。

## 一、ResearchGraph 可以发展的四条路线

![Connected Papers (@ConnectedPapers) on X](https://images.openai.com/static-rsc-4/gvanlEcZNaj2QLK9npiaJOP4sTub2gGuHH7fSG7NWeF8NGSP8KxJU3eFYi7dpwwewoXzHbtIW6eq8LX1W_a_KqmbDla0ZhU2-gvX5j3Myn6zccPZwmgFxN0_pWaj5WXbaWPPx8AImF2EDTBTPvcAfZuRiJwbZMhJTzQ2CnppeuY?purpose=inline)

A. 科研文献关系可视化

把论文组织成引用网络、主题聚类和知识地图，帮助用户发现相关研究。

主要价值是文献探索和研究脉络梳理。技术成熟，适合作为基础功能，但单独作为创新点较弱。

![Priyanka Kargupta](https://images.openai.com/static-rsc-4/g5v8ieXCidSZD-E1KXA8q4J4mf0PPQ0bGvYe1UWdnGUnQyzbWOWiA96XA01yrTSsgtiJ7mRORrV-HEBh6E_HgpQxxnvDPEgDlxren8lfMlzdEgMunDkuIiPju86en-YDqOvHkUNe8Rh_IT-tVO3Rj1IWEQq-jHFtgHbJKRfGI84?purpose=inline)

B. 跨论文论点与证据推理

AI不仅识别论文引用关系，还抽取具体的研究主张、实验条件、结果和证据，判断哪些结论相互支持、限制或冲突。

研究价值较高，也容易通过证据准确率、关系识别质量和溯源正确率开展实验。

![ChatAcademia — Supercharge Your Research With ChatAcademia](https://images.openai.com/static-rsc-4/H7rz5VzOvYttZr1cwzjDww97t-vBRDIEK8oInTtokHC2DsGzCtuEEjGYW0fEOk7hTI1-lMktrShrrzGwZ4OyZ80Lon2j0chuMthKih0kt4R6qoBhSQzwW5vsASmReTABCQkdPbzVGT9Qx3ZPt31BkBhUVAm1Y754DUP3cL0nNOI?purpose=inline)

C. 科研问题与假设探索

用户提出一个研究问题，系统分析已有证据、尚未解决的限制以及可能的研究路径，提出可检验的研究假设。

创新潜力很高，但“研究空白”和“新颖假设”很难自动验证，容易产生看似合理但没有依据的建议。

![Connecting the dots: knowledge graphs for all – Scholarcy](https://images.openai.com/static-rsc-4/mUDFfb2BoAUsH7YPtyDBcdjWjXCdcUEtaqv6yXqZd4zGSgIQUi0WXMCT1in-yweqRlf5oSA0b5gHGKSrnXsbZdSpTnMs454OvGyn_es18aNSl_AyD2gxB7AwAq47oVDV_IFCfRpZqzzFw-4kDDtgYJ0w6_QsjOKdKHCAJTFAx-w?purpose=inline)

D. 个人科研知识持续演化系统

将论文、精读笔记、个人观点和研究问题连接起来，随着阅读不断更新知识结构，并记录观点如何发生变化。

实用价值高，适合长期使用。挑战是知识合并、版本管理，以及如何区分论文事实和用户自己的推测。

### 路线对比

| 路线             | 创新潜力 | 实用价值 | 实现难度 |
| ---------------- | -------- | -------- | -------- |
| A 文献关系可视化 | 中低     | 高       | 低～中   |
| B 论点与证据推理 | 很高     | 很高     | 中高     |
| C 科研假设探索   | 很高     | 高       | 高       |
| D 知识持续演化   | 高       | 很高     | 中高     |

初步推荐：B + D 作为核心，C 作为后续拓展，A 作为辅助可视化。

这个组合比单纯的论文知识图谱更有研究价值，也能形成真正适合日常科研的软件。

## 二、现有产品调研：ResearchGraph如何避免重复造轮子？

以下是最值得参考的现有产品。

![Features | ResearchRabbit](https://images.openai.com/static-rsc-4/O1XJZ7lxZLQG5zxyY0Ohyo2_hwRGjrQGTnYgIwKB-wh8H8zRV1AzpbMNDorT-rUzhSJWppZ0oF2p2bEGqAg8Dpqb5rnIYAQra8fGTC1_u-ZLpUPc0GcJAW-HOmKG8NsoqNpgaan5yK5FmwM7wmURcbK_B6Ns5XKR7seswa2ANpw?purpose=inline)

ResearchRabbit

文献发现与可视化

提供论文、作者及研究主题之间的关系探索和文献推荐。适合借鉴其交互式文献地图，但我们的重点不应停留在论文之间的连接。

![img](https://www.google.com/s2/favicons?domain=https://www.researchrabbit.ai&sz=32)

ResearchRabbit



![Using AI To Make Scientific Research More Reliable | Paperspace Blog](https://images.openai.com/static-rsc-4/QUwbDbd6o5DRFEsR1jzDpzfTBd4pPC_BSMwtE06tJN-Ge6vxYrp3NJuFrPQs_0bsYZn8QWaKTcrxv7jPEhpGjF27zATuyfq4CoM__IOIo8ILtlktlr1ez14GfQHLVFlAuqY2Q_xks4_gguRcqwcatR8N4gNmZfcMoi6qCOogHMU?purpose=inline)

Scite

引文证据与支持、对比关系

已经能够识别引文语境中的支持、对比和提及关系。因此，仅增加“论文支持或反驳”的标签并不构成足够强的创新。

![img](https://www.google.com/s2/favicons?domain=https://scite.ai&sz=32)

scite.ai



![Elicit: AI for scientific research](https://images.openai.com/static-rsc-4/prN8561DMThc6JTjStT3yCCA1t4n2VC4LyVKyxe5i-i4yyuPNA70Ekkn5NDurz8ygDIDLBrEeAy6qmBqIfdjYObHZRh5gqNtXVr-sPGT35PbzkDTpXFb-yn2-Y6Ruxnp1PLl0wLYpmlLRWFNOptueRZNWigMnTOwFAOvDU-3GSA?purpose=inline)

Elicit

文献综述与结构化信息提取

适合参考其研究问题驱动的论文筛选、数据提取和对比表格工作流。ResearchGraph需要在提取之后增加知识演化与证据推理。

![How I take notes as a developer is quickly evolving | by Bennett | Medium](https://images.openai.com/static-rsc-4/dBjG9BZYKIg_zuzYUFPNcXXfJ_y26JrofOD8gJz723xt18tO_G_emMMRXH4SxlmLpCvZXkb2-J_vF3bDyDI4SeWusGXYRpm779U5sp7fx9t2FhmdTHyr_5b0OCnifpaBWyO-B4DD2m3wE_LTU7S3Jp0HKWUuXOa7le4_74gR3oE?purpose=inline)

Obsidian + Zotero

个人科研知识管理

前者适合笔记组织与链接，后者适合论文和引文管理。ResearchGraph应尽量兼容它们，而不是重新制作一套PDF文献管理器。

### 竞品能力与差异化定位

| 能力               | 现有代表产品     | ResearchGraph拟重点实现      |
| ------------------ | ---------------- | ---------------------------- |
| 文献关系网络       | ResearchRabbit   | 作为基础视图                 |
| 引文支持与对比     | Scite            | 深入到具体研究主张与实验条件 |
| 论文信息提取       | Elicit           | 保留可核验的证据定位         |
| 个人科研笔记       | Obsidian         | 同步用户确认的知识           |
| 跨论文条件化推理   | 各工具能力不一   | 重点创新                     |
| 知识版本与修订追踪 | 需进一步竞品验证 | 重点创新                     |

因此，我认为真正值得研究的不是“让AI自动画知识图谱”，而是：

在研究条件不同、证据不完整、论文结论可能冲突的情况下，如何让AI构建可验证、可修订的科研知识结构？

## 三、建议的最终产品形态

## ResearchGraph Studio

面向科研工作者的证据驱动知识推理桌面软件

ResearchGraph

研究工作区 · 概念界面

论文库

12篇文献

Paper A

多智能体协作

Paper B

社会推理

Paper C

群体决策

知识关系图

支持

条件差异

证据分析

论文A与论文B对协作效果的结论存在差异，但两项实验的智能体数量、信息共享机制并不一致。

待核验 · 2处证据

查看证据

界面结构示意，非已开发软件。论文和分析内容均为演示占位数据。

### 核心交互流程

1. 选择研究主题。 例如“多智能体社会推理能力”，建立一个独立研究工作区。
2. 导入论文。 从Zotero选取Collection，或直接导入PDF，系统自动识别标题、章节和实验内容。
3. 抽取研究知识。 将论文转化为研究问题、主张、方法、实验条件、结果和原文证据。
4. 构建知识关系。 AI提出支持、冲突、改进、条件限制等关系，用户可以审核、修正。
5. 进行跨论文推理。 选中某个问题，系统生成对比分析，并提供可跳转的原文证据。
6. 持续更新知识。 新论文进入后，只重新分析受影响的节点和关系，记录哪些结论发生变化。

这里最重要的交互设计是：每个知识节点都能追溯到论文原文，而每个AI推断都可以被用户确认、否定或标记为不确定。

## 四、真正值得做的三个技术创新

### 创新一：具有实验条件约束的证据关系推理

两篇论文得出不同结论，不代表它们真的矛盾。

例如：

论文A：在3个智能体的合作任务中，共享记忆提高了成功率。

论文B：在20个智能体的竞争任务中，共享记忆降低了整体收益。

ResearchGraph不能直接将其标记为“相互反驳”，而应该比较任务类型、智能体规模、记忆机制、评价指标和实验设置。

这就把简单的文本语义相似度问题，转化为具有条件约束的科研论证推理问题。

### 创新二：人机协同的知识修订机制

AI抽取的知识不是立即成为可信事实，而是经历：

AI提出

阶段 1

证据核验

阶段 2

用户确认

阶段 3

知识入库

阶段 4

系统保存模型建议、证据、用户修改和最终状态。

当后续导入的新论文提供相反证据时，系统不会直接覆盖旧结论，而是提醒用户重新审查。

### 创新三：面向研究问题的知识图谱增量更新

传统的静态知识图谱强调已有知识之间的连接。

ResearchGraph可以进一步研究：当新证据出现时，如何识别受影响的主张、重新评估关联关系，并保留此前的知识状态？

这可以形成比较清晰的算法实验：

- 全量重新推理与增量更新的时间、成本比较。
- 不同证据抽取策略的准确率比较。
- 有无人工审核时知识关系的可靠性比较。

## 五、技术实现与打包可行性

建议使用：

| 模块       | 技术选择                     |
| ---------- | ---------------------------- |
| 桌面客户端 | Tauri 2 + React + TypeScript |
| AI处理引擎 | Python + FastAPI             |
| 文献解析   | PyMuPDF + 结构化文本解析     |
| 语言模型   | 可配置云端API / 本地模型     |
| 数据库     | SQLite                       |
| 知识图谱   | SQLite关系表 + React Flow    |
| 检索       | 全文检索 + 向量相似度        |
| 文献集成   | Zotero Local API             |
| 安装包     | Windows安装包优先            |

Zotero已经提供本地API，可以在用户允许本地通信后读取文献库信息，甚至定位本地附件，因此没有必要重新实现一套文献管理功能。

![img](https://www.google.com/s2/favicons?domain=https://www.zotero.org&sz=32)

Zotero Documentation



如果以后需要从互联网扩充文献元数据，还可以利用 OpenAlex API 获取论文、作者、主题等关联信息。

![img](https://www.google.com/s2/favicons?domain=https://help.openalex.org&sz=32)

OpenAlex Help Center



### 开发范围控制

建议第一版限定为：

MVP：可安装实验版

建议优先

目标：6～8周完成，假设1名具备开发基础的学生、使用成熟模型API。

支持导入10～30篇PDF或Zotero论文

抽取论文主张、实验条件与证据

显示可交互的论证关系图

支持点击节点查看原文及页码

允许用户确认、修改、删除关系

对选中研究问题生成跨论文分析

保存项目并导出实验数据

第一版暂不做自动论文搜索、全学科知识库、完全自主科研Agent，也不承诺准确发现真正的新颖研究方向。

## 六、与SocioSim相比，哪个更值得做？

考虑到你刚才也关注了SocioSim，我把两个方向放在同一标准下比较。

| 维度               | SocioSim               | ResearchGraph                 |
| ------------------ | ---------------------- | ----------------------------- |
| 核心问题           | AI如何模拟社会互动     | AI如何组织与推理科研证据      |
| 主要用户           | AI研究者、仿真实验人员 | 研究生、科研人员              |
| 日常实用性         | 中等                   | 很高                          |
| 可量化实验         | 有，但行为有效性难验证 | 较明确，可用人工标注证据集    |
| 界面表现           | 社会网络、行为时间线   | 知识图谱、证据链、研究演化    |
| 第一版开发风险     | 中高                   | 中                            |
| 与现有科研工具结合 | 一般                   | 很强                          |
| 后续研究空间       | 社交智能、群体决策     | 科研推理、可信Agent、知识演化 |

我更倾向于你选择 ResearchGraph 作为第一个可安装的软件作品。

原因是它可以直接在真实科研工作中使用，也能通过小规模人工标注数据集检验其算法效果。相比SocioSim，不需要先解决“模拟出来的社会行为是否接近真实社会”这个困难的有效性问题。

当然，ResearchGraph的创新性也不是天然更高；它需要把证据推理和知识修订真正做好，才能超越普通论文助手。

## 七、最终选题建议

建议使用以下正式题目：

《基于证据约束推理与增量知识演化的科研知识图谱系统设计与实现》

英文作品名：ResearchGraph Studio

研究核心可以凝练为：

> 面向多篇科研文献，研究如何在实验条件约束下自动识别研究主张之间的支持、冲突与限制关系，并通过人机协同审核和增量更新机制维护可追溯的科研知识网络。

这个题目同时具备软件产品价值、明确的算法研究问题和可实施的实验路径。

### 最后需要确定一个产品定位

方案一：证据推理实验平台

重点研究跨论文主张识别、证据匹配、冲突判断和算法评测。科研性最强。

方案二：个人科研知识工作台

重点实现Zotero集成、知识组织、精读关联和长期维护。实用性最强。

方案三：证据推理 + 知识演化一体化

以证据推理为核心，以长期科研知识管理为应用场景，兼顾研究与实际使用。推荐。

按选定方案继续深化设计 

如果以你已有的Zotero、Obsidian和AI Agent科研阅读思路为基础，方案三尤其合适：让Zotero负责原文管理，ResearchGraph负责证据推理与知识演化，Obsidian继续负责人工精读笔记，三者职责清晰，不必相互替代。

Q：我决定选择ResearchGraph Studio的方案三：证据推理与知识演化一体化。请继续细化软件的产品需求、模块功能、交互原型、核心算法设计、数据结构、技术架构和分阶段开发计划，特别关注可安装运行、创新性验证与实验设计。

# ResearchGraph Studio

产品需求与技术设计方案 v1.0 · 证据推理 × 知识演化 × 人机协同科研

我们将 ResearchGraph Studio 正式确定为一款可安装、可运行、可进行科研实验的桌面软件，而不只是一个大模型论文阅读界面。

## 一、产品定位与设计原则

## ResearchGraph Studio

从论文原文到可验证、可演化的科研知识网络

用户导入论文，系统抽取研究主张、实验条件与证据；在跨论文层面识别支持、冲突和条件差异；通过人工审核构建可信知识网络，并随着新论文加入持续更新。

### 核心设计原则

1. 证据优先： 每条研究主张必须关联原文证据，推断结果不能伪装成论文事实。
2. 人机协同： AI负责提出候选知识关系，用户负责核验、修订和确认。
3. 增量演化： 新论文加入时优先更新受影响的知识，而不是无差别重建整个图谱。
4. 可复现： 每次实验保存输入、模型版本、提示词、参数、输出和评价结果。
5. 本地优先： 项目数据和知识库保存在本地，AI推理允许选择云端API或本地模型。
6. 工具兼容： 与Zotero和Obsidian协作，不重复开发完整的PDF管理器与笔记软件。

### 产品边界

第一版支持Windows 10/11，优先开发Windows安装包。macOS和Linux作为后续兼容目标。

第一版重点处理英文计算机科学论文，支持约10～30篇论文组成的研究工作区。对于扫描PDF、复杂公式、跨页表格和图表证据，允许用户手动校正，避免过度承诺自动解析效果。

## 二、软件功能架构

\#chatgpt-mermaid-_r_10c_{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:16px;fill:rgb(13, 13, 13);}@keyframes edge-animation-frame{from{stroke-dashoffset:0;}}@keyframes dash{to{stroke-dashoffset:0;}}#chatgpt-mermaid-_r_10c_ .edge-animation-slow{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 50s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_10c_ .edge-animation-fast{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 20s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_10c_ .error-icon{fill:rgb(243, 243, 243);}#chatgpt-mermaid-_r_10c_ .error-text{fill:rgb(13, 13, 13);stroke:rgb(13, 13, 13);}#chatgpt-mermaid-_r_10c_ .edge-thickness-normal{stroke-width:1px;}#chatgpt-mermaid-_r_10c_ .edge-thickness-thick{stroke-width:3.5px;}#chatgpt-mermaid-_r_10c_ .edge-pattern-solid{stroke-dasharray:0;}#chatgpt-mermaid-_r_10c_ .edge-thickness-invisible{stroke-width:0;fill:none;}#chatgpt-mermaid-_r_10c_ .edge-pattern-dashed{stroke-dasharray:3;}#chatgpt-mermaid-_r_10c_ .edge-pattern-dotted{stroke-dasharray:2;}#chatgpt-mermaid-_r_10c_ .marker{fill:rgb(143, 143, 143);stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_10c_ .marker.cross{stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_10c_ svg{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:16px;}#chatgpt-mermaid-_r_10c_ p{margin:0;}#chatgpt-mermaid-_r_10c_ .label{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";color:rgb(13, 13, 13);}#chatgpt-mermaid-_r_10c_ .cluster-label text{fill:rgb(13, 13, 13);}#chatgpt-mermaid-_r_10c_ .cluster-label span{color:rgb(13, 13, 13);}#chatgpt-mermaid-_r_10c_ .cluster-label span p{background-color:transparent;}#chatgpt-mermaid-_r_10c_ .label text,#chatgpt-mermaid-_r_10c_ span{fill:rgb(13, 13, 13);color:rgb(13, 13, 13);}#chatgpt-mermaid-_r_10c_ .node rect,#chatgpt-mermaid-_r_10c_ .node circle,#chatgpt-mermaid-_r_10c_ .node ellipse,#chatgpt-mermaid-_r_10c_ .node polygon,#chatgpt-mermaid-_r_10c_ .node path{fill:rgb(222, 234, 251);stroke:rgb(83, 154, 248);stroke-width:1px;}#chatgpt-mermaid-_r_10c_ .rough-node .label text,#chatgpt-mermaid-_r_10c_ .node .label text,#chatgpt-mermaid-_r_10c_ .image-shape .label,#chatgpt-mermaid-_r_10c_ .icon-shape .label{text-anchor:middle;}#chatgpt-mermaid-_r_10c_ .node .katex path{fill:#000;stroke:#000;stroke-width:1px;}#chatgpt-mermaid-_r_10c_ .rough-node .label,#chatgpt-mermaid-_r_10c_ .node .label,#chatgpt-mermaid-_r_10c_ .image-shape .label,#chatgpt-mermaid-_r_10c_ .icon-shape .label{text-align:center;}#chatgpt-mermaid-_r_10c_ .node.clickable{cursor:pointer;}#chatgpt-mermaid-_r_10c_ .root .anchor path{fill:rgb(143, 143, 143)!important;stroke-width:0;stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_10c_ .arrowheadPath{fill:rgb(143, 143, 143);}#chatgpt-mermaid-_r_10c_ .edgePath .path{stroke:rgb(143, 143, 143);stroke-width:1px;}#chatgpt-mermaid-_r_10c_ .flowchart-link{stroke:rgb(143, 143, 143);fill:none;}#chatgpt-mermaid-_r_10c_ .edgeLabel{background-color:rgb(252, 252, 252);text-align:center;}#chatgpt-mermaid-_r_10c_ .edgeLabel p{background-color:rgb(252, 252, 252);}#chatgpt-mermaid-_r_10c_ .edgeLabel rect{opacity:0.5;background-color:rgb(252, 252, 252);fill:rgb(252, 252, 252);}#chatgpt-mermaid-_r_10c_ .labelBkg{background-color:rgba(252, 252, 252, 0.5);}#chatgpt-mermaid-_r_10c_ .cluster rect{fill:rgb(243, 243, 243);stroke:rgba(0, 0, 0, 0.1);stroke-width:1px;}#chatgpt-mermaid-_r_10c_ .cluster text{fill:rgb(13, 13, 13);}#chatgpt-mermaid-_r_10c_ .cluster span{color:rgb(13, 13, 13);}#chatgpt-mermaid-_r_10c_ div.mermaidTooltip{position:absolute;text-align:center;max-width:200px;padding:2px;font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:12px;background:rgb(243, 243, 243);border:1px solid rgba(0, 0, 0, 0.1);border-radius:2px;pointer-events:none;z-index:100;}#chatgpt-mermaid-_r_10c_ .flowchartTitleText{text-anchor:middle;font-size:18px;fill:rgb(13, 13, 13);}#chatgpt-mermaid-_r_10c_ rect.text{fill:none;stroke-width:0;}#chatgpt-mermaid-_r_10c_ .icon-shape,#chatgpt-mermaid-_r_10c_ .image-shape{background-color:rgb(252, 252, 252);text-align:center;}#chatgpt-mermaid-_r_10c_ .icon-shape p,#chatgpt-mermaid-_r_10c_ .image-shape p{background-color:rgb(252, 252, 252);padding:2px;}#chatgpt-mermaid-_r_10c_ .icon-shape .label rect,#chatgpt-mermaid-_r_10c_ .image-shape .label rect{opacity:0.5;background-color:rgb(252, 252, 252);fill:rgb(252, 252, 252);}#chatgpt-mermaid-_r_10c_ .label-icon{display:inline-block;height:1em;overflow:visible;vertical-align:-0.125em;}#chatgpt-mermaid-_r_10c_ .node .label-icon path{fill:currentColor;stroke:revert;stroke-width:revert;}#chatgpt-mermaid-_r_10c_ .node .neo-node{stroke:rgb(83, 154, 248);}#chatgpt-mermaid-_r_10c_ [data-look="neo"].node rect,#chatgpt-mermaid-_r_10c_ [data-look="neo"].cluster rect,#chatgpt-mermaid-_r_10c_ [data-look="neo"].node polygon{stroke:url(#chatgpt-mermaid-_r_10c_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_10c_ [data-look="neo"].swimlane.cluster rect{filter:none;}#chatgpt-mermaid-_r_10c_ [data-look="neo"].node path{stroke:url(#chatgpt-mermaid-_r_10c_-gradient);stroke-width:1px;}#chatgpt-mermaid-_r_10c_ [data-look="neo"].node .outer-path{filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_10c_ [data-look="neo"].node .neo-line path{stroke:rgb(83, 154, 248);filter:none;}#chatgpt-mermaid-_r_10c_ [data-look="neo"].node circle{stroke:url(#chatgpt-mermaid-_r_10c_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_10c_ [data-look="neo"].node circle .state-start{fill:#000000;}#chatgpt-mermaid-_r_10c_ [data-look="neo"].icon-shape .icon{fill:url(#chatgpt-mermaid-_r_10c_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_10c_ [data-look="neo"].icon-shape .icon-neo path{stroke:url(#chatgpt-mermaid-_r_10c_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_10c_ .node text{font-size:14px;font-weight:600;letter-spacing:normal;fill:rgb(0, 79, 153);}#chatgpt-mermaid-_r_10c_ .edgeLabels text{font-size:13px;font-weight:600;letter-spacing:-0.08px;fill:rgb(0, 79, 153);}#chatgpt-mermaid-_r_10c_ .node tspan[font-weight="normal"],#chatgpt-mermaid-_r_10c_ .edgeLabels tspan[font-weight="normal"]{font-weight:600;}#chatgpt-mermaid-_r_10c_ .edgeLabel .label rect{opacity:1;rx:13px;ry:13px;fill:rgb(245, 250, 255);stroke:rgb(206, 219, 229);stroke-width:1px;}#chatgpt-mermaid-_r_10c_ .node rect,#chatgpt-mermaid-_r_10c_ .node circle,#chatgpt-mermaid-_r_10c_ .node ellipse,#chatgpt-mermaid-_r_10c_ .node polygon,#chatgpt-mermaid-_r_10c_ .node path{fill:rgb(229, 243, 255);stroke:rgba(0, 0, 0, 0.1);stroke-width:1px;}#chatgpt-mermaid-_r_10c_ .node rect{rx:16px;ry:16px;}#chatgpt-mermaid-_r_10c_ .node.mermaid-decision .label-container{fill:rgb(245, 250, 255);stroke:rgb(206, 219, 229);stroke-dasharray:2,2;}#chatgpt-mermaid-_r_10c_ .edgePaths .flowchart-link{stroke:rgb(143, 143, 143);stroke-width:1px;stroke-linecap:round;stroke-linejoin:round;}#chatgpt-mermaid-_r_10c_ .marker{fill:rgb(143, 143, 143);stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_10c_ :root{--mermaid-font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";}论文导入：Zotero / PDF文献解析与证据定位研究主张与实验条件抽取跨论文证据关系推理人工审核与知识确认版本化科研知识图谱研究问题查询与证据报告新论文或用户修订影响分析与增量更新Obsidian / Markdown /JSON 导出实验评测中心

建议把软件划分为六个核心模块。

| 模块           | 核心功能                                     | MVP优先级 |
| -------------- | -------------------------------------------- | --------- |
| 论文工作区     | 项目管理、PDF导入、Zotero同步、元数据管理    | P0        |
| 证据抽取器     | 识别研究主张、方法、实验条件、结果和原文位置 | P0        |
| 论证推理引擎   | 支持、冲突、条件差异、证据不足判断           | P0        |
| 知识图谱工作台 | 图谱展示、人工审核、关系编辑、原文溯源       | P0        |
| 知识演化引擎   | 版本快照、变更记录、增量影响分析             | P1        |
| 实验评测中心   | 数据集、模型配置、基线对比、指标与报告       | P1        |

其中P0是首个可用版本必须实现的功能，P1是完整研究版需要实现的功能。

## 三、交互原型设计

软件采用典型的三栏科研工作台结构：左侧管理论文与研究问题，中间展示知识图谱，右侧展示证据和审核操作。

ResearchGraph Studio

交互原型

知识图谱论文证据知识演化

研究工作区

Social Intelligence

论文 A

论文 B

论文 C

3篇论文 · 2条主张

研究主张网络

选择A选择B

Claim A：共享记忆提高合作率

实验条件：3个智能体，合作任务，记忆共享。

示例数据 · 尚未关联真实论文

待审核

确认关系撤回确认

以上是可交互的产品概念原型，不是已经连接AI引擎的成品。

### 必须重点打磨的交互

证据审查是最重要的操作。用户点击任意主张或关系后，系统应同时显示其原文依据、AI的结构化解释、实验条件对比和审核按钮。

其次是知识演化。用户需要明确看到“新增了什么、修改了什么、为什么改变、谁确认了改变”，而不是只看到一张不断扩大的图。

## 四、核心算法设计

这是整个作品最重要的研究部分。建议采用证据锚定的分阶段推理流水线，而不是直接把所有论文交给一个Agent，让它自由生成知识图谱。

### 4.1 论文解析与证据锚定

每篇论文处理为：

\[ P_i=\{M_i,S_i,C_i,E_i\} \]

其中：

- \(M_i\)：论文元数据
- \(S_i\)：章节与段落
- \(C_i\)：研究主张集合
- \(E_i\)：原文证据集合

建议优先使用PyMuPDF进行文本与坐标提取。复杂学术PDF可选用GROBID，它支持论文结构解析、参考文献提取及PDF坐标信息。

![img](https://www.google.com/s2/favicons?domain=https://grobid.readthedocs.io&sz=32)

GROBID Documentation



证据必须包含论文ID、页码、段落ID、原文、文本偏移量及可用的PDF坐标。

重要约束： LLM只能从解析出的文本中选择证据，不能自己编造证据内容和页码。系统应校验引文是否能够在对应原文中匹配；不匹配则进入人工核验队列。

### 4.2 结构化研究主张抽取

不建议把一篇论文直接抽象为一个观点。应抽取多个具有明确条件的主张。

例如：

```
{
  "claim_id": "C001",
  "subject": "shared memory",
  "predicate": "improves",
  "object": "cooperation success rate",
  "conditions": {
    "agent_count": 3,
    "task_type": "cooperative",
    "memory_type": "shared"
  },
  "evidence_ids": ["E001"],
  "status": "pending_review"
}
```

这里的示例是虚构实验数据，仅用于说明结构。

建议采用LLM结构化输出，并使用Pydantic验证字段完整性和数据类型。缺失的实验条件应显式记录为`unknown`，不能自动补全。

### 4.3 跨论文关系推理

设计五种关系类型：

| 关系         | 判定含义                           |
| ------------ | ---------------------------------- |
| SUPPORTS     | 在可比较条件下，证据支持另一主张   |
| CONTRADICTS  | 在可比较条件下，结论存在实质性冲突 |
| QUALIFIES    | 为某主张增加限制或适用条件         |
| EXTENDS      | 扩展了原方法或研究范围             |
| INSUFFICIENT | 当前证据不足以确定关系             |

建议采用两阶段策略。

第一阶段通过关键词、向量检索与研究主题筛选候选主张对，避免所有主张两两进行昂贵的LLM推理。

第二阶段执行条件比较与证据推理。

\[ R_{ij}=f(C_i,C_j,E_i,E_j,K_{ij}) \]

其中 \(K_{ij}\) 表示两个主张的实验条件可比性。

关键创新是将“语义上看起来矛盾”与“在相同或可比条件下确实矛盾”区分开来。

当实验条件差异很大时，系统应优先输出`QUALIFIES`或`INSUFFICIENT`，而不是强行判定冲突。

### 4.4 知识演化与增量更新

建议采用事件日志 + 图谱物化视图的设计。

每次知识变化保存为事件，例如：

```
{
  "event_id": "EV003",
  "event_type": "RELATION_REVIEWED",
  "target_id": "R001",
  "old_status": "pending",
  "new_status": "accepted",
  "actor": "user",
  "reason": "Experimental conditions verified",
  "timestamp": "2026-10-27T09:00:00+08:00"
}
```

这不是简单记录最后修改时间，而是保存知识的变化过程。

新增论文后，系统根据主题、实体、实验条件和已有图谱邻域找出受影响节点，再重新计算候选关系。

需要特别注意：增量更新并不天然等于正确更新。 必须设计全量重算对照实验，检查增量策略是否漏掉重要关系。

## 五、数据结构设计

第一版不需要引入Neo4j。对于几十篇论文、几百至几千个知识节点，SQLite配合关系表就足够实现原型。

### 核心实体

\#chatgpt-mermaid-_r_10v_{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:16px;fill:rgb(13, 13, 13);}@keyframes edge-animation-frame{from{stroke-dashoffset:0;}}@keyframes dash{to{stroke-dashoffset:0;}}#chatgpt-mermaid-_r_10v_ .edge-animation-slow{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 50s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_10v_ .edge-animation-fast{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 20s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_10v_ .error-icon{fill:rgb(243, 243, 243);}#chatgpt-mermaid-_r_10v_ .error-text{fill:rgb(13, 13, 13);stroke:rgb(13, 13, 13);}#chatgpt-mermaid-_r_10v_ .edge-thickness-normal{stroke-width:1px;}#chatgpt-mermaid-_r_10v_ .edge-thickness-thick{stroke-width:3.5px;}#chatgpt-mermaid-_r_10v_ .edge-pattern-solid{stroke-dasharray:0;}#chatgpt-mermaid-_r_10v_ .edge-thickness-invisible{stroke-width:0;fill:none;}#chatgpt-mermaid-_r_10v_ .edge-pattern-dashed{stroke-dasharray:3;}#chatgpt-mermaid-_r_10v_ .edge-pattern-dotted{stroke-dasharray:2;}#chatgpt-mermaid-_r_10v_ .marker{fill:rgb(143, 143, 143);stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_10v_ .marker.cross{stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_10v_ svg{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:16px;}#chatgpt-mermaid-_r_10v_ p{margin:0;}#chatgpt-mermaid-_r_10v_ .entityBox{fill:rgb(222, 234, 251);stroke:rgb(83, 154, 248);}#chatgpt-mermaid-_r_10v_ .relationshipLabelBox{fill:rgb(243, 243, 243);opacity:0.7;background-color:rgb(243, 243, 243);}#chatgpt-mermaid-_r_10v_ .relationshipLabelBox rect{opacity:0.5;}#chatgpt-mermaid-_r_10v_ .labelBkg{background-color:rgba(243, 243, 243, 0.5);}#chatgpt-mermaid-_r_10v_ .edgeLabel{background-color:rgb(252, 252, 252);}#chatgpt-mermaid-_r_10v_ .edgeLabel .label rect{fill:rgb(252, 252, 252);}#chatgpt-mermaid-_r_10v_ .edgeLabel .label text{fill:rgb(13, 13, 13);}#chatgpt-mermaid-_r_10v_ .edgeLabel .label{fill:rgb(83, 154, 248);font-size:14px;}#chatgpt-mermaid-_r_10v_ .label{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";color:rgb(13, 13, 13);}#chatgpt-mermaid-_r_10v_ .edge-pattern-dashed{stroke-dasharray:8,8;}#chatgpt-mermaid-_r_10v_ .node rect,#chatgpt-mermaid-_r_10v_ .node circle,#chatgpt-mermaid-_r_10v_ .node ellipse,#chatgpt-mermaid-_r_10v_ .node polygon{fill:rgb(222, 234, 251);stroke:rgb(83, 154, 248);stroke-width:1px;}#chatgpt-mermaid-_r_10v_ .relationshipLine{stroke:rgb(143, 143, 143);stroke-width:1px;fill:none;}#chatgpt-mermaid-_r_10v_ .marker{fill:none!important;stroke:rgb(143, 143, 143)!important;stroke-width:1;}#chatgpt-mermaid-_r_10v_ [data-look=neo].labelBkg{background-color:rgba(243, 243, 243, 0.5);}#chatgpt-mermaid-_r_10v_ .node .neo-node{stroke:rgb(83, 154, 248);}#chatgpt-mermaid-_r_10v_ [data-look="neo"].node rect,#chatgpt-mermaid-_r_10v_ [data-look="neo"].cluster rect,#chatgpt-mermaid-_r_10v_ [data-look="neo"].node polygon{stroke:url(#chatgpt-mermaid-_r_10v_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_10v_ [data-look="neo"].swimlane.cluster rect{filter:none;}#chatgpt-mermaid-_r_10v_ [data-look="neo"].node path{stroke:url(#chatgpt-mermaid-_r_10v_-gradient);stroke-width:1px;}#chatgpt-mermaid-_r_10v_ [data-look="neo"].node .outer-path{filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_10v_ [data-look="neo"].node .neo-line path{stroke:rgb(83, 154, 248);filter:none;}#chatgpt-mermaid-_r_10v_ [data-look="neo"].node circle{stroke:url(#chatgpt-mermaid-_r_10v_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_10v_ [data-look="neo"].node circle .state-start{fill:#000000;}#chatgpt-mermaid-_r_10v_ [data-look="neo"].icon-shape .icon{fill:url(#chatgpt-mermaid-_r_10v_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_10v_ [data-look="neo"].icon-shape .icon-neo path{stroke:url(#chatgpt-mermaid-_r_10v_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_10v_ :root{--mermaid-font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";}PROJECTPAPERSECTIONCLAIMEVIDENCERELATIONREVIEWKNOWLEDGE_EVENTEXPERIMENT_RUNcontainshasproposescontainsgrounded_bysourcetargetreceivesrecordsevaluates

建议至少建立以下数据表：

| 数据表           | 核心字段                                          |
| ---------------- | ------------------------------------------------- |
| projects         | id, name, description, created_at                 |
| papers           | id, doi, title, zotero_key, file_hash             |
| sections         | id, paper_id, heading, page_range                 |
| evidences        | id, section_id, quote, page, offsets, bbox        |
| claims           | id, paper_id, statement, conditions_json, status  |
| claim_evidences  | claim_id, evidence_id, role                       |
| relations        | id, source_id, target_id, type, rationale, status |
| reviews          | id, target_type, target_id, decision, reviewer    |
| knowledge_events | id, event_type, payload, timestamp                |
| experiment_runs  | id, config_hash, dataset_id, metrics_json         |

此外，还应保存模型名称、模型版本或快照标识、提示词版本、生成参数、解析器版本及输入哈希。

对于云端模型，无法保证所有提供商都提供完全确定性的复现。因此实验报告应区分“配置可追溯”和“输出可精确复现”。

### 推荐的知识状态

每个知识对象至少具有以下状态：

```
proposed → verified → accepted
```

另外允许转入`rejected`、`needs_revision`或`superseded`。

其中`verified`表示证据定位等机器校验已通过，不代表主张在科学意义上已经被证明。

## 六、桌面软件技术架构

\#chatgpt-mermaid-_r_116_{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:16px;fill:rgb(13, 13, 13);}@keyframes edge-animation-frame{from{stroke-dashoffset:0;}}@keyframes dash{to{stroke-dashoffset:0;}}#chatgpt-mermaid-_r_116_ .edge-animation-slow{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 50s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_116_ .edge-animation-fast{stroke-dasharray:9,5!important;stroke-dashoffset:900;animation:dash 20s linear infinite;stroke-linecap:round;}#chatgpt-mermaid-_r_116_ .error-icon{fill:rgb(243, 243, 243);}#chatgpt-mermaid-_r_116_ .error-text{fill:rgb(13, 13, 13);stroke:rgb(13, 13, 13);}#chatgpt-mermaid-_r_116_ .edge-thickness-normal{stroke-width:1px;}#chatgpt-mermaid-_r_116_ .edge-thickness-thick{stroke-width:3.5px;}#chatgpt-mermaid-_r_116_ .edge-pattern-solid{stroke-dasharray:0;}#chatgpt-mermaid-_r_116_ .edge-thickness-invisible{stroke-width:0;fill:none;}#chatgpt-mermaid-_r_116_ .edge-pattern-dashed{stroke-dasharray:3;}#chatgpt-mermaid-_r_116_ .edge-pattern-dotted{stroke-dasharray:2;}#chatgpt-mermaid-_r_116_ .marker{fill:rgb(143, 143, 143);stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_116_ .marker.cross{stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_116_ svg{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:16px;}#chatgpt-mermaid-_r_116_ p{margin:0;}#chatgpt-mermaid-_r_116_ .label{font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";color:rgb(13, 13, 13);}#chatgpt-mermaid-_r_116_ .cluster-label text{fill:rgb(13, 13, 13);}#chatgpt-mermaid-_r_116_ .cluster-label span{color:rgb(13, 13, 13);}#chatgpt-mermaid-_r_116_ .cluster-label span p{background-color:transparent;}#chatgpt-mermaid-_r_116_ .label text,#chatgpt-mermaid-_r_116_ span{fill:rgb(13, 13, 13);color:rgb(13, 13, 13);}#chatgpt-mermaid-_r_116_ .node rect,#chatgpt-mermaid-_r_116_ .node circle,#chatgpt-mermaid-_r_116_ .node ellipse,#chatgpt-mermaid-_r_116_ .node polygon,#chatgpt-mermaid-_r_116_ .node path{fill:rgb(222, 234, 251);stroke:rgb(83, 154, 248);stroke-width:1px;}#chatgpt-mermaid-_r_116_ .rough-node .label text,#chatgpt-mermaid-_r_116_ .node .label text,#chatgpt-mermaid-_r_116_ .image-shape .label,#chatgpt-mermaid-_r_116_ .icon-shape .label{text-anchor:middle;}#chatgpt-mermaid-_r_116_ .node .katex path{fill:#000;stroke:#000;stroke-width:1px;}#chatgpt-mermaid-_r_116_ .rough-node .label,#chatgpt-mermaid-_r_116_ .node .label,#chatgpt-mermaid-_r_116_ .image-shape .label,#chatgpt-mermaid-_r_116_ .icon-shape .label{text-align:center;}#chatgpt-mermaid-_r_116_ .node.clickable{cursor:pointer;}#chatgpt-mermaid-_r_116_ .root .anchor path{fill:rgb(143, 143, 143)!important;stroke-width:0;stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_116_ .arrowheadPath{fill:rgb(143, 143, 143);}#chatgpt-mermaid-_r_116_ .edgePath .path{stroke:rgb(143, 143, 143);stroke-width:1px;}#chatgpt-mermaid-_r_116_ .flowchart-link{stroke:rgb(143, 143, 143);fill:none;}#chatgpt-mermaid-_r_116_ .edgeLabel{background-color:rgb(252, 252, 252);text-align:center;}#chatgpt-mermaid-_r_116_ .edgeLabel p{background-color:rgb(252, 252, 252);}#chatgpt-mermaid-_r_116_ .edgeLabel rect{opacity:0.5;background-color:rgb(252, 252, 252);fill:rgb(252, 252, 252);}#chatgpt-mermaid-_r_116_ .labelBkg{background-color:rgba(252, 252, 252, 0.5);}#chatgpt-mermaid-_r_116_ .cluster rect{fill:rgb(243, 243, 243);stroke:rgba(0, 0, 0, 0.1);stroke-width:1px;}#chatgpt-mermaid-_r_116_ .cluster text{fill:rgb(13, 13, 13);}#chatgpt-mermaid-_r_116_ .cluster span{color:rgb(13, 13, 13);}#chatgpt-mermaid-_r_116_ div.mermaidTooltip{position:absolute;text-align:center;max-width:200px;padding:2px;font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";font-size:12px;background:rgb(243, 243, 243);border:1px solid rgba(0, 0, 0, 0.1);border-radius:2px;pointer-events:none;z-index:100;}#chatgpt-mermaid-_r_116_ .flowchartTitleText{text-anchor:middle;font-size:18px;fill:rgb(13, 13, 13);}#chatgpt-mermaid-_r_116_ rect.text{fill:none;stroke-width:0;}#chatgpt-mermaid-_r_116_ .icon-shape,#chatgpt-mermaid-_r_116_ .image-shape{background-color:rgb(252, 252, 252);text-align:center;}#chatgpt-mermaid-_r_116_ .icon-shape p,#chatgpt-mermaid-_r_116_ .image-shape p{background-color:rgb(252, 252, 252);padding:2px;}#chatgpt-mermaid-_r_116_ .icon-shape .label rect,#chatgpt-mermaid-_r_116_ .image-shape .label rect{opacity:0.5;background-color:rgb(252, 252, 252);fill:rgb(252, 252, 252);}#chatgpt-mermaid-_r_116_ .label-icon{display:inline-block;height:1em;overflow:visible;vertical-align:-0.125em;}#chatgpt-mermaid-_r_116_ .node .label-icon path{fill:currentColor;stroke:revert;stroke-width:revert;}#chatgpt-mermaid-_r_116_ .node .neo-node{stroke:rgb(83, 154, 248);}#chatgpt-mermaid-_r_116_ [data-look="neo"].node rect,#chatgpt-mermaid-_r_116_ [data-look="neo"].cluster rect,#chatgpt-mermaid-_r_116_ [data-look="neo"].node polygon{stroke:url(#chatgpt-mermaid-_r_116_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_116_ [data-look="neo"].swimlane.cluster rect{filter:none;}#chatgpt-mermaid-_r_116_ [data-look="neo"].node path{stroke:url(#chatgpt-mermaid-_r_116_-gradient);stroke-width:1px;}#chatgpt-mermaid-_r_116_ [data-look="neo"].node .outer-path{filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_116_ [data-look="neo"].node .neo-line path{stroke:rgb(83, 154, 248);filter:none;}#chatgpt-mermaid-_r_116_ [data-look="neo"].node circle{stroke:url(#chatgpt-mermaid-_r_116_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_116_ [data-look="neo"].node circle .state-start{fill:#000000;}#chatgpt-mermaid-_r_116_ [data-look="neo"].icon-shape .icon{fill:url(#chatgpt-mermaid-_r_116_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_116_ [data-look="neo"].icon-shape .icon-neo path{stroke:url(#chatgpt-mermaid-_r_116_-gradient);filter:drop-shadow( 1px 2px 2px rgba(185,185,185,1));}#chatgpt-mermaid-_r_116_ .node text{font-size:14px;font-weight:600;letter-spacing:normal;fill:rgb(0, 79, 153);}#chatgpt-mermaid-_r_116_ .edgeLabels text{font-size:13px;font-weight:600;letter-spacing:-0.08px;fill:rgb(0, 79, 153);}#chatgpt-mermaid-_r_116_ .node tspan[font-weight="normal"],#chatgpt-mermaid-_r_116_ .edgeLabels tspan[font-weight="normal"]{font-weight:600;}#chatgpt-mermaid-_r_116_ .edgeLabel .label rect{opacity:1;rx:13px;ry:13px;fill:rgb(245, 250, 255);stroke:rgb(206, 219, 229);stroke-width:1px;}#chatgpt-mermaid-_r_116_ .node rect,#chatgpt-mermaid-_r_116_ .node circle,#chatgpt-mermaid-_r_116_ .node ellipse,#chatgpt-mermaid-_r_116_ .node polygon,#chatgpt-mermaid-_r_116_ .node path{fill:rgb(229, 243, 255);stroke:rgba(0, 0, 0, 0.1);stroke-width:1px;}#chatgpt-mermaid-_r_116_ .node rect{rx:16px;ry:16px;}#chatgpt-mermaid-_r_116_ .node.mermaid-decision .label-container{fill:rgb(245, 250, 255);stroke:rgb(206, 219, 229);stroke-dasharray:2,2;}#chatgpt-mermaid-_r_116_ .edgePaths .flowchart-link{stroke:rgb(143, 143, 143);stroke-width:1px;stroke-linecap:round;stroke-linejoin:round;}#chatgpt-mermaid-_r_116_ .marker{fill:rgb(143, 143, 143);stroke:rgb(143, 143, 143);}#chatgpt-mermaid-_r_116_ :root{--mermaid-font-family:-apple-system-body,ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,"Apple Color Emoji",Arial,sans-serif,"Segoe UI Emoji","Segoe UI Symbol";}Tauri + React 桌面界面Tauri 命令 / 本地IPCPython Sidecar 算法服务PDF解析与证据定位抽取 / 关系推理 / 增量更新SQLite + FTS5模型提供者云端模型API本地模型服务Zotero本地APIMarkdown / JSON 导出

### 关键工程决策

1. Tauri负责应用生命周期。 启动软件时检查Python Sidecar状态，启动本地算法服务，退出时正确关闭子进程。

Tauri 2官方支持将Python打包生成的可执行程序作为Sidecar分发，因此用户不需要单独安装Python。

![img](https://www.google.com/s2/favicons?domain=https://v2.tauri.app&sz=32)

Tauri



2. 本地数据库不直接暴露给前端。 所有读写操作通过后端服务处理，避免前端绕过审核流程修改知识状态。
3. Zotero采用只读集成。 初版读取文献元数据和附件信息，不自动修改Zotero数据库。其本地API通过`localhost:23119/api/`提供访问，需要用户在Zotero设置中允许本地应用通信。

![img](https://www.google.com/s2/favicons?domain=https://www.zotero.org&sz=32)

Zotero Documentation



4. Obsidian采用文件导出方式。 生成Markdown及YAML frontmatter，由用户选择导出到指定Vault目录。避免第一版就做复杂的双向同步和冲突合并。
5. 安全边界。 Sidecar仅监听本机回环地址，使用会话令牌验证请求，限制跨域访问；API密钥使用操作系统凭据存储。PDF解析与模型返回文本均视为不可信输入，不能作为系统命令执行。

### 安装包交付标准

首个发布版本建议包含：

- `ResearchGraph-Setup-x64.exe` 或 `.msi`
- 完整图形界面与Python运行环境
- SQLite数据库初始化及迁移逻辑
- 示例论文项目和演示数据
- 模型配置向导
- 日志查看与错误诊断
- 项目导入、导出和备份

不把大型本地LLM权重强制放入安装包。软件本身可以离线打开、查看知识库和编辑图谱；AI推理功能则依赖用户选择的云端API或本地模型服务。

## 七、科研创新性验证与实验设计

这是决定作品能否从“工程项目”提升为“研究型作品”的关键。

建议设置三个独立实验，而不是仅用一个综合准确率评价全部功能。

### 实验一：证据约束是否改善关系推理？

研究问题： 加入实验条件比较和证据约束后，能否减少错误的支持、冲突判断？

设置三组：

| 组别          | 方法                                |
| ------------- | ----------------------------------- |
| Baseline A    | LLM直接判断两个主张的关系           |
| Baseline B    | LLM + 原文证据                      |
| ResearchGraph | LLM + 原文证据 + 结构化实验条件比较 |

主要指标包括Macro-F1、各类别Precision/Recall、错误冲突率和证据定位准确率。

特别需要观察`INSUFFICIENT`类别的表现，避免模型为了追求分类结果而过度推断。

### 实验二：增量更新是否降低计算成本？

研究问题： 在保持知识关系完整性的前提下，增量更新能否降低重算开销？

| 组别          | 更新方式                    |
| ------------- | --------------------------- |
| Baseline      | 新论文加入后全量重算        |
| ResearchGraph | 候选节点筛选 + 局部关系重算 |

测量总耗时、模型Token用量、推理成本、受影响关系召回率，以及相对于全量重算的结果差异。

建议分别在10、20、30篇论文的工作区上进行测试，记录每次加入新论文的结果。

### 实验三：人机协同审核是否提升科研任务表现？

研究问题： 证据可追溯的图谱界面，是否比普通AI摘要更有助于用户识别论文之间的差异？

设置两个条件：

- 普通AI论文总结与问答界面。
- ResearchGraph证据图谱与审核界面。

让参与者完成相同的文献比较任务，评价正确率、完成时间、证据核验次数、主观认知负担和使用体验。

需要控制论文难度、参与者经验和任务顺序，避免界面熟悉程度造成偏差。

### 数据集与人工标注

可以使用 SciFact 作为科学主张证据验证的初步基线。该数据集包含约1,400条专家撰写的科学主张，以及证据摘要和关系标注。

![img](https://www.google.com/s2/favicons?domain=https://huggingface.co&sz=32)

allenai/scifact at main



但SciFact主要用于科学主张验证，不能直接等同于ResearchGraph需要的跨论文实验条件关系数据集。

因此还需要自行构建一个小型测试集：建议选择20～30篇AI领域论文，人工标注约100～200组候选主张关系，记录关系类型、证据位置、实验条件和标注分歧。至少安排两名标注者独立标注部分样本，统计一致性并仲裁争议。

### 拟定验收目标

证据定位准确率

# ≥ 90%

目标值，非已有结果

关系分类Macro-F1

# ≥ 0.75

在自建标注集上验证

增量更新耗时

# ≤ 60%

相对于全量重算

知识溯源完整率

# 100%

已接受关系均有证据记录

这些是工程与研究目标。正式实验应报告实际结果、置信区间、失败案例和基线差异，而不能仅以达到预设阈值作为创新性的证明。

## 八、分阶段开发计划

建议把开发拆分为四个阶段，先做可运行的纵向闭环，再逐步扩展。

| 阶段    | 时间      | 核心任务                                 | 阶段交付                  |
| ------- | --------- | ---------------------------------------- | ------------------------- |
| Phase 1 | 第1～2周  | 桌面框架、SQLite、PDF解析、证据定位      | 可安装的论文导入器        |
| Phase 2 | 第3～4周  | 主张抽取、条件结构化、关系推理           | 可用的证据推理原型        |
| Phase 3 | 第5～6周  | 图谱交互、人工审核、知识事件日志         | 完整科研知识工作台        |
| Phase 4 | 第7～10周 | 增量更新、Zotero集成、实验中心、安装测试 | ResearchGraph Studio v1.0 |

这是一份单人借助成熟AI服务开发的估计计划。如果需要同时实现高质量本地模型推理、复杂PDF解析或多人实验，实际周期可能更长。

### 开发过程中的验收关卡

M1：真正能安装

在一台没有Python、Node.js开发环境的Windows电脑上安装软件，成功打开项目、导入PDF并查看原文证据。

M2：真正能推理

导入至少5篇相关论文，抽取研究主张，生成带证据的候选关系，并允许人工纠错。

M3：真正能演化

新增论文后，系统能够定位受影响的知识节点，更新候选关系并保留变更历史。

M4：真正能做实验

固定数据集与模型配置，批量运行对比实验，导出原始预测、错误案例和评价报告。

## 九、项目目录与代码组织

建议保持精简，避免过早拆分微服务。

```
researchgraph/
├── apps/
│   └── desktop/             # Tauri + React
├── engine/
│   ├── api/                 # 本地服务接口
│   ├── ingest/              # PDF与Zotero导入
│   ├── extraction/          # 主张、条件、证据抽取
│   ├── reasoning/           # 关系推理
│   ├── evolution/           # 增量更新与版本
│   ├── storage/             # SQLite与迁移
│   └── providers/           # 云端/本地模型适配
├── experiments/
│   ├── datasets/            # 测试数据及标注
│   ├── baselines/           # 基线方法
│   └── evaluation/          # 评价脚本
├── tests/
├── docs/
└── scripts/                 # 构建与打包
```

这个结构可以支持后续引入Codex或其他编程Agent协同开发，但不需要一开始就构建复杂的多Agent开发框架。

## 十、最终设计决策

我建议将整个作品的价值明确分为两层。

产品层： 帮助研究者建立一个能够长期维护、追溯证据、比较论文观点的个人科研知识网络。

研究层： 探索实验条件约束的跨论文证据推理，以及基于新证据的知识图谱增量演化方法。

两者互相支撑：科研算法为产品提供核心价值，产品则提供真实使用场景、人工反馈和实验数据。

### 现在可以确定的最终MVP

ResearchGraph Studio v0.1：证据驱动的科研知识图谱工作台

首个版本只需要实现一个完整流程：

> 导入5篇论文 → 提取主张与证据 → 比较实验条件 → 生成候选关系 → 人工确认 → 可视化知识图谱 → 保存项目 → 导出研究报告。

完成这个流程之后，再引入增量知识演化、Zotero深度集成和系统化实验评测。

最值得投入精力的不是界面有多复杂，而是每一个AI结论能否被追溯、被质疑、被修订，以及这些机制是否确实提升了跨论文推理的可靠性。

这将是ResearchGraph Studio区别于普通AI论文总结软件的核心。

Q：明确 Zotero，Obsidian 和我们开发的软件在这个过程中担任什么角色，是使用 MCP 方式使用 Zotero 还是采取直接将 pdf 文献导入软件的方式