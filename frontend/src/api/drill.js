// Drill API (3.8)
// Corresponding backend endpoints: /api/v1/drills

import request from '@/utils/request'

// ==================== 演练计划 ====================

// 获取演练列表（分页 + 筛选）
// params: { page, page_size, status_filter, drill_type }
export function getDrills(params) {
  return request({
    url: '/drills',
    method: 'get',
    params,
  })
}

// 创建演练计划
// data: { drill_name, drill_type, planned_at, location, participant_user_ids }
export function createDrill(data) {
  return request({
    url: '/drills',
    method: 'post',
    data,
  })
}

// 获取演练详情（含参与人员、现场记录、评估结果）
export function getDrillDetail(id) {
  return request({
    url: `/drills/${id}`,
    method: 'get',
  })
}

// 更新演练计划
export function updateDrill(id, data) {
  return request({
    url: `/drills/${id}`,
    method: 'put',
    data,
  })
}

// 删除演练计划（级联删除评估）
export function deleteDrill(id) {
  return request({
    url: `/drills/${id}`,
    method: 'delete',
  })
}

// 参与人员候选人（供表单与详情页的人员选择器使用）
//
// 刻意调演练域自己的端点而**不是** `GET /users`：后者由 `system:user` 守卫，
// 而值班员/维保员持有 `drill:execute` 却没有 `system:user`（实测 403），
// 沿用会让这两个角色在「执行演练时加人」这一步整个断掉。
// 返回精简字段 [{id, username, real_name, role_names}]，不含 phone/email。
export function getDrillParticipantCandidates() {
  return request({
    url: '/drills/participant-candidates',
    method: 'get',
  })
}

// ==================== 演练执行 ====================

// 开始执行演练（planned → ongoing）
// data: { photos?, videos? }
export function executeDrill(id, data) {
  return request({
    url: `/drills/${id}/execute`,
    method: 'post',
    data,
  })
}

// 完成演练（ongoing → completed）
// data: { summary, actual_end_at? }
export function completeDrill(id, data) {
  return request({
    url: `/drills/${id}/complete`,
    method: 'post',
    data,
  })
}

// 取消演练（planned/ongoing → cancelled）
// data: { reason? }
export function cancelDrill(id, data) {
  return request({
    url: `/drills/${id}/cancel`,
    method: 'post',
    data,
  })
}

// 添加参与人员
// data: { user_id }，role 通过 query 传递
export function addDrillParticipant(id, data, role) {
  return request({
    url: `/drills/${id}/participants`,
    method: 'post',
    params: { role },
    data,
  })
}

// 参与人员签到
// data: { user_id }
export function signInDrillParticipant(id, data) {
  return request({
    url: `/drills/${id}/sign-in`,
    method: 'post',
    data,
  })
}

// ==================== 评估打分 ====================

// 获取演练评估（每演练仅一份）
export function getDrillEvaluation(id) {
  return request({
    url: `/drills/${id}/evaluation`,
    method: 'get',
  })
}

// 提交演练评估
// data: { drill_id, items: [{item, label, score, max_score, comment}], problems, improvements, evaluation_summary }
export function submitDrillEvaluation(data) {
  return request({
    url: '/drills/evaluation',
    method: 'post',
    data,
  })
}

// ==================== 统计与报告 ====================

// 演练统计数据
export function getDrillStatistics() {
  return request({
    url: '/drills/statistics',
    method: 'get',
  })
}

// 生成演练报告 HTML（响应 data 为 HTML 字符串，前端构造 Blob 下载）
export function getDrillReportHtml(id) {
  return request({
    url: `/drills/${id}/report/html`,
    method: 'get',
  })
}
