import request from '@/utils/request'

/**
 * 报警记录分页查询
 * @param {Object} params - { page, page_size, alarm_type, alarm_level, status, org_id, device_id, start, end, include_drill }
 */
export function getAlarms(params) {
  return request({
    url: '/alarms',
    method: 'get',
    params,
  })
}

/**
 * 报警详情
 * @param {number} id
 */
export function getAlarm(id) {
  return request({
    url: `/alarms/${id}`,
    method: 'get',
  })
}

/**
 * 确认报警（FR-025/FR-026）
 * @param {number} id
 * @param {Object} data - { confirm_result, false_reason }
 */
export function confirmAlarm(id, data) {
  return request({
    url: `/alarms/${id}/confirm`,
    method: 'post',
    data,
  })
}

/**
 * 单条消音（FR-016.1，幂等且不改状态）
 * @param {number} id
 */
export function silenceAlarm(id) {
  return request({
    url: `/alarms/${id}/silence`,
    method: 'post',
  })
}

/**
 * 系统复位（FR-016.2）
 * @param {number} id
 * @param {Object} data - { physical_restored, remark }
 */
export function resetAlarm(id, data) {
  return request({
    url: `/alarms/${id}/reset`,
    method: 'post',
    data,
  })
}
