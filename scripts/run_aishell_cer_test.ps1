[CmdletBinding()]
param(
    [string]$DatasetRoot = "data\evaluation\aishell1\data_aishell",
    [ValidateSet("dev", "test")]
    [string]$Split = "test",
    [int]$Limit = 500,
    [string]$Model = "base",
    [string]$Device = "cpu",
    [string]$ComputeType = "int8",
    [double]$Threshold = 0.08,
    [string]$Output = "data\evaluation\aishell1\reports\aishell1-test-cer.json",
    [switch]$VerboseSamples,
    [switch]$FailOnThreshold
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$HostDataset = Join-Path $RepoRoot $DatasetRoot
$HostOutput = Join-Path $RepoRoot $Output
$DataRoot = (Resolve-Path (Join-Path $RepoRoot "data")).Path

if (-not (Test-Path -LiteralPath $HostDataset -PathType Container)) {
    throw "AISHELL-1 dataset directory not found: $HostDataset"
}
if (-not $HostDataset.StartsWith($DataRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "DatasetRoot must be inside the project's data directory."
}
if (-not $HostOutput.StartsWith($DataRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Output must be inside the project's data directory."
}

$ContainerDataset = "/data" + $HostDataset.Substring($DataRoot.Length).Replace("\", "/")
$ContainerOutput = "/data" + $HostOutput.Substring($DataRoot.Length).Replace("\", "/")
$ContainerScript = "/tmp/evaluate_aishell_cer.py"

Push-Location $RepoRoot
try {
    $running = docker compose ps --services --filter status=running
    if ($LASTEXITCODE -ne 0 -or $running -notcontains "worker") {
        throw "Worker is not running. Start it with: docker compose --profile dev up -d"
    }

    docker compose cp .\scripts\evaluate_aishell_cer.py "worker:$ContainerScript"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to copy the evaluator into the Worker container."
    }

    $arguments = @(
        "compose", "exec", "-T", "worker", "python", $ContainerScript,
        "--dataset-root", $ContainerDataset,
        "--split", $Split,
        "--limit", $Limit,
        "--model", $Model,
        "--device", $Device,
        "--compute-type", $ComputeType,
        "--threshold", $Threshold,
        "--output", $ContainerOutput
    )
    if ($VerboseSamples) {
        $arguments += "--verbose"
    }
    & docker @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "AISHELL-1 transcription evaluation failed."
    }

    $python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    $rescoreArguments = @(
        ".\scripts\rescore_aishell_cer.py",
        "--report", $HostOutput,
        "--threshold", $Threshold
    )
    if ($FailOnThreshold) {
        $rescoreArguments += "--fail-on-threshold"
    }
    & $python @rescoreArguments
    if ($LASTEXITCODE -ne 0) {
        throw "AISHELL-1 normalized CER did not meet the configured threshold."
    }
    Write-Host "AISHELL-1 CER evaluation completed. Report: $HostOutput" -ForegroundColor Green
}
finally {
    Pop-Location
}
