$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$agentRoot = Join-Path $repoRoot "agent"
$frontendRoot = Join-Path $agentRoot "frontend"
$pythonExe = Join-Path $agentRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
  Write-Error "未找到后端虚拟环境：$pythonExe"
}

$backendCommand = @"
Set-Location '$agentRoot'
& '$pythonExe' -m uvicorn gitIssueAssitant.RESTAPIAdapter.main:app --reload --reload-dir gitIssueAssitant --port 8000
"@

$frontendCommand = @"
Set-Location '$frontendRoot'
npm.cmd run dev
"@

Start-Process powershell -WorkingDirectory $agentRoot -ArgumentList @(
  "-NoExit",
  "-Command",
  $backendCommand
)

Start-Process powershell -WorkingDirectory $frontendRoot -ArgumentList @(
  "-NoExit",
  "-Command",
  $frontendCommand
)
