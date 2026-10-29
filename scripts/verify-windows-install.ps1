# Works with Windows PowerShell 5.1; no Python, Node or Conda is used by this script.
[CmdletBinding(DefaultParameterSetName = 'Installer')]
param(
    [Parameter(Mandatory, ParameterSetName = 'Installer')][string]$Installer,
    [Parameter(Mandatory, ParameterSetName = 'Engine')][string]$EnginePath,
    [Parameter(ParameterSetName = 'Installer')][string]$ExpectedSha256,
    [Parameter(ParameterSetName = 'Installer')][switch]$VerifyDesktop,
    [string]$OutputRoot = (Join-Path $env:TEMP ('rgs-acceptance-' + [guid]::NewGuid().ToString('N')))
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) { throw 'Use a new output directory for each verification run.' }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$unicodeName = [string][char]0x7814 + [char]0x7A76
$dataPath = Join-Path $OutputRoot ("$unicodeName project data")
$nativeData = [Environment]::GetFolderPath('LocalApplicationData')
$installedPath = Join-Path $OutputRoot ("$unicodeName installed app")
$script:engine = $null
$script:desktop = $null
$script:desktopEngine = $null
$script:token = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
$report = [ordered]@{
    recorded_at = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTimeOffset]::UtcNow, 'China Standard Time').ToString('o')
    os = [Environment]::OSVersion.VersionString
    powershell = $PSVersionTable.PSVersion.ToString()
    result = 'running'
    clean_windows_G0 = 'not_certified_by_this_script'
    developer_commands_on_host = @(@('python', 'node', 'conda', 'cargo') | Where-Object { Get-Command $_ -ErrorAction SilentlyContinue })
    child_path = 'System32 only'
    checks = [ordered]@{}
}

