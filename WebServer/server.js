const fs = require('fs')
const http = require('http')
const net = require('net')
const os = require('os')
const path = require('path')
const { performance } = require('perf_hooks')
const { execFile, execFileSync, spawn } = require('child_process')

const root = path.resolve(__dirname, '..')
const serviceConfigFile = path.join(root, 'config', 'service.json')
const serviceConfig = JSON.parse(fs.readFileSync(serviceConfigFile, 'utf8'))
const host = process.env.LIVEMNGSYS_GUI_HOST || serviceConfig.host || '0.0.0.0'
const port = Number(process.env.LIVEMNGSYS_GUI_PORT || serviceConfig.port || 7000)
const musicBotBindHost = process.env.LIVEMNGSYS_MUSICBOT_HOST || serviceConfig.musicBot?.host || '0.0.0.0'
const musicBotPort = Number(process.env.LIVEMNGSYS_MUSICBOT_PORT || serviceConfig.musicBot?.port || 7001)
const musicBotPublicPath = serviceConfig.musicBot?.publicPath || '/musicbot'
const listenerBindHost = process.env.LIVEMNGSYS_LISTENER_HOST || serviceConfig.douyinListener?.host || '0.0.0.0'
const listenerPort = Number(process.env.LIVEMNGSYS_LISTENER_PORT || serviceConfig.douyinListener?.port || 7002)
const listenerApiPath = serviceConfig.douyinListener?.apiPath || '/api/livemngsys/live'
const listenerWsPath = serviceConfig.douyinListener?.wsPath || '/live-ws'
const guiPublicPath = '/GUIDemo'
const futureApiPrefix = serviceConfig.api?.futurePrefix || '/api/livemngsys'
const servicePortsPath = futureApiPrefix + '/service/ports'
const systemMetricsPath = futureApiPrefix + '/system/metrics'
const systemControlPath = futureApiPrefix + '/system/control'
const liveUiConfigPath = futureApiPrefix + '/live-ui/config'
const liveUiConfigFile = path.join(root, 'config', 'live-ui.json')
const projectRoot = root.replace(/'/g, "''")
const terminalExitFile = path.join(root, 'tmp', '.terminal-monitor.stop')

// Wildcard addresses are valid bind targets but never valid proxy destinations.
const localProxyHost = host => ['0.0.0.0', '::', '[::]'].includes(String(host || '').trim()) ? '127.0.0.1' : host
const musicBotHost = localProxyHost(musicBotBindHost)
const listenerHost = localProxyHost(listenerBindHost)

let previousProcessCpu = new Map()
let previousProcessSampleAt = Date.now()
let terminalMonitor = null
let projectMetricsCache = { project: { cpuPercent: 0, memoryBytes: 0, processCount: 0 }, services: [], error: '' }
let projectMetricsRefresh = null

function cpuSnapshot() {
  return os.cpus().reduce((summary, cpu) => {
    const times = cpu.times
    summary.idle += times.idle
    summary.total += times.user + times.nice + times.sys + times.idle + times.irq
    return summary
  }, { idle: 0, total: 0 })
}

let previousCpuSnapshot = cpuSnapshot()
let previousEventLoop = performance.eventLoopUtilization()

function getSystemMetrics() {
  const currentCpu = cpuSnapshot()
  const idleDelta = currentCpu.idle - previousCpuSnapshot.idle
  const totalDelta = currentCpu.total - previousCpuSnapshot.total
  previousCpuSnapshot = currentCpu
  const cpuPercent = totalDelta > 0 ? Math.max(0, Math.min(100, (1 - idleDelta / totalDelta) * 100)) : 0

  const currentEventLoop = performance.eventLoopUtilization(previousEventLoop)
  previousEventLoop = performance.eventLoopUtilization()
  const totalMemory = os.totalmem()
  const freeMemory = os.freemem()
  const processMemory = process.memoryUsage()

  return {
    ok: true,
    sampledAt: Date.now(),
    cpu: { percent: Number(cpuPercent.toFixed(1)), cores: os.cpus().length },
    memory: {
      total: totalMemory,
      used: totalMemory - freeMemory,
      percent: Number((((totalMemory - freeMemory) / totalMemory) * 100).toFixed(1))
    },
    gateway: {
      rss: processMemory.rss,
      heapUsed: processMemory.heapUsed,
      heapTotal: processMemory.heapTotal,
      eventLoopPercent: Number((currentEventLoop.utilization * 100).toFixed(1)),
      uptimeSeconds: Math.floor(process.uptime())
    },
    project: {
      cpuPercent: 0,
      memoryBytes: 0,
      processCount: 0,
      terminalVisible: Boolean(terminalMonitor)
    },
    services: []
  }
}

function execPowerShell(script) {
  return new Promise((resolve, reject) => {
    execFile('powershell.exe', ['-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script], {
      windowsHide: true,
      maxBuffer: 4 * 1024 * 1024,
      encoding: 'utf8'
    }, (error, stdout) => {
      if (error) {
        reject(error)
        return
      }
      try {
        resolve(JSON.parse(stdout.replace(/^\uFEFF/, '').trim() || '[]'))
      } catch (parseError) {
        parseError.message = `PowerShell process snapshot was not JSON: ${parseError.message}`
        reject(parseError)
      }
    })
  })
}

async function getProjectProcessMetrics() {
  const script = String.raw`
$root = '${projectRoot}'
$all = @(Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId, Name, CommandLine)
$rules = @(
  @{ name = 'gateway'; label = '主网关'; fragment = 'WebServer\server.js' },
  @{ name = 'musicbot'; label = 'MusicBot'; fragment = 'MusicBot\' },
  @{ name = 'douyin'; label = '抖音弹幕监听'; fragment = 'DouyinListener\' }
)
$selected = @()
foreach ($rule in $rules) {
  $roots = @($all | Where-Object { $_.CommandLine -and $_.CommandLine -like "*$($rule.fragment)*" })
  $ids = @($roots | ForEach-Object { [int]$_.ProcessId })
  $changed = $true
  while ($changed) {
    $changed = $false
    foreach ($item in $all) {
      if ($ids -contains [int]$item.ParentProcessId -and -not ($ids -contains [int]$item.ProcessId)) {
        $ids += [int]$item.ProcessId
        $changed = $true
      }
    }
  }
  foreach ($id in $ids) {
    $item = $all | Where-Object { [int]$_.ProcessId -eq $id } | Select-Object -First 1
    if (-not $item) { continue }
    try { $proc = Get-Process -Id $id -ErrorAction Stop } catch { continue }
    $selected += [pscustomobject]@{
      service = $rule.name
      label = $rule.label
      pid = $id
      parentPid = [int]$item.ParentProcessId
      name = [string]$item.Name
      commandLine = [string]$item.CommandLine
      cpuSeconds = [double]($proc.CPU)
      memoryBytes = [int64]$proc.WorkingSet64
    }
  }
}
$selected | ConvertTo-Json -Compress
`
  const raw = await execPowerShell(script)
  const rows = Array.isArray(raw) ? raw : (raw ? [raw] : [])
  const now = Date.now()
  const elapsed = Math.max(250, now - previousProcessSampleAt) / 1000
  const coreCount = Math.max(1, os.cpus().length)
  const currentCpu = new Map()
  const services = new Map()

  for (const row of rows) {
    const pid = Number(row.pid)
    const cpuSeconds = Number(row.cpuSeconds || 0)
    currentCpu.set(pid, cpuSeconds)
    const oldCpu = previousProcessCpu.get(pid)
    const cpuPercent = oldCpu === undefined ? 0 : Math.max(0, ((cpuSeconds - oldCpu) / elapsed / coreCount) * 100)
    const name = String(row.service || 'other')
    if (!services.has(name)) services.set(name, { name, label: String(row.label || name), cpuPercent: 0, memoryBytes: 0, processCount: 0, processes: [] })
    const service = services.get(name)
    service.cpuPercent += cpuPercent
    service.memoryBytes += Number(row.memoryBytes || 0)
    service.processCount += 1
    service.processes.push({ pid, name: row.name, cpuPercent: Number(cpuPercent.toFixed(1)), memoryBytes: Number(row.memoryBytes || 0) })
  }

  previousProcessCpu = currentCpu
  previousProcessSampleAt = now
  const serviceLabels = {
    gateway: '\u4e3b\u7f51\u5173',
    musicbot: 'MusicBot',
    douyin: '\u6296\u97f3\u5f39\u5e55\u76d1\u542c'
  }
  const list = [...services.values()].map(item => ({
    ...item,
    label: serviceLabels[item.name] || item.label,
    cpuPercent: Number(item.cpuPercent.toFixed(1))
  }))
  return {
    services: list,
    project: {
      cpuPercent: Number(list.reduce((sum, item) => sum + item.cpuPercent, 0).toFixed(1)),
      memoryBytes: list.reduce((sum, item) => sum + item.memoryBytes, 0),
      processCount: list.reduce((sum, item) => sum + item.processCount, 0)
    }
  }
}

function refreshProjectMetricsInBackground() {
  if (projectMetricsRefresh) return
  projectMetricsRefresh = getProjectProcessMetrics()
    .then(snapshot => { projectMetricsCache = { ...snapshot, error: '' } })
    .catch(error => { projectMetricsCache = { ...projectMetricsCache, error: `项目进程开销不可用: ${error.message}` } })
    .finally(() => { projectMetricsRefresh = null })
}

async function openTerminalMonitor() {
  if (terminalMonitor) return terminalMonitor.pid
  fs.mkdirSync(path.dirname(terminalExitFile), { recursive: true })
  fs.rmSync(terminalExitFile, { force: true })
  const exitFile = terminalExitFile.replace(/'/g, "''")
  const command = `Set-Location -LiteralPath '${projectRoot}'; while (-not (Test-Path -LiteralPath '${exitFile}')) { Clear-Host; Write-Host 'LiveMngSys running processes' -ForegroundColor Cyan; Write-Host ('Updated: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')) -ForegroundColor DarkGray; Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -like '*WebServer\\server.js*' -or $_.CommandLine -like '*MusicBot\\*' -or $_.CommandLine -like '*DouyinListener\\*') } | Select-Object ProcessId, Name, CommandLine | Format-Table -Wrap -AutoSize; Start-Sleep -Seconds 2 }; Remove-Item -LiteralPath '${exitFile}' -Force -ErrorAction SilentlyContinue`
  const encodedCommand = Buffer.from(command, 'utf16le').toString('base64')
  const wtPath = path.join(process.env.LOCALAPPDATA || '', 'Microsoft', 'WindowsApps', 'wt.exe')
  const terminal = spawn(wtPath, ['-w', 'LiveMngSysRuntime', 'new-tab', '--title', 'LiveMngSys Runtime', 'powershell.exe', '-NoLogo', '-NoProfile', '-EncodedCommand', encodedCommand], {
    detached: true,
    stdio: 'ignore',
    windowsHide: false
  })
  terminal.unref()
  terminalMonitor = { pid: terminal.pid }
  return terminalMonitor.pid
}

function closeTerminalMonitor() {
  if (!terminalMonitor) return false
  fs.mkdirSync(path.dirname(terminalExitFile), { recursive: true })
  fs.writeFileSync(terminalExitFile, 'stop', 'utf8')
  terminalMonitor = null
  return true
}

function stopProjectProcesses() {
  const pids = new Set([process.pid])
  try {
    const netstat = execFileSync('netstat.exe', ['-ano', '-p', 'tcp'], { encoding: 'utf8', windowsHide: true })
    for (const line of netstat.split(/\r?\n/)) {
      const match = line.match(/^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$/i)
      if (match && [7000, 7001, 7002].includes(Number(match[1]))) {
        pids.add(Number(match[2]))
      }
    }
  } catch {
    // The gateway PID is always present, so the close action still has a safe fallback.
  }
  const targets = [...pids].filter(Number.isInteger)
  setTimeout(() => {
    closeTerminalMonitor()
    for (const pid of targets) {
      if (pid === process.pid) continue
      spawn('taskkill.exe', ['/PID', String(pid), '/T', '/F'], {
        detached: true,
        stdio: 'ignore',
        windowsHide: true
      }).unref()
    }
    setTimeout(() => {
      spawn('taskkill.exe', ['/PID', String(process.pid), '/T', '/F'], {
        detached: true,
        stdio: 'ignore',
        windowsHide: true
      }).unref()
    }, 700)
  }, 700)
  return targets
}

function handleSystemControlRequest(req, res) {
  if (req.method !== 'POST') {
    send(res, 405, JSON.stringify({ ok: false, error: 'Method not allowed' }), 'application/json; charset=utf-8')
    return
  }
  let body = ''
  req.setEncoding('utf8')
  req.on('data', chunk => { body += chunk })
  req.on('end', async () => {
    try {
      const action = String((JSON.parse(body || '{}') || {}).action || '')
      if (action === 'showTerminal') {
        const pid = await openTerminalMonitor()
        send(res, 200, JSON.stringify({ ok: true, terminalVisible: true, pid }), 'application/json; charset=utf-8')
        return
      }
      if (action === 'hideTerminal') {
        closeTerminalMonitor()
        send(res, 200, JSON.stringify({ ok: true, terminalVisible: false }), 'application/json; charset=utf-8')
        return
      }
      if (action === 'stopProject') {
        const pids = await stopProjectProcesses()
        send(res, 200, JSON.stringify({ ok: true, stopping: true, pids }), 'application/json; charset=utf-8')
        return
      }
      send(res, 400, JSON.stringify({ ok: false, error: 'Unknown system action' }), 'application/json; charset=utf-8')
    } catch (error) {
      send(res, 500, JSON.stringify({ ok: false, error: error.message }), 'application/json; charset=utf-8')
    }
  })
}

const mimeTypes = {
  '.css': 'text/css; charset=utf-8',
  '.gif': 'image/gif',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.jpeg': 'image/jpeg',
  '.jpg': 'image/jpeg',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.mp3': 'audio/mpeg',
  '.ogg': 'audio/ogg',
  '.png': 'image/png',
  '.svg': 'image/svg+xml; charset=utf-8',
  '.wav': 'audio/wav',
  '.webp': 'image/webp',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2'
}

function send(res, statusCode, body, contentType = 'text/plain; charset=utf-8') {
  res.writeHead(statusCode, {
    'Content-Type': contentType,
    'Cache-Control': 'no-store'
  })
  res.end(body)
}

function resolveRequestPath(urlPath) {
  if (urlPath !== guiPublicPath && !urlPath.startsWith(`${guiPublicPath}/`)) return null
  const decodedPath = decodeURIComponent(urlPath)
  const publicRoot = path.join(root, guiPublicPath.slice(1))
  const relativePath = decodedPath.slice(guiPublicPath.length) || '/'
  const candidate = path.resolve(publicRoot, `.${relativePath}`)
  const normalizedRoot = publicRoot.toLowerCase()
  const normalizedCandidate = candidate.toLowerCase()

  if (normalizedCandidate !== normalizedRoot && !normalizedCandidate.startsWith(`${normalizedRoot}${path.sep}`)) {
    return null
  }

  return candidate
}

function getMusicBotTargetPath(pathname) {
  if (pathname === musicBotPublicPath || pathname === `${musicBotPublicPath}/`) return '/'
  return pathname.startsWith(`${musicBotPublicPath}/`)
    ? pathname.slice(musicBotPublicPath.length) || '/'
    : pathname
}

function isMusicBotHttpRequest(pathname) {
  return pathname === '/api' || pathname.startsWith('/api/') ||
    pathname === '/media' || pathname.startsWith('/media/') ||
    pathname === musicBotPublicPath || pathname.startsWith(`${musicBotPublicPath}/`)
}

function isFutureApiRequest(pathname) {
  return pathname === futureApiPrefix || pathname.startsWith(`${futureApiPrefix}/`)
}

function isListenerHttpRequest(pathname) {
  return pathname === listenerApiPath || pathname.startsWith(`${listenerApiPath}/`)
}

function getConfiguredPorts() {
  return {
    public: Number(serviceConfig.port),
    musicBot: Number(serviceConfig.musicBot?.port),
    douyinListener: Number(serviceConfig.douyinListener?.port)
  }
}

function validatePorts(ports) {
  const values = [ports.public, ports.musicBot, ports.douyinListener]
  if (values.some(value => !Number.isInteger(value) || value < 7000 || value > 7100)) {
    return '所有端口必须是 7000-7100 之间的整数'
  }
  if (new Set(values).size !== values.length) {
    return '主网关、MusicBot 和监听服务端口不能重复'
  }
  return ''
}

function readLiveUiConfig() {
  try {
    const saved = JSON.parse(fs.readFileSync(liveUiConfigFile, 'utf8'))
    return {
      revision: Math.max(0, Number(saved.revision) || 0),
      config: saved.config && typeof saved.config === 'object' && !Array.isArray(saved.config) ? saved.config : {}
    }
  } catch (error) {
    return { revision: 0, config: {} }
  }
}

function handleLiveUiConfigRequest(req, res) {
  if (req.method === 'GET') {
    const current = readLiveUiConfig()
    send(res, 200, JSON.stringify({ ok: true, ...current }), 'application/json; charset=utf-8')
    return
  }
  if (req.method !== 'PUT') {
    send(res, 405, JSON.stringify({ ok: false, error: 'Method not allowed' }), 'application/json; charset=utf-8')
    return
  }

  let body = ''
  req.setEncoding('utf8')
  req.on('data', chunk => {
    body += chunk
    if (body.length > 65536) req.destroy()
  })
  req.on('end', () => {
    try {
      const parsed = JSON.parse(body || '{}')
      if (!parsed.config || typeof parsed.config !== 'object' || Array.isArray(parsed.config)) {
        send(res, 400, JSON.stringify({ ok: false, error: '直播 UI 配置必须是对象' }), 'application/json; charset=utf-8')
        return
      }
      const current = readLiveUiConfig()
      const revision = current.revision + 1
      fs.writeFileSync(liveUiConfigFile, JSON.stringify({ revision, config: parsed.config }, null, 2) + '\n', 'utf8')
      send(res, 200, JSON.stringify({ ok: true, revision }), 'application/json; charset=utf-8')
    } catch (error) {
      send(res, 400, JSON.stringify({ ok: false, error: '直播 UI 配置必须是有效 JSON' }), 'application/json; charset=utf-8')
    }
  })
}

function handleServicePortsRequest(req, res) {
  const active = { public: port, musicBot: musicBotPort, douyinListener: listenerPort }
  if (req.method === 'GET') {
    send(res, 200, JSON.stringify({ ok: true, ports: getConfiguredPorts(), active }), 'application/json; charset=utf-8')
    return
  }
  if (req.method !== 'PUT') {
    send(res, 405, JSON.stringify({ ok: false, error: 'Method not allowed' }), 'application/json; charset=utf-8')
    return
  }

  let body = ''
  req.setEncoding('utf8')
  req.on('data', chunk => {
    body += chunk
    if (body.length > 65536) req.destroy()
  })
  req.on('end', () => {
    try {
      const parsed = JSON.parse(body || '{}')
      const ports = {
        public: Number(parsed.public),
        musicBot: Number(parsed.musicBot),
        douyinListener: Number(parsed.douyinListener)
      }
      const error = validatePorts(ports)
      if (error) {
        send(res, 400, JSON.stringify({ ok: false, error }), 'application/json; charset=utf-8')
        return
      }
      serviceConfig.port = ports.public
      serviceConfig.musicBot.port = ports.musicBot
      serviceConfig.douyinListener.port = ports.douyinListener
      fs.writeFileSync(serviceConfigFile, JSON.stringify(serviceConfig, null, 2) + '\n', 'utf8')
      send(res, 200, JSON.stringify({
        ok: true,
        ports,
        active,
        restartRequired: Object.keys(ports).some(key => ports[key] !== active[key])
      }), 'application/json; charset=utf-8')
    } catch (error) {
      send(res, 400, JSON.stringify({ ok: false, error: '端口配置必须是有效 JSON' }), 'application/json; charset=utf-8')
    }
  })
}

function proxyHttpRequest(req, res, targetPath, targetHost, targetPort, serviceName) {
  const headers = { ...req.headers, host: `${targetHost}:${targetPort}` }
  delete headers.connection

  let clientClosed = false
  const upstream = http.request({
    hostname: targetHost,
    port: targetPort,
    method: req.method,
    path: `${targetPath}${new URL(req.url, 'http://localhost').search}`,
    headers,
  }, (upstreamResponse) => {
    res.writeHead(upstreamResponse.statusCode || 502, upstreamResponse.headers)
    upstreamResponse.on('error', () => {
      if (!res.destroyed) res.destroy()
    })
    upstreamResponse.pipe(res)
  })

  upstream.on('error', () => {
    if (clientClosed) return
    if (!res.headersSent) send(res, 502, `${serviceName} unavailable`)
    else res.destroy()
  })
  const abortUpstream = () => {
    clientClosed = true
    if (!upstream.destroyed) upstream.destroy()
  }
  req.on('aborted', abortUpstream)
  req.on('error', abortUpstream)
  res.on('error', abortUpstream)
  res.on('close', () => {
    if (!res.writableFinished) abortUpstream()
  })
  if (req.method === 'GET' || req.method === 'HEAD') {
    req.resume()
    upstream.end()
  } else req.pipe(upstream)
}

function proxyMusicBotRequest(req, res, targetPath) {
  proxyHttpRequest(req, res, targetPath, musicBotHost, musicBotPort, 'MusicBot')
}

const server = http.createServer((req, res) => {
  let pathname

  try {
    pathname = new URL(req.url, `http://${req.headers.host || 'localhost'}`).pathname
  } catch (error) {
    send(res, 400, 'Bad request')
    return
  }

  if (pathname === servicePortsPath) {
    handleServicePortsRequest(req, res)
    return
  }

  if (pathname === liveUiConfigPath) {
    handleLiveUiConfigRequest(req, res)
    return
  }

  if (pathname === systemMetricsPath) {
    if (req.method !== 'GET') {
      send(res, 405, JSON.stringify({ ok: false, error: 'Method not allowed' }), 'application/json; charset=utf-8')
      return
    }
    refreshProjectMetricsInBackground()
    const metrics = getSystemMetrics()
    metrics.project = { ...metrics.project, ...projectMetricsCache.project, terminalVisible: Boolean(terminalMonitor && !terminalMonitor.killed) }
    metrics.services = projectMetricsCache.services
    if (projectMetricsCache.error) metrics.error = projectMetricsCache.error
    send(res, 200, JSON.stringify(metrics), 'application/json; charset=utf-8')
    return
  }

  if (pathname === systemControlPath) {
    handleSystemControlRequest(req, res)
    return
  }

  if (isListenerHttpRequest(pathname)) {
    proxyHttpRequest(req, res, pathname, listenerHost, listenerPort, 'DouyinListener')
    return
  }

  if (isFutureApiRequest(pathname)) {
    send(res, 404, JSON.stringify({ ok: false, error: 'LiveMngSys API endpoint reserved for future modules' }), 'application/json; charset=utf-8')
    return
  }

  if (isMusicBotHttpRequest(pathname)) {
    proxyMusicBotRequest(req, res, getMusicBotTargetPath(pathname))
    return
  }

  if (pathname === '/health') {
    send(res, 200, JSON.stringify({
      service: 'livemngsys-gui',
      status: 'ok',
      publicPort: port,
      musicBot: { publicPath: musicBotPublicPath, internalPort: musicBotPort },
      douyinListener: { apiPath: listenerApiPath, wsPath: listenerWsPath, internalPort: listenerPort },
      apiFuturePrefix: serviceConfig.api?.futurePrefix || '/api/livemngsys',
    }), 'application/json; charset=utf-8')
    return
  }

  if (pathname === '/favicon.ico') {
    res.writeHead(204, { 'Cache-Control': 'no-store' })
    res.end()
    return
  }

  if (pathname === '/') {
    res.writeHead(302, { Location: '/GUIDemo/' })
    res.end()
    return
  }

  let filePath
  try {
    filePath = resolveRequestPath(pathname)
  } catch (error) {
    send(res, 400, 'Bad request')
    return
  }

  if (!filePath) {
    send(res, 403, 'Forbidden')
    return
  }

  fs.stat(filePath, (statError, stats) => {
    if (statError) {
      send(res, 404, 'Not found')
      return
    }

    const target = stats.isDirectory() ? path.join(filePath, 'index.html') : filePath
    fs.stat(target, (targetError, targetStats) => {
      if (targetError || !targetStats.isFile()) {
        send(res, 404, 'Not found')
        return
      }

      const contentType = mimeTypes[path.extname(target).toLowerCase()] || 'application/octet-stream'
      res.writeHead(200, {
        'Content-Type': contentType,
        'Content-Length': targetStats.size,
        'Cache-Control': 'no-store',
        'Cross-Origin-Resource-Policy': 'cross-origin'
      })

      if (req.method === 'HEAD') {
        res.end()
        return
      }

      const stream = fs.createReadStream(target)
      stream.on('error', () => {
        if (!res.headersSent) send(res, 500, 'Read error')
        else res.destroy()
      })
      stream.pipe(res)
    })
  })
})

function proxyWebSocket(req, socket, head, targetHost, targetPort) {
  const upstream = net.connect(targetPort, targetHost, () => {
    const headers = []
    for (let index = 0; index < req.rawHeaders.length; index += 2) {
      const name = req.rawHeaders[index]
      const value = req.rawHeaders[index + 1]
      headers.push(`${name}: ${name.toLowerCase() === 'host' ? `${targetHost}:${targetPort}` : value}`)
    }
    upstream.write(`${req.method} ${req.url} HTTP/1.1\r\n${headers.join('\r\n')}\r\n\r\n`)
    if (head.length) upstream.write(head)
    socket.pipe(upstream).pipe(socket)
  })

  const close = () => {
    socket.destroy()
    upstream.destroy()
  }
  upstream.on('error', close)
  socket.on('error', () => upstream.destroy())
}

server.on('upgrade', (req, socket, head) => {
  let pathname
  try {
    pathname = new URL(req.url, `http://${req.headers.host || 'localhost'}`).pathname
  } catch {
    socket.destroy()
    return
  }

  if (pathname === listenerWsPath) {
    proxyWebSocket(req, socket, head, listenerHost, listenerPort)
    return
  }

  if (pathname === '/ws') {
    proxyWebSocket(req, socket, head, musicBotHost, musicBotPort)
  } else {
    socket.destroy()
  }
})

server.listen(port, host, () => {
  console.log(`LiveMngSys GUI server running at http://${host}:${port}`)
})
