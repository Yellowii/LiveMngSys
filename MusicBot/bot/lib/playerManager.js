const EventEmitter = require('events')
const net = require('net')
const { spawn } = require('child_process')
const fs = require('fs')
const path = require('path')

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function pipeName(name) {
  if (process.platform === 'win32') return `\\\\.\\pipe\\${name}`
  return `/tmp/${name}.sock`
}

function findExecutable(command) {
  if (!command || command === 'mpv') {
    const candidates = [
      'mpv',
      'C:\\Program Files\\MPV Player\\mpv.exe',
      'C:\\Program Files\\mpv\\mpv.exe',
      'C:\\Program Files\\mpv.net\\mpv.exe',
      path.join(process.env.LOCALAPPDATA || '', 'Programs', 'mpv', 'mpv.exe'),
      path.join(process.env.USERPROFILE || '', 'scoop', 'shims', 'mpv.exe'),
      path.join(process.env.ProgramData || '', 'chocolatey', 'bin', 'mpv.exe'),
    ]
    return candidates.find((item) => item === 'mpv' || fs.existsSync(item)) || 'mpv'
  }
  return command
}

class PlayerManager extends EventEmitter {
  constructor(config) {
    super()
    this.config = config
    this.process = null
    this.socket = null
    this.startPromise = null
    this.buffer = ''
    this.nextRequestId = 1
    this.pending = new Map()
    this.ready = false
    this.available = false
    this.lastError = ''
    this.currentUid = null
    this.loading = false
    this.progress = {
      status: 'idle',
      position: 0,
      duration: 0,
      volume: config.player.volume,
      device: config.player.audioDevice,
    }
  }

  snapshot() {
    return {
      type: this.config.player.type,
      command: this.config.player.command,
      available: this.available,
      ready: this.ready,
      error: this.lastError,
      ...this.progress,
    }
  }

  start() {
    if (this.ready) return Promise.resolve(true)
    if (this.startPromise) return this.startPromise
    this.startPromise = this.startInternal().finally(() => {
      this.startPromise = null
    })
    return this.startPromise
  }

  normalizationFilter() {
    const configured = Number(this.config.audioNormalization?.targetLufs)
    const target = Number.isFinite(configured) ? Math.min(-5, Math.max(-30, configured)) : -14
    return `lavfi=[loudnorm=I=${target}:TP=-1.5:LRA=11]`
  }

  async startInternal() {
    if (this.config.player.type !== 'mpv') {
      this.lastError = 'Only mpv player is implemented'
      return false
    }
    if (this.ready) return true

    if (this.socket) this.socket.destroy()
    this.socket = null
    if (this.process && !this.process.killed) this.process.kill()
    this.process = null

    const ipc = pipeName(this.config.player.ipcName)
    const args = [
      '--idle=yes',
      '--force-window=no',
      '--no-video',
      '--input-terminal=no',
      `--input-ipc-server=${ipc}`,
      `--volume=${Number(this.config.player.volume || 80)}`,
    ]

    if (this.config.audioNormalization?.enabled) {
      // mpv's bundled loudnorm filter avoids an extra analyzer process or cached analysis file.
      args.push(`--af=${this.normalizationFilter()}`)
    }

    if (this.config.player.audioDevice && this.config.player.audioDevice !== 'auto') {
      args.push(`--audio-device=${this.config.player.audioDevice}`)
    }

    const command = findExecutable(this.config.player.command || 'mpv')

    try {
      this.process = spawn(command, args, {
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe'],
      })
    } catch (error) {
      this.lastError = error.message
      return false
    }

    const child = this.process
    child.stdout.resume()
    let spawnFailed = false
    child.once('error', (error) => {
      if (this.process !== child) return
      spawnFailed = true
      this.lastError = error.message
      this.available = false
      this.ready = false
      this.rejectPending(error)
      this.emit('error-state', this.lastError)
    })
    child.once('exit', (code) => {
      if (this.process !== child) return
      this.lastError = code === 0 ? '' : `mpv exited with code ${code}`
      this.available = false
      this.ready = false
      this.process = null
      this.rejectPending(new Error(this.lastError || 'mpv exited'))
      this.socket = null
      this.emit('error-state', this.lastError)
    })
    child.stderr.on('data', (chunk) => {
      const text = chunk.toString('utf8').trim()
      if (text) this.lastError = text.slice(-500)
    })

    for (let i = 0; i < 30; i += 1) {
      if (spawnFailed) return false
      try {
        await this.connect(ipc)
        this.available = true
        this.ready = true
        await this.observe()
        return true
      } catch (error) {
        if (spawnFailed) return false
        await sleep(100)
      }
    }

    this.lastError = 'mpv IPC did not become ready'
    if (this.socket) this.socket.destroy()
    this.socket = null
    if (this.process === child && !child.killed) child.kill()
    if (this.process === child) this.process = null
    return false
  }

  connect(ipc) {
    return new Promise((resolve, reject) => {
      const socket = net.connect(ipc)
      const timer = setTimeout(() => {
        socket.destroy()
        reject(new Error('IPC timeout'))
      }, 1000)

      socket.once('connect', () => {
        clearTimeout(timer)
        this.socket = socket
        socket.on('data', (chunk) => this.read(chunk))
        socket.on('error', (error) => {
          if (this.socket !== socket) return
          this.lastError = error.message
          this.ready = false
          this.rejectPending(error)
        })
        socket.on('close', () => {
          if (this.socket !== socket) return
          this.ready = false
          this.socket = null
          this.rejectPending(new Error('mpv IPC closed'))
        })
        resolve()
      })
      socket.once('error', (error) => {
        clearTimeout(timer)
        reject(error)
      })
    })
  }

