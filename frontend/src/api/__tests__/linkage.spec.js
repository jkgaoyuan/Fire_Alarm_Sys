/**
 * 联动预案 API 请求形状测试（3.4）
 *
 * 后端契约见 backend/app/api/v1/linkage_plans.py（prefix `/linkage-plans`）
 * 与 linkage_logs.py（prefix `/alarm-linkage-logs`）。
 *
 * 回归守护点：
 * - toggle 必须把目标状态放进 body（曾经接受第二参数却从不发送 → 后端盲取反）
 * - 日志导出走 `/alarm-linkage-logs/export`，不再是被 `/{log_id}` 遮蔽的 `/linkage-plans/logs/export`
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/request', () => {
  const requestMock = vi.fn()
  return { default: requestMock }
})

import request from '@/utils/request'
import {
  getLinkagePlans,
  getLinkagePlanDetail,
  createLinkagePlan,
  updateLinkagePlan,
  deleteLinkagePlan,
  togglePlanStatus,
  simulateTrigger,
  executeManualLinkage,
  getLinkageLogs,
  getLogDetail,
  exportLinkageLogs,
} from '../linkage'

const requestMock = request

describe('api/linkage.js', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    requestMock.mockResolvedValue({ code: 200, data: {} })
  })

  it('getLinkagePlans 调用 GET /linkage-plans 并携带筛选参数', async () => {
    const params = { page: 1, page_size: 10, fire_type: 'fire', is_enabled: true }
    await getLinkagePlans(params)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/linkage-plans',
      method: 'get',
      params,
    })
  })

  it('getLinkagePlanDetail 调用 GET /linkage-plans/:id', async () => {
    await getLinkagePlanDetail(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/linkage-plans/1',
      method: 'get',
    })
  })

  it('createLinkagePlan 调用 POST /linkage-plans 并把预案放在 body', async () => {
    const payload = { plan_name: '火警联动', org_id: 1, fire_type: 'fire', actions: [] }
    await createLinkagePlan(payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/linkage-plans',
      method: 'post',
      data: payload,
    })
  })

  it('updateLinkagePlan 调用 PUT /linkage-plans/:id 并把预案放在 body', async () => {
    const payload = { plan_name: '改名后' }
    await updateLinkagePlan(1, payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/linkage-plans/1',
      method: 'put',
      data: payload,
    })
  })

  it('deleteLinkagePlan 调用 DELETE /linkage-plans/:id 且不带 body', async () => {
    await deleteLinkagePlan(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/linkage-plans/1',
      method: 'delete',
    })
  })

  it('togglePlanStatus 调用 POST /:id/toggle 并把 is_enabled 放在 body', async () => {
    await togglePlanStatus(1, false)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/linkage-plans/1/toggle',
      method: 'post',
      data: { is_enabled: false },
    })
    // 回归守护：曾经该参数被完全丢弃，后端只能盲取反
    const config = requestMock.mock.calls[0][0]
    expect(config.params).toBeUndefined()
  })

  it('simulateTrigger 调用 POST /:id/simulate 并把 remark 放在 query', async () => {
    await simulateTrigger(1, '手动验证')
    expect(requestMock).toHaveBeenCalledWith({
      url: '/linkage-plans/1/simulate',
      method: 'post',
      params: { remark: '手动验证' },
    })
  })

  it('executeManualLinkage 调用 POST /linkage-plans/execute', async () => {
    const payload = { plan_id: 1, alarm_id: 2 }
    await executeManualLinkage(payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/linkage-plans/execute',
      method: 'post',
      data: payload,
    })
  })

  it('getLinkageLogs 调用 GET /alarm-linkage-logs 并携带筛选参数', async () => {
    const params = { page: 1, page_size: 20, plan_id: 1 }
    await getLinkageLogs(params)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/alarm-linkage-logs',
      method: 'get',
      params,
    })
  })

  it('getLogDetail 调用 GET /alarm-linkage-logs/:id', async () => {
    await getLogDetail(9)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/alarm-linkage-logs/9',
      method: 'get',
    })
  })

  it('exportLinkageLogs 调用 GET /alarm-linkage-logs/export 并声明 blob 响应', async () => {
    await exportLinkageLogs({ alarm_id: 3 })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/alarm-linkage-logs/export',
      method: 'get',
      params: { alarm_id: 3 },
      responseType: 'blob',
    })
  })
})
