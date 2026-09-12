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
  {
    path: '/',
    name: 'Home',
    component: () => import('@/components/Layout.vue'),
    redirect: '/monitor/dashboard',
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
    ],
  },
]
