# Register a weekly background sync (Monday 10:30, after GitHub Actions).
# Run once in PowerShell (as current user):
#   cd <repo>
#   powershell -ExecutionPolicy Bypass -File scripts\windows\install-scheduled-task.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$RunScript = Join-Path $RepoRoot "scripts\windows\run-sync.ps1"
$TaskName = "ShengshiYufeng-XimalayaSync"

if (-not (Test-Path $RunScript)) {
    Write-Error "run-sync.ps1 not found: $RunScript"
}

# Weekly Monday 10:30 local time
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "10:30"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RunScript`"" `
    -WorkingDirectory $RepoRoot

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 6)

$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Force | Out-Null

Write-Host "Registered scheduled task: $TaskName"
Write-Host "  Script: $RunScript"
Write-Host "  Schedule: every Monday 10:30"
Write-Host ""
Write-Host "Before first run:"
Write-Host "  1. python -m venv .venv"
Write-Host "  2. .venv\Scripts\pip install -r requirements-local.txt"
Write-Host "  3. .venv\Scripts\playwright install chromium"
Write-Host "  4. Log in to www.ximalaya.com in Chrome or Edge"
Write-Host ""
Write-Host "Test now:"
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\windows\run-sync.ps1"
