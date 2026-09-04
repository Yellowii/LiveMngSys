function normalizeCookie(value) {
  if (!value) return ''
  if (Array.isArray(value)) return value.filter(Boolean).join('; ')
  return String(value || '').trim()
}

function hasMusicU(cookie) {
  return /(?:^|;\s*)MUSIC_U=/.test(normalizeCookie(cookie))
}

function hasCsrf(cookie) {
  return /(?:^|;\s*)__csrf=/.test(normalizeCookie(cookie))
}

function mergeCookies(...values) {
  const map = new Map()
  for (const value of values) {
    const cookie = normalizeCookie(value)
    if (!cookie) continue
    for (const part of cookie.split(/;\s*/)) {
      const index = part.indexOf('=')
      if (index <= 0) continue
      const key = part.slice(0, index).trim()
      const val = part.slice(index + 1).trim()
      if (!key || /^(Path|Expires|Max-Age|Domain|SameSite|Secure|HttpOnly)$/i.test(key)) continue
      map.set(key, val)
    }
  }
  return Array.from(map.entries()).map(([key, val]) => `${key}=${val}`).join('; ')
}

function cookieFromLoginResult(result) {
  return mergeCookies(
    result?.body?.cookie,
    result?.cookie,
    result?.body?.data?.cookie,
  )
}

async function validateLoginCookie(api, cookie, timeout) {
  const normalized = normalizeCookie(cookie)
  if (!hasMusicU(normalized)) {
    return {
      valid: false,
      hasCookie: Boolean(normalized),
      hasMusicU: false,
      message: 'Cookie 缺少 MUSIC_U',
    }
  }

  const result = await timeout(
    api.login_status({ cookie: normalized }),
    10000,
    'login status',
  )
  const data = result.body?.data || result.body || {}
  const profile = data.profile || null
  const account = data.account || null
  const valid = Boolean(profile || (account && account.anonimousUser !== true))
  return {
    valid,
    hasCookie: true,
    hasMusicU: true,
    hasCsrf: hasCsrf(normalized),
    profile,
    account,
    vipType: profile?.vipType ?? account?.vipType ?? 0,
    nickname: profile?.nickname || account?.userName || '',
    userId: profile?.userId || account?.id || 0,
    message: valid ? '登录有效' : 'Cookie 未通过登录状态校验',
    raw: result.body,
  }
}

module.exports = {
  normalizeCookie,
  hasMusicU,
  hasCsrf,
  mergeCookies,
  cookieFromLoginResult,
  validateLoginCookie,
}
