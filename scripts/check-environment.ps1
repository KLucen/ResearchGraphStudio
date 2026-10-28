[CmdletBinding()]
param(
    [switch]$CheckNetwork,
    [string]$OutputPath,
    [string]$CondaEnvironment = 'researchgraph-studio',
    [string]$ZoteroExecutable = 'D:\Zotero\zotero.exe'
)

$ErrorActionPreference = 'Stop'

function Get-ToolProbe {
    param([string]$Name, [string[]]$VersionArgs = @('--version'))
    $taskCommand = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $taskCommand) {
        return [ordered]@{ available = $false; note = 'Not found on PATH; not proof of absence.' }
    }
    try {
        $taskOutput = (& $taskCommand.Source @VersionArgs 2>&1 | Out-String).Trim()
        $taskExitCode = $LASTEXITCODE
        return [ordered]@{ available = $true; path = $taskCommand.Source; output = $taskOutput; exitCode = $taskExitCode }
    } catch {
        return [ordered]@{ available = $true; path = $taskCommand.Source; error = $_.Exception.Message }
    }
}

$taskProjectRoot = Split-Path -Parent $PSScriptRoot
$taskTimestamp = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([datetime]::UtcNow, 'China Standard Time').ToString('yyyy-MM-ddTHH:mm:ss') + '+08:00'
$taskOS = Get-CimInstance Win32_OperatingSystem
$taskCPU = Get-CimInstance Win32_Processor | Select-Object -First 1 Name, NumberOfCores, NumberOfLogicalProcessors
$taskTools = [ordered]@{}
foreach ($taskToolName in @('git', 'node', 'npm', 'pnpm', 'conda', 'python', 'uv', 'docker', 'podman', 'psql', 'redis-server', 'rustc', 'cargo', 'cmake')) {
    $taskTools[$taskToolName] = Get-ToolProbe -Name $taskToolName
}

$taskCondaEnvironment = [ordered]@{ name = $CondaEnvironment; found = $false }
$taskCondaEnvs = Get-ToolProbe -Name 'conda' -VersionArgs @('env', 'list', '--json')
if ($taskCondaEnvs.Contains('output') -and $taskCondaEnvs.exitCode -eq 0) {
    try {
        $taskEnvList = $taskCondaEnvs.output | ConvertFrom-Json
        $taskMatchingEnvs = @($taskEnvList.envs | Where-Object { (Split-Path -Leaf $_) -eq $CondaEnvironment })
        if ($taskMatchingEnvs.Count -eq 1) {
            $taskCondaEnvironment['found'] = $true
            $taskCondaEnvironment['prefix'] = $taskMatchingEnvs[0]
            $taskCondaPython = Join-Path $taskMatchingEnvs[0] 'python.exe'
            $taskCondaEnvironment['python'] = Get-ToolProbe -Name $taskCondaPython
        } elseif ($taskMatchingEnvs.Count -gt 1) {
            $taskCondaEnvironment['note'] = 'Multiple prefixes have this name; choose an explicit prefix.'
        }
    } catch {
        $taskCondaEnvironment['note'] = 'Could not parse Conda environment inventory.'
    }
} else {
    $taskCondaEnvironment['note'] = 'Conda inventory unavailable.'
}
$taskWsl = Get-ToolProbe -Name 'wsl' -VersionArgs @('--list', '--verbose')
if ($taskWsl.Contains('output')) { $taskWsl['output'] = $taskWsl['output'] -replace "`0", '' }
$taskGPU = Get-ToolProbe -Name 'nvidia-smi' -VersionArgs @('--query-gpu=name,memory.total,driver_version', '--format=csv,noheader')
$taskGitRoot = Get-ToolProbe -Name 'git' -VersionArgs @('-C', $taskProjectRoot, 'rev-parse', '--show-toplevel')
$taskGitBranch = Get-ToolProbe -Name 'git' -VersionArgs @('-C', $taskProjectRoot, 'branch', '--show-current')
$taskGitOrigin = Get-ToolProbe -Name 'git' -VersionArgs @('-C', $taskProjectRoot, 'remote', 'get-url', 'origin')

