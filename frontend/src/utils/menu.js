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
    for (const node of nodes) {
      // Skip parent menus (Layout) - just expand their children
      if (node.component === 'Layout') {
        if (node.children && node.children.length > 0) {
          traverse(node.children)
        }
        continue
      }

      // Use perm_code as name if available, otherwise use the normalized path
      // IMPORTANT: Keep leading slash for Vue Router compatibility
      const routePath = node.route_path || node.path || '/'
      const routeName = node.perm_code || node.name || routePath

      const route = {
        path: routePath,  // Include leading slash for Vue Router
        name: routeName,
        component: node.component
          ? (modules[`@/${node.component}`] || viewComponents[node.component] || undefined)
          : undefined,
        meta: {
          title: node.perm_name || node.title,
          icon: node.icon,
          activeMenu: routePath, // Use normalized path for active menu highlighting
        },
        children: [],
      }

      if (node.children && node.children.length > 0) {
        route.children = traverse(node.children)
      }

      routes.push(route)
    }
    return routes
  }

  traverse(menus)
  return routes
}

/**
 * 将菜单数据归一化（用于 el-menu 显示）
 * 确保路径包含前导斜杠以匹配 Vue Router 路由
 * @param {Array} menus 菜单树
 * @returns {Array} 归一化后的菜单树
 */
export function normalizeMenuForDisplay(menus) {
  const normalized = []
  
  function traverse(nodes) {
    for (const node of nodes) {
      // 复制节点并添加 clone 以避免修改原对象
      const clonedNode = { ...node }
      
      // 确保 path 包含前导斜杠
      if (clonedNode.path && !clonedNode.path.startsWith('/')) {
        clonedNode.path = '/' + clonedNode.path
      }
      
      // 递归处理子菜单
      if (clonedNode.children && clonedNode.children.length > 0) {
        clonedNode.children = traverse(clonedNode.children)
      }
      
      normalized.push(clonedNode)
    }
    return normalized
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
        const normalizedPath = node.route_path || node.path
        paths.push(normalizedPath)
      }
      if (node.children) traverse(node.children)
    }
  }
  traverse(menus)
  return paths
}
