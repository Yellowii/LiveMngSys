const fs = require('fs')
const path = require('path')
const crypto = require('crypto')
const { apiDir } = require('./paths')
const { hasMusicU } = require('./authService')

const api = require(path.join(apiDir, 'main.js'))
let unblockCacheGroup = null

function unblockCaches() {
  if (unblockCacheGroup) return unblockCacheGroup
  try {
    const { CacheStorageGroup } = require('@unblockneteasemusic/server/src/cache')
    unblockCacheGroup = CacheStorageGroup.getInstance()
  } catch {
    unblockCacheGroup = null
  }
  return unblockCacheGroup
}

function compactExternalCaches(maxAliveMs = 5 * 60 * 1000, maxEntries = 200) {
  const group = unblockCaches()
  if (!group) return { storages: 0, entriesBefore: 0, entriesAfter: 0 }
  let storages = 0
  let entriesBefore = 0
  let entriesAfter = 0
  const entryLimit = Math.max(20, Number(maxEntries) || 200)
  for (const storage of group.cacheStorages || []) {
    storages += 1
    entriesBefore += storage.cacheMap?.size || 0
    if (storage.aliveDuration > maxAliveMs) storage.aliveDuration = maxAliveMs
    storage.removeExpiredCache()
    if (storage.cacheMap?.size > entryLimit) {
      const overflow = storage.cacheMap.size - entryLimit
      let removed = 0
      for (const key of storage.cacheMap.keys()) {
        storage.cacheMap.delete(key)
        removed += 1
        if (removed >= overflow) break
      }
    }
    entriesAfter += storage.cacheMap?.size || 0
  }
  return { storages, entriesBefore, entriesAfter }
}

function withTimeout(promise, ms, label) {
  let timer
  return Promise.race([
    promise.finally(() => clearTimeout(timer)),
    new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`${label} timeout`)), ms)
      timer.unref?.()
    }),
  ])
}

