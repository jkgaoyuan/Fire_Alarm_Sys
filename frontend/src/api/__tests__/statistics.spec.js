/**
 * 统计报表 API 请求形状测试（3.9）
 *
 * 后端契约见 backend/app/api/v1/statistics.py（prefix `/statistics`）。
 * 这 5 个端点全部是 query 筛选，没有一个接受 body。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/request', () => {
  const requestMock = vi.fn()
  return { default: requestMock }
})

import request from '@/utils/request'
import {
  getStatisticsOverview,
  getDeviceStatusStats,
  getAlarmTrend,
  getFaultTop10,
  getInspectionCompletion,
} from '../statistics'

const requestMock = request

describe('api/statistics.js', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    requestMock.mockResolvedValue({ code: 200, data: {} })
  })

  it('getStatisticsOverview 调用 GET /statistics/overview', async () => {
    await getStatisticsOverview({ org_id: 21 })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/statistics/overview',
      method: 'get',
      params: { org_id: 21 },
    })
  })

  it('getDeviceStatusStats 调用 GET /statistics/device-status 并携带 include_drill', async () => {
    const params = { org_id: 21, include_drill: false }
    await getDeviceStatusStats(params)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/statistics/device-status',
      method: 'get',
      params,
    })
  })

  it('getAlarmTrend 调用 GET /statistics/alarm-trend 并携带天数与时间范围', async () => {
    const params = { days: 30, org_id: 21, start: '2026-09-01', end: '2026-09-13' }
    await getAlarmTrend(params)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/statistics/alarm-trend',
      method: 'get',
      params,
    })
  })

  it('getFaultTop10 调用 GET /statistics/fault-top10', async () => {
    await getFaultTop10({ org_id: 21 })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/statistics/fault-top10',
      method: 'get',
      params: { org_id: 21 },
    })
  })

  it('getInspectionCompletion 调用 GET /statistics/inspection-completion', async () => {
    await getInspectionCompletion({ start: '2026-09-01', end: '2026-09-13' })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/statistics/inspection-completion',
      method: 'get',
      params: { start: '2026-09-01', end: '2026-09-13' },
    })
  })
})
