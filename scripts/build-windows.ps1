param(
    [switch] $Release,
    [string] $PublisherThumbprint
)
. "$PSScriptRoot/common.ps1"
$env:PATH = (Join-Path $env:USERPROFILE '.cargo/bin') + ';' + $env:PATH
Push-Location $ProjectRoot
try {
    if ($Release -and $PublisherThumbprint -notmatch '^[a-fA-F0-9]{40}$') {
        throw '发行验证需要配置发布者签名证书指纹。常规构建仍可生成隔离测试包。'
    }
    & "$PSScriptRoot/build-engine.ps1"
    if ($Release) {
        $releaseReport = Join-Path $ProjectRoot '.local/release-security'
        New-Item -ItemType Directory -Path $releaseReport -Force | Out-Null
        $npmTree = Join-Path $releaseReport 'npm-runtime.json'
        $cargoTree = Join-Path $releaseReport 'cargo-windows-runtime.txt'
        pnpm --filter '@researchgraph/desktop' list --prod --depth Infinity --json | Set-Content -LiteralPath $npmTree -Encoding utf8
        Assert-NativeSuccess '桌面运行时依赖清单'
        cargo tree --manifest-path apps/desktop/src-tauri/Cargo.toml --locked --target x86_64-pc-windows-msvc --edges normal --prefix none | Set-Content -LiteralPath $cargoTree -Encoding utf8
        Assert-NativeSuccess 'Windows Rust 依赖清单'
        & (Get-ProjectPython) scripts/audit-release-dependencies.py --npm-tree $npmTree --cargo-tree $cargoTree --output $releaseReport
        Assert-NativeSuccess '发行依赖公告检查'
        $signingConfig = Join-Path $releaseReport 'tauri-signing.json'
        $signing = @{ bundle = @{ windows = @{ certificateThumbprint = $PublisherThumbprint; digestAlgorithm = 'sha256'; timestampUrl = 'https://timestamp.digicert.com'; tsp = $true } } } | ConvertTo-Json -Depth 4
        [IO.File]::WriteAllText($signingConfig, $signing, [Text.UTF8Encoding]::new($false))
        pnpm --dir apps/desktop tauri build --bundles nsis --config $signingConfig
    } else {
        pnpm --dir apps/desktop tauri build --bundles nsis
    }
    Assert-NativeSuccess 'Windows 安装包构建'
    if ($Release) {
        $version = (Get-Content -LiteralPath 'apps/desktop/src-tauri/tauri.conf.json' -Raw | ConvertFrom-Json).version
        $installer = "apps/desktop/src-tauri/target/release/bundle/nsis/ResearchGraph Studio_${version}_x64-setup.exe"
        $signature = Get-AuthenticodeSignature -LiteralPath $installer
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Thumbprint -ne $PublisherThumbprint -or -not $signature.TimeStamperCertificate) {
            throw '发行包缺少预期发布者的有效时间戳签名。'
        }
        (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash | Set-Content -LiteralPath (Join-Path $releaseReport 'installer.sha256')
    }
} finally { Pop-Location }
