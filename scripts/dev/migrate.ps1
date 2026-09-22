[CmdletBinding()]
param(
    [string]$Revision = "head"
)

. (Join-Path $PSScriptRoot "_common.ps1")

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$alembicConfiguration = Join-Path $repositoryRoot "migrations\alembic.ini"
if (-not (Test-Path $alembicConfiguration)) {
    throw "migrations/alembic.ini does not exist. Add the migration baseline before running migrations."
}

$python = Get-ProjectPythonCommand -RepositoryRoot $repositoryRoot
Push-Location $repositoryRoot
try {
    Invoke-PythonCommand -Python $python -Arguments @(
        "-m", "alembic", "-c", "migrations/alembic.ini", "upgrade", $Revision
    )
}
finally {
    Pop-Location
}
