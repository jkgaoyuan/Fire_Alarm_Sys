export const staticRoutes = [
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
  {
    path: '/linkage',
    name: 'LinkagePlan',
    component: () => import('@/views/linkage/Plan.vue'),
    hidden: false,
    meta: { 
      title: '联动预案管理',
      icon: 'settings',
      roles: ['admin', 'fire_safety_manager', 'operator'],
      order: 10
    },
  },
]
