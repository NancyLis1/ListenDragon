[CmdletBinding()]
param(
    [string]$PythonPath = ".\.venv\Scripts\python.exe",
    [switch]$FailOnSecurityFindings
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = (Resolve-Path (Join-Path $RepoRoot $PythonPath)).Path

Push-Location $RepoRoot
try {
    & $Python -m ruff check backend scripts
    if ($LASTEXITCODE -ne 0) { throw "Ruff failed" }

    & $Python -m coverage erase
    & $Python -m coverage run --source=backend/src/listen_dragon -m pytest backend/tests -q --basetemp tmp/pytest-quality
    if ($LASTEXITCODE -ne 0) { throw "pytest failed" }
    & $Python -m coverage report --fail-under=90
    if ($LASTEXITCODE -ne 0) { throw "coverage is below 90%" }

    & $Python -m pip check
    if ($LASTEXITCODE -ne 0) { throw "pip check failed" }

    docker compose exec -T frontend npm test -- --run
    if ($LASTEXITCODE -ne 0) { throw "frontend tests failed" }
    docker compose exec -T frontend npm run build
    if ($LASTEXITCODE -ne 0) { throw "frontend build failed" }
    docker compose exec -T frontend npm audit --audit-level=high
    if ($LASTEXITCODE -ne 0) { throw "npm audit found a high-severity vulnerability" }

    $SecurityArgs = @("scripts/audit_security_controls.py")
    if ($FailOnSecurityFindings) { $SecurityArgs += "--fail-on-findings" }
    & $Python @SecurityArgs
    if ($LASTEXITCODE -ne 0) { throw "security controls audit failed" }
}
finally {
    Pop-Location
}
