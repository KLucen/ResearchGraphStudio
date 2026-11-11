param(
    [string]$OutputDirectory,
    [string]$CacheDirectory,
    [string]$Proxy
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $projectRoot 'apps/desktop/src-tauri/translation-runtime' }
if (-not $CacheDirectory) { $CacheDirectory = Join-Path $projectRoot '.local/translation-downloads' }
$outputPath = [IO.Path]::GetFullPath($OutputDirectory)
$cachePath = [IO.Path]::GetFullPath($CacheDirectory)
$manifestPath = Join-Path $PSScriptRoot 'translation-runtime-manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$manifestHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($manifest.format -ne 1) { throw 'Unsupported translation runtime manifest format' }
function Assert-PreparedRuntime([string]$Directory) {
    $installedManifest = Join-Path $Directory 'runtime-manifest.json'
    if (-not (Test-Path -LiteralPath $installedManifest) -or
        (Get-FileHash -LiteralPath $installedManifest -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifestHash) {
        throw 'Existing runtime manifest does not match; refusing to overwrite'
    }
    foreach ($asset in @($manifest.required_files) + @($manifest.sources)) {
        $relativePath = if ($asset.path) { $asset.path } else { 'source/' + $asset.file }
        $filePath = Join-Path $Directory $relativePath
        if (-not (Test-Path -LiteralPath $filePath) -or
            (Get-Item -LiteralPath $filePath).Length -ne $asset.size_bytes -or
            (Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $asset.sha256) {
            throw "Existing runtime verification failed: $relativePath; refusing to overwrite"
        }
    }
    foreach ($pair in @(@('translation-runtime-manifest.json', $manifestPath),
                        @('THIRD_PARTY_NOTICES.md', (Join-Path $PSScriptRoot 'translation-runtime-notices.md')))) {
        $included = Join-Path $Directory ('source/' + $pair[0])
        if (-not (Test-Path -LiteralPath $included) -or
            (Get-FileHash -LiteralPath $included).Hash -ne (Get-FileHash -LiteralPath $pair[1]).Hash) {
            throw 'Existing runtime source notices differ; refusing to overwrite'
        }
    }
}
if (Test-Path -LiteralPath $outputPath) {
    Assert-PreparedRuntime $outputPath
    Write-Host "Verified existing translation runtime: $outputPath"
    return
}
New-Item -ItemType Directory -Force -Path $cachePath | Out-Null

function Get-VerifiedAsset($Asset) {
    if ([IO.Path]::GetFileName($Asset.file) -ne $Asset.file -or $Asset.file -match '[\\/]') {
        throw 'Manifest contains an invalid asset filename'
    }
    if ($Asset.sha256 -notmatch '^[a-f0-9]{64}$' -or -not $Asset.url.StartsWith('https://')) {
        throw 'Manifest contains an invalid digest or non-HTTPS URL'
    }
    $destination = Join-Path $cachePath $Asset.file
    if (-not (Test-Path -LiteralPath $destination)) {
        $partial = "$destination.partial-$([Guid]::NewGuid().ToString('N'))"
        $curlArgs = @('--fail', '--location', '--silent', '--show-error', '--connect-timeout', '20', '--max-time', '1800', '--output', $partial)
        if ($Proxy) { $curlArgs += @('--proxy', $Proxy) }
        Write-Host "Downloading $($Asset.file)"
        & curl.exe @curlArgs $Asset.url
        if ($LASTEXITCODE -ne 0) { throw "Download failed for $($Asset.file); incomplete file retained at $partial" }
        if ((Get-Item -LiteralPath $partial).Length -ne $Asset.size_bytes -or
            (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Asset.sha256) {
            throw "Downloaded asset checksum mismatch: $($Asset.file)"
        }
        Move-Item -LiteralPath $partial -Destination $destination
    }
    if ((Get-Item -LiteralPath $destination).Length -ne $Asset.size_bytes -or
        (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Asset.sha256) {
        throw "Cached asset checksum mismatch: $($Asset.file); cache was not overwritten"
    }
    return $destination
}

$binary = Get-VerifiedAsset $manifest.binary
$sources = @()
foreach ($asset in $manifest.sources) { $sources += Get-VerifiedAsset $asset }
$parentPath = Split-Path -Parent $outputPath
New-Item -ItemType Directory -Force -Path $parentPath | Out-Null
$staging = Join-Path $parentPath ('.translation-staging-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $staging | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead($binary)
try {
    $boundary = [IO.Path]::GetFullPath($staging) + [IO.Path]::DirectorySeparatorChar
    foreach ($entry in $zip.Entries) {
        $resolvedEntry = [IO.Path]::GetFullPath((Join-Path $staging $entry.FullName))
        if (-not $resolvedEntry.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase) -or
            $entry.FullName -match '(^|[\\/])\.\.([\\/]|$)' -or
            $entry.FullName.Contains(':') -or
            (($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) {
            throw 'Unsafe path or symbolic link in translation archive'
        }
    }
} finally { $zip.Dispose() }
[IO.Compression.ZipFile]::ExtractToDirectory($binary, $staging)
$bundle = Join-Path $staging $manifest.binary.archive_root
foreach ($required in @('pdf2zh.exe', 'runtime/python.exe', 'runtime/python313.dll', 'runtime/LICENSE.txt', 'site-packages/pdf2zh_next/__init__.py', '_pystand_static.int')) {
    if (-not (Test-Path -LiteralPath (Join-Path $bundle $required))) { throw "Incomplete runtime: $required" }
}
if (-not (Get-ChildItem -LiteralPath $bundle -Filter 'offline_assets_*.zip')) { throw 'Offline assets missing' }
$sourceDirectory = Join-Path $bundle 'source'
New-Item -ItemType Directory -Path $sourceDirectory | Out-Null
foreach ($source in $sources) { Copy-Item -LiteralPath $source -Destination $sourceDirectory }
Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $sourceDirectory 'translation-runtime-manifest.json')
Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $bundle 'runtime-manifest.json')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'translation-runtime-notices.md') -Destination (Join-Path $sourceDirectory 'THIRD_PARTY_NOTICES.md')
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $sourceDirectory 'prepare-translation-runtime.ps1')
# Preserve all third-party code, dist-info licenses, assets and VC redistributables.
$record = @{ manifest_sha256 = $manifestHash; engine_version = $manifest.engine_version; binary_sha256 = $manifest.binary.sha256 }
$record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $bundle 'bundle-provenance.json') -Encoding UTF8
Move-Item -LiteralPath $bundle -Destination $outputPath
# Only an empty directory is removed, never recursively.
Remove-Item -LiteralPath $staging
Assert-PreparedRuntime $outputPath
Write-Host "Prepared translation runtime: $outputPath"
Write-Host 'No dependency installation, application launch or model request was performed.'