function normalizeKeyword(value) {
  return String(value || '')
    .trim()
    .replace(/[!"#$%&'()*+,./:;<=>?@[\\\]^_`{|}~\uFF0C\u3002\uFF01\uFF1F\u3001\uFF1B\uFF1A\u201C\u201D\u2018\u2019\uFF08\uFF09\u3010\u3011\u300A\u300B]/g, ' ')
    .replace(/\s+/g, ' ')
}

function artistText(song) {
  const artists = song.ar || song.artists || []
  if (!Array.isArray(artists) || artists.length === 0) return '\u672A\u77E5\u6B4C\u624B'
  return artists.map((item) => item.name).filter(Boolean).join(' / ')
}

function albumText(song) {
  return song.al?.name || song.album?.name || ''
}

function coverText(song) {
  return song.al?.picUrl || song.album?.picUrl || ''
}

function neteaseCookie(config) {
  return config.music.neteaseCookie || process.env.NETEASE_COOKIE || ''
}

function hasLoginCookie(config) {
  return hasMusicU(neteaseCookie(config))
}

function extractNeteaseId(value) {
  const text = String(value || '').trim()
  const idFromQuery = text.match(/[?&]id=(\d+)/)
  if (idFromQuery) return idFromQuery[1]
  const plain = text.match(/\d{5,}/)
  return plain ? plain[0] : ''
}

function toNeteaseSong(song, extra = {}) {
  const durationMs = Number(song.dt || song.duration || 0)
  return {
    uid: `netease:${song.id}`,
    source: 'netease',
    sourceId: String(song.id),
    title: song.name || `Song ${song.id}`,
    artist: artistText(song),
    album: albumText(song),
    duration: durationMs ? Math.round(durationMs / 1000) : 0,
    coverUrl: coverText(song),
    lyric: '',
    yrc: '',
    lyricMode: 'none',
    wordLyrics: [],
    url: '',
    playbackSource: '',
    ...extra,
  }
}

async function searchNetease(keyword, config, limit = 5) {
  const keywords = normalizeKeyword(keyword)
  if (!keywords) return []
  const response = await withTimeout(
    api.cloudsearch({
      keywords,
      type: 1,
      limit,
      cookie: neteaseCookie(config),
    }),
    10000,
    'netease search',
  )
  return response.body?.result?.songs || []
}

async function getNeteaseById(id, config) {
  const response = await withTimeout(
    api.song_detail({
      ids: String(id),
      cookie: neteaseCookie(config),
    }),
    10000,
    'netease song detail',
  )
  return response.body?.songs?.[0] || null
}

function isTrialUrl(data, songDurationSeconds) {
  if (!data || !data.url) return true
  if (
    data.freeTrialInfo &&
    data.freeTrialInfo !== 'null' &&
    data.freeTrialInfo !== 'undefined'
  ) {
    return true
  }
  const reportedMs = Number(data.time || data.expi || 0)
  if (reportedMs > 0 && songDurationSeconds > 90 && reportedMs < 60000) return true
  return false
}

async function directUrl(id, config) {
  if (api.song_url_v1) {
    const v1 = await withTimeout(
      api.song_url_v1({
        id: String(id),
        level: config.music.level || 'standard',
        cookie: neteaseCookie(config),
      }),
      12000,
      'netease url',
    ).catch(() => null)
    const item = v1?.body?.data?.[0]
    if (item?.url) return item
  }

  const response = await withTimeout(
    api.song_url({
      id: String(id),
      br: config.music.bitrate || 320000,
      cookie: neteaseCookie(config),
    }),
    12000,
    'netease url',
  )
  return response.body?.data?.[0] || null
}

async function unblockUrl(id, config) {
  if (!api.song_url_v1) return null
  const response = await withTimeout(
    api.song_url_v1({
      id: String(id),
      level: config.music.level || 'standard',
      unblock: 'true',
      cookie: neteaseCookie(config),
    }),
    22000,
    'unblock url',
  ).catch(() => null)
  return response?.body?.data?.[0] || null
}

async function getNeteaseUrl(id, config, durationSeconds = 0) {
  const primary = await directUrl(id, config).catch(() => null)
  if (primary?.url && !isTrialUrl(primary, durationSeconds)) {
    return {
      url: primary.url,
      source: hasLoginCookie(config) ? 'netease-account' : 'netease',
      trial: false,
    }
  }

  if (config.music.enableUnblock !== false) {
    const fallback = await unblockUrl(id, config)
    if (fallback?.url && !isTrialUrl(fallback, durationSeconds)) {
      const source = /music\.126\.net|126\.net/.test(fallback.url)
        ? 'netease'
        : (fallback.source || 'unblock')
      return { url: fallback.url, source, trial: false }
    }
  }

  return {
    url: '',
    source: primary?.url ? 'trial-rejected' : 'none',
    trial: Boolean(primary?.url),
  }
}

async function getLyric(id, config) {
  const query = {
    id: String(id),
    cookie: neteaseCookie(config),
  }
  const response = await withTimeout(
    api.lyric_new
      ? api.lyric_new(query).catch(() => api.lyric(query))
      : api.lyric(query),
    10000,
    'netease lyric',
  )
  const body = response.body || {}
  const lrc = normalizeLrc(body.lrc?.lyric || '')
  const yrc = body.yrc?.lyric || ''
  const wordLyrics = parseYrc(yrc)
  const lyricMode = wordLyrics.length > 0 ? 'word' : (lrc ? 'line' : 'none')
  console.log(`[LYRIC] song=${id} mode=${lyricMode} yrcLines=${wordLyrics.length} lrc=${lrc ? 'yes' : 'no'}`)
  return {
    lyric: lrc,
    yrc: '',
    lyricMode,
    wordLyrics,
  }
}

function normalizeLrc(text) {
  return String(text || '')
    .split(/\r?\n/)
    .filter((line) => /^\[\d+:\d+(?:\.\d+)?\]/.test(line.trim()))
    .join('\n')
}

function parseYrc(text) {
  return String(text || '')
    .split(/\r?\n/)
    .map((line) => {
      const match = line.match(/^\[(\d+),(\d+)\](.+)$/)
      if (!match) return null
      const startMs = Number(match[1])
      const durationMs = Number(match[2])
      const content = match[3]
      const words = []
      const tokenRe = /\((\d+),(\d+),(-?\d+)\)([^()]*)/g
      let token
      while ((token = tokenRe.exec(content))) {
        const textPart = token[4] || ''
        if (!textPart) continue
        words.push({
          start: Number(token[1]) / 1000,
          duration: Number(token[2]) / 1000,
          text: textPart,
        })
      }
      if (words.length === 0) return null
      return {
        time: startMs / 1000,
        duration: durationMs / 1000,
        text: words.map((word) => word.text).join(''),
        words,
      }
    })
    .filter(Boolean)
}

async function resolveNeteaseSong(query, config) {
  const isId = /^\d+$/.test(String(query).trim())
  const candidates = isId
    ? [await getNeteaseById(query, config)]
    : await searchNetease(query, config, 3)

  const songs = candidates.filter(Boolean).map((candidate) => toNeteaseSong(candidate))
  if (songs.length === 0) {
    const error = new Error('\u672A\u627E\u5230\u8BE5\u6B4C\u66F2')
    error.status = 404
    throw error
  }

  let selected = null
  let selectedPlayback = null

  for (const song of songs) {
    const playback = await directUrl(song.sourceId, config)
      .then((item) => item?.url && !isTrialUrl(item, song.duration)
        ? {
            url: item.url,
            source: hasLoginCookie(config) ? 'netease-account' : 'netease',
            trial: false,
          }
        : null)
      .catch(() => null)
    if (playback) {
      selected = song
      selectedPlayback = playback
      break
    }
  }

  if (!selected) {
    for (const song of songs) {
      const playback = await getNeteaseUrl(song.sourceId, config, song.duration)
      if (playback.url) {
        selected = song
        selectedPlayback = playback
        break
      }
    }
  }

  if (!selected || !selectedPlayback?.url) {
    const error = new Error(
      selectedPlayback?.trial
        ? '\u53EA\u83B7\u53D6\u5230\u8BD5\u542C\u7247\u6BB5\uFF0C\u5DF2\u62D2\u7EDD\u52A0\u5165\u961F\u5217'
        : '\u8BE5\u6B4C\u66F2\u6682\u4E0D\u53EF\u64AD\u653E',
    )
    error.status = 409
    throw error
  }

  selected.url = selectedPlayback.url
  selected.playbackSource = selectedPlayback.source
  const lyricData = await getLyric(selected.sourceId, config).catch(() => ({
    lyric: '',
    yrc: '',
    lyricMode: 'none',
    wordLyrics: [],
  }))
  Object.assign(selected, lyricData)
  return selected
}

async function resolveNeteaseMetadata(query, config) {
  const value = String(query).trim()
  const candidates = /^\d+$/.test(value)
    ? [await getNeteaseById(value, config)]
    : await searchNetease(value, config, 1)
  const candidate = candidates.find(Boolean)
  if (!candidate) {
    const error = new Error('\u672A\u627E\u5230\u8BE5\u6B4C\u66F2')
    error.status = 404
    throw error
  }
  return toNeteaseSong(candidate)
}

async function importNeteasePlaylist(playlistId, config, limit) {
  const id = extractNeteaseId(playlistId)
  if (!id) {
    const error = new Error('\u8BF7\u8F93\u5165\u6B4C\u5355 ID \u6216\u94FE\u63A5')
    error.status = 400
    throw error
  }
  const response = await withTimeout(
    api.playlist_track_all({
      id,
      limit: limit || config.music.defaultPlaylistLimit || 200,
      cookie: neteaseCookie(config),
    }),
    20000,
    'netease playlist',
  )
  const songs = response.body?.songs || []
  return songs.map((song) => toNeteaseSong(song, { url: '', lyric: '' }))
}

async function getNeteasePlaylistMeta(playlistId, config) {
  const id = extractNeteaseId(playlistId)
  if (!id) {
    const error = new Error('\u8BF7\u8F93\u5165\u6B4C\u5355 ID \u6216\u94FE\u63A5')
    error.status = 400
    throw error
  }
  const response = await withTimeout(
    api.playlist_detail({ id, cookie: neteaseCookie(config) }),
    10000,
    'netease playlist metadata',
  )
  const playlist = response.body?.playlist || {}
  return {
    id: String(id),
    name: playlist.name || `网易云歌单 ${id}`,
    coverUrl: playlist.coverImgUrl || playlist.coverImgUrl_str || '',
  }
}

function hashPath(file) {
  return crypto.createHash('sha1').update(path.resolve(file)).digest('hex').slice(0, 16)
}

function parseLocalName(file) {
  const basename = path.basename(file, path.extname(file))
  const parts = basename.split(/\s+-\s+|\s+\u2013\s+/)
  if (parts.length >= 2) {
    return {
      artist: parts[0].trim() || '\u672C\u5730\u97F3\u4E50',
      title: parts.slice(1).join(' - ').trim() || basename,
    }
  }
  return { artist: '\u672C\u5730\u97F3\u4E50', title: basename }
}

function scanFiles(dir, recursive, extensions, output = []) {
  for (const item of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, item.name)
    if (item.isDirectory() && recursive) {
      scanFiles(fullPath, recursive, extensions, output)
      continue
    }
    if (!item.isFile()) continue
    const ext = path.extname(item.name).toLowerCase()
    if (extensions.includes(ext)) output.push(fullPath)
  }
  return output
}

function readLocalLyric(file) {
  const lrc = path.join(path.dirname(file), `${path.basename(file, path.extname(file))}.lrc`)
  if (!fs.existsSync(lrc)) return ''
  return fs.readFileSync(lrc, 'utf8')
}

function localSongFromFile(file) {
  const stat = fs.statSync(file)
  const parsed = parseLocalName(file)
  const id = hashPath(file)
  const filePath = path.resolve(file)
  return {
    uid: `local:${id}`,
    source: 'local',
    sourceId: id,
    title: parsed.title,
    artist: parsed.artist,
    album: '\u672C\u5730\u6B4C\u66F2',
    duration: 0,
    coverUrl: '',
    lyric: readLocalLyric(file),
    yrc: '',
    lyricMode: 'line',
    wordLyrics: [],
    url: filePath,
    filePath,
    size: stat.size,
    mtimeMs: stat.mtimeMs,
    playbackSource: 'local',
  }
}

function importLocalDirectory(directory, config, recursive = true) {
  const resolved = path.resolve(directory)
  if (!fs.existsSync(resolved) || !fs.statSync(resolved).isDirectory()) {
    const error = new Error('\u672C\u5730\u6B4C\u66F2\u76EE\u5F55\u4E0D\u5B58\u5728')
    error.status = 404
    throw error
  }
  const extensions = (config.music.localExtensions || []).map((item) => item.toLowerCase())
  return scanFiles(resolved, recursive, extensions).map(localSongFromFile)
}

async function preparePlaybackSong(song, config, options = {}) {
  if (song.source === 'local') return song
  const playbackConfig = options.allowUnblock === false
    ? { ...config, music: { ...config.music, enableUnblock: false } }
    : config
  const [playback, lyric] = await Promise.all([
    getNeteaseUrl(song.sourceId, playbackConfig, song.duration),
    song.lyricMode && song.lyricMode !== 'none'
      ? Promise.resolve({
          lyric: song.lyric || '',
          yrc: song.yrc || '',
          lyricMode: song.lyricMode,
          wordLyrics: song.wordLyrics || [],
        })
      : getLyric(song.sourceId, config).catch(() => ({
          lyric: '',
          yrc: '',
          lyricMode: 'none',
          wordLyrics: [],
        })),
  ])
  if (!playback.url) {
    const error = new Error('\u65E0\u6CD5\u83B7\u53D6\u5B8C\u6574\u64AD\u653E\u5730\u5740')
    error.status = 409
    throw error
  }
  return {
    ...song,
    url: playback.url,
    playbackSource: playback.source,
    ...lyric,
  }
}

module.exports = {
  normalizeKeyword,
  withTimeout,
  extractNeteaseId,
  hasLoginCookie,
  compactExternalCaches,
  parseYrc,
  resolveNeteaseMetadata,
  resolveNeteaseSong,
  importNeteasePlaylist,
  getNeteasePlaylistMeta,
  importLocalDirectory,
  preparePlaybackSong,
  localSongFromFile,
}
