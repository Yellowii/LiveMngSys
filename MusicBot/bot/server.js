const fs = require('fs')
const path = require('path')
const crypto = require('crypto')
const { execFile } = require('child_process')
const { promisify } = require('util')
const express = require('express')
const WebSocket = require('ws')
const { createStore, ensureDir } = require('./lib/store')
const { BotCore, publicSong } = require('./lib/botCore')
const { PlayerManager } = require('./lib/playerManager')
const { SoundpadManager } = require('./lib/soundpadManager')
const { withTimeout } = require('./lib/musicService')
const {
  normalizeCookie,
  hasMusicU,
  mergeCookies,
  cookieFromLoginResult,
  validateLoginCookie,
} = require('./lib/authService')
const { publicDir, cacheDir, dataDir, lyricDir, coverDir, musicDir } = require('./lib/paths')
const api = require('../api-enhanced-main/main.js')
const execFileAsync = promisify(execFile)

process.on('unhandledRejection', (error) => {
  console.error('Unhandled rejection:', error)
})

process.on('uncaughtException', (error) => {
  console.error('Uncaught exception:', error)
})

ensureDir(cacheDir)
ensureDir(dataDir)
ensureDir(lyricDir)
ensureDir(coverDir)
ensureDir(musicDir)
const soundpadImportDir = path.join(cacheDir, 'Soundpad', 'imports')
ensureDir(soundpadImportDir)

const store = createStore()
const player = new PlayerManager(store.config)
const bot = new BotCore(store, player)
const soundpad = new SoundpadManager(store, path.join(dataDir, 'soundpad.json'))
const app = express()

app.use(express.json({ limit: '2mb' }))
app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PUT,PATCH,DELETE,OPTIONS')
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Soundpad-Filename')
  if (req.method === 'OPTIONS') {
    res.sendStatus(204)
    return
  }
  next()
})
app.use((req, res, next) => {
  if (req.path === '/' || req.path.endsWith('.js') || req.path.endsWith('.css') || req.path.endsWith('.html')) {
    res.setHeader('Cache-Control', 'no-store')
  }
  next()
})
const indexFile = path.join(publicDir, 'Index.html')
const soundpadFile = path.join(publicDir, 'soundpad.html')
app.get(['/', '/index.html', '/Index.html'], (req, res) => res.sendFile(indexFile))
app.get(['/soundpad', '/soundpad.html'], (req, res) => res.sendFile(soundpadFile))
app.use(express.static(publicDir))

function asyncRoute(handler) {
  return (req, res, next) => {
    Promise.resolve(handler(req, res, next)).catch(next)
  }
}

function sendState(res) {
  res.json(bot.snapshot())
}

function compactApiResult(result) {
  if (result?.uid) return publicSong(result, false)
  return result
}

app.get('/api/state', (req, res) => sendState(res))

function openWindowsDialog(script) {
  if (process.platform !== 'win32') {
    const error = new Error('File picker is available only on Windows')
    error.status = 501
    throw error
  }
  return execFileAsync('powershell.exe', ['-NoProfile', '-STA', '-Command', script], {
    encoding: 'utf8', timeout: 10 * 60 * 1000, windowsHide: true,
  }).then(({ stdout }) => stdout.trim())
}

function soundpadButton(pageId, buttonId) {
  return soundpad.button(pageId, buttonId)
}

app.get('/api/soundpad/state', (req, res) => res.json({ ok: true, soundpad: soundpad.snapshot() }))
app.get('/api/soundpad/devices', asyncRoute(async (req, res) => {
  const devices = await soundpad.player.listDevices()
  res.json({ ok: true, devices, selected: soundpad.settings().audioDevice })
}))
app.get('/api/integrations/soundpad', (req, res) => res.json({ ok: true, soundpad: soundpad.externalSnapshot() }))

app.post('/api/integrations/soundpad', asyncRoute(async (req, res) => {
  if (soundpad.settings().externalEnabled !== true) {
    const error = new Error('Soundpad external control is disabled')
    error.status = 403
    throw error
  }
  const action = String(req.body?.action || '').toLowerCase()
  if (action === 'stop') await soundpad.stop()
  else if (action === 'play') await soundpad.playButton(String(req.body?.pageId || ''), String(req.body?.buttonId || ''))
  else {
    const error = new Error('Unsupported Soundpad action')
    error.status = 400
    throw error
  }
  res.json({ ok: true, soundpad: soundpad.externalSnapshot() })
}))

