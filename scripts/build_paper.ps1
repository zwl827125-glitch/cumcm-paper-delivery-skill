param(
    [Parameter(Mandatory = $true)]
    [string]$SourceMarkdown,

    [Parameter(Mandatory = $true)]
    [string]$OutputDocx,

    [string]$ReferenceDocx,
    [switch]$TableOfContents,
    [switch]$SkipOfficeRefresh
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$source = (Resolve-Path -LiteralPath $SourceMarkdown).Path
$output = [System.IO.Path]::GetFullPath($OutputDocx)
$outputDir = Split-Path -Parent $output
if (-not (Test-Path -LiteralPath $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

$pandoc = Get-Command pandoc -ErrorAction SilentlyContinue
if ($null -eq $pandoc) {
    throw '未找到 Pandoc。请先安装 Pandoc，或由所用 Agent 的文档工具生成 DOCX 后再调用 office_bridge.ps1。'
}

$arguments = @(
    $source,
    '--from=markdown+tex_math_dollars+pipe_tables',
    '--to=docx',
    "--output=$output",
    "--resource-path=$(Split-Path -Parent $source)"
)

if (-not [string]::IsNullOrWhiteSpace($ReferenceDocx)) {
    $reference = (Resolve-Path -LiteralPath $ReferenceDocx).Path
    $arguments += "--reference-doc=$reference"
}
if ($TableOfContents) {
    $arguments += '--toc'
}

& $pandoc.Source @arguments
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $output)) {
    throw "Pandoc 生成 DOCX 失败，退出码：$LASTEXITCODE"
}

$officeRefreshed = $false
if (-not $SkipOfficeRefresh -and $env:OS -eq 'Windows_NT' -and $null -ne [Type]::GetTypeFromProgID('Word.Application')) {
    $bridge = Join-Path $PSScriptRoot 'office_bridge.ps1'
    & $bridge -Action refresh-word -InputPath $output | Out-Null
    $officeRefreshed = $true
}

[pscustomobject]@{
    source = $source
    output = $output
    reference_docx = if ([string]::IsNullOrWhiteSpace($ReferenceDocx)) { $null } else { $reference }
    office_refreshed = $officeRefreshed
} | ConvertTo-Json -Depth 3
