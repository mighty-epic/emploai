param(
    [switch] $Fast,
    [switch] $NoInstall,
    [switch] $SkipFleetBootstrap,
    [switch] $CheckOnly
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$DesktopAppDir = Join-Path $RepoRoot "desktop_app"
$RendererDir = Join-Path $DesktopAppDir "renderer_client"
$RendererIndex = Join-Path $RendererDir "dist\index.html"
$RequirementsPath = Join-Path $RepoRoot "requirements.txt"
$CorePythonModules = @("fastapi", "uvicorn", "websockets", "dotenv", "pydantic")

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

function Invoke-BestEffort {
    param(
        [string] $Label,
        [scriptblock] $Command
    )

    Write-Step $Label
    try {
        & $Command
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "$Label exited with code $LASTEXITCODE. Continuing because this step is optional."
        }
    } catch {
        Write-Warning "$Label failed: $($_.Exception.Message). Continuing because this step is optional."
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

function Test-NodeModules {
    param([string] $PackageDir)
    return Test-Path (Join-Path $PackageDir "node_modules")
}

function Start-DesktopShell {
    $ElectronExecutable = if ($IsWindows -or $env:OS -eq "Windows_NT") {
        Join-Path $DesktopAppDir "node_modules\electron\dist\electron.exe"
    } else {
        Join-Path $DesktopAppDir "node_modules\electron\dist\electron"
    }
    if (-not (Test-Path -LiteralPath $ElectronExecutable)) {
        throw "Electron is not installed. Run npm run setup first."
    }

    $RuntimeHome = if ("$env:EMPLOAI_HOME".Trim()) {
        "$env:EMPLOAI_HOME".Trim()
    } elseif ("$env:LOCALAPPDATA".Trim()) {
        Join-Path $env:LOCALAPPDATA "EmploAI"
    } else {
        Join-Path $HOME ".emploai"
    }
    $DesktopPidPath = Join-Path $RuntimeHome "desktop_shell.pid.json"
    if (Test-Path -LiteralPath $DesktopPidPath) {
        try {
            $RecordedPid = [int]((Get-Content -Raw -LiteralPath $DesktopPidPath | ConvertFrom-Json).pid)
            $RecordedProcess = Get-Process -Id $RecordedPid -ErrorAction SilentlyContinue
            if (
                $null -ne $RecordedProcess `
                -and $RecordedProcess.Path `
                -and [System.StringComparer]::OrdinalIgnoreCase.Equals(
                    [System.IO.Path]::GetFullPath($RecordedProcess.Path),
                    [System.IO.Path]::GetFullPath($ElectronExecutable)
                )
            ) {
                Write-Step "Desktop shell is already running (PID $RecordedPid)"
                return
            }
        } catch {
            # A stale advisory PID record must not block a clean launch.
        }
    }

    $LogDirectory = Join-Path $RuntimeHome "logs"
    New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
    $StandardOutputLog = Join-Path $LogDirectory "desktop_shell_stdout.log"
    $StandardErrorLog = Join-Path $LogDirectory "desktop_shell_stderr.log"
    $process = Start-Process `
        -FilePath $ElectronExecutable `
        -ArgumentList "." `
        -WorkingDirectory $DesktopAppDir `
        -RedirectStandardOutput $StandardOutputLog `
        -RedirectStandardError $StandardErrorLog `
        -PassThru

    $Deadline = [DateTime]::UtcNow.AddSeconds(12)
    while ([DateTime]::UtcNow -lt $Deadline) {
        $process.Refresh()
        if ($process.HasExited) {
            break
        }
        if (Test-Path -LiteralPath $DesktopPidPath) {
            try {
                $LivePid = [int]((Get-Content -Raw -LiteralPath $DesktopPidPath | ConvertFrom-Json).pid)
                if ($LivePid -eq $process.Id) {
                    Write-Step "Desktop shell started (PID $($process.Id))"
                    return
                }
            } catch {
                # Electron is still starting; retry until the bounded deadline.
            }
        }
        Start-Sleep -Milliseconds 250
    }

    $FailureDetail = ""
    if (Test-Path -LiteralPath $StandardErrorLog) {
        $FailureDetail = (Get-Content -LiteralPath $StandardErrorLog -Tail 20) -join " "
    }
    if ($FailureDetail) {
        throw "The EmploAI desktop process did not become ready: $FailureDetail"
    }
    throw "The EmploAI desktop process did not become ready. See $StandardErrorLog."
}

function Get-PythonRuntime {
    $configured = "$env:EMPLOAI_DESKTOP_PYTHON".Trim()
    if ($configured) {
        return $configured
    }

    foreach ($candidate in @("python", "py", "python3")) {
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

function Get-PythonVersionLabel {
    if (-not (Get-PythonRuntime)) {
        return "missing"
    }

    try {
        $version = Invoke-PythonRuntime @("-c", "import sys; print(f'Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')") 2>$null
        if ($LASTEXITCODE -eq 0 -and "$version".Trim()) {
            return "$version".Trim()
        }
    } catch {
    }

    return "found"
}

function Get-MissingCorePythonModules {
    if (-not (Get-PythonRuntime)) {
        return $CorePythonModules
    }

    $missing = @()
    foreach ($module in $CorePythonModules) {
        $probe = "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$module') else 1)"
        try {
            Invoke-PythonRuntime @("-c", $probe) *> $null
            if ($LASTEXITCODE -ne 0) {
                $missing += $module
            }
        } catch {
            $missing += $module
        }
    }
    return $missing
}

function Assert-PythonRuntime {
    if (-not (Get-PythonRuntime)) {
        throw "Python was not found. Install Python 3, add it to PATH, or set EMPLOAI_DESKTOP_PYTHON to the Python executable."
    }
}

function Ensure-CorePythonDependencies {
    $missing = @(Get-MissingCorePythonModules)
    if ($missing.Count -eq 0) {
        return
    }

    if ($NoInstall) {
        throw "Missing Python packages: $($missing -join ', '). Run 'npm run setup' or omit -NoInstall so startup can install them."
    }

    if (-not (Test-Path $RequirementsPath)) {
        throw "Missing Python packages: $($missing -join ', '), and requirements.txt was not found at $RequirementsPath."
    }

    Invoke-Checked "Installing Python runtime dependencies" {
        Invoke-PythonRuntime @("-m", "pip", "install", "-r", $RequirementsPath)
    }

    $remaining = @(Get-MissingCorePythonModules)
    if ($remaining.Count -gt 0) {
        throw "Missing Python packages after install: $($remaining -join ', '). Check the pip output above, then run 'npm run setup'."
    }
}

Assert-Command "npm"
$PythonRuntime = Get-PythonRuntime
$PythonVersion = Get-PythonVersionLabel
$MissingPythonModules = @(Get-MissingCorePythonModules)

if ($CheckOnly) {
    Write-Step "Repository: $RepoRoot"
    Write-Step "Python runtime: $(if ($PythonRuntime) { "$PythonRuntime ($PythonVersion)" } else { 'missing' })"
    Write-Step "Core Python packages: $(if ($MissingPythonModules.Count -eq 0) { 'present' } else { "missing $($MissingPythonModules -join ', ')" })"
    Write-Step "Desktop shell dependencies: $(if (Test-NodeModules $DesktopAppDir) { 'present' } else { 'missing' })"
    Write-Step "Desktop renderer dependencies: $(if (Test-NodeModules $RendererDir) { 'present' } else { 'missing' })"
    Write-Step "Renderer build: $(if (Test-Path $RendererIndex) { 'present' } else { 'missing' })"
    if ($MissingPythonModules.Count -gt 0) {
        Write-Step "Run 'npm start' to install missing Python dependencies, or 'npm run setup' for a full setup pass."
    }
    Write-Step "Check complete. Run 'npm start' to launch the app."
    exit 0
}

Assert-PythonRuntime
Ensure-CorePythonDependencies

if (-not $NoInstall) {
    if (-not (Test-NodeModules $DesktopAppDir)) {
        Invoke-Checked "Installing desktop shell dependencies" {
            Invoke-NpmInDirectory $DesktopAppDir @("ci")
        }
    }

    if (-not (Test-NodeModules $RendererDir)) {
        Invoke-Checked "Installing desktop renderer dependencies" {
            Invoke-NpmInDirectory $RendererDir @("ci")
        }
    }
}

if ($Fast -and (Test-Path $RendererIndex)) {
    Write-Step "Using existing renderer build"
} else {
    Invoke-Checked "Building desktop renderer" {
        Invoke-NpmInDirectory $RendererDir @("run", "export:web")
    }
}

$skipFleet = $SkipFleetBootstrap -or $Fast -or $env:EMPLOAI_SKIP_YGGDRASIL_BOOTSTRAP -eq "1"
if ($skipFleet) {
    Write-Step "Skipping Fleet Yggdrasil bootstrap"
} else {
    Invoke-BestEffort "Bootstrapping Fleet Yggdrasil transport" {
        Invoke-NpmInDirectory $DesktopAppDir @("run", "fleet:yggdrasil:bootstrap", "--", "--best-effort")
    }
}

Write-Step "Launching EmploAI desktop"
Start-DesktopShell
