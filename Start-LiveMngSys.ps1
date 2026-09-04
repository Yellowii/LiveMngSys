param(
    [switch]$NoBrowser,
    [switch]$ShowTerminals
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$serviceConfig = Get-Content -LiteralPath (Join-Path $root 'config\service.json') -Raw | ConvertFrom-Json
$GuiPort = [int]$serviceConfig.port
$musicBotBindHost = [string]$serviceConfig.musicBot.host
$musicBotPort = [int]$serviceConfig.musicBot.port
$listenerBindHost = [string]$serviceConfig.douyinListener.host
$listenerPort = [int]$serviceConfig.douyinListener.port
$speechAsrEnabled = [bool]$serviceConfig.speechAsr.enabled
$speechAsrBindHost = [string]$serviceConfig.speechAsr.host
$speechAsrPort = [int]$serviceConfig.speechAsr.port
$translationEnabled = [bool]$serviceConfig.translation.enabled
$translationBindHost = [string]$serviceConfig.translation.host
$translationPort = [int]$serviceConfig.translation.port

function Get-HealthHost([string]$BindHost) {
    if ($BindHost -in @('0.0.0.0', '::', '[::]')) { return '127.0.0.1' }
    return $BindHost
}

$musicBotHealthHost = Get-HealthHost $musicBotBindHost
$listenerHealthHost = Get-HealthHost $listenerBindHost
$speechAsrHealthHost = Get-HealthHost $speechAsrBindHost
$translationHealthHost = Get-HealthHost $translationBindHost

function Test-MusicBot([string]$Url) {
    try {
        $state = Invoke-RestMethod -Uri "$Url/api/state" -TimeoutSec 1
        return $null -ne $state.system.node
    } catch {
        return $false
    }
}

function Test-GuiServer([string]$Url) {
    try {
        $health = Invoke-RestMethod -Uri "$Url/health" -TimeoutSec 1
        if ($health.service -ne 'livemngsys-gui' -or $health.status -ne 'ok') { return $false }
        $state = Invoke-RestMethod -Uri "$Url/api/livemngsys/live/state" -TimeoutSec 1
        return $null -ne $state.status.state
    } catch {
        return $false
    }
}

function Test-DouyinListener([string]$Url) {
    try {
        $health = Invoke-RestMethod -Uri "$Url/health" -TimeoutSec 1
        return $health.service -eq 'douyin-listener' -and $health.status -eq 'ok'
    } catch {
        return $false
    }
}

function Test-SpeechAsr([string]$Url) {
    try {
        $health = Invoke-RestMethod -Uri "$Url/health" -TimeoutSec 1
        return $health.service -eq 'sherpa-asr' -and $health.status -eq 'ok'
    } catch {
        return $false
    }
}

function Test-TranslationServer([string]$Url) {
    try {
        $health = Invoke-RestMethod -Uri "$Url/health" -TimeoutSec 1
        return $health.status -eq 'ok'
    } catch {
        return $false
    }
}

function Stop-StaleGuiServer([string]$ScriptPath) {
    try {
        $escapedPath = [regex]::Escape($ScriptPath)
        Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" |
            Where-Object { $_.CommandLine -and $_.CommandLine -match $escapedPath } |
            ForEach-Object {
                Write-Host "Stopping stale LiveMngSys gateway process $($_.ProcessId)."
                Stop-Process -Id ([int]$_.ProcessId) -Force -ErrorAction SilentlyContinue
            }
    } catch {
        Write-Warning "Cannot inspect stale gateway process: $($_.Exception.Message)"
    }
}

function Get-LanIPv4 {
    try {
        $address = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object {
                $_.IPAddress -notlike '127.*' -and
                $_.IPAddress -notlike '169.254.*' -and
                $_.PrefixOrigin -ne 'WellKnown'
            } |
            Sort-Object InterfaceIndex |
            Select-Object -First 1 -ExpandProperty IPAddress
        if ($address) { return $address }
    } catch {
        Write-Warning "Cannot detect LAN IPv4 address: $($_.Exception.Message)"
    }
    return '127.0.0.1'
}

$windowStyle = if ($ShowTerminals) { 'Normal' } else { 'Hidden' }
$musicBotScript = Join-Path $root 'MusicBot\Start-MusicBot.ps1'
if (-not (Test-Path -LiteralPath $musicBotScript)) {
    throw "Missing MusicBot launcher: $musicBotScript"
}

$url = "http://${musicBotHealthHost}:$musicBotPort"

if (-not (Test-MusicBot $url)) {
    $musicBotRunner = Start-Process powershell.exe -WindowStyle $windowStyle -PassThru -WorkingDirectory (Join-Path $root 'MusicBot') -ArgumentList @(
        '-NoProfile',
        '-ExecutionPolicy',
        'Bypass',
        '-File',
        $musicBotScript,
        '-NoBrowser',
        '-Port',
        [string]$musicBotPort,
        '-ListenHost',
        $musicBotBindHost
    )

    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt += 1) {
        if ($musicBotRunner.HasExited -and -not (Test-MusicBot $url)) {
            throw "MusicBot exited during startup with code $($musicBotRunner.ExitCode)."
        }
        if (Test-MusicBot $url) {
            $ready = $true
            break
        }
        Start-Sleep -Milliseconds 500
    }

    if (-not $ready) {
        throw "MusicBot did not become ready at $url within 30 seconds."
    }
}

