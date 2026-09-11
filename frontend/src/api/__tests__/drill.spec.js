/**
 * 消防演练 API 测试
 * 3.8-B4/F1
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
  getDrills,
  createDrill,
  getDrillDetail,
  updateDrill,
  deleteDrill,
  executeDrill,
  completeDrill,
  cancelDrill,
  addDrillParticipant,
  signInDrillParticipant,
  getDrillEvaluation,
  submitDrillEvaluation,
  getDrillStatistics,
  getDrillReportHtml,
} from '../drill'

const requestMock = request

describe('api/drill.js', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('getDrills 调用 GET /drills 并携带分页与筛选参数', async () => {
    requestMock.mockResolvedValue({ data: { items: [], total: 0 } })
    await getDrills({ page: 1, page_size: 10, status_filter: 'planned', drill_type: 'evacuation' })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/drills',
      method: 'get',
      params: { page: 1, page_size: 10, status_filter: 'planned', drill_type: 'evacuation' },
    })
  })

  it('createDrill 调用 POST /drills', async () => {
    const payload = { drill_name: '演练', drill_type: 'evacuation', planned_at: '2026-09-11T10:00:00' }
    requestMock.mockResolvedValue({ data: { id: 1, drill_name: '演练' } })
    await createDrill(payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/drills',
      method: 'post',
      data: payload,
    })
  })

  it('getDrillDetail 调用 GET /drills/:id', async () => {
    requestMock.mockResolvedValue({ data: { id: 1 } })
    await getDrillDetail(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/drills/1',
      method: 'get',
    })
  })

  it('updateDrill 调用 PUT /drills/:id', async () => {
    const payload = { drill_name: '更新后' }
    requestMock.mockResolvedValue({ data: { id: 1 } })
    await updateDrill(1, payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/drills/1',
      method: 'put',
      data: payload,
    })
  })

  it('deleteDrill 调用 DELETE /drills/:id', async () => {
    requestMock.mockResolvedValue({ data: null })
    await deleteDrill(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/drills/1',
      method: 'delete',
    })
  })

  it('executeDrill 调用 POST /drills/:id/execute', async () => {
    const payload = { photos: [] }
    requestMock.mockResolvedValue({ data: { id: 1, status: 'ongoing' } })
    await executeDrill(1, payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/drills/1/execute',
      method: 'post',
      data: payload,
    })
  })

  it('completeDrill 调用 POST /drills/:id/complete 并携带总结', async () => {
    const payload = { summary: '演练顺利完成' }
    requestMock.mockResolvedValue({ data: { id: 1, status: 'completed' } })
    await completeDrill(1, payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/drills/1/complete',
      method: 'post',
      data: payload,
    })
  })

  it('cancelDrill 调用 POST /drills/:id/cancel 并携带原因', async () => {
    const payload = { reason: '天气原因' }
    requestMock.mockResolvedValue({ data: { id: 1, status: 'cancelled' } })
    await cancelDrill(1, payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/drills/1/cancel',
      method: 'post',
      data: payload,
    })
  })

  it('addDrillParticipant 调用 POST /drills/:id/participants 并通过 query 传角色', async () => {
    requestMock.mockResolvedValue({ data: { user_id: 2, role: '指挥员' } })
    await addDrillParticipant(1, { user_id: 2 }, '指挥员')
    expect(requestMock).toHaveBeenCalledWith({
      url: '/drills/1/participants',
      method: 'post',
      params: { role: '指挥员' },
      data: { user_id: 2 },
    })
  })

  it('signInDrillParticipant 调用 POST /drills/:id/sign-in', async () => {
    requestMock.mockResolvedValue({ data: null })
    await signInDrillParticipant(1, { user_id: 2 })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/drills/1/sign-in',
      method: 'post',
      data: { user_id: 2 },
    })
  })

  it('getDrillEvaluation 调用 GET /drills/:id/evaluation', async () => {
    requestMock.mockResolvedValue({ data: { total_score: 85 } })
    await getDrillEvaluation(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/drills/1/evaluation',
      method: 'get',
    })
  })

  it('submitDrillEvaluation 调用 POST /drills/evaluation', async () => {
    const payload = {
      drill_id: 1,
      items: [{ item: 'response', label: '响应时间', score: 8, max_score: 10 }],
    }
    requestMock.mockResolvedValue({ data: { total_score: 8 } })
    await submitDrillEvaluation(payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/drills/evaluation',
      method: 'post',
      data: payload,
    })
  })

  it('getDrillStatistics 调用 GET /drills/statistics', async () => {
    requestMock.mockResolvedValue({ data: { total_drills: 5 } })
    await getDrillStatistics()
    expect(requestMock).toHaveBeenCalledWith({
      url: '/drills/statistics',
      method: 'get',
    })
  })

  it('getDrillReportHtml 调用 GET /drills/:id/report/html', async () => {
    requestMock.mockResolvedValue({ data: '<html></html>' })
    await getDrillReportHtml(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/drills/1/report/html',
      method: 'get',
    })
  })
})
