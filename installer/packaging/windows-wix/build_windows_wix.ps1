# Builds the Windows "Rapport Installer" as a real Windows Installer
# package: a single MSI (Rapport-Setup-<version>.msi) built with the WiX
# Toolset, replacing the previous PyInstaller+NSIS approach entirely -- no
# Python involved anywhere in the Windows install path. Must run ON Windows
# (dotnet build produces a native MSI). Requires the .NET SDK on PATH
# (actions/setup-dotnet on CI, `dotnet --version` locally) -- WiX itself is
# pulled in automatically via NuGet PackageReferences in RapportPackage.wixproj,
# no separate tool install.
#
# Usage: installer\packaging\windows-wix\build_windows_wix.ps1 [version]
param(
    [string]$Version = "0.1.0"
)
$ErrorActionPreference = "Stop"

$WixDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallerDir = Resolve-Path (Join-Path $WixDir "..\..")
$PackageDir = Join-Path $WixDir "RapportPackage"
$DistDir = Join-Path $WixDir "dist"
$SetupName = "Rapport-Setup-$Version.msi"

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

Write-Host "==> Resolving docker-compose.yml for version $Version..."
$ComposeTemplate = Get-Content -Raw -Path (Join-Path $InstallerDir "compose_template.yml")
$ResolvedCompose = $ComposeTemplate -replace "__VERSION__", $Version
$ResolvedComposePath = Join-Path $PackageDir "docker-compose.yml"
Set-Content -NoNewline -Path $ResolvedComposePath -Value $ResolvedCompose

try {
    Write-Host "==> Building RapportPackage.msi..."
    dotnet build (Join-Path $PackageDir "RapportPackage.wixproj") -c Release -p:Version=$Version
    if ($LASTEXITCODE -ne 0) {
        Write-Error "dotnet build failed with exit code $LASTEXITCODE"
        exit 1
    }

    # Found via search rather than a hardcoded path: WiX Toolset SDK
    # projects don't follow the usual TFM-subfolder output layout of
    # ordinary .NET SDK projects, so search bin\ for whatever the actual
    # output path turns out to be instead of assuming one.
    $BuiltMsi = Get-ChildItem -Path (Join-Path $PackageDir "bin") -Filter "RapportPackage.msi" -Recurse |
        Select-Object -First 1
    if (-not $BuiltMsi) {
        Write-Error "RapportPackage.msi not found under RapportPackage\bin\ after dotnet build"
        exit 1
    }

    $SetupPath = Join-Path $DistDir $SetupName
    Copy-Item $BuiltMsi.FullName $SetupPath -Force

    Write-Host "==> Done: $SetupPath"
} finally {
    Remove-Item $ResolvedComposePath -ErrorAction SilentlyContinue
}
