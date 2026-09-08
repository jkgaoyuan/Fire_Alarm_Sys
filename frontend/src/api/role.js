import request from '@/utils/request'

/**
 * 获取角色列表
 * @param {Object} params - 查询参数 { page, page_size, keyword }
 */
export function getRoles(params) {
  return request({
    url: '/roles',
    method: 'get',
    params,
  })
}

/**
 * 创建角色
 * @param {Object} data - { role_name, description, perm_ids }
 */
export function createRole(data) {
  return request({
    url: '/roles',
    method: 'post',
    data,
  })
}

/**
 * 更新角色
 * @param {number} id - 角色 ID
 * @param {Object} data - { role_name, description, perm_ids }
 */
export function updateRole(id, data) {
  return request({
    url: `/roles/${id}`,
    method: 'put',
    data,
  })
}

/**
 * 删除角色
 * @param {number} id - 角色 ID
 */
export function deleteRole(id) {
  return request({
    url: `/roles/${id}`,
    method: 'delete',
  })
}

/**
 * 获取角色已绑定的权限 ID 列表
 * @param {number} id - 角色 ID
 */
export function getRolePermissions(id) {
  return request({
    url: `/roles/${id}/permissions`,
    method: 'get',
  })
}

/**
 * 获取权限树
 */
export function getPermissionTree() {
  return request({
    url: '/permissions/tree',
    method: 'get',
  })
}
