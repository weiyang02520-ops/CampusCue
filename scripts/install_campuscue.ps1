[CmdletBinding()]
param(
    [ValidateSet("Install", "Uninstall")]
    [string]$Action = "Install",
    [string]$SourceRoot,
    [string]$Destination,
    [switch]$SkipDependencies,
    [switch]$NoIntegration,
    [switch]$Unattended,
    [switch]$PurgeUserData
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "This installer supports Windows only."
}

if (-not $SourceRoot) { $SourceRoot = Split-Path -Parent $PSScriptRoot }
if (-not $Destination) { $Destination = Join-Path $env:LOCALAPPDATA "CampusCue" }
$SourceRoot = [System.IO.Path]::GetFullPath($SourceRoot)
$Destination = [System.IO.Path]::GetFullPath($Destination)
$manifestPath = Join-Path $Destination ".campuscue-install.json"
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\CampusCue"

function Get-ManagedFiles {
    param([Parameter(Mandatory)][string]$Root)

    $excludedDirectoryNames = @(
        ".git", ".mypy_cache", ".pnpm-store", ".pytest_cache", ".ruff_cache",
        ".tmp", "__pycache__", "node_modules"
    )
    $excludedRootDirectories = @("data", "MEMORY")
    $excludedRootFiles = @(
        ".campuscue-install.json", ".coverage", ".env", "PROGRESS.md",
        "PROJECT_STATE.json", "astrbot.lock", "botpy.log", "cookies.json"
    )

    $files = [System.Collections.Generic.List[string]]::new()
    $pending = [System.Collections.Generic.Stack[string]]::new()
    $pending.Push($Root)
    while ($pending.Count -gt 0) {
        $current = $pending.Pop()
        foreach ($file in Get-ChildItem -LiteralPath $current -File -Force) {
            $relative = $file.FullName.Substring($Root.Length).TrimStart("\", "/")
            if ($excludedRootFiles -notcontains $relative -and $file.Extension -notin @(".pyc", ".pyo")) {
                $files.Add($relative)
            }
        }
        foreach ($directory in Get-ChildItem -LiteralPath $current -Directory -Force) {
            $isRootDirectory = $current.TrimEnd("\") -eq $Root.TrimEnd("\")
            if (
                $excludedDirectoryNames -notcontains $directory.Name -and
                $directory.Name -notlike ".venv*" -and
                -not ($isRootDirectory -and $excludedRootDirectories -contains $directory.Name)
            ) {
                $pending.Push($directory.FullName)
            }
        }
    }
    @($files | Sort-Object -Unique)
}

function Remove-Integration {
    $shell = New-Object -ComObject WScript.Shell
    $desktop = $shell.SpecialFolders.Item("Desktop")
    $programs = $shell.SpecialFolders.Item("Programs")
    foreach ($path in @(
        (Join-Path $desktop "CampusCue.lnk"),
        (Join-Path $programs "CampusCue\CampusCue.lnk"),
        (Join-Path $programs "CampusCue\Stop CampusCue.lnk"),
        (Join-Path $programs "CampusCue\Uninstall CampusCue.lnk")
    )) {
        Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath (Join-Path $programs "CampusCue") -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $uninstallKey -Recurse -Force -ErrorAction SilentlyContinue
}

function Add-Integration {
    $shell = New-Object -ComObject WScript.Shell
    $desktop = $shell.SpecialFolders.Item("Desktop")
    $programs = Join-Path $shell.SpecialFolders.Item("Programs") "CampusCue"
    New-Item -ItemType Directory -Path $programs -Force | Out-Null

    $shortcuts = @(
        @{ Path = (Join-Path $desktop "CampusCue.lnk"); Target = "Start CampusCue.bat" },
        @{ Path = (Join-Path $programs "CampusCue.lnk"); Target = "Start CampusCue.bat" },
        @{ Path = (Join-Path $programs "Stop CampusCue.lnk"); Target = "Stop CampusCue.bat" },
        @{ Path = (Join-Path $programs "Uninstall CampusCue.lnk"); Target = "Uninstall CampusCue.bat" }
    )
    foreach ($item in $shortcuts) {
        $shortcut = $shell.CreateShortcut($item.Path)
        $shortcut.TargetPath = Join-Path $Destination $item.Target
        $shortcut.WorkingDirectory = $Destination
        $shortcut.Description = "CampusCue local campus task assistant"
        $shortcut.Save()
    }

    $versionText = Get-Content -LiteralPath (Join-Path $Destination "campuscue\__init__.py") -Raw
    $version = if ($versionText -match '__version__\s*=\s*["'']([^"'']+)["'']') {
        $Matches[1]
    } else {
        "0.0.0"
    }
    New-Item -Path $uninstallKey -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name DisplayName -Value "CampusCue" -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name DisplayVersion -Value $version -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name Publisher -Value "CampusCue" -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name InstallLocation -Value $Destination -Force | Out-Null
    $uninstallCommand = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}" -Action Uninstall -Destination "{1}"' -f (Join-Path $Destination "scripts\install_campuscue.ps1"), $Destination
    New-ItemProperty -Path $uninstallKey -Name UninstallString -Value $uninstallCommand -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name NoModify -PropertyType DWord -Value 1 -Force | Out-Null
}

if ($Action -eq "Uninstall") {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "This folder does not contain a managed CampusCue installation."
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $runtimePython = Join-Path $Destination ".venv\Scripts\python.exe"
    $runtimeScript = Join-Path $Destination "scripts\campuscue_runtime.py"
    if ((Test-Path -LiteralPath $runtimePython) -and (Test-Path -LiteralPath $runtimeScript)) {
        & $runtimePython $runtimeScript stop --timeout 15
        if ($LASTEXITCODE -notin @(0, 1)) {
            throw "CampusCue could not be stopped safely. Uninstall was cancelled."
        }
    }

    foreach ($relative in @($manifest.files)) {
        Remove-Item -LiteralPath (Join-Path $Destination $relative) -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath (Join-Path $Destination ".venv") -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $Destination ".tmp") -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $manifestPath -Force -ErrorAction SilentlyContinue
    if ($PurgeUserData) {
        Remove-Item -LiteralPath (Join-Path $Destination "data") -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath (Join-Path $Destination ".env") -Force -ErrorAction SilentlyContinue
    }
    if (-not $NoIntegration) {
        Remove-Integration
    }
    Get-ChildItem -LiteralPath $Destination -Directory -Recurse -Force -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | ForEach-Object {
            if (-not (Get-ChildItem -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue)) {
                Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
            }
        }
    Write-Host "CampusCue was uninstalled."
    if (-not $PurgeUserData) {
        Write-Host "Private settings and data were preserved in: $Destination"
    }
    if (-not $Unattended) {
        Read-Host "Press Enter to close"
    }
    exit 0
}

if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot "main.py") -PathType Leaf)) {
    throw "CampusCue source root is invalid: $SourceRoot"
}
if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot "campuscue\web\dist\index.html") -PathType Leaf)) {
    throw "The bundled CampusCue frontend is missing."
}

