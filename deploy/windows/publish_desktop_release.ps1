[CmdletBinding()]
param(
    [ValidateSet("Kraitos", "GitHub", "Both", "Local")]
    [string]$Target = "Kraitos",

    [string]$ReleaseInfoPath = "",
    [string]$MsiPath = "",
    [string]$AssetUrl = "",
    [string]$ManifestUrl = "",
    [string]$Notes = "",
    [string]$ManifestOutPath = "",

    [string]$KraitosHost = $env:EMPLOAI_RELEASE_SSH_HOST,
    [string]$KraitosUser = $env:EMPLOAI_RELEASE_SSH_USER,
    [int]$KraitosPort = 22,
    [string]$KraitosSshConfigHost = $(if ($env:EMPLOAI_RELEASE_SSH_CONFIG_HOST) { $env:EMPLOAI_RELEASE_SSH_CONFIG_HOST } else { "kraitos-vps" }),
    [string]$KraitosRemoteDataDir = "",
    [string]$SshKeyPath = $env:EMPLOAI_RELEASE_SSH_KEY,

    [string]$GitHubRepo = "",
    [string]$GitHubToken = $env:GH_TOKEN,
    [bool]$GitHubPrerelease = $true,

    [string]$LocalDataDir = "",

    [switch]$DryRun,
    [switch]$SkipVerify
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Net.Http

$DesktopReleaseManifestFilename = "desktop_windows_release_manifest.json"
$DesktopReleaseAssetDirname = "desktop_windows_releases"

function Resolve-ExistingFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    if (-not $Path.Trim()) {
        throw "$Description path was not provided."
    }
    $resolved = Resolve-Path -LiteralPath $Path -ErrorAction SilentlyContinue
    if (-not $resolved) {
        throw "$Description was not found: $Path"
    }
    return $resolved.ProviderPath
}

function ConvertTo-RemoteShellQuoted {
    param([Parameter(Mandatory = $true)][string]$Value)
    return "'" + $Value.Replace("'", "'\''") + "'"
}

function Invoke-External {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Write-Host ("+ {0} {1}" -f $Command, ($Arguments -join " "))
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Command"
    }
}

function New-DirectoryIfMissing {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Get-DefaultAssetUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ConfiguredManifestUrl,

        [Parameter(Mandatory = $true)]
        [string]$AssetName
    )

    if ($ConfiguredManifestUrl.Trim()) {
        try {
            $uri = [System.Uri]$ConfiguredManifestUrl
            return ("{0}://{1}/releases/desktop/windows/{2}" -f $uri.Scheme, $uri.Authority, $AssetName)
        }
        catch {
            # Fall through to the production default.
        }
    }
    return "https://api.kraitos.app/releases/desktop/windows/$AssetName"
}

function Get-SshConfigHostDefaults {
    param([Parameter(Mandatory = $true)][string]$HostAlias)

    $configPath = Join-Path $env:USERPROFILE ".ssh\config"
    if (-not (Test-Path -LiteralPath $configPath)) {
        return $null
    }

    $result = [ordered]@{
        Host = $HostAlias
        User = ""
        Port = $null
    }
    $inMatchingHost = $false
    foreach ($line in Get-Content -LiteralPath $configPath) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        if ($trimmed -match "^Host\s+(.+)$") {
            $patterns = $matches[1] -split "\s+"
            $inMatchingHost = $patterns -contains $HostAlias
            continue
        }
        if (-not $inMatchingHost) {
            continue
        }
        if ($trimmed -match "^User\s+(.+)$") {
            $result.User = $matches[1].Trim()
            continue
        }
        if ($trimmed -match "^Port\s+(\d+)$") {
            $result.Port = [int]$matches[1]
            continue
        }
    }
    if (-not $result.User -and -not $result.Port) {
        return $null
    }
    return [pscustomobject]$result
}

