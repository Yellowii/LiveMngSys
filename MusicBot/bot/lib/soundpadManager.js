const EventEmitter = require('events')
const crypto = require('crypto')
const fs = require('fs')
const path = require('path')
const { PlayerManager } = require('./playerManager')
const { readJson, writeJson } = require('./store')

const AUDIO_EXTENSIONS = new Set(['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.webm'])
const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.webp', '.gif'])
const BUTTON_COUNT = 30

function id(prefix) {
  return `${prefix}_${crypto.randomUUID().replace(/-/g, '').slice(0, 12)}`
}

function clamp(value, min, max, fallback) {
  const number = Number(value)
  return Number.isFinite(number) ? Math.min(max, Math.max(min, number)) : fallback
}

function filename(file) {
  return path.basename(String(file || ''), path.extname(String(file || ''))).replace(/^\d+-[0-9a-f-]{36}-/i, '')
}

function emptyButton(index, pageId = 'soundpad') {
  return {
    id: `${pageId}-button-${String(index + 1).padStart(2, '0')}`,
    clipId: '',
    label: '',
    fillColor: '#202a36',
    progressColor: '#4f8cff',
    imageFile: '',
    loopCount: 0,
    volume: 100,
    delayMs: 0,
  }
}

function newPage(name = '主面板') {
  const pageId = id('soundpad-page')
  return { id: pageId, name, buttons: Array.from({ length: BUTTON_COUNT }, (_, index) => emptyButton(index, pageId)) }
}

function defaultData() {
  return { version: 1, clips: [], pages: [newPage()] }
}

class SoundpadManager extends EventEmitter {
  constructor(store, dataFile) {
    super()
    this.store = store
    this.config = store.config
    if (this.config.soundpad?.audioDevice === 'follow_musicbot') {
      this.config.soundpad.audioDevice = 'auto'
      this.store.saveConfig()
    }
    this.dataFile = dataFile
    this.data = { ...defaultData(), ...readJson(dataFile, {}) }
    if (!Array.isArray(this.data.clips)) this.data.clips = []
    if (!Array.isArray(this.data.pages) || this.data.pages.length === 0) this.data.pages = [newPage()]
    const renamedClips = new Map()
    for (const clip of this.data.clips) {
      const oldName = String(clip.name || '')
      const normalizedName = filename(clip.path)
      if (/^\d+-[0-9a-f-]{36}-/i.test(oldName) && normalizedName && normalizedName !== oldName) {
        clip.name = normalizedName
        renamedClips.set(clip.id, { oldName, normalizedName })
      }
    }
    this.data.pages.forEach((page) => this.ensurePageButtons(page))
    for (const page of this.data.pages) {
      for (const button of page.buttons) {
        const renamed = renamedClips.get(button.clipId)
        if (renamed && (!button.label || button.label === renamed.oldName)) button.label = renamed.normalizedName
      }
    }
    this.currentButtonId = ''
    this.pendingButtonId = ''
    this.playNonce = 0
    this.playerConfig = {
      ...this.config,
      player: {
        ...this.config.player,
        ipcName: 'musicbot-soundpad-mpv',
        audioDevice: this.outputDevice(),
        volume: this.masterVolume(),
      },
      audioNormalization: { enabled: false },
    }
    this.player = new PlayerManager(this.playerConfig)
    this.player.on('progress', () => this.emitState())
    this.player.on('ended', () => {
      this.currentButtonId = ''
      this.emitState()
    })
    this.player.on('error-state', () => this.emitState())
    this.save()
  }

  settings() {
    const value = this.config.soundpad || {}
    return {
      masterVolume: clamp(value.masterVolume, 0, 100, 80),
      audioDevice: value.audioDevice === 'follow_musicbot' ? 'auto' : String(value.audioDevice || 'auto'),
      externalEnabled: value.externalEnabled === true,
    }
  }

  masterVolume() {
    return this.settings().masterVolume
  }

  outputDevice() {
    return this.settings().audioDevice
  }

  ensurePageButtons(page) {
    if (!Array.isArray(page.buttons)) page.buttons = []
    while (page.buttons.length < BUTTON_COUNT) page.buttons.push(emptyButton(page.buttons.length, page.id))
    page.buttons = page.buttons.slice(0, BUTTON_COUNT).map((button, index) => {
      const normalized = { ...emptyButton(index, page.id), ...button }
      if (button.loopCount === undefined) normalized.loopCount = button.loop === true ? -1 : 0
      if (!button.clipId && button.fillColor === '#2f6fed' && button.progressColor === '#4f8cff') {
        normalized.fillColor = '#202a36'
      }
      return normalized
    })
  }

