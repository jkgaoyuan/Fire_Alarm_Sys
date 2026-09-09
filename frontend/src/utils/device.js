/**
 * 设备档案工具函数（纯函数，便于单元测试）
 */

export const DEVICE_STATUS_OPTIONS = [
  { value: 'normal', label: '正常', type: 'success' },
  { value: 'alarm', label: '报警', type: 'danger' },
  { value: 'fault', label: '故障', type: 'warning' },
  { value: 'shield', label: '屏蔽', type: 'info' },
  { value: 'offline', label: '离线', type: 'info' },
  { value: 'retired', label: '已退役', type: 'info' },
]

const STATUS_MAP = Object.fromEntries(
  DEVICE_STATUS_OPTIONS.map((item) => [item.value, item])
)

/** 设备状态中文名 */
export function deviceStatusLabel(status) {
  return STATUS_MAP[status]?.label || status || '-'
}

/** 设备状态对应的 el-tag 类型 */
export function deviceStatusType(status) {
  return STATUS_MAP[status]?.type || 'info'
}

/** 已退役为终态：禁止编辑与再次退役 */
export function isTerminalStatus(status) {
  return status === 'retired'
}

/**
 * 去掉组织架构树中空的 children，避免 el-cascader 把叶子节点渲染成可展开的空分支
 */
export function stripEmptyChildren(nodes) {
  if (!Array.isArray(nodes)) return []
  return nodes.map((node) => {
    if (!node.children || node.children.length === 0) {
      const { children, ...rest } = node
      return rest
    }
    return { ...node, children: stripEmptyChildren(node.children) }
  })
}

/**
 * 按 attribute_schema 生成扩展属性的空值对象
 * number 用 null（el-input-number 不接受空字符串），其余用 ''
 */
export function emptyAttributes(schema) {
  const attributes = {}
  if (!schema) return attributes
  for (const [key, spec] of Object.entries(schema)) {
    attributes[key] = spec?.type === 'number' ? null : ''
  }
  return attributes
}

/**
 * 把设备已有的扩展属性补齐到与 schema 一致的键集合
 */
export function mergeAttributes(schema, attributes) {
  return { ...emptyAttributes(schema), ...(attributes || {}) }
}

/**
 * 解析 attribute_schema 供动态表单渲染
 * 后端字段类型仅支持 string / number / select
 */
export function resolveAttributeFields(schema) {
  if (!schema || typeof schema !== 'object') return []
  return Object.entries(schema).map(([key, spec]) => ({
    key,
    label: spec?.label || key,
    type: ['string', 'number', 'select'].includes(spec?.type) ? spec.type : 'string',
    options: Array.isArray(spec?.options) ? spec.options : [],
  }))
}