function Assert-Probe([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Start-ProbeProcess([string]$File, [string]$Arguments, [bool]$Pipes = $false) {
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $File
    $info.Arguments = $Arguments
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    $info.RedirectStandardInput = $Pipes
    $info.RedirectStandardOutput = $Pipes
    $info.RedirectStandardError = $Pipes
    $info.EnvironmentVariables.Clear()
    foreach ($key in @('SystemRoot', 'WINDIR', 'TEMP', 'TMP', 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA')) {
        $info.EnvironmentVariables[$key] = [Environment]::GetEnvironmentVariable($key)
    }
    $info.EnvironmentVariables['PATH'] = Join-Path $env:SystemRoot 'System32'
    # .NET Framework has no ProcessStartInfo.StandardInputEncoding. It creates
    # and flushes the stdin writer during Start, using Console.InputEncoding.
    $priorInputEncoding = [Console]::InputEncoding
    try {
        if ($Pipes) { [Console]::InputEncoding = New-Object Text.UTF8Encoding($false) }
        [Diagnostics.Process]::Start($info)
    } finally {
        if ($Pipes) { [Console]::InputEncoding = $priorInputEncoding }
    }
}

function Start-ProbeEngine {
    $script:engine = Start-ProbeProcess $EnginePath ('--data-dir "{0}"' -f $dataPath) $true
    $script:stderr = $script:engine.StandardError.ReadToEndAsync()
    # Windows PowerShell inherits the console encoding. Its StreamWriter can
    # prepend a BOM under CI's UTF-8 console; the private JSON protocol has none.
    $configuration = (@{token = $script:token} | ConvertTo-Json -Compress) + "`n"
    $bytes = [Text.Encoding]::UTF8.GetBytes($configuration)
    $script:engine.StandardInput.BaseStream.Write($bytes, 0, $bytes.Length)
    $script:engine.StandardInput.BaseStream.Flush()
    $line = $script:engine.StandardOutput.ReadLineAsync()
    Assert-Probe ($line.Wait(45000)) 'Engine readiness timed out.'
    if ($null -eq $line.Result -or -not $line.Result.StartsWith('RGS_READY ')) {
        $detail = 'Engine did not report readiness.'
        if ($script:engine.WaitForExit(1000)) {
            $detail += ' Exit code: ' + $script:engine.ExitCode + '. ' + $script:stderr.Result
        }
        throw $detail
    }
    $ready = $line.Result.Substring(10) | ConvertFrom-Json
    Assert-Probe ($ready.protocol -eq 1) 'Engine protocol mismatch.'
    $script:baseUrl = 'http://127.0.0.1:' + $ready.port + '/api/v1'
}

function Stop-ProbeEngine {
    if ($null -eq $script:engine) { return }
    try {
        if (-not $script:engine.HasExited) { $script:engine.StandardInput.Close() }
        Assert-Probe ($script:engine.WaitForExit(10000)) 'Engine remained after stdin EOF.'
        Assert-Probe ($script:engine.ExitCode -eq 0) 'Engine exited unsuccessfully.'
    } finally {
        if (-not $script:engine.HasExited) { $script:engine.Kill(); $script:engine.WaitForExit() }
        $script:stderr.Result | Set-Content -LiteralPath (Join-Path $OutputRoot 'engine-stderr.txt') -Encoding UTF8
        $script:engine.Dispose()
        $script:engine = $null
    }
}

function Invoke-ProbeApi([string]$Path, [string]$Method = 'GET', $Body = $null, [bool]$Authorized = $true) {
    $request = [Net.HttpWebRequest]::Create($script:baseUrl + $Path)
    $request.Proxy = $null
    $request.Timeout = 5000
    $request.ReadWriteTimeout = 5000
    $request.Method = $Method
    $request.ContentType = 'application/json; charset=utf-8'
    $request.Headers['Idempotency-Key'] = 'windows-acceptance-001'
    if ($Authorized) { $request.Headers['Authorization'] = 'Bearer ' + $script:token }
    if ($Method -ne 'GET') {
        $bytes = [Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Compress))
        $request.ContentLength = $bytes.Length
        $stream = $request.GetRequestStream()
        try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
    }
    $response = $request.GetResponse()
    try {
        $reader = New-Object IO.StreamReader($response.GetResponseStream(), [Text.Encoding]::UTF8)
        try { $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
    } finally { $response.Dispose() }
}

function Test-HttpStatus($Failure, [int]$Status) {
    $exception = $Failure.Exception
    while ($null -ne $exception) {
        if ($exception -is [Net.WebException] -and $null -ne $exception.Response) {
            $matches = [int]$exception.Response.StatusCode -eq $Status
            $exception.Response.Dispose()
            return $matches
        }
        $exception = $exception.InnerException
    }
    return $false
}

function Wait-DesktopEngine {
    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    do {
        Assert-Probe (-not $script:desktop.HasExited) 'Desktop exited during startup.'
        $children = @(Get-CimInstance Win32_Process -Filter "Name='researchgraph-engine.exe'" |
            Where-Object { $_.ParentProcessId -eq $script:desktop.Id })
        if ($children.Count -eq 1) {
            $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
                Where-Object { $_.OwningProcess -eq $children[0].ProcessId -and $_.LocalAddress -eq '127.0.0.1' })
            if ($listeners.Count -eq 1) {
                $script:desktopEngine = Get-Process -Id $children[0].ProcessId
                $script:baseUrl = 'http://127.0.0.1:' + $listeners[0].LocalPort + '/api/v1'
                try { Invoke-ProbeApi '/health' 'GET' $null $false | Out-Null }
                catch { if (Test-HttpStatus $_ 401) { return } }
            }
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'Desktop did not start its authenticated loopback engine.'
}

try {
    if ($PSCmdlet.ParameterSetName -eq 'Installer') {
        $existing = @(Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall' -ErrorAction SilentlyContinue |
            Get-ItemProperty | Where-Object { $_.PSObject.Properties['DisplayName'] -and $_.DisplayName -eq 'ResearchGraph Studio' })
        Assert-Probe ($existing.Count -eq 0) 'ResearchGraph is already installed. Use a separate Windows account/VM, or EnginePath mode.'
        Assert-Probe (@(Get-Process -Name researchgraph-studio -ErrorAction SilentlyContinue).Count -eq 0) 'Close ResearchGraph before installer verification.'
        if ($VerifyDesktop) {
            Assert-Probe (-not (Test-Path -LiteralPath (Join-Path $nativeData 'com.researchgraph.studio'))) 'Existing user data found. Use a fresh Windows account/VM for desktop verification.'
        }
        $Installer = (Resolve-Path -LiteralPath $Installer).Path
        $report['installer_sha256'] = (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash
        if ($ExpectedSha256) { Assert-Probe ($report.installer_sha256 -eq $ExpectedSha256) 'Installer SHA-256 mismatch.' }
        $setup = Start-Process -FilePath $Installer -ArgumentList '/S',("/D=$installedPath") -WindowStyle Hidden -PassThru -Wait
        Assert-Probe ($setup.ExitCode -eq 0) 'Silent installation failed.'
        $report.checks['install'] = 'passed'
        $EnginePath = Join-Path $installedPath 'researchgraph-engine.exe'
        Assert-Probe (Test-Path -LiteralPath (Join-Path $installedPath 'researchgraph-studio.exe')) 'Desktop executable missing.'
    }
    $EnginePath = (Resolve-Path -LiteralPath $EnginePath).Path
    Start-ProbeEngine
    $health = Invoke-ProbeApi '/health'
    Assert-Probe ($health.database -eq 'ready' -and $health.fts5 -and $health.schema_version -eq '0001') 'Health handshake failed.'
    $rejected = $false
    try { Invoke-ProbeApi '/health' 'GET' $null $false | Out-Null }
    catch { $rejected = Test-HttpStatus $_ 401 }
    Assert-Probe $rejected 'Unauthenticated request was not rejected.'
    $report.checks['authentication'] = 'passed'
    $project = Invoke-ProbeApi '/projects' 'POST' @{name = "$unicodeName acceptance"; description = 'Synthetic installer test'}
    $replay = Invoke-ProbeApi '/projects' 'POST' @{name = "$unicodeName acceptance"; description = 'Synthetic installer test'}
    Assert-Probe ($project.id -eq $replay.id) 'Idempotency replay failed.'
    $job = Invoke-ProbeApi '/jobs' 'POST' @{kind = 'diagnostics'}
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        $job = Invoke-ProbeApi ('/jobs/' + $job.id)
        if ($job.status -eq 'succeeded') { break }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    Assert-Probe ($job.status -eq 'succeeded') 'Storage diagnostic failed.'
    $report.checks['diagnostics'] = 'passed'
    Stop-ProbeEngine
    Start-ProbeEngine
    $saved = Invoke-ProbeApi '/projects'
    Assert-Probe ($saved.items.Count -eq 1 -and $saved.items[0].id -eq $project.id) 'Project was not persisted exactly once.'
    $report.checks['project_idempotency_restart'] = 'passed'
    Stop-ProbeEngine
    $report.checks['engine_eof_exit'] = 'passed'
    if ($VerifyDesktop) {
        $desktopFile = Join-Path $installedPath 'researchgraph-studio.exe'
        $script:desktop = Start-ProbeProcess $desktopFile ''
        Wait-DesktopEngine
        $report.checks['desktop_sidecar_startup'] = 'passed'
        $second = Start-ProbeProcess $desktopFile ''
        Assert-Probe ($second.WaitForExit(10000) -and $second.ExitCode -eq 0) 'Single instance launch failed.'
        $report.checks['single_instance'] = 'passed'
        Assert-Probe ($script:desktop.CloseMainWindow()) 'No closable desktop window; UI validation required.'
        Assert-Probe ($script:desktop.WaitForExit(15000)) 'Desktop normal shutdown timed out.'
        Assert-Probe ($script:desktopEngine.WaitForExit(15000)) 'Desktop left an engine running.'
        $report.checks['desktop_normal_exit'] = 'passed'
        $script:desktop = Start-ProbeProcess $desktopFile ''
        Wait-DesktopEngine
        $script:desktop.Kill()
        Assert-Probe ($script:desktop.WaitForExit(10000)) 'Could not stop test desktop.'
        Assert-Probe ($script:desktopEngine.WaitForExit(15000)) 'Orphan engine after desktop termination.'
        $report.checks['desktop_crash_cleanup'] = 'passed'
    }
    if ($PSCmdlet.ParameterSetName -eq 'Installer') {
        $uninstaller = Join-Path $installedPath 'uninstall.exe'
        Assert-Probe ($installedPath.StartsWith($OutputRoot + [IO.Path]::DirectorySeparatorChar)) 'Unexpected uninstall boundary.'
        $remove = Start-Process -FilePath $uninstaller -ArgumentList '/S' -WindowStyle Hidden -PassThru -Wait
        Assert-Probe ($remove.ExitCode -eq 0) 'Test uninstall failed.'
        $deadline = [DateTime]::UtcNow.AddSeconds(10)
        while ((Test-Path -LiteralPath $EnginePath) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 200 }
        Assert-Probe (-not (Test-Path -LiteralPath $EnginePath)) 'Program remained after uninstall.'
        if ($VerifyDesktop) {
            Assert-Probe (Test-Path -LiteralPath (Join-Path $nativeData 'com.researchgraph.studio/researchgraph.sqlite3')) 'Uninstall removed user data.'
        }
        $report.checks['uninstall'] = 'passed'
    }
    $report.result = 'passed'
} catch {
    $report.result = 'failed'
    $report['error'] = $_.Exception.Message
    throw
} finally {
    if ($null -ne $script:engine) {
        try { Stop-ProbeEngine } catch { Write-Warning ('Cleanup: ' + $_.Exception.Message) }
    }
    foreach ($process in @($script:desktop, $script:desktopEngine)) {
        if ($null -ne $process -and -not $process.HasExited) { $process.Kill(); $process.WaitForExit(10000) | Out-Null }
    }
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutputRoot 'verification.json') -Encoding UTF8
    Write-Output ('Verification report: ' + (Join-Path $OutputRoot 'verification.json'))
}
