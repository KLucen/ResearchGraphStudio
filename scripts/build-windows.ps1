. "$PSScriptRoot/common.ps1"
$env:PATH = (Join-Path $env:USERPROFILE '.cargo/bin') + ';' + $env:PATH
Push-Location $ProjectRoot
try {
    & "$PSScriptRoot/build-engine.ps1"
    pnpm --dir apps/desktop tauri build --bundles nsis
    Assert-NativeSuccess 'Windows 安装包构建'
} finally { Pop-Location }
