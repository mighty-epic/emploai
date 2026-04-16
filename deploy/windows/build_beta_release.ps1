param(
    [switch]$IncludeZip
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$specPath = Join-Path $PSScriptRoot "EmploAI.spec"
$wxsPath = Join-Path $PSScriptRoot "EmploAI.wxs"
$licenseRtfPath = Join-Path $PSScriptRoot "InstallerLicense.rtf"
$releaseInfoPath = Join-Path $PSScriptRoot "release_info.json"
$distDir = Join-Path $repoRoot "dist"
$releaseExe = Join-Path $distDir "EmploAI.exe"
$releaseMsi = Join-Path $distDir "EmploAI.msi"
$zipPath = Join-Path $distDir "EmploAI-windows-beta.zip"
$vendorDir = Join-Path $repoRoot "build\\windows-vendor"
$tesseractBundleDir = Join-Path $vendorDir "tesseract"
$toolsDir = Join-Path $repoRoot ".tools"
$wixDir = Join-Path $toolsDir "wix314"
$wixZip = Join-Path $toolsDir "wix314-binaries.zip"
$wixUrl = "https://github.com/wixtoolset/wix3/releases/download/wix3141rtm/wix314-binaries.zip"

function Ensure-WixToolset {
    $candle = Join-Path $wixDir "candle.exe"
    $light = Join-Path $wixDir "light.exe"
    if ((Test-Path $candle) -and (Test-Path $light)) {
        return
    }

    New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null
    Invoke-WebRequest -Uri $wixUrl -OutFile $wixZip
    if (Test-Path $wixDir) {
        Remove-Item -Recurse -Force $wixDir
    }
    Expand-Archive -Path $wixZip -DestinationPath $wixDir -Force
}

function Resolve-TesseractRoot {
    if ($env:EMPLOAI_TESSERACT_ROOT) {
        $candidate = $env:EMPLOAI_TESSERACT_ROOT
        if (Test-Path (Join-Path $candidate "tesseract.exe")) {
            return (Resolve-Path $candidate).Path
        }
        throw "EMPLOAI_TESSERACT_ROOT is set but does not contain tesseract.exe: $candidate"
    }

    $command = Get-Command tesseract -ErrorAction SilentlyContinue
    if ($command -and $command.Source) {
        return Split-Path -Parent $command.Source
    }

    $defaults = @(
        "C:\\Program Files\\Tesseract-OCR",
        "C:\\Program Files (x86)\\Tesseract-OCR"
    )
    foreach ($candidate in $defaults) {
        if (Test-Path (Join-Path $candidate "tesseract.exe")) {
            return $candidate
        }
    }

    throw "Tesseract OCR was not found on the build machine. Install Tesseract or set EMPLOAI_TESSERACT_ROOT before building the Windows release."
}

function Prepare-TesseractBundle {
    $sourceRoot = Resolve-TesseractRoot
    $tessdataSource = Join-Path $sourceRoot "tessdata"

    if (-not (Test-Path $tessdataSource)) {
        throw "Tesseract tessdata directory not found: $tessdataSource"
    }

    if (Test-Path $tesseractBundleDir) {
        Remove-Item -Recurse -Force $tesseractBundleDir
    }

    New-Item -ItemType Directory -Force -Path $tesseractBundleDir | Out-Null
    Copy-Item (Join-Path $sourceRoot "tesseract.exe") $tesseractBundleDir -Force
    Get-ChildItem $sourceRoot -Filter *.dll | Copy-Item -Destination $tesseractBundleDir -Force
    Copy-Item $tessdataSource (Join-Path $tesseractBundleDir "tessdata") -Recurse -Force

    $env:EMPLOAI_TESSERACT_BUNDLE = $tesseractBundleDir
    Write-Host "Bundling Tesseract OCR from: $sourceRoot"
}

Push-Location $repoRoot
try {
    python -m pip install "setuptools<81" "pyinstaller>=6.14,<7" | Out-Host
    $releaseInfo = Get-Content $releaseInfoPath | ConvertFrom-Json
    Prepare-TesseractBundle

    if (Test-Path $releaseExe) {
        Remove-Item -Force $releaseExe
    }
    if (Test-Path $releaseMsi) {
        Remove-Item -Force $releaseMsi
    }
    if ((Test-Path $zipPath) -and -not $IncludeZip) {
        Remove-Item -Force $zipPath
    }
    elseif (Test-Path $zipPath) {
        Remove-Item -Force $zipPath
    }

    python -m PyInstaller --noconfirm --clean $specPath

    if (-not (Test-Path $releaseExe)) {
        throw "Expected build output not found: $releaseExe"
    }

    Ensure-WixToolset
    $wixObj = Join-Path $distDir "EmploAI.wixobj"
    $candle = Join-Path $wixDir "candle.exe"
    $light = Join-Path $wixDir "light.exe"
    & $candle -nologo "-dProductVersion=$($releaseInfo.msi_version)" "-dReleaseExe=$releaseExe" "-dLicenseRtf=$licenseRtfPath" -out $wixObj $wxsPath
    & $light -nologo -ext WixUIExtension -ext WixUtilExtension -out $releaseMsi $wixObj

    if (-not (Test-Path $releaseMsi)) {
        throw "Expected MSI output not found: $releaseMsi"
    }

    if ($IncludeZip) {
        Compress-Archive -Path $releaseExe -DestinationPath $zipPath
    }

    Write-Host ""
    Write-Host "Windows beta release created:"
    Write-Host "  EXE: $releaseExe"
    Write-Host "  MSI: $releaseMsi"
    if ($IncludeZip) {
        Write-Host "  Zip: $zipPath"
    }
    Write-Host ""
    Write-Host "Upload EmploAI.msi to the GitHub release page as the primary installer asset."
    Write-Host "Upload EmploAI.exe as the portable fallback asset."
    if ($IncludeZip) {
        Write-Host "Upload EmploAI-windows-beta.zip as the extra fallback asset."
    }
}
finally {
    Pop-Location
}