function New-ReleaseManifest {
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$ReleaseInfo,

        [Parameter(Mandatory = $true)]
        [string]$AssetName,

        [Parameter(Mandatory = $true)]
        [string]$ResolvedAssetUrl,

        [Parameter(Mandatory = $true)]
        [string]$MsiFile,

        [Parameter(Mandatory = $true)]
        [string]$Sha256,

        [Parameter(Mandatory = $true)]
        [long]$SizeBytes,

        [Parameter(Mandatory = $true)]
        [string]$ReleaseNotes
    )

    return [ordered]@{
        channel = [string]$ReleaseInfo.channel
        latest = [ordered]@{
            version = [string]$ReleaseInfo.version
            tagName = [string]$ReleaseInfo.release_tag
            assetName = $AssetName
            assetUrl = $ResolvedAssetUrl
            publishedAt = (Get-Date).ToUniversalTime().ToString("o")
            sizeBytes = $SizeBytes
            sha256 = $Sha256
            notes = $ReleaseNotes
        }
    }
}

function Test-LiveManifest {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedVersion,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedAssetUrl
    )

    $payload = Invoke-RestMethod -Uri $Url -Headers @{ Accept = "application/json" } -TimeoutSec 30
    $latest = $payload.latest
    if (-not $latest) {
        throw "Manifest verification failed: no latest release was returned by $Url"
    }
    if ([string]$latest.version -ne $ExpectedVersion) {
        throw "Manifest verification failed: expected version $ExpectedVersion, got $($latest.version)"
    }
    if ([string]$latest.assetUrl -ne $ExpectedAssetUrl) {
        throw "Manifest verification failed: expected assetUrl $ExpectedAssetUrl, got $($latest.assetUrl)"
    }
    return $payload
}

function Test-AssetHeaders {
    param([Parameter(Mandatory = $true)][string]$Url)

    $client = [System.Net.Http.HttpClient]::new()
    try {
        $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Get, $Url)
        $request.Headers.Range = [System.Net.Http.Headers.RangeHeaderValue]::new(0, 0)
        $response = $client.SendAsync(
            $request,
            [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead
        ).GetAwaiter().GetResult()
        try {
            $code = [int]$response.StatusCode
            if ($code -lt 200 -or $code -ge 300) {
                throw "Asset verification failed: $Url returned HTTP $code"
            }
            return $response.Headers
        }
        finally {
            $response.Dispose()
        }
    }
    finally {
        $client.Dispose()
    }
}

function Publish-LocalRelease {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DataDir,

        [Parameter(Mandatory = $true)]
        [string]$MsiFile,

        [Parameter(Mandatory = $true)]
        [string]$ManifestFile,

        [Parameter(Mandatory = $true)]
        [string]$AssetName
    )

    New-DirectoryIfMissing -Path $DataDir
    $assetDir = Join-Path $DataDir $DesktopReleaseAssetDirname
    New-DirectoryIfMissing -Path $assetDir
    Copy-Item -LiteralPath $MsiFile -Destination (Join-Path $assetDir $AssetName) -Force
    Copy-Item -LiteralPath $ManifestFile -Destination (Join-Path $DataDir $DesktopReleaseManifestFilename) -Force
}

function Publish-KraitosRelease {
    param(
        [Parameter(Mandatory = $true)]
        [string]$HostName,

        [Parameter(Mandatory = $true)]
        [string]$UserName,

        [Parameter(Mandatory = $true)]
        [int]$Port,

        [Parameter(Mandatory = $true)]
        [string]$RemoteDataDir,

        [Parameter(Mandatory = $true)]
        [string]$MsiFile,

        [Parameter(Mandatory = $true)]
        [string]$ManifestFile,

        [Parameter(Mandatory = $true)]
        [string]$AssetName,

        [string]$KeyPath = ""
    )

    if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
        throw "ssh was not found on PATH. Install OpenSSH or publish through GitHub/Local target."
    }
    if (-not (Get-Command scp -ErrorAction SilentlyContinue)) {
        throw "scp was not found on PATH. Install OpenSSH or publish through GitHub/Local target."
    }

    $remote = "${UserName}@${HostName}"
    $remoteAssetDir = "$RemoteDataDir/$DesktopReleaseAssetDirname"
    $remoteAsset = "$remoteAssetDir/$AssetName"
    $remoteAssetTmp = "$remoteAsset.uploading"
    $remoteManifest = "$RemoteDataDir/$DesktopReleaseManifestFilename"
    $remoteManifestTmp = "$remoteManifest.uploading"

    $sshCommon = @("-p", [string]$Port, "-o", "StrictHostKeyChecking=accept-new")
    $scpCommon = @("-P", [string]$Port, "-o", "StrictHostKeyChecking=accept-new")
    if ($KeyPath.Trim()) {
        $resolvedKey = Resolve-ExistingFile -Path $KeyPath -Description "SSH key"
        $sshCommon += @("-i", $resolvedKey)
        $scpCommon += @("-i", $resolvedKey)
    }

    Invoke-External -Command "ssh" -Arguments ($sshCommon + @(
        $remote,
        "mkdir -p -- $(ConvertTo-RemoteShellQuoted $remoteAssetDir)"
    ))
    Invoke-External -Command "scp" -Arguments ($scpCommon + @(
        $MsiFile,
        "${remote}:$remoteAssetTmp"
    ))
    Invoke-External -Command "scp" -Arguments ($scpCommon + @(
        $ManifestFile,
        "${remote}:$remoteManifestTmp"
    ))
    Invoke-External -Command "ssh" -Arguments ($sshCommon + @(
        $remote,
        "mv -f -- $(ConvertTo-RemoteShellQuoted $remoteAssetTmp) $(ConvertTo-RemoteShellQuoted $remoteAsset) && mv -f -- $(ConvertTo-RemoteShellQuoted $remoteManifestTmp) $(ConvertTo-RemoteShellQuoted $remoteManifest)"
    ))
}

