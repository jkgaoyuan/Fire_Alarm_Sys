/**
 * 角色 / 权限 API 请求形状测试（3.1）
 *
 * 后端契约见 backend/app/api/v1/roles.py（prefix `/roles`）与 permissions.py（prefix `/permissions`）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/request', () => {
  const requestMock = vi.fn()
  return { default: requestMock }
})

import request from '@/utils/request'
import {
  getRoles,
  createRole,
  updateRole,
  deleteRole,
  getRolePermissions,
  getPermissionTree,
} from '../role'

const requestMock = request

describe('api/role.js', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    requestMock.mockResolvedValue({ code: 200, data: {} })
  })

  it('getRoles 调用 GET /roles 并把 keyword 放在 query', async () => {
    const params = { page: 1, page_size: 10, keyword: '消防' }
    await getRoles(params)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/roles',
      method: 'get',
      params,
    })
  })

  it('createRole 调用 POST /roles 并把表单放在 body', async () => {
    const payload = { role_code: 'chief2', role_name: '副主管' }
    await createRole(payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/roles',
      method: 'post',
      data: payload,
    })
  })

  it('updateRole 调用 PUT /roles/:id 并把表单放在 body', async () => {
    const payload = { role_name: '改名后' }
    await updateRole(1, payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/roles/1',
      method: 'put',
      data: payload,
    })
  })

  it('deleteRole 调用 DELETE /roles/:id 且不带 body', async () => {
    await deleteRole(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/roles/1',
      method: 'delete',
    })
  })

  it('getRolePermissions 调用 GET /roles/:id/permissions', async () => {
    await getRolePermissions(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/roles/1/permissions',
      method: 'get',
    })
  })

  it('getPermissionTree 调用 GET /permissions/tree', async () => {
    await getPermissionTree()
    expect(requestMock).toHaveBeenCalledWith({
      url: '/permissions/tree',
      method: 'get',
    })
  })
})