$sourceFiles = Get-ManagedFiles -Root $SourceRoot
if ($sourceFiles.Count -eq 0) {
    throw "No application files were selected for installation."
}

$isUpgrade = Test-Path -LiteralPath $manifestPath -PathType Leaf
$previousFiles = @()
$backupRoot = $null
if ($isUpgrade) {
    $runtimePython = Join-Path $Destination ".venv\Scripts\python.exe"
    $runtimeScript = Join-Path $Destination "scripts\campuscue_runtime.py"
    if ((Test-Path -LiteralPath $runtimePython) -and (Test-Path -LiteralPath $runtimeScript)) {
        & $runtimePython $runtimeScript stop --timeout 15
        if ($LASTEXITCODE -notin @(0, 1)) {
            throw "CampusCue could not be stopped safely. Upgrade was cancelled."
        }
    }
    $previousManifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $previousFiles = @($previousManifest.files)
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupRoot = Join-Path (Split-Path -Parent $Destination) "CampusCue-upgrade-backups\$stamp"
    foreach ($relative in $previousFiles) {
        $existing = Join-Path $Destination $relative
        if (Test-Path -LiteralPath $existing -PathType Leaf) {
            $backup = Join-Path $backupRoot $relative
            New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
            Copy-Item -LiteralPath $existing -Destination $backup -Force
        }
    }
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $backupRoot ".campuscue-install.json") -Force
}

