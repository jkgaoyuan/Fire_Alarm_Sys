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
  // 日志：记录每次路由跳转
  console.log('[Router Guard] Navigation:', from.path, '->', to.path)

  // 白名单直接放行
  if (whiteList.includes(to.path)) {
    console.log('[Router Guard] Whitelisted path:', to.path)
    return next()
  }

  const token = getToken()
  if (!token) {
    console.log('[Router Guard] No token, redirect to login')
    return next('/login')
  }

  const permStore = usePermissionStore()

  // 菜单未加载时，先获取菜单并生成动态路由
  if (!permStore.isRoutesLoaded) {
    try {
      console.log('[Router Guard] Routes not loaded, fetching menus...')
      await permStore.generateRoutes()
      console.log('[Router Guard] Routes generated, reloading navigation with replace')
      // 动态路由已添加，需要重新触发导航以匹配新路由
      // 使用 replace: true 避免历史记录堆积
      // 关键修改：直接 next() 而不是 next({...to, replace: true}) 以避免路径解析问题
      return next()
    } catch (err) {
      console.error('[Router Guard] Failed to load routes:', err)
      // 获取菜单失败，可能是 Token 过期，清除后跳转登录
      const authStore = useAuthStore()
      await authStore.logout()
      return next('/login')
    }
  }

  console.log('[Router Guard] Checking permission for path:', to.path)
  // 校验目标路由权限
  // 取最后一个匹配的路由路径（避开 layout 父路由 '/'）
  const checkPath = to.matched[to.matched.length - 1]?.path || to.path
  console.log('[Router Guard] Check path:', checkPath)
  
  const hasPermission =
    permStore.flatMenuPaths.includes(checkPath) ||
    to.path === '/' ||
    whiteList.includes(to.path)

  console.log('[Router Guard] Has permission:', hasPermission)
  if (hasPermission) {
    console.log('[Router Guard] Permission granted')
    return next()
  }

  console.log('[Router Guard] No permission, redirect to 403')
  return next('/403')
})

export default router
