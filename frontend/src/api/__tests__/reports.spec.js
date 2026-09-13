/**
 * 报表导出 API 请求形状测试（3.9 FR-052）
 *
 * 后端契约见 backend/app/api/v1/reports.py（prefix `/reports`）。
 * 注意 createExportTask 的 body 里 `params` 必须原样透传：
 * 导出中心的「重试」依赖后端回显该字段，缺了会静默产出空文件。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/request', () => {
  const requestMock = vi.fn()
  return { default: requestMock }
})

import request from '@/utils/request'
import {
  createExportTask,
  getExportTaskStatus,
  downloadExportFile,
  getMyExportTasks,
} from '../reports'

const requestMock = request

describe('api/reports.js', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    requestMock.mockResolvedValue({ code: 200, data: {} })
  })

  it('createExportTask 调用 POST /reports/export 并把导出参数放在 body', async () => {
    const payload = {
      task_type: 'alarm_trend',
      params: { org_id: 21, start: '2026-09-01', end: '2026-09-13' },
      data: [],
    }
    await createExportTask(payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/reports/export',
      method: 'post',
      data: payload,
    })
  })

  it('getExportTaskStatus 调用 GET /reports/export/:id/status', async () => {
    await getExportTaskStatus(7)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/reports/export/7/status',
      method: 'get',
    })
  })

  it('downloadExportFile 调用 GET /reports/export/:id/download 并声明 blob 响应', async () => {
    await downloadExportFile(7)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/reports/export/7/download',
      method: 'get',
      responseType: 'blob',
    })
  })

  it('getMyExportTasks 调用 GET /reports/export-tasks 并携带分页参数', async () => {
    const params = { page: 1, page_size: 20 }
    await getMyExportTasks(params)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/reports/export-tasks',
      method: 'get',
      params,
    })
  })
})
