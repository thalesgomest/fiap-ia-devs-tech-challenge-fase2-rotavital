param([string]$Model = 'qwen3:4b', [switch]$SkipPull)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runtimeRoot = Join-Path $projectRoot '.runtime\ollama'
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
$ollamaExecutable = Join-Path $runtimeRoot 'bin\ollama.exe'
$archive = Join-Path $runtimeRoot 'ollama-windows-amd64.zip'
$releaseBase = 'https://github.com/ollama/ollama/releases/download/v0.40.4'
if (-not (Test-Path -LiteralPath $ollamaExecutable)) {
    $checksums = Invoke-RestMethod -Uri "$releaseBase/sha256sum.txt" -TimeoutSec 40
    $checksumLine = ($checksums -split "`n" | Where-Object { $_ -match '\s+\*?(?:\./)?ollama-windows-amd64\.zip\s*$' })
    if (@($checksumLine).Count -ne 1) { throw 'Checksum oficial do arquivo não encontrado.' }
    $expectedHash = ($checksumLine.Trim() -split '\s+')[0]
    if (-not (Test-Path -LiteralPath $archive)) {
        Write-Output 'Baixando a distribuição portátil oficial do Ollama (aproximadamente 1,5 GB).'
        & curl.exe --fail --location --silent --show-error --retry 2 --output $archive "$releaseBase/ollama-windows-amd64.zip"
        if ($LASTEXITCODE -ne 0) { throw 'Falha no download do Ollama.' }
    }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash.ToLowerInvariant()) {
        throw 'O SHA-256 do arquivo não corresponde ao checksum oficial.'
    }
    Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $runtimeRoot 'bin') -Force
    [IO.File]::WriteAllText((Join-Path $runtimeRoot 'version.txt'), "Ollama v0.40.4`nSHA256 $expectedHash`n")
}
$env:OLLAMA_MODELS = Join-Path $runtimeRoot 'models'
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_NO_CLOUD = '1'
try {
    $serverVersion = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 3
} catch {
    Start-Process -FilePath $ollamaExecutable -ArgumentList 'serve' -WindowStyle Hidden -WorkingDirectory $runtimeRoot -RedirectStandardOutput (Join-Path $runtimeRoot 'server.stdout.log') -RedirectStandardError (Join-Path $runtimeRoot 'server.stderr.log') | Out-Null
    $serverVersion = $null
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Seconds 1
        try { $serverVersion = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2; break } catch { }
    }
    if ($null -eq $serverVersion) { throw 'O servidor Ollama não respondeu. Consulte .runtime/ollama/server.stderr.log.' }
}
Write-Output "Ollama disponível: $($serverVersion.version), em http://127.0.0.1:11434"
if (-not $SkipPull) {
    $existingModels = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 10
    if ($existingModels.models | Where-Object { $_.name -eq $Model }) {
        Write-Output "Modelo local já disponível: $Model"
        return
    }
    if ($Model -eq 'qwen3:4b') {
        # Nome do modelo não fixa quantização/revisão. Importar o GGUF verificado.
        & (Join-Path $PSScriptRoot 'import-qwen.ps1') -ModelName $Model
        return
    }
    Write-Output "Preparando o modelo local $Model."
    try {
        $pullBody = @{model=$Model; stream=$false} | ConvertTo-Json
        Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:11434/api/pull' -ContentType 'application/json' -Body $pullBody -TimeoutSec 2400 | Out-Null
    } catch {
        if ($Model -eq 'qwen3:4b') {
            Write-Output 'O registro falhou; usando o GGUF oficial da Qwen com hash e revisão fixados.'
            & (Join-Path $PSScriptRoot 'import-qwen.ps1') -ModelName $Model
        } else { throw 'Falha ao preparar o modelo.' }
    }
}
