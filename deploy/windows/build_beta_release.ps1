$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$specPath = Join-Path $PSScriptRoot "EmploAI.spec"
$distDir = Join-Path $repoRoot "dist"
$releaseDir = Join-Path $distDir "EmploAI"
$zipPath = Join-Path $distDir "EmploAI-windows-beta.zip"

Push-Location $repoRoot
try {
    python -m pip install pyinstaller | Out-Host

    if (Test-Path $releaseDir) {
        Remove-Item -Recurse -Force $releaseDir
    }
    if (Test-Path $zipPath) {
        Remove-Item -Force $zipPath
    }

    python -m PyInstaller --noconfirm --clean $specPath

    Compress-Archive -Path (Join-Path $releaseDir "*") -DestinationPath $zipPath

    Write-Host ""
    Write-Host "Windows beta release created:"
    Write-Host "  Folder: $releaseDir"
    Write-Host "  Zip:    $zipPath"
    Write-Host ""
    Write-Host "Upload the zip to the GitHub release page. Testers can unzip it and run EmploAI.exe."
}
finally {
    Pop-Location
}
