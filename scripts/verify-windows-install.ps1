# Windows PowerShell 5.1 Lite acceptance probe. No Python, Node or Conda is needed.
[CmdletBinding(DefaultParameterSetName='Engine')]
param(
  [Parameter(Mandatory,ParameterSetName='Installer')][string]$Installer,
  [Parameter(Mandatory,ParameterSetName='Engine')][string]$EnginePath,
  [string]$ExpectedSha256,
  [string]$PdfFixture,
  [string]$OutputRoot = (Join-Path $env:TEMP ('rgs-lite-acceptance-' + [guid]::NewGuid().ToString('N')))
)
$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest
if(-not $PdfFixture){$PdfFixture=Join-Path $PSScriptRoot '..\tests\fixtures\pdf\two-pages.pdf'}
$OutputRoot=[IO.Path]::GetFullPath($OutputRoot); New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$p=$null; $proc=$null; $stderrTask=$null; $token=''; $script:probePhase='starting'
$script:phaseHistory=New-Object 'Collections.Generic.List[object]'
$stderrPath=Join-Path $OutputRoot 'engine-stderr.txt'
[IO.File]::WriteAllText($stderrPath,'',[Text.UTF8Encoding]::new($false))
function Save-EngineStderr {
  if($null -ne $stderrTask -and $stderrTask.IsCompleted -and -not $stderrTask.IsFaulted -and -not $stderrTask.IsCanceled){
    $captured=[string]$stderrTask.GetAwaiter().GetResult()
    if($token){$captured=$captured.Replace($token,'[REDACTED]')}
    [IO.File]::WriteAllText($stderrPath,$captured,[Text.UTF8Encoding]::new($false))
  }
}
function Write-Phase([string]$Phase,[string]$Status='running',[hashtable]$Details=@{}){
  $script:probePhase=$Phase
  $entry=@{phase=$Phase;status=$Status;updated_at=[DateTime]::UtcNow.ToString('o');details=$Details}
  $script:phaseHistory.Add($entry)
  $snapshot=@{phase=$Phase;status=$Status;updated_at=$entry.updated_at;details=$Details;history=@($script:phaseHistory.ToArray())}
  $snapshot|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $OutputRoot 'phase.json') -Encoding UTF8
  Write-Host ('[installed-verification] '+$Phase+' '+$Status)
  Save-EngineStderr
}
function Get-InstallerChildren([int]$ParentId){
  # Names and IDs only: do not record command lines, paths, or environment.
  $pending=New-Object 'Collections.Generic.Queue[int]'; $pending.Enqueue($ParentId)
  $seen=New-Object 'Collections.Generic.HashSet[int]'; $children=New-Object 'Collections.Generic.List[object]'
  while($pending.Count -gt 0 -and $seen.Count -lt 64){
    $parent=$pending.Dequeue()
    if(-not $seen.Add($parent)){continue}
    foreach($child in @(Get-CimInstance Win32_Process -Filter ('ParentProcessId='+$parent) -ErrorAction SilentlyContinue)){
      $children.Add(@{name=[string]$child.Name;process_id=[int]$child.ProcessId;parent_process_id=[int]$child.ParentProcessId})
      $pending.Enqueue([int]$child.ProcessId)
    }
  }
  return $children.ToArray()
}
try {
Write-Phase 'starting'
if($PSCmdlet.ParameterSetName -eq 'Installer'){
  Write-Phase 'installer_hash'
  $hash=(Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant()
  if($ExpectedSha256){ if($hash -ne $ExpectedSha256.ToLowerInvariant()){throw 'Installer SHA-256 mismatch.'} }
  $installDir=Join-Path $OutputRoot 'installed'; New-Item -ItemType Directory -Path $installDir | Out-Null
  Write-Phase 'installing' 'running' @{timeout_seconds=300;installer_sha256=$hash}
  $proc=Start-Process -FilePath $Installer -ArgumentList '/S',('/D='+$installDir) -PassThru -WindowStyle Hidden
  if(-not $proc.WaitForExit(300000)){
    $children=@(Get-InstallerChildren $proc.Id)
    Write-Phase 'installing' 'timeout' @{timeout_seconds=300;installer_process_id=$proc.Id;installer_children=$children}
    # Only terminate the installer process started by this probe.
    if(-not $proc.HasExited){$proc.Kill();$null=$proc.WaitForExit(5000)}
    throw 'Silent installation exceeded 300 seconds.'
  }
  Write-Phase 'installed' 'completed' @{installer_exit_code=$proc.ExitCode}
  if($proc.ExitCode -ne 0){throw 'Silent installation failed.'}
  $EnginePath=Join-Path $installDir 'researchgraph-engine.exe'
}
if(-not (Test-Path -LiteralPath $EnginePath)){throw "Engine not found: $EnginePath"}
Write-Phase 'sidecar_starting'
$token=[guid]::NewGuid().ToString('N')+[guid]::NewGuid().ToString('N')
$data=Join-Path $OutputRoot 'data'; New-Item -ItemType Directory -Path $data | Out-Null
$info=New-Object Diagnostics.ProcessStartInfo; $info.FileName=$EnginePath; $info.Arguments='--data-dir "'+$data+'"'; $info.UseShellExecute=$false; $info.CreateNoWindow=$true; $info.RedirectStandardInput=$true; $info.RedirectStandardOutput=$true; $info.RedirectStandardError=$true; $info.EnvironmentVariables.Clear(); foreach($k in @('SystemRoot','WINDIR','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA')){$info.EnvironmentVariables[$k]=[Environment]::GetEnvironmentVariable($k)}; $info.EnvironmentVariables['PATH']=Join-Path $env:SystemRoot 'System32'
# Process uses Console.InputEncoding when it constructs StandardInput. The
# runner's UTF-8 encoding carries a preamble; Python's JSON pipe must be BOM-free.
$originalInputEncoding=[Console]::InputEncoding
try {
  [Console]::InputEncoding=[Text.UTF8Encoding]::new($false)
  $p=[Diagnostics.Process]::Start($info)
} finally {[Console]::InputEncoding=$originalInputEncoding}
$stderrTask=$p.StandardError.ReadToEndAsync()
$readyTask=$p.StandardOutput.ReadLineAsync()
$configuration=@{token=$token}|ConvertTo-Json -Compress
# Keep the BOM-free TextWriter associated with this process for the private pipe.
$p.StandardInput.WriteLine($configuration)
$p.StandardInput.Flush()
Write-Phase 'sidecar_ready_wait' 'running' @{timeout_seconds=45;sidecar_process_id=$p.Id;configuration_characters=$configuration.Length;configuration_flushed=$true;stdin_encoding=$p.StandardInput.Encoding.WebName;stdin_preamble_bytes=$p.StandardInput.Encoding.GetPreamble().Length}
if(-not $readyTask.Wait(45000)){throw 'Engine readiness exceeded 45 seconds.'}
$line=$readyTask.GetAwaiter().GetResult()
if($null -eq $line -or -not $line.StartsWith('RGS_READY ')){throw 'Engine readiness failed.'}
$ready=$line.Substring(10)|ConvertFrom-Json; $base='http://127.0.0.1:'+ $ready.port +'/api/v1'
Write-Phase 'sidecar_ready' 'completed'
function Invoke-Api([string]$Path,[string]$Method='GET',$Body=$null,[string]$Key='lite-acceptance'){$r=[Net.HttpWebRequest]::Create($base+$Path);$r.Proxy=$null;$r.Method=$Method;$r.Timeout=20000;$r.Headers['Authorization']='Bearer '+$token;$r.Headers['Idempotency-Key']=$Key;$r.ContentType='application/json';if($Method -ne 'GET'){$bodyJson=if($null -eq $Body){'null'}else{$Body|ConvertTo-Json -Compress};$b=[Text.Encoding]::UTF8.GetBytes([string]$bodyJson);$r.ContentLength=$b.Length;$s=$r.GetRequestStream();$s.Write($b,0,$b.Length);$s.Dispose()};$resp=$r.GetResponse();try{$rd=New-Object IO.StreamReader($resp.GetResponseStream(),[Text.Encoding]::UTF8);try{return $rd.ReadToEnd()|ConvertFrom-Json}finally{$rd.Dispose()}}finally{$resp.Dispose()}}
function Assert-ApiMissing([string]$Path){$missing=$false;try{$null=Invoke-Api $Path}catch [Net.WebException]{if($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 404){$missing=$true}else{throw}};if(-not $missing){throw "Expected 404 for $Path"}}
Write-Phase 'health_and_retired_routes'
$health=Invoke-Api '/health'; if($health.schema_version -ne 'lite0018' -or $health.database -ne 'ready' -or -not $health.fts5){throw 'Lite health handshake failed.'}
$retiredRequest=[Net.HttpWebRequest]::Create($base+'/settings/translation'); $retiredRequest.Proxy=$null; $retiredRequest.Timeout=20000; $retiredRequest.Headers['Authorization']='Bearer '+$token; try { $retiredResponse=$retiredRequest.GetResponse(); $retiredResponse.Dispose(); throw 'Retired translation API is still available.' } catch [Net.WebException] { if(-not $_.Exception.Response -or [int]$_.Exception.Response.StatusCode -ne 404){throw} }
if(Test-Path -LiteralPath (Join-Path (Split-Path -Parent $EnginePath) 'translation-runtime')){throw 'Retired translation runtime was unexpectedly packaged.'}
Write-Phase 'local_pdf_import'
$resolvedPdf=(Resolve-Path -LiteralPath $PdfFixture).Path; $project=Invoke-Api '/projects' 'POST' @{name='Lite acceptance';description='synthetic'} 'project-1'; $job=Invoke-Api ('/projects/'+$project.id+'/papers/import/pdf') 'POST' @{path=$resolvedPdf;mode='reference'} 'import-1'; $deadline=[DateTime]::UtcNow.AddSeconds(30); do{$current=Invoke-Api ('/jobs/'+$job.id); if($current.status -notin @('queued','running')){break}; Start-Sleep -Milliseconds 100}while([DateTime]::UtcNow -lt $deadline); if($current.status -ne 'succeeded'){throw 'PDF import failed.'}; Invoke-Api ('/projects/'+$project.id+'/papers') | Out-Null
$paperId=[string]$current.result.paper_id; if(-not $paperId){throw 'PDF import did not publish a paper ID.'}; $paperDetail=Invoke-Api ('/papers/'+$paperId); if($paperDetail.paper.id -ne $paperId -or $paperDetail.revisions.Count -lt 1){throw 'Imported paper readback failed.'}; $revisionId=[string]$paperDetail.revisions[0].id; Invoke-Api ('/papers/'+$paperId) 'PATCH' @{title='Lite acceptance renamed'} 'paper-title-1' | Out-Null; if((Invoke-Api ('/papers/'+$paperId)).paper.title -ne 'Lite acceptance renamed'){throw 'Paper title update failed.'}
Write-Phase 'model_document_materialization'
$session=Invoke-Api ('/projects/'+$project.id+'/import-sessions') 'POST' @{selection_id='synthetic-model-selection';source_kind='pdf';source_snapshot=@{paper_id=$paperId;file_name='synthetic-model-document.pdf'};plan=@{overview=$false;reading=$false;translation_mode='none';modality='pdf';allow_network=$false}} 'model-session-1'; $sessionId=$session.id
$parse=Invoke-Api ('/import-sessions/'+$sessionId+'/document-parse/result') 'POST' @{parse_version='installed-synthetic-v1';modality='pdf';segments=@(@{chapter_ref='intro';chapter_title='Introduction';chapter_order=0;chapter_level=1;ordinal=0;kind='paragraph';text='Anonymous synthetic paragraph.'},@{chapter_ref='intro';chapter_title='Introduction';chapter_order=0;chapter_level=1;ordinal=1;kind='formula';text='x = y';latex='x = y';status='needs_review'},@{chapter_ref='results';chapter_title='Results';chapter_order=1;chapter_level=1;ordinal=0;kind='table';raw_table_text='A | B`n1 | 2';status='degraded'})} 'model-parse-1'; if($parse.segments.Count -ne 3 -or $parse.segments[1].kind -ne 'formula' -or $parse.segments[2].kind -ne 'table'){throw 'Model document parse materialization failed.'}
Write-Phase 'chapter_reading_progress'
$chapterStatesPath='/import-sessions/'+$sessionId+'/chapter-reading-states'
$initialChapterStates=Invoke-Api $chapterStatesPath
if($initialChapterStates.parse_id -ne $parse.id){throw 'Chapter reading states did not use the current model parse.'}
$chapterState=Invoke-Api $chapterStatesPath 'PUT' @{parse_id=$parse.id;chapter_ref='intro';progress='COMPLETED'} 'chapter-reading-state-1'
if($chapterState.parse_id -ne $parse.id -or $chapterState.chapter_ref -ne 'intro' -or $chapterState.progress -ne 'COMPLETED'){throw 'Chapter reading state update failed.'}
$restoredChapterStates=Invoke-Api $chapterStatesPath
if(@($restoredChapterStates.items | Where-Object {$_.parse_id -eq $parse.id -and $_.chapter_ref -eq 'intro' -and $_.progress -eq 'COMPLETED'}).Count -ne 1){throw 'Chapter reading state readback failed.'}
Write-Phase 'legacy_cleanup'
$stored=Invoke-Api ('/import-sessions/'+$sessionId+'/document-parse'); $outputs=Invoke-Api ('/import-sessions/'+$sessionId+'/document-outputs'); $outputCount=@($outputs).Count; if($stored.status -ne 'succeeded' -or $stored.segments.Count -ne 3 -or $outputCount -ne 0){throw 'Model document readback failed.'}; $cleared=Invoke-Api ('/papers/'+$paperId+'/legacy-content') 'DELETE' $null 'paper-clean-1'; if($cleared.removed.chunks -lt 1){throw 'Legacy content cleanup did not remove the imported PDF chunks.'}; $storedAfterClear=Invoke-Api ('/import-sessions/'+$sessionId+'/document-parse'); if($storedAfterClear.segments.Count -ne 3){throw 'Legacy cleanup removed model document content.'}
$chapterStatesAfterClear=Invoke-Api $chapterStatesPath
if(@($chapterStatesAfterClear.items | Where-Object {$_.parse_id -eq $parse.id -and $_.chapter_ref -eq 'intro' -and $_.progress -eq 'COMPLETED'}).Count -ne 1){throw 'Legacy cleanup removed model chapter reading state.'}
Write-Phase 'local_reparse'
$localReparse=Invoke-Api ('/papers/'+$paperId+'/parse') 'POST' @{mode='local'} 'local-reparse-1'
$deadline=[DateTime]::UtcNow.AddSeconds(30)
do { $localTask=Invoke-Api ('/jobs/'+$localReparse.id); if($localTask.status -notin @('queued','running')){break}; Start-Sleep -Milliseconds 100 } while([DateTime]::UtcNow -lt $deadline)
if($localTask.status -ne 'succeeded' -or $localTask.result.paper_id -ne $paperId){throw 'Explicit local reparse failed or created another paper.'}
$localDetail=Invoke-Api ('/papers/'+$paperId)
$localChunks=Invoke-Api ('/revisions/'+$localDetail.revisions[0].id+'/chunks?limit=50')
if($localChunks.items.Count -lt 1){throw 'Explicit local reparse did not restore local chunks.'}
$clearedAgain=Invoke-Api ('/papers/'+$paperId+'/legacy-content') 'DELETE' $null 'paper-clean-2'
if($clearedAgain.removed.chunks -lt 1){throw 'Repeated local cleanup did not remove rebuilt chunks.'}
Write-Phase 'deletion_and_usage'
$readingBlocked=$false; try{$null=Invoke-Api ('/papers/'+$paperId+'/reading-document?document_version_id='+$revisionId)}catch [Net.WebException]{$response=$_.Exception.Response;if(-not $response -or [int]$response.StatusCode -lt 400){throw};$readingBlocked=$true}; if(-not $readingBlocked){throw 'Legacy reading archive was silently rebuilt after cleanup.'}; if(-not (Test-Path -LiteralPath $resolvedPdf)){throw 'Referenced source PDF was unexpectedly removed.'}; $usage=Invoke-Api ('/projects/'+$project.id+'/lite/usage'); if($usage.calls -ne 0 -or $usage.input_tokens -ne 0 -or $usage.output_tokens -ne 0){throw 'Local acceptance unexpectedly called a model.'}; Invoke-Api ('/papers/'+$paperId) 'DELETE' $null 'paper-delete-1' | Out-Null; Assert-ApiMissing ('/papers/'+$paperId); Assert-ApiMissing $chapterStatesPath; if(-not (Test-Path -LiteralPath $resolvedPdf)){throw 'Deleting the paper removed its referenced source PDF.'}
Write-Phase 'sidecar_stopping'
$p.StandardInput.Close(); if(-not $p.WaitForExit(10000)){ $p.Kill(); throw 'Engine did not stop after EOF.' }; $report=@{result='passed';schema_version=$health.schema_version;model_calls=$usage.calls;pdf_job=$job.id;paper_title_updated=$true;legacy_rows_removed=$cleared.removed.chunks;legacy_cache_rows_removed=$cleared.removed.cache_entries;model_document_parse_id=$parse.id;model_document_segments_after_cleanup=$storedAfterClear.segments.Count;chapter_reading_progress=$chapterState.progress;chapter_reading_state_preserved_after_cleanup=$true;chapter_reading_state_removed_after_paper_delete=$true;reading_archive_rebuilt_after_cleanup=$false;paper_delete_verified=$true;referenced_source_preserved=$true;postprocess_outputs=$outputCount;translation_available=$false;translation_runtime_bundled=$false}; $report|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $OutputRoot 'verification.json') -Encoding UTF8; $report|ConvertTo-Json
Write-Phase 'complete' 'passed'
} catch {
  $failedPhase=$script:probePhase
  Write-Phase $failedPhase 'failed' @{exception_type=$_.Exception.GetType().FullName}
  throw
} finally {
  if($null -ne $p){
    try {
      if(-not $p.HasExited){$p.StandardInput.Close();if(-not $p.WaitForExit(10000)){$p.Kill();$null=$p.WaitForExit(5000)}}
      if($null -ne $stderrTask){$null=$stderrTask.Wait(5000)}
      Save-EngineStderr
    } finally {$p.Dispose()}
  }
  if($null -ne $proc){$proc.Dispose()}
}
