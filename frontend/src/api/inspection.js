// Inspection API (3.6-F2)
// Corresponding backend endpoints: /api/v1/inspection-plans

import request from '@/utils/request'

// 获取巡检计划列表
export function getInspectionPlans(params) {
  return request({
    url: '/inspection-plans',
    method: 'get',
    params,
  })
}

// 创建巡检计划
export function createInspectionPlan(data) {
  return request({
    url: '/inspection-plans',
    method: 'post',
    data,
  })
}

// 获取巡检计划详情
export function getInspectionPlanDetail(id) {
  return request({
    url: `/inspection-plans/${id}`,
    method: 'get',
  })
}

// 更新巡检计划
export function updateInspectionPlan(id, data) {
  return request({
    url: `/inspection-plans/${id}`,
    method: 'put',
    data,
  })
}

// 删除巡检计划
export function deleteInspectionPlan(id) {
  return request({
    url: `/inspection-plans/${id}`,
    method: 'delete',
  })
}

// 启用/停用巡检计划
export function toggleInspectionPlanStatus(id, data) {
  return request({
    url: `/inspection-plans/${id}/toggle`,
    method: 'post',
    data,
  })
}

// 手动生成巡检任务
export function generateInspectionTasks(id, params) {
  return request({
    url: `/inspection-plans/${id}/generate`,
    method: 'post',
    params,
  })
}

// 获取巡检任务列表
export function getInspectionTasks(params) {
  return request({
    url: '/inspection-tasks',
    method: 'get',
    params,
  })
}

// 提交巡检记录
export function submitInspectionRecord(taskId, data) {
  return request({
    url: `/inspection-tasks/${taskId}/records`,
    method: 'post',
    data,
  })
}

// 获取巡检记录列表
export function getInspectionRecords(params) {
  return request({
    url: '/inspection-records',
    method: 'get',
    params,
  })
}

// 获取漏检统计
export function getMissedStatistics(params) {
  return request({
    url: '/inspection-missed-stats',
    method: 'get',
    params,
  })
}
