param([switch]$Detached)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = (Get-Command python.exe -ErrorAction Stop).Source
$taskUrl = 'http://127.0.0.1:8767/health'
$taskReady = $false
try {
    $taskHealth = Invoke-RestMethod -Uri $taskUrl -TimeoutSec 2
    $taskReady = $taskHealth.project -eq 'supportdesk-english-v1' -and $taskHealth.database -eq 'postgresql' -and $taskHealth.counts.segments -gt 0
} catch { }
if (-not $taskReady) {
    if (-not (Test-Path -LiteralPath (Join-Path $taskRoot '.local/pgdata/PG_VERSION'))) {
        & $taskPython (Join-Path $PSScriptRoot 'setup_postgres.py')
        if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL setup failed.' }
    }
    $taskPythonWindowless = Join-Path (Split-Path -Parent $taskPython) 'pythonw.exe'
    if (Test-Path -LiteralPath $taskPythonWindowless) { $taskPython = $taskPythonWindowless }
    $taskServer = Join-Path $PSScriptRoot 'run_stage1.py'
    if ($Detached) {
        $taskCommand = '"' + $taskPython + '" "' + $taskServer + '"'
        $taskCreated = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
            CommandLine = $taskCommand; CurrentDirectory = $taskRoot
        }
        if ($taskCreated.ReturnValue -ne 0) { throw ('Stage 1 launch failed: ' + $taskCreated.ReturnValue) }
    } else {
        Start-Process -FilePath $taskPython -ArgumentList ('"' + $taskServer + '"') `
            -WorkingDirectory $taskRoot -WindowStyle Hidden | Out-Null
    }
    for ($taskAttempt = 0; $taskAttempt -lt 40; $taskAttempt++) {
        try {
            $taskHealth = Invoke-RestMethod -Uri $taskUrl -TimeoutSec 2
            if ($taskHealth.project -eq 'supportdesk-english-v1' -and $taskHealth.database -eq 'postgresql' -and $taskHealth.counts.segments -gt 0) {
                $taskReady = $true
                break
            }
        } catch { }
        Start-Sleep -Milliseconds 250
    }
}
if (-not $taskReady) { throw 'Stage 1 is not ready. Check outputs/stage1-server.log.' }
Write-Output 'SupportDesk ready: http://127.0.0.1:8767/'
