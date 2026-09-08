// Access Token 管理（仅 localStorage，不处理 Refresh Token，由后端 httpOnly Cookie 管理）

const TOKEN_KEY = 'fire_alarm_access_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function removeToken() {
  localStorage.removeItem(TOKEN_KEY)
}

/**
 * 解析 JWT 的 exp 字段（单位：秒）
 */
export function getTokenExpiry(token) {
  if (!token) return null
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.exp || null
  } catch {
    return null
  }
}

/**
 * 判断 Token 是否即将过期
 * @param {string} token
 * @param {number} thresholdSeconds 阈值（默认 300 秒 = 5 分钟）
 */
export function isTokenExpiringSoon(token, thresholdSeconds = 300) {
  const exp = getTokenExpiry(token)
  if (!exp) return true
  const now = Math.floor(Date.now() / 1000)
  return exp - now < thresholdSeconds
}

/**
 * 清除所有认证状态
 */
export function clearAuth() {
  removeToken()
}
