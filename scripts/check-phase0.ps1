. "$PSScriptRoot/common.ps1"
$python = Get-ProjectPython
Push-Location $ProjectRoot
try {
    $env:PYTHONPATH = Join-Path $ProjectRoot 'services/engine'
    & $python -m ruff check services/engine tests/engine scripts/*.py
    Assert-NativeSuccess 'Python lint'
    & $python -m ruff format --check services/engine tests/engine scripts/*.py
    Assert-NativeSuccess 'Python format'
    & $python -m mypy
    Assert-NativeSuccess 'Python types'
    & $python -m pytest -q
    Assert-NativeSuccess 'Engine tests'
    & $python -m pip check
    Assert-NativeSuccess 'Python dependency check'
    & $python scripts/export-contracts.py
    Assert-NativeSuccess 'OpenAPI export'
    pnpm contracts
    Assert-NativeSuccess 'TypeScript contracts'
    pnpm format:check
    Assert-NativeSuccess 'Frontend format'
    pnpm check
    Assert-NativeSuccess 'Frontend types/lint'
    pnpm test
    Assert-NativeSuccess 'Frontend tests'
    pnpm build:web
    Assert-NativeSuccess 'Frontend production build'
} finally { Pop-Location }
