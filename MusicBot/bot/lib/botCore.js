const EventEmitter = require('events')
const os = require('os')
const path = require('path')
const {
  resolveNeteaseSong,
  importNeteasePlaylist,
  getNeteasePlaylistMeta,
  importLocalDirectory,
  preparePlaybackSong,
  compactExternalCaches,
  resolveNeteaseMetadata,
} = require('./musicService')

const TEXT = {
  request: '点歌',
  top: '顶歌',
  superTop: '超级置顶',
  skip: '切歌',
  next: '下一首',
  pause: '暂停',
  play: '播放',
  balance: '查询余额',
  playlist: '歌单',
}

const DEFAULT_COMMANDS = {
  request: '\u70b9\u6b4c',
  skip: '\u5207\u6b4c',
  top: '\u9876\u6b4c',
  superTop: '\u8d85\u7ea7\u7f6e\u9876',
  balance: '\u67e5\u8be2\u4f59\u989d',
}

function now() {
  return Date.now()
}

function requester(input = {}) {
  input = input || {}
  const roles = Array.isArray(input.roles) ? [...input.roles] : []
  if (input.isAdmin === true) roles.push('admin')
  if (input.isFanGroup === true || input.isFanClub === true) roles.push('fan_group')
  if (input.isMember === true || input.isVip === true || input.vipType > 0) roles.push('member')
  if (input.isGuardian === true || input.isStarGuardian === true) roles.push('guardian')
  const badges = Array.isArray(input.badges)
    ? input.badges.slice(0, 8).map((badge) => ({
      type: String(badge?.type || '').slice(0, 40),
      kind: String(badge?.kind || badge?.type || '').slice(0, 40),
      label: String(badge?.label || '').slice(0, 80),
      icon: String(badge?.icon || badge?.url || '').slice(0, 2048),
      bgColor: String(badge?.bgColor || '').slice(0, 40),
      fgColor: String(badge?.fgColor || '').slice(0, 40),
    })).filter((badge) => badge.label || badge.icon)
    : []
  const badgeTypes = new Set(badges.map((badge) => badge.type))
  if (badgeTypes.has('fans') || badgeTypes.has('fans_club')) roles.push('fan_group')
  if (badgeTypes.has('member') || badgeTypes.has('annual_member') || badgeTypes.has('vip')) roles.push('member')
  if (badgeTypes.has('guard')) roles.push('guardian')
  return {
    id: input.userId || input.id || 'test-user',
    name: input.nickname || input.name || '测试用户',
    avatar: input.avatar || input.avatarUrl || input.avatar_url || '',
    douyinId: input.douyinId || input.douyinNo || input.uniqueId || input.unique_id || '',
    roles,
    badges,
  }
}

function commandArg(text, command) {
  return text.slice(command.length).trim()
}

function commandMatches(text, command, allowEmpty = false, allowAttachedArgument = false) {
  const value = String(command || '').trim()
  if (!value) return false
  if (text === value) return allowEmpty
  if (!text.startsWith(value)) return false
  const suffix = text.slice(value.length)
  return /^\s/.test(suffix) || (allowAttachedArgument && suffix.length > 0)
}

function isAdmin(user) {
  return (Array.isArray(user?.roles) ? user.roles : []).some((role) => ['admin', 'administrator', 'moderator', 'owner', '主播'].includes(String(role).toLowerCase()))
}

function hasFanGroup(user) {
  return (Array.isArray(user?.roles) ? user.roles : []).some((role) => ['fan', 'fans', 'fan_group', 'fangroup', '粉丝', '粉丝团'].includes(String(role).toLowerCase()))
}

function hasMember(user) {
  return (Array.isArray(user?.roles) ? user.roles : []).some((role) => ['member', 'vip', '\u4f1a\u5458', '\u5927\u4f1a\u5458'].includes(String(role).toLowerCase()))
}

function hasGuardian(user) {
  return (Array.isArray(user?.roles) ? user.roles : []).some((role) => ['guardian', 'star_guardian', 'star-guardian', '\u661f\u5b88\u62a4'].includes(String(role).toLowerCase()))
}

function publicSong(song, includeLyrics = false) {
  if (!song) return null
  const copy = { ...song }
  delete copy.yrc
  delete copy.url
  delete copy.filePath
  if (!includeLyrics) {
    delete copy.lyric
    delete copy.wordLyrics
  } else if (copy.lyricMode !== 'word') {
    copy.wordLyrics = []
  }
  return copy
}

function isDirectIdlePlayback(song) {
  return song?.requestKind === 'idle-auto' || song?.requestKind === 'idle-manual'
}

function compactSong(song, options = {}) {
  if (!song) return null
  const {
    keepLyrics = false,
    keepUrl = false,
    keepFilePath = false,
  } = options
  const copy = { ...song }
  delete copy.yrc
  if (!keepLyrics) {
    delete copy.lyric
    delete copy.wordLyrics
    delete copy.lyricMode
  }
  if (!keepUrl) delete copy.url
  if (!keepFilePath) delete copy.filePath
  return copy
}

class BotCore extends EventEmitter {
  constructor(store, player) {
    super()
    this.store = store
    this.config = store.config
    this.persisted = store.state
    this.player = player
    this.startedAt = now()
    // Every state payload shares this server clock and monotonically increasing revision.
    // Clients use them to reject stale WebSocket/HTTP responses and extrapolate playback.
    this.stateRevision = 0
    this.stateBootId = `${this.startedAt}-${process.pid}-${Math.random().toString(36).slice(2, 10)}`
    this.current = null
    this.queue = []
    this.history = []
    this.idleNext = null
    this.idleImmediate = null
    this.idleCursor = 0
    this.syncBlacklist()
    this.syncTitleFilters()
    this.ensureIdlePlaylists()
    this.playback = {
      status: 'idle',
      position: 0,
      duration: 0,
      volume: this.config.player?.volume ?? 80,
      message: '',
      updatedAt: now(),
    }
    this.overlay = null
    this.lastBroadcast = null
    this.broadcastSequence = 0
    this.lastRequestAt = new Map()
    this.nextPromise = null
    this.preloadPromise = null
    this.preloadRequested = false
    this.prepareTasks = new Map()
    this.cacheTaskTail = Promise.resolve()
    this.songResolveQueue = []
    this.songResolveActive = 0
    this.maxSongResolveActive = 2
    this.maxSongResolvePending = 8
    this.lastProgressPublishAt = 0
    this.maxRequestTimes = Math.max(100, Number(process.env.MUSICBOT_MAX_REQUEST_USERS || 2000))
    this.maxRssMb = Math.min(500, Math.max(256, Number(process.env.MUSICBOT_MAX_RSS_MB || 500)))
    this.compactRssMb = Math.max(160, Math.min(200, this.maxRssMb - 120))
    this.maintenanceIntervalMs = Math.max(30 * 1000, Number(process.env.MUSICBOT_MAINTENANCE_MS || 2 * 60 * 1000))
    if (Number(this.config.queue.preloadCount) !== 1) {
      this.config.queue.preloadCount = 1
      this.store.saveConfig()
    }
    this.maintenanceTimer = setInterval(() => {
      try {
        this.compactRuntime()
      } catch (error) {
        console.error('[MEM] compact failed:', error.message)
      }
    }, this.maintenanceIntervalMs)
    this.maintenanceTimer.unref()
    this.compactRuntime()
    this.bindPlayer()
    setImmediate(() => this.enrichLegacyBlacklist().catch((error) => {
      console.error('[BLACKLIST] metadata migration failed:', error.message)
    }))
    if (this.config.queue.autoIdle !== false && this.selectedIdleSongs().length > 0) {
      setImmediate(() => this.startNextIfIdleInBackground())
    }
  }

  bindPlayer() {
    if (!this.player) return
    this.player.on('progress', (progress) => {
      const previous = this.playback
      const timestamp = now()
      const status = this.current ? (progress.status || this.playback.status) : 'idle'
      const position = Number(progress.position || 0)
      const duration = Number(progress.duration || this.playback.duration || 0)
      const volume = Number(progress.volume || this.playback.volume || 0)
      this.playback = {
        ...this.playback,
        status,
        position,
        duration,
        volume,
        updatedAt: timestamp,
      }
      const shouldPublish =
        previous.status !== status ||
        Math.abs((previous.duration || 0) - duration) > 0.5 ||
        Math.abs((previous.volume || 0) - volume) > 0.5 ||
        timestamp - this.lastProgressPublishAt >= 1000
      if (shouldPublish) {
        this.lastProgressPublishAt = timestamp
        this.publish({ includeLyrics: false, includeIdleList: false })
      }
    })
    this.player.on('ended', () => {
      this.next('ended').catch((error) => this.notice(error.message))
    })
    this.player.on('error-state', (message) => {
      if (message) this.notice(`播放器错误：${message}`)
    })
  }

  ensureIdlePlaylists() {
    const existing = Array.isArray(this.persisted.idlePlaylists) ? this.persisted.idlePlaylists : []
    if (existing.length > 0) {
      this.persisted.idlePlaylists = existing.map((playlist, index) => ({
        id: playlist.id || `playlist-${index + 1}`,
        name: playlist.name || '未命名歌单',
        coverUrl: playlist.coverUrl || '',
        type: playlist.type || 'custom',
        sourceId: playlist.sourceId || '',
        enabled: playlist.enabled !== false,
        songs: Array.isArray(playlist.songs) ? playlist.songs : [],
      }))
    } else {
      this.persisted.idlePlaylists = [{
        id: 'custom-default',
        name: '自定义歌单',
        coverUrl: './image/Frame_2_19.png',
        type: 'custom',
        sourceId: '',
        enabled: true,
        songs: Array.isArray(this.persisted.idleList) ? this.persisted.idleList : [],
      }]
    }
    this.syncIdleList()
    this.save()
  }

