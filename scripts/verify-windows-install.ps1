# Windows PowerShell 5.1 Lite acceptance probe. No Python, Node or Conda is needed.
[CmdletBinding(DefaultParameterSetName='Engine')]
param(
  [Parameter(Mandatory,ParameterSetName='Installer')][string]$Installer,
  [Parameter(Mandatory,ParameterSetName='Engine')][string]$EnginePath,
  [string]$ExpectedSha256,
  [string]$PdfFixture = (Join-Path $PSScriptRoot '..\tests\fixtures\pdf\two-pages.pdf'),
  [string]$OutputRoot = (Join-Path $env:TEMP ('rgs-lite-acceptance-' + [guid]::NewGuid().ToString('N')))
)
$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest
$OutputRoot=[IO.Path]::GetFullPath($OutputRoot); New-Item -ItemType Directory -Path $OutputRoot | Out-Null
if($PSCmdlet.ParameterSetName -eq 'Installer'){
  $hash=(Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant()
  if($ExpectedSha256){ if($hash -ne $ExpectedSha256.ToLowerInvariant()){throw 'Installer SHA-256 mismatch.'} }
  $installDir=Join-Path $OutputRoot 'installed'; New-Item -ItemType Directory -Path $installDir | Out-Null
  $proc=Start-Process -FilePath $Installer -ArgumentList '/S',('/D='+$installDir) -Wait -PassThru -WindowStyle Hidden
  if($proc.ExitCode -ne 0){throw 'Silent installation failed.'}
  $EnginePath=Join-Path $installDir 'researchgraph-engine.exe'
}
if(-not (Test-Path -LiteralPath $EnginePath)){throw "Engine not found: $EnginePath"}
$token=[guid]::NewGuid().ToString('N')+[guid]::NewGuid().ToString('N')
$data=Join-Path $OutputRoot 'data'; New-Item -ItemType Directory -Path $data | Out-Null
$info=New-Object Diagnostics.ProcessStartInfo; $info.FileName=$EnginePath; $info.Arguments='--data-dir "'+$data+'"'; $info.UseShellExecute=$false; $info.CreateNoWindow=$true; $info.RedirectStandardInput=$true; $info.RedirectStandardOutput=$true; $info.RedirectStandardError=$true; $info.EnvironmentVariables.Clear(); foreach($k in @('SystemRoot','WINDIR','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA')){$info.EnvironmentVariables[$k]=[Environment]::GetEnvironmentVariable($k)}; $info.EnvironmentVariables['PATH']=Join-Path $env:SystemRoot 'System32'
$p=[Diagnostics.Process]::Start($info); $cfg=([Text.Encoding]::UTF8.GetBytes((@{token=$token}|ConvertTo-Json -Compress)+"`n")); $p.StandardInput.BaseStream.Write($cfg,0,$cfg.Length); $p.StandardInput.BaseStream.Flush(); $line=$p.StandardOutput.ReadLine(); if(-not $line.StartsWith('RGS_READY ')){throw 'Engine readiness failed.'}; $ready=$line.Substring(10)|ConvertFrom-Json; $base='http://127.0.0.1:'+ $ready.port +'/api/v1'
function Invoke-Api([string]$Path,[string]$Method='GET',$Body=$null,[string]$Key='lite-acceptance'){$r=[Net.HttpWebRequest]::Create($base+$Path);$r.Proxy=$null;$r.Method=$Method;$r.Timeout=20000;$r.Headers['Authorization']='Bearer '+$token;$r.Headers['Idempotency-Key']=$Key;$r.ContentType='application/json';if($Method -ne 'GET'){$b=[Text.Encoding]::UTF8.GetBytes(($Body|ConvertTo-Json -Compress));$r.ContentLength=$b.Length;$s=$r.GetRequestStream();$s.Write($b,0,$b.Length);$s.Dispose()};$resp=$r.GetResponse();try{$rd=New-Object IO.StreamReader($resp.GetResponseStream(),[Text.Encoding]::UTF8);try{return $rd.ReadToEnd()|ConvertFrom-Json}finally{$rd.Dispose()}}finally{$resp.Dispose()}}
$health=Invoke-Api '/health'; if($health.schema_version -ne 'lite0008' -or $health.database -ne 'ready' -or -not $health.fts5){throw 'Lite health handshake failed.'}
$translationSettings=Invoke-Api '/settings/translation'; if(-not $translationSettings.enabled -or $translationSettings.launch_mode -ne 'bundled'){throw 'Bundled translation must be available by default.'}; $translationHealth=Invoke-Api '/settings/translation/check' 'POST' @{}; if(-not $translationHealth.available){throw 'Bundled runtime resources are missing.'}
$project=Invoke-Api '/projects' 'POST' @{name='Lite acceptance';description='synthetic'} 'project-1'; $job=Invoke-Api ('/projects/'+$project.id+'/papers/import/pdf') 'POST' @{path=(Resolve-Path -LiteralPath $PdfFixture).Path;mode='reference'} 'import-1'; $deadline=[DateTime]::UtcNow.AddSeconds(30); do{$current=Invoke-Api ('/jobs/'+$job.id); if($current.status -notin @('queued','running')){break}; Start-Sleep -Milliseconds 100}while([DateTime]::UtcNow -lt $deadline); if($current.status -ne 'succeeded'){throw 'PDF import failed.'}; $usage=Invoke-Api ('/projects/'+$project.id+'/lite/usage'); if($usage.calls -ne 0 -or $usage.input_tokens -ne 0 -or $usage.output_tokens -ne 0){throw 'Local import unexpectedly called a model.'}; Invoke-Api ('/projects/'+$project.id+'/papers') | Out-Null
$p.StandardInput.Close(); if(-not $p.WaitForExit(10000)){ $p.Kill(); throw 'Engine did not stop after EOF.' }; $report=@{result='passed';schema_version=$health.schema_version;model_calls=$usage.calls;pdf_job=$job.id}; $report|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $OutputRoot 'verification.json') -Encoding UTF8; $report|ConvertTo-Json
