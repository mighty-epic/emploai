$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$specPath = Join-Path $PSScriptRoot "EmploAI.spec"
$distDir = Join-Path $repoRoot "dist"
$releaseExe = Join-Path $distDir "EmploAI.exe"
$zipPath = Join-Path $distDir "EmploAI-windows-beta.zip"

Push-Location $repoRoot
try {
    python -m pip install "setuptools<81" "pyinstaller>=6.14,<7" | Out-Host

    if (Test-Path $releaseExe) {
        Remove-Item -Force $releaseExe
    }
    if (Test-Path $zipPath) {
        Remove-Item -Force $zipPath
    }

    python -m PyInstaller --noconfirm --clean $specPath

    if (-not (Test-Path $releaseExe)) {
        throw "Expected build output not found: $releaseExe"
    }

    Compress-Archive -Path $releaseExe -DestinationPath $zipPath

    Write-Host ""
    Write-Host "Windows beta release created:"
    Write-Host "  EXE: $releaseExe"
    Write-Host "  Zip: $zipPath"
    Write-Host ""
    Write-Host "Upload EmploAI.exe to the GitHub release page if you want a single direct download."
    Write-Host "Upload EmploAI-windows-beta.zip as the fallback asset."
}
finally {
    Pop-Location
}