  syncIdleList() {
    this.persisted.idleList = this.persisted.idlePlaylists.flatMap((playlist) => playlist.songs || [])
  }

  selectedIdleSongs() {
    return this.persisted.idlePlaylists
      .filter((playlist) => playlist.enabled !== false)
      .flatMap((playlist) => (playlist.songs || []).map((song) => ({
        ...song,
        idlePlaylistId: playlist.id,
        idlePlaylistName: playlist.name,
      })))
      .filter((song) => !this.isBlacklisted(song))
  }

  idlePlaylistById(id) {
    return this.persisted.idlePlaylists.find((playlist) => playlist.id === id)
  }

  upsertIdlePlaylist(playlist) {
    const normalized = {
      id: playlist.id,
      name: playlist.name || '未命名歌单',
      coverUrl: playlist.coverUrl || '',
      type: playlist.type || 'custom',
      sourceId: playlist.sourceId || '',
      enabled: playlist.enabled !== false,
      songs: Array.isArray(playlist.songs) ? playlist.songs : [],
    }
    const index = this.persisted.idlePlaylists.findIndex((item) => item.id === normalized.id)
    if (index >= 0) this.persisted.idlePlaylists[index] = normalized
    else this.persisted.idlePlaylists.push(normalized)
    this.syncIdleList()
    this.compactIdleList()
    this.save()
    this.publish()
    return normalized
  }

  snapshot(options = {}) {
    const memory = process.memoryUsage()
    const includeLyrics = options.includeLyrics !== false
    const includeIdleList = options.includeIdleList !== false
    const idleRuntime = new Map()
    for (const song of [this.current, this.idleNext, ...this.queue]) {
      if (song?.idlePlaylistId) {
        idleRuntime.set(`${song.idlePlaylistId}\u0000${song.uid}`, {
          ...song,
          isPlaying: song === this.current,
        })
      }
    }
    const visibleQueue = [
      ...(this.current && !isDirectIdlePlayback(this.current)
        ? [{ ...publicSong(this.current, false), isPlaying: true }]
        : []),
      ...this.queue.map((song) => publicSong(song, false)),
    ]
    return {
      sync: {
        protocol: 'musicbot-state-v1',
        revision: this.stateRevision,
        serverTime: now(),
        bootId: this.stateBootId,
      },
      current: publicSong(this.current, includeLyrics),
      queue: visibleQueue,
      history: this.history.slice(-20).map((song) => publicSong(song, false)),
      blacklist: this.persisted.blacklist.map((entry) => ({ ...entry })),
      titleFilters: this.persisted.titleFilters.slice(),
      idleList: includeIdleList ? this.persisted.idleList.map((song) => publicSong(song, false)) : undefined,
      idlePlaylists: includeIdleList
        ? this.persisted.idlePlaylists.map((playlist) => ({
          ...playlist,
          songs: playlist.songs.map((song) => publicSong({
            ...song,
            ...(idleRuntime.get(`${playlist.id}\u0000${song.uid}`) || {}),
          }, false)),
        }))
        : undefined,
      playback: this.playback,
      player: this.player ? this.player.snapshot() : null,
      overlay: this.overlay && this.overlay.expiresAt > now() ? this.overlay : null,
      broadcast: this.lastBroadcast,
      system: {
        uptimeSeconds: Math.round((now() - this.startedAt) / 1000),
        node: process.version,
        platform: `${os.platform()} ${os.arch()}`,
        rssMb: Math.round(memory.rss / 1024 / 1024),
        heapUsedMb: Math.round(memory.heapUsed / 1024 / 1024),
        queueLength: visibleQueue.length,
        idleLength: this.selectedIdleSongs().length,
        preloading: Boolean(this.preloadPromise),
        idleNext: this.idleNext ? this.idleNext.title : '',
        wsTime: new Date().toISOString(),
      },
      config: {
        queue: this.config.queue,
        display: this.config.display,
        player: this.config.player,
        audioNormalization: this.config.audioNormalization || {
          enabled: false,
          targetLufs: -14,
          maxGainDb: 6,
          minGainDb: -12,
        },
        commands: this.config.commands || DEFAULT_COMMANDS,
        controls: this.config.controls || {},
        music: {
          bitrate: this.config.music.bitrate,
          level: this.config.music.level,
          enableUnblock: this.config.music.enableUnblock,
          hasCookie: Boolean(this.config.music.neteaseCookie),
          login: this.config.music.login || null,
        },
        permissions: this.config.permissions,
        points: this.config.points,
      },
    }
  }

  publish(options = {}) {
    this.stateRevision += 1
    this.emit('state', this.snapshot(options))
  }

  notice(message, extra = {}) {
    this.overlay = {
      message,
      ...extra,
      expiresAt: now() + (this.config.display.overlaySeconds || 5) * 1000,
    }
    this.publish({ includeLyrics: false, includeIdleList: false })
  }

  emitLiveBroadcast(kind, message, extra = {}) {
    const payload = {
      id: ++this.broadcastSequence,
      channel: 'live-ui',
      kind,
      message,
      createdAt: new Date().toISOString(),
      ...extra,
    }
    this.lastBroadcast = payload
    this.emit('live-broadcast', payload)
    return payload
  }

  legacyCommandCost(action) {
    const freeKey = {
      request: 'freeRequest',
      skip: 'freeSkip',
      top: 'freeTop',
      superTop: 'freeSuperTop',
    }[action]
    if (freeKey && this.config.permissions?.[freeKey] !== false) return 0
    return Number(this.config.points?.[`${action}Cost`] || 0)
  }

  legacyCommandAccess(user, action) {
    const permissions = this.config.permissions || {}
    const admin = isAdmin(user)
    if (action === 'request' && permissions.requestEnabled === false && !admin) {
      const error = new Error('\u70b9\u6b4c\u529f\u80fd\u5df2\u5173\u95ed')
      error.code = 'REQUEST_DISABLED'
      throw error
    }
    if (action === 'request' && permissions.requestAdminOnly && !admin) {
      const error = new Error('\u4ec5\u5141\u8bb8\u7ba1\u7406\u5458\u70b9\u6b4c')
      error.code = 'ADMIN_REQUIRED'
      throw error
    }
    if (action === 'request' && permissions.requestFanOnly && !admin && !hasFanGroup(user)) {
      const error = new Error('请加入粉丝团后再试')
      error.code = 'FAN_REQUIRED'
      throw error
    }
    if (action === 'skip' && permissions.freeSkip === false && !admin && this.commandCost(action) <= 0) {
      const error = new Error('非管理员不可切歌')
      error.code = 'ADMIN_REQUIRED'
      throw error
    }
    if ((action === 'top' || action === 'superTop') && permissions[action === 'top' ? 'freeTop' : 'freeSuperTop'] === false && !admin && this.commandCost(action) <= 0) {
      const error = new Error('非管理员不可置顶')
      error.code = 'ADMIN_REQUIRED'
      throw error
    }
    const cost = this.commandCost(action)
    const points = Number(this.persisted.users[user.id]?.points || 0)
    if (!admin && cost > points) {
      const error = new Error('可用积分不足')
      error.code = 'INSUFFICIENT_POINTS'
      throw error
    }
  }

  requestRolePolicy(user) {
    const permissions = this.config.permissions || {}
    if (permissions.freeRequest !== false) return { allowed: true, cost: 0 }
    const roles = [
      { only: 'requestAdminOnly', free: 'requestAdminFree', match: isAdmin },
      { only: 'requestFanOnly', free: 'requestFanFree', match: hasFanGroup },
      { only: 'requestMemberOnly', free: 'requestMemberFree', match: hasMember },
      { only: 'requestGuardianOnly', free: 'requestGuardianFree', match: hasGuardian },
    ]
    const selected = roles.filter((role) => permissions[role.only] === true)
    if (selected.length === 0) return { allowed: true, cost: Number(this.config.points?.requestCost || 0) }
    const matched = selected.filter((role) => role.match(user))
    if (matched.length === 0) {
      const error = new Error('\u65e0\u70b9\u6b4c\u6743\u9650')
      error.code = 'NO_REQUEST_PERMISSION'
      throw error
    }
    return {
      allowed: true,
      cost: matched.some((role) => permissions[role.free] === true)
        ? 0
        : Number(this.config.points?.requestCost || 0),
    }
  }

  commandCost(action, user = null) {
    if (action === 'request') return this.requestRolePolicy(user || { roles: [] }).cost
    const freeKey = {
      skip: 'freeSkip',
      top: 'freeTop',
      superTop: 'freeSuperTop',
    }[action]
    const adminFreeKey = {
      skip: 'adminFreeSkip',
      top: 'adminFreeTop',
      superTop: 'adminFreeSuperTop',
    }[action]
    if (user && isAdmin(user) && adminFreeKey && this.config.permissions?.[adminFreeKey] !== false) return 0
    if (freeKey && this.config.permissions?.[freeKey] !== false) return 0
    return Number(this.config.points?.[`${action}Cost`] || 0)
  }

