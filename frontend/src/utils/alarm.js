/**
 * 报警展示元数据（3.3 FR-014 / FR-017）
 *
 * 大屏（WS 帧 + /monitor/alarms/recent）用 `alarm_id`，报警中心（/alarms 分页）用 `id`，
 * 两者共用同一批展示组件，因此取值统一走 alarmIdOf。
 */

export const ALARM_TYPE_OPTIONS = [
  { value: 'fire', label: '火警', color: '#f56c6c', tag: 'danger' },
  { value: 'pre_fire', label: '预警', color: '#e6a23c', tag: 'warning' },
  { value: 'fault', label: '故障', color: '#eec12f', tag: 'warning' },
  { value: 'shield', label: '屏蔽', color: '#909399', tag: 'info' },
]

export const ALARM_STATUS_OPTIONS = [
  { value: 'pending', label: '待确认', tag: 'danger' },
  { value: 'confirmed', label: '已确认', tag: 'warning' },
  { value: 'processing', label: '处置中', tag: 'primary' },
  { value: 'false_alarm', label: '误报', tag: 'info' },
  { value: 'resolved', label: '已解决', tag: 'success' },
]

export const ALARM_LEVEL_OPTIONS = [
  { value: 'critical', label: '紧急', tag: 'danger' },
  { value: 'major', label: '重要', tag: 'warning' },
  { value: 'minor', label: '一般', tag: 'info' },
]

/** FR-026 误报原因预置项，与 3.5 处置流程共用同一口径 */
export const FALSE_REASON_OPTIONS = ['设备故障', '环境因素', '人为误触', '其他']

const pick = (options) => (value) => options.find((item) => item.value === value) || null

export const alarmTypeMeta = pick(ALARM_TYPE_OPTIONS)
export const alarmStatusMeta = pick(ALARM_STATUS_OPTIONS)
export const alarmLevelMeta = pick(ALARM_LEVEL_OPTIONS)

export function alarmTypeLabel(value) {
  return alarmTypeMeta(value)?.label || value || '-'
}

export function alarmStatusLabel(value) {
  return alarmStatusMeta(value)?.label || value || '-'
}

export function alarmLevelLabel(value) {
  return alarmLevelMeta(value)?.label || value || '-'
}

export function alarmStatusTag(value) {
  return alarmStatusMeta(value)?.tag || 'info'
}

export function alarmLevelTag(value) {
  return alarmLevelMeta(value)?.tag || 'info'
}

export function alarmTypeColor(value) {
  return alarmTypeMeta(value)?.color || '#909399'
}

export function alarmIdOf(item) {
  if (!item) return null
  return item.alarm_id ?? item.id ?? null
}

/** 未确认火警：大屏红色呼吸灯与置顶的判定条件（FR-014） */
export function isPendingFire(alarm) {
  return !!alarm && alarm.status === 'pending' && alarm.alarm_type === 'fire'
}

/** 消音只写 silenced_at，状态不变（FR-016.1） */
export function isSilenced(alarm) {
  return !!alarm && (alarm.silenced === true || !!alarm.silenced_at)
}

export function formatAlarmTime(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 19)
}
