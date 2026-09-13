export const staticRoutes = [
  // ==================== 静态路由定义（不含动态权限菜单） ====================
  // ==================== P0-005: 路由守卫会在运行时根据权限加载动态菜单和路由 ====================

  // --- 基础页面（无 Layout） ---
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/Index.vue'),
    hidden: true,
    meta: { title: '登录' },
  },
  {
    path: '/403',
    name: 'Forbidden',
    component: () => import('@/views/error/403.vue'),
    hidden: true,
    meta: { title: '无权限' },
  },
  {
    path: '/404',
    name: 'NotFound',
    component: () => import('@/views/error/404.vue'),
    hidden: true,
    meta: { title: '页面不存在' },
  },

  // --- 根路径：Layout 壳，所有业务页面均作为其子路由 ---
  // 注意：不要在这里写死 redirect，由路由守卫根据用户权限动态重定向
  {
    path: '/',
    name: 'Home',
    component: () => import('@/components/Layout.vue'),
    children: [
      {
        path: '/monitor/dashboard',
        name: 'Dashboard',
        component: () => import('@/views/monitor/Dashboard.vue'),
        meta: {
          title: '实时监控',
          icon: 'Monitor',
          order: 1,
        },
      },
      // 隐藏子页面：巡检计划管理（从巡检任务跳转，复用 inspection:task 菜单权限）
      {
        path: '/inspection/plan',
        name: 'InspectionPlan',
        component: () => import('@/views/inspection/Plan.vue'),
        hidden: true,
        meta: { title: '巡检计划管理' },
      },
    ],
  },
]
