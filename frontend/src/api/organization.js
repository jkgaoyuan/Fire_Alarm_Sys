import request from '@/utils/request'

/**
 * 组织架构扁平列表（供筛选下拉）
 */
export function getOrganizations() {
  return request({
    url: '/organizations',
    method: 'get',
  })
}

/**
 * 组织架构树（供 el-cascader 区域选择）
 */
export function getOrganizationTree() {
  return request({
    url: '/organizations/tree',
    method: 'get',
  })
}

/**
 * 创建组织节点
 * @param {object} data
 */
export function createOrganization(data) {
  return request({
    url: '/organizations',
    method: 'post',
    data,
  })
}

/**
 * 更新组织节点
 * @param {number} orgId
 * @param {object} data
 */
export function updateOrganization(orgId, data) {
  return request({
    url: `/organizations/${orgId}`,
    method: 'put',
    data,
  })
}

/**
 * 删除组织节点
 * @param {number} orgId
 */
export function deleteOrganization(orgId) {
  return request({
    url: `/organizations/${orgId}`,
    method: 'delete',
  })
}

// ========== 平面图配置（FR-017）==========

/**
 * 上传楼层平面图（PNG/JPG/PDF，≤10MB，服务端超宽压缩后回写基准宽高）
 * @param {number} orgId
 * @param {File} file
 */
export function uploadMapImage(orgId, file) {
  const formData = new FormData()
  formData.append('file', file)
  return request({
    url: `/organizations/${orgId}/map-image`,
    method: 'post',
    data: formData,
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
}

/**
 * 删除楼层平面图（同时清空基准宽高，子区域不再继承底图）
 * @param {number} orgId
 */
export function deleteMapImage(orgId) {
  return request({
    url: `/organizations/${orgId}/map-image`,
    method: 'delete',
  })
}