  commandAccess(user, action) {
    const permissions = this.config.permissions || {}
    const admin = isAdmin(user)
    if (action === 'request') {
      if (permissions.requestEnabled === false) {
        const error = new Error('\u70b9\u6b4c\u529f\u80fd\u5df2\u5173\u95ed')
        error.code = 'REQUEST_DISABLED'
        throw error
      }
      const policy = this.requestRolePolicy(user)
      const points = Number(this.persisted.users[user.id]?.points || 0)
      if (policy.cost > points) {
        const error = new Error('\u53ef\u7528\u79ef\u5206\u4e0d\u8db3')
        error.code = 'INSUFFICIENT_POINTS'
        throw error
      }
      return policy
    }
    const cost = this.commandCost(action, user)
    if ((action === 'skip' || action === 'top' || action === 'superTop') && !admin && cost <= 0 && permissions[action === 'skip' ? 'freeSkip' : action === 'top' ? 'freeTop' : 'freeSuperTop'] === false) {
      const error = new Error('\u975e\u7ba1\u7406\u5458\u4e0d\u53ef\u64cd\u4f5c')
      error.code = 'ADMIN_REQUIRED'
      throw error
    }
    const points = Number(this.persisted.users[user.id]?.points || 0)
    if (cost > points) {
      const error = new Error('\u53ef\u7528\u79ef\u5206\u4e0d\u8db3')
      error.code = 'INSUFFICIENT_POINTS'
      throw error
    }
  }

  chargeCommand(user, action) {
    const cost = this.commandCost(action, user)
    if (!cost) return
    const account = this.persisted.users[user.id] || { points: 0 }
    account.points = Math.max(0, Number(account.points || 0) - cost)
    this.persisted.users[user.id] = account
    this.save()
  }

  broadcastFailure(action, user, subject, error) {
    const reason = error.code === 'NO_REQUEST_PERMISSION'
      ? '\u65e0\u70b9\u6b4c\u6743\u9650'
      : error.code === 'REQUEST_DISABLED'
        ? '\u70b9\u6b4c\u529f\u80fd\u5df2\u5173\u95ed'
        : error.code === 'FAN_REQUIRED'
      ? '请加入粉丝团后再试'
      : error.code === 'INSUFFICIENT_POINTS'
        ? '可用积分不足'
        : error.code === 'COOLDOWN'
          ? `请等待${error.secondsLeft || 0}秒后再试`
          : error.message
    if (action === 'request') return this.emitLiveBroadcast('request-failed', `@${user.name} 点播《${subject}》失败，${reason}`)
    if (action === 'skip') return this.emitLiveBroadcast('skip-failed', `@${user.name} 切歌失败，${reason}`)
    if (action === 'top' || action === 'superTop') return this.emitLiveBroadcast('top-failed', `@${user.name} 置顶《${subject}》失败，${reason}`)
    return null
  }

  compactHistory(limit = 20) {
    if (this.history.length > limit) this.history = this.history.slice(-limit)
    this.history = this.history.map((song) => compactSong(song, {
      keepLyrics: false,
      keepUrl: false,
      keepFilePath: false,
    }))
  }

  compactQueue() {
    const preloadCount = 1
    for (let i = 0; i < this.queue.length; i += 1) {
      const song = this.queue[i]
      const keepPrepared = i < preloadCount || song?.requestKind === 'request'
      const compacted = compactSong(song, {
        keepLyrics: keepPrepared,
        keepUrl: keepPrepared || song?.source === 'local',
        keepFilePath: song?.source === 'local',
      })
      if (!keepPrepared && compacted.source !== 'local' && compacted.cacheStatus === 'ready') {
        compacted.cacheStatus = 'pending'
        compacted.cachedAt = 0
        compacted.cacheExpiresAt = 0
      }
      this.queue[i] = compacted
    }
  }

  compactIdleList() {
    this.persisted.idlePlaylists = this.persisted.idlePlaylists.map((playlist) => ({
      ...playlist,
      songs: playlist.songs.map((song) => {
        const local = song?.source === 'local'
        const compacted = compactSong(song, {
          keepLyrics: local,
          keepUrl: local,
          keepFilePath: local,
        })
        compacted.cacheStatus = local ? 'ready' : 'pending'
        if (!local) {
          compacted.cachedAt = 0
          compacted.cacheExpiresAt = 0
        }
        return compacted
      }),
    }))
    this.syncIdleList()
  }

  compactRuntime() {
    const before = process.memoryUsage()
    this.pruneRequestTimes()
    this.compactHistory()
    this.compactQueue()
    this.compactIdleList()
    const rssMb = Math.round(before.rss / 1024 / 1024)
    const underPressure = rssMb >= this.compactRssMb
    const cache = compactExternalCaches(
      underPressure ? 30 * 1000 : 3 * 60 * 1000,
      underPressure ? 20 : 80,
    )
    if (typeof global.gc === 'function') global.gc()
    const after = process.memoryUsage()
    console.log(
      `[MEM] compact rss=${Math.round(before.rss / 1024 / 1024)}->${Math.round(after.rss / 1024 / 1024)}MB ` +
      `heap=${Math.round(before.heapUsed / 1024 / 1024)}->${Math.round(after.heapUsed / 1024 / 1024)}MB ` +
      `queue=${this.queue.length} history=${this.history.length} idle=${this.persisted.idleList.length} ` +
      `externalCache=${cache.entriesBefore}->${cache.entriesAfter}`,
    )
  }

  ensureMemoryCapacity() {
    const rssMb = Math.round(process.memoryUsage().rss / 1024 / 1024)
    if (rssMb < this.maxRssMb - 32) return
    this.compactRuntime()
    const afterMb = Math.round(process.memoryUsage().rss / 1024 / 1024)
    if (afterMb >= this.maxRssMb - 8) {
      const error = new Error('\u670d\u52a1\u5668\u6b63\u5728\u91ca\u653e\u5185\u5b58\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5')
      error.status = 503
      error.code = 'MEMORY_PRESSURE'
      throw error
    }
  }

  save() {
    this.store.saveState()
  }

  normalizeUserRecord(id, input = {}) {
    return {
      id: String(id || input.id || '').trim().slice(0, 128),
      avatar: String(input.avatar || '').trim().slice(0, 2048),
      remark: String(input.remark || '').trim().slice(0, 100),
      points: Math.max(0, Math.min(999999999, Math.trunc(Number(input.points || 0) || 0))),
      nickname: String(input.nickname || input.name || '').trim().slice(0, 100),
      douyinId: String(input.douyinId || '').trim().slice(0, 100),
      updatedAt: Number(input.updatedAt || now()),
    }
  }

  userRecords() {
    return Object.entries(this.persisted.users || {})
      .map(([id, account]) => this.normalizeUserRecord(id, account))
      .filter((account) => account.id)
      .sort((a, b) => b.updatedAt - a.updatedAt)
  }

  touchUser(user) {
    if (!user?.id) return null
    const current = this.persisted.users[user.id] || { points: 0 }
    const next = this.normalizeUserRecord(user.id, {
      ...current,
      avatar: user.avatar || current.avatar,
      nickname: user.name || current.nickname,
      douyinId: user.douyinId || current.douyinId,
      updatedAt: current.updatedAt || now(),
    })
    const changed = !this.persisted.users[user.id] || ['avatar', 'nickname', 'douyinId'].some((key) => next[key] !== (current[key] || ''))
    if (changed) {
      next.updatedAt = now()
      this.persisted.users[user.id] = next
      this.save()
    }
    return this.persisted.users[user.id] || next
  }

  updateUser(id, patch = {}) {
    const key = String(id || '').trim()
    if (!key || !this.persisted.users[key]) {
      const error = new Error('\u7528\u6237\u4e0d\u5b58\u5728')
      error.status = 404
      throw error
    }
    const account = this.normalizeUserRecord(key, {
      ...this.persisted.users[key],
      ...patch,
      updatedAt: now(),
    })
    this.persisted.users[key] = account
    this.save()
    return account
  }

  removeUsers(ids) {
    const values = Array.isArray(ids) ? ids : [ids]
    let removed = 0
    for (const id of values.slice(0, 10000)) {
      const key = String(id || '')
      if (key && Object.prototype.hasOwnProperty.call(this.persisted.users, key)) {
        delete this.persisted.users[key]
        removed += 1
      }
    }
    if (removed) this.save()
    return removed
  }

  exportManagedData(sections = []) {
    const selected = new Set(Array.isArray(sections) ? sections : [])
    const data = {}
    if (selected.has('idle')) {
      data.idle = {
        options: {
          mode: this.config.queue.idleMode || 'sequence',
          autoIdle: this.config.queue.autoIdle !== false,
        },
        playlists: this.persisted.idlePlaylists,
      }
    }
    if (selected.has('filters')) data.filters = this.persisted.titleFilters.slice()
    if (selected.has('blacklist')) data.blacklist = this.persisted.blacklist.map((entry) => ({ ...entry }))
    if (selected.has('points')) data.points = this.userRecords()
    return { version: 1, exportedAt: new Date().toISOString(), sections: [...selected], data }
  }

  importManagedData(input = {}) {
    const data = input.data || {}
    const selected = new Set(Array.isArray(input.sections) ? input.sections : Object.keys(data))
    const result = {}
    if (selected.has('idle') && data.idle) result.idle = this.importIdleConfig(data.idle)
    if (selected.has('filters') && Array.isArray(data.filters)) {
      result.filters = this.syncTitleFilters(data.filters).length
    }
    if (selected.has('blacklist') && Array.isArray(data.blacklist)) {
      result.blacklist = this.syncBlacklist(data.blacklist).length
    }
    if (selected.has('points') && Array.isArray(data.points)) {
      const users = {}
      for (const value of data.points.slice(0, 10000)) {
        const account = this.normalizeUserRecord(value?.id, value)
        if (account.id) users[account.id] = account
      }
      this.persisted.users = users
      result.points = Object.keys(users).length
    }
    this.save()
    this.store.saveConfig()
    this.publish({ includeLyrics: false, includeIdleList: false })
    return result
  }

