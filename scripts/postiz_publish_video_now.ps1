param(
    [Parameter(Mandatory = $true)]
    [string] $Video,

    [string[]] $Platform = @("all"),

    [string] $Caption,

    [string] $Title = "Kraitos: desktop AI operator",

    [string] $Url = "https://kraitos.app/",

    [switch] $PublishNow
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

$argsForPython = @(
    $scriptPath,
    "--quick-video",
    $Video,
    "--quick-title",
    $Title,
    "--quick-url",
    $Url
)

foreach ($item in $Platform) {
    $argsForPython += @("--quick-platform", $item)
}

if ($Caption) {
    $argsForPython += @("--quick-caption", $Caption)
}

if ($PublishNow) {
    $argsForPython += "--publish-now"
}

& $python @argsForPython
exit $LASTEXITCODE