  read(chunk) {
    this.buffer += chunk.toString('utf8')
    let index = this.buffer.indexOf('\n')
    while (index >= 0) {
      const line = this.buffer.slice(0, index)
      this.buffer = this.buffer.slice(index + 1)
      this.handleLine(line)
      index = this.buffer.indexOf('\n')
    }
    if (this.buffer.length > 1024 * 1024) {
      this.buffer = ''
      this.lastError = 'mpv IPC response exceeded 1 MB'
    }
  }

  rejectPending(error) {
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer)
      pending.reject(error)
    }
    this.pending.clear()
  }

  handleLine(line) {
    if (!line.trim()) return
    let message
    try {
      message = JSON.parse(line)
    } catch {
      return
    }

    if (message.request_id && this.pending.has(message.request_id)) {
      const pending = this.pending.get(message.request_id)
      this.pending.delete(message.request_id)
      clearTimeout(pending.timer)
      if (message.error && message.error !== 'success') {
        pending.reject(new Error(message.error))
      } else {
        pending.resolve(message.data)
      }
      return
    }

    if (message.event === 'property-change') this.handleProperty(message)
    if (message.event === 'file-loaded') {
      this.loading = false
      this.progress.status = 'playing'
      this.emit('progress', { ...this.progress })
    }
    if (message.event === 'end-file') {
      if (!this.loading && message.reason === 'eof') this.emit('ended')
    }
  }

  handleProperty(message) {
    const { name, data } = message
    if (name === 'time-pos') this.progress.position = Number(data || 0)
    if (name === 'duration') this.progress.duration = Number(data || 0)
    if (name === 'pause') this.progress.status = data ? 'paused' : 'playing'
    if (name === 'volume') this.progress.volume = Number(data || this.progress.volume)
    if (name === 'audio-device') this.progress.device = data || 'auto'
    this.emit('progress', { ...this.progress })
  }

  send(command) {
    if (!this.socket || !this.ready) {
      return Promise.reject(new Error('mpv is not ready'))
    }
    const requestId = this.nextRequestId++
    const payload = JSON.stringify({ command, request_id: requestId }) + '\n'
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (!this.pending.has(requestId)) return
        this.pending.delete(requestId)
        reject(new Error('mpv command timeout'))
      }, 5000).unref()
      this.pending.set(requestId, { resolve, reject, timer })
      this.socket.write(payload, 'utf8')
    })
  }

  async observe() {
    await this.send(['observe_property', 1, 'time-pos']).catch(() => {})
    await this.send(['observe_property', 2, 'duration']).catch(() => {})
    await this.send(['observe_property', 3, 'pause']).catch(() => {})
    await this.send(['observe_property', 4, 'volume']).catch(() => {})
    await this.send(['observe_property', 5, 'audio-device']).catch(() => {})
  }

  async load(song) {
    const ok = await this.start()
    if (!ok) throw new Error(this.lastError || 'mpv is unavailable')
    this.currentUid = song.uid
    this.loading = true
    this.progress.status = 'loading'
    this.progress.position = 0
    this.progress.duration = song.duration || 0
    await this.send(['loadfile', song.url, 'replace'])
    await this.send(['set_property', 'pause', false]).catch(() => {})
    this.progress.status = 'playing'
    this.emit('progress', { ...this.progress })
  }

  async play() {
    await this.start()
    await this.send(['set_property', 'pause', false])
    this.progress.status = 'playing'
    this.emit('progress', { ...this.progress })
  }

  async pause() {
    await this.start()
    await this.send(['set_property', 'pause', true])
    this.progress.status = 'paused'
    this.emit('progress', { ...this.progress })
  }

  async stop() {
    if (!this.ready) return
    await this.send(['stop']).catch(() => {})
    this.progress.status = 'idle'
    this.progress.position = 0
    this.emit('progress', { ...this.progress })
  }

  async seek(seconds) {
    await this.start()
    await this.send(['set_property', 'time-pos', Number(seconds || 0)])
  }

  async setVolume(volume) {
    await this.start()
    const numeric = Number(volume)
    await this.send(['set_property', 'volume', numeric])
    this.progress.volume = numeric
    this.emit('progress', { ...this.progress })
  }

  async setAudioNormalization(enabled) {
    this.config.audioNormalization = this.config.audioNormalization || {}
    this.config.audioNormalization.enabled = Boolean(enabled)
    if (!this.ready) return
    await this.send(['set_property', 'af', enabled ? this.normalizationFilter() : '']).catch(() => {})
  }

  async setDevice(device) {
    this.config.player.audioDevice = device || 'auto'
    if (!this.ready) return
    await this.send(['set_property', 'audio-device', this.config.player.audioDevice])
    this.progress.device = this.config.player.audioDevice
    this.emit('progress', { ...this.progress })
  }

  async listDevices() {
    const ok = await this.start()
    if (!ok) return []
    const devices = await this.send(['get_property', 'audio-device-list'])
    return Array.isArray(devices) ? devices : []
  }
}

module.exports = { PlayerManager }
