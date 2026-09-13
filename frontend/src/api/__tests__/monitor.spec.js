/**
 * 实时监控 API 请求形状测试（3.3）
 *
 * 后端契约见 backend/app/api/v1/monitor.py（router prefix `/monitor`）。
 * 注意 `/monitor/map` 的 org_id 是**必填 query**，调用方必须保证非空。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/request', () => {
  const requestMock = vi.fn()
  return {
    default: requestMock,
  }
})

import request from '@/utils/request'
import {
  getDashboard,
  getRecentAlarms,
  getMapMeta,
  getMapDevices,
  createWsTicket,
} from '../monitor'

const requestMock = request

describe('api/monitor.js', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    requestMock.mockResolvedValue({ code: 200, data: {} })
  })

  it('getDashboard 调用 GET /monitor/dashboard 并把 org_id 放在 query', async () => {
    await getDashboard({ org_id: 21 })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/monitor/dashboard',
      method: 'get',
      params: { org_id: 21 },
    })
  })

  it('getRecentAlarms 调用 GET /monitor/alarms/recent 并携带 limit/org_id/include_drill', async () => {
    const params = { limit: 20, org_id: 21, include_drill: false }
    await getRecentAlarms(params)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/monitor/alarms/recent',
      method: 'get',
      params,
    })
  })

  it('getMapMeta 调用 GET /monitor/map 并把 org_id 包成 query 对象', async () => {
    await getMapMeta(21)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/monitor/map',
      method: 'get',
      params: { org_id: 21 },
    })
  })

  it('getMapDevices 调用 GET /monitor/map/devices 并携带视口 bbox', async () => {
    const params = { org_id: 21, bbox: '0,0,100,100', limit: 500 }
    await getMapDevices(params)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/monitor/map/devices',
      method: 'get',
      params,
    })
  })

  it('createWsTicket 调用 POST /monitor/ws-ticket 且不带 body', async () => {
    await createWsTicket()
    expect(requestMock).toHaveBeenCalledWith({
      url: '/monitor/ws-ticket',
      method: 'post',
    })
    expect(requestMock.mock.calls[0][0].data).toBeUndefined()
  })
})
