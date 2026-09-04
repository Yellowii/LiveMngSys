(function () {
  'use strict'

  const $ = (id) => document.getElementById(id)
  const root = $('2_17')
  if (!root) return

  root.classList.add('musicbot-root')

  function installSpectrumTexture() {
    const header = $('2_18')
    if (!header || header.querySelector('.musicbot-nebula-layer')) return null
    const layers = Array.from(header.children)
    layers[0]?.classList.add('musicbot-top-background-layer')
    layers[1]?.classList.add('musicbot-top-border-layer')
    layers[2]?.classList.add('musicbot-top-content-layer')

    const layer = document.createElement('div')
    layer.className = 'musicbot-nebula-layer'
    layer.setAttribute('aria-hidden', 'true')
    header.insertBefore(layer, layers[1] || null)

    const fallbackPalette = [
      [79, 142, 247],
      [117, 96, 255],
      [42, 213, 194],
      [255, 112, 192],
      [255, 187, 76],
    ]
    let palette = fallbackPalette
    let coverKey = ''
    let playing = false
    let settleTimer = 0
    let driftTimer = 0

    const clamp = (value) => Math.max(0, Math.min(255, Math.round(value)))
    const enhance = (color) => {
      const average = color.reduce((sum, value) => sum + value, 0) / 3
      return color.map((value) => clamp(average + (value - average) * 1.35 + 8))
    }
    const applyPalette = () => {
      palette.forEach((color, index) => {
        layer.style.setProperty(`--nebula-${index + 1}`, color.join(', '))
      })
    }
    const stopNebulaDrift = () => {
      if (!driftTimer) return
      clearTimeout(driftTimer)
      driftTimer = 0
    }
    const randomizeNebula = () => {
      if (!playing || document.hidden) return
      const duration = 2800 + Math.random() * 3200
      layer.style.setProperty('--nebula-drift-duration', `${Math.round(duration)}ms`)
      layer.style.setProperty('--nebula-x', `${-3 + Math.random() * 6}%`)
      layer.style.setProperty('--nebula-y', `${-7 + Math.random() * 12}px`)
      layer.style.setProperty('--nebula-scale', `${1.03 + Math.random() * 0.08}`)
      layer.style.backgroundPosition = Array.from({ length: 4 }, () => `${-12 + Math.random() * 116}% ${-8 + Math.random() * 24}%`).join(', ')
      layer.style.backgroundSize = Array.from({ length: 4 }, () => `${118 + Math.random() * 72}% ${138 + Math.random() * 84}%`).join(', ')
      driftTimer = setTimeout(randomizeNebula, duration * (0.72 + Math.random() * 0.22))
    }
    const startNebulaDrift = () => {
      if (driftTimer) return
      randomizeNebula()
    }
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) stopNebulaDrift()
      else if (playing) startNebulaDrift()
    })

    const colorFromHash = (value) => {
      let hash = 0
      for (let index = 0; index < value.length; index += 1) hash = ((hash << 5) - hash + value.charCodeAt(index)) | 0
      const hue = Math.abs(hash) % 360
      const hslToRgb = (h, saturation, lightness) => {
        const s = saturation / 100
        const l = lightness / 100
        const chroma = (1 - Math.abs(2 * l - 1)) * s
        const x = chroma * (1 - Math.abs((h / 60) % 2 - 1))
        const match = l - chroma / 2
        const rgb = h < 60 ? [chroma, x, 0] : h < 120 ? [x, chroma, 0] : h < 180 ? [0, chroma, x] : h < 240 ? [0, x, chroma] : h < 300 ? [x, 0, chroma] : [chroma, 0, x]
        return rgb.map((channel) => clamp((channel + match) * 255))
      }
      return [0, 38, 82, 178, 250].map((offset, index) => enhance(hslToRgb((hue + offset) % 360, 78 - index * 4, 56 + index * 3)))
    }

    const averageColor = (sum, count, fallback) => count
      ? enhance(sum.map((value) => value / count))
      : fallback.slice()

    const sampleCover = (image) => {
      try {
        const sampler = document.createElement('canvas')
        sampler.width = 24
        sampler.height = 24
        const samplerContext = sampler.getContext('2d', { willReadFrequently: true })
        samplerContext.drawImage(image, 0, 0, 24, 24)
        const data = samplerContext.getImageData(0, 0, 24, 24).data
        const sums = Array.from({ length: 5 }, () => [0, 0, 0])
        const counts = [0, 0, 0, 0, 0]
        for (let index = 0; index < data.length; index += 4) {
          const brightness = (data[index] + data[index + 1] + data[index + 2]) / 3
          if (data[index + 3] < 100 || brightness < 18) continue
          const pixel = index / 4
          const x = pixel % 24
          const y = Math.floor(pixel / 24)
          const bucket = x < 8 ? 1 : x > 15 ? 2 : y < 12 ? 3 : 4
          for (const targetIndex of [0, bucket]) {
            sums[targetIndex][0] += data[index]
            sums[targetIndex][1] += data[index + 1]
            sums[targetIndex][2] += data[index + 2]
            counts[targetIndex] += 1
          }
        }
        const extracted = sums.map((sum, index) => averageColor(sum, counts[index], fallbackPalette[index]))
        const accents = colorFromHash(coverKey || image.src)
        palette = [extracted[0], extracted[1], accents[2], accents[3], accents[4]]
        applyPalette()
      } catch (error) {
        // Cross-origin album art may block pixel sampling; keep the stable fallback palette.
      }
    }

    const setCover = (url) => {
      const nextKey = String(url || '')
      if (nextKey === coverKey) return
      coverKey = nextKey
      palette = nextKey ? colorFromHash(nextKey) : fallbackPalette
      applyPalette()
      if (!nextKey) return
      const image = new Image()
      image.crossOrigin = 'anonymous'
      image.onload = () => {
        if (coverKey === nextKey) sampleCover(image)
      }
      image.src = nextKey
    }

    const setPlaying = (value) => {
      const nextPlaying = value === true
      if (nextPlaying === playing) return
      clearTimeout(settleTimer)
      if (nextPlaying) {
        playing = true
        startNebulaDrift()
        layer.classList.remove('musicbot-nebula-settling')
        layer.classList.add('musicbot-nebula-playing')
      } else {
        playing = false
        stopNebulaDrift()
        layer.classList.remove('musicbot-nebula-playing')
        layer.classList.add('musicbot-nebula-settling')
        settleTimer = setTimeout(() => {
          layer.classList.remove('musicbot-nebula-settling')
        }, 950)
      }
    }

    applyPalette()
    return { setCover, setPlaying }
  }

  let state = null
  let serverClockOffsetMs = 0
  let stateRevision = -1
  let stateBootId = ''
  let spectrumTexture = null
  let activeView = 'queue'
  let searchText = ''
  let seeking = false
  let logs = []
  let lastCurrentUid = ''
  let lastOverlayKey = ''
  let volumeDragging = false
  let lastPlayerRenderAt = 0
  let lyricDom = { songUid: '', mode: '', lineIndex: -2, tokenEls: [] }
  let lyricRecovery = { songUid: '', attempts: 0, timer: null }
  let idleRenderKey = ''
  let filterRenderKey = ''
  let blacklistRenderKey = ''
  let settingsRenderKey = ''
  let pointsRenderKey = ''
  let settingsSection = 'request'
  let pointsUsers = []
  let liveBadgeUsers = new Map()
  let editingUserId = ''
  let loginQrTimer = null
  let idleStateVersion = 0
  const idleExpanded = new Set()
  const selectedUserIds = new Set()
  const settingValues = {
    cookie: '',
    qrimg: '',
    qrKey: '',
    qrMessage: '',
    dataSections: new Set(['idle', 'filters', 'blacklist', 'points']),
  }

  const queueViews = {
    queue: $('2_73'),
    idle: $('2_83'),
    history: $('2_88'),
    filter: $('2_341'),
    blacklist: $('2_345'),
    settings: $('2_350'),
    points: $('2_357'),
  }

  spectrumTexture = installSpectrumTexture()

  const tableRoot = $('2_102')
  const tableFooter = $('2_660')
  const staticRows = ['2_384', '2_439', '2_494', '2_549', '2_604', '2_659']
  const workspaceRoot = $('2_71')?.firstElementChild
  const tabsRoot = $('2_72')
  const logPane = $('2_205')

  if (workspaceRoot && tabsRoot && tableRoot && logPane) {
    const workspace = document.createElement('div')
    const contentPane = document.createElement('section')
    workspace.className = 'musicbot-workspace'
    contentPane.className = 'musicbot-content-pane'
    logPane.classList.add('musicbot-log-pane')
    contentPane.append(tabsRoot, tableRoot)
    workspace.append(contentPane, logPane)
    workspaceRoot.replaceChildren(workspace)
  }

  const tableBody = document.createElement('div')
  tableBody.className = 'musicbot-table-body'
  tableRoot?.classList.add('musicbot-table')
  staticRows.forEach((id) => { if ($(id)) $(id).style.display = 'none' })
  if (tableFooter?.parentElement) tableFooter.parentElement.insertBefore(tableBody, tableFooter)
  $('2_370')?.classList.add('musicbot-column-hidden')

  const logClear = $('2_263')
  const logHeader = $('2_210')?.parentElement
  if (logClear && logHeader) {
    logHeader.appendChild(logClear)
    logClear.classList.add('musicbot-log-clear')
  }

  const logRoot = $('2_213')
  if (logRoot) {
    logRoot.innerHTML = '<div id="musicbot-log-list" class="musicbot-log-list"></div><div id="musicbot-system" class="musicbot-system"></div>'
  }

  const toast = document.createElement('div')
  toast.className = 'musicbot-toast'
  toast.hidden = true
  document.body.appendChild(toast)
  let toastTimer = null

  function text(value) {
    return String(value ?? '')
  }

  function escapeHtml(value) {
    return text(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
  }

  function formatTime(seconds) {
    const value = Math.max(0, Number(seconds || 0))
    return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(Math.floor(value % 60)).padStart(2, '0')}`
  }

  function formatShortDate(timestamp) {
    const date = new Date(Number(timestamp || 0))
    if (!timestamp || Number.isNaN(date.getTime())) return '--'
    const year = String(date.getFullYear()).slice(-2)
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  }

  function matchesSearch(...values) {
    const keyword = searchText.toLocaleLowerCase()
    if (!keyword) return true
    return values.some((value) => text(value).toLocaleLowerCase().includes(keyword))
  }

  function showToast(message, error = false) {
    toast.textContent = message
    toast.classList.toggle('error', error)
    toast.hidden = false
    clearTimeout(toastTimer)
    toastTimer = setTimeout(() => { toast.hidden = true }, 4200)
  }

  async function post(url, body = {}) {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const result = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(result.error || response.statusText)
    return result
  }

  async function remove(url) {
    const response = await fetch(url, { method: 'DELETE' })
    const result = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(result.error || response.statusText)
    return result
  }

  async function getJson(url) {
    const response = await fetch(url)
    const result = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(result.error || response.statusText)
    return result
  }

  function userIdentityKeys(user) {
    if (!user || typeof user !== 'object') return []
    return ['id', 'userId', 'douyinId', 'displayId', 'name', 'nickname']
      .map((key) => text(user[key]).trim().toLocaleLowerCase())
      .filter(Boolean)
  }

  function mergeBadges(base, incoming) {
    const merged = new Map()
    for (const badge of [...(Array.isArray(base) ? base : []), ...(Array.isArray(incoming) ? incoming : [])]) {
      if (!badge || (!badge.label && !badge.icon && !badge.url)) continue
      const key = `${badge.type || 'badge'}:${badge.label || badge.icon || badge.url}`
      const previous = merged.get(key) || {}
      merged.set(key, {
        type: text(badge.type || previous.type || 'badge'),
        kind: text(badge.kind || previous.kind || badge.type || 'badge'),
        label: text(badge.label || previous.label || '徽章'),
        icon: text(badge.icon || badge.url || previous.icon || previous.url || ''),
        bgColor: text(badge.bgColor || previous.bgColor || ''),
        fgColor: text(badge.fgColor || previous.fgColor || ''),
      })
    }
    return [...merged.values()].slice(0, 8)
  }

  function requesterWithLiveBadges(requester) {
    const user = requester && typeof requester === 'object' ? requester : {}
    const live = userIdentityKeys(user)
      .map((key) => liveBadgeUsers.get(key))
      .find(Boolean)
    return {
      ...user,
      fansClub: user.fansClub || (live && live.fansClub) || {},
      badges: mergeBadges(user.badges, live?.badges),
    }
  }

  function requesterBadgeMarkup(requester) {
    const user = requesterWithLiveBadges(requester)
    const name = text(user.name || user.nickname).trim()
    if (!name || name === '空闲歌单') return ''
    const sourceBadges = user.badges || []
    const hasStarGuard = sourceBadges.some(isStarGuardBadge)
    const badges = sourceBadges.filter((badge) => badge && badge.icon && !(hasStarGuard && isFansBadge(badge)))
    return `<div class="musicbot-requester"><span class="musicbot-requester-name">点歌人 ${escapeHtml(name)}</span>${badges.length ? `<span class="musicbot-requester-badges">${badges.map((badge) => requesterBadgeImageMarkup(badge, user)).join('')}</span>` : ''}</div>`
  }

  function isFansBadge(badge) {
    return badge?.type === 'fans' || badge?.kind === 'fans_club'
  }

  function isStarGuardBadge(badge) {
    const value = [badge?.type, badge?.kind, badge?.label, badge?.icon, badge?.uri].join(' ').toLowerCase()
    if (value.includes('star_guard')) return true
    if (value.includes('ranklist_fansclub_advanced_badge_') && value.includes('_xmp')) return true
    return value.includes('guard') || value.includes('星守护')
  }

  function starGuardText(badge, user) {
    const club = user?.fansClub || {}
    const name = text(club.name || club.clubName).trim()
    const level = Number(badge?.level || club.level || 0)
    if (name) return name
    const label = text(badge?.label).replace(/^星守护\s*/, '').replace(/^lv/i, '').trim()
    if (label === '徽章') return `${level || '守护'}`
    return label || `${level || '守护'}`
  }

  function requesterBadgeImageMarkup(badge, user) {
    if (isStarGuardBadge(badge)) {
      const ranklistClass = String(badge?.icon || '').toLowerCase().includes('ranklist_fansclub_advanced_badge_')
        ? ' musicbot-star-guard-badge-ranklist'
        : ''
      return `<span class="musicbot-requester-badge musicbot-star-guard-badge${ranklistClass}" title="${escapeHtml(badge.label)}" style="border-image-source:url('${escapeHtml(badge.icon)}')"><span>${escapeHtml(starGuardText(badge, user))}</span></span>`
    }
    return `<span class="musicbot-requester-badge" title="${escapeHtml(badge.label)}"><img src="${escapeHtml(badge.icon)}" alt="${escapeHtml(badge.label)}"></span>`
  }

  async function refreshLiveBadges() {
    try {
      const result = await getJson('/api/livemngsys/live/state')
      const sources = [result.audience, result.gifts, result.memberships, result.interactions]
      const next = new Map()
      for (const collection of sources) {
        if (!Array.isArray(collection)) continue
        for (const entry of collection) {
          const user = entry?.user && typeof entry.user === 'object' ? entry.user : entry
          if (!user || !Array.isArray(user.badges) || !user.badges.length) continue
          const badges = mergeBadges(next.get(userIdentityKeys(user)[0])?.badges, user.badges)
          for (const key of userIdentityKeys(user)) {
            const previous = next.get(key)
            next.set(key, { ...user, badges: mergeBadges(previous?.badges, badges) })
          }
        }
      }
      liveBadgeUsers = next
      if (activeView === 'queue' || activeView === 'history') renderRows()
    } catch (error) {
      // Direct MusicBot access may not be behind the LiveMngSys gateway.
    }
  }

  function addLog(message, type = 'info') {
    if (!message) return
    logs.push({ message: text(message), type, time: new Date() })
    if (logs.length > 24) logs.splice(0, logs.length - 24)
    renderLogs()
  }

  function renderLogs() {
    const list = $('musicbot-log-list')
    const count = $('2_212')
    if (!list) return
    const followLatest = list.scrollHeight - list.scrollTop - list.clientHeight <= 36
    if (count) count.textContent = `${logs.length} 条`
    list.innerHTML = logs.length
      ? logs.map((item) => `
        <div class="musicbot-log-item ${escapeHtml(item.type)}">
          <span class="musicbot-log-dot"></span>
          <div>
            <div class="musicbot-log-message">${escapeHtml(item.message)}</div>
            <div class="musicbot-log-time">${item.time.toLocaleTimeString()}</div>
          </div>
        </div>
      `).join('')
      : '<div class="musicbot-empty">暂无实时日志</div>'
    if (followLatest) requestAnimationFrame(() => { list.scrollTop = list.scrollHeight })
  }

  function renderSystem() {
    const element = $('musicbot-system')
    if (!element || !state?.system) return
    const system = state.system
    const player = state.player || {}
    const login = state.config?.music?.login
    element.innerHTML = [
      ['RSS', `${system.rssMb} MB`],
      ['队列', system.queueLength],
      ['缓存下一首', system.idleNext || '未准备'],
      ['输出设备', player.device || 'auto'],
      ['账号', login ? `${login.nickname || login.userId} · VIP ${login.vipType || 0}` : '未登录'],
    ].map(([key, value]) => `<div><span>${escapeHtml(key)}</span><strong>${escapeHtml(value)}</strong></div>`).join('')
  }

  function currentPosition() {
    if (!state?.playback) return 0
    const base = Number(state.playback.position || 0)
    if (state.playback.status !== 'playing') return base
    const updatedAt = Number(state.playback.updatedAt || 0)
    return base + (updatedAt ? Math.max(0, Date.now() + serverClockOffsetMs - updatedAt) / 1000 : 0)
  }

  function acceptStateSync(next) {
    const sync = next?.sync
    if (!sync || typeof sync !== 'object') return true
    const incomingBootId = String(sync.bootId || '')
    const incomingRevision = Number(sync.revision)
    if (incomingBootId && incomingBootId === stateBootId && Number.isFinite(incomingRevision) && incomingRevision < stateRevision) return false
    if (incomingBootId && incomingBootId !== stateBootId) {
      stateBootId = incomingBootId
      stateRevision = -1
    }
    if (Number.isFinite(incomingRevision)) stateRevision = Math.max(stateRevision, incomingRevision)
    const serverTime = Number(sync.serverTime)
    if (Number.isFinite(serverTime) && serverTime > 0) serverClockOffsetMs = serverTime - Date.now()
    return true
  }

  function parseLrc(value) {
    return text(value).split(/\r?\n/).map((line) => {
      const match = line.match(/\[(\d+):(\d+(?:\.\d+)?)\](.*)/)
      return match ? { time: Number(match[1]) * 60 + Number(match[2]), text: match[3].trim() } : null
    }).filter((line) => line && line.text)
  }

  function resetLyricDom(songUid = '') {
    lyricDom = { songUid, mode: '', lineIndex: -2, tokenEls: [] }
  }

  function hasLyrics(song) {
    return Boolean(
      (Array.isArray(song?.wordLyrics) && song.wordLyrics.length) ||
      (typeof song?.lyric === 'string' && song.lyric.trim()),
    )
  }

  function recoverLyricsIfNeeded() {
    const song = state?.current
    const songUid = song?.uid || ''
    if (lyricRecovery.songUid !== songUid) {
      if (lyricRecovery.timer) clearTimeout(lyricRecovery.timer)
      lyricRecovery = { songUid, attempts: 0, timer: null }
    }
    if (!songUid || hasLyrics(song) || state?.playback?.status === 'loading') {
      if (lyricRecovery.timer) clearTimeout(lyricRecovery.timer)
      lyricRecovery.timer = null
      return
    }
    if (lyricRecovery.timer || lyricRecovery.attempts >= 2) return
    const expectedUid = songUid
    const delay = 500 + lyricRecovery.attempts * 750
    lyricRecovery.timer = setTimeout(() => {
      lyricRecovery.timer = null
      lyricRecovery.attempts += 1
      getJson('/api/state')
        .then((next) => {
          if (state?.current?.uid === expectedUid) applyState(next)
        })
        .catch(() => {})
    }, delay)
  }

  function renderLyrics(position) {
    const song = state?.current
    const currentEl = $('2_31')
    const nextEl = $('2_32')
    if (!currentEl || !nextEl) return
    const songUid = song?.uid || ''
    if (lyricDom.songUid !== songUid) resetLyricDom(songUid)

    if (!song) {
      if (lyricDom.mode !== 'empty') {
        currentEl.classList.remove('musicbot-word-line')
        currentEl.classList.add('musicbot-lyric-current')
        currentEl.textContent = '等待点歌'
        currentEl.style.setProperty('--lyric-fill', '0%')
        nextEl.textContent = ''
        lyricDom.mode = 'empty'
      }
      return
    }

    const wordLines = Array.isArray(song.wordLyrics) ? song.wordLyrics : []
    if (wordLines.length) {
      let active = -1
      for (let i = 0; i < wordLines.length; i += 1) {
        if (wordLines[i].time <= position) active = i
        else break
      }
      const lineIndex = active >= 0 ? active : 0
      const line = wordLines[lineIndex]
      const lineWords = Array.isArray(line?.words) && line.words.length
        ? line.words
        : [{ text: line?.text || '', start: line?.time || 0, duration: line?.duration || 0 }]
      if (lyricDom.mode !== 'word' || lyricDom.lineIndex !== lineIndex) {
        currentEl.classList.remove('musicbot-lyric-current')
        currentEl.classList.add('musicbot-word-line')
        currentEl.style.removeProperty('--lyric-fill')
        currentEl.innerHTML = lineWords.map((word) => {
          const value = escapeHtml(word.text)
          return `<span class="musicbot-word-token" data-text="${value}" style="--word-fill:0%">${value}</span>`
        }).join('')
        nextEl.textContent = wordLines[lineIndex + 1]?.text || ''
        lyricDom.mode = 'word'
        lyricDom.lineIndex = lineIndex
        lyricDom.tokenEls = Array.from(currentEl.querySelectorAll('.musicbot-word-token'))
      }
      lineWords.forEach((word, index) => {
        const start = Number(word.start || 0)
        const duration = Number(word.duration || 0)
        const fill = position >= start + duration
          ? 100
          : (position > start && duration > 0 ? Math.min(100, Math.max(0, (position - start) / duration * 100)) : 0)
        lyricDom.tokenEls[index]?.style.setProperty('--word-fill', `${fill}%`)
      })
      return
    }

    const lines = parseLrc(song.lyric)
    if (!lines.length) {
      const recovering = lyricRecovery.songUid === songUid && lyricRecovery.attempts < 2
      const emptyMode = recovering ? 'recovering' : 'empty'
      if (lyricDom.mode !== emptyMode) {
        currentEl.classList.remove('musicbot-word-line')
        currentEl.classList.add('musicbot-lyric-current')
        currentEl.textContent = recovering ? '歌词加载中' : '暂无歌词'
        currentEl.style.setProperty('--lyric-fill', '0%')
        nextEl.textContent = ''
        lyricDom.mode = emptyMode
      }
      return
    }

    let index = 0
    for (let i = 0; i < lines.length; i += 1) {
      if (lines[i].time <= position) index = i
      else break
    }
    const line = lines[index]
    const next = lines[index + 1]
    const duration = next ? Math.max(0.1, next.time - line.time) : 0
    const fill = duration ? Math.min(100, Math.max(0, (position - line.time) / duration * 100)) : 100
    if (lyricDom.mode !== 'line' || lyricDom.lineIndex !== index) {
      currentEl.classList.remove('musicbot-word-line')
      currentEl.classList.add('musicbot-lyric-current')
      currentEl.textContent = line.text
      nextEl.textContent = next?.text || ''
      lyricDom.mode = 'line'
      lyricDom.lineIndex = index
      lyricDom.tokenEls = []
    }
    currentEl.style.setProperty('--lyric-fill', `${fill}%`)
  }

  function renderPlayer() {
    const song = state?.current
    const current = $('2_21')
    const artist = $('2_22')
    const source = $('2_28')
    const cover = $('2_19')
    current?.classList.add('musicbot-top-title')
    artist?.classList.add('musicbot-top-artist')
    source?.classList.add('musicbot-top-source')
    $('2_23')?.classList.add('musicbot-source-badge')
    $('2_31')?.classList.add('musicbot-top-lyric')
    $('2_32')?.classList.add('musicbot-top-lyric-next')
    $('2_30')?.classList.add('musicbot-lyric-panel')
    $('2_46')?.classList.add('musicbot-progress-row')
    $('2_39')?.classList.add('musicbot-play-control')
    $('2_40')?.classList.add('musicbot-play-icon')
    const playing = state?.playback?.status === 'playing'
    $('2_39')?.classList.toggle('musicbot-playing', playing)
    $('2_39')?.classList.toggle('musicbot-paused', !playing)
    spectrumTexture?.setPlaying(playing)
    spectrumTexture?.setCover(song?.coverUrl || '')
    if (!song) {
      if (current) current.textContent = '暂无播放'
      if (artist) artist.textContent = '等待点歌或空闲歌单'
      if (source) source.textContent = '待机'
      if (cover) cover.style.backgroundImage = "url('./image/Frame_2_19.png')"
    } else {
      if (current) current.textContent = song.title || '未知歌曲'
      if (artist) artist.textContent = `${song.artist || '未知歌手'}${song.album ? ` · ${song.album}` : ''}`
      if (source) source.textContent = song.source === 'local' ? 'local' : (song.playbackSource || 'netease')
      if (cover) cover.style.backgroundImage = song.coverUrl ? `url("${song.coverUrl.replace(/"/g, '%22')}")` : "url('./image/Frame_2_19.png')"
    }
    const position = currentPosition()
    const duration = Number(state?.playback?.duration || song?.duration || 0)
    const percent = duration ? Math.min(100, Math.max(0, position / duration * 100)) : 0
    if ($('2_47')) $('2_47').textContent = formatTime(position)
    if ($('2_51')) $('2_51').textContent = formatTime(duration)
    if ($('2_49')) $('2_49').style.width = `${percent}%`
    if ($('2_50')) $('2_50').style.left = `calc(${percent}% - 5px)`
    if ($('musicbot-seek')) $('musicbot-seek').value = String(Math.round(percent * 10))
    renderLyrics(position)
    const volume = Number(state?.playback?.volume ?? state?.player?.volume ?? 0)
    if ($('2_59')) $('2_59').style.width = `${Math.max(0, Math.min(100, volume))}%`
    if ($('2_340')) $('2_340').textContent = `${Math.round(volume)}%`
    if ($('musicbot-volume') && !volumeDragging) $('musicbot-volume').value = String(volume)
  }

  function iconButton(action, icon, label) {
    return `<button class="musicbot-icon-button" data-row-action="${action}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}" style="background-image:url('./image/${icon}.svg')"></button>`
  }

  function cacheStatusView(song) {
    if (song.isPlaying) return { className: 'playing', label: '播放中' }
    const status = song.cacheStatus || (song.source === 'local' ? 'ready' : 'pending')
    const labels = {
      pending: '等待中',
      loading: '下载中',
      ready: '已缓存',
      failed: '下载失败',
    }
    return { className: labels[status] ? status : 'pending', label: labels[status] || '等待中' }
  }

  function visibleSongs() {
    let songs = []
    if (activeView === 'queue') songs = state?.queue || []
    if (activeView === 'idle') songs = state?.idleList || []
    if (activeView === 'history') songs = state?.history || []
    if (activeView === 'blacklist') songs = state?.blacklist || []
    if (activeView === 'filter') songs = [...(state?.queue || []), ...(state?.idleList || [])]
    if (searchText) {
      const keyword = searchText.toLowerCase()
      songs = songs.filter((song) => `${song.title} ${song.artist} ${song.album}`.toLowerCase().includes(keyword))
    }
    return songs
  }

  function idlePlaylists() {
    return Array.isArray(state?.idlePlaylists) ? state.idlePlaylists : [{
      id: 'custom-default',
      name: '自定义歌单',
      coverUrl: './image/Frame_2_19.png',
      type: 'custom',
      enabled: true,
      songs: state?.idleList || [],
    }]
  }

  function idleSourceLabel(playlist) {
    if (playlist.type === 'netease') return '网易云歌单'
    if (playlist.type === 'local') return '本地歌单'
    return '自定义歌单'
  }

  function idleSongActions(playlistId, song) {
    const encodedPlaylist = encodeURIComponent(playlistId)
    const encodedUid = encodeURIComponent(song.uid)
    return iconButton('idle-play', 'play3', '播放')
      .replace('data-row-action="idle-play"', `data-idle-song-action="play" data-playlist-id="${encodedPlaylist}" data-song-uid="${encodedUid}"`)
      + iconButton('idle-request', 'listplus3', '点歌')
        .replace('data-row-action="idle-request"', `data-idle-song-action="request" data-playlist-id="${encodedPlaylist}" data-song-uid="${encodedUid}"`)
      + iconButton('idle-promote', 'arrowuptoline3', '歌单内置顶')
        .replace('data-row-action="idle-promote"', `data-idle-song-action="promote" data-playlist-id="${encodedPlaylist}" data-song-uid="${encodedUid}"`)
      + iconButton('idle-blacklist', 'ban3', '加入黑名单')
        .replace('data-row-action="idle-blacklist"', `data-idle-song-action="blacklist" data-playlist-id="${encodedPlaylist}" data-song-uid="${encodedUid}"`)
      + iconButton('idle-remove-song', 'trash24', '删除歌曲')
        .replace('data-row-action="idle-remove-song"', `data-idle-song-action="remove" data-playlist-id="${encodedPlaylist}" data-song-uid="${encodedUid}"`)
  }

  function idlePlaylistActions(playlist) {
    const encodedPlaylist = encodeURIComponent(playlist.id)
    return iconButton('idle-playlist-play', 'play3', '播放歌单')
      .replace('data-row-action="idle-playlist-play"', `data-idle-playlist-action="play" data-playlist-id="${encodedPlaylist}"`)
      + iconButton('idle-playlist-rename', 'pencil', '重命名歌单')
        .replace('data-row-action="idle-playlist-rename"', `data-idle-playlist-action="rename" data-playlist-id="${encodedPlaylist}"`)
      + iconButton('idle-playlist-remove', 'trash24', '删除歌单')
        .replace('data-row-action="idle-playlist-remove"', `data-idle-playlist-action="remove" data-playlist-id="${encodedPlaylist}"`)
  }

  function idleModeView(mode) {
    const views = {
      sequence: {
        label: '顺序播放',
        next: 'random',
        icon: '<g transform="translate(1.5 0)"><path d="M4 7h13M14 4l3 3-3 3M4 17h13M14 14l3 3-3 3"/></g>',
      },
      random: {
        label: '随机播放',
        next: 'loop',
        icon: '<path d="M16 3h5v5M4 20L21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/>',
      },
      loop: {
        label: '列表循环',
        next: 'sequence',
        icon: '<path d="M17 2l4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 0 1-3 3H3"/>',
      },
    }
    return views[mode] || views.sequence
  }

  function idleViewKey() {
    return `${idleStateVersion}:${[...idleExpanded].sort().join('\u0000')}`
  }

  function renderIdleView() {
    const playlists = idlePlaylists()
    const enabledCount = playlists.filter((playlist) => playlist.enabled !== false).length
    const mode = state?.config?.queue?.idleMode || 'sequence'
    const modeView = idleModeView(mode)
    const autoIdle = state?.config?.queue?.autoIdle !== false
    const interruptIdleOnRequest = state?.config?.queue?.interruptIdleOnRequest === true
    const allEnabled = playlists.length > 0 && enabledCount === playlists.length
    const selectAllLabel = allEnabled ? '取消全选歌单' : '全选歌单'
    return `
      <div class="musicbot-idle-view">
        <div class="musicbot-idle-columns">
          <span>歌曲</span><span>时长</span><span>下载状态</span><span>来源</span><span>歌词格式</span><span>加入时间</span>
          <button class="musicbot-select-all ${allEnabled ? 'active' : ''} ${enabledCount > 0 && !allEnabled ? 'partial' : ''}" data-idle-action="toggle-all" data-enable="${allEnabled ? 'false' : 'true'}" title="${selectAllLabel}" aria-label="${selectAllLabel}"><i></i></button>
        </div>
        <div class="musicbot-playlist-tree">
          ${playlists.map((playlist) => {
            const expanded = idleExpanded.has(playlist.id)
            const checked = playlist.enabled !== false
            return `
              <section class="musicbot-playlist-group ${expanded ? 'expanded' : ''}" data-playlist-id="${escapeHtml(playlist.id)}">
                <div class="musicbot-playlist-row">
                  <span class="musicbot-playlist-cover" style="background-image:url('${escapeHtml(playlist.coverUrl || './image/Frame_2_19.png')}')"></span>
                  <div class="musicbot-playlist-copy" data-idle-action="expand" title="${expanded ? '收起歌单' : '展开歌单'}"><strong>${escapeHtml(playlist.name)}</strong><span>${escapeHtml(idleSourceLabel(playlist))} · ${playlist.songs?.length || 0} 首</span></div>
                  <div class="musicbot-playlist-actions">${idlePlaylistActions(playlist)}</div>
                  <label class="musicbot-playlist-switch" title="启用或停用歌单">
                    <input type="checkbox" data-idle-toggle="${escapeHtml(playlist.id)}" ${checked ? 'checked' : ''} aria-label="启用${escapeHtml(playlist.name)}">
                    <i></i>
                  </label>
                </div>
                <div class="musicbot-playlist-songs" ${expanded ? '' : 'hidden'}>
                  ${(playlist.songs || []).map((song, index) => {
                    const status = cacheStatusView(song)
                    const lyricMode = song.lyricMode === 'word' ? '\u9010\u5b57' : (song.lyricMode === 'line' ? 'LRC' : '--')
                    return `
                      <div class="musicbot-idle-song-row${song.isPlaying ? ' musicbot-idle-song-row-playing' : ''}" data-idle-song="${escapeHtml(song.uid)}" data-playlist-id="${escapeHtml(playlist.id)}" data-playing="${song.isPlaying ? 'true' : 'false'}">
                        <div class="musicbot-idle-song-cell"><span class="musicbot-index">${index + 1}</span><span class="musicbot-cover" style="background-image:url('${escapeHtml(song.coverUrl || './image/Frame_2_387.png')}')"></span><div class="musicbot-song-copy"><div class="musicbot-song-title">${escapeHtml(song.title || song.uid)}</div><div class="musicbot-song-artist">${escapeHtml(song.artist || '')}</div></div></div>
                        <span>${song.duration ? formatTime(song.duration) : '--:--'}</span>
                        <span class="musicbot-status ${status.className}"><i class="musicbot-log-dot"></i>${status.label}</span>
                        <span><b class="musicbot-badge">${escapeHtml(song.source === 'local' ? '本地' : (song.playbackSource || '网易云'))}</b></span>
                        <span><b class="musicbot-badge">${escapeHtml(lyricMode)}</b></span>
                        <span>${escapeHtml(song.requestedAt ? new Date(song.requestedAt).toLocaleTimeString() : '--:--:--')}</span>
                        <div class="musicbot-actions">${idleSongActions(playlist.id, song)}</div>
                      </div>
                    `
                  }).join('') || '<div class="musicbot-empty musicbot-playlist-empty">歌单为空</div>'}
                </div>
              </section>
            `
          }).join('') || '<div class="musicbot-empty">暂无歌单</div>'}
        </div>
        <div class="musicbot-idle-controls">
          <div class="musicbot-idle-control-row musicbot-idle-source-row">
            <div class="musicbot-source-group musicbot-online-source">
              <input id="musicbot-idle-playlist-input" class="musicbot-control-input musicbot-link-input" placeholder="网易云歌单链接或 ID">
              <button class="primary" data-idle-action="import-playlist">添加在线歌单</button>
            </div>
            <div class="musicbot-source-group musicbot-local-source">
              <button class="musicbot-folder-button" data-idle-action="select-folder" title="选择本地文件夹" aria-label="选择本地文件夹">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6.5A2.5 2.5 0 0 1 5.5 4H9l2 2h7.5A2.5 2.5 0 0 1 21 8.5v8A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5z"/></svg>
              </button>
              <input id="musicbot-idle-local-input" class="musicbot-control-input musicbot-local-path" placeholder="本地文件夹路径">
              <input id="musicbot-idle-local-name" class="musicbot-control-input musicbot-name-input" placeholder="歌单名称（可选）">
              <button class="primary" data-idle-action="import-local">添加本地歌单</button>
            </div>
          </div>
          <div class="musicbot-idle-control-row musicbot-idle-control-secondary">
            <div class="musicbot-idle-player-controls">
              <button class="musicbot-mode-button" data-idle-mode="${modeView.next}" title="${modeView.label}，点击切换" aria-label="当前${modeView.label}，点击切换播放模式">
                <svg viewBox="0 0 24 24" aria-hidden="true">${modeView.icon}</svg>
              </button>
            </div>
            <span class="musicbot-idle-summary">已启用 ${enabledCount}/${playlists.length} 个歌单</span>
            <span class="musicbot-idle-control-spacer"></span>
            <button data-idle-action="locate-playing">定位到播放</button>
            <label class="musicbot-auto-toggle" title="点播列表为空时继续播放空闲歌单">
              <span>空闲时播放</span><input id="musicbot-idle-auto" type="checkbox" ${autoIdle ? 'checked' : ''}><i></i>
            </label>
            <label class="musicbot-auto-toggle" title="点播列表有歌时立即切换">
              <span>点播有歌立即切换</span><input id="musicbot-idle-interrupt" type="checkbox" ${interruptIdleOnRequest ? 'checked' : ''}><i></i>
            </label>
            <button class="danger" data-idle-action="clear">清空歌单</button>
          </div>
        </div>
      </div>
    `
  }

  function rowActions(song) {
    if (activeView === 'queue') {
      return iconButton('play', 'play3', '立即播放') +
        iconButton('promote', 'arrowuptoline3', '置顶') +
        iconButton('idle-save', 'listplus3', '加入空闲歌单') +
        iconButton('blacklist', 'ban3', '加入黑名单') +
        iconButton('remove', 'trash24', '移除')
    }
    if (activeView === 'idle') {
      return iconButton('idle-add', 'listplus3', '加入队列') +
        iconButton('blacklist', 'ban3', '加入黑名单') +
        iconButton('idle-remove', 'trash24', '删除歌曲')
    }
    if (activeView === 'history') return iconButton('replay', 'play3', '重新点播')
    return ''
  }

  function renderBlacklistView() {
    const entries = (Array.isArray(state?.blacklist) ? state.blacklist : [])
      .map((entry, index) => ({ entry, index }))
      .filter(({ entry }) => matchesSearch(entry.title, entry.artist, entry.sourceId, entry.source, entry.playbackSource))
    return `
      <div class="musicbot-blacklist-view">
        <div class="musicbot-blacklist-columns">
          <span>\u6b4c\u66f2</span><span>\u65f6\u957f</span><span>\u6765\u6e90</span><span>\u62c9\u9ed1\u65f6\u95f4</span>
        </div>
        <div class="musicbot-blacklist-list">
          ${entries.map(({ entry, index }) => `
            <div class="musicbot-blacklist-row">
              <div class="musicbot-blacklist-song">
                <span class="musicbot-blacklist-index">${index + 1}</span>
                <span class="musicbot-blacklist-cover" style="background-image:url('${escapeHtml(entry.coverUrl || './image/Frame_2_387.png')}')"></span>
                <div class="musicbot-song-copy"><div class="musicbot-song-title">${escapeHtml(entry.title || entry.sourceId || entry.uid)}</div><div class="musicbot-song-artist">${escapeHtml(entry.artist || '')}</div></div>
              </div>
              <span>${entry.duration ? formatTime(entry.duration) : '--:--'}</span>
              <span><b class="musicbot-badge">${escapeHtml(entry.playbackSource || entry.source || '--')}</b></span>
              <span>${formatShortDate(entry.blacklistedAt)}</span>
              <button class="musicbot-blacklist-delete" data-blacklist-action="remove" data-blacklist-index="${index}" title="\u89e3\u9664\u62c9\u9ed1" aria-label="\u89e3\u9664\u62c9\u9ed1 ${escapeHtml(entry.title || entry.uid)}" style="background-image:url('./image/trash24.svg')"></button>
            </div>
          `).join('') || '<div class="musicbot-empty">\u6682\u65e0\u62c9\u9ed1\u6b4c\u66f2</div>'}
        </div>
        <div class="musicbot-blacklist-controls">
          <input id="musicbot-blacklist-input" class="musicbot-control-input" placeholder="\u8f93\u5165\u6b4c\u540d\u3001\u6b4c\u624b\u6216\u7f51\u6613\u4e91\u6b4c\u66f2 ID">
          <button class="primary" data-blacklist-action="add">\u6dfb\u52a0</button>
          <button class="danger" data-blacklist-action="clear">\u6e05\u7a7a</button>
        </div>
      </div>
    `
  }

  function renderFilterView() {
    const keywords = (Array.isArray(state?.titleFilters) ? state.titleFilters : [])
      .map((keyword, index) => ({ keyword, index }))
      .filter(({ keyword }) => matchesSearch(keyword))
    return `
      <div class="musicbot-filter-view">
        <div class="musicbot-filter-list">
          ${keywords.map(({ keyword, index }) => `
            <div class="musicbot-filter-row">
              <span class="musicbot-filter-index">${index + 1}</span>
              <span class="musicbot-filter-keyword">${escapeHtml(keyword)}</span>
              <button class="musicbot-filter-delete" data-filter-action="remove" data-filter-index="${index}" title="\u5220\u9664" aria-label="\u5220\u9664 ${escapeHtml(keyword)}" style="background-image:url('./image/trash24.svg')"></button>
            </div>
          `).join('') || '<div class="musicbot-empty">\u6682\u65e0\u8fc7\u6ee4\u5173\u952e\u8bcd</div>'}
        </div>
        <div class="musicbot-filter-controls">
          <input id="musicbot-filter-input" class="musicbot-control-input" maxlength="100" placeholder="\u8f93\u5165\u9700\u8981\u8fc7\u6ee4\u7684\u6b4c\u540d\u5173\u952e\u8bcd">
          <button class="primary" data-filter-action="add">\u6dfb\u52a0</button>
          <button class="danger" data-filter-action="clear">\u6e05\u7a7a</button>
        </div>
      </div>
    `
  }

  function applyPointsUsers(users) {
    pointsUsers = Array.isArray(users) ? users : []
    const available = new Set(pointsUsers.map((user) => String(user.id)))
    for (const id of selectedUserIds) {
      if (!available.has(id)) selectedUserIds.delete(id)
    }
    if (editingUserId && !available.has(editingUserId)) editingUserId = ''
    pointsRenderKey = ''
    if (activeView === 'points') renderRows()
  }

  async function refreshPointsUsers() {
    try {
      const result = await getJson('/api/users')
      applyPointsUsers(result.users)
    } catch (error) {
      showToast(error.message, true)
    }
  }

  function renderPointsView() {
    const visibleUsers = pointsUsers.filter((user) => matchesSearch(user.remark, user.points, user.nickname, user.douyinId, user.id))
    return `
      <div class="musicbot-points-view">
        <div class="musicbot-points-columns">
          <span></span><span>&#x5934;&#x50cf;</span><span>&#x5907;&#x6ce8;</span><span>&#x79ef;&#x5206;</span><span>&#x6635;&#x79f0;</span><span>&#x6296;&#x97f3;&#x53f7;</span><span></span>
        </div>
        <div class="musicbot-points-list">
          ${visibleUsers.map((user) => {
            const id = String(user.id || '')
            const encodedId = encodeURIComponent(id)
            const editing = editingUserId === id
            const avatar = user.avatar || './image/user3.svg'
            return `
              <div class="musicbot-points-row${editing ? ' editing' : ''}" data-user-id="${escapeHtml(encodedId)}">
                <input class="musicbot-points-select" type="checkbox" data-user-select="${escapeHtml(encodedId)}"${selectedUserIds.has(id) ? ' checked' : ''} aria-label="&#x9009;&#x62e9; ${escapeHtml(user.nickname || id)}">
                <img class="musicbot-user-avatar" src="${escapeHtml(avatar)}" alt="" onerror="this.src='./image/user3.svg'">
                ${editing ? `<input class="musicbot-points-input" data-user-field="remark" value="${escapeHtml(user.remark || '')}" maxlength="100">` : `<span class="musicbot-points-text">${escapeHtml(user.remark || '--')}</span>`}
                ${editing ? `<input class="musicbot-points-input musicbot-points-number" data-user-field="points" type="number" min="0" max="999999999" value="${escapeHtml(user.points || 0)}">` : `<strong class="musicbot-points-value">${escapeHtml(user.points || 0)}</strong>`}
                ${editing ? `<input class="musicbot-points-input" data-user-field="nickname" value="${escapeHtml(user.nickname || '')}" maxlength="100">` : `<span class="musicbot-points-text">${escapeHtml(user.nickname || '--')}</span>`}
                ${editing ? `<input class="musicbot-points-input" data-user-field="douyinId" value="${escapeHtml(user.douyinId || '')}" maxlength="100">` : `<span class="musicbot-points-text">${escapeHtml(user.douyinId || id)}</span>`}
                <div class="musicbot-points-actions">
                  ${editing
                    ? `<button class="primary" data-points-action="save">&#x4fdd;&#x5b58;</button><button data-points-action="cancel">&#x53d6;&#x6d88;</button>`
                    : `<button data-points-action="edit">&#x7f16;&#x8f91;</button><button class="danger" data-points-action="remove">&#x5220;&#x9664;</button>`}
                </div>
              </div>
            `
          }).join('') || '<div class="musicbot-empty">&#x6682;&#x65e0;&#x7528;&#x6237;&#x79ef;&#x5206;&#x8bb0;&#x5f55;</div>'}
        </div>
        <div class="musicbot-points-controls">
          <span>&#x5df2;&#x9009; ${selectedUserIds.size} &#x9879;</span>
          <button class="danger" data-points-action="remove-selected"${selectedUserIds.size ? '' : ' disabled'}>&#x5220;&#x9664;&#x9009;&#x4e2d;</button>
          <button class="danger" data-points-action="clear"${pointsUsers.length ? '' : ' disabled'}>&#x6e05;&#x7a7a;&#x5217;&#x8868;</button>
        </div>
      </div>
    `
  }

  function dataSectionCheckbox(key, label) {
    const checked = settingValues.dataSections.has(key)
    return `<label class="musicbot-setting-check"><input type="checkbox" data-config-section="${key}"${checked ? ' checked' : ''}><span class="musicbot-setting-checkmark"></span><span>${label}</span></label>`
  }

  function settingCheckbox(path, label, checked, options = {}) {
    const type = options.switch ? ' musicbot-setting-switch' : ''
    const disabled = options.disabled === true
    return `<label class="musicbot-setting-check${type}${disabled ? ' disabled' : ''}"><input type="checkbox" data-settings-field="${path}"${checked ? ' checked' : ''}${disabled ? ' disabled' : ''}><span class="musicbot-setting-checkmark"></span><span>${label}</span></label>`
  }

  function settingRadio(path, label, checked, value) {
    return `<label class="musicbot-setting-check musicbot-setting-radio"><input type="radio" name="request-policy" data-settings-field="${path}" data-settings-value="${value}"${checked ? ' checked' : ''}><span class="musicbot-setting-checkmark"></span><span>${label}</span></label>`
  }

  function settingNumber(path, label, value, min, max, suffix = '', options = {}) {
    const disabled = options.disabled === true
    return `<label class="musicbot-setting-number${disabled ? ' disabled' : ''}"><span>${label}</span><input type="number" data-settings-field="${path}" value="${escapeHtml(value)}" min="${min}" max="${max}" step="1"${disabled ? ' disabled' : ''}><span>${suffix}</span></label>`
  }

  function settingHotkey(path, label, value, fallback) {
    const displayValue = value === undefined ? fallback : value
    return `<div class="musicbot-setting-hotkey"><span>${label}</span><input data-settings-field="${path}" value="${escapeHtml(displayValue)}"><button type="button" data-hotkey-clear="${path}">清空</button></div>`
  }

  function renderSettingsView() {
    const config = state?.config || {}
    const queue = config.queue || {}
    const permissions = config.permissions || {}
    const points = config.points || {}
    const commands = config.commands || {}
    const controls = config.controls || {}
    const normalization = config.audioNormalization || { enabled: false, targetLufs: -14 }
    const login = config.music?.login
    const nav = [
      ['request', '&#x70b9;&#x6b4c;'],
      ['skipTop', '&#x5207;&#x6b4c;&#x002f;&#x9876;&#x6b4c;'],
      ['controls', '&#x63a7;&#x5236;'],
      ['other', '&#x5176;&#x4ed6;'],
    ]
    let content = ''
    if (settingsSection === 'request') {
      content = `
        <section class="musicbot-setting-section">
          <div class="musicbot-setting-group-title">&#x70b9;&#x6b4c;&#x6a21;&#x5f0f;</div>
          <div class="musicbot-setting-grid">
            ${settingCheckbox('permissions.requestEnabled', '&#x5141;&#x8bb8;&#x5f39;&#x5e55;&#x70b9;&#x6b4c;', permissions.requestEnabled !== false, { switch: true })}
            ${settingRadio('permissions.freeRequest', '&#x514d;&#x8d39;&#x70b9;&#x6b4c;', permissions.freeRequest !== false, 'true')}
            ${settingRadio('permissions.freeRequest', '&#x79ef;&#x5206;&#x70b9;&#x6b4c;', permissions.freeRequest === false, 'false')}
          </div>
          <div class="musicbot-setting-subtitle">&#x8eab;&#x4efd;&#x9650;&#x5236;&#xff08;&#x53ef;&#x591a;&#x9009;&#xff09;</div>
          <div class="musicbot-setting-role-list">
            <div class="musicbot-setting-role-row">
              ${settingCheckbox('permissions.requestFanOnly', '&#x4ec5;&#x5141;&#x8bb8;&#x7c89;&#x4e1d;&#x56e2;&#x70b9;&#x6b4c;', Boolean(permissions.requestFanOnly), { disabled: permissions.freeRequest !== false })}
              <div class="musicbot-setting-role-child">${settingCheckbox('permissions.requestFanFree', '&#x7c89;&#x4e1d;&#x56e2;&#x514d;&#x8d39;&#x70b9;&#x6b4c;', Boolean(permissions.requestFanFree) && Boolean(permissions.requestFanOnly), { disabled: permissions.freeRequest !== false || !permissions.requestFanOnly })}</div>
            </div>
            <div class="musicbot-setting-role-row">
              ${settingCheckbox('permissions.requestAdminOnly', '&#x4ec5;&#x5141;&#x8bb8;&#x7ba1;&#x7406;&#x5458;&#x70b9;&#x6b4c;', Boolean(permissions.requestAdminOnly), { disabled: permissions.freeRequest !== false })}
              <div class="musicbot-setting-role-child">${settingCheckbox('permissions.requestAdminFree', '&#x7ba1;&#x7406;&#x5458;&#x514d;&#x8d39;&#x70b9;&#x6b4c;', Boolean(permissions.requestAdminFree) && Boolean(permissions.requestAdminOnly), { disabled: permissions.freeRequest !== false || !permissions.requestAdminOnly })}</div>
            </div>
            <div class="musicbot-setting-role-row">
              ${settingCheckbox('permissions.requestMemberOnly', '&#x4ec5;&#x5141;&#x8bb8;&#x4f1a;&#x5458;&#x70b9;&#x6b4c;', Boolean(permissions.requestMemberOnly), { disabled: permissions.freeRequest !== false })}
              <div class="musicbot-setting-role-child">${settingCheckbox('permissions.requestMemberFree', '&#x4f1a;&#x5458;&#x514d;&#x8d39;&#x70b9;&#x6b4c;', Boolean(permissions.requestMemberFree) && Boolean(permissions.requestMemberOnly), { disabled: permissions.freeRequest !== false || !permissions.requestMemberOnly })}</div>
            </div>
            <div class="musicbot-setting-role-row">
              ${settingCheckbox('permissions.requestGuardianOnly', '&#x4ec5;&#x5141;&#x8bb8;&#x661f;&#x5b88;&#x62a4;&#x70b9;&#x6b4c;', Boolean(permissions.requestGuardianOnly), { disabled: permissions.freeRequest !== false })}
              <div class="musicbot-setting-role-child">${settingCheckbox('permissions.requestGuardianFree', '&#x661f;&#x5b88;&#x62a4;&#x514d;&#x8d39;&#x70b9;&#x6b4c;', Boolean(permissions.requestGuardianFree) && Boolean(permissions.requestGuardianOnly), { disabled: permissions.freeRequest !== false || !permissions.requestGuardianOnly })}</div>
            </div>
          </div>
          <div class="musicbot-setting-grid">
            ${settingNumber('points.requestCost', '&#x79ef;&#x5206;&#x70b9;&#x6b4c;', points.requestCost || 0, 0, 999999, '&#x5206;&#x002f;&#x9996;', { disabled: permissions.freeRequest !== false })}
          </div>
          <div class="musicbot-setting-subtitle">&#x5f53;&#x201c;&#x514d;&#x8d39;&#x70b9;&#x6b4c;&#x201d;&#x5173;&#x95ed;&#x4e14;&#x672a;&#x52fe;&#x9009;&#x4efb;&#x4f55;&#x8eab;&#x4efd;&#x9650;&#x5236;&#x65f6;&#xff0c;&#x6240;&#x6709;&#x7528;&#x6237;&#x6309;&#x79ef;&#x5206;&#x70b9;&#x6b4c;&#x3002;</div>
          <div class="musicbot-setting-inline"><span>&#x70b9;&#x6b4c;&#x547d;&#x4ee4;</span><input data-settings-field="commands.request" value="${escapeHtml(commands.request || '\u70b9\u6b4c')}"></div>
          <div class="musicbot-setting-grid">
            ${settingCheckbox('permissions.intelligentRequest', '&#x667a;&#x80fd;&#x70b9;&#x6b4c;', permissions.intelligentRequest !== false)}
            ${settingCheckbox('permissions.smartDjFilter', '&#x667a;&#x80fd;&#x8fc7;&#x6ee4;DJ&#x7248;', Boolean(permissions.smartDjFilter))}
          </div>
        </section>
        <section class="musicbot-setting-section">
          <div class="musicbot-setting-group-title">&#x70b9;&#x6b4c;&#x51b7;&#x5374;</div>
          <div class="musicbot-setting-grid">
            ${settingNumber('queue.userCooldownSeconds', '&#x540c;&#x4e00;&#x7528;&#x6237;', queue.userCooldownSeconds ?? 60, 0, 3600, '&#x79d2;&#x5185;&#x4e0d;&#x5141;&#x8bb8;&#x8fde;&#x7eed;&#x70b9;&#x6b4c;')}
            ${settingNumber('queue.maxSongSeconds', '&#x5355;&#x9996;&#x6700;&#x957f;&#x64ad;&#x653e;', queue.maxSongSeconds ?? 300, 0, 3600, '&#x79d2;')}
            ${settingNumber('queue.maxLength', '&#x70b9;&#x6b4c;&#x961f;&#x5217;&#x4e0a;&#x9650;', queue.maxLength ?? 50, 1, 200, '&#x9996;')}
          </div>
        </section>
      `
    } else if (settingsSection === 'skipTop') {
      content = `
        <section class="musicbot-setting-section">
          <div class="musicbot-setting-group-title">&#x5207;&#x6b4c;&#x6743;&#x9650;</div>
          <div class="musicbot-setting-grid">
            ${settingCheckbox('permissions.freeSkip', '&#x514d;&#x8d39;&#x5207;&#x6b4c;&#xff08;&#x6240;&#x6709;&#x4eba;&#xff09;', permissions.freeSkip !== false)}
            ${settingCheckbox('permissions.adminFreeSkip', '&#x7ba1;&#x7406;&#x514d;&#x8d39;&#x5207;&#x6b4c;', permissions.adminFreeSkip !== false)}
            ${settingNumber('points.skipCost', '&#x79ef;&#x5206;&#x5207;&#x6b4c;', points.skipCost || 0, 0, 999999, '&#x5206;&#x002f;&#x6b21;')}
          </div>
          <div class="musicbot-setting-inline"><span>&#x5207;&#x6b4c;&#x547d;&#x4ee4;</span><input data-settings-field="commands.skip" value="${escapeHtml(commands.skip || '\u5207\u6b4c')}"></div>
        </section>
        <section class="musicbot-setting-section">
          <div class="musicbot-setting-group-title">&#x9876;&#x6b4c;&#x6743;&#x9650;</div>
          <div class="musicbot-setting-grid">
            ${settingCheckbox('permissions.freeTop', '&#x514d;&#x8d39;&#x9876;&#x6b4c;&#xff08;&#x6240;&#x6709;&#x4eba;&#xff09;', permissions.freeTop !== false)}
            ${settingCheckbox('permissions.adminFreeTop', '&#x7ba1;&#x7406;&#x514d;&#x8d39;&#x9876;&#x6b4c;', permissions.adminFreeTop !== false)}
            ${settingNumber('points.topCost', '&#x79ef;&#x5206;&#x9876;&#x6b4c;', points.topCost || 0, 0, 999999, '&#x5206;&#x002f;&#x6b21;')}
          </div>
          <div class="musicbot-setting-inline"><span>&#x9876;&#x6b4c;&#x547d;&#x4ee4;</span><input data-settings-field="commands.top" value="${escapeHtml(commands.top || '\u9876\u6b4c')}"></div>
        </section>
        <section class="musicbot-setting-section">
          <div class="musicbot-setting-group-title">&#x8d85;&#x7ea7;&#x7f6e;&#x9876;&#x6743;&#x9650;</div>
          <div class="musicbot-setting-grid">
            ${settingCheckbox('permissions.freeSuperTop', '&#x514d;&#x8d39;&#x8d85;&#x7ea7;&#x7f6e;&#x9876;&#xff08;&#x6240;&#x6709;&#x4eba;&#xff09;', permissions.freeSuperTop !== false)}
            ${settingCheckbox('permissions.adminFreeSuperTop', '&#x7ba1;&#x7406;&#x514d;&#x8d39;&#x8d85;&#x7ea7;&#x7f6e;&#x9876;', permissions.adminFreeSuperTop !== false)}
            ${settingNumber('points.superTopCost', '&#x79ef;&#x5206;&#x8d85;&#x7ea7;&#x7f6e;&#x9876;', points.superTopCost || 0, 0, 999999, '&#x5206;&#x002f;&#x6b21;')}
          </div>
          <div class="musicbot-setting-inline"><span>&#x8d85;&#x7ea7;&#x7f6e;&#x9876;&#x547d;&#x4ee4;</span><input data-settings-field="commands.superTop" value="${escapeHtml(commands.superTop || '\u8d85\u7ea7\u7f6e\u9876')}"></div>
        </section>
      `
    } else if (settingsSection === 'controls') {
      content = `
        <section class="musicbot-setting-section">
          <div class="musicbot-setting-group-title">&#x540e;&#x53f0;&#x63a7;&#x5236;</div>
          <div class="musicbot-setting-grid">
            ${settingCheckbox('controls.keyboardEnabled', '&#x542f;&#x7528;&#x9875;&#x9762;&#x5feb;&#x6377;&#x952e;', controls.keyboardEnabled !== false, { switch: true })}
            ${settingCheckbox('controls.externalCommandEnabled', '&#x5141;&#x8bb8;&#x5916;&#x90e8;&#x6307;&#x4ee4;', controls.externalCommandEnabled === true, { switch: true })}
            ${settingCheckbox('controls.deviceControlEnabled', '&#x5141;&#x8bb8;&#x5916;&#x8bbe;&#x63a7;&#x5236;', controls.deviceControlEnabled === true, { switch: true })}
          </div>
        </section>
        <section class="musicbot-setting-section">
          <div class="musicbot-setting-group-title">&#x5feb;&#x6377;&#x952e;</div>
          ${settingHotkey('controls.startStopHotkey', '&#x542f;&#x52a8;&#x002f;&#x5173;&#x95ed;', controls.startStopHotkey, 'Ctrl+Alt+F1')}
          <div class="musicbot-setting-group-label">&#x64ad;&#x653e;&#x5668;&#x5feb;&#x6377;&#x952e;</div>
          ${settingHotkey('controls.playPauseHotkey', '&#x64ad;&#x653e;&#x002f;&#x6682;&#x505c;', controls.playPauseHotkey, 'Ctrl+Alt+P')}
          ${settingHotkey('controls.previousHotkey', '&#x524d;&#x4e00;&#x9996;', controls.previousHotkey, 'Ctrl+Alt+Left')}
          ${settingHotkey('controls.nextHotkey', '&#x540e;&#x4e00;&#x9996;', controls.nextHotkey, 'Ctrl+Alt+Right')}
          ${settingHotkey('controls.volumeUpHotkey', '&#x97f3;&#x91cf;&#x589e;&#x52a0;', controls.volumeUpHotkey, 'Ctrl+Alt+Up')}
          ${settingHotkey('controls.volumeDownHotkey', '&#x97f3;&#x91cf;&#x51cf;&#x5c0f;', controls.volumeDownHotkey, 'Ctrl+Alt+Down')}
          <div class="musicbot-setting-group-label">&#x66f4;&#x591a;&#x547d;&#x4ee4;</div>
          ${settingHotkey('controls.blacklistHotkey', '&#x62c9;&#x9ed1;&#x5feb;&#x6377;&#x952e;', controls.blacklistHotkey, 'Ctrl+Alt+B')}
          ${settingHotkey('controls.skipHotkey', '&#x5207;&#x6b4c;&#x5feb;&#x6377;&#x952e;', controls.skipHotkey, 'Ctrl+Alt+S')}
        </section>
        <section class="musicbot-setting-section">
          <div class="musicbot-setting-group-title">&#x5916;&#x90e8;&#x6307;&#x4ee4;&#x4e0e;&#x72b6;&#x6001;</div>
          <div class="musicbot-setting-inline"><span>&#x63a7;&#x5236;&#x5730;&#x5740;</span><input value="/api/integrations/control" readonly></div>
          <div class="musicbot-setting-inline"><span>&#x72b6;&#x6001;&#x63a5;&#x53e3;</span><input value="/api/integrations/status" readonly></div>
          <div class="musicbot-setting-hint">&#x5f00;&#x542f;&#x540e;&#x53ef;&#x4f9b; Stream Deck&#x3001;OBS &#x6216;&#x5176;&#x4ed6;&#x5916;&#x90e8;&#x63a7;&#x5236;&#x5668;&#x8c03;&#x7528;&#x3002;</div>
        </section>
      `
    } else {
      content = `
        <section class="musicbot-setting-section">
          <div class="musicbot-setting-group-title">&#x7f51;&#x6613;&#x4e91;&#x767b;&#x5f55;</div>
          <div class="musicbot-settings-login-row">
            <input id="musicbot-cookie" data-setting-input="cookie" placeholder="MUSIC_U=..." value="${escapeHtml(settingValues.cookie)}">
            <button class="primary" data-setting-action="save-cookie">&#x4fdd;&#x5b58;</button>
            <button data-setting-action="login-status">&#x68c0;&#x67e5;&#x767b;&#x5f55;</button>
            <button data-setting-action="login-qr">&#x4e8c;&#x7ef4;&#x7801;&#x767b;&#x5f55;</button>
            <button data-setting-action="logout">&#x9000;&#x51fa;&#x767b;&#x5f55;</button>
          </div>
          <div class="musicbot-setting-status">${login ? `&#x5df2;&#x767b;&#x5f55;&#xff1a;${escapeHtml(login.nickname || login.userId || '')}` : '&#x5f53;&#x524d;&#x672a;&#x767b;&#x5f55;'}</div>
          <div id="musicbot-qr-box">${settingValues.qrimg ? `<img class="musicbot-qr" src="${escapeHtml(settingValues.qrimg)}" alt="&#x767b;&#x5f55;&#x4e8c;&#x7ef4;&#x7801;">` : ''}</div>
        </section>
        <section class="musicbot-setting-section">
          <div class="musicbot-setting-group-title">&#x97f3;&#x9891;&#x64ad;&#x653e;</div>
          <div class="musicbot-setting-grid">
            ${settingCheckbox('audioNormalization.enabled', '&#x97f3;&#x91cf;&#x5747;&#x8861;', normalization.enabled === true, { switch: true })}
            ${settingNumber('audioNormalization.targetLufs', '&#x76ee;&#x6807;&#x54cd;&#x5ea6;', normalization.targetLufs ?? -14, -30, -5, 'LUFS')}
          </div>
          <div class="musicbot-setting-hint">&#x4f7f;&#x7528; mpv &#x5185;&#x7f6e;&#x5355;&#x904d; loudnorm&#x5904;&#x7406;&#xff0c;&#x4e0d;&#x4ea7;&#x751f;&#x5206;&#x6790;&#x6587;&#x4ef6;&#x3002;</div>
        </section>
        <section class="musicbot-setting-section">
          <div class="musicbot-setting-group-title">&#x4f59;&#x989d;&#x67e5;&#x8be2;</div>
          <div class="musicbot-setting-grid">
            ${settingCheckbox('permissions.balanceQueryEnabled', '&#x5141;&#x8bb8;&#x67e5;&#x8be2;&#x4f59;&#x989d;', permissions.balanceQueryEnabled !== false, { switch: true })}
          </div>
          <div class="musicbot-setting-inline"><span>&#x67e5;&#x8be2;&#x4f59;&#x989d;&#x53e3;&#x4ee4;</span><input data-settings-field="commands.balance" value="${escapeHtml(commands.balance || '\u67e5\u8be2\u4f59\u989d')}"></div>
          <div class="musicbot-setting-hint">&#x67e5;&#x8be2;&#x7ed3;&#x679c;&#x540c;&#x65f6;&#x4fdd;&#x7559;&#x76f4;&#x64ad; UI &#x5e7f;&#x64ad;&#x63a5;&#x53e3;&#xff0c;&#x4f9b;&#x540e;&#x7eed;&#x64ad;&#x62a5;&#x4f7f;&#x7528;&#x3002;</div>
        </section>
        <section class="musicbot-setting-section">
          <div class="musicbot-setting-group-title">&#x6570;&#x636e;&#x914d;&#x7f6e;</div>
          <div class="musicbot-setting-grid">
            ${dataSectionCheckbox('idle', '&#x7a7a;&#x95f2;&#x6b4c;&#x5355;')}
            ${dataSectionCheckbox('filters', '&#x6b4c;&#x540d;&#x8fc7;&#x6ee4;')}
            ${dataSectionCheckbox('blacklist', '&#x9ed1;&#x540d;&#x5355;')}
            ${dataSectionCheckbox('points', '&#x79ef;&#x5206;&#x8bb0;&#x5f55;')}
          </div>
          <div class="musicbot-data-actions">
            <button class="primary" data-setting-action="export-data">&#x5bfc;&#x51fa;&#x9009;&#x4e2d;&#x914d;&#x7f6e;</button>
            <button data-setting-action="import-data">&#x5bfc;&#x5165;&#x9009;&#x4e2d;&#x914d;&#x7f6e;</button>
            <input id="musicbot-data-config-file" type="file" accept="application/json,.json" hidden>
          </div>
          <div class="musicbot-setting-hint">&#x5bfc;&#x5165;&#x65f6;&#x4ec5;&#x66ff;&#x6362;&#x5df2;&#x52fe;&#x9009;&#x4e14;&#x6587;&#x4ef6;&#x4e2d;&#x5b58;&#x5728;&#x7684;&#x5185;&#x5bb9;&#x3002;</div>
        </section>
      `
    }
    return `<div class="musicbot-settings-shell"><nav class="musicbot-settings-nav">${nav.map(([key, label]) => `<button class="musicbot-settings-nav-button${key === settingsSection ? ' active' : ''}" data-settings-section="${key}">${label}</button>`).join('')}</nav><div class="musicbot-settings-content">${content}</div></div>`
  }

  function settingsKey() {
    const config = state?.config || {}
    return JSON.stringify({ section: settingsSection, queue: config.queue, permissions: config.permissions, points: config.points, audioNormalization: config.audioNormalization, commands: config.commands, controls: config.controls, login: config.music?.login })
  }

  function captureSettingInputs() {
    if ($('musicbot-cookie')) settingValues.cookie = $('musicbot-cookie').value
  }

  function saveSettingsField(element) {
    const path = element?.dataset.settingsField || ''
    const [group, key] = path.split('.')
    if (!group || !key) return
    const value = element.type === 'checkbox'
      ? element.checked
      : (element.type === 'radio' ? element.dataset.settingsValue === 'true'
      : (element.type === 'number' ? Number(element.value) : element.value.trim())
      )
    const patch = { [group]: { [key]: value } }
    if (group === 'permissions' && key !== 'freeRequest' && key.endsWith('Only') && value === true) {
      patch.permissions.freeRequest = false
    }
    post('/api/settings', patch)
      .then((result) => {
        if (state) state.config = result.config || state.config
        settingsRenderKey = ''
        renderRows()
        showToast('\u8bbe\u7f6e\u5df2\u4fdd\u5b58')
      })
      .catch((error) => {
        showToast(error.message, true)
        getJson('/api/state').then(applyState).catch(() => {})
      })
  }

  function renderRows() {
    if (!tableBody) return
    if (activeView === 'idle') {
      const nextKey = idleViewKey()
      if (tableBody.dataset.view === 'idle' && idleRenderKey === nextKey) return
      const scrollTop = tableBody.querySelector('.musicbot-playlist-tree')?.scrollTop || 0
      const formValues = {
        playlist: $('musicbot-idle-playlist-input')?.value || '',
        directory: $('musicbot-idle-local-input')?.value || '',
        name: $('musicbot-idle-local-name')?.value || '',
      }
      tableBody.innerHTML = renderIdleView()
      tableBody.dataset.view = 'idle'
      idleRenderKey = nextKey
      if ($('musicbot-idle-playlist-input')) $('musicbot-idle-playlist-input').value = formValues.playlist
      if ($('musicbot-idle-local-input')) $('musicbot-idle-local-input').value = formValues.directory
      if ($('musicbot-idle-local-name')) $('musicbot-idle-local-name').value = formValues.name
      const tree = tableBody.querySelector('.musicbot-playlist-tree')
      if (tree) tree.scrollTop = scrollTop
      return
    }
    if (activeView === 'filter') {
      const nextKey = JSON.stringify({ values: state?.titleFilters || [], searchText })
      if (tableBody.dataset.view === 'filter' && filterRenderKey === nextKey) return
      const inputValue = $('musicbot-filter-input')?.value || ''
      tableBody.innerHTML = renderFilterView()
      tableBody.dataset.view = 'filter'
      filterRenderKey = nextKey
      if ($('musicbot-filter-input')) $('musicbot-filter-input').value = inputValue
      return
    }
    if (activeView === 'blacklist') {
      const nextKey = JSON.stringify({ values: state?.blacklist || [], searchText })
      if (tableBody.dataset.view === 'blacklist' && blacklistRenderKey === nextKey) return
      const inputValue = $('musicbot-blacklist-input')?.value || ''
      tableBody.innerHTML = renderBlacklistView()
      tableBody.dataset.view = 'blacklist'
      blacklistRenderKey = nextKey
      if ($('musicbot-blacklist-input')) $('musicbot-blacklist-input').value = inputValue
      return
    }
    if (activeView === 'settings') {
      const nextKey = settingsKey()
      if (tableBody.dataset.view === 'settings' && settingsRenderKey === nextKey) return
      captureSettingInputs()
      tableBody.dataset.view = 'settings'
      tableBody.innerHTML = renderSettingsView()
      settingsRenderKey = nextKey
      return
      /* legacy settings markup retained below only as a migration guard */
      if ($('musicbot-cookie')) settingValues.cookie = $('musicbot-cookie').value
      if ($('musicbot-playlist')) settingValues.playlist = $('musicbot-playlist').value
      if ($('musicbot-local')) settingValues.local = $('musicbot-local').value
      tableBody.innerHTML = `
        <div class="musicbot-settings">
          <section class="musicbot-settings-section">
            <h3>网易云账号</h3>
            <div class="musicbot-settings-line">
              <input id="musicbot-cookie" placeholder="MUSIC_U=..." value="${escapeHtml(settingValues.cookie)}">
              <button class="primary" data-setting-action="save-cookie">保存 Cookie</button>
              <button data-setting-action="login-status">检查登录</button>
              <button data-setting-action="login-qr">二维码登录</button>
            </div>
            <div id="musicbot-qr-box"></div>
          </section>
          <section class="musicbot-settings-section">
            <h3>空闲歌单</h3>
            <div class="musicbot-settings-line">
              <input id="musicbot-playlist" placeholder="网易云歌单 ID 或链接" value="${escapeHtml(settingValues.playlist)}">
              <button class="primary" data-setting-action="import-playlist">导入歌单</button>
            </div>
            <div class="musicbot-settings-line">
              <input id="musicbot-local" placeholder="本地歌曲目录，例如 D:\\Music" value="${escapeHtml(settingValues.local)}">
              <button data-setting-action="import-local">导入本地目录</button>
            </div>
          </section>
          <section class="musicbot-settings-section">
            <h3>运行状态</h3>
            <div>当前设备和音量可直接在顶部播放器控制；点歌接口会在入队前完成账号音源和歌词缓存。</div>
          </section>
        </div>
      `
      return
    }
    if (activeView === 'points') {
      const nextKey = JSON.stringify({ users: pointsUsers, selected: [...selectedUserIds].sort(), editingUserId, searchText })
      if (tableBody.dataset.view === 'points' && pointsRenderKey === nextKey) return
      const scrollTop = tableBody.querySelector('.musicbot-points-list')?.scrollTop || 0
      tableBody.dataset.view = 'points'
      tableBody.innerHTML = renderPointsView()
      const list = tableBody.querySelector('.musicbot-points-list')
      if (list) list.scrollTop = scrollTop
      pointsRenderKey = nextKey
      return
    }
    tableBody.dataset.view = activeView
    const songs = visibleSongs()
    const historyScrollTop = tableBody.scrollTop
    const followHistory = activeView === 'history' && (
      tableBody.dataset.renderedView !== 'history' ||
      tableBody.scrollHeight - tableBody.scrollTop - tableBody.clientHeight <= 36
    )
    if (!songs.length) {
      tableBody.innerHTML = '<div class="musicbot-empty">暂无歌曲</div>'
      tableBody.dataset.renderedView = activeView
      return
    }
    tableBody.innerHTML = songs.map((song, index) => {
      const duration = song.duration ? formatTime(song.duration) : '--:--'
      const cacheStatus = cacheStatusView(song)
      const lyricMode = song.lyricMode === 'word' ? '\u9010\u5b57' : (song.lyricMode === 'line' ? 'LRC' : '--')
      return `
        <div class="musicbot-row${song.isPlaying ? ' musicbot-row-playing' : ''}" data-uid="${escapeHtml(song.uid)}" data-playing="${song.isPlaying ? 'true' : 'false'}">
          <div class="musicbot-song-cell">
            <span class="musicbot-index">${index + 1}</span>
            <span class="musicbot-cover" style="background-image:url('${escapeHtml(song.coverUrl || './image/Frame_2_387.png')}')"></span>
            <div class="musicbot-song-copy"><div class="musicbot-song-title">${escapeHtml(song.title || song.uid)}</div><div class="musicbot-song-artist">${escapeHtml(song.artist || '')}</div>${requesterBadgeMarkup(song.requestedBy)}</div>
          </div>
          <span>${escapeHtml(duration)}</span>
          <span class="musicbot-status ${cacheStatus.className}"><i class="musicbot-log-dot"></i>${cacheStatus.label}</span>
          <span><b class="musicbot-badge">${escapeHtml(song.source === 'local' ? '本地' : (song.playbackSource || '网易云'))}</b></span>
          <span><b class="musicbot-badge">${escapeHtml(lyricMode)}</b></span>
          <span>${escapeHtml(song.requestedAt ? new Date(song.requestedAt).toLocaleTimeString() : '--:--:--')}</span>
          <div class="musicbot-actions">${rowActions(song)}</div>
        </div>
      `
    }).join('')
    tableBody.dataset.renderedView = activeView
    if (activeView === 'history') {
      requestAnimationFrame(() => {
        tableBody.scrollTop = followHistory ? tableBody.scrollHeight : historyScrollTop
      })
    }
  }

  function renderCounts() {
    const count = state?.queue?.length || 0
    if ($('2_82')) $('2_82').textContent = String(count)
    if ($('2_81')) {
      $('2_81').title = `${count} \u9996\u70b9\u64ad\u6b4c\u66f2`
      $('2_81').style.display = count > 0 ? 'flex' : 'none'
    }
  }

  function renderState() {
    renderPlayer()
    renderRows()
    renderCounts()
    renderSystem()
    syncViewControls()
  }

  function syncViewControls() {
    const showQueueControls = activeView === 'queue'
    ;[$('2_661'), $('2_662'), $('2_669')].forEach((element) => {
      if (element) element.style.display = showQueueControls ? '' : 'none'
    })
    const simpleManagementView = activeView === 'filter' || activeView === 'blacklist' || activeView === 'settings' || activeView === 'points'
    if ($('2_96')) $('2_96').style.display = activeView === 'settings' ? 'none' : ''
    const searchInput = $('musicbot-search')
    if (searchInput) {
      const placeholders = {
        filter: '搜索过滤关键词',
        blacklist: '搜索歌曲、歌手或来源',
        points: '搜索备注、积分、昵称或抖音号',
      }
      searchInput.placeholder = placeholders[activeView] || '搜索歌曲或歌手'
    }
    const customListView = activeView === 'idle' || simpleManagementView
    if ($('2_103')) $('2_103').style.display = customListView ? 'none' : ''
    if (tableFooter) tableFooter.style.display = customListView ? 'none' : ''
    tableBody?.classList.toggle('musicbot-table-body-idle', activeView === 'idle')
    tableBody?.classList.toggle('musicbot-table-body-filter', activeView === 'filter')
    tableBody?.classList.toggle('musicbot-table-body-blacklist', activeView === 'blacklist')
    tableBody?.classList.toggle('musicbot-table-body-settings', activeView === 'settings')
    tableBody?.classList.toggle('musicbot-table-body-points', activeView === 'points')
  }

  function applyState(next) {
    if (!acceptStateSync(next)) return
    const previous = state
    const chronologicalHistory = Array.isArray(next.history)
      ? [...next.history].sort((left, right) => {
        const leftTime = Number(left.endedAt || left.failedAt || left.requestedAt || 0)
        const rightTime = Number(right.endedAt || right.failedAt || right.requestedAt || 0)
        return leftTime - rightTime
      })
      : (state?.history || [])
    const previousMode = previous?.config?.queue?.idleMode || 'sequence'
    const previousAutoIdle = previous?.config?.queue?.autoIdle !== false
    const previousInterruptIdle = previous?.config?.queue?.interruptIdleOnRequest === true
    const nextMode = next?.config?.queue?.idleMode || previousMode
    const nextAutoIdle = next?.config?.queue?.autoIdle ?? previousAutoIdle
    const nextInterruptIdle = next?.config?.queue?.interruptIdleOnRequest ?? previousInterruptIdle
    if (Array.isArray(next.idlePlaylists) || nextMode !== previousMode || nextAutoIdle !== previousAutoIdle || nextInterruptIdle !== previousInterruptIdle) {
      idleStateVersion += 1
    }
    state = {
      ...(state || {}),
      ...next,
      queue: Array.isArray(next.queue) ? next.queue : (state?.queue || []),
      idleList: Array.isArray(next.idleList) ? next.idleList : (state?.idleList || []),
      idlePlaylists: Array.isArray(next.idlePlaylists) ? next.idlePlaylists : (state?.idlePlaylists || []),
      history: chronologicalHistory,
      blacklist: Array.isArray(next.blacklist) ? next.blacklist : (state?.blacklist || []),
      titleFilters: Array.isArray(next.titleFilters) ? next.titleFilters : (state?.titleFilters || []),
    }
    if (previous?.current?.uid && state.current?.uid === previous.current.uid) {
      state.current = { ...previous.current, ...state.current }
    }
    if (state.current?.uid !== lastCurrentUid) lastCurrentUid = state.current?.uid || ''
    recoverLyricsIfNeeded()
    if (state.overlay?.message) {
      const overlayKey = `${state.overlay.message}:${state.overlay.expiresAt || ''}`
      if (overlayKey !== lastOverlayKey) {
        lastOverlayKey = overlayKey
        addLog(state.overlay.message, 'info')
      }
    } else {
      lastOverlayKey = ''
    }
    renderState()
  }

  async function refreshDevices() {
    try {
      const result = await getJson('/api/player/devices')
      const select = $('musicbot-device')
      if (!select) return
      select.innerHTML = [{ name: 'auto', description: '本机音频' }, ...(result.devices || [])]
        .map((item) => `<option value="${escapeHtml(item.name || item.description)}">${escapeHtml(item.description || item.name)}</option>`).join('')
      select.value = result.selected || 'auto'
      if ($('2_68')) $('2_68').textContent = select.selectedOptions[0]?.textContent || '本机音频'
    } catch (error) {
      showToast(error.message, true)
    }
  }

  async function requestSong(query) {
    const value = text(query).trim()
    if (!value) return
    try {
      const result = await post('/api/queue/song', { query: value, user: { userId: 'host', nickname: '主播' } })
      if (result.result?.ignored) return false
      showToast(`已缓存并加入队列：${result.result?.title || value}`)
      return true
    } catch (error) {
      showToast(error.message, true)
      addLog(error.message, 'error')
    }
  }

  async function rowAction(action, uid, isPlaying = false) {
    const song = visibleSongs().find((item) => item.uid === uid && Boolean(item.isPlaying) === isPlaying) || {}
    try {
      if (isPlaying && (action === 'play' || action === 'promote')) return
      if (action === 'play') await post(`/api/queue/${encodeURIComponent(uid)}/play`)
      if (action === 'promote') await post(`/api/queue/${encodeURIComponent(uid)}/promote`)
      if (action === 'remove') {
        if (isPlaying) await post(`/api/queue/${encodeURIComponent(uid)}/remove`, { playing: true })
        else await remove(`/api/queue/${encodeURIComponent(uid)}`)
      }
      if (action === 'blacklist') await post('/api/blacklist', { uid })
      if (action === 'idle-save') await post(`/api/idle/${encodeURIComponent(uid)}`)
      if (action === 'idle-add') await post('/api/queue/idle', { uid, user: { userId: 'host', nickname: '主播' } })
      if (action === 'idle-remove') await remove(`/api/idle/${encodeURIComponent(uid)}`)
      if (action === 'replay' && !(await requestSong(song.sourceId || uid))) return
      showToast('操作已完成')
    } catch (error) {
      showToast(error.message, true)
      addLog(error.message, 'error')
    }
  }

  async function settingAction(action) {
    try {
      if (action === 'export-data') {
        await exportManagedData()
        return
      }
      if (action === 'import-data') {
        $('musicbot-data-config-file')?.click()
        return
      }
      if (action === 'logout') {
        if (loginQrTimer) clearInterval(loginQrTimer)
        loginQrTimer = null
        await post('/api/login/logout')
        settingValues.cookie = ''
        settingValues.qrimg = ''
        settingValues.qrKey = ''
        settingsRenderKey = ''
        await getJson('/api/state').then(applyState)
        showToast('\u5df2\u9000\u51fa\u767b\u5f55')
        return
      }
      if (action === 'save-cookie') {
        settingValues.cookie = $('musicbot-cookie')?.value.trim() || ''
        const result = await post('/api/login/cookie', { cookie: settingValues.cookie })
        settingsRenderKey = ''
        await getJson('/api/state').then(applyState)
        showToast(`\u767b\u5f55\u6210\u529f\uff1a${result.nickname || result.userId || ''}`)
        return
        showToast(`登录成功：${result.nickname || result.userId || ''}`)
      }
      if (action === 'login-status') {
        const result = await getJson('/api/login/status')
        showToast(result.valid ? `\u5df2\u767b\u5f55\uff1a${result.nickname || result.userId || ''}` : (result.message || '\u672a\u767b\u5f55'), !result.valid)
        return
        showToast(result.valid ? `已登录：${result.nickname || result.userId || ''}` : result.message, !result.valid)
      }
      if (action === 'login-qr') {
        if (loginQrTimer) clearInterval(loginQrTimer)
        const qrResult = await getJson('/api/login/qr')
        settingValues.qrimg = qrResult.qrimg || ''
        settingValues.qrKey = qrResult.key || ''
        settingsRenderKey = ''
        renderRows()
        showToast('\u4e8c\u7ef4\u7801\u5df2\u751f\u6210\uff0c\u8bf7\u4f7f\u7528\u7f51\u6613\u4e91\u5ba2\u6237\u7aef\u626b\u7801')
        if (settingValues.qrKey) {
          loginQrTimer = setInterval(async () => {
            try {
              const check = await getJson(`/api/login/qr/check?key=${encodeURIComponent(settingValues.qrKey)}`)
              if (check.saved || check.code === 803) {
                clearInterval(loginQrTimer)
                loginQrTimer = null
                settingValues.qrimg = ''
                settingsRenderKey = ''
                await getJson('/api/state').then(applyState)
                showToast('\u4e8c\u7ef4\u7801\u767b\u5f55\u6210\u529f')
              } else if (check.code === 800) {
                clearInterval(loginQrTimer)
                loginQrTimer = null
                showToast('\u4e8c\u7ef4\u7801\u5df2\u8fc7\u671f', true)
              }
            } catch (error) {
              clearInterval(loginQrTimer)
              loginQrTimer = null
              showToast(error.message, true)
            }
          }, 2000)
        }
        return
      }
      if (action === 'login-qr-legacy-disabled') {
        const result = await getJson('/api/login/qr')
        const box = $('musicbot-qr-box')
        if (box) box.innerHTML = `<img class="musicbot-qr" src="${escapeHtml(result.qrimg)}" alt="登录二维码">`
        showToast('二维码已生成，请使用网易云客户端扫码')
      }
      if (action === 'import-playlist') {
        settingValues.playlist = $('musicbot-playlist')?.value.trim() || ''
        const result = await post('/api/idle/import/playlist', { id: settingValues.playlist })
        showToast(`已导入 ${result.result?.imported || 0} 首歌曲`)
      }
      if (action === 'import-local') {
        settingValues.local = $('musicbot-local')?.value.trim() || ''
        const result = await post('/api/idle/import/local', { directory: settingValues.local, recursive: true })
        showToast(`已导入 ${result.result?.imported || 0} 首本地歌曲`)
      }
    } catch (error) {
      showToast(error.message, true)
      addLog(error.message, 'error')
    }
  }

  async function idleAction(action, element = null) {
    try {
      if (action === 'expand') {
        const group = element?.closest('[data-playlist-id]')
        const id = group?.dataset.playlistId
        if (id) idleExpanded.has(id) ? idleExpanded.delete(id) : idleExpanded.add(id)
        idleRenderKey = ''
        renderRows()
        return
      }
      if (action === 'locate-playing') {
        const current = state?.current
        const playlistId = current?.idlePlaylistId
        const uid = current?.uid
        if (!playlistId || !uid || !current.requestKind?.startsWith('idle-')) {
          showToast('当前没有播放空闲歌单歌曲', true)
          return
        }
        idleExpanded.add(playlistId)
        idleRenderKey = ''
        renderRows()
        requestAnimationFrame(() => {
          const row = tableBody.querySelector(`[data-idle-song="${CSS.escape(uid)}"][data-playlist-id="${CSS.escape(playlistId)}"]`)
          row?.scrollIntoView({ behavior: 'smooth', block: 'center' })
        })
        return
      }
      if (action === 'toggle-all') {
        const enabled = element?.dataset.enable === 'true'
        await post('/api/idle/playlists/toggle', { enabled })
        showToast(enabled ? '已启用全部歌单' : '已停用全部歌单')
        return
      }
      if (action === 'select-folder') {
        element?.classList.add('loading')
        try {
          const result = await getJson('/api/system/select-folder')
          if (result.directory && $('musicbot-idle-local-input')) $('musicbot-idle-local-input').value = result.directory
        } finally {
          element?.classList.remove('loading')
        }
        return
      }
      if (action === 'add-playlist') {
        const id = $('musicbot-idle-playlist-input')?.value.trim()
        const directory = $('musicbot-idle-local-input')?.value.trim()
        const name = $('musicbot-idle-local-name')?.value.trim()
        if (id && directory) throw new Error('链接与本地路径请只填写一项')
        if (!id && !directory) throw new Error('请输入歌单链接、ID 或本地文件夹路径')
        if (id) {
          const result = await post('/api/idle/import/playlist', { id })
          if ($('musicbot-idle-playlist-input')) $('musicbot-idle-playlist-input').value = ''
          showToast(`已添加歌单：${result.result?.playlist?.name || '网易云歌单'}`)
        } else {
          const result = await post('/api/idle/import/local', { directory, name, recursive: true })
          if ($('musicbot-idle-local-input')) $('musicbot-idle-local-input').value = ''
          if ($('musicbot-idle-local-name')) $('musicbot-idle-local-name').value = ''
          showToast(`已添加歌单：${result.result?.playlist?.name || name || '本地歌单'}`)
        }
        return
      }
      if (action === 'import-playlist') {
        const id = $('musicbot-idle-playlist-input')?.value.trim()
        if (!id) return
        const result = await post('/api/idle/import/playlist', { id })
        if ($('musicbot-idle-playlist-input')) $('musicbot-idle-playlist-input').value = ''
        showToast(`已添加歌单：${result.result?.playlist?.name || '网易云歌单'}`)
        return
      }
      if (action === 'import-local') {
        const directory = $('musicbot-idle-local-input')?.value.trim()
        const name = $('musicbot-idle-local-name')?.value.trim()
        if (!directory) return
        const result = await post('/api/idle/import/local', { directory, name, recursive: true })
        if ($('musicbot-idle-local-input')) $('musicbot-idle-local-input').value = ''
        if ($('musicbot-idle-local-name')) $('musicbot-idle-local-name').value = ''
        showToast(`已添加歌单：${result.result?.playlist?.name || name || '本地歌单'}`)
        return
      }
      if (action === 'export') {
        const result = await getJson('/api/idle/export')
        const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
        const link = document.createElement('a')
        link.href = URL.createObjectURL(blob)
        link.download = 'musicbot-idle-playlists.json'
        link.click()
        setTimeout(() => URL.revokeObjectURL(link.href), 1000)
        showToast('歌单配置已导出')
        return
      }
      if (action === 'import-config') {
        $('musicbot-idle-config-file')?.click()
        return
      }
      if (action === 'clear') {
        if (!window.confirm('确定清空已勾选歌单中的歌曲吗？')) return
        const ids = idlePlaylists().filter((playlist) => playlist.enabled !== false).map((playlist) => playlist.id)
        await post('/api/idle/playlists/clear', { ids })
        showToast('已清空选中歌单')
      }
    } catch (error) {
      showToast(error.message, true)
      addLog(error.message, 'error')
    }
  }

  async function idlePlaylistAction(action, element) {
    const playlistId = decodeURIComponent(element?.dataset.playlistId || '')
    const playlist = idlePlaylists().find((item) => item.id === playlistId)
    if (!playlist) return
    try {
      if (action === 'play') {
        await post(`/api/idle/playlists/${encodeURIComponent(playlistId)}/play`)
        showToast(`开始播放《${playlist.name}》`)
        return
      }
      if (action === 'rename') {
        const name = window.prompt('请输入新的歌单名称', playlist.name)
        if (name === null) return
        const normalized = name.trim()
        if (!normalized || normalized === playlist.name) return
        await post(`/api/idle/playlists/${encodeURIComponent(playlistId)}/rename`, { name: normalized })
        showToast(`歌单已重命名为《${normalized}》`)
        return
      }
      if (action === 'remove') {
        if (!window.confirm(`确定删除歌单《${playlist.name}》及其中全部歌曲吗？`)) return
        idleExpanded.delete(playlistId)
        await remove(`/api/idle/playlists/${encodeURIComponent(playlistId)}`)
        showToast(`歌单《${playlist.name}》已删除`)
      }
    } catch (error) {
      showToast(error.message, true)
      addLog(error.message, 'error')
    }
  }

  async function idleSongAction(action, element) {
    const playlistId = decodeURIComponent(element.dataset.playlistId || '')
    const uid = decodeURIComponent(element.dataset.songUid || '')
    try {
      if (action === 'play') await post(`/api/idle/playlists/${encodeURIComponent(playlistId)}/songs/${encodeURIComponent(uid)}/play`)
      if (action === 'request') {
        const result = await post('/api/queue/idle', { uid, playlistId, user: { userId: 'host', nickname: '主播' } })
        if (result.result?.ignored) return
      }
      if (action === 'promote') await post(`/api/idle/playlists/${encodeURIComponent(playlistId)}/songs/${encodeURIComponent(uid)}/promote`)
      if (action === 'blacklist') await post('/api/blacklist', { uid })
      if (action === 'remove') await remove(`/api/idle/playlists/${encodeURIComponent(playlistId)}/songs/${encodeURIComponent(uid)}`)
      showToast('操作已完成')
    } catch (error) {
      showToast(error.message, true)
      addLog(error.message, 'error')
    }
  }

  async function importIdleConfigFile(file) {
    if (!file) return
    try {
      const config = JSON.parse(await file.text())
      const result = await post('/api/idle/import/config', config)
      showToast(`已导入 ${result.result?.playlists || 0} 个歌单`)
    } catch (error) {
      showToast(error.message, true)
      addLog(error.message, 'error')
    }
  }

  function applyTitleFilterKeywords(keywords) {
    if (!Array.isArray(keywords)) return
    state = { ...(state || {}), titleFilters: keywords }
    filterRenderKey = ''
    renderRows()
  }

  async function filterAction(action, element) {
    try {
      if (action === 'add') {
        const keyword = $('musicbot-filter-input')?.value.trim()
        if (!keyword) return
        const result = await post('/api/title-filters', { keyword })
        applyTitleFilterKeywords(result.keywords)
        showToast('\u8fc7\u6ee4\u5173\u952e\u8bcd\u5df2\u6dfb\u52a0')
        return
      }
      if (action === 'remove') {
        const result = await remove(`/api/title-filters/${encodeURIComponent(element.dataset.filterIndex)}`)
        applyTitleFilterKeywords(result.keywords)
        return
      }
      if (action === 'import') {
        $('musicbot-filter-file')?.click()
        return
      }
      if (action === 'export') {
        const payload = {
          version: 1,
          exportedAt: new Date().toISOString(),
          keywords: state?.titleFilters || [],
        }
        const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
        const link = document.createElement('a')
        link.href = URL.createObjectURL(blob)
        link.download = 'musicbot-title-filters.json'
        link.click()
        setTimeout(() => URL.revokeObjectURL(link.href), 1000)
        showToast('\u8fc7\u6ee4\u5173\u952e\u8bcd\u5df2\u5bfc\u51fa')
        return
      }
      if (action === 'clear') {
        if (!window.confirm('\u786e\u5b9a\u6e05\u7a7a\u5168\u90e8\u6b4c\u540d\u8fc7\u6ee4\u5173\u952e\u8bcd\u5417\uff1f')) return
        const result = await remove('/api/title-filters')
        applyTitleFilterKeywords(result.keywords)
        showToast('\u8fc7\u6ee4\u5173\u952e\u8bcd\u5df2\u6e05\u7a7a')
      }
    } catch (error) {
      showToast(error.message, true)
    }
  }

  async function importTitleFilterFile(file) {
    if (!file) return
    try {
      const content = await file.text()
      let keywords
      try {
        const parsed = JSON.parse(content)
        keywords = Array.isArray(parsed) ? parsed : parsed?.keywords
      } catch {
        keywords = content.split(/\r?\n/)
      }
      if (!Array.isArray(keywords)) throw new Error('Invalid title filter file')
      const result = await post('/api/title-filters', { keywords })
      applyTitleFilterKeywords(result.keywords)
      showToast(`\u5df2\u5bfc\u5165 ${keywords.filter((keyword) => String(keyword || '').trim()).length} \u4e2a\u8fc7\u6ee4\u5173\u952e\u8bcd`)
    } catch (error) {
      showToast(error.message, true)
    }
  }

  function applyBlacklistEntries(entries) {
    if (!Array.isArray(entries)) return
    state = { ...(state || {}), blacklist: entries }
    blacklistRenderKey = ''
    renderRows()
  }

  async function blacklistAction(action, element) {
    try {
      if (action === 'add') {
        const query = $('musicbot-blacklist-input')?.value.trim()
        if (!query) return
        const result = await post('/api/blacklist', { query })
        applyBlacklistEntries(result.blacklist)
        showToast(`\u300a${result.result?.title || query}\u300b\u5df2\u62c9\u9ed1`)
        return
      }
      if (action === 'remove') {
        const result = await remove(`/api/blacklist/${encodeURIComponent(element.dataset.blacklistIndex)}`)
        applyBlacklistEntries(result.blacklist)
        return
      }
      if (action === 'clear') {
        if (!window.confirm('\u786e\u5b9a\u6e05\u7a7a\u5168\u90e8\u6b4c\u66f2\u9ed1\u540d\u5355\u5417\uff1f')) return
        const result = await remove('/api/blacklist')
        applyBlacklistEntries(result.blacklist)
        showToast('\u9ed1\u540d\u5355\u5df2\u6e05\u7a7a')
      }
    } catch (error) {
      showToast(error.message, true)
    }
  }

  async function pointsAction(action, element) {
    const row = element?.closest('[data-user-id]')
    const id = row ? decodeURIComponent(row.dataset.userId || '') : ''
    try {
      if (action === 'edit') {
        editingUserId = id
        pointsRenderKey = ''
        renderRows()
        return
      }
      if (action === 'cancel') {
        editingUserId = ''
        pointsRenderKey = ''
        renderRows()
        return
      }
      if (action === 'save') {
        const patch = {}
        row.querySelectorAll('[data-user-field]').forEach((input) => {
          patch[input.dataset.userField] = input.type === 'number' ? Number(input.value) : input.value.trim()
        })
        const result = await post(`/api/users/${encodeURIComponent(id)}`, patch)
        editingUserId = ''
        applyPointsUsers(result.users)
        showToast('\u79ef\u5206\u8bb0\u5f55\u5df2\u4fdd\u5b58')
        return
      }
      if (action === 'remove') {
        const result = await remove(`/api/users/${encodeURIComponent(id)}`)
        selectedUserIds.delete(id)
        applyPointsUsers(result.users)
        return
      }
      if (action === 'remove-selected') {
        if (!selectedUserIds.size) return
        const result = await post('/api/users/delete', { ids: [...selectedUserIds] })
        selectedUserIds.clear()
        applyPointsUsers(result.users)
        showToast(`\u5df2\u5220\u9664 ${result.removed || 0} \u6761\u79ef\u5206\u8bb0\u5f55`)
        return
      }
      if (action === 'clear') {
        if (!pointsUsers.length || !window.confirm('\u786e\u5b9a\u6e05\u7a7a\u5168\u90e8\u79ef\u5206\u8bb0\u5f55\u5417\uff1f')) return
        await remove('/api/users')
        selectedUserIds.clear()
        applyPointsUsers([])
        showToast('\u79ef\u5206\u8bb0\u5f55\u5df2\u6e05\u7a7a')
      }
    } catch (error) {
      showToast(error.message, true)
    }
  }

  function downloadJson(payload, filename) {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = filename
    link.click()
    setTimeout(() => URL.revokeObjectURL(link.href), 1000)
  }

  async function exportManagedData() {
    const sections = [...settingValues.dataSections]
    if (!sections.length) throw new Error('\u8bf7\u81f3\u5c11\u9009\u62e9\u4e00\u9879\u5bfc\u51fa\u5185\u5bb9')
    const result = await post('/api/data/export', { sections })
    downloadJson(result, 'musicbot-data-config.json')
    showToast('\u6570\u636e\u914d\u7f6e\u5df2\u5bfc\u51fa')
  }

  async function importManagedDataFile(file) {
    if (!file) return
    const payload = JSON.parse(await file.text())
    const sections = [...settingValues.dataSections]
    if (!sections.length) throw new Error('\u8bf7\u81f3\u5c11\u9009\u62e9\u4e00\u9879\u5bfc\u5165\u5185\u5bb9')
    await post('/api/data/import', { ...payload, sections })
    settingsRenderKey = ''
    idleRenderKey = ''
    filterRenderKey = ''
    blacklistRenderKey = ''
    await getJson('/api/state').then(applyState)
    if (sections.includes('points')) await refreshPointsUsers()
    showToast('\u6570\u636e\u914d\u7f6e\u5df2\u5bfc\u5165')
  }

  function applyIdleConfigResult(result) {
    if (!result || !state?.config?.queue) return
    state = {
      ...state,
      config: {
        ...state.config,
        queue: {
          ...state.config.queue,
          idleMode: result.mode || state.config.queue.idleMode,
          autoIdle: typeof result.autoIdle === 'boolean' ? result.autoIdle : state.config.queue.autoIdle,
          interruptIdleOnRequest: typeof result.interruptIdleOnRequest === 'boolean'
            ? result.interruptIdleOnRequest
            : state.config.queue.interruptIdleOnRequest,
        },
      },
    }
    idleStateVersion += 1
    renderRows()
  }

  function hotkeyText(event) {
    const parts = []
    if (event.ctrlKey) parts.push('Ctrl')
    if (event.altKey) parts.push('Alt')
    if (event.shiftKey) parts.push('Shift')
    if (event.metaKey) parts.push('Meta')
    const key = event.key === ' ' ? 'Space' : event.key
    if (!['Control', 'Alt', 'Shift', 'Meta'].includes(key)) parts.push(key)
    return parts.join('+').toLowerCase()
  }

  function handleConfiguredHotkey(event) {
    const tagName = event.target?.tagName?.toLowerCase()
    if (event.repeat || event.target?.isContentEditable || ['input', 'textarea', 'select'].includes(tagName)) return
    const controls = state?.config?.controls || {}
    if (controls.keyboardEnabled === false) return
    const pressed = hotkeyText(event)
    const matches = (value) => text(value).replace(/\s+/g, '').toLowerCase() === pressed
    let endpoint = ''
    let body = {}
    if (matches(controls.startStopHotkey || 'Ctrl+Alt+F1')) {
      endpoint = state?.playback?.status === 'playing' ? '/api/control/pause' : '/api/control/play'
    } else if (matches(controls.playPauseHotkey || 'Ctrl+Alt+P')) {
      endpoint = state?.playback?.status === 'playing' ? '/api/control/pause' : '/api/control/play'
    } else if (matches(controls.previousHotkey || 'Ctrl+Alt+Left')) {
      endpoint = '/api/control/previous'
    } else if (matches(controls.nextHotkey || 'Ctrl+Alt+Right') || matches(controls.skipHotkey || 'Ctrl+Alt+S')) {
      endpoint = '/api/control/next'
    }
    if (matches(controls.volumeUpHotkey || 'Ctrl+Alt+Up')) {
      event.preventDefault()
      post('/api/control/volume', { volume: Math.min(100, Number(state?.playback?.volume || 80) + 5) }).catch((error) => showToast(error.message, true))
      return
    }
    if (matches(controls.volumeDownHotkey || 'Ctrl+Alt+Down')) {
      event.preventDefault()
      post('/api/control/volume', { volume: Math.max(0, Number(state?.playback?.volume || 80) - 5) }).catch((error) => showToast(error.message, true))
      return
    }
    if (matches(controls.blacklistHotkey || 'Ctrl+Alt+B')) {
      if (!state?.current?.uid) return
      event.preventDefault()
      post('/api/blacklist', { uid: state.current.uid }).catch((error) => showToast(error.message, true))
      return
    }
    if (!endpoint) return
    event.preventDefault()
    post(endpoint, body).catch((error) => showToast(error.message, true))
  }

  function bindControls() {
    const setActiveView = (view) => {
      activeView = view
      Object.entries(queueViews).forEach(([name, item]) => {
        if (!item) return
        const active = name === view
        item.classList.toggle('musicbot-tab-active', active)
        item.classList.toggle('musicbot-tab-inactive', !active)
      })
      renderRows()
      syncViewControls()
      if (view === 'points') refreshPointsUsers()
    }

    Object.entries(queueViews).forEach(([view, element]) => {
      if (!element) return
      element.classList.add('musicbot-clickable')
      element.addEventListener('click', () => setActiveView(view))
    })
    setActiveView('queue')

    const bindControl = (id, handler) => {
      const element = $(id)
      if (!element) return
      element.classList.add('musicbot-clickable')
      element.addEventListener('click', () => {
        element.classList.remove('musicbot-control-active')
        void element.offsetWidth
        element.classList.add('musicbot-control-active')
        handler()
      })
    }
    bindControl('2_39', () => {
      const endpoint = state?.playback?.status === 'playing' ? '/api/control/pause' : '/api/control/play'
      post(endpoint).catch((error) => showToast(error.message, true))
    })
    bindControl('2_43', () => post('/api/control/next').catch((error) => showToast(error.message, true)))
    bindControl('2_36', () => post('/api/control/previous').then((result) => {
      if (result.ignored) showToast('\u70b9\u64ad\u5217\u8868\u6ca1\u6709\u4e0a\u4e00\u9996\u6b4c\u66f2')
    }).catch((error) => showToast(error.message, true)))
    $('2_662')?.addEventListener('click', () => requestSong($('musicbot-request')?.value))
    $('2_669')?.addEventListener('click', async () => {
      if (!window.confirm('确定清空点播队列吗？')) return
      try {
        await remove('/api/queue')
        showToast('点播队列已清空')
      } catch (error) {
        showToast(error.message, true)
      }
    })
    $('2_267')?.parentElement?.parentElement?.addEventListener('click', () => { logs = []; renderLogs() })
    tableBody?.addEventListener('click', (event) => {
      const settingsTab = event.target.closest('[data-settings-section]')
      if (settingsTab) {
        settingsSection = settingsTab.dataset.settingsSection || 'request'
        settingsRenderKey = ''
        renderRows()
        return
      }
      const hotkeyClear = event.target.closest('[data-hotkey-clear]')
      if (hotkeyClear) {
        const field = tableBody.querySelector(`[data-settings-field="${hotkeyClear.dataset.hotkeyClear}"]`)
        if (field) {
          field.value = ''
          saveSettingsField(field)
        }
        return
      }
      const pointsButton = event.target.closest('[data-points-action]')
      if (pointsButton) {
        pointsAction(pointsButton.dataset.pointsAction, pointsButton)
        return
      }
      const blacklistButton = event.target.closest('[data-blacklist-action]')
      if (blacklistButton) {
        blacklistAction(blacklistButton.dataset.blacklistAction, blacklistButton)
        return
      }
      const filterButton = event.target.closest('[data-filter-action]')
      if (filterButton) {
        filterAction(filterButton.dataset.filterAction, filterButton)
        return
      }
      const idleSong = event.target.closest('[data-idle-song-action]')
      if (idleSong) {
        idleSongAction(idleSong.dataset.idleSongAction, idleSong)
        return
      }
      const idlePlaylist = event.target.closest('[data-idle-playlist-action]')
      if (idlePlaylist) {
        idlePlaylistAction(idlePlaylist.dataset.idlePlaylistAction, idlePlaylist)
        return
      }
      const idleButton = event.target.closest('[data-idle-action]')
      if (idleButton) {
        idleAction(idleButton.dataset.idleAction, idleButton)
        return
      }
      const idleMode = event.target.closest('[data-idle-mode]')
      if (idleMode) {
        const nextConfig = { mode: idleMode.dataset.idleMode, autoIdle: state?.config?.queue?.autoIdle !== false }
        applyIdleConfigResult(nextConfig)
        post('/api/idle/config', nextConfig)
          .then(applyIdleConfigResult)
          .catch((error) => {
            showToast(error.message, true)
            getJson('/api/state').then(applyState).catch(() => {})
          })
        return
      }
      const button = event.target.closest('[data-row-action]')
      const row = event.target.closest('[data-uid]')
      if (button && row) rowAction(button.dataset.rowAction, row.dataset.uid, row.dataset.playing === 'true')
      const setting = event.target.closest('[data-setting-action]')
      if (setting) settingAction(setting.dataset.settingAction)
    })
    tableBody?.addEventListener('change', (event) => {
      const dataSection = event.target.closest('[data-config-section]')
      if (dataSection) {
        if (dataSection.checked) settingValues.dataSections.add(dataSection.dataset.configSection)
        else settingValues.dataSections.delete(dataSection.dataset.configSection)
        return
      }
      const userSelect = event.target.closest('[data-user-select]')
      if (userSelect) {
        const id = decodeURIComponent(userSelect.dataset.userSelect || '')
        if (userSelect.checked) selectedUserIds.add(id)
        else selectedUserIds.delete(id)
        pointsRenderKey = ''
        renderRows()
        return
      }
      const settingsField = event.target.closest('[data-settings-field]')
      if (settingsField) {
        saveSettingsField(settingsField)
        return
      }
      const toggle = event.target.closest('[data-idle-toggle]')
      if (toggle) {
        post(`/api/idle/playlists/${encodeURIComponent(toggle.dataset.idleToggle)}/toggle`, { enabled: toggle.checked })
          .catch((error) => showToast(error.message, true))
        return
      }
      if (event.target.id === 'musicbot-idle-auto') {
        const nextConfig = {
          autoIdle: event.target.checked,
          interruptIdleOnRequest: state?.config?.queue?.interruptIdleOnRequest === true,
          mode: state?.config?.queue?.idleMode || 'sequence',
        }
        applyIdleConfigResult(nextConfig)
        post('/api/idle/config', nextConfig)
          .then(applyIdleConfigResult)
          .catch((error) => {
            showToast(error.message, true)
            getJson('/api/state').then(applyState).catch(() => {})
          })
        return
      }
      if (event.target.id === 'musicbot-idle-interrupt') {
        const nextConfig = {
          autoIdle: state?.config?.queue?.autoIdle !== false,
          interruptIdleOnRequest: event.target.checked,
          mode: state?.config?.queue?.idleMode || 'sequence',
        }
        applyIdleConfigResult(nextConfig)
        post('/api/idle/config', nextConfig)
          .then(applyIdleConfigResult)
          .catch((error) => {
            showToast(error.message, true)
            getJson('/api/state').then(applyState).catch(() => {})
          })
        return
      }
      if (event.target.id === 'musicbot-idle-config-file') importIdleConfigFile(event.target.files?.[0])
      if (event.target.id === 'musicbot-data-config-file') {
        importManagedDataFile(event.target.files?.[0]).catch((error) => showToast(error.message, true))
        event.target.value = ''
      }
      if (event.target.id === 'musicbot-filter-file') {
        importTitleFilterFile(event.target.files?.[0])
        event.target.value = ''
      }
    })
    tableBody?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && event.target.id === 'musicbot-blacklist-input') {
        event.preventDefault()
        blacklistAction('add', event.target)
        return
      }
      if (event.key === 'Enter' && event.target.id === 'musicbot-filter-input') {
        event.preventDefault()
        filterAction('add', event.target)
      }
    })
    $('2_96')?.addEventListener('click', () => $('musicbot-search')?.focus())
    $('musicbot-search')?.addEventListener('input', (event) => {
      searchText = event.target.value.trim()
      renderRows()
    })
    $('musicbot-search')?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') requestSong(event.target.value)
    })
    $('musicbot-request')?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') requestSong(event.target.value)
    })
    $('musicbot-seek')?.addEventListener('input', (event) => {
      seeking = true
      const duration = Number(state?.playback?.duration || state?.current?.duration || 0)
      if ($('2_49')) $('2_49').style.width = `${event.target.value / 10}%`
      if ($('2_47')) $('2_47').textContent = formatTime(duration * event.target.value / 1000)
    })
    $('musicbot-seek')?.addEventListener('change', (event) => {
      const duration = Number(state?.playback?.duration || state?.current?.duration || 0)
      seeking = false
      post('/api/control/seek', { position: duration * event.target.value / 1000 }).catch((error) => showToast(error.message, true))
    })
    $('musicbot-volume')?.addEventListener('pointerdown', () => { volumeDragging = true })
    $('musicbot-volume')?.addEventListener('input', (event) => {
      if ($('2_59')) $('2_59').style.width = `${event.target.value}%`
      if ($('2_340')) $('2_340').textContent = `${event.target.value}%`
    })
    $('musicbot-volume')?.addEventListener('change', (event) => {
      volumeDragging = false
      post('/api/control/volume', { volume: Number(event.target.value) }).catch((error) => showToast(error.message, true))
    })
    $('musicbot-volume')?.addEventListener('pointerup', () => { volumeDragging = false })
    $('musicbot-device')?.addEventListener('change', (event) => {
      if ($('2_68')) $('2_68').textContent = event.target.selectedOptions[0]?.textContent || '本机音频'
      post('/api/player/device', { device: event.target.value }).catch((error) => showToast(error.message, true))
    })
    window.addEventListener('keydown', handleConfiguredHotkey)
  }

  function installInputs() {
    const searchBox = $('2_96')
    if (searchBox) {
      searchBox.classList.add('musicbot-input-shell')
      const input = document.createElement('input')
      input.id = 'musicbot-search'
      input.className = 'musicbot-input musicbot-search-input'
      input.placeholder = '搜索歌曲或歌手...'
      searchBox.appendChild(input)
    }
    const requestBox = $('2_661')
    if (requestBox) {
      requestBox.classList.add('musicbot-input-shell')
      const input = document.createElement('input')
      input.id = 'musicbot-request'
      input.className = 'musicbot-input musicbot-request-input'
      input.placeholder = '输入歌曲名或歌手名点歌...'
      requestBox.appendChild(input)
    }
    const seekTrack = $('2_48')
    if (seekTrack) {
      const input = document.createElement('input')
      input.id = 'musicbot-seek'
      input.className = 'musicbot-range'
      input.type = 'range'
      input.min = '0'
      input.max = '1000'
      input.value = '0'
      seekTrack.appendChild(input)
    }
    const volumeTrack = $('2_58')
    if (volumeTrack) {
      const input = document.createElement('input')
      input.id = 'musicbot-volume'
      input.className = 'musicbot-range'
      input.type = 'range'
      input.min = '0'
      input.max = '100'
      input.value = '80'
      volumeTrack.appendChild(input)
    }
    const deviceBox = $('2_61')
    if (deviceBox) {
      const select = document.createElement('select')
      select.id = 'musicbot-device'
      select.className = 'musicbot-select'
      deviceBox.appendChild(select)
    }
  }

  function connect() {
    const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`)
    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        if (payload.type === 'state') applyState(payload.state)
      } catch (error) {
        addLog(`状态解析失败：${error.message}`, 'error')
      }
    }
    socket.onclose = () => setTimeout(connect, 1000)
    socket.onerror = () => socket.close()
  }

  function animate(time) {
    if (!seeking && time - lastPlayerRenderAt >= 50) {
      lastPlayerRenderAt = time
      renderPlayer()
    }
    requestAnimationFrame(animate)
  }

  installInputs()
  bindControls()
  addLog('MusicBot UI 已连接', 'success')
  getJson('/api/state').then(applyState).catch((error) => addLog(error.message, 'error'))
  refreshLiveBadges()
  setInterval(refreshLiveBadges, 5000)
  refreshDevices()
  connect()
  renderLogs()
  requestAnimationFrame(animate)
}())
