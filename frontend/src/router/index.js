import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '@/utils/auth'
import { usePermissionStore } from '@/stores/permission'
import { staticRoutes } from './staticRoutes'

const whiteList = ['/login', '/403', '/404']

// ✅ Singleton promise ensures concurrent navigations share one initialization.
// The promise is automatically cleared after completion so that a subsequent
// logout → login cycle can re-initialize cleanly.
let initPromise = null

async function initializeRoutes() {
  const permStore = usePermissionStore()
  if (permStore.isRoutesLoaded) return

  if (!initPromise) {
    initPromise = permStore.generateRoutes().finally(() => {
      initPromise = null
    })
  }
  await initPromise
}

export function resetInitializeRoutes() {
  initPromise = null
}

const router = createRouter({
  history: createWebHistory(),
  routes: staticRoutes,
  scrollBehavior() {
    return { top: 0 }
  },
})

// ✅ 完整修复的路由守卫（P0-005）
router.beforeEach(async (to, from) => {
  // 白名单直接放行
  if (whiteList.includes(to.path)) {
    return true
  }

  const token = getToken()
  if (!token) {
    return '/login'
  }

  const permStore = usePermissionStore()

  // 如果路由未加载，等待初始化完成后再检查
  if (!permStore.isRoutesLoaded) {
    try {
      await initializeRoutes()

      // Re-check token after async initialization (session may have expired)
      if (!getToken()) {
        permStore.resetPermission()
        return '/login'
      }

      // Root path is already in staticRoutes, no need to re-navigate
      if (to.path === '/') {
        return true
      }

      // If the current navigation has no matched routes (production: dynamic routes
      // not yet added), trigger a re-navigation so Vue Router can match the newly
      // added routes. In tests, static routes are pre-registered, so to.matched is
      // already populated and we can fall through to permission checks below.
      if (to.matched.length === 0) {
        return to.fullPath
      }
    } catch (err) {
      // Propagate error so callers (e.g., tests) can catch it and decide retry
      throw err
    }
  }

  // 路由已加载完成，进行正常权限校验

  // 根路径直接允许（会显示 dashboard）
  if (to.path === '/') {
    return true
  }

  // 校验目标路由权限
  // 优先使用 matched 中最后一层的路由定义 path（支持参数路由如 /device/:id），
  // 回退到 to.path（无匹配时的兜底）
  const checkPath = to.matched.at(-1)?.path || to.path

  const hasPermission = permStore.flatMenuPaths.includes(checkPath)

  if (hasPermission) {
    return true
  }

  return '/403'
})

export default router
