param([string]$ModelName = 'qwen3:4b')
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runtimeRoot = Join-Path $projectRoot '.runtime\ollama'
$ollamaExecutable = Join-Path $runtimeRoot 'bin\ollama.exe'
if (-not (Test-Path -LiteralPath $ollamaExecutable)) { throw 'Execute setup-ollama.ps1 -SkipPull primeiro.' }
$revision = 'bc640142c66e1fdd12af0bd68f40445458f3869b'
$expectedHash = '7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5'
$sourceUrl = "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/$revision/Qwen3-4B-Q4_K_M.gguf"
$weights = Join-Path $runtimeRoot 'Qwen3-4B-Q4_K_M.gguf'
if (-not (Test-Path -LiteralPath $weights) -or (Get-Item -LiteralPath $weights).Length -ne 2497280256) {
    Write-Output 'Baixando GGUF Q4_K_M oficial da Qwen, revisão fixada (aproximadamente 2,5 GB).'
    $downloadUrl = $sourceUrl + '?download=true&rotavital=' + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    & curl.exe --fail --location --silent --show-error --retry 2 --output $weights $downloadUrl
    if ($LASTEXITCODE -ne 0) { throw 'Falha no download do GGUF.' }
}
if ((Get-FileHash -LiteralPath $weights -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) {
    throw 'O SHA-256 do GGUF não corresponde ao arquivo oficial.'
}
$modelFile = Join-Path $runtimeRoot 'Modelfile.qwen3'
$portableWeights = $weights.Replace('\', '/')
[IO.File]::WriteAllText($modelFile, "FROM `"$portableWeights`"`nPARAMETER num_ctx 8192`n")
$env:OLLAMA_HOST = '127.0.0.1:11434'
& $ollamaExecutable create $ModelName -f $modelFile > (Join-Path $runtimeRoot 'model-import.log') 2>&1
if ($LASTEXITCODE -ne 0) { throw 'Falha na importação. Consulte .runtime/ollama/model-import.log.' }
$tags = Invoke-RestMethod -Uri http://127.0.0.1:11434/api/tags -TimeoutSec 10
$model = $tags.models | Where-Object { $_.name -eq $ModelName }
$manifest = [ordered]@{
    schema_version=1; model=$ModelName; source_url=$sourceUrl; source_revision=$revision;
    weights_sha256=$expectedHash; model_digest=$model.digest; quantization='Q4_K_M';
    license='Apache-2.0 (Qwen official repository)'; imported_at_utc=[DateTimeOffset]::UtcNow.ToString('o')
}
[IO.File]::WriteAllText((Join-Path $runtimeRoot 'imported-model-manifest.json'), ($manifest | ConvertTo-Json))
Write-Output "Modelo local importado e verificado: $ModelName"