function Invoke-GitHubApi {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Method,

        [Parameter(Mandatory = $true)]
        [string]$Uri,

        [Parameter(Mandatory = $true)]
        [string]$Token,

        [object]$Body = $null
    )

    $headers = @{
        Authorization = "Bearer $Token"
        Accept = "application/vnd.github+json"
        "X-GitHub-Api-Version" = "2022-11-28"
        "User-Agent" = "EmploAI-Desktop-Release-Publisher"
    }

    $args = @{
        Method = $Method
        Uri = $Uri
        Headers = $headers
        TimeoutSec = 60
    }
    if ($null -ne $Body) {
        $args.Body = ($Body | ConvertTo-Json -Depth 10)
        $args.ContentType = "application/json"
    }
    return Invoke-RestMethod @args
}

function Publish-GitHubRelease {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Repo,

        [Parameter(Mandatory = $true)]
        [string]$Token,

        [Parameter(Mandatory = $true)]
        [string]$TagName,

        [Parameter(Mandatory = $true)]
        [string]$Version,

        [Parameter(Mandatory = $true)]
        [string]$MsiFile,

        [Parameter(Mandatory = $true)]
        [string]$AssetName,

        [Parameter(Mandatory = $true)]
        [bool]$Prerelease,

        [Parameter(Mandatory = $true)]
        [string]$ReleaseNotes
    )

    if (-not $Token.Trim()) {
        throw "GitHub token was not provided. Set GH_TOKEN or pass -GitHubToken."
    }

    $apiRoot = "https://api.github.com/repos/$Repo"
    try {
        $release = Invoke-GitHubApi -Method "Get" -Uri "$apiRoot/releases/tags/$TagName" -Token $Token
    }
    catch {
        $statusCode = $null
        if ($_.Exception.Response) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        if ($statusCode -ne 404) {
            throw
        }
        $release = Invoke-GitHubApi -Method "Post" -Uri "$apiRoot/releases" -Token $Token -Body @{
            tag_name = $TagName
            name = "EmploAI $Version"
            body = $ReleaseNotes
            draft = $false
            prerelease = $Prerelease
        }
    }

    foreach ($asset in @($release.assets)) {
        if ($asset.name -eq $AssetName) {
            Invoke-GitHubApi -Method "Delete" -Uri "$apiRoot/releases/assets/$($asset.id)" -Token $Token | Out-Null
        }
    }

    $uploadUrl = "https://uploads.github.com/repos/$Repo/releases/$($release.id)/assets?name=$([System.Uri]::EscapeDataString($AssetName))"
    $headers = @{
        Authorization = "Bearer $Token"
        Accept = "application/vnd.github+json"
        "X-GitHub-Api-Version" = "2022-11-28"
        "User-Agent" = "EmploAI-Desktop-Release-Publisher"
    }
    return Invoke-RestMethod -Method Post -Uri $uploadUrl -Headers $headers -ContentType "application/octet-stream" -InFile $MsiFile -TimeoutSec 3600
}

