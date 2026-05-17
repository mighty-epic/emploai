param(
    [switch]$IncludeZip,
    [switch]$BundleEnglishVoicePack
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$backendSpecPath = Join-Path $PSScriptRoot "EmploAIBackend.spec"
$wxsPath = Join-Path $PSScriptRoot "EmploAI.wxs"
$licenseRtfPath = Join-Path $PSScriptRoot "InstallerLicense.rtf"
$releaseInfoPath = Join-Path $PSScriptRoot "release_info.json"
$distDir = Join-Path $repoRoot "dist"
$desktopBuildDir = Join-Path $distDir "desktop"
$releaseDir = Join-Path $desktopBuildDir "EmploAI-win32-x64"
$releaseAppExe = Join-Path $releaseDir "EmploAI.exe"
$backendDistDir = Join-Path $distDir "EmploAIBackend"
$backendExe = Join-Path $backendDistDir "EmploAIBackend.exe"
$releaseMsi = Join-Path $distDir "EmploAI.msi"
$portableZip = Join-Path $distDir "EmploAI-portable.zip"
$harvestWxsPath = Join-Path $distDir "EmploAI.ReleaseFiles.wxs"
$vendorDir = Join-Path $repoRoot "build\\windows-vendor"
$tesseractBundleDir = Join-Path $vendorDir "tesseract"
$requiredTesseractVersion = if ($env:EMPLOAI_REQUIRED_TESSERACT_VERSION) { $env:EMPLOAI_REQUIRED_TESSERACT_VERSION } else { "5.5.2" }
$projectTesseractRoot = Join-Path $repoRoot ".tools\\tesseract-$requiredTesseractVersion"
$whisperBundleDir = Join-Path $vendorDir "whisper"
$whisperBinaryFlavor = if ($env:EMPLOAI_WHISPER_BINARY_FLAVOR) { $env:EMPLOAI_WHISPER_BINARY_FLAVOR } else { "blas" }
$whisperReleaseTag = if ($env:EMPLOAI_WHISPER_RELEASE_TAG) { $env:EMPLOAI_WHISPER_RELEASE_TAG } else { "v1.8.4" }
$whisperModels = @("base.en-q5_1", "tiny.en")
$toolsDir = Join-Path $repoRoot ".tools"
$wixDir = Join-Path $toolsDir "wix314"
$wixZip = Join-Path $toolsDir "wix314-binaries.zip"
$wixUrl = "https://github.com/wixtoolset/wix3/releases/download/wix3141rtm/wix314-binaries.zip"
$desktopAppDir = Join-Path $repoRoot "desktop_app"
$desktopRendererDir = Join-Path $desktopAppDir "renderer"
$desktopBackendDir = Join-Path $desktopAppDir "backend"
$clientDistDir = Join-Path $repoRoot "mobile_app\\client\\dist"

function Ensure-WixToolset {
    $candle = Join-Path $wixDir "candle.exe"
    $light = Join-Path $wixDir "light.exe"
    $heat = Join-Path $wixDir "heat.exe"
    if ((Test-Path $candle) -and (Test-Path $light) -and (Test-Path $heat)) {
        return
    }

    New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null
    Invoke-WebRequest -Uri $wixUrl -OutFile $wixZip
    if (Test-Path $wixDir) {
        Remove-Item -Recurse -Force $wixDir
    }
    Expand-Archive -Path $wixZip -DestinationPath $wixDir -Force
}

function Assert-LastExitCode {
    param(
        [string]$CommandName
    )

    if ($LASTEXITCODE -ne 0) {
        throw "$CommandName failed with exit code $LASTEXITCODE"
    }
}

function New-StableGuidFromText {
    param(
        [string]$Text
    )

    $md5 = [System.Security.Cryptography.MD5]::Create()
    try {
        $hash = $md5.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Text))
    }
    finally {
        $md5.Dispose()
    }

    $hex = ($hash | ForEach-Object { $_.ToString("x2") }) -join ""
    return (
        "{0}-{1}-{2}-{3}-{4}" -f
        $hex.Substring(0, 8),
        $hex.Substring(8, 4),
        $hex.Substring(12, 4),
        $hex.Substring(16, 4),
        $hex.Substring(20, 12)
    ).ToUpperInvariant()
}

