[CmdletBinding()]
param(
    [string]$SourceRoot,
    [string]$DeliveryRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Add-Type -AssemblyName System.IO.Compression
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
$fixedTimestamp = [DateTimeOffset]::Parse("2026-01-01T00:00:00+00:00")

$excludedDirectoryNames = @(
    ".git",
    ".mypy_cache",
    ".pnpm-store",
    ".pytest_cache",
    ".ruff_cache",
    ".tmp",
    "__pycache__",
    "node_modules"
)
$excludedRootDirectories = @("MEMORY", "data")
$excludedRootFiles = @("PROGRESS.md", "PROJECT_STATE.json")
$excludedFileNames = @(".campuscue-install.json", ".coverage", "astrbot.lock", "botpy.log", "cookies.json")

function Test-IsExcludedSourceFile {
    param([Parameter(Mandatory)][string]$RelativePath)

    $segments = $RelativePath -split "[\\/]"
    $fileName = $segments[-1]
    $directories = if ($segments.Length -gt 1) { $segments[0..($segments.Length - 2)] } else { @() }

    if ($excludedRootFiles -contains $RelativePath) { return $true }
    if ($segments.Length -gt 1 -and $excludedRootDirectories -contains $segments[0]) { return $true }
    if ($directories | Where-Object { $excludedDirectoryNames -contains $_ }) { return $true }
    if ($directories | Where-Object { $_ -like ".venv*" }) { return $true }
    if ($fileName -eq ".env" -or ($fileName -like ".env.*" -and $fileName -ne ".env.example")) { return $true }
    if ($excludedFileNames -contains $fileName) { return $true }
    if ($fileName -like "*.pyc" -or $fileName -like "*.pyo") { return $true }
    return $false
}

function New-DeterministicZip {
    param(
        [Parameter(Mandatory)][string]$ArchivePath,
        [Parameter(Mandatory)][object[]]$Entries
    )

    $parent = Split-Path -Parent $ArchivePath
    [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    if (Test-Path -LiteralPath $ArchivePath) {
        Remove-Item -LiteralPath $ArchivePath -Force
    }

    try {
        $stream = [System.IO.File]::Open([string]$ArchivePath, [System.IO.FileMode]::CreateNew)
    } catch {
        throw "Cannot create ZIP '$ArchivePath'. $($_.Exception.Message)"
    }
    try {
        $archive = [System.IO.Compression.ZipArchive]::new(
            $stream,
            [System.IO.Compression.ZipArchiveMode]::Create,
            $false,
            [System.Text.Encoding]::UTF8
        )
        try {
            foreach ($item in ($Entries | Sort-Object ArchiveName)) {
                $entry = $archive.CreateEntry(
                    ($item.ArchiveName -replace "\\", "/"),
                    [System.IO.Compression.CompressionLevel]::Optimal
                )
                $entry.LastWriteTime = $fixedTimestamp
                try {
                    $input = [System.IO.File]::OpenRead([string]$item.SourcePath)
                } catch {
                    throw "Cannot read source for ZIP entry '$($item.ArchiveName)': $($item.SourcePath). $($_.Exception.Message)"
                }
                try {
                    $output = $entry.Open()
                    try { $input.CopyTo($output) } finally { $output.Dispose() }
                } finally {
                    $input.Dispose()
                }
            }
        } finally {
            $archive.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

$sourceEntries = @(
    Get-ChildItem -LiteralPath $SourceRoot -Recurse -File -Force | ForEach-Object {
        $relative = $_.FullName.Substring($SourceRoot.Length).TrimStart("\", "/")
        if (-not (Test-IsExcludedSourceFile -RelativePath $relative)) {
            [pscustomobject]@{
                SourcePath = $_.FullName
                ArchiveName = "$sourceTopLevel/$($relative -replace '\\', '/')"
            }
        }
    }
)

if (-not ($sourceEntries.ArchiveName -contains "$sourceTopLevel/campuscue/web/dist/index.html")) {
    throw "Frontend build output is missing: campuscue/web/dist/index.html"
}
if ($sourceEntries.Count -eq 0) {
    throw "No source files were selected for packaging."
}

New-DeterministicZip -ArchivePath $sourceArchive -Entries $sourceEntries

$outerFiles = @(
    Get-ChildItem -LiteralPath $DeliveryRoot -File | Where-Object {
        $_.Extension -ne ".zip" -and
        $_.Extension -ne ".tmp" -and
        $_.Name -ne "PROJECTS.json" -and
        $_.Name -ne "SHA256SUMS.txt"
    } | Sort-Object Name | Select-Object -ExpandProperty Name
)
$deliveryEntries = @(
    foreach ($name in $outerFiles) {
        $path = Join-Path $DeliveryRoot $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Delivery file is missing: $path"
        }
        [pscustomobject]@{ SourcePath = $path; ArchiveName = "$deliveryTopLevel/$name" }
    }
    [pscustomobject]@{
        SourcePath = $sourceArchive
        ArchiveName = "$deliveryTopLevel/$(Split-Path -Leaf $sourceArchive)"
    }
)

New-DeterministicZip -ArchivePath $deliveryArchive -Entries $deliveryEntries

$sourceHash = (Get-FileHash -LiteralPath $sourceArchive -Algorithm SHA256).Hash
$deliveryHash = (Get-FileHash -LiteralPath $deliveryArchive -Algorithm SHA256).Hash
$checksumText = @(
    "$sourceHash *$(Split-Path -Leaf $sourceArchive)"
    "$deliveryHash *$(Split-Path -Leaf $deliveryArchive)"
) -join "`n"
[System.IO.File]::WriteAllText(
    $checksumPath,
    "$checksumText`n",
    [System.Text.UTF8Encoding]::new($false)
)
Write-Host "Source ZIP:   $sourceArchive"
Write-Host "SHA-256:      $sourceHash"
Write-Host "Delivery ZIP: $deliveryArchive"
Write-Host "SHA-256:      $deliveryHash"
Write-Host "Checksums:    $checksumPath"
