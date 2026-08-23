[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $CumcmArguments
)

$CumcmScript = Join-Path $PSScriptRoot 'cumcm_engine.py'
$CumcmBundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'

if (Test-Path -LiteralPath $CumcmBundledPython -PathType Leaf) {
    & $CumcmBundledPython $CumcmScript @CumcmArguments
    exit $LASTEXITCODE
}

$CumcmPythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($null -ne $CumcmPythonCommand -and $CumcmPythonCommand.Source -notmatch '\\WindowsApps\\python\.exe$') {
    & $CumcmPythonCommand.Source $CumcmScript @CumcmArguments
    exit $LASTEXITCODE
}

$CumcmPyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($null -ne $CumcmPyLauncher) {
    & $CumcmPyLauncher.Source -3 $CumcmScript @CumcmArguments
    exit $LASTEXITCODE
}

throw 'Python 3 was not found. Install Python or load the bundled Codex Desktop workspace runtime.'
