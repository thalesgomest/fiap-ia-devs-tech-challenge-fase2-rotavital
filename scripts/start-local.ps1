param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $projectRoot
$pythonExecutable = Join-Path $projectRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) {
    throw 'Prepare o ambiente primeiro: py -3.11 scripts/tasks.py setup'
}
& (Join-Path $PSScriptRoot 'setup-ollama.ps1')
try {
    $existingApp = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/openapi.json" -TimeoutSec 3
    if ($existingApp.info.title -eq 'RotaVital API') {
        Write-Output "RotaVital já está ativo em http://127.0.0.1:$Port"
        return
    }
} catch { }
Write-Output "RotaVital: http://127.0.0.1:$Port (Ctrl+C para encerrar o aplicativo)."
& $pythonExecutable -X utf8 -m uvicorn rotavital.api.main:app --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
