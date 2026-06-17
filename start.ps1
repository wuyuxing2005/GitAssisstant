$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$agentRoot = Join-Path $repoRoot "agent"
$frontendRoot = Join-Path $agentRoot "frontend"
$pythonExe = Join-Path $agentRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonExe)) {
  Write-Error "Backend Python venv not found: $pythonExe"
}

$script:managedProcesses = @()
$script:isStopping = $false
$script:stopRequested = $false

function Write-PrefixedLine {
  param(
    [string]$Prefix,
    [string]$Message,
    [ConsoleColor]$Color = [ConsoleColor]::Gray
  )

  if ([string]::IsNullOrWhiteSpace($Message)) {
    return
  }

  Write-Host "[$Prefix] $Message" -ForegroundColor $Color
}

function Stop-ManagedProcesses {
  if ($script:isStopping) {
    return
  }

  $script:isStopping = $true

  foreach ($entry in $script:managedProcesses) {
    $process = $entry.Process
    if ($null -eq $process) {
      continue
    }

    if (-not $process.HasExited) {
      Write-PrefixedLine -Prefix "system" -Message "Stopping $($entry.Name) process tree (PID=$($process.Id))" -Color DarkYellow
      taskkill.exe /PID $process.Id /T /F | Out-Null
      $process.WaitForExit(5000) | Out-Null
    }
  }

}

function Start-ManagedProcess {
  param(
    [string]$Name,
    [string]$FilePath,
    [string]$Arguments,
    [string]$WorkingDirectory
  )

  $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
  $startInfo.FileName = $FilePath
  $startInfo.Arguments = $Arguments
  $startInfo.WorkingDirectory = $WorkingDirectory
  $startInfo.UseShellExecute = $false
  $startInfo.CreateNoWindow = $true

  $process = [System.Diagnostics.Process]::new()
  $process.StartInfo = $startInfo
  $process.EnableRaisingEvents = $true

  $null = $process.Start()

  $entry = [pscustomobject]@{
    Name = $Name
    Process = $process
  }
  $script:managedProcesses += $entry

  Write-PrefixedLine -Prefix "system" -Message "Started $Name, PID=$($process.Id)" -Color DarkGreen

  return $entry
}

$backendArgs = "-m uvicorn gitIssueAssitant.RESTAPIAdapter.main:app --reload --reload-dir gitIssueAssitant --port 8000"
$frontendArgs = '/c "npm.cmd run dev"'
$cancelHandler = [ConsoleCancelEventHandler] {
  param($sender, $eventArgs)
  $eventArgs.Cancel = $true
  $script:stopRequested = $true
}

[Console]::add_CancelKeyPress($cancelHandler)

try {
  Write-PrefixedLine -Prefix "system" -Message "Starting backend and frontend in this terminal. Press Ctrl+C to stop both." -Color Cyan

  $backend = Start-ManagedProcess -Name "backend" -FilePath $pythonExe -Arguments $backendArgs -WorkingDirectory $agentRoot
  $frontend = Start-ManagedProcess -Name "frontend" -FilePath "cmd.exe" -Arguments $frontendArgs -WorkingDirectory $frontendRoot

  Write-PrefixedLine -Prefix "system" -Message "Backend: http://127.0.0.1:8000  Frontend: http://127.0.0.1:5173" -Color Yellow

  while ($true) {
    if ($script:stopRequested) {
      Write-PrefixedLine -Prefix "system" -Message "Interrupt received; cleaning up child processes." -Color DarkYellow
      break
    }

    $exited = $script:managedProcesses | Where-Object { $_.Process.HasExited }
    if ($exited.Count -gt 0) {
      $firstExited = $exited[0]
      Write-PrefixedLine -Prefix "system" -Message "$($firstExited.Name) exited; stopping remaining processes." -Color DarkYellow
      break
    }

    Start-Sleep -Seconds 1
  }
}
catch [System.Management.Automation.PipelineStoppedException] {
  Write-PrefixedLine -Prefix "system" -Message "Interrupt received; cleaning up child processes." -Color DarkYellow
}
finally {
  [Console]::remove_CancelKeyPress($cancelHandler)
  Stop-ManagedProcesses
}
