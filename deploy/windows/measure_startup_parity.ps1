param(
    [string]$PackagedBackendPath = "",
    [string]$PythonLauncher = "py",
    [string]$PythonVersion = "-3.13"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $PackagedBackendPath) {
    $PackagedBackendPath = Join-Path $repoRoot "dist\EmploAIBackend\EmploAIBackend.exe"
}

function Invoke-JsonCommand {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    $output = & $FilePath @Arguments 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $FilePath $($Arguments -join ' ')"
    }
    return ($output | ConvertFrom-Json)
}

function Invoke-LocalBackendJson {
    param(
        [string[]]$Arguments
    )

    $output = & $PythonLauncher $PythonVersion -m deploy.windows.release_backend @Arguments 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Local backend command failed: $PythonLauncher $PythonVersion -m deploy.windows.release_backend $($Arguments -join ' ')"
    }
    return ($output | ConvertFrom-Json)
}

function Stop-Backends {
    try {
        [void](Invoke-LocalBackendJson -Arguments @("stop"))
    } catch {}
    if (Test-Path $PackagedBackendPath) {
        try {
            [void](Invoke-JsonCommand -FilePath $PackagedBackendPath -Arguments @("stop"))
        } catch {}
    }
    Start-Sleep -Milliseconds 500
}

if (-not (Test-Path $PackagedBackendPath)) {
    throw "Packaged backend not found: $PackagedBackendPath"
}

Stop-Backends
$localCold = Invoke-LocalBackendJson -Arguments @("bootstrap", "--launch-if-needed")
$localWarm = Invoke-LocalBackendJson -Arguments @("bootstrap", "--launch-if-needed")
Stop-Backends
$packagedCold = Invoke-JsonCommand -FilePath $PackagedBackendPath -Arguments @("bootstrap", "--launch-if-needed")
$packagedWarm = Invoke-JsonCommand -FilePath $PackagedBackendPath -Arguments @("bootstrap", "--launch-if-needed")
Stop-Backends

$localColdMs = [double]($localCold.startupTimings.total_ms)
$localWarmMs = [double]($localWarm.startupTimings.total_ms)
$packagedColdMs = [double]($packagedCold.startupTimings.total_ms)
$packagedWarmMs = [double]($packagedWarm.startupTimings.total_ms)
$coldToleranceMs = [Math]::Max($localColdMs * 0.25, 2000.0)
$warmToleranceMs = [Math]::Max($localWarmMs * 0.25, 2000.0)

$result = [pscustomobject]@{
    ok = (($packagedColdMs - $localColdMs) -le $coldToleranceMs) -and (($packagedWarmMs - $localWarmMs) -le $warmToleranceMs)
    local = [pscustomobject]@{
        cold_ms = $localColdMs
        warm_ms = $localWarmMs
    }
    packaged = [pscustomobject]@{
        cold_ms = $packagedColdMs
        warm_ms = $packagedWarmMs
    }
    tolerance = [pscustomobject]@{
        cold_ms = [Math]::Round($coldToleranceMs, 1)
        warm_ms = [Math]::Round($warmToleranceMs, 1)
    }
    delta = [pscustomobject]@{
        cold_ms = [Math]::Round($packagedColdMs - $localColdMs, 1)
        warm_ms = [Math]::Round($packagedWarmMs - $localWarmMs, 1)
    }
}

$result | ConvertTo-Json -Depth 5