  normalizeBlacklistEntry(entry) {
    const sourceValue = typeof entry === 'string' ? entry : (entry?.uid || `${entry?.source || ''}:${entry?.sourceId || ''}`)
    const separator = sourceValue.indexOf(':')
    const source = typeof entry === 'object' && entry?.source
      ? entry.source
      : (separator > 0 ? sourceValue.slice(0, separator) : 'unknown')
    const sourceId = typeof entry === 'object' && entry?.sourceId
      ? String(entry.sourceId)
      : (separator > 0 ? sourceValue.slice(separator + 1) : sourceValue)
    const uid = typeof entry === 'object' && entry?.uid
      ? entry.uid
      : (separator > 0 ? sourceValue : `${source}:${sourceId}`)
    return {
      uid,
      source,
      sourceId,
      title: typeof entry === 'object' && entry?.title ? entry.title : sourceId,
      artist: typeof entry === 'object' ? (entry.artist || '') : '',
      coverUrl: typeof entry === 'object' ? (entry.coverUrl || '') : '',
      duration: typeof entry === 'object' ? Number(entry.duration || 0) : 0,
      playbackSource: typeof entry === 'object' ? (entry.playbackSource || '') : '',
      blacklistedAt: typeof entry === 'object' ? Number(entry.blacklistedAt || now()) : now(),
    }
  }

  syncBlacklist(values = this.persisted.blacklist) {
    const seen = new Set()
    const normalized = []
    for (const value of Array.isArray(values) ? values : []) {
      const entry = this.normalizeBlacklistEntry(value)
      const key = entry.uid || `${entry.source}:${entry.sourceId}`
      if (!key || seen.has(key)) continue
      seen.add(key)
      normalized.push(entry)
      if (normalized.length >= 500) break
    }
    this.persisted.blacklist = normalized
    this.blacklistKeys = new Set(normalized.flatMap((entry) => [entry.uid, `${entry.source}:${entry.sourceId}`]))
    return normalized
  }

  isBlacklisted(song) {
    return this.blacklistKeys.has(song.uid) ||
      this.blacklistKeys.has(`${song.source}:${song.sourceId}`)
  }

  syncTitleFilters(values = this.persisted.titleFilters) {
    const seen = new Set()
    const normalized = []
    for (const value of Array.isArray(values) ? values : []) {
      const keyword = String(value || '').trim().slice(0, 100)
      const matcher = keyword.toLocaleLowerCase()
      if (!keyword || seen.has(matcher)) continue
      seen.add(matcher)
      normalized.push(keyword)
      if (normalized.length >= 500) break
    }
    this.persisted.titleFilters = normalized
    this.titleFilterMatchers = normalized.map((keyword) => keyword.toLocaleLowerCase())
    return normalized
  }

  matchesTitleText(value) {
    if (!this.titleFilterMatchers?.length) return false
    const title = String(value || '').toLocaleLowerCase()
    return this.titleFilterMatchers.some((keyword) => title.includes(keyword))
  }

  matchesTitleFilter(song) {
    return this.matchesTitleText(song?.title)
  }

  addTitleFilters(values, replace = false) {
    const incoming = Array.isArray(values) ? values : [values]
    const result = this.syncTitleFilters(replace ? incoming : [...this.persisted.titleFilters, ...incoming])
    this.save()
    this.publish({ includeLyrics: false, includeIdleList: false })
    return result.slice()
  }

  removeTitleFilter(index) {
    const position = Number(index)
    if (!Number.isInteger(position) || position < 0 || position >= this.persisted.titleFilters.length) {
      const error = new Error('Filter keyword not found')
      error.status = 404
      throw error
    }
    const [removed] = this.persisted.titleFilters.splice(position, 1)
    this.syncTitleFilters()
    this.save()
    this.publish({ includeLyrics: false, includeIdleList: false })
    return removed
  }

  clearTitleFilters() {
    const removed = this.persisted.titleFilters.length
    this.syncTitleFilters([])
    this.save()
    this.publish({ includeLyrics: false, includeIdleList: false })
    return removed
  }

  ensureQueueRoom(count = 1) {
    if (this.queue.length + count > this.config.queue.maxLength) {
      const error = new Error('当前点歌列表已满，请稍后再点歌')
      error.status = 409
      throw error
    }
  }

  ensureCooldown(user) {
    const seconds = this.config.queue.userCooldownSeconds || 0
    if (!seconds) return
    const last = this.lastRequestAt.get(user.id) || 0
    const left = seconds - Math.floor((now() - last) / 1000)
    if (left > 0) {
      const error = new Error(`${left} 秒后才可以再次点歌`)
      error.status = 429
      error.code = 'COOLDOWN'
      error.secondsLeft = left
      throw error
    }
  }

  markCooldown(user) {
    if (this.config.queue.userCooldownSeconds) this.lastRequestAt.set(user.id, now())
  }

  pruneRequestTimes() {
    if (this.lastRequestAt.size === 0) return
    const cooldownMs = Math.max(60 * 1000, Number(this.config.queue.userCooldownSeconds || 0) * 2000)
    const cutoff = now() - cooldownMs
    for (const [userId, timestamp] of this.lastRequestAt) {
      if (timestamp < cutoff) this.lastRequestAt.delete(userId)
    }
    if (this.lastRequestAt.size <= this.maxRequestTimes) return
    const overflow = this.lastRequestAt.size - this.maxRequestTimes
    let removed = 0
    for (const userId of this.lastRequestAt.keys()) {
      this.lastRequestAt.delete(userId)
      removed += 1
      if (removed >= overflow) break
    }
  }

  duplicateInActive(song) {
    if (this.current?.uid === song.uid) return true
    return this.queue.some((item) => item.uid === song.uid)
  }

  queueCacheTask(task) {
    const queued = this.cacheTaskTail.then(task, task)
    this.cacheTaskTail = queued.catch(() => {})
    return queued
  }

  resolveSong(query) {
    if (this.songResolveQueue.length >= this.maxSongResolvePending) {
      const error = new Error('\u5f53\u524d\u6b4c\u66f2\u8bf7\u6c42\u8fc7\u591a\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5')
      error.status = 429
      error.code = 'REQUEST_BUSY'
      throw error
    }
    return new Promise((resolve, reject) => {
      this.songResolveQueue.push({ query, resolve, reject })
      this.drainSongResolveQueue()
    })
  }

  drainSongResolveQueue() {
    while (this.songResolveActive < this.maxSongResolveActive && this.songResolveQueue.length) {
      const job = this.songResolveQueue.shift()
      this.songResolveActive += 1
      Promise.resolve()
        .then(() => resolveNeteaseSong(job.query, this.config))
        .then(job.resolve, job.reject)
        .finally(() => {
          this.songResolveActive -= 1
          this.drainSongResolveQueue()
        })
    }
  }

  async ensurePrepared(song, force = false, options = {}) {
    if (song.source === 'local') return song
    if (!force && song.url && song.cacheExpiresAt && song.cacheExpiresAt > now()) return song
    const taskKey = song.uid || `${song.source}:${song.sourceId}`
    if (this.prepareTasks.has(taskKey)) {
      try {
        return await this.prepareTasks.get(taskKey)
      } catch (error) {
        if (options.allowUnblock === false) throw error
      }
    }
    const task = this.queueCacheTask(async () => {
      if (!force && song.url && song.cacheExpiresAt && song.cacheExpiresAt > now()) return song
      const prepared = await preparePlaybackSong(song, this.config, options)
      prepared.cacheStatus = 'ready'
      prepared.cachedAt = now()
      prepared.cacheExpiresAt = now() + 10 * 60 * 1000
      Object.assign(song, prepared)
      return song
    }).finally(() => {
      if (this.prepareTasks.get(taskKey) === task) this.prepareTasks.delete(taskKey)
    })
    this.prepareTasks.set(taskKey, task)
    return task
  }

  schedulePreload() {
    if (this.preloadPromise) {
      this.preloadRequested = true
      return
    }
    this.preloadRequested = false
    this.preloadPromise = this.preloadNext()
      .catch((error) => this.notice(`预取缓存失败：${error.message}`))
      .finally(() => {
        this.preloadPromise = null
        this.compactQueue()
        this.publish({ includeLyrics: false, includeIdleList: Boolean(this.idleNext) })
        if (this.preloadRequested) {
          this.preloadRequested = false
          setImmediate(() => this.schedulePreload())
        }
      })
  }

  async preloadNext() {
    const song = this.queue[0]
    if (!song) {
      await this.preloadIdleNext()
      return
    }
    if (song.source === 'local') {
      song.cacheStatus = 'ready'
      return
    }
    if (song.cacheStatus === 'ready' && song.cacheExpiresAt > now()) return
    song.cacheStatus = 'loading'
    this.publish({ includeLyrics: false, includeIdleList: false })
    try {
      await this.ensurePrepared(song, false, { allowUnblock: false })
    } catch (error) {
      song.cacheStatus = 'failed'
      song.cacheError = error.message
    }
  }