function Convert-HarvestedWixToPerUserKeyPaths {
    param(
        [string]$HarvestPath
    )

    [xml]$xml = Get-Content $HarvestPath
    $namespaceUri = $xml.DocumentElement.NamespaceURI

    $componentGroup = $null
    foreach ($candidateGroup in $xml.GetElementsByTagName("ComponentGroup", $namespaceUri)) {
        if ($candidateGroup.GetAttribute("Id") -eq "EmploAIReleaseFiles") {
            $componentGroup = $candidateGroup
            break
        }
    }
    if (-not $componentGroup) {
        throw "Expected ComponentGroup 'EmploAIReleaseFiles' in harvested WiX fragment."
    }

    foreach ($component in $xml.GetElementsByTagName("Component", $namespaceUri)) {
        $fileNodes = @(
            $component.ChildNodes | Where-Object {
                $_.LocalName -eq "File" -and $_.GetAttribute("KeyPath") -eq "yes"
            }
        )
        if (-not $fileNodes.Count) {
            continue
        }

        foreach ($fileNode in $fileNodes) {
            $fileNode.SetAttribute("KeyPath", "no")
        }

        $existingRegistryKeyPath = @(
            $component.ChildNodes | Where-Object {
                $_.LocalName -eq "RegistryValue" -and $_.GetAttribute("KeyPath") -eq "yes"
            }
        )
        if ($existingRegistryKeyPath.Count) {
            continue
        }

        $registryNode = $xml.CreateElement("RegistryValue", $namespaceUri)
        $registryNode.SetAttribute("Root", "HKCU")
        $registryNode.SetAttribute("Key", "Software\MightyEpic\EmploAI\Components")
        $registryNode.SetAttribute("Name", $component.GetAttribute("Id"))
        $registryNode.SetAttribute("Type", "integer")
        $registryNode.SetAttribute("Value", "1")
        $registryNode.SetAttribute("KeyPath", "yes")

        $firstRegistryValue = $component.ChildNodes | Where-Object { $_.LocalName -eq "RegistryValue" } | Select-Object -First 1
        if ($firstRegistryValue) {
            [void]$component.InsertBefore($registryNode, $firstRegistryValue)
        }
        else {
            [void]$component.AppendChild($registryNode)
        }
    }

    foreach ($directory in $xml.GetElementsByTagName("Directory", $namespaceUri)) {
        $directoryId = $directory.GetAttribute("Id")
        if (-not $directoryId -or $directoryId -eq "INSTALLDIR") {
            continue
        }

        $componentWithCleanup = (
            $directory.ChildNodes | Where-Object {
                $_.LocalName -eq "Component" -and @(
                    $_.ChildNodes | Where-Object { $_.LocalName -eq "RemoveFolder" }
                ).Count
            } | Select-Object -First 1
        )
        if ($componentWithCleanup) {
            continue
        }

        $component = $directory.ChildNodes | Where-Object { $_.LocalName -eq "Component" } | Select-Object -First 1
        $createdCleanupComponent = $false
        if (-not $component) {
            $componentId = "cmpCleanup$directoryId"
            $component = $xml.CreateElement("Component", $namespaceUri)
            $component.SetAttribute("Id", $componentId)
            $component.SetAttribute("Guid", "{0}" -f ("{" + (New-StableGuidFromText $componentId) + "}"))

            $registryNode = $xml.CreateElement("RegistryValue", $namespaceUri)
            $registryNode.SetAttribute("Root", "HKCU")
            $registryNode.SetAttribute("Key", "Software\MightyEpic\EmploAI\Directories")
            $registryNode.SetAttribute("Name", $directoryId)
            $registryNode.SetAttribute("Type", "integer")
            $registryNode.SetAttribute("Value", "1")
            $registryNode.SetAttribute("KeyPath", "yes")
            [void]$component.AppendChild($registryNode)
            [void]$directory.AppendChild($component)

            $componentRef = $xml.CreateElement("ComponentRef", $namespaceUri)
            $componentRef.SetAttribute("Id", $componentId)
            [void]$componentGroup.AppendChild($componentRef)
            $createdCleanupComponent = $true
        }

        $removeFolderNode = $xml.CreateElement("RemoveFolder", $namespaceUri)
        $removeFolderNode.SetAttribute("Id", "rm$directoryId")
        $removeFolderNode.SetAttribute("On", "uninstall")

        $firstRegistryValue = $component.ChildNodes | Where-Object { $_.LocalName -eq "RegistryValue" } | Select-Object -First 1
        if ($firstRegistryValue) {
            [void]$component.InsertBefore($removeFolderNode, $firstRegistryValue)
        }
        else {
            [void]$component.AppendChild($removeFolderNode)
        }

        if (-not $createdCleanupComponent) {
            continue
        }
    }

    $settings = [System.Xml.XmlWriterSettings]::new()
    $settings.Indent = $true
    $settings.Encoding = [System.Text.UTF8Encoding]::new($false)
    $writer = [System.Xml.XmlWriter]::Create($HarvestPath, $settings)
    try {
        $xml.Save($writer)
    }
    finally {
        $writer.Dispose()
    }
}

