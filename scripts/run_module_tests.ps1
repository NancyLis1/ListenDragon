[CmdletBinding()]
param(
    [string]$PythonPath = "",
    [ValidateSet("auto", "docker", "local")]
    [string]$FrontendMode = "auto",
    [switch]$SkipBackend,
    [switch]$SkipFrontend,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

function Resolve-Python {
    if ($PythonPath) {
        if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
            throw "Python executable not found: $PythonPath"
        }
        return (Resolve-Path -LiteralPath $PythonPath).Path
    }
    $projectPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $projectPython -PathType Leaf) {
        return $projectPython
    }
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "Python was not found. Pass -PythonPath explicitly."
    }
    return $command.Source
}

function Resolve-FrontendRunner {
    if ($FrontendMode -eq "docker") {
        return "docker"
    }
    if ($FrontendMode -eq "local") {
        return "local"
    }
    try {
        $running = docker compose --profile dev ps --services --filter status=running 2>$null
        if ($LASTEXITCODE -eq 0 -and $running -contains "frontend") {
            return "docker"
        }
    }
    catch {
        # Fall through to the local Node.js installation.
    }
    return "local"
}

Push-Location $RepoRoot
try {
    $python = Resolve-Python
    Write-Host "Repository: $RepoRoot"
    Write-Host "Python: $python"

    if (-not $SkipBackend) {
        $tempParent = Join-Path $RepoRoot "tmp"
        New-Item -ItemType Directory -Force -Path $tempParent | Out-Null
        $pytestTemp = Join-Path $tempParent "pytest-module-$PID"

        Invoke-Checked "Python static checks" {
            & $python -m ruff check backend scripts\test_t13_live_features.py
        }
        Invoke-Checked "Backend module and API tests" {
            & $python -m pytest backend\tests -q --basetemp $pytestTemp
        }
        Invoke-Checked "Backend dependency consistency" {
            & $python -m pip check
        }
    }

    if (-not $SkipFrontend) {
        $runner = Resolve-FrontendRunner
        Write-Host "Frontend runner: $runner"
        if ($runner -eq "docker") {
            Invoke-Checked "Frontend component tests" {
                docker compose exec -T frontend npm test -- --run
            }
            if (-not $SkipBuild) {
                Invoke-Checked "Frontend production build" {
                    docker compose exec -T frontend npm run build
                }
            }
        }
        else {
            $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
            if ($null -eq $npm) {
                throw "npm.cmd was not found. Start the dev Compose profile or install Node.js."
            }
            Push-Location (Join-Path $RepoRoot "frontend")
            try {
                Invoke-Checked "Frontend component tests" {
                    & $npm.Source test -- --run
                }
                if (-not $SkipBuild) {
                    Invoke-Checked "Frontend production build" {
                        & $npm.Source run build
                    }
                }
            }
            finally {
                Pop-Location
            }
        }
    }

    Write-Host "`nMODULE TESTS PASSED" -ForegroundColor Green
}
finally {
    Pop-Location
}
