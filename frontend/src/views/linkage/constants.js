/**
 * 联动域共用常量
 *
 * 动作类型的中文名此前在 `Plan.vue`（`formatActionType`）和 `PlanForm.vue`
 * （`actionTypes`）各有一份；联动日志页是第三个使用点，所以收敛到这里，
 * 新页面直接用，不再抄第三遍。
 *
 * TODO: `Plan.vue` / `PlanForm.vue` 仍在用各自的副本，待逐步并入本文件。
 */

export const ACTION_TYPE_LABELS = {
  start_exhaust: '启动排烟',
  close_door: '关闭防火门',
  start_lighting: '启动应急照明',
  broadcast: '疏散广播',
}

/** 联动日志状态：pending → sent → success/failed（见 linkage_executor） */
export const LOG_STATUS_LABELS = {
  pending: '待执行',
  sent: '已下发',
  success: '成功',
  failed: '失败',
}

export const LOG_STATUS_TAG_TYPES = {
  pending: 'info',
  sent: 'warning',
  success: 'success',
  failed: 'danger',
}

export function actionLabel(actionType) {
  return ACTION_TYPE_LABELS[actionType] || actionType || '-'
}

export function logStatusLabel(status) {
  return LOG_STATUS_LABELS[status] || status || '-'
}

export function logStatusTagType(status) {
  return LOG_STATUS_TAG_TYPES[status] || 'info'
}
