[CmdletBinding()]
param(
    [string]$SourceRoot,
    [string]$DeliveryRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Add-Type -AssemblyName System.IO.Compression.FileSystem

if (-not $SourceRoot) { $SourceRoot = Split-Path -Parent $PSScriptRoot }
if (-not $DeliveryRoot) { $DeliveryRoot = Split-Path -Parent (Split-Path -Parent $SourceRoot) }
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
$DeliveryRoot = (Resolve-Path -LiteralPath $DeliveryRoot).Path
$sourceContainerName = Split-Path -Leaf (Split-Path -Parent $SourceRoot)
$deliveryTopLevel = Split-Path -Leaf $DeliveryRoot
$sourceTopLevel = Split-Path -Leaf $SourceRoot
$sourceArchive = Join-Path $DeliveryRoot "$sourceContainerName.zip"
$deliveryArchive = Join-Path $DeliveryRoot "$deliveryTopLevel.zip"
$checksumPath = Join-Path $DeliveryRoot "SHA256SUMS.txt"

function Get-ZipEntries {
    param([Parameter(Mandatory)][string]$ArchivePath)

    $zip = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
    try {
        return @($zip.Entries | ForEach-Object FullName)
    } finally {
        $zip.Dispose()
    }
}

$sourceEntries = Get-ZipEntries -ArchivePath $sourceArchive
$deliveryEntries = Get-ZipEntries -ArchivePath $deliveryArchive
$forbiddenPattern = '(^|/)(data/|MEMORY/|PROGRESS\.md$|PROJECT_STATE\.json$|node_modules/|\.venv[^/]*/|\.tmp/|__pycache__/|\.pytest_cache/|\.ruff_cache/|\.git/|\.env$|\.env\.(?!example$))'
$forbidden = @($sourceEntries | Where-Object { $_ -match $forbiddenPattern })
$unsafePaths = @($sourceEntries + $deliveryEntries | Where-Object {
    $_ -match '(^|/)\.\.(/|$)' -or $_.StartsWith('/') -or $_ -match '^[A-Za-z]:'
})
$requiredEntries = @(
    "$sourceTopLevel/campuscue/web/dist/index.html",
    "$sourceTopLevel/campuscue/web/src/boardState.js",
    "$sourceTopLevel/campuscue/web/tests/board-state.test.js",
    "$sourceTopLevel/campuscue/web/tests/http.test.js",
    "$sourceTopLevel/campuscue/web/src/http.js",
    "$sourceTopLevel/campuscue/api/backup.py",
    "$sourceTopLevel/tests/test_campuscue_backup.py",
    "$sourceTopLevel/tests/test_campuscue_runtime.py",
    "$sourceTopLevel/scripts/campuscue_runtime.py",
    "$sourceTopLevel/scripts/install_campuscue.ps1",
    "$sourceTopLevel/scripts/test_windows_installer.ps1",
    "$sourceTopLevel/scripts/package_campuscue_delivery.ps1",
    "$sourceTopLevel/scripts/validate_campuscue_delivery.ps1",
    "$sourceTopLevel/Install CampusCue.bat",
    "$sourceTopLevel/Uninstall CampusCue.bat",
    "$sourceTopLevel/CAMPUSCUE_CHANGELOG.md",
    "$sourceTopLevel/RELEASING_CAMPUSCUE.md"
)
$missing = @($requiredEntries | Where-Object { $sourceEntries -notcontains $_ })

$expectedOuterPrefix = "$deliveryTopLevel/"
$badOuterPaths = @($deliveryEntries | Where-Object { -not $_.StartsWith($expectedOuterPrefix) })
$expectedSourceEntry = "$deliveryTopLevel/$(Split-Path -Leaf $sourceArchive)"
if ($deliveryEntries -notcontains $expectedSourceEntry) {
    $missing += $expectedSourceEntry
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("campuscue-package-" + [guid]::NewGuid().ToString("N"))
[System.IO.Directory]::CreateDirectory($tempRoot) | Out-Null
Expand-Archive -LiteralPath $deliveryArchive -DestinationPath $tempRoot
$extractedDelivery = Join-Path $tempRoot $deliveryTopLevel
$embeddedSourceArchive = Join-Path $extractedDelivery (Split-Path -Leaf $sourceArchive)
$sourceExtractRoot = Join-Path $tempRoot "source"
Expand-Archive -LiteralPath $embeddedSourceArchive -DestinationPath $sourceExtractRoot
$extractedSource = Join-Path $sourceExtractRoot $sourceTopLevel

$versionMismatches = @()
$pythonVersionText = Get-Content -LiteralPath (Join-Path $extractedSource "campuscue\__init__.py") -Raw
$pythonVersion = if ($pythonVersionText -match '__version__\s*=\s*["'']([^"'']+)["'']') { $Matches[1] } else { $null }
$packagePath = Join-Path $extractedSource "campuscue\web\package.json"
$lockPath = Join-Path $extractedSource "campuscue\web\package-lock.json"
$versionScript = 'import json,sys; [print(json.load(open(path, encoding="utf-8"))["version"]) for path in sys.argv[1:]]'
$encodedVersionScript = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($versionScript))
$pythonBootstrap = 'import base64,sys;exec(base64.b64decode(sys.argv.pop(1)))'
$sourcePython = Join-Path $SourceRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $sourcePython -PathType Leaf) {
    $webVersions = @(& $sourcePython -c $pythonBootstrap $encodedVersionScript $packagePath $lockPath)
} else {
    $webVersions = @(& py.exe -3.12 -c $pythonBootstrap $encodedVersionScript $packagePath $lockPath)
}
if ($LASTEXITCODE -ne 0) { throw "Could not parse frontend version metadata with Python 3.12." }
if ($webVersions.Count -ne 2) { throw "Frontend version metadata did not contain exactly two versions." }
$webPackageVersion = $webVersions[0]
$webLockVersion = $webVersions[1]
if (-not $pythonVersion) { $versionMismatches += "Missing campuscue.__version__." }
if ($pythonVersion -ne $webPackageVersion) { $versionMismatches += "Python and web package versions differ." }
if ($pythonVersion -ne $webLockVersion) { $versionMismatches += "Python and web lock versions differ." }

