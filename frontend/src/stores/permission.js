import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getMenus, getPermissions } from '@/api/user'
import router from '@/router'
import { staticRoutes } from '@/router/staticRoutes'
import { generateRoutesFromMenus, collectPaths, normalizeMenuForDisplay } from '@/utils/menu'

export const usePermissionStore = defineStore('permission', () => {
  // State
  const menus = ref([])  // 原始菜单数据（后端返回）
  const permissions = ref([])
  const dynamicRoutes = ref([])
  const isRoutesLoaded = ref(false)

  // Getters
  const flatMenuPaths = computed(() => collectPaths(menus.value))
  
  // 用于 el-menu 显示的归一化菜单（路径不带前导斜杠）
  const displayMenus = computed(() => {
    return menus.value.length > 0 ? normalizeMenuForDisplay(menus.value) : []
  })

  // Actions
  async function generateRoutes() {
    // 1. 获取菜单
    const menuRes = await getMenus()
    const rawMenus = menuRes.data || []
    menus.value = rawMenus

    // 2. 获取权限码列表
    const permRes = await getPermissions()
    permissions.value = permRes.data || []

    // 3. 生成动态路由（只包含后端返回的菜单项）
    const routes = generateRoutesFromMenus(menus.value)
    dynamicRoutes.value = routes

    console.log('[Permission Store] Generated routes:', routes.map(r => `${r.path} (${r.name})`))
    console.log('[Permission Store] All available routes before adding:', router.getRoutes().map(r => `${r.path} [${r.name}]`))

    // 4. Add generated routes as children of the Home route so they share Layout.
    // All business pages must be under '/' to keep the sidebar mounted.
    console.log('[Permission Store] Adding', routes.length, 'dynamic routes under Home')

    routes.forEach(route => {
      router.addRoute('Home', route)
      console.log(`  [Permission Store] Added dynamic route: ${route.path}`)
    })

    // 5. 404 fallback (must be added last for wildcard matching)
    router.addRoute({
      path: '/:pathMatch(.*)*',
      name: 'NotFoundWildcard',
      component: () => import('@/views/error/404.vue'),
    })

    console.log('[Permission Store] All routes after generation:', router.getRoutes().map(r => `${r.path} (${r.name})`))
    
    // Force Vue to re-render any components using permission store state
    // This ensures menu reflects new routes immediately
    console.log('[Permission Store] Routes loaded, triggering updates...')

    isRoutesLoaded.value = true
    return routes
  }

  function resetPermission() {
    menus.value = []
    permissions.value = []
    dynamicRoutes.value = []
    isRoutesLoaded.value = false
  }

  return {
    menus,
    displayMenus,  // 用于 el-menu 显示的归一化菜单
    permissions,
    dynamicRoutes,
    isRoutesLoaded,
    flatMenuPaths,
    generateRoutes,
    resetPermission,
  }
})
