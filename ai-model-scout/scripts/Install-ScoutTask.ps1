<#
.SYNOPSIS
  Registers a weekly Windows scheduled task that runs AI Model Scout.

.EXAMPLE
  .\scripts\Install-ScoutTask.ps1                         # Sundays 07:00
  .\scripts\Install-ScoutTask.ps1 -Day Saturday -Time 09:30
  .\scripts\Install-ScoutTask.ps1 -Remove
#>
param(
    [ValidateSet("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday")]
    [string]$Day = "Sunday",
    [string]$Time = "07:00",
    [string]$TaskName = "AI Model Scout",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed scheduled task '$TaskName'."
    return
}

$AppDir = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $AppDir ".venv\Scripts\pythonw.exe"
if (Test-Path $Venv) {
    $Python = $Venv
} else {
    $Python = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
    if (-not $Python) { $Python = (Get-Command python.exe -ErrorAction Stop).Source }
}

# --open pops the report up in your browser when it's done (only if you're logged in).
$Action = New-ScheduledTaskAction -Execute $Python -Argument "-m scout --open" -WorkingDirectory $AppDir
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Day -At $Time
# StartWhenAvailable: if the machine was off at the scheduled time, run at next start-up.
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description "Weekly scan for open-weight LLMs and music AI models" -Force | Out-Null

Write-Host "Scheduled '$TaskName' every $Day at $Time using $Python"
Write-Host "Run it now with:  Start-ScheduledTask -TaskName '$TaskName'"
