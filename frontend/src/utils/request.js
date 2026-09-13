import axios from 'axios'
import { getToken, setToken, removeToken, isTokenExpiringSoon } from './auth'
import { ElMessage } from 'element-plus'

const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

// 普通请求实例
const request = axios.create({
  baseURL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 用于刷新的独立实例（需要携带 Cookie）
const refreshInstance = axios.create({
  baseURL,
  timeout: 10000,
  withCredentials: true,
})

// 并发刷新控制：单一 Promise 缓存
let refreshingPromise = null

function doRefreshToken() {
  if (!refreshingPromise) {
    refreshingPromise = refreshInstance
      .post('/auth/refresh')
      .then((res) => {
        const data = res.data?.data
        if (data?.access_token) {
          setToken(data.access_token)
          return data.access_token
        }
        throw new Error('刷新失败：响应中无 access_token')
      })
      .catch((err) => {
        removeToken()
        window.location.href = '/login'
        throw err
      })
      .finally(() => {
        refreshingPromise = null
      })
  }
  return refreshingPromise
}

// 请求拦截器
request.interceptors.request.use(
  async (config) => {
    const token = getToken()
    if (token) {
      // 主动刷新检查：Token 即将过期时先刷新
      if (isTokenExpiringSoon(token, 300) && config.url !== '/auth/refresh') {
        try {
          const newToken = await doRefreshToken()
          config.headers.Authorization = `Bearer ${newToken}`
        } catch {
          // doRefreshToken 内部已处理跳转
        }
      } else {
        config.headers.Authorization = `Bearer ${token}`
      }
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器
request.interceptors.response.use(
  (response) => {
    const { data } = response
    // 统一响应格式：{ code, message, data, timestamp }
    if (data && typeof data.code === 'number') {
      if (data.code >= 200 && data.code < 300) {
        return data
      }
      // 业务错误（非 401/403）由调用方处理
      return Promise.reject(data)
    }
    return data
  },
  async (error) => {
    const { response, config } = error
    if (!response) {
      ElMessage.error('网络异常，请检查网络连接')
      return Promise.reject(error)
    }

    const status = response.status
    const url = config?.url

    // 401 兜底刷新（主动刷新遗漏或失败时）
    if (status === 401 && url !== '/auth/refresh') {
      try {
        const newToken = await doRefreshToken()
        // 重试原请求
        config.headers.Authorization = `Bearer ${newToken}`
        return request(config)
      } catch {
        // doRefreshToken 内部已处理跳转
        return Promise.reject(error)
      }
    }

    // 403 无权限
    if (status === 403) {
      ElMessage.error('无权限访问')
      return Promise.reject(error)
    }

    // 其他 HTTP 错误
    const msg = response.data?.message || `请求失败 (${status})`
    ElMessage.error(msg)
    return Promise.reject(error)
  }
)

export default request
