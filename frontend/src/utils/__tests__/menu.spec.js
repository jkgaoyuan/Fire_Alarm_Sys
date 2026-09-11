import { describe, it, expect } from 'vitest'
import { generateRoutesFromMenus, collectPaths, normalizeMenuForDisplay } from '../menu'

// Mock Vite 模块映射（测试中无需真实 import）
const mockModules = {
  '@/views/monitor/Dashboard.vue': () => Promise.resolve({ default: {} }),
  '@/views/system/User.vue': () => Promise.resolve({ default: {} }),
  '@/views/system/Role.vue': () => Promise.resolve({ default: {} }),
  '@/views/Level3.vue': () => Promise.resolve({ default: {} }),
}

const nestedMenus = [
  {
    path: '/system', name: 'system', component: 'Layout',
    meta: { title: 'System', icon: 'Setting' },
    children: [{
      path: '/system/user', name: 'system:user', component: 'views/system/User.vue',
      meta: { title: 'Users', icon: 'User' }, children: [],
    }],
  },
  {
    path: '/statistics/report', name: 'statistics:report', component: 'views/statistics/Report.vue',
    meta: { title: 'Reports', icon: 'Document' },
    children: [{
      path: '/statistics/device-status', name: 'statistics:device',
      component: 'views/statistics/DeviceStatus.vue',
      meta: { title: 'Devices', icon: 'Monitor' }, children: [],
    }],
  },
]

describe('normalizeMenuForDisplay', () => {
  it('keeps nested backend menus acyclic with isolated children', () => {
    const original = JSON.stringify(nestedMenus)
    const menus = normalizeMenuForDisplay(nestedMenus)
    expect(() => JSON.stringify(menus)).not.toThrow()
    expect(menus).toHaveLength(2)
    expect(menus[0].children).not.toBe(menus)
    expect(menus[0].children.map(node => node.path)).toEqual(['/system/user'])
    expect(menus[1].children.map(node => node.path)).toEqual(['/statistics/device-status'])
    expect(JSON.stringify(nestedMenus)).toBe(original)
  })

  it('normalizes paths at every level without changing the input', () => {
    const input = [{ path: 'system', children: [{ path: 'system/user' }] }]
    const menus = normalizeMenuForDisplay(input)
    expect(() => JSON.stringify(menus)).not.toThrow()
    expect(menus[0].path).toBe('/system')
    expect(menus[0].children[0].path).toBe('/system/user')
    expect(input[0].children[0].path).toBe('system/user')
    expect(normalizeMenuForDisplay([])).toEqual([])
  })
})

