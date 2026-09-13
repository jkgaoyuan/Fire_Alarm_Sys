/**
 * 登录日志审计 API 请求形状测试（P1-003）
 *
 * 后端契约见 backend/app/api/v1/login_logs.py（prefix `/login-logs`）。
 * 全部筛选走 query：username / status / start_time / end_time。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/request', () => {
  const requestMock = vi.fn()
  return { default: requestMock }
})

import request from '@/utils/request'
import { getLoginLogs } from '../loginLog'

const requestMock = request

describe('api/loginLog.js', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    requestMock.mockResolvedValue({ code: 200, data: {} })
  })

  it('getLoginLogs 调用 GET /login-logs 并把 6 个筛选键放在 query', async () => {
    const params = {
      page: 1,
      page_size: 20,
      username: 'admin',
      status: 'success',
      start_time: '2026-09-01T00:00:00',
      end_time: '2026-09-13T23:59:59',
    }
    await getLoginLogs(params)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/login-logs',
      method: 'get',
      params,
    })
  })
})
