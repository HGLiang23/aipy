[CmdletBinding()]
param(
    [ValidateSet("Up", "Application", "Down", "Stop", "Status", "Logs", "Validate")]
    [string]$Action = "Up"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$composeFile = Join-Path $repositoryRoot "deploy\compose.yaml"
$environmentFile = Join-Path $repositoryRoot "deploy\.env"

if ($null -eq (Get-Command "docker" -ErrorAction SilentlyContinue)) {
    throw "Docker was not found on PATH. Install Docker Desktop or Docker Engine with Compose v2."
}
if (-not (Test-Path $environmentFile)) {
    throw "deploy/.env does not exist. Create it from deploy/.env.example and replace placeholder passwords."
}

$composeArguments = @("compose", "--env-file", $environmentFile, "-f", $composeFile)
switch ($Action) {
    "Up" { $composeArguments += @("up", "-d") }
    "Application" { $composeArguments += @("--profile", "application", "up", "-d", "--build") }
    "Down" { $composeArguments += @("down") }
    "Stop" { $composeArguments += @("stop") }
    "Status" { $composeArguments += @("ps") }
    "Logs" { $composeArguments += @("logs", "--follow", "--tail", "200") }
    "Validate" { $composeArguments += @("config", "--quiet") }
}

& docker @composeArguments
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose failed with exit code $LASTEXITCODE."
}

