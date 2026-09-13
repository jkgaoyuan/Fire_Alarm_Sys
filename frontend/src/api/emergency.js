import request from '@/utils/request'

/**
 * 应急事件分页查询（B4）
 */
export function getEmergencyEvents(params) {
  return request({
    url: '/emergency/events',
    method: 'get',
    params,
  })
}

/**
 * 应急事件详情（B5）
 */
export function getEventDetail(id) {
  return request({
    url: `/emergency/events/${id}`,
    method: 'get',
  })
}

/**
 * 应急事件时间轴列表（B5）
 */
export function getEventTimelines(eventId) {
  return request({
    url: `/emergency/events/${eventId}/timelines`,
    method: 'get',
  })
}

/**
 * 添加时间轴节点（B5）
 */
export function addTimelineNode(eventId, data) {
  return request({
    url: `/emergency/events/${eventId}/timelines`,
    method: 'post',
    data,
  })
}

/**
 * 删除时间轴节点（B5）
 * 后端路由：DELETE /emergency/events/timelines/{node_id}
 */
export function deleteTimelineNode(nodeId) {
  return request({
    url: `/emergency/events/timelines/${nodeId}`,
    method: 'delete',
  })
}

/**
 * 导出应急事件报告（B6/F6）
 * 响应为 HTML Blob，由调用方触发浏览器下载
 * @param {number} eventId
 * @returns {Promise<Blob>}
 */
export async function exportEventReport(eventId) {
  const blob = await request({
    url: `/emergency/events/${eventId}/report`,
    method: 'get',
    responseType: 'blob',
  })
  return blob
}

/**
 * 获取用户通知列表（B7）
 */
export function getNotifications(params) {
  return request({
    url: '/notifications',
    method: 'get',
    params,
  })
}

/**
 * 标记单条通知为已读（B7）
 */
export function markNotificationRead(notificationId) {
  return request({
    url: `/notifications/${notificationId}/read`,
    method: 'post',
  })
}

/**
 * 标记所有通知为已读（B7）
 * 后端路由：POST /notifications/read-all
 */
export function markNotificationsAsRead() {
  return request({
    url: '/notifications/read-all',
    method: 'post',
  })
}
