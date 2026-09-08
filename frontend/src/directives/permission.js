import { usePermissionStore } from '@/stores/permission'

/**
 * v-permission 指令
 *
 * 基础用法：v-permission="'device:create'"
 *   - 无权限时默认 CSS 隐藏（display: none），避免布局跳动
 *
 * 修饰符 remove：v-permission.remove="'device:create'"
 *   - 无权限时彻底移除 DOM 节点
 *
 * 修饰符 disabled：v-permission.disabled="'device:create'"
 *   - 无权限时设置 disabled = true，并添加 is-disabled 类
 *
 * 支持数组权限：v-permission="['device:create', 'device:update']"
 *   - 任一权限满足即视为有权限
 */
function checkPermission(value, permissions) {
  if (Array.isArray(value)) {
    return value.some((perm) => permissions.includes(perm))
  }
  return permissions.includes(value)
}

export const permission = {
  mounted(el, binding) {
    const { value, modifiers } = binding
    const permStore = usePermissionStore()
    const hasPermission = checkPermission(value, permStore.permissions)

    if (!hasPermission) {
      if (modifiers.remove) {
        el.parentNode?.removeChild(el)
      } else if (modifiers.disabled) {
        el.disabled = true
        el.classList.add('is-disabled')
      } else {
        el.style.display = 'none'
      }
    }
  },
  updated(el, binding) {
    // 权限列表可能在动态获取后更新，需要重新评估
    const { value, modifiers } = binding
    const permStore = usePermissionStore()
    const hasPermission = checkPermission(value, permStore.permissions)

    if (hasPermission) {
      // 恢复显示 / 恢复可用状态
      if (modifiers.disabled) {
        el.disabled = false
        el.classList.remove('is-disabled')
      } else {
        el.style.display = ''
      }
    } else {
      if (modifiers.remove) {
        if (el.parentNode) {
          el.parentNode.removeChild(el)
        }
      } else if (modifiers.disabled) {
        el.disabled = true
        el.classList.add('is-disabled')
      } else {
        el.style.display = 'none'
      }
    }
  },
}

export default permission
