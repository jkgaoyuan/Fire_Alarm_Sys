/**
 * 巡检 API 请求形状测试（3.6）
 *
 * 这一层专门盯「请求怎么发」：method / url / 参数落在 query 还是 body。
 * 组件测试 mock 掉本模块，因此只有这里能拦住
 * 「generate 把 days 发成 query、后端从 body 读 → 422」这类缺陷。
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
  getInspectionPlans,
  createInspectionPlan,
  getInspectionPlanDetail,
  updateInspectionPlan,
  deleteInspectionPlan,
  toggleInspectionPlanStatus,
  generateInspectionTasks,
  getInspectionTasks,
  submitInspectionRecord,
  getInspectionRecords,
  getMissedStatistics,
} from '../inspection'

const requestMock = request

describe('api/inspection.js', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    requestMock.mockResolvedValue({ code: 200, data: {} })
  })

  it('getInspectionPlans 调用 GET /inspection-plans 并携带分页筛选参数', async () => {
    await getInspectionPlans({ page: 2, page_size: 20, org_id: 1, is_enabled: false })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/inspection-plans',
      method: 'get',
      params: { page: 2, page_size: 20, org_id: 1, is_enabled: false },
    })
  })

  it('createInspectionPlan 调用 POST /inspection-plans 并把表单放在 body', async () => {
    const payload = {
      plan_name: '每日巡检',
      org_id: 1,
      cycle_type: 'daily',
      responsible_user_id: 3,
      start_date: '2026-09-01',
    }
    await createInspectionPlan(payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/inspection-plans',
      method: 'post',
      data: payload,
    })
  })

  it('getInspectionPlanDetail 调用 GET /inspection-plans/:id', async () => {
    await getInspectionPlanDetail(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/inspection-plans/1',
      method: 'get',
    })
  })

  it('updateInspectionPlan 调用 PUT /inspection-plans/:id 并把表单放在 body', async () => {
    const payload = { plan_name: '更新后' }
    await updateInspectionPlan(1, payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/inspection-plans/1',
      method: 'put',
      data: payload,
    })
  })

  it('deleteInspectionPlan 调用 DELETE /inspection-plans/:id', async () => {
    await deleteInspectionPlan(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/inspection-plans/1',
      method: 'delete',
    })
  })

  it('toggleInspectionPlanStatus 调用 POST /:id/toggle 并把 is_enabled 放在 body', async () => {
    await toggleInspectionPlanStatus(1, { is_enabled: false })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/inspection-plans/1/toggle',
      method: 'post',
      data: { is_enabled: false },
    })
  })

  it('generateInspectionTasks 调用 POST /:id/generate 并把 days 放在 body 而不是 query', async () => {
    await generateInspectionTasks(1, { days: 7 })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/inspection-plans/1/generate',
      method: 'post',
      data: { days: 7 },
    })
    // 回归守护：曾经误用 params，后端从 body 读导致 422
    const config = requestMock.mock.calls[0][0]
    expect(config.params).toBeUndefined()
  })

  it('getInspectionTasks 调用 GET /inspection-tasks 并携带分页筛选参数', async () => {
    await getInspectionTasks({ page: 1, page_size: 20, status: 'pending' })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/inspection-tasks',
      method: 'get',
      params: { page: 1, page_size: 20, status: 'pending' },
    })
  })

  it('submitInspectionRecord 调用 POST /inspection-tasks/:id/records', async () => {
    const payload = { task_id: 1, device_id: 2, result: 'normal', photos: [] }
    await submitInspectionRecord(1, payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/inspection-tasks/1/records',
      method: 'post',
      data: payload,
    })
  })

  it('getInspectionRecords 调用 GET /inspection-records', async () => {
    await getInspectionRecords({ page: 1, page_size: 20, task_id: 1 })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/inspection-records',
      method: 'get',
      params: { page: 1, page_size: 20, task_id: 1 },
    })
  })

  it('getMissedStatistics 调用 GET /inspection-missed-stats', async () => {
    await getMissedStatistics({ before_date: '2026-09-01' })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/inspection-missed-stats',
      method: 'get',
      params: { before_date: '2026-09-01' },
    })
  })
})
