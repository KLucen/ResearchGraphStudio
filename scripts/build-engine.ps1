. "$PSScriptRoot/common.ps1"
$python = Get-ProjectPython
Push-Location $ProjectRoot
try {
    $env:PYTHONUTF8 = '1'
    $migrations = (Join-Path $ProjectRoot 'services/engine/researchgraph/migrations') + ';researchgraph/migrations'
    & $python -m PyInstaller --noconfirm --onedir --name researchgraph-engine --paths services/engine --distpath .local/engine-dist --workpath .local/engine-build --specpath .local --collect-submodules alembic --add-data $migrations scripts/engine_entry.py
    Assert-NativeSuccess 'Python Sidecar 打包'
    $binaries = Join-Path $ProjectRoot 'apps/desktop/src-tauri/binaries'
    New-Item -ItemType Directory -Path $binaries -Force | Out-Null
    $internal = [IO.Path]::GetFullPath((Join-Path $binaries '_internal'))
    $boundary = [IO.Path]::GetFullPath($binaries) + [IO.Path]::DirectorySeparatorChar
    if (-not $internal.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase)) { throw '拒绝越界清理构建资源' }
    if (Test-Path -LiteralPath $internal) { Remove-Item -LiteralPath $internal -Recurse -Force }
    Copy-Item -LiteralPath '.local/engine-dist/researchgraph-engine/_internal' -Destination $internal -Recurse
    Copy-Item -LiteralPath '.local/engine-dist/researchgraph-engine/researchgraph-engine.exe' -Destination (Join-Path $binaries 'researchgraph-engine-x86_64-pc-windows-msvc.exe') -Force
} finally { Pop-Location }
