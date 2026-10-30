param([switch]$Detached)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskOutput = Join-Path $taskRoot 'outputs'
$taskPython = (Get-Command python.exe -ErrorAction Stop).Source
$taskUrl = 'http://127.0.0.1:8768/stage0.html'

if (-not (Test-Path -LiteralPath (Join-Path $taskOutput 'stage0.html'))) {
    throw 'Missing outputs/stage0.html. Run python -m app.baseline first.'
}

$taskAlreadyReady = $false
try {
    $taskExisting = Invoke-WebRequest -Uri $taskUrl -UseBasicParsing -TimeoutSec 2
    $taskAlreadyReady = $taskExisting.StatusCode -eq 200 -and $taskExisting.Content -match 'SUPPORTDESK /'
} catch { }
if (-not $taskAlreadyReady) {
    $taskPythonWindowless = Join-Path (Split-Path -Parent $taskPython) 'pythonw.exe'
    if (Test-Path -LiteralPath $taskPythonWindowless) { $taskPython = $taskPythonWindowless }
    $taskServer = Join-Path $PSScriptRoot 'serve_preview.py'
    if ($Detached) {
        # Windows creates this process independently of the temporary chat shell.
        $taskCommand = '"' + $taskPython + '" "' + $taskServer + '"'
        $taskCreated = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
            CommandLine = $taskCommand; CurrentDirectory = $taskRoot
        }
        if ($taskCreated.ReturnValue -ne 0) { throw ('Detached preview failed: ' + $taskCreated.ReturnValue) }
    } else {
        Start-Process -FilePath $taskPython -ArgumentList ('"' + $taskServer + '"') `
          -WorkingDirectory $taskRoot -WindowStyle Hidden | Out-Null
    }
}

$taskReady = $false
for ($taskAttempt = 0; $taskAttempt -lt 20; $taskAttempt++) {
    try {
        $taskResponse = Invoke-WebRequest -Uri $taskUrl -UseBasicParsing -TimeoutSec 2
        if ($taskResponse.StatusCode -eq 200 -and $taskResponse.Content -match 'SUPPORTDESK /') {
            $taskReady = $true
            break
        }
    } catch { }
    Start-Sleep -Milliseconds 250
}
if (-not $taskReady) {
    throw 'Preview did not start. Check outputs/preview.log or open outputs/stage0.html directly.'
}
Write-Output ('Preview ready: ' + $taskUrl)
Write-Output ('Offline report: ' + (Join-Path $taskOutput 'stage0.html'))
