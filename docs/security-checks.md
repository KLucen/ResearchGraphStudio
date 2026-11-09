# 安全检查

提交或合并前必须检查暂存文件和 Git 历史：

```powershell
conda run -n researchgraph-studio python scripts/check-sensitive.py --gitleaks C:\tools\gitleaks.exe --staged
C:\tools\gitleaks.exe git . --redact=100 --no-banner --exit-code 1
git diff --cached --check
```

工具路径可以放在项目外。扫描会拒绝 `.env`、数据库、日志、安装器、私人 PDF、凭据和运行目录；不要仅依赖 `.gitignore`。本轮使用项目外的 Gitleaks 8.24.3（官方发布压缩包 SHA-256 已核对）完成了暂存内容扫描、工作区目录扫描和 Git 历史扫描：暂存内容 73 个可扫描文件、工作区源码 223 个候选文件、历史 29 个提交，均未发现泄露。用户 Zotero 数据、私人 PDF、批注、模型 Key 和正式数据库不在工程清理范围。

Lite 数据库使用新的本地目录和空 Schema 初始化，不读取旧项目数据库。错误响应只返回稳定错误码和用户可理解的消息，不回显 SQL、路径、论文正文、模型原始响应或凭据。
