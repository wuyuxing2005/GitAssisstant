$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$agentRoot = Join-Path $repoRoot "agent"
$frontendRoot = Join-Path $agentRoot "frontend"
$pythonExe = Join-Path $agentRoot ".venv\Scripts\python.exe"

$backendLog = Join-Path $repoRoot "backend.log"
$frontendLog = Join-Path $repoRoot "frontend.log"

if (-not (Test-Path -LiteralPath $pythonExe)) {
  Write-Error "Backend Python venv not found: $pythonExe"
}

function Stop-PortProcess {
  param(
    [int[]]$Ports
  )

  foreach ($port in $Ports) {
    $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue

    foreach ($conn in $connections) {
      $pidToKill = $conn.OwningProcess

      if ($pidToKill -and $pidToKill -ne $PID) {
        try {
          Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
          Write-Host "Stopped process on port $port, PID: $pidToKill"
        }
        catch {
          Write-Host "Failed to stop process on port $port, PID: $pidToKill"
        }
      }
    }
  }
}

$backendCommand = @"
Set-Location -LiteralPath '$agentRoot'
`$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 > `$null
`$env:PYTHONUTF8 = '1'
`$env:PYTHONIOENCODING = 'utf-8'
cmd.exe /d /c '"$pythonExe" -X utf8 -m uvicorn gitIssueAssitant.RESTAPIAdapter.main:app --reload --reload-dir gitIssueAssitant --port 8000 > "$backendLog" 2>&1'
"@

$frontendCommand = @"
Set-Location -LiteralPath '$frontendRoot'
`$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 > `$null
`$env:NO_COLOR = '1'
cmd.exe /d /c "npm.cmd run dev > ""$frontendLog"" 2>&1"
"@

Write-Host "Starting Code Agent..."
Write-Host "Backend log:  $backendLog"
Write-Host "Frontend log: $frontendLog"
Write-Host ""

try {
  $backendProcess = Start-Process `
    -FilePath "powershell.exe" `
    -WindowStyle Hidden `
    -PassThru `
    -ArgumentList "-ExecutionPolicy Bypass -Command `"$backendCommand`""

  $frontendProcess = Start-Process `
    -FilePath "powershell.exe" `
    -WindowStyle Hidden `
    -PassThru `
    -ArgumentList "-ExecutionPolicy Bypass -Command `"$frontendCommand`""

  Start-Sleep -Seconds 5

  Start-Process "http://127.0.0.1:5173"

  Write-Host "Code Agent started."
  Write-Host "Backend:  http://127.0.0.1:8000"
  Write-Host "Frontend: http://127.0.0.1:5173"
  Write-Host ""
  Write-Host "Press Ctrl + C to stop backend and frontend."

  while ($true) {
    Start-Sleep -Seconds 1
  }
}
finally {
  Write-Host ""
  Write-Host "Stopping Code Agent..."

  if ($backendProcess -and -not $backendProcess.HasExited) {
    Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
  }

  if ($frontendProcess -and -not $frontendProcess.HasExited) {
    Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue
  }

  Stop-PortProcess -Ports @(8000, 5173)

  Write-Host "Code Agent stopped."
}
