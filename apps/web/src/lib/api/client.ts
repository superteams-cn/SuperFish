import axios, { type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios'
import i18n from '@/i18n'

import type { ApiEnvelope } from './types'
import { clearTokens, getAccessToken, getRefreshToken, setTokens } from '@/lib/auth-storage'

// 创建 axios 实例
const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001',
  timeout: 300000, // 5 分钟超时（本体生成可能需要较长时间）
  headers: {
    'Content-Type': 'application/json',
  },
})

// 401（会话失效且刷新失败）时由 AuthProvider 注册回调：清状态 + 弹登录框。
let unauthorizedHandler: (() => void) | null = null
export function setUnauthorizedHandler(fn: (() => void) | null) {
  unauthorizedHandler = fn
}

// 请求拦截器：附带当前语言 + Bearer 令牌
service.interceptors.request.use(
  (config) => {
    config.headers['Accept-Language'] = i18n.language
    const token = getAccessToken()
    if (token) config.headers['Authorization'] = `Bearer ${token}`
    return config
  },
  (error) => {
    console.error('Request error:', error)
    return Promise.reject(error)
  },
)

// 单飞刷新：并发 401 只发一次 refresh，其余等待同一结果。
let refreshPromise: Promise<boolean> | null = null
async function tryRefreshToken(): Promise<boolean> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) return false
  if (!refreshPromise) {
    refreshPromise = axios
      .create({ baseURL: service.defaults.baseURL })
      .post('/api/auth/refresh', { refresh_token: refreshToken })
      .then((resp) => {
        const data = resp.data?.data
        if (data?.access_token) {
          setTokens(data.access_token, data.refresh_token)
          return true
        }
        return false
      })
      .catch(() => false)
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

// 响应拦截器：解包 data 并对 success=false 抛错
service.interceptors.response.use(
  (response) => {
    const res = response.data
    if (!res.success && res.success !== undefined) {
      console.error('API Error:', res.error || res.message || 'Unknown error')
      return Promise.reject(new Error(res.error || res.message || 'Error'))
    }
    return res
  },
  async (error) => {
    const original = error.config as
      | (InternalAxiosRequestConfig & { __isRetry?: boolean })
      | undefined
    const status = error.response?.status
    const url = original?.url || ''
    // 鉴权接口自身的 401（如密码错误）属正常表单错误，交给调用方，不触发刷新/弹框。
    const isAuthEndpoint = url.includes('/api/auth/')

    if (status === 401 && original && !isAuthEndpoint && !original.__isRetry) {
      const refreshed = await tryRefreshToken()
      if (refreshed) {
        original.__isRetry = true
        original.headers = original.headers || {}
        const token = getAccessToken()
        if (token) original.headers['Authorization'] = `Bearer ${token}`
        return service(original)
      }
      clearTokens()
      unauthorizedHandler?.()
    }

    // 归一化错误文案：FastAPI HTTPException 走 {detail}，业务信封走 {error}。
    // 统一抬到 error.message，调用方读 (err as Error).message 即可拿到本地化文案。
    const serverMsg = error.response?.data?.detail ?? error.response?.data?.error
    if (typeof serverMsg === 'string' && serverMsg) {
      error.message = serverMsg
    }

    console.error('Response error:', error)
    if (error.code === 'ECONNABORTED' && error.message.includes('timeout')) {
      console.error('Request timeout')
    }
    if (error.message === 'Network Error') {
      console.error('Network error - please check your connection')
    }
    return Promise.reject(error)
  },
)

/** 带指数退避重试的请求包装。 */
export async function requestWithRetry<T>(
  requestFn: () => Promise<T>,
  maxRetries = 3,
  delay = 1000,
): Promise<T> {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await requestFn()
    } catch (error) {
      if (i === maxRetries - 1) throw error
      console.warn(`Request failed, retrying (${i + 1}/${maxRetries})...`)
      await new Promise((resolve) => setTimeout(resolve, delay * Math.pow(2, i)))
    }
  }
  // 理论上不可达
  throw new Error('requestWithRetry: unreachable')
}

// 响应拦截器已把信封解包，故以下助手在运行期 resolve 为 ApiEnvelope<T>。
// 用 `unknown` 中转完成类型断言，避免在每个调用点重复书写。
export const http = {
  get: <T>(url: string, config?: AxiosRequestConfig): Promise<ApiEnvelope<T>> =>
    service.get(url, config) as unknown as Promise<ApiEnvelope<T>>,
  post: <T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<ApiEnvelope<T>> =>
    service.post(url, data, config) as unknown as Promise<ApiEnvelope<T>>,
  delete: <T>(url: string, config?: AxiosRequestConfig): Promise<ApiEnvelope<T>> =>
    service.delete(url, config) as unknown as Promise<ApiEnvelope<T>>,
}

export default service
