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

/** 根据用户权限返回默认落地页（第一个可用菜单），无权限则返回 /403 */
function getDefaultPath(permStore) {
  console.log('[Router Debug] menus:', JSON.parse(JSON.stringify(permStore.menus)))
  console.log('[Router Debug] flatMenuPaths:', permStore.flatMenuPaths)
  const firstPath = permStore.flatMenuPaths.find((p) => p !== '/')
  console.log('[Router Debug] firstPath:', firstPath)
  return firstPath || '/403'
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
  console.log('[Router Debug] beforeEach triggered:', to.path, 'isRoutesLoaded:', usePermissionStore().isRoutesLoaded)
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

      // 根路径动态重定向到用户第一个可用菜单，避免写死 /monitor/dashboard
      if (to.path === '/') {
        return getDefaultPath(permStore)
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

  // 根路径动态重定向到用户第一个可用菜单
  if (to.path === '/') {
    return getDefaultPath(permStore)
  }

  // 校验目标路由权限
  // 优先使用 matched 中最后一层的路由定义 path（支持参数路由如 /device/:id），
  // 回退到 to.path（无匹配时的兜底）
  const checkPath = to.matched.at(-1)?.path || to.path

  // 隐藏子页面复用父菜单权限（如 /inspection/plan 从 /inspection/task 跳转进入）
  const subPagePermissionMap = {
    '/inspection/plan': '/inspection/task',
  }
  const effectivePath = subPagePermissionMap[checkPath] || checkPath

  const hasPermission = permStore.flatMenuPaths.includes(effectivePath)

  if (hasPermission) {
    return true
  }

  return '/403'
})

export default router
