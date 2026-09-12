/**
 * 菜单路由工具函数
 * 纯函数，无副作用，便于单元测试
 */

// 显式组件映射表（替代 import.meta.glob，避免生产构建键格式不一致问题）
const viewComponents = {
  'views/monitor/Dashboard.vue': () => import('@/views/monitor/Dashboard.vue'),
  'views/alarm/Center.vue': () => import('@/views/alarm/Center.vue'),
  'views/device/Archive.vue': () => import('@/views/device/Archive.vue'),
  'views/linkage/Plan.vue': () => import('@/views/linkage/Plan.vue'),
  'views/emergency/Event.vue': () => import('@/views/emergency/Event.vue'),
  'views/inspection/Task.vue': () => import('@/views/inspection/Task.vue'),
  'views/repair/OrderList.vue': () => import('@/views/repair/OrderList.vue'),
  'views/repair/RepairStatistics.vue': () => import('@/views/repair/RepairStatistics.vue'),
  'views/drill/Event.vue': () => import('@/views/drill/Event.vue'),
  'views/statistics/Report.vue': () => import('@/views/statistics/Report.vue'),
  'views/statistics/DeviceStatus.vue': () => import('@/views/statistics/DeviceStatus.vue'),
  'views/statistics/AlarmTrend.vue': () => import('@/views/statistics/AlarmTrend.vue'),
  'views/statistics/FaultTop10.vue': () => import('@/views/statistics/FaultTop10.vue'),
  'views/statistics/InspectionCompletion.vue': () => import('@/views/statistics/InspectionCompletion.vue'),
  'views/statistics/ExportCenter.vue': () => import('@/views/statistics/ExportCenter.vue'),
  'views/system/User.vue': () => import('@/views/system/User.vue'),
  'views/system/Role.vue': () => import('@/views/system/Role.vue'),
  'views/system/LoginLog.vue': () => import('@/views/system/LoginLog.vue'),
}

// 兼容测试环境注入 mock modules（键格式为 '@/views/...'）
const viewModules = Object.fromEntries(
  Object.entries(viewComponents).map(([k, v]) => [`@/${k}`, v])
)

/**
 * 将菜单树转换为 Vue Router 路由配置
 * @param {Array} menus 后端返回的菜单树
 * @param {Object} [modules] 模块映射（测试时可注入 mock）
 * @returns {Array} Vue Router 路由配置数组
 */
export function generateRoutesFromMenus(menus, modules = viewModules) {
  const routes = []

  function traverse(nodes) {
    if (!Array.isArray(nodes)) return []
    
    const currentBatch = []
    
    for (const node of nodes) {
      // Skip parent menus (Layout) - just expand their children
      if (node.component === 'Layout') {
        if (node.children && Array.isArray(node.children)) {
          const childRoutes = traverse(node.children)
          currentBatch.push(...childRoutes)
        }
        continue
      }

      // Use perm_code as name if available, otherwise use the normalized path
      // IMPORTANT: Keep leading slash for Vue Router compatibility
      const routePath = node.route_path || node.path || '/'
      const routeName = node.perm_code || node.name || routePath

      const route = {
        path: routePath,
        name: routeName,
        component: node.component
          ? (modules[`@/${node.component}`] || viewComponents[node.component] || undefined)
          : undefined,
        meta: {
          title: node.perm_name || node.title || node?.meta?.title,
          icon: node.icon || node?.meta?.icon,
          activeMenu: routePath,
        },
        children: [],
      }

      // ✅ Key fix: Always process children if they exist
      if (node.children && Array.isArray(node.children)) {
        const childRoutes = traverse(node.children)
        if (childRoutes.length > 0) {
          route.children = childRoutes
        }
      }

      currentBatch.push(route)
    }
    
    return currentBatch
  }

  return traverse(menus)
}

/**
 * 将菜单数据归一化（用于 el-menu 显示）
 * 确保路径包含前导斜杠以匹配 Vue Router 路由
 * @param {Array} menus 菜单树
 * @returns {Array} 归一化后的菜单树
 */
export function normalizeMenuForDisplay(menus) {
  // ✅ 关键修复：返回全新的数组，避免修改原对象
  const normalized = []
  
  function traverse(nodes) {
    if (!Array.isArray(nodes)) return []
    
    const result = []
    for (const node of nodes) {
      // ✅ 创建深拷贝以避免修改原对象
      const clonedNode = { ...node, children: [] }
      
      // ✅ 为子节点分配新的数组，防止循环引用
      const childResults = traverse(node.children || [])
      clonedNode.children = childResults
      
      // 确保 path 包含前导斜杠
      if (clonedNode.path && !clonedNode.path.startsWith('/')) {
        clonedNode.path = '/' + clonedNode.path
      }
      
      result.push(clonedNode)
    }
    return result
  }
  
  return traverse(menus)
}

/**
 * 递归收集所有菜单路径（用于路由守卫权限校验）
 * @param {Array} menus
 * @returns {Array} 路径字符串数组
 */
export function collectPaths(menus) {
  const paths = []
  function traverse(nodes) {
    for (const node of nodes) {
      if (node.route_path || node.path) {
        // IMPORTANT: Keep leading slash to match Vue Router route paths
        let normalizedPath = node.route_path || node.path
        // Normalize: ensure leading slash for Vue Router compatibility
        if (normalizedPath && !normalizedPath.startsWith('/')) {
          normalizedPath = '/' + normalizedPath
        }
        paths.push(normalizedPath)
      }
      if (node.children) traverse(node.children)
    }
  }
  traverse(menus)
  return paths
}
