param(
    [switch]$NoBrowser,
    [int]$Port = 0,
    [string]$ListenHost = '127.0.0.1'
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Get-MusicBotPort {
    $files = @(
        (Join-Path $root 'Cache\Data\config.json'),
        (Join-Path $root 'bot\config.default.json')
    )
    foreach ($file in $files) {
        if (-not (Test-Path -LiteralPath $file)) { continue }
        try {
            $config = Get-Content -LiteralPath $file -Raw | ConvertFrom-Json
            if ($config.server.port) { return [int]$config.server.port }
        } catch {
            Write-Warning "Cannot read port from $file"
        }
    }
    return 7001
}

function Test-MusicBot([string]$Url) {
    try {
        $state = Invoke-RestMethod -Uri "$Url/api/state" -TimeoutSec 1
        return $null -ne $state.system.node
    } catch {
        return $false
    }
}

$node = Get-Command node.exe -ErrorAction SilentlyContinue
if (-not $node) { $node = Get-Command node -ErrorAction SilentlyContinue }
if (-not $node) {
    throw 'Node.js was not found. Install Node.js 18 or newer and try again.'
}

if (-not (Test-Path -LiteralPath (Join-Path $root 'node_modules\express\package.json'))) {
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npm) { $npm = Get-Command npm -ErrorAction SilentlyContinue }
    if (-not $npm) { throw 'npm was not found.' }
    Write-Host 'Installing MusicBot dependencies...'
    & $npm.Source install
    if ($LASTEXITCODE -ne 0) { throw "npm install failed with exit code $LASTEXITCODE" }
}

$listenPort = if ($Port -gt 0) { $Port } else { Get-MusicBotPort }
$healthHost = if ($ListenHost -in @('0.0.0.0', '::', '[::]')) { '127.0.0.1' } else { $ListenHost }
$healthUrl = "http://${healthHost}:$listenPort"
$publicUrl = "http://${ListenHost}:$listenPort"
if (Test-MusicBot $healthUrl) {
    Write-Host "MusicBot is already running at $publicUrl"
    if (-not $NoBrowser) { Start-Process $healthUrl }
    exit 0
}

if (-not $env:MUSICBOT_MAX_RSS_MB) { $env:MUSICBOT_MAX_RSS_MB = '500' }

Write-Host "Starting MusicBot at $publicUrl"
$previousHost = $env:HOST
$previousPort = $env:PORT
$env:HOST = $ListenHost
$env:PORT = [string]$listenPort
$process = Start-Process `
    -FilePath $node.Source `
    -ArgumentList @('--expose-gc', '--max-old-space-size=384', 'bot/server.js') `
    -WorkingDirectory $root `
    -NoNewWindow `
    -PassThru

try {
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt += 1) {
        if ($process.HasExited) {
            throw "MusicBot exited during startup with code $($process.ExitCode)."
        }
        if (Test-MusicBot $healthUrl) {
            $ready = $true
            break
        }
        Start-Sleep -Milliseconds 500
    }

    if (-not $ready) { throw "MusicBot did not become ready at $healthUrl within 30 seconds." }

    Write-Host "MusicBot is ready. Close this window to stop it."
    if (-not $NoBrowser) { Start-Process $url }
    while (-not $process.WaitForExit(1000)) { }
    exit $process.ExitCode
} finally {
    if ($null -eq $previousHost) {
        Remove-Item Env:HOST -ErrorAction SilentlyContinue
    } else {
        $env:HOST = $previousHost
    }
    if ($null -eq $previousPort) {
        Remove-Item Env:PORT -ErrorAction SilentlyContinue
    } else {
        $env:PORT = $previousPort
    }
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
}
