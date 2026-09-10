/**
 * 维修工单 API 测试
 * 3.7-F1
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
  getRepairOrders,
  createRepairOrder,
  getRepairOrderDetail,
  assignRepairOrder,
  completeRepairOrder,
  acceptRepairOrder,
  returnRepairOrder,
  getRepairOverview,
  getRepairerWorkload,
  getFaultDistribution,
  getTop10FaultDevices,
} from '../repair'

const requestMock = request

describe('api/repair.js', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('getRepairOrders 调用 GET /repair-orders 并携带查询参数', async () => {
    requestMock.mockResolvedValue({ data: { items: [], total: 0 } })
    await getRepairOrders({ page: 1, page_size: 20, status: 'pending' })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/repair-orders',
      method: 'get',
      params: { page: 1, page_size: 20, status: 'pending' },
    })
  })

  it('createRepairOrder 调用 POST /repair-orders', async () => {
    const payload = { device_id: 1, fault_desc: '设备故障' }
    requestMock.mockResolvedValue({ data: { id: 1, order_no: 'RO-20260910-001' } })
    await createRepairOrder(payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/repair-orders',
      method: 'post',
      data: payload,
    })
  })

  it('getRepairOrderDetail 调用 GET /repair-orders/:id', async () => {
    requestMock.mockResolvedValue({ data: { id: 1, order_no: 'RO-20260910-001' } })
    await getRepairOrderDetail(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/repair-orders/1',
      method: 'get',
    })
  })

  it('assignRepairOrder 调用 PUT /repair-orders/:id/assign', async () => {
    const payload = { repairer_id: 2 }
    requestMock.mockResolvedValue({ data: { id: 1, status: 'assigned' } })
    await assignRepairOrder(1, payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/repair-orders/1/assign',
      method: 'put',
      data: payload,
    })
  })

  it('completeRepairOrder 调用 PUT /repair-orders/:id/complete', async () => {
    const payload = { repair_result: '更换传感器' }
    requestMock.mockResolvedValue({ data: { id: 1, status: 'pending_accept' } })
    await completeRepairOrder(1, payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/repair-orders/1/complete',
      method: 'put',
      data: payload,
    })
  })

  it('acceptRepairOrder 调用 PUT /repair-orders/:id/accept', async () => {
    requestMock.mockResolvedValue({ data: { id: 1, status: 'completed' } })
    await acceptRepairOrder(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/repair-orders/1/accept',
      method: 'put',
    })
  })

  it('returnRepairOrder 调用 PUT /repair-orders/:id/return', async () => {
    const payload = { return_reason: '故障未修复' }
    requestMock.mockResolvedValue({ data: { id: 1, status: 'returned' } })
    await returnRepairOrder(1, payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/repair-orders/1/return',
      method: 'put',
      data: payload,
    })
  })

  it('getRepairOverview 调用 GET /repair-statistics/overview', async () => {
    requestMock.mockResolvedValue({ data: { total_orders: 10, avg_repair_hours: 2.5 } })
    await getRepairOverview()
    expect(requestMock).toHaveBeenCalledWith({
      url: '/repair-statistics/overview',
      method: 'get',
    })
  })

  it('getRepairerWorkload 调用 GET /repair-statistics/by-repairer', async () => {
    requestMock.mockResolvedValue({ data: { items: [] } })
    await getRepairerWorkload()
    expect(requestMock).toHaveBeenCalledWith({
      url: '/repair-statistics/by-repairer',
      method: 'get',
    })
  })

  it('getFaultDistribution 调用 GET /repair-statistics/fault-types', async () => {
    requestMock.mockResolvedValue({ data: { items: [] } })
    await getFaultDistribution()
    expect(requestMock).toHaveBeenCalledWith({
      url: '/repair-statistics/fault-types',
      method: 'get',
    })
  })

  it('getTop10FaultDevices 调用 GET /repair-statistics/top10-devices', async () => {
    requestMock.mockResolvedValue({ data: { items: [] } })
    await getTop10FaultDevices()
    expect(requestMock).toHaveBeenCalledWith({
      url: '/repair-statistics/top10-devices',
      method: 'get',
    })
  })
})
