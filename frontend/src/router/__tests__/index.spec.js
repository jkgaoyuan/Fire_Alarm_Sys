import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePermissionStore } from '@/stores/permission'

vi.mock('@/utils/auth', () => ({
  getToken: vi.fn(),
}))

vi.mock('@/api/user', () => ({
  getMenus: vi.fn(),
  getPermissions: vi.fn(),
}))

// mock menu.js 中的 glob，避免测试环境找不到组件模块
vi.mock('@/utils/menu', async (importOriginal) => {
  const actual = await importOriginal()
  const mockModules = {
    '@/views/monitor/Dashboard.vue': () => Promise.resolve({ default: { template: '<div>Dashboard</div>' } }),
    '@/views/system/Role.vue': () => Promise.resolve({ default: { template: '<div>Role</div>' } }),
    '@/views/system/User.vue': () => Promise.resolve({ default: { template: '<div>User</div>' } }),
  }
  return {
    ...actual,
    generateRoutesFromMenus: (menus, _modules = mockModules) =>
      actual.generateRoutesFromMenus(menus, mockModules),
  }
})

import { getToken } from '@/utils/auth'
import { getMenus, getPermissions } from '@/api/user'
import router from '@/router/index.js'

const STATIC_ROUTE_NAMES = new Set(['Login', 'Forbidden', 'NotFound', 'NotFoundWildcard'])

function resetRouter() {
  const permStore = usePermissionStore()
  permStore.resetPermission()
  // 移除动态添加的路由，只保留静态路由
  router.getRoutes().forEach((route) => {
    if (route.name && !STATIC_ROUTE_NAMES.has(route.name)) {
      try {
        router.removeRoute(route.name)
      } catch {
        // 忽略重复移除
      }
    }
  })
}

function addTestRoute(path, name) {
  router.addRoute({
    path,
    name,
    component: { template: '<div>Test</div>' },
  })
}

describe('router guard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    resetRouter()
  })

  it('白名单路由 /login 直接放行', async () => {
    getToken.mockReturnValue(null)
    await router.push('/login')
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('无 Token 时访问非白名单路由应跳转到 /login', async () => {
    getToken.mockReturnValue(null)
    addTestRoute('/system/role', 'test-role')
    await router.push('/system/role')
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('已登录且菜单未加载时应获取菜单并重新导航', async () => {
    getToken.mockReturnValue('valid-token')
    getMenus.mockResolvedValue({
      data: [
        {
          path: '/monitor/dashboard',
          name: 'monitor:dashboard',
          component: 'views/monitor/Dashboard.vue',
          meta: { title: '监控大屏', icon: 'Monitor' },
        },
      ],
    })
    getPermissions.mockResolvedValue({ data: ['monitor:dashboard'] })

    await router.push('/monitor/dashboard')
    expect(router.currentRoute.value.path).toBe('/monitor/dashboard')
  })

  it('已登录且有权限访问 /system/role 应放行', async () => {
    getToken.mockReturnValue('valid-token')
    addTestRoute('/system/role', 'system-role')

    const permStore = usePermissionStore()
    permStore.menus = [
      {
        path: '/system/role',
        name: 'system:role',
        meta: { title: '角色管理', icon: 'Role' },
      },
    ]
    permStore.permissions = ['system:role']
    permStore.isRoutesLoaded = true

    await router.push('/system/role')
    expect(router.currentRoute.value.path).toBe('/system/role')
  })

  it('已登录但无权限访问应跳转到 /403', async () => {
    getToken.mockReturnValue('valid-token')
    addTestRoute('/system/role', 'system-role')

    const permStore = usePermissionStore()
    permStore.menus = [
      { path: '/dashboard', name: 'dashboard', meta: { title: '首页' } },
    ]
    permStore.permissions = []
    permStore.isRoutesLoaded = true

    await router.push('/system/role')
    expect(router.currentRoute.value.path).toBe('/403')
  })

  it('含参数路由应使用路由定义 path 而非实际 URL', async () => {
    getToken.mockReturnValue('valid-token')
    const permStore = usePermissionStore()
    // 菜单中登记的是路由定义路径 /device/:id
    permStore.menus = [
      { path: '/device/:id', name: 'device:detail', meta: { title: '设备详情' } },
    ]
    permStore.permissions = []
    permStore.isRoutesLoaded = true

    // 注册参数路由
    router.addRoute({
      path: '/device/:id',
      name: 'device:detail',
      component: { template: '<div>Device</div>' },
    })

    await router.push('/device/123')
    // matched[last].path 应为 /device/:id，与菜单路径匹配，因此放行
    expect(router.currentRoute.value.path).toBe('/device/123')
  })

  it('访问根路径 / 应放行', async () => {
    getToken.mockReturnValue('valid-token')
    const permStore = usePermissionStore()
    permStore.menus = [
      { path: '/dashboard', name: 'dashboard', meta: { title: '首页' } },
    ]
    permStore.isRoutesLoaded = true

    // 注册根路由
    router.addRoute({
      path: '/',
      name: 'Root',
      component: { template: '<div>Root</div>' },
    })

    await router.push('/')
    expect(router.currentRoute.value.path).toBe('/')
  })
})