function Resolve-TesseractRoot {
    if ($env:EMPLOAI_TESSERACT_ROOT) {
        $candidate = $env:EMPLOAI_TESSERACT_ROOT
        if (Test-Path (Join-Path $candidate "tesseract.exe")) {
            return (Resolve-Path $candidate).Path
        }
        throw "EMPLOAI_TESSERACT_ROOT is set but does not contain tesseract.exe: $candidate"
    }

    if (Test-Path (Join-Path $projectTesseractRoot "tesseract.exe")) {
        return (Resolve-Path $projectTesseractRoot).Path
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

function Assert-TesseractVersion {
    param(
        [string]$SourceRoot
    )

    $tesseractExe = Join-Path $SourceRoot "tesseract.exe"
    $versionLine = (& $tesseractExe --version 2>&1 | Select-Object -First 1)
    if (-not ($versionLine -match [regex]::Escape($requiredTesseractVersion))) {
        throw "Refusing to build with Tesseract '$versionLine'. Expected version $requiredTesseractVersion. Set EMPLOAI_TESSERACT_ROOT to a matching bundle or place one at $projectTesseractRoot."
    }
}

function Prepare-TesseractBundle {
    $sourceRoot = Resolve-TesseractRoot
    Assert-TesseractVersion $sourceRoot
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

function Resolve-WhisperAssetDirName {
    param(
        [string]$Flavor
    )

    switch ($Flavor) {
        "plain" { return "whisper-bin-x64" }
        "blas" { return "whisper-blas-bin-x64" }
        "cublas-11.8" { return "whisper-cublas-11.8.0-bin-x64" }
        "cublas-12.4" { return "whisper-cublas-12.4.0-bin-x64" }
        default { throw "Unsupported whisper.cpp binary flavor: $Flavor" }
    }
}

function Prepare-WhisperBundle {
    $modelCsv = $whisperModels -join ","
    python -c "from mobile_app.backend.whisper_cpp_runtime import ensure_prebuilt_whisper_cpp, ensure_ggml_model; ensure_prebuilt_whisper_cpp(release_tag='$whisperReleaseTag', flavor='$whisperBinaryFlavor'); [ensure_ggml_model(model) for model in '$modelCsv'.split(',') if model]"
    Assert-LastExitCode "prepare whisper.cpp runtime assets"

    $assetDirName = Resolve-WhisperAssetDirName $whisperBinaryFlavor
    $sourceBinaryDir = Join-Path $repoRoot ".tools\\$assetDirName"
    $sourceModelsDir = Join-Path $repoRoot ".tools\\whisper_cpp_models"

    if (-not (Test-Path (Join-Path $sourceBinaryDir "Release\\whisper-cli.exe"))) {
        throw "whisper-cli.exe was not found after preparing whisper.cpp assets: $sourceBinaryDir"
    }

    if (Test-Path $whisperBundleDir) {
        Remove-Item -Recurse -Force $whisperBundleDir
    }

    New-Item -ItemType Directory -Force -Path $whisperBundleDir | Out-Null
    Copy-Item $sourceBinaryDir (Join-Path $whisperBundleDir $assetDirName) -Recurse -Force

    $modelBundleDir = Join-Path $whisperBundleDir "models"
    New-Item -ItemType Directory -Force -Path $modelBundleDir | Out-Null
    foreach ($model in $whisperModels) {
        $modelPath = Join-Path $sourceModelsDir "ggml-$model.bin"
        if (-not (Test-Path $modelPath)) {
            throw "Expected Whisper model was not found after prepare: $modelPath"
        }
        Copy-Item $modelPath $modelBundleDir -Force
    }

    $env:EMPLOAI_WHISPER_BUNDLE = $whisperBundleDir
    Write-Host "Bundling local Whisper from: $sourceBinaryDir"
    Write-Host "Bundling local Whisper models: $($whisperModels -join ', ')"
}

function Prepare-DesktopPackageAssets {
    if (Test-Path $desktopRendererDir) {
        Remove-Item -Recurse -Force $desktopRendererDir
    }
    if (Test-Path $desktopBackendDir) {
        Remove-Item -Recurse -Force $desktopBackendDir
    }

    New-Item -ItemType Directory -Force -Path $desktopRendererDir | Out-Null
    New-Item -ItemType Directory -Force -Path $desktopBackendDir | Out-Null

    Copy-Item (Join-Path $clientDistDir "*") $desktopRendererDir -Recurse -Force
    Copy-Item (Join-Path $backendDistDir "*") $desktopBackendDir -Recurse -Force
}

function Assert-BackendBundleShape {
    if (-not (Test-Path $backendExe)) {
        throw "Expected backend build output not found: $backendExe"
    }

    $internalDir = Join-Path $backendDistDir "_internal"
    if (-not (Test-Path $internalDir)) {
        throw "Expected a PyInstaller onedir backend bundle with an _internal directory. A single self-extracting backend EXE makes desktop startup and helper calls too slow."
    }

    $internalFileCount = @(Get-ChildItem $internalDir -Recurse -File -ErrorAction SilentlyContinue).Count
    if ($internalFileCount -lt 1) {
        throw "Backend _internal directory is empty: $internalDir"
    }
}

Push-Location $repoRoot
try {
    python -m pip install "setuptools<81" "pyinstaller>=6.14,<7" | Out-Host
    Assert-LastExitCode "python -m pip install"
    python -m pip install -r requirements.txt | Out-Host
    Assert-LastExitCode "python -m pip install -r requirements.txt"

    $releaseInfo = Get-Content $releaseInfoPath | ConvertFrom-Json
    Prepare-TesseractBundle
    if ($BundleEnglishVoicePack) {
        Prepare-WhisperBundle
    } else {
        Remove-Item Env:EMPLOAI_WHISPER_BUNDLE -ErrorAction SilentlyContinue
        Write-Host "Skipping bundled English voice assets. Voice packs will download on first launch based on installer/app selection."
    }

    npm --prefix mobile_app/client install | Out-Host
    Assert-LastExitCode "npm --prefix mobile_app/client install"
    npm --prefix mobile_app/client run export:web | Out-Host
    Assert-LastExitCode "npm --prefix mobile_app/client run export:web"
    npm --prefix desktop_app install | Out-Host
    Assert-LastExitCode "npm --prefix desktop_app install"

    if (Test-Path $backendDistDir) {
        Remove-Item -Recurse -Force $backendDistDir
    }
    $legacyBackendExe = Join-Path $distDir "EmploAIBackend.exe"
    if (Test-Path $legacyBackendExe) {
        Remove-Item -Force $legacyBackendExe
    }
    if (Test-Path $releaseMsi) {
        Remove-Item -Force $releaseMsi
    }
    if (Test-Path $portableZip) {
        Remove-Item -Force $portableZip
    }
    if (Test-Path $desktopBuildDir) {
        Remove-Item -Recurse -Force $desktopBuildDir
    }
    if (Test-Path $harvestWxsPath) {
        Remove-Item -Force $harvestWxsPath
    }

    python -m PyInstaller --noconfirm --clean $backendSpecPath
    Assert-LastExitCode "python -m PyInstaller"

    Assert-BackendBundleShape
    if (-not (Test-Path $clientDistDir)) {
        throw "Expected renderer export output not found: $clientDistDir"
    }

    Prepare-DesktopPackageAssets

    npx --prefix $desktopAppDir electron-packager $desktopAppDir EmploAI --platform=win32 --arch=x64 --out $desktopBuildDir --overwrite --prune=true --app-version $releaseInfo.version | Out-Host
    Assert-LastExitCode "npx electron-packager"

    if (-not (Test-Path $releaseAppExe)) {
        throw "Expected desktop app output not found: $releaseAppExe"
    }

    Ensure-WixToolset
    $heat = Join-Path $wixDir "heat.exe"
    $candle = Join-Path $wixDir "candle.exe"
    $light = Join-Path $wixDir "light.exe"

    & $heat dir $releaseDir -nologo -gg -scom -sfrag -srd -dr INSTALLDIR -cg EmploAIReleaseFiles -var var.ReleaseDir -out $harvestWxsPath
    Assert-LastExitCode "heat.exe"
    Convert-HarvestedWixToPerUserKeyPaths $harvestWxsPath

    $wixMainObj = Join-Path $distDir "EmploAI.wixobj"
    $wixHarvestObj = Join-Path $distDir "EmploAI.ReleaseFiles.wixobj"
    & $candle -nologo "-dProductVersion=$($releaseInfo.msi_version)" "-dReleaseDir=$releaseDir" "-dLicenseRtf=$licenseRtfPath" -out $wixMainObj $wxsPath
    Assert-LastExitCode "candle.exe (main)"
    & $candle -nologo "-dProductVersion=$($releaseInfo.msi_version)" "-dReleaseDir=$releaseDir" -out $wixHarvestObj $harvestWxsPath
    Assert-LastExitCode "candle.exe (harvest)"
    & $light -nologo -sval -ext WixUIExtension -ext WixUtilExtension -out $releaseMsi $wixMainObj $wixHarvestObj
    Assert-LastExitCode "light.exe"

    if (-not (Test-Path $releaseMsi)) {
        throw "Expected MSI output not found: $releaseMsi"
    }

    if ($IncludeZip) {
        Compress-Archive -Path $releaseDir -DestinationPath $portableZip
    }

    Write-Host ""
    Write-Host "Windows desktop release created:"
    Write-Host "  MSI: $releaseMsi"
    Write-Host "  App EXE: $releaseAppExe"
    Write-Host "  Backend bundle: $backendDistDir"
    if ($IncludeZip) {
        Write-Host "  Portable Zip: $portableZip"
    }
    Write-Host ""
    Write-Host "Upload EmploAI.msi to the GitHub release page as the primary installer asset."
    if ($IncludeZip) {
        Write-Host "Upload EmploAI-portable.zip as the optional portable fallback asset."
    }
}
finally {
    Pop-Location
}
