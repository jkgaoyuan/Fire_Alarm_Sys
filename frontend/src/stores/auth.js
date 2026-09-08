import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getToken, setToken, removeToken } from '@/utils/auth'
import { login as loginApi, logout as logoutApi } from '@/api/auth'
import { getMe } from '@/api/user'

export const useAuthStore = defineStore('auth', () => {
  // State
  const accessToken = ref(getToken())
  const userInfo = ref(null)
  const isLoggedIn = computed(() => !!accessToken.value)

  // Actions
  async function login(credentials) {
    const res = await loginApi(credentials)
    const data = res.data
    if (data?.access_token) {
      accessToken.value = data.access_token
      setToken(data.access_token)
      // 缓存用户信息
      if (data.user) {
        userInfo.value = data.user
      }
      return data
    }
    throw new Error('登录响应格式异常')
  }

  async function fetchUserInfo() {
    const res = await getMe()
    userInfo.value = res.data
    return userInfo.value
  }

  async function logout() {
    try {
      await logoutApi()
    } catch {
      // 即使接口失败也清除本地状态
    } finally {
      accessToken.value = null
      userInfo.value = null
      removeToken()
    }
  }

  return {
    accessToken,
    userInfo,
    isLoggedIn,
    login,
    fetchUserInfo,
    logout,
  }
})