New-Item -ItemType Directory -Path $Destination -Force | Out-Null
try {
    if ($SourceRoot.TrimEnd("\") -ne $Destination.TrimEnd("\")) {
        foreach ($relative in $sourceFiles) {
            $source = Join-Path $SourceRoot $relative
            $target = Join-Path $Destination $relative
            New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
            Copy-Item -LiteralPath $source -Destination $target -Force
        }
    }
    foreach ($relative in $previousFiles) {
        if ($sourceFiles -notcontains $relative) {
            Remove-Item -LiteralPath (Join-Path $Destination $relative) -Force -ErrorAction SilentlyContinue
        }
    }

    if (-not (Test-Path -LiteralPath (Join-Path $Destination ".env")) -and
        (Test-Path -LiteralPath (Join-Path $Destination ".env.example"))) {
        Copy-Item -LiteralPath (Join-Path $Destination ".env.example") -Destination (Join-Path $Destination ".env")
    }

    if (-not $SkipDependencies) {
        $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if (-not $launcher) {
            throw "Python Launcher was not found. Install Python 3.12 from python.org and retry."
        }
        & $launcher.Source -3.12 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)"
        if ($LASTEXITCODE -ne 0) {
            throw "Python 3.12 was not found. Install Python 3.12 from python.org and retry."
        }
        $venvPython = Join-Path $Destination ".venv\Scripts\python.exe"
        if (Test-Path -LiteralPath $venvPython) {
            & $venvPython -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)"
            if ($LASTEXITCODE -ne 0) {
                $incompatible = Join-Path $Destination (".venv-incompatible-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
                Move-Item -LiteralPath (Join-Path $Destination ".venv") -Destination $incompatible
            }
        }
        if (-not (Test-Path -LiteralPath $venvPython)) {
            & $launcher.Source -3.12 -m venv (Join-Path $Destination ".venv")
            if ($LASTEXITCODE -ne 0) { throw "Failed to create the Python 3.12 environment." }
        }
        & $venvPython -m pip install --disable-pip-version-check -r (Join-Path $Destination "requirements.txt")
        if ($LASTEXITCODE -ne 0) { throw "Failed to install CampusCue dependencies." }
        & $venvPython -m pip check
        if ($LASTEXITCODE -ne 0) { throw "Installed Python dependencies are inconsistent." }
    }

    $versionText = Get-Content -LiteralPath (Join-Path $Destination "campuscue\__init__.py") -Raw
    $version = if ($versionText -match '__version__\s*=\s*["'']([^"'']+)["'']') { $Matches[1] } else { "0.0.0" }
    $manifest = [ordered]@{
        schemaVersion = 1
        product = "CampusCue"
        version = $version
        installedAt = [DateTimeOffset]::Now.ToString("o")
        source = $SourceRoot
        files = $sourceFiles
    }
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    if (-not $NoIntegration) {
        Remove-Integration
        Add-Integration
    }
} catch {
    if ($backupRoot -and (Test-Path -LiteralPath $backupRoot)) {
        foreach ($relative in $previousFiles) {
            $backup = Join-Path $backupRoot $relative
            if (Test-Path -LiteralPath $backup -PathType Leaf) {
                $target = Join-Path $Destination $relative
                New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
                Copy-Item -LiteralPath $backup -Destination $target -Force
            }
        }
        Copy-Item -LiteralPath (Join-Path $backupRoot ".campuscue-install.json") -Destination $manifestPath -Force
    }
    throw
}

Write-Host "CampusCue installation completed: $Destination"
if ($backupRoot) {
    Write-Host "Previous application files were backed up to: $backupRoot"
}
if (-not $Unattended) {
    if (-not $isUpgrade) {
        Start-Process notepad.exe -ArgumentList ('"{0}"' -f (Join-Path $Destination ".env"))
        Write-Host "The private .env settings file has been opened in Notepad."
    }
    Read-Host "Press Enter to close"
}
