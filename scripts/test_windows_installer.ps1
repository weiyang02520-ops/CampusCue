[CmdletBinding()]
param([string]$SourceRoot)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not $SourceRoot) { $SourceRoot = Split-Path -Parent $PSScriptRoot }
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("campuscue-installer-" + [guid]::NewGuid().ToString("N"))
$destination = Join-Path $testRoot "CampusCue"
$installer = Join-Path $SourceRoot "scripts\install_campuscue.ps1"

try {
    & $installer -Action Install -SourceRoot $SourceRoot -Destination $destination -SkipDependencies -NoIntegration -Unattended

    $manifestPath = Join-Path $destination ".campuscue-install.json"
    if (-not (Test-Path -LiteralPath $manifestPath)) { throw "Install manifest is missing." }
    if (-not (Test-Path -LiteralPath (Join-Path $destination "Start CampusCue.bat"))) { throw "Launcher is missing." }
    if (Test-Path -LiteralPath (Join-Path $destination "node_modules")) { throw "node_modules leaked into the install." }
    if (Test-Path -LiteralPath (Join-Path $destination ".venv")) { throw "Source virtual environment leaked into the install." }

    Set-Content -LiteralPath (Join-Path $destination ".env") -Value "PRESERVE_ENV=1" -Encoding ASCII
    New-Item -ItemType Directory -Path (Join-Path $destination "data") -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $destination "data\preserve.txt") -Value "private" -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $destination "obsolete-managed.txt") -Value "old" -Encoding ASCII
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $manifest.files = @($manifest.files) + "obsolete-managed.txt"
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

    & $installer -Action Install -SourceRoot $SourceRoot -Destination $destination -SkipDependencies -NoIntegration -Unattended
    if ((Get-Content -LiteralPath (Join-Path $destination ".env") -Raw).Trim() -ne "PRESERVE_ENV=1") { throw ".env was overwritten." }
    if ((Get-Content -LiteralPath (Join-Path $destination "data\preserve.txt") -Raw).Trim() -ne "private") { throw "Private data was overwritten." }
    if (Test-Path -LiteralPath (Join-Path $destination "obsolete-managed.txt")) { throw "Obsolete managed file was not removed." }
    if (-not (Test-Path -LiteralPath (Join-Path $testRoot "CampusCue-upgrade-backups") -PathType Container)) { throw "Upgrade backup is missing." }

    & $installer -Action Uninstall -Destination $destination -NoIntegration -Unattended
    if (Test-Path -LiteralPath (Join-Path $destination "Start CampusCue.bat")) { throw "Managed files remain after uninstall." }
    if (Test-Path -LiteralPath $manifestPath) { throw "Install manifest remains after uninstall." }
    if ((Get-Content -LiteralPath (Join-Path $destination ".env") -Raw).Trim() -ne "PRESERVE_ENV=1") { throw ".env was removed by default uninstall." }
    if ((Get-Content -LiteralPath (Join-Path $destination "data\preserve.txt") -Raw).Trim() -ne "private") { throw "Private data was removed by default uninstall." }

    Write-Host "Windows installer lifecycle test passed."
} finally {
    $resolvedTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    $resolvedTest = [System.IO.Path]::GetFullPath($testRoot)
    if (-not $resolvedTest.StartsWith($resolvedTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean a test path outside the system temporary directory."
    }
    Remove-Item -LiteralPath $resolvedTest -Recurse -Force -ErrorAction SilentlyContinue
}