app.post('/api/soundpad/import/file', asyncRoute(async (req, res) => {
  const selected = await openWindowsDialog([
    'Add-Type -AssemblyName System.Windows.Forms',
    '$dialog = New-Object System.Windows.Forms.OpenFileDialog',
    "$dialog.Filter = 'Audio files|*.mp3;*.wav;*.ogg;*.m4a;*.aac;*.flac;*.webm'",
    '$dialog.Multiselect = $false',
    "if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Write($dialog.FileName) }",
  ].join('; '))
  const added = selected ? soundpad.importFile(selected) : []
  res.json({ ok: true, cancelled: !selected, added, soundpad: soundpad.snapshot() })
}))

app.post('/api/soundpad/import/folder', asyncRoute(async (req, res) => {
  const selected = await openWindowsDialog([
    'Add-Type -AssemblyName System.Windows.Forms',
    '$dialog = New-Object System.Windows.Forms.FolderBrowserDialog',
    "$dialog.Description = 'Select a Soundpad audio folder'",
    '$dialog.ShowNewFolderButton = $false',
    "if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Write($dialog.SelectedPath) }",
  ].join('; '))
  const added = selected ? soundpad.importFolder(selected) : []
  res.json({ ok: true, cancelled: !selected, added, soundpad: soundpad.snapshot() })
}))

app.post('/api/soundpad/import/upload', express.raw({ type: 'application/octet-stream', limit: '512mb' }), (req, res, next) => {
  try {
    const requestedName = decodeURIComponent(String(req.get('X-Soundpad-Filename') || ''))
    const extension = path.extname(requestedName).toLowerCase()
    if (!['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.webm'].includes(extension)) {
      const error = new Error('Unsupported Soundpad audio file type')
      error.status = 400
      throw error
    }
    if (!Buffer.isBuffer(req.body) || req.body.length === 0) {
      const error = new Error('Soundpad upload is empty')
      error.status = 400
      throw error
    }
    const baseName = path.basename(requestedName, extension).replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').trim() || 'sound'
    const target = path.join(soundpadImportDir, `${Date.now()}-${crypto.randomUUID()}-${baseName}${extension}`)
    fs.writeFileSync(target, req.body)
    const added = soundpad.importFile(target)
    if (added.length === 0) fs.unlinkSync(target)
    res.json({ ok: true, added, soundpad: soundpad.snapshot() })
  } catch (error) { next(error) }
})

app.post('/api/soundpad/pages', (req, res) => {
  const page = soundpad.createPage(req.body?.name)
  res.json({ ok: true, page, soundpad: soundpad.snapshot() })
})

app.put('/api/soundpad/pages/:pageId/buttons/:buttonId', (req, res, next) => {
  try {
    const button = soundpad.updateButton(req.params.pageId, req.params.buttonId, req.body || {})
    res.json({ ok: true, button, soundpad: soundpad.snapshot() })
  } catch (error) { next(error) }
})

app.post('/api/soundpad/pages/:pageId/buttons/:buttonId/image', asyncRoute(async (req, res) => {
  if (!soundpadButton(req.params.pageId, req.params.buttonId)) {
    const error = new Error('Soundpad button was not found')
    error.status = 404
    throw error
  }
  const selected = await openWindowsDialog([
    'Add-Type -AssemblyName System.Windows.Forms',
    '$dialog = New-Object System.Windows.Forms.OpenFileDialog',
    "$dialog.Filter = 'Image files|*.png;*.jpg;*.jpeg;*.webp;*.gif'",
    '$dialog.Multiselect = $false',
    "if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Write($dialog.FileName) }",
  ].join('; '))
  if (selected) soundpad.updateButton(req.params.pageId, req.params.buttonId, { imageFile: selected })
  res.json({ ok: true, cancelled: !selected, soundpad: soundpad.snapshot() })
}))

