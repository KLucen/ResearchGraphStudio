# 精读右侧分析与章末阅读状态验证 — 2026-11-20

本轮依据用户截图及三项反馈，修正上一版重复高亮摘录卡、分析被挤到下方和阅读状态放在章首的设计。决策见[ADR0059](adr/0059-reading-analysis-and-chapter-end-progress.md)，原[ADR0058](adr/0058-anchored-reading-annotations.md)与[旧验证](reading-annotations-verification-20261120.md)保留历史，不能作为本轮成绩。

## 行为与改动

`ReadingContent.tsx`移除右栏重复英文摘录卡与blockquote。原文继续显示五色与编号，右侧一份实际分析包含论证作用、核查提醒和阅读问题，只有紧凑的类型/编号按钮用于定位。重复/重叠标记身份、精确occurrence、双向键盘定位及原文DOM文字保持；整段分析没有复制成逐片段专属解读。

`useReadingAnnotationLayout.ts`将分析直接对齐正文起点，不再对齐译文，也不排在所有高亮卡片之后。实际阅读宽度至少560px时维持左右两栏，更窄才按段堆叠；列标题同步变化，正文/元数据/字体/宽度变化后重新测量。布局不写库、不触发模型或逐滚动重排。

`ChapterProgress.tsx`和新增`chapterProgress.css`将状态呈现为带章标题的末尾footer。`ModelDocumentPanel.tsx`在根章节全部小节、段落和材料后显示；`PaperCloseReading.tsx`按真实正文大章分组，章内正文与折叠材料之后再显示状态。原section/parse/chapter身份、progress窄写入、目录已读和继续阅读路径保持。

独立复核发现生产投影会将各页figure/formula追加在数组尾部，不能用该顺序将所有材料放进最后一章。已改为正文确定章界、材料根据章节/父链和唯一来源归章；历史共享section需要页码或实际有界顺序消歧，不能唯一确定时在“未确定章节的图表与其他材料”独立保留，未删除或伪造归属。

## 验证范围

使用合成材料与真实React渲染组件，未读取正式库、私人PDF或凭据。右侧截图和模型章末截图已实际查看，重复摘录卡消失，实际分析从原文旁边开始，末尾控件在小节内容后。旧本地浏览器断言曾假定材料必须位于正文容器外，本轮按章收纳后首轮2/3；修正为本章折叠材料3项后专项3/3，失败记录保留。该夹具变化不冒充模型或正式库验收。

## 实际验证

| 检查 | 实际结果 |
| --- | --- |
| `pnpm --dir apps/desktop check` | TypeScript / ESLint通过 |
| `pnpm --dir apps/desktop test` | **17 files /179 passed，17.67秒** |
| `pnpm --dir apps/desktop test:browser --output=test-results/reading-sidebar-footer-release` | 实际Edge **34 passed，28.7秒** |
| Prettier | 全部src及本轮5个E2E文件通过 |
| 私人路径规则与Gitleaks | **434 files passed** |

React涵盖删除重复引文卡后紧凑按钮的来源关系、同色邻接/完全重叠/第N次出现、只读定位与原文变化清选中；章末专项涵盖父子章节/模型材料顺序和原ID进度保存。材料加固补两大章后追加首章子section的图像、旧共享section的唯一来源/页范围消歧、无法归属的gap页与未知章节材料独立保留。专项37项与全量重叠，不相加。

浏览器验证真正分析位于正文右侧且靠正文开头，确认没有英文摘录卡、无额外模型请求、五色与DOM原文完整、来源信息/字号/宽度变化后重排。模型根章控件位于所有子章和公式表格之后，本地控件位于本章正文及折叠材料之后；目录已读、继续阅读和重新加载仍通过。620px合成阅读区保持双栏，390px堆叠且无横向溢出。

此前第一轮全量178/34通过后，独立review发现尾追加材料归属缺陷，已修正并补生产形态/历史歧义测试；上表179/34在该最后修正后重新运行。后端与Rust逻辑无变更，本轮未重跑历史引擎全量或Host单测，不把旧成绩作本轮成绩。

## 安装交付

新的未签名安装器：[ResearchGraph-Studio-Reading-Sidebar-Footer-0.0.1-x64-setup.exe](../.local/releases/reading-sidebar-footer-20261120/ResearchGraph-Studio-Reading-Sidebar-Footer-0.0.1-x64-setup.exe)，**160,584,055 bytes**，2026-11-20 **13:09:45（Asia/Shanghai）**构建，SHA-256 `9f5833771a7f154eb109c0b31c2fb5e5a3b267481ccdcb4c3bf4c0ca79d2140e`。Tauri/NSIS生产构建成功，Vite保留既有主包大小提示。

Windows PowerShell5.1在新隔离目录静默安装/sidecar烟测通过：schema `lite0015`、匿名PDF本地解析、3段模型材料及章节状态保存/读取、旧本地内容清理/重建、论文删除、引用原PDF保留，模型调用0。安装EXE及**328项**内部资源与打包源逐项匹配；复用前次相同sidecar，EXE SHA-256 `192bb5975e769a5bcccaf917935328e5b325ae055e029e4b419220db1a8f31a6`。**142项**运行源/配置在构建前后保持不变，无数据库迁移或引擎重构。

验证材料位于`.local/verify/reading-sidebar-footer-20261120/`，包括source-freeze、install/verification与最终合成截图：[右侧分析](../.local/verify/reading-sidebar-footer-20261120/reading-analysis-right.png)、[模型章末状态](../.local/verify/reading-sidebar-footer-20261120/model-document-desktop.png)、[620px阅读区](../.local/verify/reading-sidebar-footer-20261120/reading-analysis-620.png)和[390px阅读区](../.local/verify/reading-sidebar-footer-20261120/reading-analysis-390.png)。

安装后直接读取已有合法精读即可，无需重新生成；原失败输出仍遵循原恢复资格，不自动重发。正式库/私人论文/凭据未读取，真实模型0，未Commit/Push或安装到日常目录。原生WebView的实际阅读体验、真实论文质量与干净机仍待用户反馈，不将模拟材料或隔离sidecar烟测称为这些验收。

最终收尾：6份当前文档174个本地链接均存在，`git diff --check`通过、暂存区为空；敏感内容/私人路径/Gitleaks最终434文件通过。交付与验证目录保存`verification.json`/`final-summary.json`，仅含非私人测试与包指纹。