if ($env:EMPLOAI_RELEASE_SSH_PORT -and $KraitosPort -eq 22) {
    $KraitosPort = [int]$env:EMPLOAI_RELEASE_SSH_PORT
}
if ((-not $KraitosHost.Trim() -or -not $KraitosUser.Trim()) -and $KraitosSshConfigHost.Trim()) {
    $sshConfigDefaults = Get-SshConfigHostDefaults -HostAlias $KraitosSshConfigHost
    if ($sshConfigDefaults) {
        if (-not $KraitosHost.Trim()) {
            $KraitosHost = [string]$sshConfigDefaults.Host
        }
        if (-not $KraitosUser.Trim() -and $sshConfigDefaults.User) {
            $KraitosUser = [string]$sshConfigDefaults.User
        }
        if ($KraitosPort -eq 22 -and $sshConfigDefaults.Port) {
            $KraitosPort = [int]$sshConfigDefaults.Port
        }
    }
}
if (-not $KraitosRemoteDataDir.Trim()) {
    $KraitosRemoteDataDir = if ($env:EMPLOAI_RELEASE_REMOTE_DATA_DIR) {
        $env:EMPLOAI_RELEASE_REMOTE_DATA_DIR
    }
    else {
        "/var/lib/emploai-remote/data"
    }
}
if (-not $ReleaseInfoPath.Trim()) {
    $ReleaseInfoPath = Join-Path $PSScriptRoot "release_info.json"
}

$releaseInfoFile = Resolve-ExistingFile -Path $ReleaseInfoPath -Description "release_info.json"
$releaseInfo = Get-Content -LiteralPath $releaseInfoFile -Raw | ConvertFrom-Json

$repoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")
$manifestAssetName = [string]$releaseInfo.primary_asset
if (-not $manifestAssetName.Trim()) {
    $manifestAssetName = "EmploAI.msi"
}
if (-not $MsiPath.Trim()) {
    $candidateMsiPath = Join-Path $repoRoot.ProviderPath "dist\$manifestAssetName"
    if (-not (Test-Path -LiteralPath $candidateMsiPath)) {
        $versionedAssetName = "EmploAI-$($releaseInfo.msi_version).msi"
        $versionedCandidateMsiPath = Join-Path $repoRoot.ProviderPath "dist\$versionedAssetName"
        if (Test-Path -LiteralPath $versionedCandidateMsiPath) {
            $candidateMsiPath = $versionedCandidateMsiPath
        }
    }
    $MsiPath = $candidateMsiPath
}
$msiFile = Resolve-ExistingFile -Path $MsiPath -Description "MSI"
$msiItem = Get-Item -LiteralPath $msiFile
$uploadAssetName = $msiItem.Name

if (-not $ManifestUrl.Trim()) {
    $ManifestUrl = [string]$releaseInfo.update_manifest_url
}
if (-not $AssetUrl.Trim()) {
    $AssetUrl = Get-DefaultAssetUrl -ConfiguredManifestUrl $ManifestUrl -AssetName $uploadAssetName
}
if (-not $GitHubRepo.Trim()) {
    $GitHubRepo = [string]$releaseInfo.github_repo
}
if (-not $Notes.Trim()) {
    $Notes = "EmploAI desktop release $($releaseInfo.version)."
}

