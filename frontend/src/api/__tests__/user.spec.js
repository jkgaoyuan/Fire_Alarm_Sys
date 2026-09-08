import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/request', () => {
  const requestMock = vi.fn()
  return {
    default: requestMock,
  }
})

import request from '@/utils/request'
import {
  getMe,
  getMenus,
  getPermissions,
  getUsers,
  createUser,
  updateUser,
  deleteUser,
  updateUserStatus,
  assignUserRoles,
  resetUserPassword,
  getAllRoles,
} from '../user'

const requestMock = request

describe('api/user.js', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('getMe 调用 GET /users/me', async () => {
    requestMock.mockResolvedValue({ data: { username: 'admin' } })
    const res = await getMe()
    expect(requestMock).toHaveBeenCalledWith({
      url: '/users/me',
      method: 'get',
    })
    expect(res.data.username).toBe('admin')
  })

  it('getMenus 调用 GET /users/me/menus', async () => {
    requestMock.mockResolvedValue({ data: [] })
    await getMenus()
    expect(requestMock).toHaveBeenCalledWith({
      url: '/users/me/menus',
      method: 'get',
    })
  })

  it('getPermissions 调用 GET /users/me/permissions', async () => {
    requestMock.mockResolvedValue({ data: [] })
    await getPermissions()
    expect(requestMock).toHaveBeenCalledWith({
      url: '/users/me/permissions',
      method: 'get',
    })
  })

  it('getUsers 调用 GET /users 并携带查询参数', async () => {
    requestMock.mockResolvedValue({ data: { items: [], total: 0 } })
    await getUsers({ page: 1, page_size: 10, keyword: 'admin' })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/users',
      method: 'get',
      params: { page: 1, page_size: 10, keyword: 'admin' },
    })
  })

  it('createUser 调用 POST /users', async () => {
    const payload = {
      username: 'newuser',
      password: 'New123456',
      data_scope: 'self',
      role_ids: [],
    }
    requestMock.mockResolvedValue({ data: payload })
    await createUser(payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/users',
      method: 'post',
      data: payload,
    })
  })

  it('updateUser 调用 PUT /users/:id', async () => {
    const payload = { real_name: '更新' }
    requestMock.mockResolvedValue({ data: payload })
    await updateUser(1, payload)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/users/1',
      method: 'put',
      data: payload,
    })
  })

  it('deleteUser 调用 DELETE /users/:id', async () => {
    requestMock.mockResolvedValue({ data: null })
    await deleteUser(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/users/1',
      method: 'delete',
    })
  })

  it('updateUserStatus 调用 PUT /users/:id/status', async () => {
    requestMock.mockResolvedValue({ data: { status: 'disabled' } })
    await updateUserStatus(1, { status: 'disabled' })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/users/1/status',
      method: 'put',
      data: { status: 'disabled' },
    })
  })

  it('assignUserRoles 调用 PUT /users/:id/roles', async () => {
    requestMock.mockResolvedValue({ data: { roles: [] } })
    await assignUserRoles(1, { role_ids: [1, 2] })
    expect(requestMock).toHaveBeenCalledWith({
      url: '/users/1/roles',
      method: 'put',
      data: { role_ids: [1, 2] },
    })
  })

  it('resetUserPassword 调用 PUT /users/:id/reset-password', async () => {
    requestMock.mockResolvedValue({ data: { new_password: 'random123' } })
    await resetUserPassword(1)
    expect(requestMock).toHaveBeenCalledWith({
      url: '/users/1/reset-password',
      method: 'put',
    })
  })

  it('getAllRoles 调用 GET /users/roles/all', async () => {
    requestMock.mockResolvedValue({ data: [] })
    await getAllRoles()
    expect(requestMock).toHaveBeenCalledWith({
      url: '/users/roles/all',
      method: 'get',
    })
  })
})
