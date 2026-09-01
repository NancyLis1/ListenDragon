$ErrorActionPreference = 'Continue'

function Get-ToolVersion([string]$Name, [string[]]$Arguments) {
  $command = Get-Command $Name -ErrorAction SilentlyContinue
  if (-not $command) {
    return [pscustomobject]@{ Tool = $Name; Status = 'MISSING'; Version = '' }
  }
  $text = (& $Name @Arguments 2>&1 | Select-Object -First 1) -join ''
  return [pscustomobject]@{ Tool = $Name; Status = 'FOUND'; Version = $text.Trim() }
}

$rows = @(
  Get-ToolVersion 'git' @('--version')
  Get-ToolVersion 'docker' @('--version')
  Get-ToolVersion 'node' @('--version')
  Get-ToolVersion 'npm' @('--version')
  Get-ToolVersion 'python' @('--version')
  Get-ToolVersion 'ffmpeg' @('-version')
)

$rows | Format-Table -AutoSize

Write-Output "`nDocker Compose configuration:"
docker compose -f compose.yaml config --quiet
if ($LASTEXITCODE -eq 0) { Write-Output 'PASS' } else { Write-Output 'FAIL' }

Write-Output "`nRepository safeguards:"
$requiredIgnored = @('.env', 'data/uploads/sample.mp4', 'data/listendragon.db')
foreach ($path in $requiredIgnored) {
  git check-ignore --quiet $path
  $result = if ($LASTEXITCODE -eq 0) { 'PASS' } else { 'FAIL' }
  Write-Output "$result`t$path"
}
