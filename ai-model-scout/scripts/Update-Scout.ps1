<#
.SYNOPSIS
  Updates AI Model Scout in place from GitHub. Keeps your config.toml, .env, .venv and reports.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\Update-Scout.ps1
#>
param(
    [string]$Repo = "https://github.com/robepierre-afk/djauto.git",
    [string]$Branch = "claude/weekly-ai-model-discovery-gn1i5b"
)

$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $PSScriptRoot
$Tmp = Join-Path $env:TEMP "ai-scout-update"

if (Test-Path $Tmp) { Remove-Item $Tmp -Recurse -Force }
git clone --quiet --depth 1 -b $Branch $Repo $Tmp
if ($LASTEXITCODE -ne 0) { throw "git clone failed" }

# config.toml, .env, .venv and reports aren't in the repo, so this never overwrites them.
Copy-Item (Join-Path $Tmp "ai-model-scout\*") $AppDir -Recurse -Force
Remove-Item $Tmp -Recurse -Force

& (Join-Path $AppDir ".venv\Scripts\pip.exe") install --quiet -r (Join-Path $AppDir "requirements.txt")
Write-Host "AI Model Scout updated in $AppDir"
