const fs = require('fs')
const path = require('path')
const { dataDir } = require('./paths')

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true })
}

function readJson(file, fallback) {
  try {
    if (!fs.existsSync(file)) return fallback
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch (error) {
    console.error(`Failed to read ${file}:`, error.message)
    return fallback
  }
}

function writeJson(file, value) {
  ensureDir(path.dirname(file))
  const tmp = `${file}.tmp`
  fs.writeFileSync(tmp, JSON.stringify(value, null, 2), 'utf8')
  fs.renameSync(tmp, file)
}

function createStore() {
  ensureDir(dataDir)
  const configFile = path.join(dataDir, 'config.json')
  const stateFile = path.join(dataDir, 'state.json')
  const defaultConfig = readJson(
    path.join(__dirname, '..', 'config.default.json'),
    {},
  )

  const config = {
    ...defaultConfig,
    ...readJson(configFile, {}),
    server: {
      ...defaultConfig.server,
      ...readJson(configFile, {}).server,
    },
    queue: {
      ...defaultConfig.queue,
      ...readJson(configFile, {}).queue,
    },
    music: {
      ...defaultConfig.music,
      ...readJson(configFile, {}).music,
    },
    player: {
      ...defaultConfig.player,
      ...readJson(configFile, {}).player,
    },
    display: {
      ...defaultConfig.display,
      ...readJson(configFile, {}).display,
    },
    permissions: {
      ...defaultConfig.permissions,
      ...readJson(configFile, {}).permissions,
    },
    points: {
      ...defaultConfig.points,
      ...readJson(configFile, {}).points,
    },
    audioNormalization: {
      ...defaultConfig.audioNormalization,
      ...readJson(configFile, {}).audioNormalization,
    },
    soundpad: {
      ...defaultConfig.soundpad,
      ...readJson(configFile, {}).soundpad,
    },
    commands: {
      ...defaultConfig.commands,
      ...readJson(configFile, {}).commands,
    },
    controls: {
      ...defaultConfig.controls,
      ...readJson(configFile, {}).controls,
    },
  }

  // Migrate the previous built-in shortcut defaults without overwriting user customizations.
  if (
    config.controls.previousHotkey === 'Alt+ArrowLeft' &&
    config.controls.playPauseHotkey === 'Space' &&
    config.controls.nextHotkey === 'Alt+ArrowRight'
  ) {
    config.controls = { ...config.controls, ...defaultConfig.controls }
  }

  const state = {
    users: {},
    blacklist: [],
    titleFilters: [],
    idleList: [],
    ...readJson(stateFile, {}),
  }

  writeJson(configFile, config)
  writeJson(stateFile, state)

  return {
    config,
    state,
    saveConfig() {
      writeJson(configFile, config)
    },
    saveState() {
      writeJson(stateFile, state)
    },
  }
}

module.exports = { createStore, ensureDir, readJson, writeJson }
