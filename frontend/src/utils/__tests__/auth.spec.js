import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  getToken,
  setToken,
  removeToken,
  getTokenExpiry,
  isTokenExpiringSoon,
  clearAuth,
} from '../auth'

function createMockLocalStorage() {
  let store = {}
  return {
    getItem: (key) => store[key] ?? null,
    setItem: (key, value) => { store[key] = String(value) },
    removeItem: (key) => { delete store[key] },
    clear: () => { store = {} },
  }
}

describe('auth utils', () => {
  let mockStorage

  beforeEach(() => {
    mockStorage = createMockLocalStorage()
    vi.stubGlobal('localStorage', mockStorage)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('getToken 应从 localStorage 读取', () => {
    mockStorage.setItem('fire_alarm_access_token', 'abc123')
    expect(getToken()).toBe('abc123')
  })

  it('getToken 无值时应返回 null', () => {
    expect(getToken()).toBeNull()
  })

  it('setToken 应写入 localStorage', () => {
    setToken('xyz789')
    expect(mockStorage.getItem('fire_alarm_access_token')).toBe('xyz789')
  })

  it('removeToken 应删除 localStorage 中的 token', () => {
    mockStorage.setItem('fire_alarm_access_token', 'abc')
    removeToken()
    expect(mockStorage.getItem('fire_alarm_access_token')).toBeNull()
  })

  it('getTokenExpiry 应正确解析 exp', () => {
    const payload = btoa(JSON.stringify({ exp: 1234567890 }))
    const token = `header.${payload}.signature`
    expect(getTokenExpiry(token)).toBe(1234567890)
  })

  it('getTokenExpiry 对非法 token 应返回 null', () => {
    expect(getTokenExpiry('bad-token')).toBeNull()
    expect(getTokenExpiry(null)).toBeNull()
    expect(getTokenExpiry('')).toBeNull()
  })

  it('isTokenExpiringSoon 在即将过期时应返回 true', () => {
    const exp = Math.floor(Date.now() / 1000) + 100
    const payload = btoa(JSON.stringify({ exp }))
    const token = `h.${payload}.s`
    expect(isTokenExpiringSoon(token, 300)).toBe(true)
  })

  it('isTokenExpiringSoon 在足够远时不应返回 true', () => {
    const exp = Math.floor(Date.now() / 1000) + 10000
    const payload = btoa(JSON.stringify({ exp }))
    const token = `h.${payload}.s`
    expect(isTokenExpiringSoon(token, 300)).toBe(false)
  })

  it('isTokenExpiringSoon 对非法 token 应视为即将过期', () => {
    expect(isTokenExpiringSoon('bad', 300)).toBe(true)
  })

  it('clearAuth 应清除 token', () => {
    mockStorage.setItem('fire_alarm_access_token', 'abc')
    clearAuth()
    expect(mockStorage.getItem('fire_alarm_access_token')).toBeNull()
  })
})