app.post('/api/soundpad/pages/:pageId/reorder', (req, res, next) => {
  try {
    soundpad.reorder(req.params.pageId, String(req.body?.sourceButtonId || ''), String(req.body?.targetButtonId || ''))
    res.json({ ok: true, soundpad: soundpad.snapshot() })
  } catch (error) { next(error) }
})

app.patch('/api/soundpad/settings', asyncRoute(async (req, res) => {
  const settings = await soundpad.updateSettings(req.body || {})
  res.json({ ok: true, settings, soundpad: soundpad.snapshot() })
}))

app.post('/api/soundpad/play', asyncRoute(async (req, res) => {
  const button = await soundpad.playButton(String(req.body?.pageId || ''), String(req.body?.buttonId || ''))
  res.json({ ok: true, button, soundpad: soundpad.snapshot() })
}))
app.post('/api/soundpad/stop', asyncRoute(async (req, res) => {
  await soundpad.stop()
  res.json({ ok: true, soundpad: soundpad.snapshot() })
}))
app.get('/api/soundpad/buttons/:buttonId/image', (req, res) => {
  const image = soundpad.buttonImage(req.params.buttonId)
  if (!image) return res.sendStatus(404)
  return res.sendFile(image)
})

app.get('/api/system/select-folder', asyncRoute(async (req, res) => {
  if (process.platform !== 'win32') return res.status(501).json({ ok: false, error: '当前系统不支持文件夹选择器' })
  const script = [
    '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8',
    'Add-Type -AssemblyName System.Windows.Forms',
    '$dialog = New-Object System.Windows.Forms.FolderBrowserDialog',
    "$dialog.Description = '选择本地音乐文件夹'",
    '$dialog.ShowNewFolderButton = $false',
    'if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Write($dialog.SelectedPath) }',
  ].join('; ')
  const { stdout } = await execFileAsync('powershell.exe', ['-NoProfile', '-STA', '-Command', script], {
    encoding: 'utf8',
    timeout: 10 * 60 * 1000,
    windowsHide: true,
  })
  const directory = stdout.trim()
  return res.json({ ok: true, cancelled: !directory, directory })
}))

app.get('/api/live/broadcast', (req, res) => {
  res.json({ ok: true, broadcast: bot.lastBroadcast })
})

// Reserved for future integrations such as 妙联宝. This endpoint is read-only.
app.get('/api/integrations/status', (req, res) => {
  res.json({
    ok: true,
    status: {
      playback: bot.playback,
      current: bot.current ? publicSong(bot.current, false) : null,
      queueLength: bot.queue.length,
      idleLength: bot.selectedIdleSongs().length,
      controls: bot.config.controls || {},
    },
  })
})

app.post('/api/integrations/danmaku/command', asyncRoute(async (req, res) => {
  const result = await bot.handleCommand(req.body || {})
  res.json({ ok: true, result })
}))

app.post('/api/integrations/control', asyncRoute(async (req, res) => {
  if (bot.config.controls?.externalCommandEnabled !== true) {
    const error = new Error('External control is disabled')
    error.status = 403
    throw error
  }
  const command = String(req.body?.command || '').toLowerCase()
  if (command === 'play') await bot.play(null, { origin: 'external' })
  else if (command === 'pause') await bot.pause()
  else if (command === 'next' || command === 'skip') await bot.next('external')
  else if (command === 'previous') await bot.previous()
  else {
    const error = new Error('Unsupported external control command')
    error.status = 400
    throw error
  }
  res.json({ ok: true, command })
}))

app.post('/api/queue/song', asyncRoute(async (req, res) => {
  const result = await bot.requestSong(req.body.query, req.body.user, { privileged: true, origin: 'backend' })
  res.json({ ok: true, result: compactApiResult(result) })
}))

app.post('/api/queue/idle', asyncRoute(async (req, res) => {
  const result = await bot.enqueueIdle(req.body.uid, req.body.user, req.body.playlistId)
  res.json({ ok: true, result: compactApiResult(result) })
}))

app.post('/api/queue/playlist', asyncRoute(async (req, res) => {
  const result = await bot.addPlaylistToQueue(req.body.id || req.body.url, req.body.user, req.body.limit)
  res.json({ ok: true, result })
}))

