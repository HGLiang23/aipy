[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot "_common.ps1")

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Get-ProjectPythonCommand -RepositoryRoot $repositoryRoot

Push-Location $repositoryRoot
try {
    Invoke-PythonCommand -Python $python -Arguments @("-m", "ruff", "check", ".")
    Invoke-PythonCommand -Python $python -Arguments @("-m", "ruff", "format", "--check", ".")
    Invoke-PythonCommand -Python $python -Arguments @("-m", "mypy")
    Invoke-PythonCommand -Python $python -Arguments @("-m", "pytest")
}
finally {
    Pop-Location
}

