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

    // 3. 生成动态路由
    const routes = generateRoutesFromMenus(menus.value)
    dynamicRoutes.value = routes

    // 4. 挂载到路由器
    // 使用一个 layout 路由作为父级容器
    const layoutRoute = {
      path: '/',
      name: 'LayoutRoot',
      component: () => import('@/components/Layout.vue'),
      redirect: menus.value[0]?.path || '/dashboard',
      children: routes,
    }
    router.addRoute(layoutRoute)

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
