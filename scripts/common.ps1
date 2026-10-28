$ErrorActionPreference = 'Stop'
$script:ProjectRoot = Split-Path -Parent $PSScriptRoot

function Get-ProjectPython {
    if ($env:RGS_PYTHON) { $candidate = $env:RGS_PYTHON }
    elseif ($env:CONDA_DEFAULT_ENV -eq 'researchgraph-studio') { $candidate = Join-Path $env:CONDA_PREFIX 'python.exe' }
    else {
        $candidate = & conda run -n researchgraph-studio python -c 'import sys; print(sys.executable)' |
            Where-Object { $_ -match 'python\.exe\s*$' } | Select-Object -Last 1
        if ($LASTEXITCODE -ne 0) { throw '无法定位 researchgraph-studio Conda 环境' }
        if (-not $candidate) { throw 'Conda 未返回项目 Python 路径' }
        $candidate = $candidate.Trim()
    }
    if (-not (Test-Path -LiteralPath $candidate)) { throw '项目 Python 不存在，请先创建 Conda 环境' }
    $prefixName = & $candidate -c 'import sys,pathlib; print(pathlib.Path(sys.prefix).name)'
    if ($prefixName -ne 'researchgraph-studio') { throw '必须使用 researchgraph-studio，禁止安装或运行到 base' }
    return $candidate
}

function Assert-NativeSuccess([string]$Action) {
    if ($LASTEXITCODE -ne 0) { throw "$Action 失败，退出码 $LASTEXITCODE" }
}
