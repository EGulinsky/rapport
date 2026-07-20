# Builds the "Rapport Installer" Windows setup wizard: a PyInstaller onedir
# bundle wrapped into a real graphical Setup.exe via NSIS (Nullsoft
# Scriptable Install System, https://nsis.sourceforge.io/ -- free and open
# source under the zlib/libpng license), replacing the bare .zip this used
# to ship as. Must run ON Windows — PyInstaller does not cross-compile.
# Requires `makensis` on PATH (choco install nsis, or
# https://nsis.sourceforge.io/Download).
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
$SetupName = "Rapport-Setup-$Version.exe"

$VersionFile = Join-Path $RepoRoot "installer\version.py"
$OriginalVersionContent = Get-Content -Raw -Path $VersionFile
try {
    Write-Host "==> Stamping version $Version..."
    Set-Content -NoNewline -Path $VersionFile -Value "INSTALLER_VERSION = `"$Version`""

    Write-Host "==> Building Rapport Installer.exe with PyInstaller..."
    pyinstaller (Join-Path $ScriptDir "installer-windows.spec") --distpath $DistDir --workpath $BuildDir --noconfirm

    if (-not (Test-Path $AppDir)) {
        Write-Error "Expected output not found: $AppDir"
        exit 1
    }

    $SetupPath = Join-Path $DistDir $SetupName
    if (Test-Path $SetupPath) {
        Remove-Item $SetupPath
    }

    Write-Host "==> Building $SetupName with NSIS..."
    makensis "-DVERSION=$Version" "-DREPO_ROOT=$RepoRoot" "-DDIST_DIR=$DistDir" (Join-Path $ScriptDir "installer-windows.nsi")

    if (-not (Test-Path $SetupPath)) {
        Write-Error "Expected output not found: $SetupPath"
        exit 1
    }

    Write-Host "==> Done: $SetupPath"
} finally {
    Set-Content -NoNewline -Path $VersionFile -Value $OriginalVersionContent
}
