// Repair Order API (3.7-F1)
// Corresponding backend endpoints: /api/v1/repair-orders

import request from '@/utils/request'

// 获取维修工单列表
export function getRepairOrders(params) {
  return request({
    url: '/repair-orders',
    method: 'get',
    params,
  })
}

// 创建维修工单
export function createRepairOrder(data) {
  return request({
    url: '/repair-orders',
    method: 'post',
    data,
  })
}

// 获取维修工单详情
export function getRepairOrderDetail(id) {
  return request({
    url: `/repair-orders/${id}`,
    method: 'get',
  })
}

// 派单
export function assignRepairOrder(id, data) {
  return request({
    url: `/repair-orders/${id}/assign`,
    method: 'put',
    data,
  })
}

// 完成维修
export function completeRepairOrder(id, data) {
  return request({
    url: `/repair-orders/${id}/complete`,
    method: 'put',
    data,
  })
}

// 验收通过
export function acceptRepairOrder(id) {
  return request({
    url: `/repair-orders/${id}/accept`,
    method: 'put',
  })
}

// 验收退回
export function returnRepairOrder(id, data) {
  return request({
    url: `/repair-orders/${id}/return`,
    method: 'put',
    data,
  })
}
