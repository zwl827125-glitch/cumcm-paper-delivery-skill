[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$InputDocx,

  [Parameter(Mandatory = $true)]
  [string]$OutputDir,

  [ValidateRange(100, 500)]
  [int]$Zoom = 250
)

$ErrorActionPreference = 'Stop'

if ([System.Threading.Thread]::CurrentThread.ApartmentState -ne 'STA') {
  throw 'Clipboard capture requires an STA host. Run with Windows PowerShell: powershell.exe -STA -File <script> ...'
}

$inputPath = (Resolve-Path -LiteralPath $InputDocx).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$word = New-Object -ComObject Word.Application
$word.Visible = $true
$word.DisplayAlerts = 0
$doc = $null
$records = @()

try {
  $doc = $word.Documents.OpenNoRepairDialog($inputPath, $false, $true, $false)
  $window = $doc.ActiveWindow
  $window.WindowState = 1
  $window.View.Type = 3
  $window.View.Zoom.Percentage = $Zoom
  $word.Activate()
  Start-Sleep -Milliseconds 700

  $observedZoom = [int]$window.View.Zoom.Percentage
  if ($observedZoom -ne $Zoom) {
    throw "Word zoom mismatch: requested $Zoom, observed $observedZoom"
  }

  $formulaCount = [int]$doc.OMaths.Count
  if ($formulaCount -lt 1) {
    throw 'No Office Math objects were found in the DOCX.'
  }

  for ($index = 1; $index -le $formulaCount; $index++) {
    $formula = $doc.OMaths.Item($index)
    $range = $formula.Range
    $range.Select()
    $window.ScrollIntoView($range, $true)
    $word.Activate()
    Start-Sleep -Milliseconds 450

    [System.Windows.Forms.Clipboard]::Clear()
    $word.Selection.CopyAsPicture()
    Start-Sleep -Milliseconds 350

    $image = [System.Windows.Forms.Clipboard]::GetImage()
    if ($null -eq $image) {
      Start-Sleep -Milliseconds 500
      $word.Selection.CopyAsPicture()
      Start-Sleep -Milliseconds 350
      $image = [System.Windows.Forms.Clipboard]::GetImage()
    }
    if ($null -eq $image) {
      throw "Word did not place formula $index on the clipboard as an image."
    }

    $marginX = 36
    $marginY = 28
    $bitmap = New-Object System.Drawing.Bitmap ($image.Width + 2 * $marginX), ($image.Height + 2 * $marginY)
    $outputWidth = [int]$bitmap.Width
    $outputHeight = [int]$bitmap.Height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
      $graphics.Clear([System.Drawing.Color]::White)
      $graphics.DrawImage($image, $marginX, $marginY, $image.Width, $image.Height)
      $fileName = 'formula-{0:D2}.png' -f $index
      $filePath = Join-Path $outputPath $fileName
      $bitmap.Save($filePath, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
      $graphics.Dispose()
      $bitmap.Dispose()
      $image.Dispose()
    }

    $saved = Get-Item -LiteralPath $filePath
    $records += [ordered]@{
      id = 'F{0:D2}' -f $index
      file = $fileName
      width_px = $outputWidth
      height_px = $outputHeight
      bytes = [int64]$saved.Length
    }
  }

  $manifest = [ordered]@{
    input_docx = $inputPath
    input_sha256 = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash
    microsoft_word_version = [string]$word.Version
    view = 'Print View'
    zoom_requested_percent = $Zoom
    zoom_observed_percent = $observedZoom
    capture_method = 'Microsoft Word Selection.CopyAsPicture after selecting each Office Math object at the observed zoom'
    formula_count = $formulaCount
    formulas = $records
  }
  $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $outputPath 'capture_manifest.json') -Encoding UTF8
  $manifest | ConvertTo-Json -Depth 5
}
finally {
  if ($null -ne $doc) {
    $doc.Close($false)
  }
  $word.Quit()
}
