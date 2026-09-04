[CmdletBinding()]
param(
    [switch]$SkipDependencies,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$listenerRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$modelRoot = Join-Path $listenerRoot 'data\speech_models'
$packages = @(
    @{
        Name = 'Streaming Zipformer bilingual ASR'
        Directory = 'sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20'
        Archive = 'streaming-zipformer.tar.bz2'
        Url = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2'
    },
    @{
        Name = 'SenseVoice INT8'
        Directory = 'sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17'
        Archive = 'sense-voice.tar.bz2'
        Url = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2'
    },
    @{
        Name = 'MeloTTS Chinese and English'
        Directory = 'vits-melo-tts-zh_en'
        Archive = 'vits-melo.tar.bz2'
        Url = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-melo-tts-zh_en.tar.bz2'
    }
)

New-Item -ItemType Directory -Force -Path $modelRoot | Out-Null

if (-not $SkipDependencies) {
    & python -m pip install -r (Join-Path $listenerRoot 'requirements-speech.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Failed to install speech dependencies.' }
}

foreach ($package in $packages) {
    $target = Join-Path $modelRoot $package.Directory
    if ((Test-Path -LiteralPath $target) -and -not $Force) {
        Write-Host "$($package.Name) already exists: $target"
        continue
    }
    $archive = Join-Path $modelRoot $package.Archive
    Write-Host "Downloading $($package.Name)..."
    & curl.exe -L --fail --retry 3 --output $archive $package.Url
    if ($LASTEXITCODE -ne 0) { throw "Failed to download $($package.Name)." }
    & tar -xjf $archive -C $modelRoot
    if ($LASTEXITCODE -ne 0) { throw "Failed to extract $($package.Name)." }
    Remove-Item -LiteralPath $archive
}

Write-Host ''
Write-Host "Speech models are ready in $modelRoot"
Write-Host 'Start LiveMngSys, then open GUIDemo > Running > Configuration > Speech Lab.'
