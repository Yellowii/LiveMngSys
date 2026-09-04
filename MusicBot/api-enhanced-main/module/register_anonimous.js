const CryptoJS = require('crypto-js')
const crypto = require('crypto')
const path = require('path')
const fs = require('fs')
const ID_XOR_KEY_1 = '3go8&$8*3*3h0k(2)2'
const deviceIdPath = path.resolve(__dirname, '../data/deviceid.txt')
const deviceidText = fs.existsSync(deviceIdPath)
  ? fs.readFileSync(deviceIdPath, 'utf-8')
  : ''

const createOption = require('../util/option.js')
const deviceidList = deviceidText.split(/\r?\n/).map(value => value.trim()).filter(Boolean)

function getRandomFromList(list) {
  return list.length
    ? list[Math.floor(Math.random() * list.length)]
    : crypto.randomBytes(20).toString('hex')
}
function cloudmusic_dll_encode_id(some_id) {
  let xoredString = ''
  for (let i = 0; i < some_id.length; i++) {
    const charCode =
      some_id.charCodeAt(i) ^ ID_XOR_KEY_1.charCodeAt(i % ID_XOR_KEY_1.length)
    xoredString += String.fromCharCode(charCode)
  }
  const wordArray = CryptoJS.enc.Utf8.parse(xoredString)
  const digest = CryptoJS.MD5(wordArray)
  return CryptoJS.enc.Base64.stringify(digest)
}

module.exports = async (query, request) => {
  const deviceId = getRandomFromList(deviceidList)
  global.deviceId = deviceId
  const encodedId = CryptoJS.enc.Base64.stringify(
    CryptoJS.enc.Utf8.parse(
      `${deviceId} ${cloudmusic_dll_encode_id(deviceId)}`,
    ),
  )
  const data = {
    username: encodedId,
  }
  let result = await request(
    `/api/register/anonimous`,
    data,
    createOption(query, 'weapi'),
  )
  if (result.body.code === 200) {
    result = {
      status: 200,
      body: {
        ...result.body,
        cookie: result.cookie.join(';'),
      },
      cookie: result.cookie,
    }
  }
  return result
}
