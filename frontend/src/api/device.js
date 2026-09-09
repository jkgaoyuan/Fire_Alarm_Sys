import request from '@/utils/request'

// ========== 设备类型（登录即可，供下拉框与动态表单）==========

/**
 * 设备类型列表（全部，不分页）
 */
export function getDeviceTypes() {
  return request({
    url: '/device-types',
    method: 'get',
  })
}

/**
 * 设备类型详情（含 attribute_schema）
 * @param {number} id
 */
export function getDeviceType(id) {
  return request({
    url: `/device-types/${id}`,
    method: 'get',
  })
}

// ========== 设备档案 CRUD ==========

/**
 * 设备列表
 * @param {Object} params - { page, page_size, keyword, type_id, org_id, status, brand, include_retired }
 */
export function getDevices(params) {
  return request({
    url: '/devices',
    method: 'get',
    params,
  })
}

/**
 * 设备详情
 * @param {number} id
 */
export function getDevice(id) {
  return request({
    url: `/devices/${id}`,
    method: 'get',
  })
}

/**
 * 创建设备
 * @param {Object} data - DeviceCreate
 */
export function createDevice(data) {
  return request({
    url: '/devices',
    method: 'post',
    data,
  })
}

/**
 * 更新设备
 * @param {number} id
 * @param {Object} data - DeviceUpdate
 */
export function updateDevice(id, data) {
  return request({
    url: `/devices/${id}`,
    method: 'put',
    data,
  })
}

/**
 * 设备退役（status -> retired，保留关联历史）
 * @param {number} id
 * @param {Object} data - { reason }
 */
export function retireDevice(id, data) {
  return request({
    url: `/devices/${id}/retire`,
    method: 'post',
    data,
  })
}

/**
 * 逻辑删除设备档案
 * @param {number} id
 */
export function deleteDevice(id) {
  return request({
    url: `/devices/${id}`,
    method: 'delete',
  })
}

// ========== 设备历史 ==========

/**
 * 设备历史记录（统一时间轴）
 * @param {number} id
 * @param {Object} [params] - { limit }
 */
export function getDeviceHistory(id, params) {
  return request({
    url: `/devices/${id}/history`,
    method: 'get',
    params,
  })
}

// ========== 历史轨迹（FR-018）==========

/**
 * 状态轨迹时间序列（默认近 7 天，最长 90 天）
 * @param {number} id
 * @param {Object} [params] - { start, end, page, page_size }
 */
export function getDeviceTrajectory(id, params) {
  return request({
    url: `/devices/${id}/trajectory`,
    method: 'get',
    params,
  })
}

/**
 * 导出轨迹文件流
 *
 * 走 axios 而非 `window.open(tokenUrl)`：Token 进 query 会落进 Nginx access_log 与浏览器历史。
 * @param {number} id
 * @param {Object} params - { start, end, format: 'xlsx' | 'csv' }
 */
export function exportDeviceTrajectory(id, params) {
  return request({
    url: `/devices/${id}/trajectory/export`,
    method: 'get',
    params,
    responseType: 'blob',
  })
}

// ========== 批量导入 ==========

/**
 * Excel 批量导入设备
 * @param {File} file
 */
export function importDevices(file) {
  const formData = new FormData()
  formData.append('file', file)
  return request({
    url: '/devices/import',
    method: 'post',
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
}

/**
 * 下载导入模板（返回 .xlsx 文件流）
 */
export function downloadImportTemplate() {
  return request({
    url: '/devices/import/template',
    method: 'get',
    responseType: 'blob',
  })
}
