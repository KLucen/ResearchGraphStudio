# 可选公式 OCR 运行时

更新：2026-11-17（Asia/Shanghai）。这是公式识别的可选本地运行说明，不是默认安装步骤。

ResearchGraph Studio Lite 默认不安装 Torch、Pix2Text 或公式模型权重。论文解析、公式候选定位和原图预览仍可在没有 OCR 的情况下运行，真实模型调用和 Token 为 0。需要生成可复制 LaTeX 时，先准备 Pix2Text MFR-1.5 的本地模型目录，再在启动引擎前设置：

```powershell
$env:RESEARCHGRAPH_FORMULA_OCR = "pix2text"
$env:RESEARCHGRAPH_FORMULA_MODEL_DIR = "D:\Models\pix2text\mfr-1.5"
```

模型目录必须已经包含 Pix2Text `LatexOCR` 能读取的 MFR-1.5 ONNX 模型和 processor 文件。应用不会因为打开论文或点击普通“重新整理本地阅读版面”而自动下载权重；目录不存在、依赖缺失或模型加载失败时，界面会保留公式原图和原始文本，并显示 `FORMULA_RECOGNIZER_UNAVAILABLE` 或具体失败状态。

启用后，在论文精读中点击“自动识别公式并刷新”。识别过程只对已经由本地 PDF 版面定位的公式候选生成局部原图，使用本地 CPU OCR，不读取 LLM Provider、不写入用量账本。通过语法检查的结果状态为 `recognized`，低置信度为 `needs_review`，失败为 `failed`；只有 `recognized` 才会进入 KaTeX 渲染。原始 PDF、候选原文、页码、bbox 和哈希始终保留。

识别结果写入当前版本化结构存档，绑定 PDF SHA、revision、原文哈希、识别器版本和配置哈希。替换 PDF、修改候选区域或更换识别器后，旧结果不会自动显示为当前 LaTeX。识别完成后桌面端会重新读取论文精读投影；如果需要重新确认内容，可点击“重新读取本地存档”。

Pix2Text 及其模型依赖和权重应单独检查许可、CPU 性能和分发体积。当前未将这些重量级依赖或模型权重放入 Windows 安装包，也没有把第三方权重上传到 Git。
