import request from '@/utils/request'

/**
 * 获取预案列表
 */
export function getLinkagePlans(params) {
  return request({
    url: '/linkage-plans',
    method: 'get',
    params,
  })
}

/**
 * 获取预案详情
 */
export function getLinkagePlanDetail(id) {
  return request({
    url: `/linkage-plans/${id}`,
    method: 'get',
  })
}

/**
 * 创建预案
 */
export function createLinkagePlan(data) {
  return request({
    url: '/linkage-plans',
    method: 'post',
    data,
  })
}

/**
 * 更新预案
 */
export function updateLinkagePlan(id, data) {
  return request({
    url: `/linkage-plans/${id}`,
    method: 'put',
    data,
  })
}

/**
 * 删除预案
 */
export function deleteLinkagePlan(id) {
  return request({
    url: `/linkage-plans/${id}`,
    method: 'delete',
  })
}

/**
 * 切换预案启用状态
 */
export function togglePlanStatus(id, isEnabled) {
  return request({
    url: `/linkage-plans/${id}/toggle`,
    method: 'post',
  })
}

/**
 * 模拟触发预案
 */
export function simulateTrigger(planId, remark = null) {
  return request({
    url: `/linkage-plans/${planId}/simulate`,
    method: 'post',
    params: { remark },
  })
}

/**
 * 手动执行预案
 */
export function executeManualLinkage(data) {
  return request({
    url: '/linkage-plans/execute',
    method: 'post',
    data,
  })
}

/**
 * 查询联动日志
 */
export function getLinkageLogs(params) {
  return request({
    url: '/alarm-linkage-logs',
    method: 'get',
    params,
  })
}

/**
 * 获取日志详情
 */
export function getLogDetail(id) {
  return request({
    url: `/alarm-linkage-logs/${id}`,
    method: 'get',
  })
}

/**
 * 导出联动日志
 */
export function exportLinkageLogs(params) {
  return request({
    url: '/alarm-linkage-logs/export',
    method: 'get',
    params,
    responseType: 'blob',
  })
}
