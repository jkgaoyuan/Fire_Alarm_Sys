import request from '@/utils/request'

// ========== 统计看板（FR-048 ~ FR-051）==========

/**
 * 综合概览卡片
 * @param {Object} [params] - { org_id }
 */
export function getStatisticsOverview(params) {
  return request({
    url: '/statistics/overview',
    method: 'get',
    params,
  })
}

/**
 * 设备完好率看板（FR-048）
 * @param {Object} [params] - { org_id, include_drill }
 */
export function getDeviceStatusStats(params) {
  return request({
    url: '/statistics/device-status',
    method: 'get',
    params,
  })
}

/**
 * 报警趋势图（FR-049）
 * @param {Object} [params] - { days, org_id, include_drill, start, end }
 */
export function getAlarmTrend(params) {
  return request({
    url: '/statistics/alarm-trend',
    method: 'get',
    params,
  })
}

/**
 * 故障 TOP10（FR-050）
 * @param {Object} [params] - { org_id, start, end }
 */
export function getFaultTop10(params) {
  return request({
    url: '/statistics/fault-top10',
    method: 'get',
    params,
  })
}

/**
 * 巡检完成率（FR-051）
 * @param {Object} [params] - { org_id, start, end }
 */
export function getInspectionCompletion(params) {
  return request({
    url: '/statistics/inspection-completion',
    method: 'get',
    params,
  })
}
