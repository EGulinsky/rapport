# Builds the "Rapport Agent" Windows onedir bundle via PyInstaller, then
# zips it for distribution. Must run ON Windows — PyInstaller does not
# cross-compile, so this cannot be run from the Mac dev checkout.
#
# Usage (from a venv with requirements-packaging-windows.txt installed):
#   agent\packaging\build_windows.ps1 [version]
param(
    [string]$Version = "0.1.0"
)
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DistDir = Join-Path $ScriptDir "dist"
$BuildDir = Join-Path $ScriptDir "build"
$AppDir = Join-Path $DistDir "Rapport Agent"
$ZipName = "Rapport-Agent-$Version-windows.zip"

Write-Host "==> Building Rapport Agent.exe with PyInstaller..."
pyinstaller (Join-Path $ScriptDir "agent-windows.spec") --distpath $DistDir --workpath $BuildDir --noconfirm

if (-not (Test-Path $AppDir)) {
    Write-Error "Expected output not found: $AppDir"
    exit 1
}

$ZipPath = Join-Path $DistDir $ZipName
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath
}

Write-Host "==> Zipping to $ZipName..."
Compress-Archive -Path $AppDir -DestinationPath $ZipPath

Write-Host "==> Done: $ZipPath"
Write-Host ""
Write-Host "First launch of 'Rapport Agent.exe' inside the extracted folder"
Write-Host "self-registers a Task Scheduler entry (see task_scheduler.py) so it"
Write-Host "restarts at login without a second manual start."
