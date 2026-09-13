/**
 * 设备档案 API 请求形状测试（3.2）
 *
 * 只盯「请求怎么发」：method / url / 参数落在 query 还是 body。
 * 后端契约见 backend/app/api/v1/devices.py（router prefix `/devices`，类型路由 `/device-types`）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/request', () => {
  const requestMock = vi.fn()
  return {
    default: requestMock,
  }
})

import request from '@/utils/request'
import {
  getDeviceTypes,
  getDeviceType,
  getDevices,
  getDevice,
  createDevice,
  updateDevice,
  retireDevice,
  deleteDevice,
  restoreDevice,
  getDeviceHistory,
  getDeviceTrajectory,
  exportDeviceTrajectory,
  importDevices,
  downloadImportTemplate,
} from '../device'

const requestMock = request

describe('api/device.js', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    requestMock.mockResolvedValue({ code: 200, data: {} })
  })

  it('getDeviceTypes 调用 GET /device-types', async () => {
    await getDeviceTypes()
    expect(requestMock).toHaveBeenCalledWith({
      url: '/device-types',
      method: 'get',
    })
  })

  it('getDeviceType 调用 GET /device-types/:id', async () => {
    await getDeviceType(11)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/device-types/11',
      method: 'get',
    })
  })

  it('getDevices 调用 GET /devices 并把筛选放在 query', async () => {
    const params = { page: 1, page_size: 20, keyword: '烟感', type_id: 11, status: 'normal' }
    await getDevices(params)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/devices',
      method: 'get',
      params,
    })
  })

  it('getDevice 调用 GET /devices/:id', async () => {
    await getDevice(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/devices/1',
      method: 'get',
    })
  })

  it('createDevice 调用 POST /devices 并把表单放在 body', async () => {
    const payload = { device_code: 'DEV-001', device_name: '1F烟感', type_id: 11, org_id: 21 }
    await createDevice(payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/devices',
      method: 'post',
      data: payload,
    })
  })

  it('updateDevice 调用 PUT /devices/:id 并把表单放在 body', async () => {
    const payload = { device_name: '改名后' }
    await updateDevice(1, payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/devices/1',
      method: 'put',
      data: payload,
    })
  })

  it('retireDevice 调用 POST /devices/:id/retire 并携带 reason', async () => {
    await retireDevice(1, { reason: '超期报废' })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/devices/1/retire',
      method: 'post',
      data: { reason: '超期报废' },
    })
  })

  it('deleteDevice 调用 DELETE /devices/:id 且不带 body', async () => {
    await deleteDevice(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/devices/1',
      method: 'delete',
    })
  })

  it('restoreDevice 调用 POST /devices/:id/restore 且不带 body', async () => {
    await restoreDevice(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/devices/1/restore',
      method: 'post',
    })
    // 回收站恢复是无参 POST
    expect(requestMock.mock.calls[0][0].data).toBeUndefined()
  })

  it('getDevices 支持 include_deleted 回收站筛选', async () => {
    await getDevices({ include_deleted: true })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/devices',
      method: 'get',
      params: { include_deleted: true },
    })
  })

  it('getDeviceHistory 调用 GET /devices/:id/history 并把 limit 放在 query', async () => {
    await getDeviceHistory(1, { limit: 200 })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/devices/1/history',
      method: 'get',
      params: { limit: 200 },
    })
  })

  it('getDeviceTrajectory 调用 GET /devices/:id/trajectory 并携带分页与时间范围', async () => {
    const params = { start: '2026-09-01', end: '2026-09-10', page: 1, page_size: 50 }
    await getDeviceTrajectory(1, params)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/devices/1/trajectory',
      method: 'get',
      params,
    })
  })

  it('exportDeviceTrajectory 调用 GET …/trajectory/export 并声明 blob 响应', async () => {
    await exportDeviceTrajectory(1, { start: '2026-09-01', end: '2026-09-10', format: 'xlsx' })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/devices/1/trajectory/export',
      method: 'get',
      params: { start: '2026-09-01', end: '2026-09-10', format: 'xlsx' },
      responseType: 'blob',
    })
  })

  it('importDevices 调用 POST /devices/import 并以 multipart 发送 FormData', async () => {
    const file = new File(['x'], 'devices.xlsx')
    await importDevices(file)

    const config = requestMock.mock.calls[0][0]
    expect(config.url).toBe('/devices/import')
    expect(config.method).toBe('post')
    expect(config.data).toBeInstanceOf(FormData)
    expect(config.data.get('file')).toBe(file)
    expect(config.headers['Content-Type']).toBe('multipart/form-data')
    expect(config.timeout).toBe(120000)
  })

  it('downloadImportTemplate 调用 GET /devices/import/template 并声明 blob 响应', async () => {
    await downloadImportTemplate()
    expect(requestMock).toHaveBeenCalledWith({
      url: '/devices/import/template',
      method: 'get',
      responseType: 'blob',
    })
  })
})