app.post('/api/queue/:uid/promote', asyncRoute(async (req, res) => {
  const result = bot.promoteQueued(req.params.uid)
  res.json({ ok: true, result: compactApiResult(result) })
}))

app.post('/api/queue/:uid/play', asyncRoute(async (req, res) => {
  const result = await bot.playQueued(req.params.uid)
  res.json({ ok: true, result: compactApiResult(result) })
}))

app.delete('/api/queue/:uid', asyncRoute(async (req, res) => {
  const result = bot.removeQueued(req.params.uid)
  res.json({ ok: true, result: compactApiResult(result) })
}))

app.post('/api/queue/:uid/remove', asyncRoute(async (req, res) => {
  const result = await bot.removeSong(req.params.uid, req.body?.playing === true)
  res.json({ ok: true, result: compactApiResult(result) })
}))

app.delete('/api/queue', (req, res) => {
  res.json({ ok: true, result: bot.clearQueue() })
})

app.post('/api/control/next', asyncRoute(async (req, res) => {
  await bot.skip()
  res.json({ ok: true })
}))

app.post('/api/control/previous', asyncRoute(async (req, res) => {
  const result = await bot.previous()
  res.json({ ok: true, ignored: !result })
}))

app.post('/api/control/play', asyncRoute(async (req, res) => {
  await bot.play()
  res.json({ ok: true })
}))

app.post('/api/control/pause', asyncRoute(async (req, res) => {
  await bot.pause()
  res.json({ ok: true })
}))

app.post('/api/control/seek', asyncRoute(async (req, res) => {
  await bot.seek(req.body.position)
  res.json({ ok: true })
}))

app.post('/api/control/volume', asyncRoute(async (req, res) => {
  await bot.setVolume(req.body.volume)
  res.json({ ok: true })
}))

app.post('/api/player/device', asyncRoute(async (req, res) => {
  await bot.setDevice(req.body.device)
  res.json({ ok: true, device: store.config.player.audioDevice })
}))

app.get('/api/player/devices', asyncRoute(async (req, res) => {
  const devices = await player.listDevices()
  res.json({ ok: true, devices, selected: store.config.player.audioDevice })
}))

app.post('/api/control/playback', asyncRoute(async (req, res) => {
  bot.setPlaybackPatch(req.body || {})
  res.json({ ok: true })
}))

app.post('/api/idle/import/playlist', asyncRoute(async (req, res) => {
  const result = await bot.importPlaylist(req.body.id, req.body.limit)
  res.json({ ok: true, result })
}))

app.post('/api/idle/import/local', asyncRoute(async (req, res) => {
  const result = bot.importLocal(req.body.directory, req.body.recursive !== false, req.body.name)
  res.json({ ok: true, result })
}))

app.post('/api/idle/config', (req, res) => {
  let resetIdleNext = false
  if (['sequence', 'random', 'loop'].includes(req.body.mode) && req.body.mode !== bot.config.queue.idleMode) {
    bot.config.queue.idleMode = req.body.mode
    bot.idleCursor = 0
    resetIdleNext = true
  }
  if (typeof req.body.autoIdle === 'boolean' && req.body.autoIdle !== bot.config.queue.autoIdle) {
    bot.config.queue.autoIdle = req.body.autoIdle
    resetIdleNext = true
  }
  if (typeof req.body.interruptIdleOnRequest === 'boolean') bot.config.queue.interruptIdleOnRequest = req.body.interruptIdleOnRequest
  bot.store.saveConfig()
  if (resetIdleNext) bot.idleNext = null
  bot.publish()
  res.json({
    ok: true,
    mode: bot.config.queue.idleMode,
    autoIdle: bot.config.queue.autoIdle,
    interruptIdleOnRequest: bot.config.queue.interruptIdleOnRequest === true,
  })
})

app.post('/api/settings', asyncRoute(async (req, res) => {
  const config = await bot.updateSettings(req.body || {})
  res.json({ ok: true, config })
}))

app.get('/api/users', (req, res) => {
  res.json({ ok: true, users: bot.userRecords() })
})

app.post('/api/users/delete', (req, res) => {
  const removed = bot.removeUsers(req.body.ids || [])
  res.json({ ok: true, removed, users: bot.userRecords() })
})

