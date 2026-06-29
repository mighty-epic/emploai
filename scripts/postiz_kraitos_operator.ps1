param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $ArgsForPython
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$scriptPath = Join-Path $repoRoot "scripts\postiz_kraitos_operator.py"
$bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

$pythonCandidates = @(
    "python",
    "py",
    $bundledPython
)

$python = $null
foreach ($candidate in $pythonCandidates) {
    if ($candidate -eq $bundledPython) {
        if (Test-Path -LiteralPath $candidate) {
            $python = $candidate
            break
        }
        continue
    }

    $command = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($command) {
        $python = $command.Source
        break
    }
}

if (-not $python) {
    throw "No Python runtime found. Install Python or run through the Codex bundled runtime."
}

& $python $scriptPath @ArgsForPython
exit $LASTEXITCODE
