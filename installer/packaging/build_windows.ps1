# Builds the "Rapport Installer" Windows onedir bundle via PyInstaller, then
# zips it for distribution. Must run ON Windows — PyInstaller does not
# cross-compile. Mirrors agent/packaging/build_windows.ps1, plus a
# version-stamping step for installer/version.py.
#
# Usage (from a venv with requirements-packaging-windows.txt installed):
#   installer\packaging\build_windows.ps1 [version]
param(
    [string]$Version = "0.1.0"
)
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$DistDir = Join-Path $ScriptDir "dist"
$BuildDir = Join-Path $ScriptDir "build"
$AppDir = Join-Path $DistDir "Rapport Installer"
$ZipName = "Rapport-Installer-$Version-windows.zip"

$VersionFile = Join-Path $RepoRoot "installer\version.py"
$OriginalVersionContent = Get-Content -Raw $VersionFile
try {
    Write-Host "==> Stamping version $Version..."
    "INSTALLER_VERSION = `"$Version`"" | Set-Content -NoNewline $VersionFile

    Write-Host "==> Building Rapport Installer.exe with PyInstaller..."
    pyinstaller (Join-Path $ScriptDir "installer-windows.spec") --distpath $DistDir --workpath $BuildDir --noconfirm

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
} finally {
    Set-Content -NoNewline $VersionFile $OriginalVersionContent
}
