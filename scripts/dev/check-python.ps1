[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot "_common.ps1")

$python = Get-Python312Command
$arguments = @($python.PrefixArguments) + @("--version")
& $python.FilePath @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Unable to execute Python 3.12."
}

Write-Host "Python command: $($python.FilePath) $($python.PrefixArguments -join ' ')"

