param(
    [string]$TargetRoot,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($TargetRoot)) {
    $codexBase = if ([string]::IsNullOrWhiteSpace($env:CODEX_HOME)) {
        Join-Path $env:USERPROFILE '.codex'
    }
    else {
        $env:CODEX_HOME
    }
    $TargetRoot = Join-Path $codexBase 'skills'
}

$target = [System.IO.Path]::GetFullPath($TargetRoot)
$targetDriveRoot = [System.IO.Path]::GetPathRoot($target)
if ($target.TrimEnd('\', '/') -eq $targetDriveRoot.TrimEnd('\', '/')) {
    throw '拒绝把磁盘根目录作为 Skills 安装目标。请指定明确的 skills 文件夹。'
}
New-Item -ItemType Directory -Path $target -Force | Out-Null

function Copy-Package {
    param([string]$Source, [string]$Destination)
    if (Test-Path -LiteralPath $Destination) {
        if (-not $Force) {
            throw "目标已存在：$Destination。若要更新，请显式加 -Force。"
        }
    }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    Get-ChildItem -LiteralPath $Source -Recurse -File | ForEach-Object {
        $relative = $_.FullName.Substring($Source.Length).TrimStart('\', '/')
        if ($relative -like '.git\*' -or $relative -like '__pycache__\*' -or $relative -like '*.pyc') {
            return
        }
        $output = Join-Path $Destination $relative
        $parent = Split-Path -Parent $output
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $output -Force
    }
}

$mainDestination = Join-Path $target 'cumcm-paper-delivery'
if ((Test-Path -LiteralPath $mainDestination) -and -not $Force) {
    throw "目标已存在：$mainDestination。若要更新，请显式加 -Force。"
}
New-Item -ItemType Directory -Path $mainDestination -Force | Out-Null

$mainFiles = @('SKILL.md', 'VERSION', 'requirements.txt', 'LICENSE', 'NOTICE.md', 'RIGHTS_AND_SOURCES.md', 'PAPER_CHECKSUMS.sha256')
foreach ($name in $mainFiles) {
    Copy-Item -LiteralPath (Join-Path $repoRoot $name) -Destination (Join-Path $mainDestination $name) -Force
}
foreach ($name in @('agents', 'references', 'scripts')) {
    Copy-Package (Join-Path $repoRoot $name) (Join-Path $mainDestination $name)
}

$dependencyRoot = Join-Path $repoRoot 'dependencies'
$installed = @('cumcm-paper-delivery')
Get-ChildItem -LiteralPath $dependencyRoot -Directory | Sort-Object Name | ForEach-Object {
    $destination = Join-Path $target $_.Name
    Copy-Package $_.FullName $destination
    $installed += $_.Name
}

[pscustomobject]@{
    target_root = $target
    installed = $installed
    count = $installed.Count
    updated_existing = [bool]$Force
} | ConvertTo-Json -Depth 4
