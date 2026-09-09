[CmdletBinding()]
param(
    [string]$VideoId = "",
    [string]$Upload = "",
    [string]$ApiBase = "http://localhost:8000/api/v1",
    [string]$Query = "",
    [string]$FollowUp = "",
    [int]$RequestTimeout = 120,
    [int]$WorkerTimeout = 1800,
    [double]$PollSeconds = 2,
    [string]$Output = "",
    [string]$PythonPath = "",
    [switch]$SkipGeneration,
    [switch]$StartServices,
    [switch]$BuildServices
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if ($VideoId -and $Upload) {
    throw "Use either -VideoId or -Upload, not both."
}

if ($PythonPath) {
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        throw "Python executable not found: $PythonPath"
    }
    $python = (Resolve-Path -LiteralPath $PythonPath).Path
}
else {
    $projectPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $projectPython -PathType Leaf) {
        $python = $projectPython
    }
    else {
        $command = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $command) {
            throw "Python was not found. Pass -PythonPath explicitly."
        }
        $python = $command.Source
    }
}

Push-Location $RepoRoot
try {
    if ($StartServices -or $BuildServices) {
        $composeArgs = @("compose", "--profile", "dev", "up", "-d")
        if ($BuildServices) {
            $composeArgs += "--build"
        }
        Write-Host "`n=== Start Docker services ===" -ForegroundColor Cyan
        & docker @composeArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Docker Compose startup failed with exit code $LASTEXITCODE"
        }
    }

    $script = Join-Path $PSScriptRoot "test_t13_live_features.py"
    $arguments = @(
        $script,
        "--api-base", $ApiBase,
        "--timeout", $RequestTimeout,
        "--worker-timeout", $WorkerTimeout,
        "--poll-seconds", $PollSeconds
    )
    if ($Query) {
        $arguments += @("--query", $Query)
    }
    if ($FollowUp) {
        $arguments += @("--follow-up", $FollowUp)
    }
    if ($VideoId) {
        [void][guid]::Parse($VideoId)
        $arguments += @("--video-id", $VideoId)
    }
    elseif ($Upload) {
        if (-not (Test-Path -LiteralPath $Upload -PathType Leaf)) {
            throw "Upload video not found: $Upload"
        }
        $arguments += @("--upload", (Resolve-Path -LiteralPath $Upload).Path)
    }
    if ($SkipGeneration) {
        $arguments += "--skip-generation"
    }
    if ($Output) {
        $arguments += @("--output", $Output)
    }

    Write-Host "`n=== T13 full-chain functional test ===" -ForegroundColor Cyan
    & $python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Full-chain test failed with exit code $LASTEXITCODE"
    }
    Write-Host "`nFULL-CHAIN TEST PASSED" -ForegroundColor Green
}
finally {
    Pop-Location
}