$taskPortNumbers = @(3000, 5173, 8000, 5432, 6379, 7474, 7687, 11434, 23119)
$taskListeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in $taskPortNumbers } | Select-Object LocalAddress, LocalPort)
$taskServices = @(Get-Service -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'docker|postgres|redis|neo4j|ollama' } | Select-Object Name, @{ Name = 'Status'; Expression = { $_.Status.ToString() } })

$taskAppPaths = @(
    $ZoteroExecutable,
    'C:\Program Files\Docker\Docker\resources\bin\docker.exe',
    'C:\Program Files\Zotero\zotero.exe',
    'C:\Program Files (x86)\Zotero\zotero.exe',
    "$env:LOCALAPPDATA\Programs\Zotero\zotero.exe",
    "$env:LOCALAPPDATA\Programs\Obsidian\Obsidian.exe"
)
$taskApplications = @($taskAppPaths | ForEach-Object {
    $taskAppExists = Test-Path -LiteralPath $_ -PathType Leaf
    [ordered]@{
        path = $_
        exists = $taskAppExists
        productVersion = if ($taskAppExists) { (Get-Item -LiteralPath $_).VersionInfo.ProductVersion } else { $null }
    }
})

$taskNetwork = @()
if ($CheckNetwork) {
    foreach ($taskUrl in @('https://registry.npmjs.org/-/ping', 'https://pypi.org/simple/', 'https://github.com')) {
        try {
            $taskResponse = Invoke-WebRequest -Uri $taskUrl -Method Head -TimeoutSec 10
            $taskNetwork += [ordered]@{ url = $taskUrl; httpStatus = [int]$taskResponse.StatusCode }
        } catch {
            $taskNetwork += [ordered]@{ url = $taskUrl; error = $_.Exception.Message }
        }
    }
}

$taskReport = [ordered]@{
    checkedAt = $taskTimestamp
    timezone = 'Asia/Shanghai'
    projectRoot = $taskProjectRoot
    powershell = $PSVersionTable.PSVersion.ToString()
    os = [ordered]@{ name = $taskOS.Caption; version = $taskOS.Version; ramGiB = [math]::Round($taskOS.TotalVisibleMemorySize / 1MB, 1) }
    cpu = $taskCPU
    drives = @(Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Name -in @('C', 'D') } | Select-Object Name, Root, @{ Name = 'freeGiB'; Expression = { [math]::Round($_.Free / 1GB, 1) } })
    gpu = $taskGPU
    tools = $taskTools
    pythonEnvironmentManager = 'conda'
    condaEnvironment = $taskCondaEnvironment
    wsl = $taskWsl
    gitRoot = $taskGitRoot
    gitBranch = $taskGitBranch
    gitOrigin = $taskGitOrigin
    services = $taskServices
    checkedPorts = $taskPortNumbers
    listeners = $taskListeners
    knownApplicationPaths = $taskApplications
    networkChecks = $taskNetwork
    limits = @(
        'PATH and known paths are not a full installed-software inventory.',
        'No WSL distribution was started or inspected internally.',
        'This check installs no packages and does not benchmark model or application workloads.',
        'Successful HTTP HEAD checks do not verify package installation or model API access.',
        'Secrets and personal research libraries were not inspected.'
    )
}
$taskJson = $taskReport | ConvertTo-Json -Depth 8
if ($OutputPath) {
    $taskResolvedOutput = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath)
    $taskOutputParent = Split-Path -Parent $taskResolvedOutput
    [System.IO.Directory]::CreateDirectory($taskOutputParent) | Out-Null
    [System.IO.File]::WriteAllText($taskResolvedOutput, $taskJson + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
}
Write-Output $taskJson
