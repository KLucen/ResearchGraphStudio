# 提交与上传前的敏感信息检查

用户在 2026-11-01 的 P3 指令覆盖旧自动推送授权：本轮未经新的明确授权不得 Push。发现泄露风险时停止 Commit/Push。

`.gitignore` 只是一层保护。提交前还需审阅暂存差异和文件清单，确认私人论文、批注/笔记内容、运行数据、日志和安装产物不在提交内；自造 PDF 仅允许 `tests/fixtures/`。

使用经官方 release SHA-256 校验的 Gitleaks，执行历史与候选源码内容扫描：

```powershell
# 工具路径按本机实际位置传入，日志和报告必须在忽略目录
.local/tools/gitleaks-8.30.1/gitleaks.exe git . --redact=100 --no-banner --report-format json --report-path .local/gitleaks-history.json
conda run -n researchgraph-studio python scripts/check-sensitive.py --gitleaks .local/tools/gitleaks-8.30.1/gitleaks.exe
conda run -n researchgraph-studio python scripts/check-sensitive.py --gitleaks .local/tools/gitleaks-8.30.1/gitleaks.exe --staged
git diff --cached --check
```

内容扫描复制实际候选文件到独立临时目录，不依赖 `.gitignore` 排除已跟踪内容；`--staged` 扫描索引中的实际内容，包括重命名目的路径。内置规则先拒绝运行库、私有目录、日志、密钥文件和安装产物，再运行 Gitleaks。失败只输出状态/文件路径，不回显匹配的凭据。

扫描工具不能判断所有自然语言内容是否属于私人材料，人工审阅仍是提交前必需步骤。报告使用 `--redact=100`，不将报告中的匹配内容复制到聊天或源码。模型调用密钥由 Windows 凭据管理器保存，与 Git 安全扫描相互独立。
