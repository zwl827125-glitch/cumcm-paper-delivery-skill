param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('probe', 'inspect-word', 'refresh-word', 'word-to-pdf', 'excel-recalc')]
    [string]$Action,

    [string]$InputPath,
    [string]$OutputPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-InputFile {
    param([string]$PathValue)
    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        throw '该操作必须提供 -InputPath。'
    }
    return (Resolve-Path -LiteralPath $PathValue).Path
}

function Resolve-OutputFile {
    param([string]$PathValue, [string]$DefaultPath)
    $candidate = if ([string]::IsNullOrWhiteSpace($PathValue)) { $DefaultPath } else { $PathValue }
    $absolute = [System.IO.Path]::GetFullPath($candidate)
    $parent = Split-Path -Parent $absolute
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    return $absolute
}

function Release-ComObject {
    param($Object)
    if ($null -ne $Object -and [System.Runtime.InteropServices.Marshal]::IsComObject($Object)) {
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($Object)
    }
}

function Get-OfficeProbe {
    $isWindowsHost = $env:OS -eq 'Windows_NT'
    $wordAvailable = $false
    $excelAvailable = $false
    if ($isWindowsHost) {
        $wordAvailable = $null -ne [Type]::GetTypeFromProgID('Word.Application')
        $excelAvailable = $null -ne [Type]::GetTypeFromProgID('Excel.Application')
    }
    [pscustomobject]@{
        action = 'probe'
        windows = $isWindowsHost
        word_com = $wordAvailable
        excel_com = $excelAvailable
        pandoc = [bool](Get-Command pandoc -ErrorAction SilentlyContinue)
        libreoffice = [bool](Get-Command libreoffice -ErrorAction SilentlyContinue)
    }
}

function Invoke-WordAction {
    param([string]$Mode, [string]$DocumentPath, [string]$TargetPath)

    if ($env:OS -ne 'Windows_NT') {
        throw 'Microsoft Word COM 仅可在安装了桌面版 Word 的 Windows 上运行。'
    }

    $word = $null
    $document = $null
    try {
        $word = New-Object -ComObject Word.Application
        $word.Visible = $false
        $word.DisplayAlerts = 0
        try { $word.AutomationSecurity = 3 } catch { }

        $readOnly = $Mode -eq 'inspect-word' -or $Mode -eq 'word-to-pdf'
        $document = $word.Documents.Open($DocumentPath, $false, $readOnly, $false)

        if ($Mode -eq 'refresh-word') {
            foreach ($field in @($document.Fields)) { [void]$field.Update() }
            foreach ($toc in @($document.TablesOfContents)) { [void]$toc.Update() }
            foreach ($tof in @($document.TablesOfFigures)) { [void]$tof.Update() }
            $document.Repaginate()
            $document.Save()
        }

        if ($Mode -eq 'word-to-pdf') {
            $document.Repaginate()
            $document.ExportAsFixedFormat($TargetPath, 17)
        }

        [pscustomobject]@{
            action = $Mode
            input = $DocumentPath
            output = if ($Mode -eq 'word-to-pdf') { $TargetPath } else { $null }
            pages = $document.ComputeStatistics(2)
            equations = $document.OMaths.Count
            tables = $document.Tables.Count
            inline_shapes = $document.InlineShapes.Count
            floating_shapes = $document.Shapes.Count
            fields = $document.Fields.Count
            sections = $document.Sections.Count
        }
    }
    finally {
        if ($null -ne $document) {
            try { $document.Close(0) } catch { }
        }
        if ($null -ne $word) {
            try { $word.Quit() } catch { }
        }
        Release-ComObject $document
        Release-ComObject $word
        [GC]::Collect()
        [GC]::WaitForPendingFinalizers()
    }
}

function Invoke-ExcelRecalc {
    param([string]$WorkbookPath)

    if ($env:OS -ne 'Windows_NT') {
        throw 'Microsoft Excel COM 仅可在安装了桌面版 Excel 的 Windows 上运行。'
    }

    $excel = $null
    $workbook = $null
    try {
        $excel = New-Object -ComObject Excel.Application
        $excel.Visible = $false
        $excel.DisplayAlerts = $false
        try { $excel.AutomationSecurity = 3 } catch { }
        $workbook = $excel.Workbooks.Open($WorkbookPath, 0, $false)
        $excel.Calculation = -4105
        $excel.CalculateFullRebuild()
        $workbook.Save()

        $formulaCount = 0
        foreach ($sheet in @($workbook.Worksheets)) {
            try {
                $formulaCells = $sheet.UsedRange.SpecialCells(-4123)
                $formulaCount += $formulaCells.Count
                Release-ComObject $formulaCells
            }
            catch { }
            Release-ComObject $sheet
        }

        [pscustomobject]@{
            action = 'excel-recalc'
            input = $WorkbookPath
            worksheets = $workbook.Worksheets.Count
            formula_cells = $formulaCount
            calculation = 'full-rebuild'
        }
    }
    finally {
        if ($null -ne $workbook) {
            try { $workbook.Close($true) } catch { }
        }
        if ($null -ne $excel) {
            try { $excel.Quit() } catch { }
        }
        Release-ComObject $workbook
        Release-ComObject $excel
        [GC]::Collect()
        [GC]::WaitForPendingFinalizers()
    }
}

$result = switch ($Action) {
    'probe' {
        Get-OfficeProbe
    }
    'inspect-word' {
        $input = Resolve-InputFile $InputPath
        Invoke-WordAction $Action $input $null
    }
    'refresh-word' {
        $input = Resolve-InputFile $InputPath
        Invoke-WordAction $Action $input $null
    }
    'word-to-pdf' {
        $input = Resolve-InputFile $InputPath
        $defaultOutput = [System.IO.Path]::ChangeExtension($input, '.pdf')
        $output = Resolve-OutputFile $OutputPath $defaultOutput
        Invoke-WordAction $Action $input $output
    }
    'excel-recalc' {
        $input = Resolve-InputFile $InputPath
        Invoke-ExcelRecalc $input
    }
}

$result | ConvertTo-Json -Depth 4
