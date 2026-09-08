import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePermissionStore } from '../permission'

vi.mock('@/router', () => {
  const mockAddRoute = vi.fn()
  return { default: { addRoute: mockAddRoute } }
})

vi.mock('@/api/user', () => ({
  getMenus: vi.fn(),
  getPermissions: vi.fn(),
}))

import { getMenus, getPermissions } from '@/api/user'

// 获取 mockAddRoute 引用（必须在 import 之后）
import router from '@/router'
const mockAddRoute = router.addRoute

describe('permission store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('初始状态应正确', () => {
    const store = usePermissionStore()
    expect(store.menus).toEqual([])
    expect(store.permissions).toEqual([])
    expect(store.dynamicRoutes).toEqual([])
    expect(store.isRoutesLoaded).toBe(false)
    expect(store.flatMenuPaths).toEqual([])
  })

  it('generateRoutes 应获取菜单并生成动态路由', async () => {
    const store = usePermissionStore()
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

    const routes = await store.generateRoutes()

    expect(store.menus).toHaveLength(1)
    expect(store.permissions).toEqual(['monitor:dashboard'])
    expect(store.isRoutesLoaded).toBe(true)
    expect(routes).toHaveLength(1)
    expect(routes[0].path).toBe('/monitor/dashboard')
    // layout 路由 + 404 兜底
    expect(mockAddRoute).toHaveBeenCalledTimes(2)
  })

  it('generateRoutes 的 layout redirect 应指向第一个菜单路径', async () => {
    const store = usePermissionStore()
    getMenus.mockResolvedValue({
      data: [{ path: '/dashboard', name: 'dashboard', meta: { title: '首页' } }],
    })
    getPermissions.mockResolvedValue({ data: [] })

    await store.generateRoutes()

    const layoutCall = mockAddRoute.mock.calls.find(
      (call) => call[0].path === '/'
    )
    expect(layoutCall).toBeDefined()
    expect(layoutCall[0].redirect).toBe('/dashboard')
  })

  it('generateRoutes 无菜单时应 redirect 到 /dashboard', async () => {
    const store = usePermissionStore()
    getMenus.mockResolvedValue({ data: [] })
    getPermissions.mockResolvedValue({ data: [] })

    await store.generateRoutes()

    const layoutCall = mockAddRoute.mock.calls.find(
      (call) => call[0].path === '/'
    )
    expect(layoutCall[0].redirect).toBe('/dashboard')
  })

  it('resetPermission 应清空所有状态', () => {
    const store = usePermissionStore()
    store.menus = [{ path: '/a' }]
    store.permissions = ['a:view']
    store.dynamicRoutes = [{ path: '/a' }]
    store.isRoutesLoaded = true

    store.resetPermission()

    expect(store.menus).toEqual([])
    expect(store.permissions).toEqual([])
    expect(store.dynamicRoutes).toEqual([])
    expect(store.isRoutesLoaded).toBe(false)
    expect(store.flatMenuPaths).toEqual([])
  })
})
