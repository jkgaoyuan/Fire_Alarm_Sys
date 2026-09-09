import request from '@/utils/request'

/**
 * 获取登录日志列表
 * @param {Object} params - 查询参数 { page, page_size, username, status, start_time, end_time }
 */
export function getLoginLogs(params) {
  return request({
    url: '/login-logs',
    method: 'get',
    params,
  })
}
