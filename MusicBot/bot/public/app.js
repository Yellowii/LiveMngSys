const title = document.getElementById('title')
const artist = document.getElementById('artist')
const source = document.getElementById('source')
const cover = document.getElementById('cover')
const lyricsEl = document.getElementById('lyrics')
const queueEl = document.getElementById('queue')
const idleEl = document.getElementById('idle')
const systemEl = document.getElementById('system')
const seek = document.getElementById('seek')
const notice = document.getElementById('notice')
const volume = document.getElementById('volume')
const device = document.getElementById('device')

let state = null
let serverClockOffsetMs = 0
let stateRevision = -1
let stateBootId = ''
let lrc = []
let wordLyrics = []
let lyricMode = 'none'
let seeking = false
let qrTimer = null
let lastPlaybackRenderAt = 0
let renderedSongUid = ''
let renderedQueueKey = ''
let renderedIdleKey = ''
let lyricDom = {
  mode: '',
  lineIndex: -2,
  tokenEls: [],
  currentEl: null,
}

function listKey(songs) {
  return (songs || [])
    .map((song) => `${song.uid}:${song.cacheStatus || ''}:${song.cacheError || ''}`)
    .join('|')
}

function post(url, body = {}) {
  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(async (res) => {
    const json = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(json.error || res.statusText)
    return json
  })
}

function getJson(url) {
  return fetch(url).then(async (res) => {
    const json = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(json.error || res.statusText)
    return json
  })
}