$documentMismatches = @()
$matchedDocumentCount = 0
Get-ChildItem -LiteralPath $extractedDelivery -File -Filter "*.md" | ForEach-Object {
    $sourceDocument = Join-Path $extractedSource $_.Name
    if (Test-Path -LiteralPath $sourceDocument -PathType Leaf) {
        $matchedDocumentCount++
        if ((Get-FileHash -LiteralPath $_.FullName).Hash -ne (Get-FileHash -LiteralPath $sourceDocument).Hash) {
            $documentMismatches += $_.Name
        }
    }
}
if ($matchedDocumentCount -lt 2) {
    $documentMismatches += "Fewer than two mirrored documents were found."
}

$sourceHash = (Get-FileHash -LiteralPath $sourceArchive -Algorithm SHA256).Hash
$deliveryHash = (Get-FileHash -LiteralPath $deliveryArchive -Algorithm SHA256).Hash
$expectedChecksums = @(
    "$sourceHash *$(Split-Path -Leaf $sourceArchive)"
    "$deliveryHash *$(Split-Path -Leaf $deliveryArchive)"
)
$actualChecksums = if (Test-Path -LiteralPath $checksumPath -PathType Leaf) {
    @(Get-Content -LiteralPath $checksumPath -Encoding UTF8)
} else {
    @()
}
$checksumMismatch = -not (
    $actualChecksums.Count -eq $expectedChecksums.Count -and
    -not (Compare-Object $expectedChecksums $actualChecksums)
)

$quoteClass = "[" + [char]39 + [char]34 + "]"
$secretPattern = '(sk-[A-Za-z0-9_-]{20,}|AKLT[A-Za-z0-9]{16,}|(?i)(api[_-]?key|secret|token)\s*[=:]\s*' + $quoteClass + '[A-Za-z0-9_-]{20,}' + $quoteClass + ')'
$secretHits = @(& rg -n -I --hidden --glob "!*.map" --glob "!.env.example" $secretPattern $extractedSource 2>$null)
if ($LASTEXITCODE -gt 1) {
    throw "Secret scan failed with exit code $LASTEXITCODE."
}

$failures = $forbidden.Count + $unsafePaths.Count + $missing.Count + $badOuterPaths.Count + $documentMismatches.Count + $versionMismatches.Count + $secretHits.Count + [int]$checksumMismatch
[pscustomobject]@{
    SourceEntries = $sourceEntries.Count
    DeliveryEntries = $deliveryEntries.Count
    SourceBytes = (Get-Item -LiteralPath $sourceArchive).Length
    DeliveryBytes = (Get-Item -LiteralPath $deliveryArchive).Length
    SourceSha256 = $sourceHash
    DeliverySha256 = $deliveryHash
    ForbiddenEntries = $forbidden.Count
    UnsafePaths = $unsafePaths.Count
    MissingEntries = $missing.Count
    BadOuterPaths = $badOuterPaths.Count
    DocumentMismatches = $documentMismatches.Count
    VersionMismatches = $versionMismatches.Count
    SecretLikeHits = $secretHits.Count
    ChecksumFile = if ($checksumMismatch) { "mismatch" } else { "passed" }
    ExtractedSource = $extractedSource
} | Format-List

if ($failures -gt 0) {
    if ($forbidden) { Write-Error "Forbidden entries: $($forbidden -join ', ')" }
    if ($unsafePaths) { Write-Error "Unsafe paths: $($unsafePaths -join ', ')" }
    if ($missing) { Write-Error "Missing entries: $($missing -join ', ')" }
    if ($badOuterPaths) { Write-Error "Bad outer paths: $($badOuterPaths -join ', ')" }
    if ($documentMismatches) { Write-Error "Document mismatches: $($documentMismatches -join ', ')" }
    if ($versionMismatches) { Write-Error "Version mismatches: $($versionMismatches -join ', ')" }
    if ($secretHits) { Write-Error "Secret-like content found in $($secretHits.Count) location(s)." }
    if ($checksumMismatch) { Write-Error "SHA256SUMS.txt is missing or does not match the archives." }
    exit 1
}

Write-Host "Delivery validation passed."
