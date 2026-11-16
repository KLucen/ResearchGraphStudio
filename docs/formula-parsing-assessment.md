# PDF 公式定位与解析评估

更新：2026-11-16（Asia/Shanghai）。状态：**现有代码诊断与后续方案；公式检测、局部预览和 OCR 尚未实现**。导航本轮交付读 [progress](progress.md)，边界见 [ADR0043](adr/0043-reading-outline-and-formula-source-boundary.md)。

## 当前问题发生在哪里

公式通常依赖二维位置表达关系。当前链路读取和显示的是普通文本，并没有从版面恢复数学表达结构。

| 模块 | 当前实现 | 对公式的实际影响 |
| --- | --- | --- |
| `services/engine/researchgraph/ingest.py` / `parse_pdf` | `get_text("blocks", sort=True)` 保存文字、页码、块 bbox | 分数、上下标及积分上下限变为线性文字，未建立结构关系 |
| `services/engine/researchgraph/pdf_structure.py` / `_page_blocks` | 保存行、Span 的字体/字号/bbox，flags 只取 bold | 缺少完整 flags、origin、行方向及字符级位置，部分上下标定位线索未保存 |
| `services/engine/researchgraph/reading_projection.py` / `_clean` | 压平换行和连续空格 | 不能依靠残留空白保持多行公式版式 |
| 同模块 / `_classify` | 正文、标题与图表材料分型，没有 equation | 公式可能成为普通正文；邻近图区域的短式子可能归入疑似图内标签 |
| `apps/desktop/src/PaperCloseReading.tsx` | 普通文本与精确高亮渲染 | 无可供数学渲染器使用的 LaTeX/MathML，不能靠换字体修复结构 |

原 PDF 仍保留视觉公式；上述行为没有改动 Zotero/PDF 字节。当前阅读来源中已有页码、源块 bbox、Span 与哈希，因此可以建设受控原图定位，但已有块 bbox 不代表已精确识别每个行内公式。当前 warning 已说明图表/公式未作语义校验。

## 推荐先做：原图保真定位

1. 对登记且同 SHA 的 PDF，在独立、可取消的本地任务中读取字符/Span 几何、字体、基线和行方向。按需补充新派生信息，不覆盖旧 Chunk、Span、DocumentParse 或历史模型输入。
2. 结合数学符号/字体、上下标相对位置、居中布局、公式编号与周围正文识别疑似区域。单个等号、数字或变量不构成可靠公式判断；行内公式先保持在所属段落中，避免误拆正文。
3. 在原文位置显示“查看公式原图”，按页码和 bbox 用 PyMuPDF 渲染局部图像，保留足够上下文。来源缺失/字节改变时给明确错误，不把其他文件当作原公式。
4. 客户端只提交已登记论文版本和受验证区域标识，不允许任意路径；渲染尺寸、区域面积、页数与耗时有界。显示原图不调用 LLM、不额外产生 API Token。

这一步能够先解决“看见正确公式”的需求。无需将整篇论文送入新的解析平台，也不要求先恢复 LaTeX。现有 PyMuPDF 已支持区域渲染，但项目还需增加安全 API、宿主白名单及界面入口，不能把已有依赖当作已实现功能。

## 需要可复制公式时：按需局部 OCR

用户明确点击识别某个区域后，对**原图**做公式识别，生成 LaTeX，再交给数学渲染器显示。不要让普通语言模型从已经损坏的线性文本补猜原式。

- 可评估专用图像转 LaTeX 模型，或 Pix2Text 的公式检测与识别能力；MinerU 可作完整版面解析方案的比较对象。选择前需要检查实际版本、模型权重许可、离线/CPU 能力、Python/ONNX/PyTorch 兼容性、下载量与安装包成本，不能直接将整个依赖树加入现有环境。
- 本地识别通常不消耗云端 API Token，但会增加权重、启动时间和算力要求；如果使用视觉 API，需单独确认 Provider 的图像输入能力、外发授权和实际用量，现有纯文本配置不能自动视为支持图片。
- 识别结果是独立派生草稿：缓存绑定源 SHA、页码/bbox、识别器版本和配置。保留原图与原文，失败/低置信度/不完整表达明确待核对，不覆盖原 Span 或把识别结果直接当成作者权威原式。
- LaTeX 可渲染只表示语法可以显示，不证明符号识别、括号范围、上下标或数学含义正确。原图对照是必须保留的界面能力。

## 验证要求

样本需分别覆盖行内公式、独立编号公式、分数、根号、矩阵、积分/求和上下限、双栏及扫描页。逐项验证区域覆盖和误报，检查原图是否裁掉上下标；OCR 验收单独比较符号与结构错误，不能只检查渲染成功。测试用自造或可分发样例，不读取私人论文作实验。源文件不可修改，缺失/改变、取消、重启和缓存重放不能引发隐式外发。

## 核对的官方资料

2026-11-16 查阅；这些能力说明不是本工程测试成绩。

- PyMuPDF TextPage / RAWDICT：`https://pymupdf.readthedocs.io/en/latest/textpage.html`。
- PyMuPDF 区域图像渲染：`https://pymupdf.readthedocs.io/en/latest/recipes-images.html`。
- Pix2Text 官方项目：`https://github.com/breezedeus/Pix2Text`。
- MinerU 官方项目：`https://github.com/opendatalab/MinerU`。

本轮只完成以上诊断；没有安装 OCR、下载权重、创建公式模型任务或产生真实模型费用。
