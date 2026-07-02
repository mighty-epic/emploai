param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Args
)

& "$PSScriptRoot\scripts\desktop\start.ps1" @Args
exit $LASTEXITCODE
