/**
 * 报警中心 API 请求形状测试（3.3）
 *
 * 后端契约见 backend/app/api/v1/alarms.py（router prefix `/alarms`）。
 * 消音是不带 body 的 POST —— 断言它「没有 body」同样重要。
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
  getAlarms,
  getAlarm,
  confirmAlarm,
  silenceAlarm,
  resetAlarm,
} from '../alarm'

const requestMock = request

describe('api/alarm.js', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    requestMock.mockResolvedValue({ code: 200, data: {} })
  })

  it('getAlarms 调用 GET /alarms 并把 9 个筛选键放在 query', async () => {
    const params = {
      page: 1,
      page_size: 20,
      alarm_type: 'fire',
      alarm_level: 'critical',
      status: 'pending',
      org_id: 21,
      device_id: 1,
      start: '2026-09-01',
      end: '2026-09-10',
    }
    await getAlarms(params)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/alarms',
      method: 'get',
      params,
    })
  })

  it('getAlarm 调用 GET /alarms/:id', async () => {
    await getAlarm(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/alarms/1',
      method: 'get',
    })
  })

  it('confirmAlarm 调用 POST /alarms/:id/confirm 并把确认结果放在 body', async () => {
    const payload = { confirm_result: 'real', false_reason: null }
    await confirmAlarm(1, payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/alarms/1/confirm',
      method: 'post',
      data: payload,
    })
  })

  it('silenceAlarm 调用 POST /alarms/:id/silence 且不带 body', async () => {
    await silenceAlarm(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/alarms/1/silence',
      method: 'post',
    })
    // 消音是幂等的无参 POST，多带 body 会与后端签名不符
    expect(requestMock.mock.calls[0][0].data).toBeUndefined()
  })

  it('resetAlarm 调用 POST /alarms/:id/reset 并携带 physical_restored 与 remark', async () => {
    const payload = { physical_restored: true, remark: '现场已恢复' }
    await resetAlarm(1, payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/alarms/1/reset',
      method: 'post',
      data: payload,
    })
  })
})