$python = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if (-not $python) { $python = Get-Command py.exe -ErrorAction SilentlyContinue }
if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $python) {
    throw 'Python 3 was not found. Install Python 3.10 or newer and try again.'
}

if ($speechAsrEnabled) {
    $speechAsrScript = Join-Path $root 'DouyinListener\speech_asr_service.py'
    $speechAsrUrl = "http://${speechAsrHealthHost}:$speechAsrPort"
    $speechAsrArguments = @('--host', $speechAsrBindHost, '--port', [string]$speechAsrPort)
    $listenerSpeechConfigPath = Join-Path $root 'DouyinListener\data\config.json'
    if (Test-Path -LiteralPath $listenerSpeechConfigPath) {
        try {
            $listenerSpeechConfig = Get-Content -LiteralPath $listenerSpeechConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $streamingModel = [string]$listenerSpeechConfig.speech.asr.streamingModel
            if ($streamingModel) {
                $streamingRoot = Join-Path $root 'DouyinListener\data\speech_models' $streamingModel
                if (Test-Path -LiteralPath $streamingRoot) {
                    $encoder = Get-ChildItem -LiteralPath $streamingRoot -Filter 'encoder-*.onnx' -File | Sort-Object Name | Select-Object -First 1
                    $decoder = Get-ChildItem -LiteralPath $streamingRoot -Filter 'decoder-*.onnx' -File | Sort-Object Name | Select-Object -First 1
                    $joiner = Get-ChildItem -LiteralPath $streamingRoot -Filter 'joiner-*.onnx' -File | Sort-Object Name | Select-Object -First 1
                    $tokens = Join-Path $streamingRoot 'tokens.txt'
                    if ($encoder -and $decoder -and $joiner -and (Test-Path -LiteralPath $tokens)) {
                        $speechAsrArguments += @('--tokens', $tokens, '--encoder', $encoder.FullName, '--decoder', $decoder.FullName, '--joiner', $joiner.FullName)
                    }
                }
            }
        } catch { Write-Warning "Could not read saved streaming ASR model: $($_.Exception.Message)" }
    }
    if (-not (Test-Path -LiteralPath $speechAsrScript)) {
        Write-Warning "Speech ASR service is enabled but missing: $speechAsrScript"
    } elseif (-not (Test-SpeechAsr $speechAsrUrl)) {
        $speechAsrRunner = Start-Process `
            -FilePath $python.Source `
            -ArgumentList (@($speechAsrScript) + $speechAsrArguments) `
            -WorkingDirectory (Join-Path $root 'DouyinListener') `
            -WindowStyle $windowStyle `
            -PassThru
        $speechAsrReady = $false
        for ($attempt = 0; $attempt -lt 120; $attempt += 1) {
            if ($speechAsrRunner.HasExited) { break }
            if (Test-SpeechAsr $speechAsrUrl) {
                $speechAsrReady = $true
                break
            }
            Start-Sleep -Milliseconds 500
        }
        if (-not $speechAsrReady) {
            Write-Warning "Speech ASR did not become ready at $speechAsrUrl. Other LiveMngSys services will continue."
        }
    }
}

if ($translationEnabled) {
    $translationExe = Join-Path $root ([string]$serviceConfig.translation.executable)
    $translationModel = Join-Path $root ([string]$serviceConfig.translation.model)
    $listenerSpeechConfigPath = Join-Path $root 'DouyinListener\data\config.json'
    if (Test-Path -LiteralPath $listenerSpeechConfigPath) {
        try {
            $listenerSpeechConfig = Get-Content -LiteralPath $listenerSpeechConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $savedModel = [string]$listenerSpeechConfig.speech.translation.model
            if ($savedModel -and (Test-Path -LiteralPath $savedModel)) {
                $translationModel = (Resolve-Path -LiteralPath $savedModel).Path
            } elseif ($savedModel -and (Test-Path -LiteralPath (Join-Path $root $savedModel))) {
                $translationModel = (Resolve-Path -LiteralPath (Join-Path $root $savedModel)).Path
            }
        } catch {
            Write-Warning "Could not read saved speech model selection: $($_.Exception.Message)"
        }
    }
    $translationUrl = "http://${translationHealthHost}:$translationPort"
    if (-not (Test-Path -LiteralPath $translationExe)) {
        Write-Warning "Translation server is enabled but llama-server is missing: $translationExe"
    } elseif (-not (Test-Path -LiteralPath $translationModel)) {
        Write-Warning "Translation server is enabled but the GGUF model is missing: $translationModel"
    } elseif (-not (Test-TranslationServer $translationUrl)) {
        $translationRunner = Start-Process `
            -FilePath $translationExe `
            -ArgumentList @('-m', $translationModel, '--host', $translationBindHost, '--port', [string]$translationPort, '-c', [string]$serviceConfig.translation.contextSize, '-np', [string]$serviceConfig.translation.parallel) `
            -WorkingDirectory (Split-Path -Parent $translationExe) `
            -WindowStyle $windowStyle `
            -PassThru
        $translationReady = $false
        for ($attempt = 0; $attempt -lt 180; $attempt += 1) {
            if ($translationRunner.HasExited) { break }
            if (Test-TranslationServer $translationUrl) {
                $translationReady = $true
                break
            }
            Start-Sleep -Milliseconds 500
        }
        if (-not $translationReady) {
            Write-Warning "Translation server did not become ready at $translationUrl. ASR captions remain available."
        }
    }
}