  createIdleCandidate() {
    const songs = this.selectedIdleSongs()
    if (songs.length === 0) return null
    const mode = this.config.queue.idleMode || 'sequence'
    if (mode === 'sequence' && this.idleCursor >= songs.length) return null
    const random = mode === 'random'
    const start = random ? Math.floor(Math.random() * songs.length) : this.idleCursor % songs.length
    for (let attempt = 0; attempt < songs.length; attempt += 1) {
      const index = mode === 'sequence' ? start + attempt : (start + attempt) % songs.length
      if (index >= songs.length) break
      const song = songs[index]
      this.idleCursor = mode === 'sequence' ? index + 1 : (index + 1) % songs.length
      if (songs.length > 1 && song.uid === this.current?.uid) continue
      return {
        ...song,
        requestedBy: { id: 'idle-list', name: '空闲歌单', roles: [] },
        requestedAt: now(),
        requestKind: 'idle-auto',
        cacheStatus: song.source === 'local' ? 'ready' : 'pending',
      }
    }
    return null
  }

  async preloadIdleNext() {
    if (!this.current || this.config.queue.autoIdle === false) return
    if (!this.idleNext) this.idleNext = this.createIdleCandidate()
    const song = this.idleNext
    if (!song) return
    if (song.source === 'local') {
      song.cacheStatus = 'ready'
      return
    }
    if (song.cacheStatus === 'ready' && song.cacheExpiresAt > now()) return
    song.cacheStatus = 'loading'
    this.publish({ includeLyrics: false })
    try {
      await this.ensurePrepared(song, false, { allowUnblock: false })
    } catch (error) {
      song.cacheStatus = 'failed'
      song.cacheError = error.message
    }
  }

  async requestSong(query, userInput, options = {}) {
    this.ensureMemoryCapacity()
    const user = requester(userInput)
    const privileged = options.privileged === true
    const origin = options.origin || 'backend'
    if (this.matchesTitleText(query)) return { ignored: true, reason: 'title-filter' }
    const song = await this.resolveSong(query)
    if (this.matchesTitleFilter(song)) return { ignored: true, reason: 'title-filter' }
    this.ensureQueueRoom()
    const repeatedActiveSong = this.duplicateInActive(song)
    if (!privileged && !repeatedActiveSong) this.ensureCooldown(user)
    if (this.idleNext?.uid === song.uid) this.idleNext = null
    if (this.isBlacklisted(song)) {
      const error = new Error('该歌曲已被拉黑')
      error.status = 409
      throw error
    }
    const queued = {
      ...song,
      requestedBy: user,
      requestedAt: now(),
      requestKind: 'request',
      requestOrigin: origin,
      cacheStatus: song.url ? 'ready' : 'pending',
      cachedAt: song.url ? now() : 0,
      cacheExpiresAt: song.url ? now() + 10 * 60 * 1000 : 0,
    }
    this.queue.push(queued)
    if (!privileged && !repeatedActiveSong) this.markCooldown(user)
    this.notice(`@${user.name} 点播《${queued.title}》成功`)
    if (origin === 'danmaku') {
      this.emitLiveBroadcast('request', `@${user.name} 点播《${queued.title}》成功，前面还有${Math.max(0, this.queue.length - 1)}首歌曲`)
    }
    this.startNextIfIdleInBackground()
    this.schedulePreload()
    this.compactQueue()
    this.publish({ includeLyrics: false, includeIdleList: false })
    return queued
  }

  async topSong(query, userInput, superTop = false, options = {}) {
    this.ensureMemoryCapacity()
    const user = requester(userInput)
    const origin = options.origin || 'backend'
    if (this.matchesTitleText(query)) return { ignored: true, reason: 'title-filter' }
    const song = await this.resolveSong(query)
    if (this.matchesTitleFilter(song)) return { ignored: true, reason: 'title-filter' }
    this.ensureQueueRoom()
    if (this.idleNext?.uid === song.uid) this.idleNext = null
    const queued = {
      ...song,
      requestedBy: user,
      requestedAt: now(),
      requestKind: 'request',
      requestOrigin: origin,
      priority: superTop ? 'super' : 'top',
      cacheStatus: song.url ? 'ready' : 'pending',
      cachedAt: song.url ? now() : 0,
      cacheExpiresAt: song.url ? now() + 10 * 60 * 1000 : 0,
    }
    // Super-top requests always stay ahead of regular top requests. Regular
    // top requests still lead the ordinary queue, newest first.
    if (superTop) {
      this.queue.unshift(queued)
    } else {
      const firstRegularIndex = this.queue.findIndex((item) => item?.priority !== 'super')
      if (firstRegularIndex === -1) this.queue.push(queued)
      else this.queue.splice(firstRegularIndex, 0, queued)
    }
    this.notice(`@${user.name} 已置顶《${queued.title}》`)
    if (origin === 'danmaku') this.emitLiveBroadcast('top', `@${user.name} 已置顶《${queued.title}》`)
    this.startNextIfIdleInBackground()
    this.schedulePreload()
    this.compactQueue()
    this.publish({ includeLyrics: false, includeIdleList: false })
    return queued
  }

  async enqueueIdle(uid, userInput, playlistId = '') {
    const user = requester(userInput)
    const playlist = playlistId ? this.idlePlaylistById(playlistId) : null
    const song = playlist
      ? playlist.songs.find((item) => item.uid === uid)
      : this.persisted.idleList.find((item) => item.uid === uid)
    if (!song) {
      const error = new Error('空闲列表中未找到歌曲')
      error.status = 404
      throw error
    }
    if (this.matchesTitleFilter(song)) return { ignored: true, reason: 'title-filter' }
    this.ensureQueueRoom()
    if (this.config.queue.dedupeIdleOnly && this.duplicateInActive(song)) {
      const error = new Error('该歌曲正在播放或已在队列中')
      error.status = 409
      throw error
    }
    const queued = {
      ...song,
      requestedBy: user,
      requestedAt: now(),
      requestKind: 'idle',
      cacheStatus: song.url ? 'ready' : 'pending',
    }
    this.queue.push(queued)
    this.notice(`@${user.name} 已加入队列：${queued.title}`)
    this.startNextIfIdleInBackground()
    this.schedulePreload()
    this.compactQueue()
    this.publish({ includeLyrics: false, includeIdleList: false })
    return queued
  }

  async addPlaylistToQueue(playlistId, userInput, limit) {
    const user = requester(userInput)
    const songs = await this.queueCacheTask(() => importNeteasePlaylist(playlistId, this.config, limit))
    const filtered = songs.filter((song) => !this.isBlacklisted(song) && !this.matchesTitleFilter(song))
    this.ensureQueueRoom(filtered.length)
    for (const song of filtered) {
      this.queue.push({
        ...song,
        requestedBy: user,
        requestedAt: now(),
        requestKind: 'playlist',
        cacheStatus: 'pending',
      })
    }
    this.notice(`已添加歌单歌曲 ${filtered.length} 首到队列`)
    this.startNextIfIdleInBackground()
    this.schedulePreload()
    this.compactQueue()
    this.publish({ includeLyrics: false, includeIdleList: false })
    return { added: filtered.length, queueLength: this.queue.length }
  }

  async importPlaylist(playlistId, limit) {
    const [songs, meta] = await Promise.all([
      this.queueCacheTask(() => importNeteasePlaylist(playlistId, this.config, limit)),
      getNeteasePlaylistMeta(playlistId, this.config),
    ])
    const id = `netease:${meta.id}`
    const current = this.idlePlaylistById(id)
    const playlist = this.mergeIdlePlaylistSongs(current || {
      id,
      name: meta.name,
      coverUrl: meta.coverUrl,
      type: 'netease',
      sourceId: meta.id,
      enabled: true,
      songs: [],
    }, songs)
    this.upsertIdlePlaylist(playlist)
    return { imported: songs.length, total: playlist.songs.length, playlist: { ...playlist, songs: undefined } }
  }

  importLocal(directory, recursive = true, name = '') {
    const songs = importLocalDirectory(directory, this.config, recursive)
    const resolved = path.resolve(directory)
    const id = `local:${Buffer.from(resolved).toString('base64url')}`
    const current = this.idlePlaylistById(id)
    const playlist = this.mergeIdlePlaylistSongs(current || {
      id,
      name: name || path.basename(resolved) || '本地歌单',
      coverUrl: '',
      type: 'local',
      sourceId: resolved,
      enabled: true,
      songs: [],
    }, songs)
    this.upsertIdlePlaylist(playlist)
    return { imported: songs.length, total: playlist.songs.length, playlist: { ...playlist, songs: undefined } }
  }

  mergeIdlePlaylistSongs(playlist, songs) {
    const byUid = new Map((playlist.songs || []).map((song) => [song.uid, song]))
    for (const song of songs) {
      if (!this.isBlacklisted(song)) byUid.set(song.uid, compactSong(song, {
        keepLyrics: false,
        keepUrl: song?.source === 'local',
        keepFilePath: song?.source === 'local',
      }))
    }
    return {
      ...playlist,
      songs: [...byUid.values()].sort((a, b) => {
      return `${a.artist}${a.title}`.localeCompare(`${b.artist}${b.title}`, 'zh-Hans-CN')
      }),
    }
  }

  mergeIdleSongs(songs) {
    const playlist = this.idlePlaylistById('custom-default') || {
      id: 'custom-default',
      name: '自定义歌单',
      coverUrl: './image/Frame_2_19.png',
      type: 'custom',
      sourceId: '',
      enabled: true,
      songs: [],
    }
    const merged = this.mergeIdlePlaylistSongs(playlist, songs)
    this.upsertIdlePlaylist(merged)
    return { imported: songs.length, total: merged.songs.length }
  }

