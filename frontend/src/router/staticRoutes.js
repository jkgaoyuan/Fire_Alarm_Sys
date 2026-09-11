export const staticRoutes = [
  // ==================== 静态路由定义（不含动态权限菜单） ====================
  // ==================== P0-005: 路由守卫会在运行时根据权限加载动态菜单和路由 ====================

  // --- 基础页面 ---
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

  // --- 根路径（默认显示监控大屏）---
  {
    path: '/',
    name: 'Home',
    component: () => import('@/components/Layout.vue'),
    redirect: '/monitor/dashboard',  // 明确重定向到监控大屏
    children: [
      {
        path: 'monitor/dashboard',
        name: 'Dashboard',
        component: () => import('@/views/monitor/Dashboard.vue'),
        meta: { 
          title: '实时监控',
          icon: 'Monitor',
          order: 1
        },
      },
    ],
  },

  // --- 联动预案管理 ---
  {
    path: '/linkage',
    name: 'LinkagePlan',
    component: () => import('@/views/linkage/Plan.vue'),
    meta: { 
      title: '联动预案管理',
      icon: 'Setting',
      order: 10
    },
  },

  // --- 巡检管理 ---
  {
    path: '/inspection-plan',
    name: 'InspectionPlan',
    component: () => import('@/views/inspection/Plan.vue'),
    meta: { 
      title: '巡检计划',
      icon: 'List',
      order: 20
    },
  },
  {
    path: '/inspection-task',
    name: 'InspectionTask',
    component: () => import('@/views/inspection/Task.vue'),
    meta: { 
      title: '巡检任务',
      icon: 'Clipboard',
      order: 21
    },
  },

  // --- 告警中心 ---
  {
    path: '/alarm',
    name: 'AlarmCenter',
    component: () => import('@/views/alarm/Center.vue'),
    meta: { 
      title: '告警中心',
      icon: 'Bell',
      order: 30
    },
  },

  // --- 设备管理 ---
  {
    path: '/device-archive',
    name: 'DeviceArchive',
    component: () => import('@/views/device/Archive.vue'),
    meta: { 
      title: '设备档案',
      icon: 'Box',
      order: 40
    },
  },
  {
    path: '/device-import',
    name: 'DeviceImport',
    component: () => import('@/views/device/ArchiveImport.vue'),
    meta: { 
      title: '批量导入',
      icon: 'Upload',
      order: 41
    },
  },

  // --- 消防演练 ---
  {
    path: '/drill-event',
    name: 'DrillEvent',
    component: () => import('@/views/drill/Event.vue'),
    meta: { 
      title: '演练事件',
      icon: 'VideoCamera',
      order: 50
    },
  },

  // --- 应急处置 ---
  {
    path: '/emergency',
    name: 'EmergencyEvent',
    component: () => import('@/views/emergency/Event.vue'),
    meta: { 
      title: '应急处置',
      icon: 'Sos',
      order: 60
    },
  },

  // --- 故障维修 ---
  {
    path: '/repair-order',
    name: 'RepairOrder',
    component: () => import('@/views/repair/OrderList.vue'),
    meta: { 
      title: '维修工单',
      icon: 'Tools',
      order: 70
    },
  },
  {
    path: '/repair-statistics',
    name: 'RepairStatistics',
    component: () => import('@/views/repair/RepairStatistics.vue'),
    meta: { 
      title: '维修统计',
      icon: 'TrendCharts',
      order: 71
    },
  },

  // --- 统计报表 ---
  {
    path: '/statistics-report',
    name: 'StatisticsReport',
    component: () => import('@/views/statistics/Report.vue'),
    meta: { 
      title: '综合报表',
      icon: 'Document',
      order: 80
    },
  },
  {
    path: '/statistics-alarm',
    name: 'AlarmTrend',
    component: () => import('@/views/statistics/AlarmTrend.vue'),
    meta: { 
      title: '告警趋势',
      icon: 'TrendingUp',
      order: 81
    },
  },
  {
    path: '/statistics-device',
    name: 'DeviceStatus',
    component: () => import('@/views/statistics/DeviceStatus.vue'),
    meta: { 
      title: '设备状态',
      icon: 'DataAnalysis',
      order: 82
    },
  },

  // --- 系统管理 ---
  {
    path: '/system-user',
    name: 'SystemUser',
    component: () => import('@/views/system/User.vue'),
    meta: { 
      title: '用户管理',
      icon: 'User',
      order: 90
    },
  },
  {
    path: '/system-role',
    name: 'SystemRole',
    component: () => import('@/views/system/Role.vue'),
    meta: { 
      title: '角色管理',
      icon: 'Lock',
      order: 91
    },
  },
  {
    path: '/system-loginlog',
    name: 'LoginLog',
    component: () => import('@/views/system/LoginLog.vue'),
    meta: { 
      title: '登录日志',
      icon: 'View',
      order: 92
    },
  },
]
