param(
    [int]$DeviceIndex = 1,
    [int]$SampleRate = 0,
    [string]$ModelDir = "$HOME\Documents\Models\hebrew-whisper-small-pass3-knesset-runtime-ready",
    [ValidateSet("transformers", "faster-whisper")]
    [string]$Runtime = "",
    [ValidateSet("balanced", "accurate")]
    [string]$Preset = "balanced",
    [int]$CommitSilenceMs = 0,
    [int]$MaxUtteranceMs = 0,
    [int]$SegmentMs = 0,
    [int]$DraftMinMs = 0,
    [int]$DraftIntervalMs = 0,
    [double]$EarlyFinishConfidence = 0,
    [double]$DiscardConfidence = 0,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = "Stop"

$env:EMPLO_APP_STT_HEBREW_MODEL_DIR = $ModelDir
$ExtraArgs = @($ExtraArgs | Where-Object { $_ -is [string] -and $_.Trim().Length -gt 0 })
$PresetArgs = @()
$OverrideArgs = @()

$launcher = Join-Path $PSScriptRoot "start_hebrew_whisper_live.ps1"
if ($Runtime) {
    $OverrideArgs += @("--runtime", $Runtime)
}
if ($Preset -eq "accurate") {
    $PresetArgs = @(
        "--segment-ms", "1200",
        "--draft-min-ms", "1400",
        "--draft-interval-ms", "1200",
        "--commit-silence-ms", "1400",
        "--max-utterance-ms", "4200",
        "--early-finish-confidence", "0.98",
        "--discard-confidence", "0.35"
    )
}
if ($CommitSilenceMs -gt 0) {
    $OverrideArgs += @("--commit-silence-ms", "$CommitSilenceMs")
}
if ($MaxUtteranceMs -gt 0) {
    $OverrideArgs += @("--max-utterance-ms", "$MaxUtteranceMs")
}
if ($SegmentMs -gt 0) {
    $OverrideArgs += @("--segment-ms", "$SegmentMs")
}
if ($DraftMinMs -gt 0) {
    $OverrideArgs += @("--draft-min-ms", "$DraftMinMs")
}
if ($DraftIntervalMs -gt 0) {
    $OverrideArgs += @("--draft-interval-ms", "$DraftIntervalMs")
}
if ($EarlyFinishConfidence -gt 0) {
    $OverrideArgs += @("--early-finish-confidence", "$EarlyFinishConfidence")
}
if ($DiscardConfidence -gt 0) {
    $OverrideArgs += @("--discard-confidence", "$DiscardConfidence")
}
$ExtraArgs = @($PresetArgs + $OverrideArgs + $ExtraArgs)
& $launcher -DeviceIndex $DeviceIndex -SampleRate $SampleRate @ExtraArgs
