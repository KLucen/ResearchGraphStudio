# PDF 公式定位与解析评估

更新：2026-11-17（Asia/Shanghai）。状态：**保守公式候选定位、同 SHA 局部原图预览和可选本地公式 OCR 流程已实现；默认安装包仍不携带 OCR 权重**。导航本轮交付读 [progress](progress.md)，边界见 [ADR0043](adr/0043-reading-outline-and-formula-source-boundary.md)。

## 当前问题发生在哪里

公式通常依赖二维位置表达关系。当前链路读取和显示的是普通文本，并没有从版面恢复数学表达结构。

| 模块 | 当前实现 | 对公式的实际影响 |
| --- | --- | --- |
| `services/engine/researchgraph/ingest.py` / `parse_pdf` | `get_text("blocks", sort=True)` 保存文字、页码、块 bbox | 分数、上下标及积分上下限变为线性文字，未建立结构关系 |
| `services/engine/researchgraph/pdf_structure.py` / `_page_blocks` | 保存行、Span 的字体/字号/bbox，并额外保守标记独立公式候选 | 仍缺少完整字符级二维数学结构；候选只用于定位，不代表上下标已识别 |
| `services/engine/researchgraph/reading_projection.py` / `_clean` | 压平换行和连续空格 | 不能依靠残留空白保持多行公式版式 |
| 同模块 / `_classify` | 正文、标题与图表材料分型，没有 equation | 公式可能成为普通正文；邻近图区域的短式子可能归入疑似图内标签 |
| `services/engine/researchgraph/formula_api.py` | 同 SHA 来源校验、候选列表、局部 PNG `/image`、JSON base64 `/preview`，以及本地识别请求/结果存档 | 识别只接受本地专用适配器；没有适配器时保持明确的 unavailable 状态 |
| `services/engine/researchgraph/formula_ocr.py` | 可选 Pix2Text MFR-1.5 ONNX CPU 适配器，惰性加载、零云端调用 | 仅在显式配置环境变量和本地模型目录后启用，不自动下载权重 |
| `apps/desktop/src/PaperCloseReading.tsx` | 可信 LaTeX 使用 KaTeX；未识别结果保留原文和原图入口 | KaTeX 只能渲染已有正确标记，不能靠换字体修复结构 |

原 PDF 仍保留视觉公式；上述行为没有改动 Zotero/PDF 字节。当前阅读来源中已有页码、源块 bbox、Span 与哈希，现已建设受控候选定位和原图预览，但已有块 bbox 不代表已精确识别每个行内公式。当前 warning 仍说明图表/公式未作语义校验。

## 已实现：原图保真定位

1. 对登记且同 SHA 的 PDF，在本地读取字符/Span 几何、字体、居中布局、公式编号和符号线索，保守标记疑似独立公式区域。派生候选包含 revision-bound `formula_id`、页码、bbox、原文和哈希，不覆盖旧 Chunk、Span、DocumentParse 或历史模型输入。
2. 单个等号、数字或变量不构成可靠公式判断；行内公式继续保留在所属段落中，避免误拆正文。候选状态为 `latex_unavailable`，表示定位结果而不是识别结果。
3. `GET /api/v1/revisions/{revision_id}/formulas/{formula_id}/preview` 按页码和 bbox 用 PyMuPDF 渲染有界局部 PNG，并以 JSON base64 返回；兼容 `/image` 路由保留。来源缺失/字节改变时给明确错误，不把其他文件当作原公式。
4. Tauri bridge 只接受已登记 revision、受限 formula ID 和有限查询参数；渲染尺寸、区域面积和页数有界。显示原图不调用 LLM、不额外产生 API Token。

这一步先解决“看见 PDF 中正确公式”的需求。无需将整篇论文送入新的解析平台，也不要求先恢复 LaTeX。原图预览仍然是核对入口，不代表候选边界或文本层已经正确识别。

## 需要可复制公式时：按需局部 OCR

用户明确点击识别某个区域后，对**原图**做公式识别，生成 LaTeX，再交给数学渲染器显示。不要让普通语言模型从已经损坏的线性文本补猜原式。

