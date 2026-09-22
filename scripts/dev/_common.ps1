Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-Python312Command {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$PrefixArguments = @()
    )

    $arguments = @($PrefixArguments) + @(
        "-c",
        "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    )
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        $version = & $FilePath @arguments 2>$null
        $exitCode = $LASTEXITCODE
    }
    catch {
        return $false
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    return $exitCode -eq 0 -and $version -eq "3.12"
}

function Get-Python312Command {
    $launcher = Get-Command "py" -ErrorAction SilentlyContinue
    if ($null -ne $launcher -and (Test-Python312Command -FilePath $launcher.Source -PrefixArguments @("-3.12"))) {
        return [pscustomobject]@{
            FilePath = $launcher.Source
            PrefixArguments = [string[]]@("-3.12")
        }
    }

    $python = Get-Command "python" -ErrorAction SilentlyContinue
    if ($null -ne $python -and (Test-Python312Command -FilePath $python.Source)) {
        return [pscustomobject]@{
            FilePath = $python.Source
            PrefixArguments = [string[]]@()
        }
    }

    throw "Python 3.12 was not found. Install it and ensure either 'py -3.12' or 'python' can launch it."
}

function Get-ProjectPythonCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot
    )

    $virtualEnvironmentPython = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
    if (Test-Path $virtualEnvironmentPython) {
        if (-not (Test-Python312Command -FilePath $virtualEnvironmentPython)) {
            throw "The existing .venv does not use Python 3.12. Recreate it with scripts/dev/install.ps1."
        }
        return [pscustomobject]@{
            FilePath = $virtualEnvironmentPython
            PrefixArguments = [string[]]@()
        }
    }

    return Get-Python312Command
}

function Invoke-PythonCommand {
    param(
        [Parameter(Mandatory = $true)]
        [pscustomobject]$Python,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $allArguments = @($Python.PrefixArguments) + $Arguments
    & $Python.FilePath @allArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code ${LASTEXITCODE}: $($Arguments -join ' ')"
    }
}
