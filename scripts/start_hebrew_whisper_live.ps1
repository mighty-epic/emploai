param(
    [int]$DeviceIndex = 1,
    [int]$SampleRate = 0,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot "hebrew_whisper_live_terminal.py"
$ExtraArgs = @($ExtraArgs | Where-Object { $_ -is [string] -and $_.Trim().Length -gt 0 })

$pythonCandidates = @(
    "C:\Program Files\Python313\python.exe",
    "C:\Python313\python.exe"
)

$python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($python) {
    & $python $script --device-index $DeviceIndex --sample-rate $SampleRate @ExtraArgs
    exit $LASTEXITCODE
}

$py = Get-Command py.exe -ErrorAction SilentlyContinue
if ($py) {
    & $py.Source -3.13 $script --device-index $DeviceIndex --sample-rate $SampleRate @ExtraArgs
    exit $LASTEXITCODE
}

throw "Python 3.13 was not found. Install Python 3.13 or update scripts/start_hebrew_whisper_live.ps1."
