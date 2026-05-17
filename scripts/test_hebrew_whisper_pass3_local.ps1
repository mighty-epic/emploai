param(
    [Parameter(Mandatory = $true)]
    [string]$AudioPath,
    [string]$ModelDir = "$HOME\Documents\Models\hebrew-whisper-small-pass3-knesset-runtime-ready",
    [ValidateSet("transformers", "faster-whisper")]
    [string]$Runtime = "",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot "test_hebrew_whisper_local.py"

$env:EMPLO_APP_STT_HEBREW_MODEL_DIR = $ModelDir
if ($Runtime) {
    $ExtraArgs = @("--runtime", $Runtime) + $ExtraArgs
}

$pythonCandidates = @(
    "C:\Program Files\Python313\python.exe",
    "C:\Python313\python.exe"
)

$python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($python) {
    & $python $script --audio-path $AudioPath @ExtraArgs
    exit $LASTEXITCODE
}

$py = Get-Command py.exe -ErrorAction SilentlyContinue
if ($py) {
    & $py.Source -3.13 $script --audio-path $AudioPath @ExtraArgs
    exit $LASTEXITCODE
}

throw "Python 3.13 was not found. Install Python 3.13 or update scripts/test_hebrew_whisper_pass3_local.ps1."
