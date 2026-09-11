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

// ✅ 完整修复的路由守卫（P0-005）
// 使用非 async 模式，直接返回字符串或布尔值
router.beforeEach((to, from) => {
  // 日志：记录每次路由跳转
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

  // 菜单未加载时，先获取菜单并生成动态路由
  if (!permStore.isRoutesLoaded) {
    try {
      console.log('[Router Guard] Routes not loaded, fetching menus...')
      
      // ✅ 关键修复 1: 立即设置标志位，避免重复调用
      permStore.isRoutesLoaded = true
      
      // ✅ 关键修复 2: 异步生成路由（不阻塞导航）
      permStore.generateRoutes().catch(err => {
        console.error('[Router Guard] Failed to load routes:', err)
        const authStore = useAuthStore()
        authStore.logout().then(() => {
          console.log('[Router Guard] Redirecting to login due to error')
          window.location.href = '/login'
        })
      })
      
      // ✅ 关键修复 3: 直接返回 true，让当前导航继续
      // ❌ 不要在后面再次调用 next() 或返回重定向，会导致无限循环！
      console.log('[Router Guard] Allowing initial navigation, routes loading in background')
      return true
    } catch (err) {
      console.error('[Router Guard] Critical error:', err)
      const authStore = useAuthStore()
      authStore.logout()
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