  addToIdle(uid) {
    const source = this.current?.uid === uid
      ? this.current
      : this.queue.find((song) => song.uid === uid) ||
        this.history.find((song) => song.uid === uid)
    if (!source) {
      const error = new Error('当前页面中未找到该歌曲')
      error.status = 404
      throw error
    }
    const result = this.mergeIdleSongs([source])
    this.notice(`《${source.title}》已加入空闲歌单`)
    return result
  }

  removeIdle(uid) {
    this.persisted.idlePlaylists = this.persisted.idlePlaylists.map((playlist) => ({
      ...playlist,
      songs: playlist.songs.filter((song) => song.uid !== uid),
    }))
    this.syncIdleList()
    if (this.idleNext?.uid === uid) this.idleNext = null
    this.save()
    this.publish()
  }

  blacklist(songOrUid) {
    const uid = typeof songOrUid === 'string' ? songOrUid : songOrUid?.uid
    if (!uid) {
      const error = new Error('Song ID is required')
      error.status = 400
      throw error
    }
    const idleSource = this.persisted.idlePlaylists
      .flatMap((playlist) => playlist.songs || [])
      .find((song) => song.uid === uid)
    const source = typeof songOrUid === 'object' && songOrUid?.uid
      ? songOrUid
      : (this.current?.uid === uid
        ? this.current
        : this.queue.find((song) => song.uid === uid) ||
          this.history.find((song) => song.uid === uid) || idleSource || this.normalizeBlacklistEntry(uid))
    if (this.isBlacklisted(source)) {
      const index = this.persisted.blacklist.findIndex((entry) => {
        return entry.uid === source.uid || `${entry.source}:${entry.sourceId}` === `${source.source}:${source.sourceId}`
      })
      const existing = this.persisted.blacklist[index]
      if (existing && typeof songOrUid === 'object') {
        const enriched = this.normalizeBlacklistEntry({ ...existing, ...source, blacklistedAt: existing.blacklistedAt })
        this.persisted.blacklist[index] = enriched
        this.syncBlacklist()
        this.save()
        this.publish({ includeLyrics: false, includeIdleList: false })
        return enriched
      }
      return existing
    }
    const entry = this.normalizeBlacklistEntry({ ...source, blacklistedAt: now() })
    this.syncBlacklist([...this.persisted.blacklist, entry])
    this.persisted.idlePlaylists = this.persisted.idlePlaylists.map((playlist) => ({
      ...playlist,
      songs: playlist.songs.filter((song) => song.uid !== entry.uid),
    }))
    this.syncIdleList()
    this.queue = this.queue.filter((song) => song.uid !== entry.uid)
    if (this.idleNext?.uid === entry.uid) this.idleNext = null
    if (this.current?.uid === entry.uid) this.next('blacklist').catch(() => {})
    this.save()
    this.notice(`《${entry.title}》已拉黑`)
    this.publish()
    return entry
  }

  async blacklistQuery(query) {
    const value = String(query || '').trim()
    if (!value) {
      const error = new Error('Please enter a song name, artist, or ID')
      error.status = 400
      throw error
    }
    const song = await this.queueCacheTask(() => resolveNeteaseMetadata(value, this.config))
    return this.blacklist(song)
  }

  removeBlacklist(index) {
    const position = Number(index)
    if (!Number.isInteger(position) || position < 0 || position >= this.persisted.blacklist.length) {
      const error = new Error('Blacklist entry not found')
      error.status = 404
      throw error
    }
    const [removed] = this.persisted.blacklist.splice(position, 1)
    this.syncBlacklist()
    this.save()
    this.publish({ includeLyrics: false, includeIdleList: false })
    return removed
  }

  clearBlacklist() {
    const removed = this.persisted.blacklist.length
    this.syncBlacklist([])
    this.save()
    this.publish({ includeLyrics: false, includeIdleList: false })
    return removed
  }

  async enrichLegacyBlacklist() {
    const targets = this.persisted.blacklist.filter((entry) => {
      return entry.source === 'netease' && /^\d+$/.test(entry.sourceId) &&
        (!entry.coverUrl || entry.title === entry.sourceId)
    }).slice(0, 50)
    let changed = false
    for (const target of targets) {
      try {
        const song = await this.queueCacheTask(() => resolveNeteaseMetadata(target.sourceId, this.config))
        const index = this.persisted.blacklist.findIndex((entry) => entry.uid === target.uid)
        if (index < 0) continue
        this.persisted.blacklist[index] = this.normalizeBlacklistEntry({
          ...target,
          ...song,
          blacklistedAt: target.blacklistedAt,
        })
        changed = true
      } catch (error) {
        console.error(`[BLACKLIST] cannot resolve ${target.sourceId}:`, error.message)
      }
    }
    if (!changed) return
    this.syncBlacklist()
    this.save()
    this.publish({ includeLyrics: false, includeIdleList: false })
  }

  setIdlePlaylistEnabled(id, enabled) {
    const playlist = this.idlePlaylistById(id)
    if (!playlist) {
      const error = new Error('歌单不存在')
      error.status = 404
      throw error
    }
    playlist.enabled = enabled !== false
    if (!playlist.enabled && this.idleNext && this.idleNext.idlePlaylistId === id) this.idleNext = null
    this.save()
    this.publish()
    return playlist
  }

  setAllIdlePlaylistsEnabled(enabled) {
    const nextEnabled = enabled !== false
    for (const playlist of this.persisted.idlePlaylists) playlist.enabled = nextEnabled
    if (!nextEnabled) this.idleNext = null
    this.save()
    this.publish()
    return { enabled: nextEnabled, playlists: this.persisted.idlePlaylists.length }
  }

  renameIdlePlaylist(id, input) {
    const playlist = this.idlePlaylistById(id)
    if (!playlist) {
      const error = new Error('歌单不存在')
      error.status = 404
      throw error
    }
    const name = String(input || '').trim().replace(/\s+/g, ' ').slice(0, 100)
    if (!name) {
      const error = new Error('歌单名称不能为空')
      error.status = 400
      throw error
    }
    playlist.name = name
    if (this.current?.idlePlaylistId === id) this.current.idlePlaylistName = name
    if (this.idleNext?.idlePlaylistId === id) this.idleNext.idlePlaylistName = name
    if (this.idleImmediate?.idlePlaylistId === id) this.idleImmediate.idlePlaylistName = name
    this.save()
    this.publish()
    return playlist
  }

  removeIdlePlaylist(id) {
    const index = this.persisted.idlePlaylists.findIndex((playlist) => playlist.id === id)
    if (index < 0) {
      const error = new Error('歌单不存在')
      error.status = 404
      throw error
    }
    const [removed] = this.persisted.idlePlaylists.splice(index, 1)
    if (this.idleNext?.idlePlaylistId === id) this.idleNext = null
    if (this.idleImmediate?.idlePlaylistId === id) this.idleImmediate = null
    if (this.persisted.idlePlaylists.length === 0) {
      this.persisted.idlePlaylists.push({
        id: 'custom-default',
        name: '自定义歌单',
        coverUrl: './image/Frame_2_19.png',
        type: 'custom',
        sourceId: '',
        enabled: true,
        songs: [],
      })
    }
    this.syncIdleList()
    const remaining = this.selectedIdleSongs().length
    this.idleCursor = remaining > 0 ? this.idleCursor % remaining : 0
    this.save()
    this.publish()
    return removed
  }

  async playIdlePlaylist(id) {
    const playlist = this.idlePlaylistById(id)
    if (!playlist) {
      const error = new Error('歌单不存在')
      error.status = 404
      throw error
    }
    if (playlist.enabled === false) {
      const error = new Error('请先启用该歌单')
      error.status = 409
      throw error
    }
    const songs = (playlist.songs || []).filter((song) => !this.isBlacklisted(song))
    if (songs.length === 0) {
      const error = new Error('歌单中没有可播放歌曲')
      error.status = 409
      throw error
    }
    const index = this.config.queue.idleMode === 'random'
      ? Math.floor(Math.random() * songs.length)
      : 0
    return this.playIdleSong(id, songs[index].uid)
  }

  promoteIdleSong(playlistId, uid) {
    const playlist = this.idlePlaylistById(playlistId)
    const index = playlist?.songs.findIndex((song) => song.uid === uid) ?? -1
    if (!playlist || index < 0) {
      const error = new Error('歌单中未找到歌曲')
      error.status = 404
      throw error
    }
    const [song] = playlist.songs.splice(index, 1)
    playlist.songs.unshift(song)
    this.syncIdleList()
    this.save()
    this.publish()
    return song
  }

  async playIdleSong(playlistId, uid) {
    const playlist = this.idlePlaylistById(playlistId)
    const song = playlist?.songs.find((item) => item.uid === uid)
    if (!playlist || !song) {
      const error = new Error('歌单中未找到歌曲')
      error.status = 404
      throw error
    }
    if (playlist.enabled === false) {
      const error = new Error('请先勾选该歌单')
      error.status = 409
      throw error
    }
    const selectedSongs = this.selectedIdleSongs()
    const selectedIndex = selectedSongs.findIndex((item) => item.idlePlaylistId === playlistId && item.uid === uid)
    if (selectedIndex >= 0) {
      this.idleCursor = this.config.queue.idleMode === 'sequence'
        ? selectedIndex + 1
        : (selectedIndex + 1) % selectedSongs.length
    }
    this.idleNext = null
    this.idleImmediate = {
      ...song,
      idlePlaylistId: playlist.id,
      idlePlaylistName: playlist.name,
      requestedBy: { id: 'idle-manual', name: '空闲歌单', roles: [] },
      requestedAt: now(),
      requestKind: 'idle-manual',
      cacheStatus: song.source === 'local' ? 'ready' : 'pending',
    }
    await this.next('selected')
    return song
  }

