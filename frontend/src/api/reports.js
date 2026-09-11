import request from '@/utils/request'

// ========== 报表导出（FR-052）==========

/**
 * 创建导出任务（Excel/CSV/Word）
 * @param {Object} data - { task_type, params, data, format }
 */
export function createExportTask(data) {
  return request({
    url: '/reports/export',
    method: 'post',
    data,
  })
}

/**
 * 查询导出任务状态
 * @param {number} taskId
 */
export function getExportTaskStatus(taskId) {
  return request({
    url: `/reports/export/${taskId}/status`,
    method: 'get',
  })
}

/**
 * 下载导出文件（返回 Blob）
 * @param {number} taskId
 */
export function downloadExportFile(taskId) {
  return request({
    url: `/reports/export/${taskId}/download`,
    method: 'get',
    responseType: 'blob',
  })
}

/**
 * 我的导出任务列表
 * @param {Object} params - { page, page_size }
 */
export function getMyExportTasks(params) {
  return request({
    url: '/reports/export-tasks',
    method: 'get',
    params,
  })
}
