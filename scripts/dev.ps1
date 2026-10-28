. "$PSScriptRoot/common.ps1"
$env:PATH = (Join-Path $env:USERPROFILE '.cargo/bin') + ';' + $env:PATH
Push-Location $ProjectRoot
try {
    & "$PSScriptRoot/build-engine.ps1"
    pnpm dev
    Assert-NativeSuccess '桌面开发模式'
} finally { Pop-Location }
