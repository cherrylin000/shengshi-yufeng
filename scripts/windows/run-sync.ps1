# Background sync entry for Windows Task Scheduler.
# Logs to _agent/logs/; uses repo .venv if present.

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $RepoRoot

$LogDir = Join-Path $RepoRoot "_agent\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("sync-{0:yyyyMMdd-HHmmss}.log" -f (Get-Date))

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

Write-Output "=== run-sync.ps1 $(Get-Date -Format o) ===" | Tee-Object -FilePath $LogFile -Append
Write-Output "repo: $RepoRoot" | Tee-Object -FilePath $LogFile -Append
Write-Output "python: $Python" | Tee-Object -FilePath $LogFile -Append

& $Python "scripts\transcripts\sync_local.py" --log-file $LogFile 2>&1 |
    Tee-Object -FilePath $LogFile -Append

$code = $LASTEXITCODE
Write-Output "exit code: $code" | Tee-Object -FilePath $LogFile -Append
exit $code
