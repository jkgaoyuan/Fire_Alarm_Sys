import request from '@/utils/request'

/**
 * 监控大屏统计
 * @param {Object} [params] - { org_id }
 */
export function getDashboard(params) {
  return request({
    url: '/monitor/dashboard',
    method: 'get',
    params,
  })
}

/**
 * 大屏报警 TopN（未确认火警置顶）
 * @param {Object} [params] - { limit, org_id, include_drill }
 */
export function getRecentAlarms(params) {
  return request({
    url: '/monitor/alarms/recent',
    method: 'get',
    params,
  })
}

/**
 * 区域平面图元数据（后端自动向上继承最近持图楼层）
 * @param {number} org_id
 */
export function getMapMeta(org_id) {
  return request({
    url: '/monitor/map',
    method: 'get',
    params: { org_id },
  })
}

/**
 * 视口内设备点位，超过 limit 时后端返回网格聚合桶
 * @param {Object} [params] - { org_id, bbox, limit }
 */
export function getMapDevices(params) {
  return request({
    url: '/monitor/map/devices',
    method: 'get',
    params,
  })
}

/**
 * 换取一次性 WebSocket 握手 Ticket（60s，用一次即失效）
 */
export function createWsTicket() {
  return request({
    url: '/monitor/ws-ticket',
    method: 'post',
  })
}