$sha256 = (Get-FileHash -LiteralPath $msiFile -Algorithm SHA256).Hash.ToLowerInvariant()
$publishRoot = Join-Path $env:TEMP "emploai-desktop-release-publish"
New-DirectoryIfMissing -Path $publishRoot
$manifestFile = if ($ManifestOutPath.Trim()) {
    $ManifestOutPath
}
else {
    Join-Path $publishRoot $DesktopReleaseManifestFilename
}
$manifestParent = Split-Path -Parent $manifestFile
if ($manifestParent) {
    New-DirectoryIfMissing -Path $manifestParent
}
$manifest = New-ReleaseManifest `
    -ReleaseInfo $releaseInfo `
    -AssetName $manifestAssetName `
    -ResolvedAssetUrl $AssetUrl `
    -MsiFile $msiFile `
    -Sha256 $sha256 `
    -SizeBytes $msiItem.Length `
    -ReleaseNotes $Notes
$manifestJson = $manifest | ConvertTo-Json -Depth 8
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($manifestFile, $manifestJson + [Environment]::NewLine, $utf8NoBom)

Write-Host "Prepared desktop release:"
Write-Host "  Version: $($releaseInfo.version)"
Write-Host "  Tag: $($releaseInfo.release_tag)"
Write-Host "  MSI: $msiFile"
Write-Host "  Size: $($msiItem.Length) bytes"
Write-Host "  SHA256: $sha256"
Write-Host "  Manifest: $manifestFile"
Write-Host "  Manifest asset name: $manifestAssetName"
Write-Host "  Upload asset name: $uploadAssetName"
Write-Host "  Manifest URL: $ManifestUrl"
Write-Host "  Asset URL: $AssetUrl"

if ($DryRun) {
    Write-Host "Dry run enabled; no files were published."
    exit 0
}

if ($Target -in @("Kraitos", "Both")) {
    if (-not $KraitosHost.Trim() -or -not $KraitosUser.Trim()) {
        throw "Kraitos publish requires -KraitosHost and -KraitosUser, EMPLOAI_RELEASE_SSH_HOST and EMPLOAI_RELEASE_SSH_USER, or an SSH config host named '$KraitosSshConfigHost' with a User."
    }
}
if ($Target -in @("GitHub", "Both")) {
    if (-not $GitHubRepo.Trim()) {
        throw "GitHub publish requires -GitHubRepo or github_repo in release_info.json."
    }
    if (-not $GitHubToken.Trim()) {
        throw "GitHub publish requires -GitHubToken or GH_TOKEN."
    }
}

switch ($Target) {
    "Local" {
        if (-not $LocalDataDir.Trim()) {
            $LocalDataDir = Join-Path $repoRoot.ProviderPath "dist\desktop-release-publish"
        }
        Publish-LocalRelease -DataDir $LocalDataDir -MsiFile $msiFile -ManifestFile $manifestFile -AssetName $uploadAssetName
        Write-Host "Published local release data to: $LocalDataDir"
    }
    "Kraitos" {
        Publish-KraitosRelease `
            -HostName $KraitosHost `
            -UserName $KraitosUser `
            -Port $KraitosPort `
            -RemoteDataDir $KraitosRemoteDataDir `
            -MsiFile $msiFile `
            -ManifestFile $manifestFile `
            -AssetName $uploadAssetName `
            -KeyPath $SshKeyPath
    }
    "GitHub" {
        $asset = Publish-GitHubRelease `
            -Repo $GitHubRepo `
            -Token $GitHubToken `
            -TagName ([string]$releaseInfo.release_tag) `
            -Version ([string]$releaseInfo.version) `
            -MsiFile $msiFile `
            -AssetName $uploadAssetName `
            -Prerelease $GitHubPrerelease `
            -ReleaseNotes $Notes
        Write-Host "Published GitHub asset: $($asset.browser_download_url)"
        Write-Warning "GitHub-only publishing does not update the Kraitos manifest. Existing 14.4 clients require the Kraitos manifest to advertise the newer release."
    }
    "Both" {
        $asset = Publish-GitHubRelease `
            -Repo $GitHubRepo `
            -Token $GitHubToken `
            -TagName ([string]$releaseInfo.release_tag) `
            -Version ([string]$releaseInfo.version) `
            -MsiFile $msiFile `
            -AssetName $uploadAssetName `
            -Prerelease $GitHubPrerelease `
            -ReleaseNotes $Notes
        Write-Host "Published GitHub asset: $($asset.browser_download_url)"

        Publish-KraitosRelease `
            -HostName $KraitosHost `
            -UserName $KraitosUser `
            -Port $KraitosPort `
            -RemoteDataDir $KraitosRemoteDataDir `
            -MsiFile $msiFile `
            -ManifestFile $manifestFile `
            -AssetName $uploadAssetName `
            -KeyPath $SshKeyPath
    }
}

if (-not $SkipVerify -and $Target -in @("Kraitos", "Both")) {
    Test-LiveManifest -Url $ManifestUrl -ExpectedVersion ([string]$releaseInfo.version) -ExpectedAssetUrl $AssetUrl | Out-Null
    Test-AssetHeaders -Url $AssetUrl | Out-Null
    Write-Host "Verified live manifest and installer asset."
}
elseif ($SkipVerify) {
    Write-Host "Skipped live verification."
}

Write-Host "Desktop release publish completed."
