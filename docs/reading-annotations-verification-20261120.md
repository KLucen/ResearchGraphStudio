# 精读标记对应与就近批注验证 — 2026-11-20

本轮针对同段多种高亮无法辨认批注对应范围、右栏从顶端排列的问题。决策见[ADR0058](adr/0058-anchored-reading-annotations.md)。此前精读恢复/模型输出回归是历史成绩，不作为本轮重跑。

## 实现

`ReadingContent.tsx`共用组件现在为每条合法高亮显示原文顺序编号、五类类型名及精确摘录卡；原文与卡片可双向定位，Enter/Space可操作。`readingHighlights.ts`保留每条精确occurrence区间和原数组索引，相邻同色及重叠标记保留各自身份，原文DOM文字和空白不变。

`useReadingAnnotationLayout.ts`在段落内测量高亮首行和批注栏的相对位置，通过文档流间距让卡片贴近对应行；同一行多处或密集标记顺延，保证卡片间及下一段不重叠。整段解读另标“第N段·整段批注”，分清论证作用/核查提醒/阅读问题，并说明其整段范围；既有合同没有每条高亮独立解释，本轮不补造此类说明。

按实际阅读宽度760px切双栏/段内单栏，来源目录挤窄时同样有效；列标题移到模型正文容器并按同一宽度隐藏。观察正文、元数据、卡片尺寸及字体加载，窗口/字号/来源信息展开后重排，卸载清理观察器与RAF，无逐帧滚动监听或坐标持久化。五色/图例由`readingHighlights.css`直接共享，正常本地和模型页以及独立组件均可显示。

## 实际检查

| 检查 | 实际结果 |
| --- | --- |
| `pnpm --dir apps/desktop check` | TypeScript与ESLint通过 |
| `pnpm --dir apps/desktop test` | **17 files /177 passed，15.65秒** |
| `pnpm --dir apps/desktop test:browser --output=test-results/annotation-release-final` | 实际Edge **32 passed，22.7秒** |
| Prettier | 全部src及本轮E2E通过 |
| Tauri/NSIS生产构建 | 成功；保留既有大于500kB主包提示 |
| PowerShell5.1隔离静默安装及sidecar smoke | passed，schema `lite0015`、模型调用0 |
| 私人路径规则与Gitleaks | **431 files passed**（包含最终报告） |
| `git diff --check` | 通过 |

React新增4项覆盖混合类型与原文卡关联、相邻同色/完全重叠和第N次出现、双向键盘及原文变更清选中、非法引文不产生悬空卡与旧稿占位。浏览器新增7项包含真实模型材料页、本地共享组件、五种背景色、原文完整/安全文本、实际行位置、密集不重叠、字号/阅读宽度变化、1000px窗口下正文单栏与列标题、620/390宽度和来源元数据展开后的重定位；模拟夹具没有访问数据库或Provider。

首轮9项浏览器专项7通过/2失败，暴露相邻块margin折叠造成12px定位偏差；将批注栏改为flex后9/9通过。独立复核指出字体/元数据尺寸观察和实际阅读宽度列标题两个边界，均修正并补浏览器测试。独立组件夹具曾依赖父页加载旧五色CSS，已提取共享样式并验证五色各异。最终32项在全部运行源修正后执行；失败截图/记录保留，不覆盖为成功。

已查看稀疏对齐、模型稿及窄屏截图。稀疏标记卡可贴近首行；密集卡顺延会增加段落高度及滚动，不能声称所有卡片始终与原文同高。现有整段解释保持整段范围。

## 安装包

新的未签名安装器：[ResearchGraph-Studio-Reading-Annotations-0.0.1-x64-setup.exe](../.local/releases/reading-annotations-20261120/ResearchGraph-Studio-Reading-Annotations-0.0.1-x64-setup.exe)，**160,575,183 bytes**，2026-11-20 **12:14:14（Asia/Shanghai）**构建；SHA-256 `1d69670fb373705ac86ac4f9993a7f978530713505258927e421fd41b5d25720`。

本轮只修改前端。安装包复用已验证的`lite0015`sidecar，EXE SHA-256 `192bb5975e769a5bcccaf917935328e5b325ae055e029e4b419220db1a8f31a6`，与前次隔离安装版一致；没有把上一轮728项引擎/Host测试称为本轮重跑。新安装实测schema握手、匿名PDF本地解析、3段模型材料保存/读取、重命名、本地解析清理/重建、章节阅读状态保留、论文删除和源PDF保留，模型调用0。安装sidecar与打包源EXE及**328项**内部资源逐项匹配；**141项**源码/配置在构建前后保持。

验收目录`.local/verify/reading-annotations-20261120/`保存源指纹、安装报告及本轮截图；[桌面标记对齐图](../.local/verify/reading-annotations-20261120/reading-annotations-aligned.png)和[390px对应图](../.local/verify/reading-annotations-20261120/reading-annotations-390.png)只含合成材料。最终6份当前文档165个本地链接均存在，暂存区为空。

安装后打开已有论文精读即可使用，已有合法笔记无需重新生成；原失败响应仍须依原有资格显式恢复。无迁移或新增模型请求，正式库/私人PDF/凭据未读取，未Commit/Push或安装到用户日常目录。真实论文阅读体验、用户原生WebView和干净机未作为本轮通过项。
