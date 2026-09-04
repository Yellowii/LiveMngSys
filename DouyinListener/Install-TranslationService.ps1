[CmdletBinding()]
param([switch]$Force)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$toolRoot = Join-Path $root 'tools\llama.cpp'
$modelRoot = Join-Path $root 'DouyinListener\data\speech_models'
$modelPath = Join-Path $modelRoot 'HY-MT1.5-1.8B-Q4_K_M.gguf'

New-Item -ItemType Directory -Force -Path $toolRoot, $modelRoot | Out-Null
if ($Force -or -not (Test-Path -LiteralPath (Join-Path $toolRoot 'llama-server.exe'))) {
    $releases = Invoke-RestMethod 'https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=30'
    $asset = $null
    foreach ($release in $releases) {
        $asset = $release.assets | Where-Object { $_.name -match '^llama-b\d+-bin-win-cpu-x64\.zip$' } | Select-Object -First 1
        if ($asset) { break }
    }
    if (-not $asset) { throw 'No Windows x64 CPU llama.cpp release was found.' }
    $archive = Join-Path $env:TEMP $asset.name
    curl.exe -L --fail --retry 3 -o $archive $asset.browser_download_url
    if ($LASTEXITCODE -ne 0) { throw 'Failed to download llama.cpp.' }
    Expand-Archive -LiteralPath $archive -DestinationPath $toolRoot -Force
    Remove-Item -LiteralPath $archive
}

if ($Force -or -not (Test-Path -LiteralPath $modelPath)) {
    curl.exe -L --fail --retry 3 -o $modelPath 'https://huggingface.co/tencent/HY-MT1.5-1.8B-GGUF/resolve/main/HY-MT1.5-1.8B-Q4_K_M.gguf'
    if ($LASTEXITCODE -ne 0) { throw 'Failed to download HY-MT GGUF.' }
}

Write-Host "llama.cpp: $toolRoot"
Write-Host "HY-MT model: $modelPath"
Write-Host 'Translation will start with LiveMngSys when config/service.json translation.enabled is true.'
