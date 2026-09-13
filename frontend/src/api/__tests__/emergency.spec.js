/**
 * 应急处置 / 通知中心 API 请求形状测试（3.5）
 *
 * 后端契约见 backend/app/api/v1/emergency_events.py（prefix `/emergency/events`）
 * 与 notifications.py（prefix `/notifications`）。
 *
 * 回归守护点：
 * - 时间轴删除是 `DELETE /emergency/events/timelines/{id}`（曾错写成 `/emergency/timeline-nodes/{id}` → 404）
 * - 全部已读是 `POST /notifications/read-all`（曾错写成 `/notifications/mark-all-read` → 404）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/request', () => {
  const requestMock = vi.fn()
  return { default: requestMock }
})

import request from '@/utils/request'
import {
  getEmergencyEvents,
  getEventDetail,
  getEventTimelines,
  addTimelineNode,
  deleteTimelineNode,
  exportEventReport,
  getNotifications,
  markNotificationRead,
  markNotificationsAsRead,
} from '../emergency'

const requestMock = request

describe('api/emergency.js', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    requestMock.mockResolvedValue({ code: 200, data: {} })
  })

  it('getEmergencyEvents 调用 GET /emergency/events 并携带筛选参数', async () => {
    const params = { page: 1, page_size: 20, status: 'processing', org_id: 21 }
    await getEmergencyEvents(params)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/emergency/events',
      method: 'get',
      params,
    })
  })

  it('getEventDetail 调用 GET /emergency/events/:id', async () => {
    await getEventDetail(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/emergency/events/1',
      method: 'get',
    })
  })

  it('getEventTimelines 调用 GET /emergency/events/:id/timelines', async () => {
    await getEventTimelines(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/emergency/events/1/timelines',
      method: 'get',
    })
  })

  it('addTimelineNode 调用 POST /emergency/events/:id/timelines 并把节点放在 body', async () => {
    const payload = { node_type: 'manual_confirm', remark: '现场核实' }
    await addTimelineNode(1, payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/emergency/events/1/timelines',
      method: 'post',
      data: payload,
    })
  })

  it('deleteTimelineNode 调用 DELETE /emergency/events/timelines/:id', async () => {
    await deleteTimelineNode(5)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/emergency/events/timelines/5',
      method: 'delete',
    })
  })

  it('exportEventReport 调用 GET /emergency/events/:id/report 并声明 blob 响应', async () => {
    await exportEventReport(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/emergency/events/1/report',
      method: 'get',
      responseType: 'blob',
    })
  })

  it('getNotifications 调用 GET /notifications 并携带分页参数', async () => {
    const params = { page: 1, page_size: 20, module: 'emergency' }
    await getNotifications(params)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/notifications',
      method: 'get',
      params,
    })
  })

  it('markNotificationRead 调用 POST /notifications/:id/read 且不带 body', async () => {
    await markNotificationRead(3)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/notifications/3/read',
      method: 'post',
    })
  })

  it('markNotificationsAsRead 调用 POST /notifications/read-all', async () => {
    await markNotificationsAsRead()
    expect(requestMock).toHaveBeenCalledWith({
      url: '/notifications/read-all',
      method: 'post',
    })
  })
})
