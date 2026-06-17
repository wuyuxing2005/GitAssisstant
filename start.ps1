$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$agentRoot = Join-Path $repoRoot "agent"
$frontendRoot = Join-Path $agentRoot "frontend"
$pythonExe = Join-Path $agentRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonExe)) {
  Write-Error "Backend Python venv not found: $pythonExe"
}

$backendCommand = "`$host.UI.RawUI.WindowTitle = 'code-agent backend'; Set-Location -LiteralPath '$agentRoot'; & '$pythonExe' -m uvicorn gitIssueAssitant.RESTAPIAdapter.main:app --reload --reload-dir gitIssueAssitant --port 8000"
$frontendCommand = "`$host.UI.RawUI.WindowTitle = 'code-agent frontend'; Set-Location -LiteralPath '$frontendRoot'; npm.cmd run dev"

Start-Process -FilePath "powershell.exe" -ArgumentList "-NoExit -ExecutionPolicy Bypass -Command `"$backendCommand`""
Start-Process -FilePath "powershell.exe" -ArgumentList "-NoExit -ExecutionPolicy Bypass -Command `"$frontendCommand`""

Write-Host "Backend window:  http://127.0.0.1:8000"
Write-Host "Frontend window: http://127.0.0.1:5173"