  clearIdlePlaylists(ids = []) {
    const selected = new Set(ids.length ? ids : this.persisted.idlePlaylists.map((playlist) => playlist.id))
    let removed = 0
    this.persisted.idlePlaylists = this.persisted.idlePlaylists.map((playlist) => {
      if (!selected.has(playlist.id)) return playlist
      removed += playlist.songs.length
      return { ...playlist, songs: [] }
    })
    this.syncIdleList()
    this.idleNext = null
    this.save()
    this.publish()
    return { removed }
  }

  importIdleConfig(input = {}) {
    if (!Array.isArray(input.playlists)) {
      const error = new Error('歌单配置格式错误')
      error.status = 400
      throw error
    }
    this.persisted.idlePlaylists = input.playlists.map((playlist, index) => ({
      id: playlist.id || `imported-${index + 1}`,
      name: playlist.name || '未命名歌单',
      coverUrl: playlist.coverUrl || '',
      type: playlist.type || 'custom',
      sourceId: playlist.sourceId || '',
      enabled: playlist.enabled !== false,
      songs: Array.isArray(playlist.songs) ? playlist.songs : [],
    }))
    if (!this.persisted.idlePlaylists.length) this.ensureIdlePlaylists()
    this.syncIdleList()
    if (['sequence', 'random', 'loop'].includes(input.options?.mode)) this.config.queue.idleMode = input.options.mode
    if (typeof input.options?.autoIdle === 'boolean') this.config.queue.autoIdle = input.options.autoIdle
    this.save()
    this.store.saveConfig()
    this.publish()
    return { playlists: this.persisted.idlePlaylists.length, songs: this.persisted.idleList.length }
  }

  promoteQueued(uid) {
    const index = this.queue.findIndex((song) => song.uid === uid)
    if (index < 0) {
      const error = new Error('队列中未找到该歌曲')
      error.status = 404
      throw error
    }
    const [song] = this.queue.splice(index, 1)
    this.queue.unshift(song)
    this.notice(`@主播 已置顶《${song.title}》`)
    this.schedulePreload()
    this.publish({ includeLyrics: false, includeIdleList: false })
    return song
  }

  removeQueued(uid) {
    const index = this.queue.findIndex((song) => song.uid === uid)
    if (index < 0) {
      const error = new Error('队列中未找到该歌曲')
      error.status = 404
      throw error
    }
    const [song] = this.queue.splice(index, 1)
    this.notice(`《${song.title}》已删除`)
    this.schedulePreload()
    this.publish({ includeLyrics: false, includeIdleList: false })
    return song
  }

  async removeSong(uid, playing = false) {
    if (playing && this.current?.uid === uid) {
      const song = this.current
      this.notice(`《${song.title}》已删除`)
      await this.next('delete')
      return song
    }
    return this.removeQueued(uid)
  }

  clearQueue() {
    const removed = this.queue.length
    this.queue = []
    this.publish({ includeLyrics: false, includeIdleList: false })
    return { removed }
  }

  async playQueued(uid) {
    const index = this.queue.findIndex((item) => item.uid === uid)
    if (index < 0) {
      const error = new Error('队列中未找到歌曲')
      error.status = 404
      throw error
    }
    const [song] = this.queue.splice(index, 1)
    this.queue.unshift(song)
    this.schedulePreload()
    this.publish({ includeLyrics: false, includeIdleList: false })
    await this.next('selected')
    return song
  }

  async startNextIfIdle() {
    if (this.current) return
    const hasIdle = this.config.queue.autoIdle !== false && this.selectedIdleSongs().length > 0
    if (this.queue.length === 0 && !this.idleNext && !hasIdle) return
    await this.next('idle')
  }

  startNextIfIdleInBackground() {
    this.startNextIfIdle().catch((error) => this.notice(`播放启动失败：${error.message}`))
    this.switchFromIdleToQueueIfNeeded()
  }

  switchFromIdleToQueueIfNeeded() {
    if (this.config.queue.interruptIdleOnRequest !== true || !isDirectIdlePlayback(this.current) || !this.queue.length) return
    this.next('request-arrived').catch((error) => this.notice(`切换点播队列失败：${error.message}`))
  }

  async next(reason = 'manual') {
    if (this.nextPromise) return this.nextPromise
    this.nextPromise = this.runNext(reason).finally(() => {
      this.nextPromise = null
      this.schedulePreload()
    })
    return this.nextPromise
  }

  announcePlayback(song, options = {}) {
    if (!song) return
    this.notice(`开始播放《${song.title}》`)
    if (song.requestOrigin === 'danmaku') {
      const requesterName = song.requestedBy?.name || '未知用户'
      this.emitLiveBroadcast('play', `开始播放《${song.title}》，点播人@${requesterName}`)
    } else if (options.origin === 'danmaku') {
      const requesterName = song.requestedBy?.name || '未知用户'
      this.emitLiveBroadcast('play', `开始播放《${song.title}》，点播人@${requesterName}`)
    }
  }

  async runNext(reason) {
    if (this.current) {
      this.history.push({
        ...compactSong(this.current, { keepLyrics: false, keepUrl: false, keepFilePath: false }),
        endedAt: now(),
        endReason: reason,
      })
      this.compactHistory()
    }

    let idleAttempts = 0
    const maxIdleAttempts = Math.min(3, this.selectedIdleSongs().length)
    while (this.idleImmediate || this.queue.length > 0 || idleAttempts < maxIdleAttempts) {
      let nextSong = null
      if (this.idleImmediate) {
        nextSong = this.idleImmediate
        this.idleImmediate = null
      } else if (this.queue.length > 0) {
        nextSong = this.queue.shift()
      } else {
        const idleSong = this.idleNext || this.createIdleCandidate()
        this.idleNext = null
        if (!idleSong) break
        nextSong = idleSong
        idleAttempts += 1
      }
      this.current = nextSong
      this.playback = {
        ...this.playback,
        status: 'loading',
        position: 0,
        duration: nextSong.duration || 0,
        message: '',
        updatedAt: now(),
      }
      this.publish()

      try {
        this.current = await this.ensurePrepared(nextSong)
        if (!this.current.url) throw new Error('无法获取播放地址')
        if (this.player) await this.player.load(this.current)
        console.log(`[LYRIC] playing=${this.current.sourceId || this.current.uid} mode=${this.current.lyricMode || 'none'} words=${this.current.wordLyrics?.length || 0}`)
        this.playback.status = 'playing'
        this.playback.duration = this.current.duration || this.playback.duration
        this.playback.position = 0
        this.playback.updatedAt = now()
        this.announcePlayback(this.current)
        // The playback notice intentionally omits lyrics; send the prepared
        // current song once more so the lyric panel cannot lose its payload.
        this.publish({ includeIdleList: false })
        return this.current
      } catch (error) {
        this.history.push({
          ...compactSong(nextSong, { keepLyrics: false, keepUrl: false, keepFilePath: false }),
          failedAt: now(),
          error: error.message,
        })
        this.compactHistory()
        this.notice(`跳过无法播放：${nextSong.title}（${error.message}）`)
      }
    }

    this.current = null
    this.playback = {
      ...this.playback,
      status: 'idle',
      position: 0,
      duration: 0,
      message: '暂无歌曲',
      updatedAt: now(),
    }
    if (this.player) await this.player.stop().catch(() => {})
    this.compactRuntime()
    this.publish()
    return null
  }

  async previous() {
    if (!isDirectIdlePlayback(this.current)) return null
    const songs = this.selectedIdleSongs()
    if (songs.length < 2) return null
    let index = songs.findIndex((song) => {
      return song.uid === this.current.uid && song.idlePlaylistId === this.current.idlePlaylistId
    })
    if (index < 0) index = songs.findIndex((song) => song.uid === this.current.uid)
    if (index < 0) return null
    const targetIndex = (index - 1 + songs.length) % songs.length
    const song = songs[targetIndex]
    this.idleCursor = (targetIndex + 1) % songs.length
    this.idleNext = null
    this.idleImmediate = {
      ...song,
      requestedBy: { id: 'idle-previous', name: '\u7a7a\u95f2\u6b4c\u5355', roles: [] },
      requestedAt: now(),
      requestKind: 'idle-manual',
      cacheStatus: song.source === 'local' ? 'ready' : 'pending',
    }
    return this.next('previous')
  }

  async skip(userInput = null, options = {}) {
    const user = requester(userInput)
    const message = options.origin === 'danmaku' ? `@${user.name} 切歌成功` : '已切换到下一首歌曲'
    this.notice(message)
    if (options.origin === 'danmaku') this.emitLiveBroadcast('skip', message)
    return this.next('skip')
  }

  setPlaybackPatch(patch) {
    this.playback = { ...this.playback, ...patch, updatedAt: now() }
    this.publish()
  }

  async play(userInput = null, options = {}) {
    if (!this.current) await this.startNextIfIdle()
    if (this.current && this.player) await this.player.play()
    if (this.current) {
      const wasPlaying = this.playback.status === 'playing'
      this.setPlaybackPatch({ status: 'playing' })
      if (!wasPlaying) {
        this.notice(`开始播放《${this.current.title}》`)
        if (options.origin === 'danmaku') {
          this.emitLiveBroadcast('play', `开始播放《${this.current.title}》，点播人@${this.current.requestedBy?.name || '未知用户'}`)
        }
      }
    }
  }