app.post('/api/users/:id', (req, res) => {
  const user = bot.updateUser(req.params.id, req.body || {})
  res.json({ ok: true, user, users: bot.userRecords() })
})

app.delete('/api/users/:id', (req, res) => {
  const removed = bot.removeUsers([req.params.id])
  res.json({ ok: true, removed, users: bot.userRecords() })
})

app.delete('/api/users', (req, res) => {
  const removed = bot.removeUsers(Object.keys(bot.persisted.users || {}))
  res.json({ ok: true, removed, users: [] })
})

app.post('/api/data/export', (req, res) => {
  res.json(bot.exportManagedData(req.body.sections || []))
})

app.post('/api/data/import', (req, res) => {
  const result = bot.importManagedData(req.body || {})
  res.json({ ok: true, result })
})

app.get('/api/idle/export', (req, res) => {
  res.json({
    version: 1,
    exportedAt: new Date().toISOString(),
    options: {
      mode: bot.config.queue.idleMode || 'sequence',
      autoIdle: bot.config.queue.autoIdle !== false,
    },
    playlists: bot.persisted.idlePlaylists,
  })
})

app.post('/api/idle/import/config', (req, res) => {
  const result = bot.importIdleConfig(req.body)
  res.json({ ok: true, result })
})

app.post('/api/idle/playlists/:id/toggle', (req, res) => {
  const result = bot.setIdlePlaylistEnabled(req.params.id, req.body.enabled)
  res.json({ ok: true, playlist: result })
})

app.post('/api/idle/playlists/toggle', (req, res) => {
  const result = bot.setAllIdlePlaylistsEnabled(req.body.enabled)
  res.json({ ok: true, result })
})

app.post('/api/idle/playlists/:id/play', asyncRoute(async (req, res) => {
  const result = await bot.playIdlePlaylist(req.params.id)
  res.json({ ok: true, result: compactApiResult(result) })
}))

app.post('/api/idle/playlists/:id/rename', (req, res) => {
  const playlist = bot.renameIdlePlaylist(req.params.id, req.body.name)
  res.json({ ok: true, playlist: { ...playlist, songs: undefined } })
})

app.delete('/api/idle/playlists/:id', (req, res) => {
  const playlist = bot.removeIdlePlaylist(req.params.id)
  res.json({ ok: true, playlist: { ...playlist, songs: undefined } })
})

app.post('/api/idle/playlists/:id/songs/:uid/promote', (req, res) => {
  const result = bot.promoteIdleSong(req.params.id, req.params.uid)
  res.json({ ok: true, result: compactApiResult(result) })
})

app.post('/api/idle/playlists/:id/songs/:uid/play', asyncRoute(async (req, res) => {
  const result = await bot.playIdleSong(req.params.id, req.params.uid)
  res.json({ ok: true, result: compactApiResult(result) })
}))

app.delete('/api/idle/playlists/:id/songs/:uid', (req, res) => {
  const playlist = bot.idlePlaylistById(req.params.id)
  if (!playlist) return res.status(404).json({ ok: false, error: '歌单不存在' })
  playlist.songs = playlist.songs.filter((song) => song.uid !== req.params.uid)
  bot.syncIdleList()
  bot.save()
  bot.publish()
  return res.json({ ok: true })
})

app.post('/api/idle/playlists/clear', (req, res) => {
  res.json({ ok: true, result: bot.clearIdlePlaylists(req.body.ids || []) })
})

app.post('/api/idle/:uid', asyncRoute(async (req, res) => {
  const result = bot.addToIdle(req.params.uid)
  res.json({ ok: true, result })
}))

app.delete('/api/idle/:uid', (req, res) => {
  bot.removeIdle(req.params.uid)
  res.json({ ok: true })
})

app.post('/api/blacklist', asyncRoute(async (req, res) => {
  const result = req.body.query
    ? await bot.blacklistQuery(req.body.query)
    : bot.blacklist(req.body.uid)
  res.json({ ok: true, result: compactApiResult(result), blacklist: bot.persisted.blacklist.slice() })
}))

