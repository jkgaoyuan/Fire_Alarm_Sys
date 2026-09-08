import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '../auth'

vi.mock('@/api/auth', () => ({
  login: vi.fn(),
  logout: vi.fn(),
}))

vi.mock('@/api/user', () => ({
  getMe: vi.fn(),
}))

vi.mock('@/utils/auth', () => ({
  getToken: vi.fn(() => null),
  setToken: vi.fn(),
  removeToken: vi.fn(),
}))

import { login, logout } from '@/api/auth'
import { getMe } from '@/api/user'
import { setToken, removeToken } from '@/utils/auth'

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('初始状态应为未登录', () => {
    const store = useAuthStore()
    expect(store.isLoggedIn).toBe(false)
    expect(store.accessToken).toBeNull()
    expect(store.userInfo).toBeNull()
  })

  it('login 成功应设置 token 和用户信息', async () => {
    const store = useAuthStore()
    login.mockResolvedValue({
      data: {
        access_token: 'token123',
        user: { username: 'admin', real_name: '管理员' },
      },
    })

    const result = await store.login({ username: 'admin', password: '123' })

    expect(setToken).toHaveBeenCalledWith('token123')
    expect(store.accessToken).toBe('token123')
    expect(store.userInfo).toEqual({ username: 'admin', real_name: '管理员' })
    expect(result.access_token).toBe('token123')
  })

  it('login 响应无 access_token 应抛异常', async () => {
    const store = useAuthStore()
    login.mockResolvedValue({ data: { user: {} } })

    await expect(store.login({})).rejects.toThrow('登录响应格式异常')
  })

  it('fetchUserInfo 应更新用户信息', async () => {
    const store = useAuthStore()
    getMe.mockResolvedValue({
      data: { username: 'admin', roles: ['chief'] },
    })

    const user = await store.fetchUserInfo()

    expect(store.userInfo).toEqual({ username: 'admin', roles: ['chief'] })
    expect(user.username).toBe('admin')
  })

  it('logout 应清除所有本地状态', async () => {
    const store = useAuthStore()
    store.accessToken = 'token'
    store.userInfo = { username: 'admin' }
    logout.mockResolvedValue({})

    await store.logout()

    expect(removeToken).toHaveBeenCalled()
    expect(store.accessToken).toBeNull()
    expect(store.userInfo).toBeNull()
    expect(store.isLoggedIn).toBe(false)
  })

  it('logout 即使接口失败也清除本地状态', async () => {
    const store = useAuthStore()
    store.accessToken = 'token'
    store.userInfo = { username: 'admin' }
    logout.mockRejectedValue(new Error('network error'))

    await store.logout()

    expect(removeToken).toHaveBeenCalled()
    expect(store.accessToken).toBeNull()
    expect(store.userInfo).toBeNull()
  })
})
