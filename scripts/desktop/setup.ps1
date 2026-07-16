param(
    [switch] $SkipPython,
    [switch] $SkipRendererBuild
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$DesktopAppDir = Join-Path $RepoRoot "desktop_app"
$RendererDir = Join-Path $DesktopAppDir "renderer_client"
$RequirementsPath = Join-Path $RepoRoot "requirements.txt"

function Write-Step {
    param([string] $Message)
    Write-Host "[emploai] $Message"
}

function Assert-Command {
    param([string] $Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found on PATH."
    }
}

function Invoke-Checked {
    param(
        [string] $Label,
        [scriptblock] $Command
    )

    Write-Step $Label
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

function Invoke-NpmInDirectory {
    param(
        [string] $Directory,
        [string[]] $NpmArgs
    )

    Push-Location -LiteralPath $Directory
    try {
        & npm @NpmArgs
    } finally {
        Pop-Location
    }
}

function Get-PythonRuntime {
    $configured = "$env:EMPLOAI_DESKTOP_PYTHON".Trim()
    if ($configured) {
        return $configured
    }

    foreach ($candidate in @("py", "python", "python3")) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            return $candidate
        }
    }

    return $null
}

function Invoke-PythonRuntime {
    param([string[]] $PythonArgs)

    $configured = "$env:EMPLOAI_DESKTOP_PYTHON".Trim()
    if ($configured) {
        & $configured @PythonArgs
        return
    }

    if (Get-Command "py" -ErrorAction SilentlyContinue) {
        & py -3 @PythonArgs
        return
    }

    if (Get-Command "python" -ErrorAction SilentlyContinue) {
        & python @PythonArgs
        return
    }

    if (Get-Command "python3" -ErrorAction SilentlyContinue) {
        & python3 @PythonArgs
        return
    }

    throw "Python was not found. Install Python 3, add it to PATH, or set EMPLOAI_DESKTOP_PYTHON to the Python executable."
}

Assert-Command "npm"
$PythonRuntime = Get-PythonRuntime

Invoke-Checked "Installing desktop shell dependencies" {
    Invoke-NpmInDirectory $DesktopAppDir @("ci")
}

Invoke-Checked "Installing desktop renderer dependencies" {
    Invoke-NpmInDirectory $RendererDir @("ci")
}

if (-not $SkipPython) {
    if (-not $PythonRuntime) {
        throw "Python was not found. Install Python 3, add it to PATH, or set EMPLOAI_DESKTOP_PYTHON to the Python executable."
    }

    Invoke-Checked "Installing Python runtime dependencies" {
        Invoke-PythonRuntime @("-m", "pip", "install", "-r", $RequirementsPath)
    }
}

if (-not $SkipRendererBuild) {
    Invoke-Checked "Building desktop renderer" {
        Invoke-NpmInDirectory $RendererDir @("run", "export:web")
    }
}

Write-Step "Setup complete. Start the app with: npm start"