function formatTime(seconds) {
  seconds = Math.max(0, Number(seconds || 0))
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function parseLrc(text) {
  return String(text || '')
    .split(/\r?\n/)
    .map((line) => {
      const match = line.match(/\[(\d+):(\d+(?:\.\d+)?)\](.*)/)
      if (!match) return null
      return { time: Number(match[1]) * 60 + Number(match[2]), text: match[3].trim() }
    })
    .filter((item) => item && item.text)
}

const LYRIC_WORD_SECONDS = 0.26
const LYRIC_SPACE_PAUSE_SECONDS = 0.08
const LYRIC_PUNCT_PAUSE_SECONDS = 0.16
const LYRIC_SENTENCE_PAUSE_SECONDS = 0.28

function getLyricTokens(text) {
  const value = String(text || '').trim()
  const tokens = value.match(/\s+|[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*|[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]|./g) || []
  return tokens.map((token) => {
    if (/^\s+$/.test(token)) {
      return {
        type: 'space',
        text: token,
        duration: token.length * LYRIC_SPACE_PAUSE_SECONDS,
        width: token.length,
      }
    }
    const isPunctuation = /^[^\sA-Za-z0-9\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]+$/.test(token)
    const punctuationDuration = /[。！？.!?]/.test(token)
      ? LYRIC_SENTENCE_PAUSE_SECONDS
      : (/[，、,;；:：]/.test(token) ? LYRIC_PUNCT_PAUSE_SECONDS : 0)
    return {
      type: isPunctuation ? 'punctuation' : 'unit',
      text: token,
      duration: isPunctuation ? punctuationDuration : LYRIC_WORD_SECONDS,
      width: token.length,
    }
  })
}

function getLyricFillPercent(text, lineDuration, elapsed) {
  if (!text || lineDuration <= 0 || elapsed <= 0) return 0
  if (elapsed >= lineDuration) return 100
  const tokens = getLyricTokens(text)
  const totalDuration = tokens.reduce((sum, token) => sum + token.duration, 0)
  const totalWidth = tokens.reduce((sum, token) => sum + token.width, 0) || text.length || 1
  const scale = totalDuration > 0 ? lineDuration / totalDuration : 1
  let remaining = elapsed
  let filledWidth = 0
  for (const token of tokens) {
    const duration = token.duration * scale
    if (token.type === 'space') {
      if (remaining < duration) break
      remaining -= duration
      filledWidth += token.width
      continue
    }
    if (duration <= 0) {
      filledWidth += token.width
      continue
    }
    if (remaining < duration) {
      filledWidth += token.width * (remaining / duration)
      return Math.min(100, Math.max(0, filledWidth / totalWidth * 100))
    }
    remaining -= duration
    filledWidth += token.width
  }
  return Math.min(100, Math.max(0, filledWidth / totalWidth * 100))
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function renderLyrics(position) {
  if (lyricMode === 'word' && wordLyrics.length) {
    renderWordLyrics(position)
    return
  }
  renderLineLyrics(position)
}

function resetLyricDom() {
  lyricDom = {
    mode: '',
    lineIndex: -2,
    tokenEls: [],
    currentEl: null,
  }
}

function currentDuration() {
  return state?.playback?.duration || state?.current?.duration || 0
}

function serverNow() {
  return Date.now() + serverClockOffsetMs
}

function acceptStateSync(nextState) {
  const sync = nextState?.sync
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

function currentPosition() {
  if (!state?.playback) return 0
  const base = Number(state.playback.position || 0)
  if (state.playback.status !== 'playing') return base
  const updatedAt = Number(state.playback.updatedAt || 0)
  const elapsed = updatedAt ? Math.max(0, (serverNow() - updatedAt) / 1000) : 0
  const duration = currentDuration()
  const position = base + elapsed
  return duration ? Math.min(duration, position) : position
}

function renderPlayback(position = currentPosition()) {
  const duration = currentDuration()
  if (!seeking) seek.value = duration ? Math.round((position / duration) * 1000) : 0
  document.getElementById('time-current').textContent = formatTime(position)
  document.getElementById('time-duration').textContent = formatTime(duration)
  renderLyrics(position)
}

function animatePlayback(time) {
  if (state?.current && state?.playback?.status === 'playing' && time - lastPlaybackRenderAt >= 50) {
    lastPlaybackRenderAt = time
    renderPlayback()
  }
  requestAnimationFrame(animatePlayback)
}

function renderWordLyrics(position) {
  let index = -1
  for (let i = 0; i < wordLyrics.length; i += 1) {
    if (wordLyrics[i].time <= position) index = i
    else break
  }
  const lineIndex = index >= 0 ? index : 0
  const line = wordLyrics[lineIndex]
  const next = index + 1 < wordLyrics.length ? wordLyrics[index + 1].text : ''
  if (!line) {
    if (lyricDom.mode !== 'empty') {
      lyricsEl.innerHTML = '<div class="word-line">暂无歌词</div>'
      lyricDom.mode = 'empty'
    }
    return
  }

  if (lyricDom.mode !== 'word' || lyricDom.lineIndex !== lineIndex) {
    const html = line.words.map((word) => {
      const text = escapeHtml(word.text)
      return `<span class="word-token" data-text="${text}" style="--word-fill:0%">${text}</span>`
    }).join('')
    lyricsEl.innerHTML = `<div class="word-line">${html}</div><div class="ktv-next">${escapeHtml(next)}</div>`
    lyricDom.mode = 'word'
    lyricDom.lineIndex = lineIndex
    lyricDom.tokenEls = Array.from(lyricsEl.querySelectorAll('.word-token'))
    lyricDom.currentEl = null
  }

  line.words.forEach((word, wordIndex) => {
    const end = word.start + word.duration
    const fill = position >= end
      ? 100
      : (position > word.start && word.duration > 0
        ? Math.min(100, Math.max(0, ((position - word.start) / word.duration) * 100))
        : 0)
    const el = lyricDom.tokenEls[wordIndex]
    if (!el) return
    el.style.setProperty('--word-fill', `${fill}%`)
    el.className = `word-token ${fill >= 100 ? 'past' : (fill > 0 ? 'active' : '')}`
  })
}

function renderLineLyrics(position) {
  if (!lrc.length) {
    if (lyricDom.mode !== 'empty') {
      lyricsEl.innerHTML = '<div class="ktv-current" data-text="暂无歌词">暂无歌词</div><div class="ktv-next"></div>'
      lyricDom.mode = 'empty'
    }
    return
  }
  let active = 0
  for (let i = 0; i < lrc.length; i += 1) {
    if (lrc[i].time <= position) active = i
  }
  const current = lrc[active]?.text || lrc[0]?.text || '暂无歌词'
  const next = active + 1 < lrc.length ? lrc[active + 1].text : ''
  const lineStart = active >= 0 ? lrc[active].time : 0
  const lineEnd = active + 1 < lrc.length ? lrc[active + 1].time : lineStart
  const fill = lineEnd > lineStart
    ? getLyricFillPercent(current, lineEnd - lineStart, position - lineStart)
    : (active >= 0 ? 100 : 0)
  if (lyricDom.mode !== 'line' || lyricDom.lineIndex !== active) {
    lyricsEl.innerHTML = `<div class="ktv-current" data-text="${escapeHtml(current)}" style="--lyric-fill:${fill}%">${escapeHtml(current)}</div><div class="ktv-next">${escapeHtml(next)}</div>`
    lyricDom.mode = 'line'
    lyricDom.lineIndex = active
    lyricDom.currentEl = lyricsEl.querySelector('.ktv-current')
    lyricDom.tokenEls = []
    return
  }
  lyricDom.currentEl?.style.setProperty('--lyric-fill', `${fill}%`)
}

function renderSong(song) {
  if (!song) {
    renderedSongUid = ''
    resetLyricDom()
    title.textContent = '暂无播放'
    artist.textContent = '等待点歌或从空闲列表加入'
    source.textContent = '待机'
    cover.textContent = '♪'
    lrc = []
    wordLyrics = []
    lyricMode = 'none'
    renderLyrics(0)
    return
  }
  const songUid = song.uid || `${song.source || ''}:${song.sourceId || ''}`
  if (renderedSongUid !== songUid) {
    renderedSongUid = songUid
    resetLyricDom()
    lrc = []
    wordLyrics = []
    lyricMode = 'none'
  }
  title.textContent = song.title
  artist.textContent = `${song.artist || '未知歌手'}${song.album ? ` · ${song.album}` : ''}`
  source.textContent = `${song.source === 'local' ? '本地歌曲' : '网易云音乐'}${song.playbackSource ? ` · ${song.playbackSource}` : ''}${song.cacheStatus ? ` · ${song.cacheStatus}` : ''}`
  cover.innerHTML = song.coverUrl ? `<img src="${escapeHtml(song.coverUrl)}" alt="">` : '♪'
  if (typeof song.lyric === 'string' || Array.isArray(song.wordLyrics) || song.lyricMode) {
    lrc = parseLrc(song.lyric)
    wordLyrics = Array.isArray(song.wordLyrics) ? song.wordLyrics : []
    lyricMode = song.lyricMode === 'word' && wordLyrics.length ? 'word' : (lrc.length ? 'line' : 'none')
  }
}

function renderList(el, songs, actions) {
  if (!songs.length) {
    el.innerHTML = '<div class="item"><div class="item-title">暂无歌曲</div></div>'
    return
  }
  el.innerHTML = songs
    .map((song, index) => `
      <div class="item">
        <div>
          <div class="item-title">${index + 1}. ${escapeHtml(song.title)}</div>
          <div class="item-meta">${escapeHtml(song.artist || '')} · ${escapeHtml(song.source || '')}${song.cacheStatus ? ` · ${escapeHtml(song.cacheStatus)}` : ''}</div>
        </div>
        <div class="item-actions">${actions(song)}</div>
      </div>
    `)
    .join('')
}

function renderSystem(system, player) {
  const login = state?.config?.music?.login
  const rows = [
    ['运行时间', `${system.uptimeSeconds}s`],
    ['Node', system.node],
    ['平台', system.platform],
    ['内存 RSS', `${system.rssMb} MB`],
    ['堆内存', `${system.heapUsedMb} MB`],
    ['队列', system.queueLength],
    ['空闲列表', system.idleLength],
    ['预取缓存', system.preloading ? '运行中' : '空闲'],
    ['空闲下一首', system.idleNext || '未准备'],
    ['播放器', player?.available ? 'mpv 已连接' : `不可用 ${player?.error || ''}`],
    ['输出设备', player?.device || 'auto'],
    ['网易云账号', login ? `${login.nickname || login.userId} · VIP ${login.vipType || 0}` : '未登录'],
  ]
  systemEl.innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${escapeHtml(v)}</dd>`).join('')
}

function applyState(nextState) {
  if (!acceptStateSync(nextState)) return
  state = {
    ...(state || {}),
    ...nextState,
    queue: Array.isArray(nextState.queue) ? nextState.queue : (state?.queue || []),
    idleList: Array.isArray(nextState.idleList) ? nextState.idleList : (state?.idleList || []),
  }
  renderSong(state.current)
  volume.value = Math.round(state.playback.volume || state.player?.volume || 80)
  renderPlayback()
  const queueKey = listKey(state.queue)
  if (queueKey !== renderedQueueKey) {
    renderedQueueKey = queueKey
    renderList(queueEl, state.queue || [], () => '')
  }
  const idleKey = listKey(state.idleList)
  if (idleKey !== renderedIdleKey) {
    renderedIdleKey = idleKey
    renderList(idleEl, state.idleList || [], (song) => `<button type="button" data-enqueue="${escapeHtml(song.uid)}">加入</button>`)
  }
  renderSystem(state.system, state.player)
  document.getElementById('queue-count').textContent = state.queue.length
  document.getElementById('idle-count').textContent = state.idleList.length
  if (state.overlay?.message) notice.textContent = state.overlay.message
}

function connectWs() {
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`)
  ws.onmessage = (event) => {
    const payload = JSON.parse(event.data)
    if (payload.type === 'state') applyState(payload.state)
  }
  ws.onclose = () => setTimeout(connectWs, 1000)
}

async function refreshDevices() {
  try {
    const result = await getJson('/api/player/devices')
    const items = [{ name: 'auto', description: 'auto' }].concat(result.devices || [])
    device.innerHTML = items.map((item) => {
      const name = item.name || item.description
      const label = item.description || item.name
      return `<option value="${escapeHtml(name)}">${escapeHtml(label)}</option>`
    }).join('')
    device.value = result.selected || 'auto'
  } catch (error) {
    device.innerHTML = '<option value="auto">mpv 未就绪</option>'
    notice.textContent = error.message
  }
}

document.getElementById('play').addEventListener('click', () => post('/api/control/play').catch((error) => notice.textContent = error.message))
document.getElementById('pause').addEventListener('click', () => post('/api/control/pause').catch((error) => notice.textContent = error.message))
document.getElementById('next').addEventListener('click', () => post('/api/control/next').catch((error) => notice.textContent = error.message))
document.getElementById('refresh-devices').addEventListener('click', refreshDevices)

volume.addEventListener('change', () => {
  post('/api/control/volume', { volume: Number(volume.value) }).catch((error) => notice.textContent = error.message)
})

device.addEventListener('change', () => {
  post('/api/player/device', { device: device.value }).catch((error) => notice.textContent = error.message)
})

seek.addEventListener('input', () => {
  seeking = true
})

seek.addEventListener('change', () => {
  const duration = state?.playback?.duration || state?.current?.duration || 0
  const position = duration ? (Number(seek.value) / 1000) * duration : 0
  seeking = false
  post('/api/control/seek', { position }).catch((error) => notice.textContent = error.message)
})

document.getElementById('queue-playlist').addEventListener('click', () => {
  const id = document.getElementById('playlist-id').value.trim()
  post('/api/queue/playlist', {
    id,
    user: { userId: 'host', nickname: '主播' },
  })
    .then((result) => notice.textContent = `已添加到队列：${result.result.added} 首`)
    .catch((error) => notice.textContent = error.message)
})

document.getElementById('import-playlist').addEventListener('click', () => {
  const id = document.getElementById('playlist-id').value.trim()
  post('/api/idle/import/playlist', { id })
    .then((result) => notice.textContent = `已加入空闲列表：${result.result.imported} 首，总计 ${result.result.total} 首`)
    .catch((error) => notice.textContent = error.message)
})

document.getElementById('import-local').addEventListener('click', () => {
  const directory = document.getElementById('local-dir').value.trim()
  post('/api/idle/import/local', { directory, recursive: true })
    .then((result) => notice.textContent = `已加入本地目录：${result.result.imported} 首，总计 ${result.result.total} 首`)
    .catch((error) => notice.textContent = error.message)
})

document.getElementById('login-qr').addEventListener('click', async () => {
  try {
    const qr = await getJson('/api/login/qr')
    document.getElementById('qr-box').innerHTML = `<img class="qr" src="${escapeHtml(qr.qrimg)}" alt="login qr">`
    clearInterval(qrTimer)
    qrTimer = setInterval(async () => {
      try {
        const status = await getJson(`/api/login/qr/check?key=${encodeURIComponent(qr.key)}`)
        if (status.saved || status.hasMusicU) {
          clearInterval(qrTimer)
          notice.textContent = '登录成功'
          document.getElementById('qr-box').innerHTML = ''
        } else if (status.code === 800) {
          clearInterval(qrTimer)
          notice.textContent = '二维码已过期，请重新获取'
        } else if (status.message) {
          notice.textContent = status.message
        }
      } catch (error) {
        notice.textContent = error.message
      }
    }, 2500)
  } catch (error) {
    notice.textContent = error.message
  }
})

document.getElementById('save-cookie').addEventListener('click', () => {
  post('/api/login/cookie', { cookie: document.getElementById('cookie').value.trim() })
    .then((result) => notice.textContent = `登录成功：${result.nickname || result.userId || ''}`)
    .catch((error) => notice.textContent = error.message)
})

document.getElementById('login-status').addEventListener('click', () => {
  getJson('/api/login/status')
    .then((status) => notice.textContent = status.valid ? `已登录：${status.nickname || status.userId || ''} · VIP ${status.vipType || 0}` : status.message)
    .catch((error) => notice.textContent = error.message)
})

document.getElementById('login-refresh').addEventListener('click', () => {
  post('/api/login/refresh')
    .then((status) => notice.textContent = `登录已刷新：${status.nickname || status.userId || ''}`)
    .catch((error) => notice.textContent = error.message)
})

document.getElementById('logout').addEventListener('click', () => {
  post('/api/login/logout')
    .then(() => notice.textContent = '已退出登录')
    .catch((error) => notice.textContent = error.message)
})

idleEl.addEventListener('click', (event) => {
  const uid = event.target?.dataset?.enqueue
  if (!uid) return
  post('/api/queue/idle', {
    uid,
    user: { userId: 'host', nickname: '主播' },
  }).catch((error) => notice.textContent = error.message)
})

fetch('/api/state').then((res) => res.json()).then(applyState)
connectWs()
refreshDevices()
requestAnimationFrame(animatePlayback)
