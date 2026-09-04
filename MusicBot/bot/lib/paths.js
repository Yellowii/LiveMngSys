const path = require('path')

const rootDir = path.resolve(__dirname, '..', '..')
const botDir = path.join(rootDir, 'bot')
const publicDir = path.join(rootDir, 'UI', 'html')
const cacheDir = path.join(rootDir, 'Cache')
const dataDir = path.join(cacheDir, 'Data')
const lyricDir = path.join(cacheDir, 'Lyric')
const coverDir = path.join(cacheDir, 'Cover')
const musicDir = path.join(cacheDir, 'Music')
const apiDir = path.join(rootDir, 'api-enhanced-main')

module.exports = {
  rootDir,
  botDir,
  publicDir,
  cacheDir,
  dataDir,
  lyricDir,
  coverDir,
  musicDir,
  apiDir,
}
