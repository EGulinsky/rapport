# Builds the Windows "Rapport Installer" as a real Windows Installer
# package: a WiX Burn bootstrapper (Rapport-Setup-<version>.exe) wrapping
# an MSI (RapportPackage.msi), replacing the previous PyInstaller+NSIS
# approach entirely -- no Python involved anywhere in the Windows install
# path. Must run ON Windows (dotnet build produces a native MSI/Burn
# engine). Requires the .NET SDK on PATH (actions/setup-dotnet on CI,
# `dotnet --version` locally) -- WiX itself is pulled in automatically via
# NuGet PackageReferences in the .wixproj files, no separate tool install.
#
# Usage: installer\packaging\windows-wix\build_windows_wix.ps1 [version]
param(
    [string]$Version = "0.1.0"
)
$ErrorActionPreference = "Stop"

$WixDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $WixDir "..\..\..")
$InstallerDir = Join-Path $RepoRoot "installer"
$DistDir = Join-Path $WixDir "dist"
$SetupName = "Rapport-Setup-$Version.exe"

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

Write-Host "==> Resolving docker-compose.yml for version $Version..."
$ComposeTemplate = Get-Content -Raw -Path (Join-Path $InstallerDir "compose_template.yml")
$ResolvedCompose = $ComposeTemplate -replace "__VERSION__", $Version
$ResolvedComposePath = Join-Path $WixDir "RapportPackage\docker-compose.yml"
Set-Content -NoNewline -Path $ResolvedComposePath -Value $ResolvedCompose

# WixStandardBootstrapperApplication's license page needs RTF, not plain
# text -- generated fresh from the repo's actual LICENSE on every build so
# it can never drift out of sync, rather than a hand-copied duplicate.
function ConvertTo-Rtf {
    param([string]$Text)
    $escaped = $Text -replace '\\', '\\\\'
    $escaped = $escaped -replace '\{', '\{'
    $escaped = $escaped -replace '\}', '\}'
    $escaped = $escaped -replace "`r`n", "`n"
    $lines = ($escaped -split "`n") | ForEach-Object { "$_\par" }
    return "{\rtf1\ansi\deff0{\fonttbl{\f0 Consolas;}}\f0\fs18 " + ($lines -join "`n") + "}"
}

Write-Host "==> Generating License.rtf from repo LICENSE..."
$LicenseText = Get-Content -Raw -Path (Join-Path $RepoRoot "LICENSE")
$LicenseRtfPath = Join-Path $WixDir "RapportBundle\License.rtf"
Set-Content -NoNewline -Path $LicenseRtfPath -Value (ConvertTo-Rtf $LicenseText)

try {
    Write-Host "==> Building RapportBundle (dotnet build, pulls in RapportPackage via project reference)..."
    dotnet build (Join-Path $WixDir "RapportBundle\RapportBundle.wixproj") -c Release -p:Version=$Version
    if ($LASTEXITCODE -ne 0) {
        Write-Error "dotnet build failed with exit code $LASTEXITCODE"
        exit 1
    }

    # Found via search rather than a hardcoded path: WiX Toolset SDK
    # projects don't follow the usual TFM-subfolder output layout of
    # ordinary .NET SDK projects, so search bin\ for whatever the actual
    # output path turns out to be instead of assuming one.
    $BuiltExe = Get-ChildItem -Path (Join-Path $WixDir "RapportBundle\bin") -Filter "RapportBundle.exe" -Recurse |
        Select-Object -First 1
    if (-not $BuiltExe) {
        Write-Error "RapportBundle.exe not found under RapportBundle\bin\ after dotnet build"
        exit 1
    }

    $SetupPath = Join-Path $DistDir $SetupName
    Copy-Item $BuiltExe.FullName $SetupPath -Force

    Write-Host "==> Done: $SetupPath"
} finally {
    Remove-Item $ResolvedComposePath -ErrorAction SilentlyContinue
    Remove-Item $LicenseRtfPath -ErrorAction SilentlyContinue
}