  save() {
    writeJson(this.dataFile, this.data)
  }

  page(pageId) {
    return this.data.pages.find((item) => item.id === pageId) || null
  }

  clip(clipId) {
    return this.data.clips.find((item) => item.id === clipId) || null
  }

  button(pageId, buttonId) {
    return this.page(pageId)?.buttons.find((item) => item.id === buttonId) || null
  }

  publicButton(pageId, button) {
    const clip = this.clip(button.clipId)
    const progress = this.currentButtonId === button.id ? this.player.progress : null
    return {
      ...button,
      pageId,
      clip: clip ? { id: clip.id, name: clip.name, path: clip.path } : null,
      active: this.currentButtonId === button.id,
      pending: this.pendingButtonId === button.id,
      progress: progress ? { position: progress.position, duration: progress.duration } : null,
    }
  }

  snapshot() {
    const settings = this.settings()
    const player = this.player.snapshot()
    return {
      settings,
      pages: this.data.pages.map((page) => ({
        id: page.id,
        name: page.name,
        buttons: page.buttons.map((button) => this.publicButton(page.id, button)),
      })),
      clips: this.data.clips.map((clip) => ({ ...clip })),
      playback: {
        buttonId: this.currentButtonId,
        pendingButtonId: this.pendingButtonId,
        ...player,
        status: this.pendingButtonId ? 'pending' : this.currentButtonId ? player.status : 'idle',
      },
    }
  }

  externalSnapshot() {
    const snapshot = this.snapshot()
    return {
      playback: snapshot.playback,
      pages: snapshot.pages.map((page) => ({
        id: page.id,
        name: page.name,
        buttons: page.buttons.map((button) => ({
          id: button.id,
          label: button.label || button.clip?.name || '',
          active: button.active,
          pending: button.pending,
          progress: button.progress,
        })),
      })),
    }
  }

  emitState() {
    this.emit('state', this.snapshot())
  }

