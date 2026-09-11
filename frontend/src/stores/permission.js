import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getMenus, getPermissions } from '@/api/user'
import router from '@/router'
import { staticRoutes } from '@/router/staticRoutes'
import { generateRoutesFromMenus, collectPaths } from '@/utils/menu'

export const usePermissionStore = defineStore('permission', () => {
  // State
  const menus = ref([])
  const permissions = ref([])
  const dynamicRoutes = ref([])
  const isRoutesLoaded = ref(false)

  // Getters
  const flatMenuPaths = computed(() => collectPaths(menus.value))

  // Actions
  async function generateRoutes() {
    // 1. 获取菜单
    const menuRes = await getMenus()
    menus.value = menuRes.data || []

    // 2. 获取权限码列表
    const permRes = await getPermissions()
    permissions.value = permRes.data || []

    // 3. 生成动态路由（只包含后端返回的菜单项）
    const routes = generateRoutesFromMenus(menus.value)
    dynamicRoutes.value = routes

    // 4. 检查是否已经有 Layout 根路由存在（来自静态路由）
    const hasLayoutRoute = router.getRoutes().some(r => r.path === '/')
    
    if (!hasLayoutRoute) {
      // 如果没有，则创建默认的 Layout
      const layoutRoute = {
        path: '/',
        name: 'LayoutRoot',
        component: () => import('@/components/Layout.vue'),
        children: routes,
      }
      router.addRoute(layoutRoute)
    }

    // 404 兜底（必须最后添加）
    router.addRoute({
      path: '/:pathMatch(.*)*',
      name: 'NotFoundWildcard',
      redirect: '/404',
    })

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
    permissions,
    dynamicRoutes,
    isRoutesLoaded,
    flatMenuPaths,
    generateRoutes,
    resetPermission,
  }
})
