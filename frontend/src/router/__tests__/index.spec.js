import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePermissionStore } from '@/stores/permission'

vi.mock('@/utils/auth', () => ({
  getToken: vi.fn(),
}))

vi.mock('@/api/user', () => ({
  getMenus: vi.fn(),
  getPermissions: vi.fn(),
}))

const { mockLogout, mockFetchUserInfo } = vi.hoisted(() => ({
  mockLogout: vi.fn().mockResolvedValue(),
  mockFetchUserInfo: vi.fn().mockResolvedValue({ username: 'admin', real_name: '管理员' }),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    logout: mockLogout,
    fetchUserInfo: mockFetchUserInfo,
  }),
}))
vi.mock('@/router/staticRoutes', () => ({
  staticRoutes: [
    { path: '/login', name: 'Login', component: { template: '<div>Login</div>' } },
    { path: '/403', name: 'Forbidden', component: { template: '<div>Forbidden</div>' } },
    { path: '/404', name: 'NotFound', component: { template: '<div>Not found</div>' } },
    // Home route with children — matches production structure where all business
    // pages are mounted under '/' so Layout (sidebar) stays alive.
    {
      path: '/',
      name: 'Home',
      component: { template: '<div>Layout</div>' },
      redirect: '/monitor/dashboard',
      children: [
        // Pre-register routes used in tests so to.matched is never empty
        // Dynamic routes from generateRoutes() will override these by name
        { path: '/monitor/dashboard', name: 'Dashboard', component: { template: '<div>Dashboard</div>' } },
        { path: '/system/user', name: 'system:user', component: { template: '<div>User</div>' } },
        { path: '/device/:id', name: 'DeviceDetail', component: { template: '<div>Device</div>' } },
      ],
    },
  ],
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
import router, { resetInitializeRoutes } from '@/router/index.js'

const STATIC_ROUTE_NAMES = new Set(['Login', 'Forbidden', 'NotFound', 'NotFoundWildcard', 'Home', 'Dashboard', 'system:user', 'DeviceDetail'])

function resetRouter() {
  const permStore = usePermissionStore()
  permStore.resetPermission()
  resetInitializeRoutes()
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

const dashboardMenu = {
  path: '/monitor/dashboard', name: 'monitor:dashboard',
  component: 'views/monitor/Dashboard.vue', meta: { title: 'Dashboard' },
}

function deferred() {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

describe('router guard', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    getMenus.mockReset()
    getPermissions.mockReset()
    mockFetchUserInfo.mockReset()
    mockFetchUserInfo.mockResolvedValue({ username: 'admin', real_name: '管理员' })
    vi.spyOn(console, 'error').mockImplementation(() => {})
    resetRouter()
    // Prevent guard from triggering route initialization during login reset
    getToken.mockReturnValue(null)
    await router.replace('/login')
  })

  afterEach(() => vi.restoreAllMocks())

  it('waits for slow menus and permissions before entering the dashboard', async () => {
    getToken.mockReturnValue('valid-token')
    const menus = deferred()
    const permissions = deferred()
    getMenus.mockReturnValue(menus.promise)
    getPermissions.mockReturnValue(permissions.promise)
    let finished = false
    const navigation = router.replace('/monitor/dashboard').then(() => { finished = true })
    await vi.waitFor(() => expect(getMenus).toHaveBeenCalledOnce())
    const whileMenusPending = {
      path: router.currentRoute.value.path, loaded: usePermissionStore().isRoutesLoaded, finished,
    }
    menus.resolve({ data: [dashboardMenu] })
    await vi.waitFor(() => expect(getPermissions).toHaveBeenCalledOnce())
    const whilePermissionsPending = {
      path: router.currentRoute.value.path, loaded: usePermissionStore().isRoutesLoaded, finished,
    }
    permissions.resolve({ data: ['monitor:dashboard'] })
    await navigation
    expect(whileMenusPending).toEqual({ path: '/login', loaded: false, finished: false })
    expect(whilePermissionsPending).toEqual({ path: '/login', loaded: false, finished: false })
    expect(router.currentRoute.value.path).toBe('/monitor/dashboard')
    expect(usePermissionStore().isRoutesLoaded).toBe(true)
    expect(mockLogout).not.toHaveBeenCalled()
  })

  it('preserves the requested dynamic URL including query and hash', async () => {
    getToken.mockReturnValue('valid-token')
    getMenus.mockResolvedValue({ data: [{
      path: '/system/user', name: 'system:user', component: 'views/system/User.vue',
    }] })
    getPermissions.mockResolvedValue({ data: ['system:user'] })
    await router.replace('/system/user?page=2#details')
    expect(router.currentRoute.value.fullPath).toBe('/system/user?page=2#details')
    expect(router.currentRoute.value.matched.at(-1).name).toBe('system:user')
    expect(getMenus).toHaveBeenCalledOnce()
  })

  it('does not log out on initialization failure and allows a retry', async () => {
    getToken.mockReturnValue('valid-token')
    const failure = new Error('Permission service unavailable')
    getMenus.mockResolvedValue({ data: [dashboardMenu] })
    getPermissions.mockRejectedValueOnce(failure)
    const result = await router.replace('/monitor/dashboard').then(() => null, error => error)
    expect(result).toBe(failure)
    expect(router.currentRoute.value.path).toBe('/login')
    expect(mockLogout).not.toHaveBeenCalled()
    expect(getToken()).toBe('valid-token')
    expect(usePermissionStore().isRoutesLoaded).toBe(false)
    getPermissions.mockResolvedValue({ data: ['monitor:dashboard'] })
    await router.replace('/monitor/dashboard')
    expect(router.currentRoute.value.path).toBe('/monitor/dashboard')
  })

  it('keeps a genuinely unauthorized user on 403 without logging out', async () => {
    getToken.mockReturnValue('valid-token')
    getMenus.mockResolvedValue({ data: [] })
    getPermissions.mockResolvedValue({ data: [] })
    await router.replace('/monitor/dashboard')
    expect(router.currentRoute.value.path).toBe('/403')
    expect(usePermissionStore().isRoutesLoaded).toBe(true)
    expect(mockLogout).not.toHaveBeenCalled()
  })

  it('returns to login if the session expires during initialization', async () => {
    getToken.mockReturnValue('valid-token')
    const menus = deferred()
    getMenus.mockReturnValue(menus.promise)
    getPermissions.mockResolvedValue({ data: [] })
    const navigation = router.replace('/monitor/dashboard')
    await vi.waitFor(() => expect(getMenus).toHaveBeenCalledOnce())
    getToken.mockReturnValue(null)
    menus.resolve({ data: [dashboardMenu] })
    await navigation
    expect(router.currentRoute.value.path).toBe('/login')
    expect(usePermissionStore().isRoutesLoaded).toBe(false)
  })

  it('uses one initialization for concurrent navigations and keeps the latest target', async () => {
    getToken.mockReturnValue('valid-token')
    const menus = deferred()
    getMenus.mockReturnValue(menus.promise)
    getPermissions.mockResolvedValue({ data: ['monitor:dashboard', 'system:user'] })
    const first = router.replace('/monitor/dashboard')
    await vi.waitFor(() => expect(getMenus).toHaveBeenCalledOnce())
    const second = router.replace('/system/user?page=2')
    menus.resolve({ data: [dashboardMenu, {
      path: '/system/user', name: 'system:user', component: 'views/system/User.vue',
    }] })
    await Promise.all([first, second])
    expect(router.currentRoute.value.fullPath).toBe('/system/user?page=2')
    expect(getMenus).toHaveBeenCalledOnce()
    expect(getPermissions).toHaveBeenCalledOnce()
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
    // Home route has redirect: '/monitor/dashboard', so menus must cover the target path
    permStore.menus = [
      { path: '/monitor/dashboard', name: 'dashboard', meta: { title: '实时监控' } },
    ]
    permStore.isRoutesLoaded = true

    await router.push('/')
    // Home redirects to /monitor/dashboard; permission check should allow it
    expect(router.currentRoute.value.path).toBe('/monitor/dashboard')
  })
})

/**
 * 刷新页面后 accessToken 会从 localStorage 恢复，但 userInfo 是纯内存状态。
 * 若初始化时不重新拉取当前用户，AppHeader 只能渲染兜底文案「用户」。
 */
describe('初始化时加载当前用户信息', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    getMenus.mockReset()
    getPermissions.mockReset()
    mockFetchUserInfo.mockReset()
    mockFetchUserInfo.mockResolvedValue({ username: 'admin', real_name: '管理员' })
    vi.spyOn(console, 'error').mockImplementation(() => {})
    resetRouter()
    getToken.mockReturnValue(null)
    await router.replace('/login')
  })

  afterEach(() => vi.restoreAllMocks())

  it('路由初始化时应拉取当前用户信息（刷新后不再回退到「用户」）', async () => {
    getToken.mockReturnValue('valid-token')
    getMenus.mockResolvedValue({ data: [dashboardMenu] })
    getPermissions.mockResolvedValue({ data: ['monitor:dashboard'] })

    await router.replace('/monitor/dashboard')

    expect(mockFetchUserInfo).toHaveBeenCalledOnce()
    expect(router.currentRoute.value.path).toBe('/monitor/dashboard')
  })

  it('应在用户信息返回后才放行导航，避免头部先渲染兜底文案', async () => {
    getToken.mockReturnValue('valid-token')
    getMenus.mockResolvedValue({ data: [dashboardMenu] })
    getPermissions.mockResolvedValue({ data: ['monitor:dashboard'] })
    const profile = deferred()
    mockFetchUserInfo.mockReturnValue(profile.promise)

    let finished = false
    const navigation = router.replace('/monitor/dashboard').then(() => { finished = true })
    await vi.waitFor(() => expect(mockFetchUserInfo).toHaveBeenCalledOnce())
    const whileProfilePending = { path: router.currentRoute.value.path, finished }

    profile.resolve({ username: 'admin', real_name: '管理员' })
    await navigation

    expect(whileProfilePending).toEqual({ path: '/login', finished: false })
    expect(router.currentRoute.value.path).toBe('/monitor/dashboard')
  })

  it('用户信息拉取失败时不得标记初始化完成，以便重试', async () => {
    getToken.mockReturnValue('valid-token')
    getMenus.mockResolvedValue({ data: [dashboardMenu] })
    getPermissions.mockResolvedValue({ data: ['monitor:dashboard'] })
    const failure = new Error('profile service unavailable')
    mockFetchUserInfo.mockRejectedValueOnce(failure)

    const result = await router.replace('/monitor/dashboard').then(() => null, (error) => error)

    expect(result).toBe(failure)
    expect(usePermissionStore().isRoutesLoaded).toBe(false)

    // 重试应能成功进入，且用户信息已就位
    await router.replace('/monitor/dashboard')
    expect(router.currentRoute.value.path).toBe('/monitor/dashboard')
    expect(mockFetchUserInfo).toHaveBeenCalledTimes(2)
  })
})
