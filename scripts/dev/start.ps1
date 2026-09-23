#Requires -Version 5.1
<#
.SYNOPSIS
    Start the AIPY local development stack: FastAPI backend + Next.js web.

.DESCRIPTION
    Launches the backend (FastAPI via uvicorn) and the frontend (Next.js dev
    server) in two separate windows. Both bind 0.0.0.0 so other machines on the
    network can reach them. Configuration is read from the repository-root .env.

    Demo account: editor@example.com / demo-password

    NOTE: keep this file ASCII-only. Windows PowerShell 5.1 decodes .ps1 files
    without a UTF-8 BOM as ANSI, which corrupts non-ASCII string literals and
    breaks parsing.

.PARAMETER ApiPort
    Backend listen port. Defaults to 8000.

.PARAMETER WebPort
    Frontend listen port. Defaults to 3000.

.PARAMETER ApiOnly
    Start only the backend.

.PARAMETER WebOnly
    Start only the frontend (the backend is expected to run elsewhere).

.PARAMETER Reload
    Enable uvicorn hot reload for the backend. Requires the watchfiles package.

.EXAMPLE
    ./scripts/dev/start.ps1
    Starts both services on the default ports.

.EXAMPLE
    ./scripts/dev/start.ps1 -ApiPort 8001 -WebPort 3001
    Starts both services on alternative ports.
#>
[CmdletBinding()]
param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 3000,
    [switch]$ApiOnly,
    [switch]$WebOnly,
    [switch]$Reload
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "_common.ps1")

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

if (-not (Test-Path (Join-Path $repositoryRoot ".env"))) {
    throw "Missing .env. Copy .env.example to .env and set AIPY_DATABASE__URL / AIPY_REDIS__URL first."
}

function Test-PortInUse {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $pattern = ":$Port\s"
    $listeners = netstat -ano | Select-String -Pattern "LISTENING" | Select-String -Pattern $pattern
    return $null -ne $listeners
}

if (-not $WebOnly) {
    if (Test-PortInUse -Port $ApiPort) {
        throw "Port $ApiPort is already in use. Pass -ApiPort with a free port."
    }

    $python = Get-ProjectPythonCommand -RepositoryRoot $repositoryRoot
    $apiArguments = @($python.PrefixArguments) + @(
        "-m", "uvicorn", "apps.api.main:app",
        "--host", "0.0.0.0",
        "--port", "$ApiPort"
    )
    if ($Reload) {
        $apiArguments += "--reload"
    }

    Start-Process -FilePath $python.FilePath `
        -ArgumentList $apiArguments `
        -WorkingDirectory $repositoryRoot | Out-Null

    Write-Host "[api] http://localhost:$ApiPort  (openapi docs at /docs)" -ForegroundColor Green
}

if (-not $ApiOnly) {
    if (Test-PortInUse -Port $WebPort) {
        throw "Port $WebPort is already in use. Pass -WebPort with a free port."
    }

    $webRoot = Join-Path $repositoryRoot "web"
    $nextCommand = Join-Path $webRoot "node_modules\.bin\next.cmd"
    if (-not (Test-Path $nextCommand)) {
        throw "Cannot find $nextCommand. Run pnpm install (or npm install) inside web/ first."
    }

    Start-Process -FilePath $nextCommand `
        -ArgumentList @("dev", "-H", "0.0.0.0", "-p", "$WebPort") `
        -WorkingDirectory $webRoot | Out-Null

    Write-Host "[web] http://localhost:$WebPort" -ForegroundColor Green
}

Write-Host ""
Write-Host "Demo account: editor@example.com / demo-password" -ForegroundColor Cyan
Write-Host "To stop: close the two spawned windows." -ForegroundColor DarkGray