app.delete('/api/blacklist/:index', (req, res) => {
  const removed = bot.removeBlacklist(req.params.index)
  res.json({ ok: true, removed, blacklist: bot.persisted.blacklist.slice() })
})

app.delete('/api/blacklist', (req, res) => {
  const removed = bot.clearBlacklist()
  res.json({ ok: true, removed, blacklist: [] })
})

app.post('/api/title-filters', (req, res) => {
  const values = Array.isArray(req.body.keywords) ? req.body.keywords : [req.body.keyword]
  const keywords = bot.addTitleFilters(values, req.body.replace === true)
  res.json({ ok: true, keywords })
})

app.delete('/api/title-filters/:index', (req, res) => {
  const removed = bot.removeTitleFilter(req.params.index)
  res.json({ ok: true, removed, keywords: bot.persisted.titleFilters.slice() })
})

app.delete('/api/title-filters', (req, res) => {
  const removed = bot.clearTitleFilters()
  res.json({ ok: true, removed, keywords: [] })
})

async function saveLoginCookie(cookie) {
  const normalized = normalizeCookie(cookie)
  const status = await validateLoginCookie(api, normalized, withTimeout)
  if (!status.valid) {
    const error = new Error(status.message)
    error.status = 400
    throw error
  }
  store.config.music.neteaseCookie = normalized
  store.config.music.login = {
    userId: status.userId,
    nickname: status.nickname,
    vipType: status.vipType,
    savedAt: new Date().toISOString(),
  }
  store.saveConfig()
  bot.publish()
  return status
}

app.post('/api/login/cookie', asyncRoute(async (req, res) => {
  const status = await saveLoginCookie(req.body.cookie || '')
  res.json({ ok: true, ...status })
}))

app.post('/api/login/logout', (req, res) => {
  store.config.music.neteaseCookie = ''
  store.config.music.login = null
  store.saveConfig()
  bot.publish()
  res.json({ ok: true })
})

app.get('/api/login/status', asyncRoute(async (req, res) => {
  const cookie = store.config.music.neteaseCookie || process.env.NETEASE_COOKIE || ''
  if (!cookie) {
    res.json({
      ok: true,
      valid: false,
      hasCookie: false,
      hasMusicU: false,
      message: '未登录',
    })
    return
  }
  if (!hasMusicU(cookie)) {
    res.json({
      ok: true,
      valid: false,
      hasCookie: true,
      hasMusicU: false,
      message: 'Cookie 缺少 MUSIC_U',
    })
    return
  }
  const status = await validateLoginCookie(api, cookie, withTimeout)
  res.json({ ok: true, ...status })
}))

app.post('/api/login/refresh', asyncRoute(async (req, res) => {
  const cookie = store.config.music.neteaseCookie || process.env.NETEASE_COOKIE || ''
  if (!hasMusicU(cookie)) {
    const error = new Error('未登录，无法刷新')
    error.status = 400
    throw error
  }
  const result = await withTimeout(
    api.login_refresh({ cookie }),
    10000,
    'login refresh',
  )
  const refreshed = mergeCookies(cookie, cookieFromLoginResult(result))
  const status = await saveLoginCookie(refreshed)
  res.json({ ok: true, ...status })
}))

app.get('/api/login/qr', asyncRoute(async (req, res) => {
  const keyResult = await withTimeout(api.login_qr_key({}), 10000, 'login qr key')
  const key = keyResult.body?.data?.data?.unikey || keyResult.body?.data?.unikey
  if (!key) {
    const error = new Error('Failed to create login QR key')
    error.status = 502
    throw error
  }
  const qrResult = await withTimeout(
    api.login_qr_create({ key, qrimg: true }),
    10000,
    'login qr image',
  )
  res.json({ key, ...qrResult.body.data })
}))

app.get('/api/login/qr/check', asyncRoute(async (req, res) => {
  const result = await withTimeout(
    api.login_qr_check({ key: req.query.key }),
    10000,
    'login qr check',
  )
  const cookie = cookieFromLoginResult(result)
  let saved = false
  let status = null
  if (hasMusicU(cookie)) {
    status = await saveLoginCookie(cookie)
    saved = true
  }
  res.json({
    ...result.body,
    saved,
    login: status,
    hasMusicU: hasMusicU(store.config.music.neteaseCookie || ''),
  })
}))