  scanFiles(root, recursive = true) {
    const result = []
    const visit = (directory) => {
      for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
        const target = path.join(directory, entry.name)
        if (entry.isSymbolicLink()) continue
        if (entry.isDirectory()) {
          if (recursive) visit(target)
        } else if (entry.isFile() && AUDIO_EXTENSIONS.has(path.extname(entry.name).toLowerCase())) {
          result.push(target)
        }
        if (result.length >= 1000) return
      }
    }
    visit(root)
    return result
  }

  importFiles(files) {
    const added = []
    for (const candidate of files) {
      const file = path.resolve(String(candidate || ''))
      if (!AUDIO_EXTENSIONS.has(path.extname(file).toLowerCase()) || !fs.existsSync(file)) continue
      const stat = fs.statSync(file)
      if (!stat.isFile() || this.data.clips.some((clip) => clip.path.toLowerCase() === file.toLowerCase())) continue
      const clip = { id: id('sound'), name: filename(file), path: file, addedAt: Date.now() }
      this.data.clips.push(clip)
      added.push(clip)
    }
    const page = this.data.pages[0]
    for (const clip of added) {
      const button = page.buttons.find((item) => !item.clipId)
      if (!button) break
      button.clipId = clip.id
      button.label = clip.name
    }
    this.save()
    this.emitState()
    return added
  }

  importFile(file) {
    return this.importFiles([file])
  }

  importFolder(folder) {
    const root = path.resolve(String(folder || ''))
    if (!fs.existsSync(root) || !fs.statSync(root).isDirectory()) throw new Error('音效文件夹不存在')
    return this.importFiles(this.scanFiles(root, true))
  }

  createPage(name) {
    const page = newPage(String(name || '新页面').trim().slice(0, 30) || '新页面')
    this.data.pages.push(page)
    this.save()
    this.emitState()
    return page
  }

  updateButton(pageId, buttonId, patch = {}) {
    const button = this.button(pageId, buttonId)
    if (!button) throw new Error('未找到 Soundpad 按键')
    if (patch.clipId !== undefined && patch.clipId && !this.clip(String(patch.clipId))) throw new Error('未找到音效文件')
    if (patch.clipId !== undefined) button.clipId = String(patch.clipId || '')
    if (patch.label !== undefined) button.label = String(patch.label || '').trim().slice(0, 32)
    if (patch.fillColor !== undefined) button.fillColor = /^#[0-9a-f]{6}$/i.test(String(patch.fillColor)) ? String(patch.fillColor) : button.fillColor
    if (patch.progressColor !== undefined) button.progressColor = /^#[0-9a-f]{6}$/i.test(String(patch.progressColor)) ? String(patch.progressColor) : button.progressColor
    if (patch.imageFile !== undefined) {
      const imageFile = String(patch.imageFile || '')
      if (imageFile && (!IMAGE_EXTENSIONS.has(path.extname(imageFile).toLowerCase()) || !fs.existsSync(imageFile))) throw new Error('按钮图片不可用')
      button.imageFile = imageFile
    }
    if (patch.loop !== undefined && patch.loopCount === undefined) button.loopCount = patch.loop === true ? -1 : 0
    if (patch.loopCount !== undefined) button.loopCount = clamp(patch.loopCount, -1, 999, button.loopCount)
    if (patch.volume !== undefined) button.volume = clamp(patch.volume, 0, 100, button.volume)
    if (patch.delayMs !== undefined) button.delayMs = clamp(patch.delayMs, 0, 60000, button.delayMs)
    const clip = this.clip(button.clipId)
    if (!button.label && clip) button.label = clip.name
    this.save()
    this.emitState()
    return button
  }

  reorder(pageId, sourceButtonId, targetButtonId) {
    const page = this.page(pageId)
    if (!page) throw new Error('未找到 Soundpad 页面')
    const sourceIndex = page.buttons.findIndex((item) => item.id === sourceButtonId)
    const targetIndex = page.buttons.findIndex((item) => item.id === targetButtonId)
    if (sourceIndex < 0 || targetIndex < 0 || sourceIndex === targetIndex) return page
    const [button] = page.buttons.splice(sourceIndex, 1)
    page.buttons.splice(targetIndex, 0, button)
    this.save()
    this.emitState()
    return page
  }

  async updateSettings(patch = {}) {
    this.config.soundpad = { ...this.settings(), ...this.config.soundpad }
    if (patch.masterVolume !== undefined) this.config.soundpad.masterVolume = clamp(patch.masterVolume, 0, 100, this.masterVolume())
    if (patch.audioDevice !== undefined) this.config.soundpad.audioDevice = String(patch.audioDevice || 'auto')
    if (patch.externalEnabled !== undefined) this.config.soundpad.externalEnabled = patch.externalEnabled === true
    this.store.saveConfig()
    this.playerConfig.player.audioDevice = this.outputDevice()
    await this.player.setDevice(this.playerConfig.player.audioDevice).catch(() => {})
    await this.player.setVolume(this.masterVolume()).catch(() => {})
    this.emitState()
    return this.settings()
  }

  async playButton(pageId, buttonId) {
    const button = this.button(pageId, buttonId)
    const clip = button && this.clip(button.clipId)
    if (!button || !clip) throw new Error('该按键尚未配置音效')
    if (!fs.existsSync(clip.path)) throw new Error('音效文件不存在，请重新导入')
    const nonce = ++this.playNonce
    this.pendingButtonId = button.id
    this.currentButtonId = ''
    this.emitState()
    if (button.delayMs) await new Promise((resolve) => setTimeout(resolve, button.delayMs))
    if (nonce !== this.playNonce) return { cancelled: true }
    this.pendingButtonId = ''
    this.playerConfig.player.audioDevice = this.outputDevice()
    await this.player.setDevice(this.playerConfig.player.audioDevice).catch(() => {})
    await this.player.load({ uid: clip.id, url: clip.path, duration: 0 })
    const loopCount = Number(button.loopCount || 0)
    await this.player.send(['set_property', 'loop-file', loopCount < 0 ? 'inf' : loopCount > 0 ? String(loopCount) : 'no'])
    await this.player.setVolume(Math.round(this.masterVolume() * button.volume / 100))
    this.currentButtonId = button.id
    this.emitState()
    return this.publicButton(pageId, button)
  }

  async stop() {
    this.playNonce += 1
    this.currentButtonId = ''
    this.pendingButtonId = ''
    await this.player.stop()
    this.emitState()
  }

  buttonImage(buttonId) {
    for (const page of this.data.pages) {
      const button = page.buttons.find((item) => item.id === buttonId)
      if (button?.imageFile && fs.existsSync(button.imageFile)) return button.imageFile
    }
    return ''
  }
}

module.exports = { SoundpadManager }
