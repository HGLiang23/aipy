[CmdletBinding()]
param(
    [switch]$SkipPipUpgrade
)

. (Join-Path $PSScriptRoot "_common.ps1")

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$hostPython = Get-Python312Command
$virtualEnvironment = Join-Path $repositoryRoot ".venv"

if (-not (Test-Path $virtualEnvironment)) {
    Invoke-PythonCommand -Python $hostPython -Arguments @("-m", "venv", $virtualEnvironment)
}

$projectPython = Get-ProjectPythonCommand -RepositoryRoot $repositoryRoot
Push-Location $repositoryRoot
try {
    if (-not $SkipPipUpgrade) {
        Invoke-PythonCommand -Python $projectPython -Arguments @("-m", "pip", "install", "--upgrade", "pip")
    }
    Invoke-PythonCommand -Python $projectPython -Arguments @("-m", "pip", "install", "--editable", ".[dev]")
}
finally {
    Pop-Location
}