app.get('/media/local/:id', (req, res, next) => {
  const song = store.state.idleList
    .concat(bot.queue)
    .concat(bot.current ? [bot.current] : [])
    .find((item) => item.source === 'local' && item.sourceId === req.params.id)

  if (!song || !song.filePath || !fs.existsSync(song.filePath)) {
    res.status(404).json({ error: 'Local media not found' })
    return
  }

  const stat = fs.statSync(song.filePath)
  const range = req.headers.range
  const ext = path.extname(song.filePath).toLowerCase()
  const types = {
    '.mp3': 'audio/mpeg',
    '.flac': 'audio/flac',
    '.wav': 'audio/wav',
    '.m4a': 'audio/mp4',
    '.aac': 'audio/aac',
    '.ogg': 'audio/ogg',
  }
  const contentType = types[ext] || 'application/octet-stream'

  if (!range) {
    res.setHeader('Content-Length', stat.size)
    res.setHeader('Content-Type', contentType)
    fs.createReadStream(song.filePath).pipe(res)
    return
  }

  const parts = range.replace(/bytes=/, '').split('-')
  const start = parseInt(parts[0], 10)
  const end = parts[1] ? parseInt(parts[1], 10) : stat.size - 1
  if (Number.isNaN(start) || Number.isNaN(end) || start >= stat.size) {
    res.status(416).end()
    return
  }
  res.writeHead(206, {
    'Content-Range': `bytes ${start}-${end}/${stat.size}`,
    'Accept-Ranges': 'bytes',
    'Content-Length': end - start + 1,
    'Content-Type': contentType,
  })
  fs.createReadStream(song.filePath, { start, end }).pipe(res).on('error', next)
})

app.use((error, req, res, next) => {
  console.error(error)
  res.status(error.status || 500).json({
    ok: false,
    error: error.message || 'Server error',
  })
})

const listenHost = process.env.HOST || '0.0.0.0'
const listenPort = Number(process.env.PORT || store.config.server.port)

const server = app.listen(listenPort, listenHost, () => {
  const host = listenHost
  const port = listenPort
  console.log(`MusicBot running at http://${host}:${port}`)
})

const wss = new WebSocket.Server({ server, path: '/ws' })

const maxWsBufferedBytes = Math.max(256 * 1024, Number(process.env.MUSICBOT_WS_BUFFER_BYTES || 2 * 1024 * 1024))
let pendingBroadcastState = null
let broadcastScheduled = false

function hasLyricPayload(state) {
  const current = state?.current
  return Boolean(current) && (
    Object.prototype.hasOwnProperty.call(current, 'lyric') ||
    Object.prototype.hasOwnProperty.call(current, 'wordLyrics')
  )
}

function flushBroadcast() {
  broadcastScheduled = false
  const state = pendingBroadcastState
  pendingBroadcastState = null
  if (!state) return

  sendWebSocketPayload({ type: 'state', state })
}

function sendWebSocketPayload(payload) {
  const clients = [...wss.clients].filter((client) => {
    return client.readyState === WebSocket.OPEN && client.bufferedAmount <= maxWsBufferedBytes
  })
  if (clients.length === 0) return
  const serialized = JSON.stringify(payload)
  for (const client of clients) client.send(serialized)
}

function broadcastState(state) {
  if (
    pendingBroadcastState?.current?.uid &&
    pendingBroadcastState.current.uid === state?.current?.uid &&
    hasLyricPayload(pendingBroadcastState) &&
    !hasLyricPayload(state)
  ) {
    state = {
      ...state,
      current: { ...pendingBroadcastState.current, ...state.current },
    }
  }
  pendingBroadcastState = state
  if (broadcastScheduled) return
  broadcastScheduled = true
  setImmediate(flushBroadcast)
}

wss.on('connection', (socket) => {
  socket.send(JSON.stringify({ type: 'state', state: bot.snapshot() }))
})

bot.on('state', broadcastState)
bot.on('live-broadcast', (broadcast) => sendWebSocketPayload({ type: 'live-broadcast', broadcast }))

setInterval(() => bot.publish({ includeLyrics: false, includeIdleList: false }), 5000).unref()
