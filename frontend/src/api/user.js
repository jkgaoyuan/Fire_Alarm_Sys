import request from '@/utils/request'

// ========== 当前用户相关 ==========

export function getMe() {
  return request({
    url: '/users/me',
    method: 'get',
  })
}

export function getMenus() {
  return request({
    url: '/users/me/menus',
    method: 'get',
  })
}

export function getPermissions() {
  return request({
    url: '/users/me/permissions',
    method: 'get',
  })
}

// ========== 用户管理（需 system:user 权限）==========

/**
 * 获取用户列表
 * @param {Object} params - 查询参数 { page, page_size, keyword }
 */
export function getUsers(params) {
  return request({
    url: '/users',
    method: 'get',
    params,
  })
}

/**
 * 创建用户
 * @param {Object} data - { username, password, real_name, phone, email, org_id, data_scope, role_ids }
 */
export function createUser(data) {
  return request({
    url: '/users',
    method: 'post',
    data,
  })
}

/**
 * 更新用户
 * @param {number} id - 用户 ID
 * @param {Object} data - { real_name, phone, email, org_id, data_scope, role_ids, status }
 */
export function updateUser(id, data) {
  return request({
    url: `/users/${id}`,
    method: 'put',
    data,
  })
}

/**
 * 删除用户
 * @param {number} id - 用户 ID
 */
export function deleteUser(id) {
  return request({
    url: `/users/${id}`,
    method: 'delete',
  })
}

/**
 * 变更用户状态
 * @param {number} id - 用户 ID
 * @param {Object} data - { status: 'active' | 'locked' | 'disabled' }
 */
export function updateUserStatus(id, data) {
  return request({
    url: `/users/${id}/status`,
    method: 'put',
    data,
  })
}

/**
 * 分配用户角色
 * @param {number} id - 用户 ID
 * @param {Object} data - { role_ids: number[] }
 */
export function assignUserRoles(id, data) {
  return request({
    url: `/users/${id}/roles`,
    method: 'put',
    data,
  })
}

/**
 * 重置用户密码
 * @param {number} id - 用户 ID
 */
export function resetUserPassword(id) {
  return request({
    url: `/users/${id}/reset-password`,
    method: 'put',
  })
}

/**
 * 获取所有角色（用于分配角色弹窗）
 */
export function getAllRoles() {
  return request({
    url: '/users/roles/all',
    method: 'get',
  })
}
