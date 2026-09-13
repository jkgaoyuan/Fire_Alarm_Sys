/**
 * 认证 API 请求形状测试（3.1）
 *
 * 后端契约见 backend/app/api/v1/auth.py（prefix `/auth`）。
 * refresh 走 HttpOnly Cookie，必须带 withCredentials；
 * logout 用 Authorization 头（由 request 拦截器统一附加），不带 body。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/request', () => {
  const requestMock = vi.fn()
  return { default: requestMock }
})

import request from '@/utils/request'
import { login, refresh, logout } from '../auth'

const requestMock = request

describe('api/auth.js', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    requestMock.mockResolvedValue({ code: 200, data: {} })
  })

  it('login 调用 POST /auth/login 并把凭据放在 body', async () => {
    const payload = { username: 'admin', password: 'Admin1234' }
    await login(payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/auth/login',
      method: 'post',
      data: payload,
    })
  })

  it('refresh 调用 POST /auth/refresh 且声明 withCredentials', async () => {
    await refresh()
    expect(requestMock).toHaveBeenCalledWith({
      url: '/auth/refresh',
      method: 'post',
      withCredentials: true,
    })
  })

  it('logout 调用 POST /auth/logout 且不带 body', async () => {
    await logout()
    expect(requestMock).toHaveBeenCalledWith({
      url: '/auth/logout',
      method: 'post',
    })
    expect(requestMock.mock.calls[0][0].data).toBeUndefined()
  })
})
