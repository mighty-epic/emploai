param(
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path -LiteralPath (Join-Path $scriptDir "..")
$releaseInfoPath = Join-Path $repoRoot "deploy\windows\release_info.json"
$mobilePackagePath = Join-Path $repoRoot "mobile_app\client\package.json"

$releaseInfo = $null
if (Test-Path -LiteralPath $releaseInfoPath) {
    $releaseInfo = Get-Content -LiteralPath $releaseInfoPath -Raw | ConvertFrom-Json
}

$mobilePackage = $null
if (Test-Path -LiteralPath $mobilePackagePath) {
    $mobilePackage = Get-Content -LiteralPath $mobilePackagePath -Raw | ConvertFrom-Json
}

$distDir = Join-Path $repoRoot "dist"
$mobileBuildsDir = Join-Path $repoRoot "mobile_app\client\builds"
$downloadsDir = Join-Path $env:USERPROFILE "Downloads"
$desktopDir = Join-Path $env:USERPROFILE "Desktop"
$publishSmokeDir = Join-Path $env:TEMP "emploai-publish-smoke"
$publishTempDir = Join-Path $env:TEMP "emploai-desktop-release-publish"

$packageDirs = @(
    $distDir,
    $mobileBuildsDir,
    $downloadsDir,
    $desktopDir,
    $publishSmokeDir,
    $publishTempDir
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

function Get-PackageFiles {
    param(
        [string[]]$Extensions
    )

    $files = @()
    foreach ($dir in $packageDirs) {
        $recurse = ($dir -ieq $publishSmokeDir) -or ($dir -ieq $publishTempDir)
        $items = Get-ChildItem -LiteralPath $dir -File -Recurse:$recurse -ErrorAction SilentlyContinue
        $files += $items | Where-Object {
            $Extensions -contains $_.Extension.ToLowerInvariant() -and
            ($_.Name -match "(?i)(emploai|kraitos)" -or $_.FullName -match "(?i)(emploai|kraitos)")
        }
    }
    return @($files | Sort-Object FullName -Unique)
}

function Remove-StalePackage {
    param(
        [System.IO.FileInfo]$File,
        [string]$Reason
    )

    if ($WhatIf) {
        Write-Host "Would remove $($File.FullName) ($Reason)"
        return
    }
    Remove-Item -LiteralPath $File.FullName -Force
    Write-Host "Removed $($File.FullName) ($Reason)"
}

$desktopPackages = Get-PackageFiles -Extensions @(".msi")
$desktopKeep = $null
if ($releaseInfo -and $releaseInfo.msi_version) {
    $expectedName = "EmploAI-$($releaseInfo.msi_version).msi"
    $desktopKeep = $desktopPackages |
        Where-Object { $_.Name -ieq $expectedName -and $_.DirectoryName -ieq $distDir } |
        Select-Object -First 1
}
if (-not $desktopKeep) {
    $desktopKeep = $desktopPackages |
        Sort-Object @{ Expression = { $_.DirectoryName -ieq $distDir }; Descending = $true }, LastWriteTime -Descending |
        Select-Object -First 1
}

foreach ($file in $desktopPackages) {
    if ($desktopKeep -and $file.FullName -ieq $desktopKeep.FullName) {
        Write-Host "Keeping desktop package $($file.FullName)"
        continue
    }
    Remove-StalePackage -File $file -Reason "stale desktop installer"
}

$mobilePackages = Get-PackageFiles -Extensions @(".apk", ".aab")
$mobileKeepPaths = @{}
foreach ($extension in @(".apk", ".aab")) {
    $packagesForType = @($mobilePackages | Where-Object { $_.Extension -ieq $extension })
    if ($packagesForType.Count -lt 1) {
        continue
    }

    $mobileKeep = $null
    if ($mobilePackage -and $mobilePackage.version) {
        $mobileKeep = $packagesForType |
            Where-Object { $_.Name -like "*$($mobilePackage.version)*" -and $_.DirectoryName -ieq $mobileBuildsDir } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
    }
    if (-not $mobileKeep) {
        $mobileKeep = $packagesForType |
            Sort-Object @{ Expression = { $_.DirectoryName -ieq $mobileBuildsDir }; Descending = $true }, LastWriteTime -Descending |
            Select-Object -First 1
    }
    if ($mobileKeep) {
        $mobileKeepPaths[$mobileKeep.FullName.ToLowerInvariant()] = $true
    }
}

foreach ($file in $mobilePackages) {
    if ($mobileKeepPaths.ContainsKey($file.FullName.ToLowerInvariant())) {
        Write-Host "Keeping mobile package $($file.FullName)"
        continue
    }
    Remove-StalePackage -File $file -Reason "stale mobile package"
}
