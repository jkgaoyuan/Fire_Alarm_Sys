/**
 * 组织架构 API 请求形状测试（3.2）
 *
 * 后端契约见 backend/app/api/v1/organizations.py（prefix `/organizations`）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/request', () => {
  const requestMock = vi.fn()
  return { default: requestMock }
})

import request from '@/utils/request'
import {
  getOrganizations,
  getOrganizationTree,
  createOrganization,
  updateOrganization,
  deleteOrganization,
  uploadMapImage,
  deleteMapImage,
} from '../organization'

const requestMock = request

describe('api/organization.js', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    requestMock.mockResolvedValue({ code: 200, data: {} })
  })

  it('getOrganizations 调用 GET /organizations', async () => {
    await getOrganizations()
    expect(requestMock).toHaveBeenCalledWith({
      url: '/organizations',
      method: 'get',
    })
  })

  it('getOrganizationTree 调用 GET /organizations/tree', async () => {
    await getOrganizationTree()
    expect(requestMock).toHaveBeenCalledWith({
      url: '/organizations/tree',
      method: 'get',
    })
  })

  it('createOrganization 调用 POST /organizations 并把表单放在 body', async () => {
    const payload = { org_name: '三号楼', org_type: 'building', parent_id: 20 }
    await createOrganization(payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/organizations',
      method: 'post',
      data: payload,
    })
  })

  it('updateOrganization 调用 PUT /organizations/:id 并把表单放在 body', async () => {
    const payload = { org_name: '改名后' }
    await updateOrganization(21, payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/organizations/21',
      method: 'put',
      data: payload,
    })
  })

  it('deleteOrganization 调用 DELETE /organizations/:id 且不带 body', async () => {
    await deleteOrganization(21)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/organizations/21',
      method: 'delete',
    })
  })

  it('uploadMapImage 调用 POST /organizations/:id/map-image 并以 multipart 发送 file 字段', async () => {
    const file = new File(['x'], 'map.png')
    await uploadMapImage(21, file)

    const config = requestMock.mock.calls[0][0]
    expect(config.url).toBe('/organizations/21/map-image')
    expect(config.method).toBe('post')
    expect(config.data).toBeInstanceOf(FormData)
    // 后端签名为 file: UploadFile = File(...)，字段名必须是 file
    expect(config.data.get('file')).toBe(file)
    expect(config.headers['Content-Type']).toBe('multipart/form-data')
  })

  it('deleteMapImage 调用 DELETE /organizations/:id/map-image', async () => {
    await deleteMapImage(21)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/organizations/21/map-image',
      method: 'delete',
    })
  })
})