- 当前提供 `POST /api/v1/revisions/{revision_id}/formulas/recognize`。请求可以处理全部候选或显式的 `formula_ids`；它只读取已验证的 PDF 原图裁剪，不发送正文、图片或公式到 LLM。成功后识别结果写回当前 `DocumentParse.data.formulas` 的派生字段，并绑定 PDF SHA、revision、页码、bbox、原文哈希、识别器版本和配置哈希；随后重组阅读投影，桌面端自动重新读取论文精读内容。
- `services/engine/researchgraph/formula_ocr.py` 提供 Pix2Text MFR-1.5 ONNX CPU 适配器。主环境没有 `pix2text`、Torch 或权重时，接口返回 `FORMULA_RECOGNIZER_UNAVAILABLE`，不会伪造 LaTeX。启用适配器需要显式设置 `RESEARCHGRAPH_FORMULA_OCR=pix2text`，并将 `RESEARCHGRAPH_FORMULA_MODEL_DIR` 指向已经下载的 MFR 模型目录；应用启动和普通 PDF 解析不会触发网络下载。
- 可评估专用图像转 LaTeX 模型，或 Pix2Text 的公式检测与识别能力；MinerU 可作完整版面解析方案的比较对象。选择前需要检查实际版本、模型权重许可、离线/CPU 能力、Python/ONNX/PyTorch 兼容性、下载量与安装包成本，不能直接将整个依赖树加入现有环境。
- 本地识别通常不消耗云端 API Token，但会增加权重、启动时间和算力要求；如果使用视觉 API，需单独确认 Provider 的图像输入能力、外发授权和实际用量，现有纯文本配置不能自动视为支持图片。
- 识别结果是独立派生草稿：缓存绑定源 SHA、页码/bbox、识别器版本和配置。保留原图与原文，失败/低置信度/不完整表达明确待核对，不覆盖原 Span 或把识别结果直接当成作者权威原式。识别结果保存在结构存档中，重启后仍可读取；PDF SHA、原文哈希或区域变化时旧结果不会暴露为可渲染 LaTeX。
- LaTeX 可渲染只表示语法可以显示，不证明符号识别、括号范围、上下标或数学含义正确。原图对照是必须保留的界面能力。

## 验证要求

样本需分别覆盖行内公式、独立编号公式、分数、根号、矩阵、积分/求和上下限、双栏及扫描页。逐项验证区域覆盖和误报，检查原图是否裁掉上下标；OCR 验收单独比较符号与结构错误，不能只检查渲染成功。测试用自造或可分发样例，不读取私人论文作实验。源文件不可修改，缺失/改变、取消、重启和缓存重放不能引发隐式外发。

## 核对的官方资料

2026-11-16 查阅；这些能力说明不是本工程测试成绩。

- PyMuPDF TextPage / RAWDICT：`https://pymupdf.readthedocs.io/en/latest/textpage.html`。
- PyMuPDF 区域图像渲染：`https://pymupdf.readthedocs.io/en/latest/recipes-images.html`。
- Pix2Text 官方项目：`https://github.com/breezedeus/Pix2Text`。
- MinerU 官方项目：`https://github.com/opendatalab/MinerU`。

本轮没有安装 OCR、下载权重、创建公式模型任务或产生真实模型费用；代码已提供保守候选、受限原图预览、可选本地识别接口和精读自动刷新。

## 2026-11-17 · 公式显示问题的增量处理

当前用户界面中出现空方框、线性化的上下标和不完整的 `W`、`x`、求和符号，原因是 PDF 文本层已经丢失了部分字体映射或二维关系。公式原图仍然存在于 PDF 页面中，但普通文本提取不能把它安全地还原成 LaTeX。直接接入 KaTeX/MathJax 只能渲染已有的正确数学标记，不能修复错误的字符顺序、缺失字形、分子分母或上下标。

当前按三步边界推进：

1. **保真定位（零模型调用，P0 已完成）**：从同 SHA 的登记 PDF 中保存疑似公式区域的页码、bbox、来源块和检测依据；通过受限接口渲染带上下文的局部原图。行内公式继续保留在所属段落中，只有独立且有明确版面信号的公式才进入单独材料。候选检测要求等号之外还有数学符号、数学函数或编号信号，普通正文中的孤立 `a = b` 会被过滤。原图是默认回退，不覆盖既有正文或 Span。公式材料卡片支持查看 PNG 原图；来源缺失或 SHA 变化时拒绝预览。
2. **按需公式识别（P1 已接入）**：用户在论文精读中点击“自动识别公式并刷新”，接口使用已登记原图和可选 Pix2Text MFR 适配器。识别结果绑定源 SHA、页码/bbox、识别器版本和配置缓存，状态区分 `recognized`、`needs_review`、`failed` 和 `latex_unavailable`。识别完成后自动重新读取阅读投影；不可用或失败时保留原图和原始文本。
3. **安全渲染（显示壳已完成）**：只对明确标记为 `recognized` 且通过 JSON/LaTeX 语法检查的结果使用 KaTeX 渲染；界面同时提供原图、原始提取文本和 LaTeX 复制入口。当前生产解析结果仍为 `latex_unavailable`，所以默认回退到原始文本和原图。渲染成功只表示语法可显示，不表示符号、括号范围、上下标或科学含义正确。

公式识别应单独验收行内公式、编号公式、分数、根号、矩阵、积分/求和上下限、双栏和扫描页。每项同时检查区域是否覆盖完整、字符/结构是否正确、原图是否可回看以及源文件变化后的缓存失效；不能把“页面显示出公式”作为科学准确性的证明。当前主环境没有安装 OCR 权重，真实模型调用、Token、OCR 权重下载和新增费用均为 0；P1 的适配器、结果缓存、接口、自动刷新和无适配器回退已完成，实际 LaTeX 质量仍需在用户配置专用权重后用可分发样本单独验收。该增量方案不增加整篇论文的默认 Token，也不恢复 PDF 翻译或完整 Knowledge Engine。
