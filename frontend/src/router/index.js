import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '@/utils/auth'
import { useAuthStore } from '@/stores/auth'
import { usePermissionStore } from '@/stores/permission'
import { staticRoutes } from './staticRoutes'

const whiteList = ['/login', '/403', '/404']

const router = createRouter({
  history: createWebHistory(),
  routes: staticRoutes,
  scrollBehavior() {
    return { top: 0 }
  },
})

// 完整路由守卫（P0-005）
router.beforeEach(async (to, from, next) => {
  // 白名单直接放行
  if (whiteList.includes(to.path)) {
    return next()
  }

  const token = getToken()
  if (!token) {
    return next('/login')
  }

  const permStore = usePermissionStore()

  // 菜单未加载时，先获取菜单并生成动态路由
  if (!permStore.isRoutesLoaded) {
    try {
      await permStore.generateRoutes()
      // 动态路由已添加，需要重新触发导航以匹配新路由
      return next({ ...to, replace: true })
    } catch (err) {
      // 获取菜单失败，可能是 Token 过期，清除后跳转登录
      const authStore = useAuthStore()
      await authStore.logout()
      return next('/login')
    }
  }

  // 校验目标路由权限
  // 取最后一个匹配的路由路径（避开 layout 父路由 '/'）
  const checkPath = to.matched[to.matched.length - 1]?.path || to.path
  const hasPermission =
    permStore.flatMenuPaths.includes(checkPath) ||
    to.path === '/' ||
    whiteList.includes(to.path)

  if (hasPermission) {
    return next()
  }

  return next('/403')
})

export default router
