[CmdletBinding()]
param(
    [string]$Destination = "data\evaluation\aishell1"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Target = Join-Path $RepoRoot $Destination
$ParquetDir = Join-Path $Target "parquet"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Project Python not found: $Python"
}
New-Item -ItemType Directory -Force -Path $ParquetDir | Out-Null

$Files = @(
    @{ Name = "0000.parquet"; Size = 398009873 },
    @{ Name = "0001.parquet"; Size = 382183828 },
    @{ Name = "0002.parquet"; Size = 357172889 }
)
$BaseUrl = "https://huggingface.co/datasets/TwinkStart/AISHELL-1/resolve/refs%2Fconvert%2Fparquet/default/test"

foreach ($File in $Files) {
    $Output = Join-Path $ParquetDir $File.Name
    if ((Test-Path -LiteralPath $Output -PathType Leaf) -and (Get-Item $Output).Length -eq $File.Size) {
        Write-Host "Already downloaded: $($File.Name)"
        continue
    }
    curl.exe -L --continue-at - --output $Output "$BaseUrl/$($File.Name)"
    if ($LASTEXITCODE -ne 0) {
        throw "Download failed: $($File.Name)"
    }
    if ((Get-Item $Output).Length -ne $File.Size) {
        throw "Unexpected file size for $($File.Name)"
    }
}

& $Python (Join-Path $PSScriptRoot "extract_aishell1.py") `
    --parquet-dir $ParquetDir `
    --destination $Target
if ($LASTEXITCODE -ne 0) {
    throw "AISHELL-1 extraction failed."
}
Write-Host "AISHELL-1 test split is ready at $Target\data_aishell" -ForegroundColor Green