describe('generateRoutesFromMenus', () => {
  it('keeps non-Layout children acyclic and preserves backend metadata', () => {
    const original = JSON.stringify(nestedMenus)
    const routes = generateRoutesFromMenus(nestedMenus, mockModules)
    expect(() => JSON.stringify(routes)).not.toThrow()
    // Statistics/report has a child, so only parent + leaf routes are generated
    expect(routes.map(route => route.path)).toEqual(['/system/user', '/statistics/report'])
    
    expect(routes.length).toBe(2)
    expect(routes[0].name).toBe('system:user')
    expect(routes[1].name).toBe('statistics:report')
    expect(routes[1].children).toBeDefined()
    expect(routes[1].children.length).toBe(1)
    expect(routes[1].children[0].path).toBe('/statistics/device-status')
    expect(routes[1].children[0].name).toBe('statistics:device')
    expect(routes[1].meta.title).toBe('Reports')
    expect(routes[1].meta.icon).toBe('Document')
    expect(JSON.stringify(nestedMenus)).toBe(original)
  })

  it('keeps componentless nested groups acyclic', () => {
    const routes = generateRoutesFromMenus([{
      path: '/group', children: [{ path: '/group/leaf' }],
    }], mockModules)
    expect(() => JSON.stringify(routes)).not.toThrow()
    expect(routes).toHaveLength(1) // Only /group leaf is generated
    expect(routes[0].path).toBe('/group')
    expect(routes[0].children.length).toBe(1)
    expect(routes[0].children[0].path).toBe('/group/leaf')
  })
  it('应将叶子菜单生成为路由', () => {
    const menus = [
      {
        perm_code: 'monitor:dashboard',
        perm_name: '监控大屏',
        route_path: '/monitor/dashboard',
        component: 'views/monitor/Dashboard.vue',
        icon: 'Monitor',
      },
    ]
    const routes = generateRoutesFromMenus(menus, mockModules)

    expect(routes).toHaveLength(1)
    expect(routes[0].path).toBe('/monitor/dashboard')
    expect(routes[0].name).toBe('monitor:dashboard')
    expect(routes[0].meta.title).toBe('监控大屏')
    expect(routes[0].meta.icon).toBe('Monitor')
    expect(typeof routes[0].component).toBe('function')
  })

  it('应跳过 component 为 Layout 的父菜单，只展开子路由', () => {
    const menus = [
      {
        perm_code: 'system:management',
        perm_name: '系统管理',
        route_path: '/system',
        component: 'Layout',
        icon: 'Setting',
        children: [
          {
            perm_code: 'system:user',
            perm_name: '用户管理',
            route_path: '/system/user',
            component: 'views/system/User.vue',
            icon: 'User',
          },
          {
            perm_code: 'system:role',
            perm_name: '角色管理',
            route_path: '/system/role',
            component: 'views/system/Role.vue',
            icon: 'Role',
          },
        ],
      },
    ]
    const routes = generateRoutesFromMenus(menus, mockModules)

    // 父菜单不应生成路由，只有 2 个子路由
    expect(routes).toHaveLength(2)
    expect(routes.some((r) => r.path === '/system')).toBe(false)
    expect(routes[0].path).toBe('/system/user')
    expect(routes[1].path).toBe('/system/role')
  })

  it('应支持多级嵌套菜单', () => {
    const menus = [
      {
        perm_code: 'level1',
        route_path: '/level1',
        component: 'Layout',
        children: [
          {
            perm_code: 'level2',
            route_path: '/level2',
            component: 'Layout',
            children: [
              {
                perm_code: 'level3',
                route_path: '/level3',
                component: 'views/Level3.vue',
              },
            ],
          },
        ],
      },
    ]
    const routes = generateRoutesFromMenus(menus, mockModules)

    // 中间两层 Layout 都应跳过，最终只剩叶子节点
    expect(routes).toHaveLength(1)
    expect(routes[0].path).toBe('/level3')
  })

  it('没有 component 的菜单应生成无 component 的路由', () => {
    const menus = [
      {
        perm_code: 'empty:menu',
        perm_name: '空菜单',
        route_path: '/empty',
      },
    ]
    const routes = generateRoutesFromMenus(menus, mockModules)

    expect(routes).toHaveLength(1)
    expect(routes[0].path).toBe('/empty')
    expect(routes[0].component).toBeUndefined()
  })

  it('空菜单数组应返回空路由数组', () => {
    expect(generateRoutesFromMenus([], mockModules)).toEqual([])
  })
})

describe('collectPaths', () => {
  it('应收集所有菜单路径（含嵌套）', () => {
    const menus = [
      { route_path: '/a' },
      {
        route_path: '/b',
        children: [
          { route_path: '/b/1' },
          { route_path: '/b/2' },
        ],
      },
    ]
    const paths = collectPaths(menus)

    expect(paths).toHaveLength(4)
    expect(paths).toContain('/a')
    expect(paths).toContain('/b')
    expect(paths).toContain('/b/1')
    expect(paths).toContain('/b/2')
  })

  it('应兼容 path 字段（当 route_path 不存在时）', () => {
    const menus = [{ path: '/legacy' }]
    expect(collectPaths(menus)).toContain('/legacy')
  })

  it('空数组应返回空数组', () => {
    expect(collectPaths([])).toEqual([])
  })
})