$listenerScript = Join-Path $root 'DouyinListener\service.py'
if (-not (Test-Path -LiteralPath $listenerScript)) {
    throw "Missing Douyin listener service: $listenerScript"
}

$listenerUrl = "http://${listenerHealthHost}:$listenerPort"
if (-not (Test-DouyinListener $listenerUrl)) {
    $listenerRunner = Start-Process `
        -FilePath $python.Source `
        -ArgumentList @($listenerScript, '--host', $listenerBindHost, '--port', [string]$listenerPort) `
        -WorkingDirectory (Join-Path $root 'DouyinListener') `
        -WindowStyle $windowStyle `
        -PassThru

    $listenerReady = $false
    for ($attempt = 0; $attempt -lt 40; $attempt += 1) {
        if ($listenerRunner.HasExited -and -not (Test-DouyinListener $listenerUrl)) {
            throw "Douyin listener exited during startup with code $($listenerRunner.ExitCode)."
        }
        if (Test-DouyinListener $listenerUrl) {
            $listenerReady = $true
            break
        }
        Start-Sleep -Milliseconds 250
    }

    if (-not $listenerReady) {
        throw "Douyin listener did not become ready at $listenerUrl within 10 seconds."
    }
}

$node = Get-Command node.exe -ErrorAction SilentlyContinue
if (-not $node) { $node = Get-Command node -ErrorAction SilentlyContinue }
if (-not $node) {
    throw 'Node.js was not found. Install Node.js 18 or newer and try again.'
}

$guiServerScript = Join-Path $root 'WebServer\server.js'
if (-not (Test-Path -LiteralPath $guiServerScript)) {
    throw "Missing GUI server: $guiServerScript"
}

$guiHealthUrl = "http://127.0.0.1:$GuiPort"
$lanIp = Get-LanIPv4
$lanGuiUrl = "http://${lanIp}:$GuiPort"
if (-not (Test-GuiServer $guiHealthUrl)) {
    Stop-StaleGuiServer $guiServerScript
    $previousGuiPort = $env:LIVEMNGSYS_GUI_PORT
    $previousGuiHost = $env:LIVEMNGSYS_GUI_HOST
    $env:LIVEMNGSYS_GUI_PORT = [string]$GuiPort
    $env:LIVEMNGSYS_GUI_HOST = [string]$serviceConfig.host
    try {
        $guiRunner = Start-Process `
            -FilePath $node.Source `
            -ArgumentList @($guiServerScript) `
            -WorkingDirectory $root `
            -WindowStyle $windowStyle `
            -PassThru
    } finally {
        if ($null -eq $previousGuiPort) {
            Remove-Item Env:LIVEMNGSYS_GUI_PORT -ErrorAction SilentlyContinue
        } else {
            $env:LIVEMNGSYS_GUI_PORT = $previousGuiPort
        }
        if ($null -eq $previousGuiHost) {
            Remove-Item Env:LIVEMNGSYS_GUI_HOST -ErrorAction SilentlyContinue
        } else {
            $env:LIVEMNGSYS_GUI_HOST = $previousGuiHost
        }
    }

    $guiReady = $false
    for ($attempt = 0; $attempt -lt 40; $attempt += 1) {
        if ($guiRunner.HasExited -and -not (Test-GuiServer $guiHealthUrl)) {
            throw "GUI server exited during startup with code $($guiRunner.ExitCode)."
        }
        if (Test-GuiServer $guiHealthUrl) {
            $guiReady = $true
            break
        }
        Start-Sleep -Milliseconds 250
    }

    if (-not $guiReady) {
        throw "GUI server did not become ready at $guiHealthUrl within 10 seconds."
    }
}

if (-not $NoBrowser) {
    Start-Process ($lanGuiUrl + '/GUIDemo/')
}

Write-Host "LiveMngSys is ready at $lanGuiUrl/GUIDemo/"
Write-Host "LAN GUI: $lanGuiUrl/GUIDemo/"
Write-Host "MusicBot gateway: $lanGuiUrl/musicbot/"
Write-Host "Douyin listener API: $lanGuiUrl/api/livemngsys/live/state"
if ($speechAsrEnabled) { Write-Host "Streaming ASR: http://${speechAsrHealthHost}:$speechAsrPort" }
if ($translationEnabled) { Write-Host "Translation server: http://${translationHealthHost}:$translationPort" }
