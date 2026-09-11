import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '@/utils/auth'
import { useAuthStore } from '@/stores/auth'
import { usePermissionStore } from '@/stores/permission'
import { staticRoutes } from './staticRoutes'

const whiteList = ['/login', '/403', '/404']

// ✅ Initialize routes before any navigation (shared across all route guards)
const initializeRoutes = (() => {
  let initPromise = null
  return async () => {
    if (!initPromise) {
      initPromise = (async () => {
        const permStore = usePermissionStore()
        if (!permStore.isRoutesLoaded) {
          console.log('[Router Guard] Starting route initialization...')
          try {
            await permStore.generateRoutes()
            console.log('[Router Guard] Routes initialized successfully')
          } catch (err) {
            console.error('[Router Guard] Route initialization failed:', err)
            // Don't logout user on initialization failure
          }
        }
      })()
    }
    return initPromise
  }
})()

const router = createRouter({
  history: createWebHistory(),
  routes: staticRoutes,
  scrollBehavior() {
    return { top: 0 }
  },
})

// ✅ 完整修复的路由守卫（P0-005）
// 使用非 async 模式，直接返回字符串或布尔值
router.beforeEach(async (to, from) => {
  console.log('[Router Guard] Navigation:', from.path, '->', to.path)

  // 白名单直接放行
  if (whiteList.includes(to.path)) {
    console.log('[Router Guard] Whitelisted path:', to.path)
    return true
  }

  const token = getToken()
  if (!token) {
    console.log('[Router Guard] No token, redirect to login')
    return '/login'
  }

  const permStore = usePermissionStore()

  // 如果路由未加载，等待初始化完成后再检查
  if (!permStore.isRoutesLoaded) {
    console.log('[Router Guard] Routes not loaded, waiting for initialization...')
    
    try {
      // Wait for initialization to complete
      const init = initializeRoutes()
      await init()
      
      // Re-check permission after routes are loaded
      console.log('[Router Guard] Initialization complete, re-checking permission for:', to.path)
      
      // Now check permission again with full route list
      if (to.path === '/') {
        console.log('[Router Guard] Root path allowed')
        return true
      }
      
      const hasPermission = permStore.flatMenuPaths.includes(to.path)
      console.log('[Router Guard] Has permission:', hasPermission)
      
      if (hasPermission) {
        console.log('[Router Guard] Permission granted')
        return true
      }
      
      console.log('[Router Guard] No permission, redirect to 403')
      return '/403'
    } catch (err) {
      console.error('[Router Guard] Initialization error:', err)
      // On initialization failure, redirect to login for manual recovery
      const authStore = useAuthStore()
      authStore.logout().then(() => {
        console.log('[Router Guard] Logged out user due to initialization error')
      })
      return '/login'
    }
  }

  // 路由已加载完成，进行正常权限校验
  console.log('[Router Guard] Checking permission for path:', to.path)
  
  // 根路径直接允许（会显示 dashboard）
  if (to.path === '/') {
    console.log('[Router Guard] Root path allowed')
    return true
  }
  
  // 校验目标路由权限
  // ✅ 直接使用 to.path，而不是 to.matched[x].path（这是导致栈溢出的原因）
  const checkPath = to.path
  console.log('[Router Guard] Check path:', checkPath)
  
  const hasPermission = permStore.flatMenuPaths.includes(checkPath)

  console.log('[Router Guard] Has permission:', hasPermission)
  if (hasPermission) {
    console.log('[Router Guard] Permission granted')
    return true
  }

  console.log('[Router Guard] No permission, redirect to 403')
  return '/403'
})

export default router