  async pause() {
    if (this.player) await this.player.pause()
    this.setPlaybackPatch({ status: 'paused' })
  }

  async seek(seconds) {
    if (this.player) await this.player.seek(seconds)
    this.setPlaybackPatch({ position: Number(seconds || 0) })
  }

  async setVolume(volume) {
    const numeric = Number(volume)
    this.config.player.volume = numeric
    this.store.saveConfig()
    if (this.player) await this.player.setVolume(numeric)
    this.setPlaybackPatch({ volume: numeric })
  }

  async updateSettings(patch = {}) {
    const queue = patch.queue || {}
    const permissions = patch.permissions || {}
    const points = patch.points || {}
    const normalization = patch.audioNormalization || {}
    const commands = patch.commands || {}
    const controls = patch.controls || {}
    const clamp = (value, min, max, fallback) => {
      const number = Number(value)
      return Number.isFinite(number) ? Math.min(max, Math.max(min, number)) : fallback
    }
    const booleanKeys = [
      'requestEnabled', 'freeRequest', 'requestAdminOnly', 'requestAdminFree',
      'requestFanOnly', 'requestFanFree', 'requestMemberOnly', 'requestMemberFree',
      'requestGuardianOnly', 'requestGuardianFree', 'balanceQueryEnabled',
      'intelligentRequest', 'smartDjFilter', 'freeSkip', 'freeTop', 'freeSuperTop',
      'adminFreeSkip', 'adminFreeTop', 'adminFreeSuperTop',
    ]
    booleanKeys.forEach((key) => {
      if (typeof permissions[key] === 'boolean') this.config.permissions[key] = permissions[key]
    })
    const requestRoleKeys = ['requestFanOnly', 'requestAdminOnly', 'requestMemberOnly', 'requestGuardianOnly']
    if (permissions.freeRequest === true) {
      requestRoleKeys.forEach((key) => { this.config.permissions[key] = false })
    } else if (requestRoleKeys.some((key) => permissions[key] === true)) {
      this.config.permissions.freeRequest = false
    }
    const queueRanges = {
      maxLength: [1, 200],
      userCooldownSeconds: [0, 3600],
      maxSongSeconds: [0, 3600],
    }
    Object.entries(queueRanges).forEach(([key, [min, max]]) => {
      if (queue[key] !== undefined) this.config.queue[key] = clamp(queue[key], min, max, this.config.queue[key])
    })
    if (typeof queue.interruptIdleOnRequest === 'boolean') this.config.queue.interruptIdleOnRequest = queue.interruptIdleOnRequest
    ;['request', 'skip', 'top', 'superTop'].forEach((key) => {
      const field = `${key}Cost`
      if (points[field] !== undefined) this.config.points[field] = clamp(points[field], 0, 999999, this.config.points[field])
    })
    if (typeof normalization.enabled === 'boolean') this.config.audioNormalization.enabled = normalization.enabled
    if (normalization.targetLufs !== undefined) this.config.audioNormalization.targetLufs = clamp(normalization.targetLufs, -30, -5, -14)
    if (normalization.maxGainDb !== undefined) this.config.audioNormalization.maxGainDb = clamp(normalization.maxGainDb, 0, 24, 6)
    if (normalization.minGainDb !== undefined) this.config.audioNormalization.minGainDb = clamp(normalization.minGainDb, -24, 0, -12)
    if (this.config.audioNormalization.minGainDb > this.config.audioNormalization.maxGainDb) {
      this.config.audioNormalization.minGainDb = this.config.audioNormalization.maxGainDb
    }
    ;['request', 'skip', 'top', 'superTop', 'balance'].forEach((key) => {
      if (commands[key] === undefined) return
      const value = String(commands[key] || '').trim().slice(0, 32)
      if (value) this.config.commands[key] = value
    })
    ;['keyboardEnabled', 'externalCommandEnabled', 'deviceControlEnabled'].forEach((key) => {
      if (typeof controls[key] === 'boolean') this.config.controls[key] = controls[key]
    })
    ;[
      'startStopHotkey', 'playPauseHotkey', 'previousHotkey', 'nextHotkey',
      'volumeUpHotkey', 'volumeDownHotkey', 'blacklistHotkey', 'skipHotkey',
    ].forEach((key) => {
      if (controls[key] === undefined) return
      const value = String(controls[key] || '').trim().slice(0, 40)
      this.config.controls[key] = value
    })
    this.store.saveConfig()
    if (this.player && typeof this.player.setAudioNormalization === 'function') {
      await this.player.setAudioNormalization(this.config.audioNormalization.enabled)
    }
    this.publish()
    return this.snapshot().config
  }

  async setDevice(device) {
    this.config.player.audioDevice = device || 'auto'
    this.store.saveConfig()
    if (this.player) await this.player.setDevice(this.config.player.audioDevice)
    this.publish()
  }

  async handleCommand(payload) {
    const text = String(payload.text || '').trim()
    if (!text) return null
    const user = requester(payload)
    this.touchUser(user)
    let action = ''
    let subject = ''
    const commands = { ...DEFAULT_COMMANDS, ...(this.config.commands || {}) }
    const allowAttachedArgument = this.config.permissions?.intelligentRequest === true
    try {
      if (commandMatches(text, commands.balance, true)) {
        if (this.config.permissions?.balanceQueryEnabled === false) return { type: 'ignored' }
        const points = Number(this.persisted.users[user.id]?.points || 0)
        const message = `@${user.name} \u5f53\u524d\u79ef\u5206\uff1a${points}`
        this.notice(message)
        this.emitLiveBroadcast('balance', message, { userId: user.id, points })
        return { type: 'balance', points }
      }
      if (commandMatches(text, commands.skip, true)) {
        action = 'skip'
        this.commandAccess(user, action)
        const result = await this.skip(payload, { origin: 'danmaku' })
        this.chargeCommand(user, action)
        return { type: 'skip', result }
      }
      if (commandMatches(text, commands.superTop, false, allowAttachedArgument)) {
        action = 'superTop'
        subject = commandArg(text, commands.superTop)
        if (this.matchesTitleText(subject)) return { type: 'ignored' }
        this.commandAccess(user, action)
        const result = await this.topSong(subject, payload, true, { origin: 'danmaku' })
        if (result?.ignored) return { type: 'ignored' }
        this.chargeCommand(user, action)
        return result
      }
      if (commandMatches(text, commands.top, false, allowAttachedArgument)) {
        action = 'top'
        subject = commandArg(text, commands.top)
        if (this.matchesTitleText(subject)) return { type: 'ignored' }
        this.commandAccess(user, action)
        const result = await this.topSong(subject, payload, false, { origin: 'danmaku' })
        if (result?.ignored) return { type: 'ignored' }
        this.chargeCommand(user, action)
        return result
      }
      if (commandMatches(text, commands.request, false, allowAttachedArgument)) {
        action = 'request'
        subject = commandArg(text, commands.request)
        if (this.matchesTitleText(subject)) return { type: 'ignored' }
        this.commandAccess(user, action)
        const result = await this.requestSong(subject, payload, { origin: 'danmaku' })
        if (result?.ignored) return { type: 'ignored' }
        this.chargeCommand(user, action)
        return result
      }
      if (false && text === TEXT.balance) {
        const points = this.persisted.users[user.id]?.points || 0
        this.notice(`@${user.name} 当前积分：${points}`)
        return { type: 'balance', points }
      }
      if (false && (text === TEXT.skip || text === TEXT.next)) {
        action = 'skip'
        this.commandAccess(user, action)
        const result = await this.skip(payload, { origin: 'danmaku' })
        this.chargeCommand(user, action)
        return { type: 'skip', result }
      }
      if (text === TEXT.pause) {
        await this.pause()
        return { type: 'pause' }
      }
      if (text === TEXT.play) {
        await this.play(payload, { origin: 'danmaku' })
        return { type: 'play' }
      }
      if (false && text.startsWith(TEXT.superTop)) {
        action = 'superTop'
        subject = commandArg(text, TEXT.superTop)
        if (this.matchesTitleText(subject)) return { type: 'ignored' }
        this.commandAccess(user, action)
        const result = await this.topSong(subject, payload, true, { origin: 'danmaku' })
        if (result?.ignored) return { type: 'ignored' }
        this.chargeCommand(user, action)
        return result
      }
      if (false && text.startsWith(TEXT.top)) {
        action = 'top'
        subject = commandArg(text, TEXT.top)
        if (this.matchesTitleText(subject)) return { type: 'ignored' }
        this.commandAccess(user, action)
        const result = await this.topSong(subject, payload, false, { origin: 'danmaku' })
        if (result?.ignored) return { type: 'ignored' }
        this.chargeCommand(user, action)
        return result
      }
      if (text.startsWith(TEXT.playlist)) {
        return this.addPlaylistToQueue(commandArg(text, TEXT.playlist), payload)
      }
      if (false && text.startsWith(TEXT.request)) {
        action = 'request'
        subject = commandArg(text, TEXT.request)
        if (this.matchesTitleText(subject)) return { type: 'ignored' }
        this.commandAccess(user, action)
        const result = await this.requestSong(subject, payload, { origin: 'danmaku' })
        if (result?.ignored) return { type: 'ignored' }
        this.chargeCommand(user, action)
        return result
      }
      return { type: 'ignored' }
    } catch (error) {
      if (action) this.broadcastFailure(action, user, subject, error)
      throw error
    }
  }
}

module.exports = { BotCore, publicSong }
